from __future__ import annotations

import unittest

from finance_app.services.voice.vad_endpointing import VoiceActivityEndpoint


def _speech_chunk(samples: int = 1600, amplitude: int = 2000) -> bytes:
    return b"".join(int(amplitude).to_bytes(2, byteorder="little", signed=True) for _ in range(samples))


def _silence_chunk(samples: int = 1600) -> bytes:
    return b"\x00\x00" * samples


class VoiceActivityEndpointTests(unittest.TestCase):
    def test_detects_end_after_silence(self) -> None:
        endpoint = VoiceActivityEndpoint(min_speech_ms=200, end_silence_ms=300, energy_threshold=100.0)

        for _ in range(3):
            decision = endpoint.process_chunk(_speech_chunk(), sample_rate=16000)
            self.assertFalse(decision.utterance_complete)

        done = False
        for _ in range(5):
            decision = endpoint.process_chunk(_silence_chunk(), sample_rate=16000)
            if decision.utterance_complete:
                done = True
                break

        self.assertTrue(done)

    def test_max_utterance_forces_completion(self) -> None:
        endpoint = VoiceActivityEndpoint(min_speech_ms=200, end_silence_ms=800, max_utterance_ms=250, energy_threshold=100.0)

        decision = endpoint.process_chunk(_speech_chunk(), sample_rate=16000)
        self.assertFalse(decision.utterance_complete)

        decision = endpoint.process_chunk(_speech_chunk(), sample_rate=16000)
        self.assertFalse(decision.utterance_complete)

        decision = endpoint.process_chunk(_speech_chunk(), sample_rate=16000)
        self.assertTrue(decision.utterance_complete)
        self.assertEqual(decision.reason, "max_utterance")


if __name__ == "__main__":
    unittest.main()
