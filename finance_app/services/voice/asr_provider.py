from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class AsrResult:
    text: str
    provider: str
    confidence_0_1: float = 0.0
    latency_ms: int = 0
    is_final: bool = True
    no_speech_0_1: float = 0.0
    fallback_reason: str | None = None
    used_fallback: bool = False


class AsrProvider(Protocol):
    """Provider contract for one-shot utterance transcription."""

    name: str

    def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int) -> AsrResult:
        ...
