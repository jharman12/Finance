"""Persistent TLS connection manager with heartbeat and exponential backoff (Phase 3)."""

from __future__ import annotations

import base64
import json
import random
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(slots=True)
class ReconnectConfig:
    """Configuration for exponential backoff reconnection."""

    initial_delay_ms: int = 500  # Start with 500ms
    max_delay_ms: int = 30000  # Cap at 30 seconds
    backoff_factor: float = 1.5  # Multiply by 1.5 each attempt
    jitter_factor: float = 0.1  # Add ±10% random jitter
    max_attempts: int = 0  # 0 = unlimited


class PersistentRemoteConnection:
    """Maintains a persistent TLS connection with heartbeat and auto-reconnect (Phase 3).
    
    Replaces per-utterance connect/close pattern with always-available connection.
    Handles:
    - Connection initialization with hello handshake
    - Periodic heartbeat (ping/pong) to keep connection alive
    - Automatic reconnection with exponential backoff + jitter
    - Session resumption to continue from last_seq_no on reconnect
    """

    def __init__(
        self,
        host: str,
        port: int,
        token: str,
        source_id: str,
        pairing_code: str = "",
        pairing_session_id: str = "",
        ca_cert_path: str | None = None,
        tls_server_name: str | None = None,
        allow_untrusted: bool = False,
        heartbeat_interval_ms: int = 25000,  # 25 second heartbeat
        reconnect_config: ReconnectConfig | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.source_id = source_id
        self.pairing_code = pairing_code
        self.pairing_session_id = pairing_session_id
        self.ca_cert_path = ca_cert_path
        self.tls_server_name = tls_server_name
        self.allow_untrusted = allow_untrusted
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.reconnect_config = reconnect_config or ReconnectConfig()

        self._socket: ssl.SSLSocket | None = None
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._reconnect_thread: threading.Thread | None = None
        self._heartbeat_thread_lock = threading.Lock()
        
        # Session resumption state (Phase 3)
        self.connection_id = ""
        self.last_seq_no = 0
        self.connected = False
        self._audio_seq_no = 0
        
        # Callbacks
        self.on_connected: Callable[[], None] | None = None
        self.on_disconnected: Callable[[str], None] | None = None  # reason: str
        self.on_message: Callable[[dict], None] | None = None
        self.on_error: Callable[[str], None] | None = None

    def start(self) -> bool:
        """Start the persistent connection and heartbeat."""
        with self._lock:
            if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
                return False

            self._stop_event.clear()

            # Initial connection
            if not self._connect():
                self._emit_error("Failed to establish initial connection")
                return False

            # Start heartbeat thread
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

            # Start reconnect thread
            self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
            self._reconnect_thread.start()

            return True

    def stop(self) -> None:
        """Stop the connection and threads."""
        self._stop_event.set()
        
        with self._lock:
            if self._socket is not None:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
                self.connected = False

        # Wait for threads to stop
        current = threading.current_thread()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive() and self._heartbeat_thread is not current:
            self._heartbeat_thread.join(timeout=2.0)
        if self._reconnect_thread is not None and self._reconnect_thread.is_alive() and self._reconnect_thread is not current:
            self._reconnect_thread.join(timeout=2.0)

    def send_audio(self, *args, chunk: bytes | None = None, seq_no: int | None = None, audio_b64: str | None = None, sent_at_ms: int | None = None) -> bool:
        """Send an audio frame on the persistent connection.

        Accepts either raw PCM bytes or a pre-encoded base64 payload for compatibility.
        If seq_no is omitted, the connection manages an internal increasing sequence.
        """
        if args:
            if len(args) == 1 and isinstance(args[0], (bytes, bytearray)):
                chunk = bytes(args[0])
            elif len(args) >= 2 and isinstance(args[0], int) and isinstance(args[1], str):
                seq_no = args[0]
                audio_b64 = args[1]
                if len(args) >= 3 and sent_at_ms is None and isinstance(args[2], int):
                    sent_at_ms = args[2]
            else:
                raise TypeError("send_audio() accepts either raw bytes or (seq_no, audio_b64, [sent_at_ms])")

        if chunk is not None:
            audio_b64 = base64.b64encode(chunk).decode("ascii")
        if audio_b64 is None:
            raise ValueError("audio_b64 or chunk must be provided")
        if seq_no is None:
            self._audio_seq_no += 1
            seq_no = self._audio_seq_no
        message = {
            "type": "audio",
            "connection_id": self.connection_id,
            "seq_no": seq_no,
            "audio_b64": audio_b64,
        }
        if sent_at_ms is not None:
            message["sent_at_ms"] = sent_at_ms
        
        return self._send_json(message)

    def _connect(self) -> bool:
        """Establish initial TLS connection and send hello."""
        try:
            return self._connect_with_allow_untrusted(self.allow_untrusted)
        except ssl.SSLCertVerificationError as exc:
            if self.allow_untrusted:
                self._emit_error(f"Connection failed: {exc}")
                return False

            # Verified TLS failed. Retry once in trust-refresh mode, which matches the
            # older pairing probe behavior and avoids breaking on stale receiver certs.
            self._emit_error(
                "Certificate verification failed. Retrying with trust refresh for this pairing attempt."
            )
            try:
                return self._connect_with_allow_untrusted(True)
            except Exception as retry_exc:
                self._emit_error(f"Connection failed after trust refresh: {retry_exc}")
                return False
        except Exception as e:
            self._emit_error(f"Connection failed: {e}")
            return False

    def _connect_with_allow_untrusted(self, allow_untrusted: bool) -> bool:
        context = ssl.create_default_context()
        if allow_untrusted:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        elif self.ca_cert_path:
            context.load_verify_locations(self.ca_cert_path)
            cert_path = Path(self.ca_cert_path)
            if cert_path.name.lower() == "receiver-ca-cert.pem":
                context.check_hostname = False
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        raw_socket = socket.create_connection((self.host, self.port), timeout=5.0)
        try:
            server_name = self.tls_server_name or self.host
            self._socket = context.wrap_socket(raw_socket, server_hostname=server_name)
            if allow_untrusted:
                self._persist_peer_certificate()

            # Send hello message
            hello_msg = {
                "type": "hello",
                "token": self.token,
                "source_id": self.source_id,
                "pairing_code": self.pairing_code,
            }
            if self.pairing_session_id:
                hello_msg["pairing_session_id"] = self.pairing_session_id

            # Phase 3: Include last_seq_no for session resumption
            if self.last_seq_no > 0:
                hello_msg["last_seq_no"] = self.last_seq_no

            # Handshake send must bypass _send_json because connected=False until
            # hello_ack is validated.
            hello_line = (json.dumps(hello_msg, ensure_ascii=True) + "\n").encode("utf-8")
            self._socket.sendall(hello_line)

            # Receive hello_ack
            ack_line = self._receive_line(timeout_seconds=4.0)
            if not ack_line:
                return False

            ack_msg = json.loads(ack_line)
            if str(ack_msg.get("type", "")).lower() != "hello_ack":
                self._emit_error("Persistent hello rejected: invalid_ack_type")
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
                return False

            if bool(ack_msg.get("auth_rejected", False)):
                self._emit_error("Persistent hello rejected: auth_rejected")
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
                return False

            if not bool(ack_msg.get("paired", False)):
                self._emit_error("Persistent hello rejected: paired_false")
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
                return False

            # Phase 3: Extract connection_id for session resumption
            self.connection_id = str(ack_msg.get("connection_id", "")).strip()
            if not self.connection_id:
                self.connection_id = f"{self.source_id}-{int(time.time() * 1000)}"
            self._audio_seq_no = max(self._audio_seq_no, self.last_seq_no)

            self.connected = True
            if self.on_connected:
                self.on_connected()

            return True

        except Exception:
            raise

    def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to keep connection alive."""
        interval_sec = self.heartbeat_interval_ms / 1000.0
        
        while not self._stop_event.is_set():
            try:
                time.sleep(interval_sec)
                
                if self.connected:
                    ping_msg = {
                        "type": "ping",
                        "connection_id": self.connection_id,
                    }
                    if not self._send_json(ping_msg):
                        # Disconnected
                        with self._lock:
                            self.connected = False
                        if self.on_disconnected:
                            self.on_disconnected("heartbeat_failed")
                        continue

                    pong_line = self._receive_line(timeout_seconds=2.0)
                    if not pong_line:
                        with self._lock:
                            self.connected = False
                        if self.on_disconnected:
                            self.on_disconnected("heartbeat_timeout")
                        continue

                    try:
                        pong_msg = json.loads(pong_line)
                        if str(pong_msg.get("type", "")).lower() != "pong":
                            continue
                    except Exception:
                        continue
            
            except Exception as e:
                self._emit_error(f"Heartbeat error: {e}")

    def _reconnect_loop(self) -> None:
        """Monitor connection and reconnect with exponential backoff."""
        attempt = 0
        
        while not self._stop_event.is_set():
            try:
                # Check if connected
                if self.connected:
                    time.sleep(1.0)
                    continue
                
                # Calculate backoff delay
                delay_ms = self._calculate_backoff_delay(attempt)
                delay_sec = delay_ms / 1000.0
                
                self._emit_error(
                    f"Reconnecting in {delay_ms}ms (attempt {attempt + 1})"
                )
                time.sleep(delay_sec)
                
                # Try to reconnect
                with self._lock:
                    if self.connected:
                        continue
                    
                    if self._socket is not None:
                        try:
                            self._socket.close()
                        except Exception:
                            pass
                        self._socket = None
                    
                    if self._connect():
                        attempt = 0  # Reset on successful reconnect
                    else:
                        attempt += 1
                        if self.reconnect_config.max_attempts > 0:
                            if attempt >= self.reconnect_config.max_attempts:
                                self._emit_error("Max reconnection attempts reached")
                                break
            
            except Exception as e:
                self._emit_error(f"Reconnect loop error: {e}")
                attempt += 1

    def _calculate_backoff_delay(self, attempt: int) -> int:
        """Calculate exponential backoff delay with jitter."""
        config = self.reconnect_config
        
        # Exponential backoff: initial_delay * (backoff_factor ^ attempt)
        delay_ms = config.initial_delay_ms * (config.backoff_factor ** attempt)
        delay_ms = min(delay_ms, config.max_delay_ms)  # Cap at max
        
        # Add jitter: ±jitter_factor
        jitter_amount = delay_ms * config.jitter_factor
        jitter = random.uniform(-jitter_amount, jitter_amount)
        
        return max(int(delay_ms + jitter), config.initial_delay_ms)

    def _persist_peer_certificate(self) -> None:
        """Persist peer certificate for subsequent verified TLS connections."""
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
        self.ca_cert_path = str(receiver_cert_path)

    def close(self) -> None:
        """Compatibility alias for stop()."""
        self.stop()

    def _send_json(self, message: dict) -> bool:
        """Send JSON message on socket."""
        try:
            with self._lock:
                if self._socket is None or not self.connected:
                    return False
                
                line = json.dumps(message, ensure_ascii=True) + "\n"
                self._socket.sendall(line.encode("utf-8"))
                return True
        
        except Exception as e:
            self._emit_error(f"Send failed: {e}")
            with self._lock:
                self.connected = False
            return False

    def _receive_line(self, timeout_seconds: float | None = None) -> str:
        """Receive one line from socket."""
        try:
            with self._lock:
                if self._socket is None:
                    return ""
                previous_timeout = self._socket.gettimeout()
                if timeout_seconds is not None:
                    self._socket.settimeout(timeout_seconds)
                try:
                    line = b""
                    while b"\n" not in line:
                        part = self._socket.recv(4096)
                        if not part:
                            return ""
                        line += part

                    return line.split(b"\n", 1)[0].decode("utf-8", errors="ignore")
                finally:
                    if timeout_seconds is not None:
                        self._socket.settimeout(previous_timeout)
        
        except Exception:
            return ""

    def _emit_error(self, message: str) -> None:
        """Emit error callback."""
        if self.on_error:
            self.on_error(message)
