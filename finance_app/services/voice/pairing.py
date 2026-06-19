from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


@dataclass(slots=True)
class PairingCode:
    """Short code for user verification during pairing."""

    code: str
    generated_at: float
    window_seconds: int = 300

    def is_expired(self) -> bool:
        elapsed = time.time() - self.generated_at
        return elapsed > self.window_seconds

    def is_valid(self) -> bool:
        return not self.is_expired()


class PairingCodeGenerator:
    """Generate and verify human-readable pairing codes."""

    ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # Avoid 0, 1, O, I, S, Z for clarity

    @staticmethod
    def generate(auth_token: str, source_id: str, timestamp: float | None = None, code_length: int = 6) -> PairingCode:
        """Generate a deterministic pairing code from token and source ID.

        The code changes every 60 seconds, so tokens need to be re-verified frequently.
        """
        if timestamp is None:
            timestamp = time.time()

        time_window = int(timestamp / 60)
        combined = f"{auth_token}:{source_id}:{time_window}".encode("utf-8")
        digest = hashlib.sha256(combined).digest()

        code_chars = []
        for i in range(code_length):
            byte_val = digest[i]
            char_index = byte_val % len(PairingCodeGenerator.ALPHABET)
            code_chars.append(PairingCodeGenerator.ALPHABET[char_index])

        return PairingCode(code="".join(code_chars), generated_at=timestamp, window_seconds=300)

    @staticmethod
    def verify(code_to_verify: str, auth_token: str, source_id: str, timestamp: float | None = None) -> bool:
        """Verify that a pairing code matches expected value.

        Checks current window and adjacent windows (previous/next) for time skew tolerance.
        """
        if timestamp is None:
            timestamp = time.time()

        code_to_verify_normalized = code_to_verify.upper().strip()

        for window_offset in (-1, 0, 1):
            check_time = timestamp + (window_offset * 60)
            expected = PairingCodeGenerator.generate(auth_token, source_id, check_time)
            if expected.code == code_to_verify_normalized:
                return True

        return False
