"""Manage pairing state for remote voice connections."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class PairingState:
    """State of an active pairing session."""

    source_id: str
    expected_pairing_code: str
    pairing_session_id: str
    session_created_at: float
    session_timeout_seconds: float = 60.0  # 30-60s window as per Phase 2 spec
    confirmed: bool = False

    def is_session_expired(self) -> bool:
        """Check if pairing session has expired."""
        elapsed = time.time() - self.session_created_at
        return elapsed > self.session_timeout_seconds

    def get_session_age_seconds(self) -> float:
        """Get age of pairing session in seconds."""
        return time.time() - self.session_created_at


class RemoteVoicePairingManager:
    """Manages pairing state for incoming remote voice connections."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pairing_state: PairingState | None = None
        self._on_pairing_confirmed: Callable[[str, str], None] | None = None

    def set_callbacks(self, on_confirmed: Callable[[str, str], None] | None = None) -> None:
        """Set callback functions."""
        with self._lock:
            self._on_pairing_confirmed = on_confirmed

    def start_pairing(self, source_id: str, expected_code: str, pairing_session_id: str = "") -> None:
        """Start waiting for a pairing connection.
        
        Args:
            source_id: ID of the remote device to pair
            expected_code: Expected pairing code for verification
            pairing_session_id: Unique session ID for this pairing attempt (required for Phase 2)
        """
        with self._lock:
            self._pairing_state = PairingState(
                source_id=source_id,
                expected_pairing_code=expected_code,
                pairing_session_id=pairing_session_id,
                session_created_at=time.time(),
            )

    def cancel_pairing(self) -> None:
        """Cancel the active pairing session."""
        with self._lock:
            self._pairing_state = None

    def is_pairing(self) -> bool:
        """Check if currently waiting for a pairing connection."""
        with self._lock:
            return self._pairing_state is not None

    def verify_pairing_code(self, source_id: str, pairing_code: str, pairing_session_id: str = "") -> bool:
        """
        Verify incoming pairing code and session ID.

        Returns True if pairing is confirmed and session is valid, False otherwise.
        """
        callback: Callable[[str, str], None] | None = None
        with self._lock:
            if self._pairing_state is None:
                return False

            # Check if session has expired
            if self._pairing_state.is_session_expired():
                return False

            # Check if source matches
            if self._pairing_state.source_id != source_id:
                return False

            # Check if session ID matches (Phase 2 requirement)
            if pairing_session_id and self._pairing_state.pairing_session_id != pairing_session_id:
                return False

            # Check if code matches
            if self._pairing_state.expected_pairing_code != pairing_code:
                return False

            self._pairing_state.confirmed = True
            callback = self._on_pairing_confirmed

        # Keep callback invocation synchronous here; UI dispatch should be marshaled
        # by the callback target via Qt queued signals.
        if callback is not None:
            self._safe_invoke_callback(callback, source_id, pairing_code)

        return True

    @staticmethod
    def _safe_invoke_callback(callback: Callable[[str, str], None], source_id: str, pairing_code: str) -> None:
        try:
            callback(source_id, pairing_code)
        except Exception:
            return

    def get_pairing_state(self) -> PairingState | None:
        """Get current pairing state."""
        with self._lock:
            return self._pairing_state
