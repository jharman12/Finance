from __future__ import annotations

import base64
import json
import os
import socket
import time
import unittest
from unittest.mock import patch

from finance_app.services.voice.network_transport import RemoteAudioPacket, RemoteAudioServer


class VoiceRemoteTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.received: list[RemoteAudioPacket] = []

    def _send(self, host: str, port: int, messages: list[dict[str, object]]) -> None:
        with socket.create_connection((host, port), timeout=2.0) as sock:
            for message in messages:
                payload = (json.dumps(message) + "\n").encode("utf-8")
                sock.sendall(payload)

    def test_accepts_authenticated_audio_packet(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        server.on_packet = self.received.append
        server.start()
        try:
            payload = b"\x00\x01\x02\x03"
            self._send(
                "127.0.0.1",
                server.bound_port,
                [
                    {"type": "hello", "source_id": "node-1", "token": "1234567890abcdef"},
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
        server.on_packet = self.received.append
        server.start()
        try:
            audio_a = base64.b64encode(b"chunk-a").decode("ascii")
            audio_b = base64.b64encode(b"chunk-b").decode("ascii")
            self._send(
                "127.0.0.1",
                server.bound_port,
                [
                    {"type": "hello", "source_id": "node-1", "token": "1234567890abcdef"},
                    {"type": "audio", "seq_no": 2, "audio_b64": audio_a},
                    {"type": "audio", "seq_no": 1, "audio_b64": audio_b},
                ],
            )
            time.sleep(0.1)
        finally:
            server.stop()

        self.assertEqual(len(self.received), 1)
        self.assertEqual(self.received[0].seq_no, 2)

    def test_phase4_discovery_properties_exclude_secrets(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=45881, auth_token="1234567890abcdef")
        with patch.dict(os.environ, {"FINANCE_APP_REMOTE_MDNS_TOKEN_BOOTSTRAP": "0"}):
            properties = server._build_discovery_properties("192.168.1.10")

        self.assertEqual(properties.get("tls_server_name"), "192.168.1.10")
        self.assertEqual(properties.get("endpoint"), "192.168.1.10:45881")
        self.assertNotIn("auth_token", properties)
        self.assertNotIn("tls_cert_path", properties)


if __name__ == "__main__":
    unittest.main()
