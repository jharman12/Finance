from __future__ import annotations

import base64
import hmac
import json
import os
import socket
import socketserver
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from finance_app.services.voice.discovery import RemoteVoiceDiscoveryPublisher, resolve_local_ipv4
from finance_app.services.voice.remote_config import RemoteVoiceConfigManager


@dataclass(slots=True)
class RemoteAudioPacket:
    source_id: str
    seq_no: int
    payload: bytes
    sent_at_ms: int | None = None


class _ThreadingTcpServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class RemoteAudioServer:
    """Authenticated LAN audio ingest server.

    Protocol: newline-delimited JSON messages.
    - hello: {"type":"hello","token":"...","source_id":"node-1"}
    - audio: {"type":"audio","seq_no":1,"audio_b64":"...","sent_at_ms":...}
    - ping:  {"type":"ping"}
    """

    def __init__(
        self,
        host: str,
        port: int,
        auth_token: str,
        max_chunk_bytes: int = 32768,
        max_messages_per_second: int = 120,
        tls_cert_path: str | None = None,
        tls_key_path: str | None = None,
        pairing_manager: object | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.max_chunk_bytes = max(1024, int(max_chunk_bytes))
        self.max_messages_per_second = max(10, int(max_messages_per_second))
        self.tls_cert_path = tls_cert_path
        self.tls_key_path = tls_key_path
        self.pairing_manager = pairing_manager

        self._server: _ThreadingTcpServer | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._debug = os.getenv("FINANCE_APP_REMOTE_AUDIO_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
        self._discovery_name = os.getenv("FINANCE_APP_REMOTE_DISCOVERY_NAME", "Finance Voice Receiver").strip() or "Finance Voice Receiver"
        self._discovery_publisher: RemoteVoiceDiscoveryPublisher | None = None

        self.on_packet: Callable[[RemoteAudioPacket], None] | None = None
        self.on_status: Callable[[str], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self.on_diagnostic: Callable[[dict[str, object]], None] | None = None

    @property
    def bound_port(self) -> int:
        server = self._server
        if server is None:
            return self.port
        return int(server.server_address[1])

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        if len(self.auth_token) < 16:
            raise ValueError("Remote audio token must be at least 16 characters.")

        self._stop_event.clear()

        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:  # noqa: D401
                source_id = ""
                authenticated = False
                last_seq = -1
                window: deque[float] = deque(maxlen=512)
                tls_enabled = False
                packet_count = 0

                sock = self.request
                if isinstance(sock, ssl.SSLSocket):
                    tls_enabled = True

                outer._debug_log(f"Connection accepted from {self.client_address}, tls={tls_enabled}")

                while not outer._stop_event.is_set():
                    try:
                        raw = self.rfile.readline()
                    except (ConnectionAbortedError, ConnectionResetError, OSError):
                        return
                    if not raw:
                        return
                    if len(raw) > 131072:
                        outer._emit_error("Remote audio message exceeded max line size.")
                        return

                    try:
                        msg = json.loads(raw.decode("utf-8"))
                    except Exception:
                        outer._emit_error("Remote audio received invalid JSON message.")
                        return

                    msg_type = str(msg.get("type", "")).strip().lower()
                    now = time.monotonic()
                    window.append(now)
                    while window and (now - window[0]) > 1.0:
                        window.popleft()
                    if len(window) > outer.max_messages_per_second:
                        outer._emit_diagnostic(
                            event="rate_limit",
                            source_id=source_id or "unidentified",
                            mps=len(window),
                        )
                        return

                    if msg_type == "ping":
                        outer._debug_log(f"Ping received from {source_id or self.client_address}")
                        continue

                    if not authenticated:
                        if msg_type != "hello":
                            outer._emit_error("Remote audio first message must be hello.")
                            return

                        source_id_candidate = str(msg.get("source_id", "")).strip()
                        token = str(msg.get("token", ""))
                        if not source_id_candidate:
                            outer._emit_error("Remote audio hello missing source_id.")
                            return
                        if not hmac.compare_digest(token, outer.auth_token):
                            outer._emit_diagnostic(event="auth_rejected", source_id=source_id_candidate)
                            outer._debug_log(f"Auth rejected for source_id={source_id_candidate}")
                            return

                        source_id = source_id_candidate
                        authenticated = True
                        outer._emit_diagnostic(event="client_authenticated", source_id=source_id, tls=tls_enabled)
                        outer._debug_log(f"Client authenticated source_id={source_id}, tls={tls_enabled}")

                        # Check pairing code if present
                        pairing_verified = False
                        pairing_code = str(msg.get("pairing_code", "")).strip()
                        if pairing_code and outer.pairing_manager is not None:
                            if hasattr(outer.pairing_manager, 'verify_pairing_code'):
                                pairing_verified = outer.pairing_manager.verify_pairing_code(source_id, pairing_code)
                                outer._debug_log(f"Pairing code verification for {source_id}: {pairing_verified}")

                        pairing_required = False
                        if outer.pairing_manager is not None and hasattr(outer.pairing_manager, "is_pairing"):
                            try:
                                pairing_required = bool(outer.pairing_manager.is_pairing())
                            except Exception:
                                pairing_required = False

                        outer._emit_diagnostic(
                            event="pairing_evaluated",
                            source_id=source_id,
                            pairing_code_present=bool(pairing_code),
                            pairing_verified=pairing_verified,
                            pairing_required=pairing_required,
                        )

                        try:
                            self.wfile.write(
                                (
                                    json.dumps(
                                        {
                                            "type": "hello_ack",
                                            "paired": pairing_verified,
                                            "pairing_required": pairing_required,
                                        },
                                        ensure_ascii=True,
                                    )
                                    + "\n"
                                ).encode("utf-8")
                            )
                            self.wfile.flush()
                        except Exception:
                            return
                        continue

                    if msg_type != "audio":
                        continue

                    try:
                        seq_no = int(msg.get("seq_no"))
                    except Exception:
                        outer._emit_error("Remote audio packet missing seq_no.")
                        return

                    if seq_no <= last_seq:
                        outer._emit_diagnostic(
                            event="seq_rejected",
                            source_id=source_id,
                            seq_no=seq_no,
                            last_seq=last_seq,
                        )
                        return

                    audio_b64 = msg.get("audio_b64")
                    if not isinstance(audio_b64, str) or not audio_b64:
                        outer._emit_error("Remote audio packet missing audio_b64 payload.")
                        return

                    try:
                        payload = base64.b64decode(audio_b64.encode("ascii"), validate=True)
                    except Exception:
                        outer._emit_error("Remote audio payload was not valid base64.")
                        return

                    if not payload or len(payload) > outer.max_chunk_bytes:
                        outer._emit_diagnostic(
                            event="payload_rejected",
                            source_id=source_id,
                            bytes=len(payload),
                            max_bytes=outer.max_chunk_bytes,
                        )
                        return

                    sent_at_ms = msg.get("sent_at_ms")
                    parsed_sent_at: int | None = None
                    if isinstance(sent_at_ms, int):
                        parsed_sent_at = sent_at_ms

                    last_seq = seq_no
                    packet_count += 1
                    if packet_count == 1 or (packet_count % 50) == 0:
                        outer._debug_log(
                            f"Audio packet from source_id={source_id} seq={seq_no} bytes={len(payload)} count={packet_count}"
                        )
                    packet = RemoteAudioPacket(
                        source_id=source_id,
                        seq_no=seq_no,
                        payload=payload,
                        sent_at_ms=parsed_sent_at,
                    )
                    if outer.on_packet:
                        outer.on_packet(packet)

        self._server = _ThreadingTcpServer((self.host, self.port), Handler)

        if self.tls_cert_path and self.tls_key_path:
            cert = Path(self.tls_cert_path)
            key = Path(self.tls_key_path)
            if not cert.exists() or not key.exists():
                raise ValueError("TLS cert/key paths were provided but file(s) do not exist.")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(certfile=str(cert), keyfile=str(key))
            self._server.socket = context.wrap_socket(self._server.socket, server_side=True)

        self._thread = threading.Thread(target=self._serve, name="RemoteAudioServer", daemon=True)
        self._thread.start()

        advertised_tls_server_name = self.host
        if advertised_tls_server_name in {"", "0.0.0.0", "::"}:
            advertised_tls_server_name = resolve_local_ipv4()

        self._discovery_publisher = RemoteVoiceDiscoveryPublisher(
            source_id="finance-main-pc",
            port=self.bound_port,
            device_name=self._discovery_name,
            role="voice-receiver",
            extra_properties={
                "auth_token": self.auth_token,
                "tls_cert_path": self.tls_cert_path or "",
                "tls_server_name": advertised_tls_server_name,
            },
        )
        discovery_started = False
        try:
            discovery_started = self._discovery_publisher.start()
        except Exception as exc:
            self._emit_diagnostic(event="mdns_publish_failed", error=str(exc))
            self._debug_log(f"mDNS publish failed: {exc}")

        self._emit_status(f"Remote audio server listening on {self.host}:{self.bound_port}")
        if discovery_started:
            self._emit_diagnostic(
                event="mdns_published",
                service_name=self._discovery_name,
                port=self.bound_port,
            )
        self._debug_log(f"RemoteAudioServer started host={self.host} port={self.bound_port} debug={self._debug}")

    def stop(self) -> None:
        self._stop_event.set()
        server = self._server
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        discovery_publisher = self._discovery_publisher
        self._discovery_publisher = None
        if discovery_publisher is not None:
            try:
                discovery_publisher.stop()
            except Exception:
                pass

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        try:
            server.serve_forever(poll_interval=0.2)
        except (OSError, socket.error) as exc:
            self._emit_error(f"Remote audio server failed: {exc}")

    def _emit_status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def _emit_error(self, message: str) -> None:
        if self.on_error:
            self.on_error(message)

    def _emit_diagnostic(self, **payload: object) -> None:
        if self.on_diagnostic:
            self.on_diagnostic(dict(payload))

    def _debug_log(self, message: str) -> None:
        if not self._debug:
            return
        print(f"[RemoteAudioServer DEBUG] {message}")
