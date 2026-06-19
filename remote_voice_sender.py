from __future__ import annotations

import argparse
import base64
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
    def __init__(self, config: SenderConfig) -> None:
        self.config = config
        self._socket: ssl.SSLSocket | None = None
        self._seq_no = 0

    def connect(self) -> None:
        if len(self.config.token) < 16:
            raise RuntimeError("Remote audio token must be at least 16 characters long.")

        cafile = Path(self.config.ca_cert_path)
        if not cafile.exists():
            raise RuntimeError(f"CA certificate not found at {self.config.ca_cert_path}")

        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(cafile))
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        _debug(
            f"Connecting to {self.config.host}:{self.config.port} with TLS server name "
            f"'{self.config.tls_server_name or self.config.host}'"
        )
        raw_socket = socket.create_connection((self.config.host, self.config.port), timeout=5.0)
        try:
            server_name = self.config.tls_server_name or self.config.host
            self._socket = context.wrap_socket(raw_socket, server_hostname=server_name)
            _debug("TLS handshake complete. Sending hello message.")
            self._send_json(
                {
                    "type": "hello",
                    "token": self.config.token,
                    "source_id": self.config.source_id,
                }
            )
            _debug("Hello message sent.")
        except Exception:
            raw_socket.close()
            self._socket = None
            raise

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
            f"Remote stream stays offline until wake is detected."
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
            try:
                self.wake_detector.stop()
            except Exception:
                pass

        return 0

    def _handle_chunk(self, chunk: bytes) -> None:
        if not chunk:
            return

        self._preroll_buffer.append(chunk)
        now = time.monotonic()

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

    def _open_stream(self, now: float) -> None:
        connection = SecureRemoteAudioConnection(self.config)
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
    parser.add_argument("--host", default=_env("FINANCE_APP_REMOTE_AUDIO_HOST", "127.0.0.1"))
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
    token = str(args.token).strip()
    if len(token) < 16:
        raise ValueError("Provide FINANCE_APP_REMOTE_AUDIO_TOKEN or --token with at least 16 characters.")

    ca_cert_path = str(args.ca_cert).strip()
    if not ca_cert_path:
        raise ValueError("Provide FINANCE_APP_REMOTE_AUDIO_CA_CERT or --ca-cert to enforce TLS server verification.")

    wake_mode = str(args.wake_mode).strip().lower() or "phrase_vosk"
    if wake_mode not in {"phrase_vosk", "openwakeword"}:
        raise ValueError("Wake mode must be phrase_vosk or openwakeword.")

    return SenderConfig(
        host=str(args.host).strip() or "127.0.0.1",
        port=int(args.port),
        token=token,
        source_id=str(args.source_id).strip() or socket.gethostname(),
        ca_cert_path=ca_cert_path,
        tls_server_name=(str(args.tls_server_name).strip() or None),
        wake_phrase=str(args.wake_phrase).strip() or "hey steven",
        wake_mode=wake_mode,
        vosk_model_path=(str(args.vosk_model_path).strip() or None),
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
