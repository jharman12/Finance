from __future__ import annotations

import base64
import threading
import unittest

from finance_app.services.voice.tts_provider import RemoteSpeakerSink, SynthesizedSpeech
from remote_voice_sender import RemoteSpeechPlayer


class RemoteSpeakerSinkTests(unittest.TestCase):
    """Main-PC sink that streams PCM to a paired device."""

    def setUp(self) -> None:
        self.sent: list[dict] = []
        self.sink = RemoteSpeakerSink("node-1", self._send, chunk_bytes=8)

    def _send(self, source_id: str, message: dict) -> bool:
        self.sent.append({"source_id": source_id, **message})
        return True

    def _speech(self, pcm: bytes) -> SynthesizedSpeech:
        return SynthesizedSpeech(pcm16=pcm, sample_rate=16000, channels=1)

    def test_pcm_is_chunked_with_increasing_seq_and_single_final(self) -> None:
        self.sink.play(self._speech(b"\x01\x02" * 10), threading.Event())

        self.assertEqual([m["seq_no"] for m in self.sent], [1, 2, 3])
        self.assertEqual([m["final"] for m in self.sent], [False, False, True])
        self.assertTrue(all(m["type"] == "speak" for m in self.sent))
        self.assertTrue(all(m["source_id"] == "node-1" for m in self.sent))

    def test_chunks_reassemble_to_original_pcm(self) -> None:
        pcm = bytes(range(40))
        self.sink.play(self._speech(pcm), threading.Event())

        joined = b"".join(base64.b64decode(m["audio_b64"]) for m in self.sent)
        self.assertEqual(joined, pcm)

    def test_all_chunks_share_one_speech_id(self) -> None:
        self.sink.play(self._speech(b"\x00" * 24), threading.Event())

        self.assertEqual(len({m["speech_id"] for m in self.sent}), 1)

    def test_empty_speech_sends_nothing(self) -> None:
        self.sink.play(self._speech(b""), threading.Event())

        self.assertEqual(self.sent, [])

    def test_cancelled_before_start_sends_cancel_not_audio(self) -> None:
        cancel = threading.Event()
        cancel.set()
        self.sink.play(self._speech(b"\x00" * 24), cancel)

        self.assertEqual([m["type"] for m in self.sent], ["speak_cancel"])

    def test_send_failure_stops_streaming(self) -> None:
        def failing_send(source_id: str, message: dict) -> bool:
            self.sent.append(message)
            return False

        sink = RemoteSpeakerSink("node-1", failing_send, chunk_bytes=8)
        sink.play(self._speech(b"\x00" * 40), threading.Event())

        self.assertEqual(len(self.sent), 1)


class RemoteSpeechPlayerTests(unittest.TestCase):
    """Device-side intake of speak messages (queueing, cancellation, acks)."""

    def setUp(self) -> None:
        self.acks: list[dict] = []
        self.player = RemoteSpeechPlayer(self._send_ack)

    def _send_ack(self, message: dict) -> bool:
        self.acks.append(message)
        return True

    def _speak(self, speech_id: str = "s1", seq_no: int = 1, final: bool = False, **overrides) -> dict:
        message = {
            "type": "speak",
            "speech_id": speech_id,
            "seq_no": seq_no,
            "final": final,
            "encoding": "pcm_s16le",
            "sample_rate": 16000,
            "channels": 1,
            "audio_b64": base64.b64encode(b"\x00\x01" * 4).decode("ascii"),
        }
        message.update(overrides)
        return message

    def _queued(self) -> list:
        return list(self.player._queue.queue)

    def test_speak_message_is_queued_for_playback(self) -> None:
        self.player.handle_message(self._speak())

        queued = self._queued()
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].speech_id, "s1")
        self.assertEqual(queued[0].pcm, b"\x00\x01" * 4)

    def test_unsupported_encoding_is_rejected_with_error_ack(self) -> None:
        self.player.handle_message(self._speak(encoding="opus"))

        self.assertEqual(self._queued(), [])
        self.assertEqual(self.acks[-1]["state"], "error")

    def test_invalid_base64_is_rejected_with_error_ack(self) -> None:
        self.player.handle_message(self._speak(audio_b64="not base64!!"))

        self.assertEqual(self._queued(), [])
        self.assertEqual(self.acks[-1]["state"], "error")

    def test_cancel_drops_queued_chunks_and_acks_cancelled(self) -> None:
        self.player.handle_message(self._speak(seq_no=1))
        self.player.handle_message(self._speak(seq_no=2))
        self.player.handle_message(self._speak(speech_id="s2", seq_no=1))

        self.player.handle_message({"type": "speak_cancel", "speech_id": "s1"})

        self.assertEqual([chunk.speech_id for chunk in self._queued()], ["s2"])
        self.assertEqual(self.acks[-1], {"type": "speak_ack", "speech_id": "s1", "seq_no": 0, "state": "cancelled"})

    def test_chunks_arriving_after_cancel_are_dropped(self) -> None:
        self.player.handle_message({"type": "speak_cancel", "speech_id": "s1"})
        self.player.handle_message(self._speak(seq_no=1))

        self.assertEqual(self._queued(), [])

    def test_unknown_message_type_is_ignored(self) -> None:
        self.player.handle_message({"type": "some_future_thing", "speech_id": "s1"})

        self.assertEqual(self._queued(), [])
        self.assertEqual(self.acks, [])


if __name__ == "__main__":
    unittest.main()
