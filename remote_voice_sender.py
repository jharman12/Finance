from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import queue
import socket
import ssl
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from finance_app.services.voice.discovery import (
    RemoteVoiceDiscoveryBrowser,
    RemoteVoiceDiscoveryDevice,
    RemoteVoiceDiscoveryPublisher,
    SERVICE_TYPE_SENDER,
)
from finance_app.services.voice.pairing import PairingCodeGenerator
from finance_app.services.voice.remote_config import RemoteVoiceConfigManager
from finance_app.services.voice.vad_endpointing import VoiceActivityEndpoint
from finance_app.services.voice.wake_detector import OpenWakeWordDetector, VoskPhraseWakeDetector


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _log(message: str) -> None:
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


def _debug_enabled() -> bool:
    return _bool_env("FINANCE_APP_REMOTE_DEBUG", False)


def _debug(message: str) -> None:
    if not _debug_enabled():
        return
    _log(f"DEBUG: {message}")


def _token_fingerprint(token: str) -> str:
    cleaned = token.strip()
    if not cleaned:
        return ""
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:6]


@dataclass(slots=True)
class SenderConfig:
    host: str
    port: int
    token: str
    source_id: str
    ca_cert_path: str
    tls_server_name: str | None
    wake_phrase: str
    wake_mode: str
    vosk_model_path: str | None
    openwakeword_model_path: str | None
    wake_threshold: float
    sample_rate: int
    blocksize: int
    preroll_ms: int
    post_wake_grace_ms: int
    max_stream_seconds: float
    cooldown_seconds: float
    endpoint_min_speech_ms: int
    endpoint_silence_ms: int
    endpoint_max_utterance_ms: int
    energy_threshold: float


class SecureRemoteAudioConnection:
    def __init__(self, config: SenderConfig, pairing_code: str | None = None, allow_untrusted: bool = False) -> None:
        self.config = config
        self.pairing_code = pairing_code or ""
        self.allow_untrusted = allow_untrusted
        self.paired_acknowledged = False
        self.pairing_required = False
        self.server_token_fingerprint = ""
        self._socket: ssl.SSLSocket | None = None
        self._seq_no = 0

    def connect(self) -> None:
        if len(self.config.token) < 16:
            raise RuntimeError("Remote audio token must be at least 16 characters long.")

        cafile = Path(self.config.ca_cert_path).expanduser() if self.config.ca_cert_path else None
        use_verified_tls = cafile is not None and cafile.exists() and not self.allow_untrusted

        if use_verified_tls:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(cafile))
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        _debug(
            f"Connecting to {self.config.host}:{self.config.port} with TLS server name "
            f"'{self.config.tls_server_name or self.config.host}'"
        )
        raw_socket = socket.create_connection((self.config.host, self.config.port), timeout=5.0)
        try:
            server_name = self.config.tls_server_name or self.config.host
            self._socket = context.wrap_socket(raw_socket, server_hostname=server_name)
            if self.allow_untrusted:
                self._persist_peer_certificate()
            _debug("TLS handshake complete. Sending hello message.")
            self._send_json(
                {
                    "type": "hello",
                    "token": self.config.token,
                    "source_id": self.config.source_id,
                    "pairing_code": self.pairing_code,
                }
            )
            try:
                self._socket.settimeout(4.0)
                ack_raw = b""
                while b"\n" not in ack_raw:
                    part = self._socket.recv(4096)
                    if not part:
                        break
                    ack_raw += part
                if ack_raw:
                    line = ack_raw.split(b"\n", 1)[0].decode("utf-8", errors="ignore").strip()
                    _debug(f"hello_ack raw line: {line}")
                    if line:
                        ack_msg = json.loads(line)
                        if str(ack_msg.get("type", "")).strip().lower() == "hello_ack":
                            self.paired_acknowledged = bool(ack_msg.get("paired", False))
                            self.pairing_required = bool(ack_msg.get("pairing_required", False))
                            self.server_token_fingerprint = str(ack_msg.get("server_token_fingerprint", "")).strip()
                            _debug(
                                "hello_ack parsed: "
                                f"paired={self.paired_acknowledged}, pairing_required={self.pairing_required}, "
                                f"server_token_fp={self.server_token_fingerprint or '(none)'}"
                            )
                        else:
                            _debug(f"Unexpected ack message type: {ack_msg.get('type')}")
                else:
                    _debug("No hello_ack payload received before socket closed.")
            except Exception:
                self.paired_acknowledged = False
                self.pairing_required = False
                _debug("Failed to read hello_ack; defaulting paired=false.")
            finally:
                try:
                    self._socket.settimeout(None)
                except Exception:
                    pass
            _debug("Hello message sent.")
        except Exception:
            raw_socket.close()
            self._socket = None
            raise

    def _persist_peer_certificate(self) -> None:
        sock = self._socket
        if sock is None:
            return
        try:
            peer_cert_der = sock.getpeercert(binary_form=True)
        except Exception:
            return
        if not peer_cert_der:
            return

        config_dir = Path.home() / ".finance-voice"
        config_dir.mkdir(parents=True, exist_ok=True)
        receiver_cert_path = config_dir / "receiver-ca-cert.pem"
        receiver_cert_path.write_text(ssl.DER_cert_to_PEM_cert(peer_cert_der), encoding="utf-8")
        self.config.ca_cert_path = str(receiver_cert_path)

    def send_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        if self._socket is None:
            raise RuntimeError("Remote audio connection is not open.")

        self._seq_no += 1
        if self._seq_no == 1 or (self._seq_no % 50) == 0:
            _debug(f"Sending audio seq={self._seq_no} bytes={len(chunk)}")
        self._send_json(
            {
                "type": "audio",
                "seq_no": self._seq_no,
                "sent_at_ms": int(time.time() * 1000),
                "audio_b64": base64.b64encode(chunk).decode("ascii"),
            }
        )

    def close(self) -> None:
        sock = self._socket
        self._socket = None
        self._seq_no = 0
        if sock is None:
            return
        try:
            sock.close()
        except Exception:
            return

    def _send_json(self, payload: dict[str, object]) -> None:
        sock = self._socket
        if sock is None:
            raise RuntimeError("Remote audio connection is not open.")
        encoded = (json.dumps(payload, ensure_ascii=True) + "\n").encode("utf-8")
        sock.sendall(encoded)


class RemoteWakeStreamSender:
    def __init__(self, config: SenderConfig) -> None:
        self.config = config
        self.endpoint = VoiceActivityEndpoint(
            min_speech_ms=config.endpoint_min_speech_ms,
            end_silence_ms=config.endpoint_silence_ms,
            max_utterance_ms=config.endpoint_max_utterance_ms,
            energy_threshold=config.energy_threshold,
        )
        self.wake_detector = self._build_wake_detector()
        preroll_chunks = max(1, int(config.preroll_ms / max(1, int((config.blocksize * 1000) / config.sample_rate))))
        self._preroll_buffer: deque[bytes] = deque(maxlen=preroll_chunks)
        self._audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=128)
        self._stop_event = threading.Event()
        self._connection: SecureRemoteAudioConnection | None = None
        self._cooldown_until = 0.0
        self._stream_started_at = 0.0
        self._grace_deadline = 0.0
        self._grace_reset_pending = False
        self._discovery_browser: RemoteVoiceDiscoveryBrowser | None = None
        self._discovery_ready = threading.Event()
        self._discovery_publisher: RemoteVoiceDiscoveryPublisher | None = None
        self._paired_with_main = False
        self._pair_probe_interval_seconds = 3.0
        self._last_pair_probe_at = 0.0
        self._pairing_code: str | None = None
        self._last_announced_pairing_code: str | None = None
        self._waiting_for_pair_notice_logged = False

    def run(self) -> int:
        try:
            import sounddevice as sd
        except ImportError:
            _log("Missing dependency: sounddevice. Install with `pip install sounddevice`.")
            return 2

        try:
            self.wake_detector.start()
        except Exception as exc:
            _log(f"Wake detector failed to start: {exc}")
            hint = self._wake_detector_start_hint()
            if hint:
                _log(hint)
            return 2

        self._discovery_browser = RemoteVoiceDiscoveryBrowser()
        if self._discovery_browser.start(on_device=self._handle_discovered_receiver, on_diagnostic=self._handle_discovery_diagnostic):
            _log("Browsing the local network for the Finance Voice Receiver.")
        elif not self.config.host:
            _log("mDNS discovery is unavailable. Set --host or FINANCE_APP_REMOTE_AUDIO_HOST manually.")

        self._discovery_publisher = RemoteVoiceDiscoveryPublisher(
            source_id=self.config.source_id,
            port=0,  # Sender doesn't listen; port is for identification only
            device_name=f"Remote Voice Sender ({self.config.source_id[:8]})",
            role="remote-sender",
            protocol_version="1",
        )
        # Override to use sender service type
        self._discovery_publisher.service_type = SERVICE_TYPE_SENDER
        if self._discovery_publisher.start():
            _log(f"Advertising as remote device '{self._discovery_publisher.device_name}' on the network.")
        else:
            _log("Failed to advertise on network; pairing from main app may not discover this device.")

        def callback(indata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
            del frames, time_info
            if status:
                _log(f"Mic status: {status}")
            try:
                self._audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        _log(
            f"Listening locally for wake phrase '{self.config.wake_phrase}' as {self.config.source_id}. "
            "Waiting for pairing before wake-word streaming is enabled."
        )

        try:
            with sd.RawInputStream(
                samplerate=self.config.sample_rate,
                blocksize=self.config.blocksize,
                dtype="int16",
                channels=1,
                callback=callback,
            ):
                while not self._stop_event.is_set():
                    try:
                        chunk = self._audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    self._handle_chunk(chunk)
        except KeyboardInterrupt:
            _log("Stopping remote voice sender.")
        except Exception as exc:
            _log(f"Microphone capture failed: {exc}")
            return 1
        finally:
            self._close_stream(reason="shutdown")
            if self._discovery_browser is not None:
                try:
                    self._discovery_browser.stop()
                except Exception:
                    pass
            if self._discovery_publisher is not None:
                try:
                    self._discovery_publisher.stop()
                except Exception:
                    pass
            try:
                self.wake_detector.stop()
            except Exception:
                pass

        return 0

    def _handle_discovery_diagnostic(self, payload: dict[str, object]) -> None:
        _debug(f"mDNS diagnostic: {payload}")

    def _handle_discovered_receiver(self, device: RemoteVoiceDiscoveryDevice) -> None:
        if device.role and device.role != "voice-receiver":
            return
        if not device.port:
            return
        if self.config.host and self.config.host not in {"127.0.0.1", "localhost"}:
            return
        if device.host:
            self.config.host = device.host
        if device.port:
            self.config.port = int(device.port)
        discovered_token = device.properties.get("auth_token", "").strip()
        if discovered_token:
            self.config.token = discovered_token
            _debug(
                "Pairing diagnostic: discovered receiver token fingerprint="
                f"{_token_fingerprint(self.config.token)}"
            )
        discovered_cert_path = device.properties.get("tls_cert_path", "").strip()
        if discovered_cert_path:
            self.config.ca_cert_path = discovered_cert_path
        discovered_tls_server_name = device.properties.get("tls_server_name", "").strip()
        if discovered_tls_server_name:
            self.config.tls_server_name = discovered_tls_server_name
        elif not self.config.tls_server_name and device.host:
            self.config.tls_server_name = device.host
        self._discovery_ready.set()
        self._waiting_for_pair_notice_logged = False
        _log(f"Discovered Finance Voice Receiver: {device.device_name} at {device.host}:{device.port}")
        self._attempt_pair_probe(force=True)

    def _handle_chunk(self, chunk: bytes) -> None:
        if not chunk:
            return

        self._preroll_buffer.append(chunk)
        now = time.monotonic()

        if not self._paired_with_main:
            self._attempt_pair_probe(now=now)
            return

        if self._connection is None:
            if now < self._cooldown_until:
                return
            if self._detect_wake(chunk):
                _debug("Wake detector returned true; opening remote stream.")
                self._open_stream(now)
            return

        try:
            self._connection.send_audio(chunk)
        except Exception as exc:
            _log(f"Remote audio send failed: {exc}")
            self._close_stream(reason="send_error")
            return

        if now >= (self._stream_started_at + self.config.max_stream_seconds):
            self._close_stream(reason="max_stream_seconds")
            return

        if now < self._grace_deadline:
            return

        if self._grace_reset_pending:
            self.endpoint.reset()
            self._grace_reset_pending = False

        decision = self.endpoint.process_chunk(chunk, self.config.sample_rate)
        if decision.utterance_complete:
            self._close_stream(reason=decision.reason or "silence")

    def _attempt_pair_probe(self, now: float | None = None, force: bool = False) -> None:
        if self._paired_with_main:
            return
        if not self.config.host:
            return

        current = time.monotonic() if now is None else now
        if not force and (current - self._last_pair_probe_at) < self._pair_probe_interval_seconds:
            return
        self._last_pair_probe_at = current

        # Phase 1: capability probe without pairing code. This should be low-noise and
        # tells us whether the main app has entered active pairing mode yet.
        connection = self._connect_pair_probe(pairing_code="")
        if connection is None:
            return

        pairing_required = connection.pairing_required
        paired_acknowledged = connection.paired_acknowledged
        _debug(
            "Pair probe capability result: "
            f"paired_acknowledged={paired_acknowledged}, pairing_required={pairing_required}, "
            f"source_id={self.config.source_id}"
        )
        connection.close()

        if paired_acknowledged:
            self._paired_with_main = True
            self._waiting_for_pair_notice_logged = False
            self._pairing_code = None
            self._last_announced_pairing_code = None
            _log(f"Paired with main device at {self.config.host}:{self.config.port}. Waiting for wake phrase.")
            return

        if not pairing_required:
            self._pairing_code = None
            self._last_announced_pairing_code = None
            if not self._waiting_for_pair_notice_logged:
                self._waiting_for_pair_notice_logged = True
                _log("Waiting for you to select a device and click 'Pair Selected Device' on the main app.")
            _debug("Pair probe indicates pairing is not active yet on main app.")
            return

        # Phase 2: active pairing mode is open on main, now send pairing code.
        if not self._pairing_code:
            self._pairing_code = PairingCodeGenerator.generate(self.config.token, self.config.source_id).code
            _debug(
                "Pairing diagnostic: local token fingerprint="
                f"{_token_fingerprint(self.config.token)} source_id={self.config.source_id}"
            )
        if self._pairing_code != self._last_announced_pairing_code:
            self._last_announced_pairing_code = self._pairing_code
            _log(f"Pairing code for verification: {self._pairing_code}")

        confirm_connection = self._connect_pair_probe(pairing_code=self._pairing_code)
        if confirm_connection is None:
            return

        _debug(
            "Pair probe confirmation result: "
            f"paired_acknowledged={confirm_connection.paired_acknowledged}, "
            f"pairing_required={confirm_connection.pairing_required}, source_id={self.config.source_id}"
        )
        confirm_connection.close()

        if not confirm_connection.paired_acknowledged:
            _log("Pairing request sent, but main app has not confirmed yet. Please keep the pairing dialog open.")
            return

        self._paired_with_main = True
        self._waiting_for_pair_notice_logged = False
        self._pairing_code = None
        self._last_announced_pairing_code = None
        _log(f"Paired with main device at {self.config.host}:{self.config.port}. Waiting for wake phrase.")

    def _connect_pair_probe(self, pairing_code: str) -> SecureRemoteAudioConnection | None:
        allow_untrusted = not self._has_verified_receiver_cert()
        connection = SecureRemoteAudioConnection(
            self.config,
            pairing_code=pairing_code,
            allow_untrusted=allow_untrusted,
        )
        try:
            connection.connect()
            return connection
        except Exception as exc:
            connection.close()
            if self._has_verified_receiver_cert() and self._is_cert_verification_error(exc):
                _log("Stored receiver certificate no longer matches. Refreshing trust for this pairing attempt.")
                refresh_connection = SecureRemoteAudioConnection(
                    self.config,
                    pairing_code=pairing_code,
                    allow_untrusted=True,
                )
                try:
                    refresh_connection.connect()
                    return refresh_connection
                except Exception as retry_exc:
                    _debug(
                        "Pair probe failed after trust refresh: "
                        f"{retry_exc} (target={self.config.host}:{self.config.port}, "
                        f"tls_name={self.config.tls_server_name or self.config.host})"
                    )
                    refresh_connection.close()
                    return None

            _debug(
                "Pair probe failed: "
                f"{exc} (target={self.config.host}:{self.config.port}, tls_name={self.config.tls_server_name or self.config.host})"
            )
            return None

    @staticmethod
    def _is_cert_verification_error(exc: Exception) -> bool:
        if isinstance(exc, ssl.SSLCertVerificationError):
            return True
        if isinstance(exc, ssl.SSLError) and "CERTIFICATE_VERIFY_FAILED" in str(exc).upper():
            return True
        return False

    def _has_verified_receiver_cert(self) -> bool:
        if not self.config.ca_cert_path:
            return False
        try:
            return Path(self.config.ca_cert_path).expanduser().exists()
        except Exception:
            return False

    def _open_stream(self, now: float) -> None:
        if not self.config.host:
            if not self._discovery_ready.wait(timeout=5.0):
                _log("Remote audio connection failed: no Finance Voice Receiver was discovered yet.")
                self._cooldown_until = time.monotonic() + self.config.cooldown_seconds
                return

        self._pairing_code = PairingCodeGenerator.generate(self.config.token, self.config.source_id).code
        _log(f"Pairing code for verification: {self._pairing_code}")

        connection = SecureRemoteAudioConnection(self.config, pairing_code=self._pairing_code)
        try:
            connection.connect()
            _debug(f"Sending preroll buffer chunks={len(self._preroll_buffer)}")
            for buffered_chunk in self._preroll_buffer:
                connection.send_audio(buffered_chunk)
        except Exception as exc:
            connection.close()
            _log(
                "Remote audio connection failed: "
                f"{exc} (target={self.config.host}:{self.config.port}, tls_name={self.config.tls_server_name or self.config.host})"
            )
            _log(
                "Check: main PC app running with remote audio enabled, bind host set for LAN, firewall open on port, "
                "and TLS cert/server name match."
            )
            self._cooldown_until = time.monotonic() + self.config.cooldown_seconds
            return

        self._connection = connection
        self._stream_started_at = now
        self._grace_deadline = now + (self.config.post_wake_grace_ms / 1000.0)
        self._grace_reset_pending = True
        self.endpoint.reset()
        _log(
            f"Wake detected. Streaming to {self.config.host}:{self.config.port} over TLS as {self.config.source_id}."
        )

    def _close_stream(self, reason: str) -> None:
        connection = self._connection
        self._connection = None
        self.endpoint.reset()
        self._stream_started_at = 0.0
        self._grace_deadline = 0.0
        self._grace_reset_pending = False
        self._cooldown_until = time.monotonic() + self.config.cooldown_seconds
        if connection is not None:
            connection.close()
            _log(f"Remote stream closed ({reason}).")

    def _detect_wake(self, chunk: bytes) -> bool:
        try:
            return bool(self.wake_detector.detect(chunk))
        except Exception as exc:
            _log(f"Wake detection failed: {exc}")
            self._cooldown_until = time.monotonic() + self.config.cooldown_seconds
            return False

    def _build_wake_detector(self):
        wake_mode = self.config.wake_mode.strip().lower()
        if wake_mode == "openwakeword":
            return OpenWakeWordDetector(
                sample_rate=self.config.sample_rate,
                threshold=self.config.wake_threshold,
                model_path=self.config.openwakeword_model_path,
            )

        model_path = (self.config.vosk_model_path or "").strip()
        if not model_path:
            raise RuntimeError("Vosk wake mode requires a local Vosk model path.")
        return VoskPhraseWakeDetector(
            model_path=model_path,
            sample_rate=self.config.sample_rate,
            wake_phrase=self.config.wake_phrase,
        )

    def _wake_detector_start_hint(self) -> str:
        wake_mode = self.config.wake_mode.strip().lower()
        if wake_mode == "phrase_vosk":
            model_path = (self.config.vosk_model_path or "").strip()
            if not model_path:
                return (
                    "Set FINANCE_APP_REMOTE_VOSK_MODEL_PATH to the root Vosk model folder, "
                    "for example C:\\FinanceVoice\\models\\vosk-model-en-us-0.22-lgraph"
                )

            resolved = Path(model_path).expanduser().resolve()
            if not resolved.exists():
                return f"Vosk model path does not exist: {resolved}"

            missing = [name for name in ("am", "conf", "graph") if not (resolved / name).exists()]
            if missing:
                joined = ", ".join(missing)
                return (
                    f"Vosk model folder looks invalid ({resolved}). Missing expected subfolders: {joined}. "
                    "Point to the model root directory, not a nested subfolder."
                )

            return f"Vosk model path detected: {resolved}"

        if wake_mode == "openwakeword":
            model_path = (self.config.openwakeword_model_path or "").strip()
            if not model_path:
                return "Set FINANCE_APP_REMOTE_OPENWAKEWORD_MODEL_PATH to your custom wake model file."

            resolved = Path(model_path).expanduser().resolve()
            if not resolved.exists():
                return f"OpenWakeWord model file does not exist: {resolved}"
            return f"OpenWakeWord model path detected: {resolved}"

        return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lightweight remote wake-word sender for the Finance Assistant voice server."
    )
    parser.add_argument("--host", default=_env("FINANCE_APP_REMOTE_AUDIO_HOST", ""))
    parser.add_argument("--port", type=int, default=int(_env("FINANCE_APP_REMOTE_AUDIO_PORT", "45881")))
    parser.add_argument("--token", default=_env("FINANCE_APP_REMOTE_AUDIO_TOKEN", ""))
    parser.add_argument("--source-id", default=_env("FINANCE_APP_REMOTE_SOURCE_ID", socket.gethostname()))
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--ca-cert", default=_env("FINANCE_APP_REMOTE_AUDIO_CA_CERT", ""))
    parser.add_argument("--tls-server-name", default=_env("FINANCE_APP_REMOTE_AUDIO_TLS_SERVER_NAME", ""))
    parser.add_argument("--wake-phrase", default=_env("FINANCE_APP_REMOTE_WAKE_PHRASE", "hey steven"))
    parser.add_argument("--wake-mode", default=_env("FINANCE_APP_REMOTE_WAKE_MODE", "phrase_vosk"))
    parser.add_argument(
        "--vosk-model-path",
        default=_env("FINANCE_APP_REMOTE_VOSK_MODEL_PATH", _env("FINANCE_APP_VOSK_MODEL_PATH", "")),
    )
    parser.add_argument(
        "--openwakeword-model-path",
        default=_env("FINANCE_APP_REMOTE_OPENWAKEWORD_MODEL_PATH", ""),
    )
    parser.add_argument(
        "--wake-threshold",
        type=float,
        default=float(_env("FINANCE_APP_REMOTE_WAKE_THRESHOLD", "0.5")),
    )
    parser.add_argument("--sample-rate", type=int, default=int(_env("FINANCE_APP_REMOTE_SAMPLE_RATE", "16000")))
    parser.add_argument("--blocksize", type=int, default=int(_env("FINANCE_APP_REMOTE_BLOCKSIZE", "1600")))
    parser.add_argument("--preroll-ms", type=int, default=int(_env("FINANCE_APP_REMOTE_PREROLL_MS", "2000")))
    parser.add_argument(
        "--post-wake-grace-ms",
        type=int,
        default=int(_env("FINANCE_APP_REMOTE_POST_WAKE_GRACE_MS", "1200")),
    )
    parser.add_argument(
        "--max-stream-seconds",
        type=float,
        default=float(_env("FINANCE_APP_REMOTE_MAX_STREAM_SECONDS", "12.0")),
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=float,
        default=float(_env("FINANCE_APP_REMOTE_COOLDOWN_SECONDS", "0.8")),
    )
    parser.add_argument(
        "--endpoint-min-speech-ms",
        type=int,
        default=int(_env("FINANCE_APP_REMOTE_ENDPOINT_MIN_SPEECH_MS", "300")),
    )
    parser.add_argument(
        "--endpoint-silence-ms",
        type=int,
        default=int(_env("FINANCE_APP_REMOTE_ENDPOINT_SILENCE_MS", "700")),
    )
    parser.add_argument(
        "--endpoint-max-utterance-ms",
        type=int,
        default=int(_env("FINANCE_APP_REMOTE_ENDPOINT_MAX_UTTERANCE_MS", "12000")),
    )
    parser.add_argument(
        "--energy-threshold",
        type=float,
        default=float(_env("FINANCE_APP_REMOTE_ENERGY_THRESHOLD", "450")),
    )
    return parser


def build_config(args: argparse.Namespace) -> SenderConfig:
    # Auto-generate credentials if not provided
    config_manager = RemoteVoiceConfigManager()
    creds = config_manager.get_credentials()

    token = str(args.token).strip()
    if len(token) < 16:
        token = creds.auth_token
        _log(f"Using auto-generated token from {Path.home() / '.finance-voice'}")

    ca_cert_path = str(args.ca_cert).strip()
    if not ca_cert_path:
        # Try to use auto-generated cert path
        cert_path = Path.home() / ".finance-voice" / "tls-cert.pem"
        if cert_path.exists():
            ca_cert_path = str(cert_path)
            _log(f"Using auto-generated CA cert from {cert_path}")
        else:
            raise ValueError(
                f"CA certificate not found. Expected at {cert_path}. "
                "Please run main.py first to generate credentials, or provide --ca-cert manually."
            )

    wake_mode = str(args.wake_mode).strip().lower() or "phrase_vosk"
    if wake_mode not in {"phrase_vosk", "openwakeword"}:
        raise ValueError("Wake mode must be phrase_vosk or openwakeword.")

    # Provide smart defaults for model paths
    vosk_model_path = str(args.vosk_model_path).strip()
    if wake_mode == "phrase_vosk" and not vosk_model_path:
        # Try to find Vosk model in workspace
        workspace_vosk = Path("models/vosk-model-en-us-0.22-lgraph")
        if workspace_vosk.exists():
            vosk_model_path = str(workspace_vosk.resolve())
            _log(f"Using Vosk model from {vosk_model_path}")
        else:
            raise ValueError(
                f"Vosk model not found at {workspace_vosk}. "
                "Provide --vosk-model-path or set FINANCE_APP_REMOTE_VOSK_MODEL_PATH, "
                "or use --wake-mode openwakeword for a lighter-weight option."
            )

    return SenderConfig(
        host=str(args.host).strip(),
        port=int(args.port),
        token=token,
        source_id=str(args.source_id).strip() or socket.gethostname(),
        ca_cert_path=ca_cert_path,
        tls_server_name=(str(args.tls_server_name).strip() or None),
        wake_phrase=str(args.wake_phrase).strip() or "hey steven",
        wake_mode=wake_mode,
        vosk_model_path=(vosk_model_path or None),
        openwakeword_model_path=(str(args.openwakeword_model_path).strip() or None),
        wake_threshold=float(args.wake_threshold),
        sample_rate=int(args.sample_rate),
        blocksize=int(args.blocksize),
        preroll_ms=max(500, int(args.preroll_ms)),
        post_wake_grace_ms=max(250, int(args.post_wake_grace_ms)),
        max_stream_seconds=max(2.0, float(args.max_stream_seconds)),
        cooldown_seconds=max(0.0, float(args.cooldown_seconds)),
        endpoint_min_speech_ms=max(100, int(args.endpoint_min_speech_ms)),
        endpoint_silence_ms=max(200, int(args.endpoint_silence_ms)),
        endpoint_max_utterance_ms=max(1000, int(args.endpoint_max_utterance_ms)),
        energy_threshold=max(1.0, float(args.energy_threshold)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = build_config(args)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    if args.debug:
        os.environ["FINANCE_APP_REMOTE_DEBUG"] = "1"
    _debug("Remote sender debug logging enabled.")

    sender = RemoteWakeStreamSender(config)
    return sender.run()


if __name__ == "__main__":
    sys.exit(main())
