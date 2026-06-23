from __future__ import annotations

import base64
import json
import socket
import time
import unittest


class _FakePairingState:
    def __init__(self, source_id: str, code: str, session_id: str) -> None:
        self.source_id = source_id
        self.expected_pairing_code = code
        self.pairing_session_id = session_id

    def is_session_expired(self) -> bool:
        return False


class _FakePairingManager:
    def __init__(self) -> None:
        self._state = _FakePairingState("node-1", "ABC123", "sess-1")

    def is_pairing(self) -> bool:
        return True

    def get_pairing_state(self):
        return self._state

    def verify_pairing_code(self, source_id: str, pairing_code: str, pairing_session_id: str = "") -> bool:
        return (
            source_id == self._state.source_id
            and pairing_code == self._state.expected_pairing_code
            and pairing_session_id == self._state.pairing_session_id
        )

from finance_app.services.voice.network_transport import RemoteAudioPacket, RemoteAudioServer


class VoiceRemoteTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.received: list[RemoteAudioPacket] = []

    def _send(self, host: str, port: int, messages: list[dict[str, object]]) -> None:
        with socket.create_connection((host, port), timeout=2.0) as sock:
            for message in messages:
                payload = (json.dumps(message) + "\n").encode("utf-8")
                sock.sendall(payload)

    def _send_and_read_first_line(self, host: str, port: int, message: dict[str, object]) -> dict[str, object]:
        with socket.create_connection((host, port), timeout=2.0) as sock:
            sock.sendall((json.dumps(message) + "\n").encode("utf-8"))
            raw = b""
            while b"\n" not in raw:
                part = sock.recv(4096)
                if not part:
                    break
                raw += part
            if not raw:
                return {}
            line = raw.split(b"\n", 1)[0].decode("utf-8", errors="ignore").strip()
            return json.loads(line) if line else {}

    def test_accepts_authenticated_audio_packet(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        server._device_tokens["node-1"] = "device-token-1234567890abcdef"
        server.on_packet = self.received.append
        server.start()
        try:
            payload = b"\x00\x01\x02\x03"
            self._send(
                "127.0.0.1",
                server.bound_port,
                [
                    {"type": "hello", "source_id": "node-1", "token": "device-token-1234567890abcdef"},
                    {
                        "type": "audio",
                        "seq_no": 1,
                        "audio_b64": base64.b64encode(payload).decode("ascii"),
                        "sent_at_ms": 1234,
                    },
                ],
            )
            time.sleep(0.1)
        finally:
            server.stop()

        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].source_id, "node-1")
        self.assertEqual(self.received[0].seq_no, 1)
        self.assertEqual(self.received[0].payload, payload)

    def test_rejects_invalid_token(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        server.on_packet = self.received.append
        server.start()
        try:
            self._send(
                "127.0.0.1",
                server.bound_port,
                [
                    {"type": "hello", "source_id": "node-1", "token": "bad-token"},
                    {
                        "type": "audio",
                        "seq_no": 1,
                        "audio_b64": base64.b64encode(b"abc").decode("ascii"),
                    },
                ],
            )
            time.sleep(0.1)
        finally:
            server.stop()

        self.assertEqual(self.received, [])

    def test_rejects_non_monotonic_sequence(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        server._device_tokens["node-1"] = "device-token-1234567890abcdef"
        server.on_packet = self.received.append
        server.start()
        try:
            audio_a = base64.b64encode(b"chunk-a").decode("ascii")
            audio_b = base64.b64encode(b"chunk-b").decode("ascii")
            self._send(
                "127.0.0.1",
                server.bound_port,
                [
                    {"type": "hello", "source_id": "node-1", "token": "device-token-1234567890abcdef"},
                    {"type": "audio", "seq_no": 2, "audio_b64": audio_a},
                    {"type": "audio", "seq_no": 1, "audio_b64": audio_b},
                ],
            )
            time.sleep(0.1)
        finally:
            server.stop()

        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].seq_no, 2)

    def test_rejects_legacy_shared_token_without_enrollment(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        server.on_packet = self.received.append
        server.start()
        try:
            self._send(
                "127.0.0.1",
                server.bound_port,
                [
                    {"type": "hello", "source_id": "node-1", "token": "1234567890abcdef"},
                    {
                        "type": "audio",
                        "seq_no": 1,
                        "audio_b64": base64.b64encode(b"abc").decode("ascii"),
                    },
                ],
            )
            time.sleep(0.1)
        finally:
            server.stop()

        self.assertEqual(self.received, [])

    def test_phase4_discovery_properties_exclude_secrets(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=45881, auth_token="1234567890abcdef")
        properties = server._build_discovery_properties("192.168.1.10")

        self.assertEqual(properties.get("tls_server_name"), "192.168.1.10")
        self.assertEqual(properties.get("endpoint"), "192.168.1.10:45881")
        self.assertNotIn("auth_token", properties)
        self.assertNotIn("tls_cert_path", properties)

    def test_unauthenticated_hello_returns_pairing_hint_when_pairing_active(self) -> None:
        server = RemoteAudioServer(
            host="127.0.0.1",
            port=0,
            auth_token="1234567890abcdef",
            pairing_manager=_FakePairingManager(),
        )
        server.start()
        try:
            ack = self._send_and_read_first_line(
                "127.0.0.1",
                server.bound_port,
                {
                    "type": "hello",
                    "source_id": "node-1",
                    "token": "not-shared",
                },
            )
        finally:
            server.stop()

        self.assertEqual(ack.get("type"), "hello_ack")
        self.assertEqual(bool(ack.get("auth_rejected")), True)
        self.assertEqual(bool(ack.get("pairing_required")), True)
        self.assertEqual(str(ack.get("pairing_code_hint", "")), "ABC123")
        self.assertEqual(str(ack.get("pairing_session_id", "")), "sess-1")

    def test_authenticated_hello_returns_pairing_hint_when_pairing_active(self) -> None:
        server = RemoteAudioServer(
            host="127.0.0.1",
            port=0,
            auth_token="1234567890abcdef",
            pairing_manager=_FakePairingManager(),
        )
        server._device_tokens["node-1"] = "device-token-1234567890abcdef"
        server.start()
        try:
            ack = self._send_and_read_first_line(
                "127.0.0.1",
                server.bound_port,
                {
                    "type": "hello",
                    "source_id": "node-1",
                    "token": "device-token-1234567890abcdef",
                },
            )
        finally:
            server.stop()

        self.assertEqual(ack.get("type"), "hello_ack")
        self.assertEqual(bool(ack.get("pairing_required")), True)
        self.assertEqual(bool(ack.get("paired")), False)
        self.assertEqual(str(ack.get("pairing_code_hint", "")), "ABC123")
        self.assertEqual(str(ack.get("pairing_session_id", "")), "sess-1")

    def test_authenticated_hello_with_pairing_code_confirms_pairing(self) -> None:
        server = RemoteAudioServer(
            host="127.0.0.1",
            port=0,
            auth_token="1234567890abcdef",
            pairing_manager=_FakePairingManager(),
        )
        server._device_tokens["node-1"] = "device-token-1234567890abcdef"
        server.start()
        try:
            ack = self._send_and_read_first_line(
                "127.0.0.1",
                server.bound_port,
                {
                    "type": "hello",
                    "source_id": "node-1",
                    "token": "device-token-1234567890abcdef",
                    "pairing_code": "ABC123",
                    "pairing_session_id": "sess-1",
                },
            )
        finally:
            server.stop()

        self.assertEqual(ack.get("type"), "hello_ack")
        self.assertEqual(bool(ack.get("paired")), True)
        self.assertEqual(bool(ack.get("pairing_required")), True)


if __name__ == "__main__":
    unittest.main()
