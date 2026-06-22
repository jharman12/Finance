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

        The code is stable for a given token and source ID during a pairing session.
        Timestamp is accepted for API compatibility but not used in current generation.
        """
        if timestamp is None:
            timestamp = time.time()

        combined = f"{auth_token}:{source_id}".encode("utf-8")
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

        Accepts current stable code and legacy minute-window codes for compatibility.
        """
        if timestamp is None:
            timestamp = time.time()

        code_to_verify_normalized = code_to_verify.upper().strip()

        expected_stable = PairingCodeGenerator.generate(auth_token, source_id, timestamp)
        if expected_stable.code == code_to_verify_normalized:
            return True

        # Backward compatibility for older minute-window code generation.
        for window_offset in (-1, 0, 1):
            check_time = timestamp + (window_offset * 60)
            time_window = int(check_time / 60)
            combined = f"{auth_token}:{source_id}:{time_window}".encode("utf-8")
            digest = hashlib.sha256(combined).digest()
            code_chars = []
            for i in range(6):
                byte_val = digest[i]
                char_index = byte_val % len(PairingCodeGenerator.ALPHABET)
                code_chars.append(PairingCodeGenerator.ALPHABET[char_index])
            expected = "".join(code_chars)
            if expected == code_to_verify_normalized:
                return True

        return False
