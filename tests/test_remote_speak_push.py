from __future__ import annotations

import base64
import json
import socket
import time
import unittest

from finance_app.services.voice.network_transport import RemoteAudioServer


class RemoteSpeakPushTests(unittest.TestCase):
    """Server-side outbound push to a connected device."""

    def _connect_and_authenticate(self, server: RemoteAudioServer, source_id: str, token: str):
        sock = socket.create_connection(("127.0.0.1", server.bound_port), timeout=2.0)
        sock.sendall(
            (json.dumps({"type": "hello", "source_id": source_id, "token": token}) + "\n").encode("utf-8")
        )
        raw = b""
        while b"\n" not in raw:
            part = sock.recv(4096)
            if not part:
                break
            raw += part
        return sock

    def _read_line(self, sock: socket.socket) -> dict:
        raw = b""
        while b"\n" not in raw:
            part = sock.recv(4096)
            if not part:
                break
            raw += part
        if not raw:
            return {}
        return json.loads(raw.split(b"\n", 1)[0].decode("utf-8"))

    def test_authenticated_device_is_registered(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        token = server._device_token_store.issue_token("node-1")
        server.start()
        try:
            sock = self._connect_and_authenticate(server, "node-1", token)
            try:
                time.sleep(0.15)
                self.assertIn("node-1", server.connected_source_ids())
            finally:
                sock.close()
        finally:
            server.stop()

    def test_disconnect_deregisters_device(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        token = server._device_token_store.issue_token("node-1")
        server.start()
        try:
            sock = self._connect_and_authenticate(server, "node-1", token)
            time.sleep(0.15)
            sock.close()
            time.sleep(0.3)

            self.assertNotIn("node-1", server.connected_source_ids())
        finally:
            server.stop()

    def test_send_to_device_delivers_speak_message(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        token = server._device_token_store.issue_token("node-1")
        server.start()
        try:
            sock = self._connect_and_authenticate(server, "node-1", token)
            try:
                time.sleep(0.15)
                payload = base64.b64encode(b"\x00\x01").decode("ascii")

                delivered = server.send_to_device(
                    "node-1",
                    {
                        "type": "speak",
                        "speech_id": "abc",
                        "seq_no": 1,
                        "final": True,
                        "encoding": "pcm_s16le",
                        "sample_rate": 16000,
                        "channels": 1,
                        "audio_b64": payload,
                    },
                )

                self.assertTrue(delivered)
                message = self._read_line(sock)
                self.assertEqual(message.get("type"), "speak")
                self.assertEqual(message.get("speech_id"), "abc")
                self.assertEqual(message.get("audio_b64"), payload)
            finally:
                sock.close()
        finally:
            server.stop()

    def test_send_to_unknown_device_returns_false(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        server.start()
        try:
            self.assertFalse(server.send_to_device("ghost-node", {"type": "speak"}))
        finally:
            server.stop()

    def test_unauthenticated_device_is_not_registered(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        server.start()
        try:
            with socket.create_connection(("127.0.0.1", server.bound_port), timeout=2.0) as sock:
                sock.sendall(
                    (json.dumps({"type": "hello", "source_id": "node-1", "token": "bad"}) + "\n").encode("utf-8")
                )
                time.sleep(0.2)

            self.assertEqual(server.connected_source_ids(), [])
        finally:
            server.stop()

    def test_speak_ack_is_accepted_without_closing_connection(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        token = server._device_token_store.issue_token("node-1")
        diagnostics: list[dict] = []
        server.on_diagnostic = diagnostics.append
        server.start()
        try:
            sock = self._connect_and_authenticate(server, "node-1", token)
            try:
                sock.sendall(
                    (
                        json.dumps(
                            {"type": "speak_ack", "speech_id": "abc", "seq_no": 1, "state": "playing"}
                        )
                        + "\n"
                    ).encode("utf-8")
                )
                time.sleep(0.2)

                self.assertTrue(any(d.get("event") == "speak_ack" for d in diagnostics))
                # Connection must survive so audio can continue to flow.
                self.assertIn("node-1", server.connected_source_ids())
            finally:
                sock.close()
        finally:
            server.stop()

    def test_unknown_message_type_is_ignored(self) -> None:
        server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        token = server._device_token_store.issue_token("node-1")
        server.start()
        try:
            sock = self._connect_and_authenticate(server, "node-1", token)
            try:
                sock.sendall((json.dumps({"type": "from_the_future"}) + "\n").encode("utf-8"))
                time.sleep(0.2)

                self.assertIn("node-1", server.connected_source_ids())
            finally:
                sock.close()
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
