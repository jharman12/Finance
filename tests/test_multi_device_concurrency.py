from __future__ import annotations

import base64
import json
import socket
import threading
import time
import unittest

from finance_app.services.voice.network_transport import (
    AUDIO_FRAME_MAGIC,
    RemoteAudioPacket,
    RemoteAudioServer,
)

DEVICE_IDS = ["node-1", "node-2", "node-3", "node-4"]


class MultiDeviceConcurrencyTests(unittest.TestCase):
    """Phase 1 validation: several remote devices connected at the same time."""

    def setUp(self) -> None:
        self.server = RemoteAudioServer(host="127.0.0.1", port=0, auth_token="1234567890abcdef")
        self.packets: list[RemoteAudioPacket] = []
        self._packet_lock = threading.Lock()
        self.server.on_packet = self._record_packet
        self.server.start()
        self.sockets: list[socket.socket] = []
        self._buffers: dict[int, bytes] = {}

    def tearDown(self) -> None:
        for sock in self.sockets:
            try:
                sock.close()
            except Exception:
                pass
        self.server.stop()

    def _record_packet(self, packet: RemoteAudioPacket) -> None:
        with self._packet_lock:
            self.packets.append(packet)

    def _recorded(self) -> list[RemoteAudioPacket]:
        with self._packet_lock:
            return list(self.packets)

    def _connect(self, source_id: str) -> socket.socket:
        token = self.server._device_token_store.issue_token(source_id)
        sock = socket.create_connection(("127.0.0.1", self.server.bound_port), timeout=2.0)
        self.sockets.append(sock)
        sock.sendall(
            (json.dumps({"type": "hello", "source_id": source_id, "token": token}) + "\n").encode("utf-8")
        )
        self._read_line(sock)
        return sock

    def _read_line(self, sock: socket.socket, timeout: float = 2.0) -> dict:
        sock.settimeout(timeout)
        buffer = self._buffers.get(id(sock), b"")
        while b"\n" not in buffer:
            try:
                part = sock.recv(4096)
            except socket.timeout:
                self._buffers[id(sock)] = buffer
                return {}
            if not part:
                break
            buffer += part
        if b"\n" not in buffer:
            self._buffers[id(sock)] = buffer
            return {}
        raw_line, remainder = buffer.split(b"\n", 1)
        self._buffers[id(sock)] = remainder
        if not raw_line:
            return {}
        return json.loads(raw_line.decode("utf-8"))

    def _send_audio(self, sock: socket.socket, seq_no: int, payload: bytes) -> None:
        message = {
            "type": "audio",
            "magic": AUDIO_FRAME_MAGIC,
            "seq_no": seq_no,
            "audio_b64": base64.b64encode(payload).decode("ascii"),
        }
        sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

    def _wait_for(self, predicate, timeout: float = 3.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def test_four_devices_register_simultaneously(self) -> None:
        for source_id in DEVICE_IDS:
            self._connect(source_id)

        self.assertTrue(self._wait_for(lambda: len(self.server.connected_source_ids()) == 4))
        self.assertEqual(self.server.connected_source_ids(), sorted(DEVICE_IDS))

    def test_concurrent_audio_is_attributed_to_the_right_device(self) -> None:
        sockets = {source_id: self._connect(source_id) for source_id in DEVICE_IDS}
        self.assertTrue(self._wait_for(lambda: len(self.server.connected_source_ids()) == 4))

        def stream(source_id: str) -> None:
            for seq_no in range(1, 6):
                self._send_audio(sockets[source_id], seq_no, f"{source_id}:{seq_no}".encode("utf-8"))

        threads = [threading.Thread(target=stream, args=(source_id,)) for source_id in DEVICE_IDS]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5.0)

        self.assertTrue(self._wait_for(lambda: len(self._recorded()) == 20))
        for packet in self._recorded():
            self.assertTrue(packet.payload.decode("utf-8").startswith(f"{packet.source_id}:"))

    def test_speak_push_reaches_only_the_addressed_device(self) -> None:
        sockets = {source_id: self._connect(source_id) for source_id in DEVICE_IDS}
        self.assertTrue(self._wait_for(lambda: len(self.server.connected_source_ids()) == 4))

        target = "node-3"
        self.assertTrue(
            self.server.send_to_device(target, {"type": "speak", "speech_id": "s1", "seq_no": 1})
        )

        self.assertEqual(self._read_line(sockets[target]).get("speech_id"), "s1")
        for source_id in DEVICE_IDS:
            if source_id != target:
                self.assertEqual(self._read_line(sockets[source_id], timeout=0.3), {})

    def test_concurrent_pushes_stay_line_delimited(self) -> None:
        sockets = {source_id: self._connect(source_id) for source_id in DEVICE_IDS}
        self.assertTrue(self._wait_for(lambda: len(self.server.connected_source_ids()) == 4))

        def push(source_id: str) -> None:
            for seq_no in range(1, 11):
                self.server.send_to_device(
                    source_id,
                    {"type": "speak", "speech_id": source_id, "seq_no": seq_no, "audio_b64": "AAAA" * 64},
                )

        threads = [threading.Thread(target=push, args=(source_id,)) for source_id in DEVICE_IDS]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5.0)

        for source_id in DEVICE_IDS:
            for expected_seq in range(1, 11):
                message = self._read_line(sockets[source_id])
                self.assertEqual(message.get("speech_id"), source_id)
                self.assertEqual(message.get("seq_no"), expected_seq)

    def test_reconnect_replaces_the_previous_channel_for_the_same_device(self) -> None:
        first = self._connect("node-1")
        self.assertTrue(self._wait_for(lambda: "node-1" in self.server.connected_source_ids()))
        first.close()
        self.assertTrue(self._wait_for(lambda: "node-1" not in self.server.connected_source_ids()))

        second = self._connect("node-1")
        self.assertTrue(self._wait_for(lambda: "node-1" in self.server.connected_source_ids()))
        self.assertEqual(self.server.connected_source_ids().count("node-1"), 1)

        self.assertTrue(self.server.send_to_device("node-1", {"type": "speak", "speech_id": "s2"}))
        self.assertEqual(self._read_line(second).get("speech_id"), "s2")

    def test_one_device_dropping_does_not_disturb_the_others(self) -> None:
        sockets = {source_id: self._connect(source_id) for source_id in DEVICE_IDS}
        self.assertTrue(self._wait_for(lambda: len(self.server.connected_source_ids()) == 4))

        sockets["node-2"].close()
        self.assertTrue(self._wait_for(lambda: "node-2" not in self.server.connected_source_ids()))

        for source_id in ["node-1", "node-3", "node-4"]:
            self.assertTrue(
                self.server.send_to_device(source_id, {"type": "speak", "speech_id": source_id})
            )
            self.assertEqual(self._read_line(sockets[source_id]).get("speech_id"), source_id)


if __name__ == "__main__":
    unittest.main()
