from __future__ import annotations

from enum import Enum


class VoiceSessionState(str, Enum):
    IDLE = "idle"
    WAKE_DETECTED = "wake_detected"
    CAPTURING = "capturing"
    DECODING = "decoding"
    DISPATCHING = "dispatching"
    COOLDOWN = "cooldown"
    ERROR = "error"
