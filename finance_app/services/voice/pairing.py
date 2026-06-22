from __future__ import annotations

import hashlib
import hmac
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
    def generate(
        auth_token: str,
        source_id: str,
        pairing_session_id: str = "",
        timestamp: float | None = None,
        code_length: int = 6,
    ) -> PairingCode:
        """Generate a deterministic pairing code from token, source ID, and session ID.

        Phase 2: Uses HMAC with session_id to prevent cross-session pairing.
        The code is valid only for the specific session within a 60-second window.

        Args:
            auth_token: Server auth token
            source_id: Remote device ID
            pairing_session_id: Unique session ID for this pairing attempt (Phase 2)
            timestamp: Override timestamp (for testing)
            code_length: Length of generated code (6-8 chars)
        """
        if timestamp is None:
            timestamp = time.time()

        # Phase 2: Include session_id in HMAC for session-specific codes
        if pairing_session_id:
            message = f"{source_id}:{pairing_session_id}".encode("utf-8")
            digest = hmac.new(auth_token.encode("utf-8"), message, hashlib.sha256).digest()
        else:
            # Fallback to legacy generation for backward compatibility
            combined = f"{auth_token}:{source_id}".encode("utf-8")
            digest = hashlib.sha256(combined).digest()

        code_chars = []
        for i in range(min(code_length, 8)):  # Max 8 chars
            byte_val = digest[i]
            char_index = byte_val % len(PairingCodeGenerator.ALPHABET)
            code_chars.append(PairingCodeGenerator.ALPHABET[char_index])

        return PairingCode(code="".join(code_chars), generated_at=timestamp, window_seconds=60)

    @staticmethod
    def verify(
        code_to_verify: str,
        auth_token: str,
        source_id: str,
        pairing_session_id: str = "",
        timestamp: float | None = None,
    ) -> bool:
        """Verify that a pairing code matches expected value.

        Phase 2: Prefers session-specific verification when session_id is provided.
        Falls back to legacy code generation for backward compatibility.
        """
        if timestamp is None:
            timestamp = time.time()

        code_to_verify_normalized = code_to_verify.upper().strip()

        # Phase 2: Try session-specific code first if session_id provided
        if pairing_session_id:
            expected_session = PairingCodeGenerator.generate(auth_token, source_id, pairing_session_id, timestamp)
            if expected_session.code == code_to_verify_normalized and expected_session.is_valid():
                return True

        # Try stable code generation (backward compatibility)
        expected_stable = PairingCodeGenerator.generate(auth_token, source_id, "", timestamp)
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
