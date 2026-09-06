"""Signal quality metrics for incoming PCM16 audio (clipping, level, rough SNR)."""

from __future__ import annotations

import array
import math
from dataclasses import dataclass

_FULL_SCALE = 32768.0
_CLIP_THRESHOLD = 32000
_FRAME_MS = 10


@dataclass(frozen=True, slots=True)
class AudioQualityMetrics:
    frames: int
    rms_dbfs: float
    peak_dbfs: float
    clipped_ratio: float
    estimated_snr_db: float

    @property
    def is_clipping(self) -> bool:
        return self.clipped_ratio >= 0.01

    @property
    def is_too_quiet(self) -> bool:
        return self.rms_dbfs < -45.0


def _dbfs(amplitude: float) -> float:
    if amplitude <= 0:
        return -120.0
    return max(-120.0, 20.0 * math.log10(amplitude / _FULL_SCALE))


def analyze_pcm16(payload: bytes, sample_rate: int = 16000) -> AudioQualityMetrics:
    """Summarize one chunk of mono PCM16 audio."""
    usable = len(payload) - (len(payload) % 2)
    if usable <= 0:
        return AudioQualityMetrics(0, -120.0, -120.0, 0.0, 0.0)

    samples = array.array("h")
    samples.frombytes(payload[:usable])

    peak = 0
    clipped = 0
    total_square = 0.0
    for sample in samples:
        magnitude = abs(sample)
        if magnitude > peak:
            peak = magnitude
        if magnitude >= _CLIP_THRESHOLD:
            clipped += 1
        total_square += float(sample) * float(sample)

    count = len(samples)
    rms = math.sqrt(total_square / count)

    return AudioQualityMetrics(
        frames=count,
        rms_dbfs=round(_dbfs(rms), 2),
        peak_dbfs=round(_dbfs(peak), 2),
        clipped_ratio=round(clipped / count, 4),
        estimated_snr_db=round(_estimate_snr_db(samples, sample_rate), 2),
    )


def _estimate_snr_db(samples: array.array, sample_rate: int) -> float:
    """Compare loud frames against the quiet noise floor of the same chunk."""
    frame_size = max(1, int(sample_rate * _FRAME_MS / 1000))
    if len(samples) < frame_size * 4:
        return 0.0

    frame_rms: list[float] = []
    for start in range(0, len(samples) - frame_size + 1, frame_size):
        total = 0.0
        for index in range(start, start + frame_size):
            value = float(samples[index])
            total += value * value
        frame_rms.append(math.sqrt(total / frame_size))

    frame_rms.sort()
    # Digital silence would divide by zero, so the floor is one quantization step.
    noise = max(frame_rms[len(frame_rms) // 10], 1.0)
    signal = frame_rms[(len(frame_rms) * 9) // 10]
    if signal <= 0:
        return 0.0
    return min(90.0, max(0.0, 20.0 * math.log10(signal / noise)))
