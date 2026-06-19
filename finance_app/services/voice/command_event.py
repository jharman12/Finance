from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class VoiceCommandEvent:
    text: str
    source_id: str
    session_id: str
    provider: str
    confidence_0_1: float | None = None
    latency_ms: float | None = None
    used_fallback: bool = False
    fallback_reason: str | None = None
