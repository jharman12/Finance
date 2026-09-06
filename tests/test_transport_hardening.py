from __future__ import annotations

import base64
import json
import socket
import time
import unittest

from finance_app.services.voice.network_transport import (
    AUDIO_FRAME_MAGIC,
    MAX_AUTH_ATTEMPTS,
    RemoteAudioPacket,
    RemoteAudioServer,
)


class FrameValidationTests(unittest.TestCase):
    """Audio frames must carry the protocol magic marker."""

    def setUp(self) -> None:
        self.received: list[RemoteAudioPacket] = []
        self.diagnostics: list[dict] = []
        self.server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        self.server.on_packet = self.received.append
        self.server.on_diagnostic = self.diagnostics.append
        self.token = self.server._device_token_store.issue_token("node-1")
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()

    def _send_frames(self, messages: list[dict]) -> None:
        with socket.create_connection(("127.0.0.1", self.server.bound_port), timeout=2.0) as sock:
            for message in messages:
                sock.sendall((json.dumps(message) + "\n").encode("utf-8"))
                time.sleep(0.05)
            time.sleep(0.15)

    def _audio(self, seq_no: int, **overrides) -> dict:
        message = {
            "type": "audio",
            "magic": AUDIO_FRAME_MAGIC,
            "seq_no": seq_no,
            "audio_b64": base64.b64encode(b"\x01\x02\x03\x04").decode("ascii"),
        }
        message.update(overrides)
        return message

    def test_frame_with_valid_magic_is_accepted(self) -> None:
        self._send_frames(
            [{"type": "hello", "source_id": "node-1", "token": self.token}, self._audio(1)]
        )

        self.assertEqual(len(self.received), 1)

    def test_frame_without_magic_is_rejected(self) -> None:
        frame = self._audio(1)
        del frame["magic"]
        self._send_frames([{"type": "hello", "source_id": "node-1", "token": self.token}, frame])

        self.assertEqual(self.received, [])
        self.assertTrue(any(d.get("event") == "magic_rejected" for d in self.diagnostics))

    def test_frame_with_wrong_magic_is_rejected(self) -> None:
        self._send_frames(
            [
                {"type": "hello", "source_id": "node-1", "token": self.token},
                self._audio(1, magic="XXXX"),
            ]
        )

        self.assertEqual(self.received, [])
        self.assertTrue(any(d.get("event") == "magic_rejected" for d in self.diagnostics))


class AuthRateLimitTests(unittest.TestCase):
    """Repeated hello attempts from one peer are throttled."""

    def setUp(self) -> None:
        self.diagnostics: list[dict] = []
        self.server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        self.server.on_diagnostic = self.diagnostics.append
        self.server.start()

    def tearDown(self) -> None:
        self.server.stop()

    def _attempt_hello(self) -> dict:
        with socket.create_connection(("127.0.0.1", self.server.bound_port), timeout=2.0) as sock:
            sock.sendall(
                (json.dumps({"type": "hello", "source_id": "node-1", "token": "bad"}) + "\n").encode("utf-8")
            )
            raw = b""
            sock.settimeout(1.0)
            try:
                while b"\n" not in raw:
                    part = sock.recv(4096)
                    if not part:
                        break
                    raw += part
            except socket.timeout:
                return {}
        if not raw:
            return {}
        return json.loads(raw.split(b"\n", 1)[0].decode("utf-8"))

    def test_attempts_within_budget_still_get_a_rejection_ack(self) -> None:
        for _ in range(MAX_AUTH_ATTEMPTS):
            ack = self._attempt_hello()
            self.assertTrue(bool(ack.get("auth_rejected", False)))

    def test_attempts_beyond_the_budget_are_dropped(self) -> None:
        for _ in range(MAX_AUTH_ATTEMPTS):
            self._attempt_hello()

        self.assertEqual(self._attempt_hello(), {})
        self.assertTrue(any(d.get("event") == "auth_rate_limited" for d in self.diagnostics))

    def test_only_failed_attempts_consume_the_budget(self) -> None:
        token = self.server._device_token_store.issue_token("node-ok")
        for _ in range(MAX_AUTH_ATTEMPTS * 2):
            with socket.create_connection(("127.0.0.1", self.server.bound_port), timeout=2.0) as sock:
                sock.sendall(
                    (json.dumps({"type": "hello", "source_id": "node-ok", "token": token}) + "\n").encode("utf-8")
                )
                time.sleep(0.05)

        self.assertFalse(self.server._auth_attempts_exhausted("127.0.0.1"))

    def test_budget_is_tracked_per_peer(self) -> None:
        for _ in range(MAX_AUTH_ATTEMPTS):
            self.server._register_auth_failure("10.0.0.5")

        self.assertTrue(self.server._auth_attempts_exhausted("10.0.0.5"))
        self.assertFalse(self.server._auth_attempts_exhausted("10.0.0.6"))


if __name__ == "__main__":
    unittest.main()
