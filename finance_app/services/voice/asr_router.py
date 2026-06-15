from __future__ import annotations

from .asr_provider import AsrProvider, AsrResult


class AsrRouter:
    def __init__(
        self,
        primary: AsrProvider,
        fallback: AsrProvider | None = None,
        accept_confidence: float = 0.62,
        fallback_trigger_confidence: float = 0.48,
        min_chars_for_accept: int = 2,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.accept_confidence = accept_confidence
        self.fallback_trigger_confidence = fallback_trigger_confidence
        self.min_chars_for_accept = min_chars_for_accept

    def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int) -> AsrResult:
        try:
            primary_result = self.primary.transcribe_pcm16(audio_bytes, sample_rate)
        except Exception:
            if self.fallback is None:
                raise
            fallback_result = self.fallback.transcribe_pcm16(audio_bytes, sample_rate)
            fallback_result.used_fallback = True
            fallback_result.fallback_reason = "provider_error"
            return fallback_result

        if self._accept(primary_result):
            return primary_result

        if self.fallback is None:
            return primary_result

        fallback_result = self.fallback.transcribe_pcm16(audio_bytes, sample_rate)
        fallback_result.used_fallback = True
        fallback_result.fallback_reason = self._fallback_reason(primary_result)

        if self._accept(fallback_result):
            return fallback_result

        if len(fallback_result.text.strip()) > len(primary_result.text.strip()):
            return fallback_result
        return primary_result

    def _accept(self, result: AsrResult) -> bool:
        if len(result.text.strip()) < self.min_chars_for_accept:
            return False
        return result.confidence_0_1 >= self.accept_confidence

    def _fallback_reason(self, primary_result: AsrResult) -> str:
        if len(primary_result.text.strip()) < self.min_chars_for_accept:
            return "empty_text"
        if primary_result.confidence_0_1 < self.fallback_trigger_confidence:
            return "low_confidence"
        return "quality_check"
