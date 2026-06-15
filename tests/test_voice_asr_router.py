from __future__ import annotations

import unittest

from finance_app.services.voice.asr_provider import AsrResult
from finance_app.services.voice.asr_router import AsrRouter


class _FakeProvider:
    def __init__(self, name: str, result: AsrResult | None = None, should_raise: bool = False) -> None:
        self.name = name
        self._result = result
        self._should_raise = should_raise

    def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int) -> AsrResult:  # noqa: ARG002
        if self._should_raise:
            raise RuntimeError("provider failed")
        if self._result is None:
            raise RuntimeError("missing fake result")
        return self._result


class AsrRouterTests(unittest.TestCase):
    def test_uses_primary_when_confident(self) -> None:
        primary = _FakeProvider(
            "faster_whisper",
            AsrResult(text="add grocery expense", provider="faster_whisper", confidence_0_1=0.91),
        )
        fallback = _FakeProvider(
            "vosk",
            AsrResult(text="bad transcript", provider="vosk", confidence_0_1=0.4),
        )
        router = AsrRouter(primary=primary, fallback=fallback)

        result = router.transcribe_pcm16(b"audio", 16000)

        self.assertEqual(result.provider, "faster_whisper")
        self.assertFalse(result.used_fallback)

    def test_falls_back_when_primary_errors(self) -> None:
        primary = _FakeProvider("faster_whisper", should_raise=True)
        fallback = _FakeProvider(
            "vosk",
            AsrResult(text="add dining expense", provider="vosk", confidence_0_1=0.7),
        )
        router = AsrRouter(primary=primary, fallback=fallback)

        result = router.transcribe_pcm16(b"audio", 16000)

        self.assertEqual(result.provider, "vosk")
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.fallback_reason, "provider_error")

    def test_falls_back_when_primary_low_confidence(self) -> None:
        primary = _FakeProvider(
            "faster_whisper",
            AsrResult(text="a", provider="faster_whisper", confidence_0_1=0.2),
        )
        fallback = _FakeProvider(
            "vosk",
            AsrResult(text="add transport expense", provider="vosk", confidence_0_1=0.8),
        )
        router = AsrRouter(primary=primary, fallback=fallback)

        result = router.transcribe_pcm16(b"audio", 16000)

        self.assertEqual(result.provider, "vosk")
        self.assertTrue(result.used_fallback)


if __name__ == "__main__":
    unittest.main()
