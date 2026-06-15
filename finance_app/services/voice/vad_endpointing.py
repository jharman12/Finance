from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class EndpointDecision:
    speech_started: bool = False
    utterance_complete: bool = False
    reason: str = ""
    speech_ms: int = 0


class VoiceActivityEndpoint:
    """Simple energy-based endpointing for command utterances."""

    def __init__(
        self,
        min_speech_ms: int = 300,
        end_silence_ms: int = 700,
        max_utterance_ms: int = 12000,
        energy_threshold: float = 450.0,
    ) -> None:
        self.min_speech_ms = min_speech_ms
        self.end_silence_ms = end_silence_ms
        self.max_utterance_ms = max_utterance_ms
        self.energy_threshold = energy_threshold
        self.reset()

    def reset(self) -> None:
        self._speech_started = False
        self._speech_ms = 0
        self._silence_ms = 0
        self._total_ms = 0

    def process_chunk(self, chunk: bytes, sample_rate: int) -> EndpointDecision:
        frame_ms = int((len(chunk) / 2) * 1000 / max(sample_rate, 1))
        if frame_ms <= 0:
            frame_ms = 20

        is_speech = self._is_speech_chunk(chunk)
        self._total_ms += frame_ms

        if is_speech:
            if not self._speech_started:
                self._speech_started = True
            self._speech_ms += frame_ms
            self._silence_ms = 0
        elif self._speech_started:
            self._silence_ms += frame_ms

        if self._total_ms >= self.max_utterance_ms:
            return EndpointDecision(
                speech_started=self._speech_started,
                utterance_complete=self._speech_started,
                reason="max_utterance",
                speech_ms=self._speech_ms,
            )

        if (
            self._speech_started
            and self._speech_ms >= self.min_speech_ms
            and self._silence_ms >= self.end_silence_ms
        ):
            return EndpointDecision(
                speech_started=True,
                utterance_complete=True,
                reason="silence",
                speech_ms=self._speech_ms,
            )

        return EndpointDecision(
            speech_started=self._speech_started,
            utterance_complete=False,
            reason="listening",
            speech_ms=self._speech_ms,
        )

    def is_speech_chunk(self, chunk: bytes) -> bool:
        return self._is_speech_chunk(chunk)

    def _is_speech_chunk(self, chunk: bytes) -> bool:
        if not chunk:
            return False

        # Approximate RMS from int16 PCM without extra dependencies.
        sample_count = len(chunk) // 2
        if sample_count == 0:
            return False

        total_sq = 0.0
        for i in range(0, len(chunk) - 1, 2):
            sample = int.from_bytes(chunk[i : i + 2], byteorder="little", signed=True)
            total_sq += float(sample * sample)

        rms = (total_sq / sample_count) ** 0.5
        return rms >= self.energy_threshold
