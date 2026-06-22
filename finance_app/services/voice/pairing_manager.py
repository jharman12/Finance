"""Manage pairing state for remote voice connections."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class PairingState:
    """State of an active pairing session."""

    source_id: str
    expected_pairing_code: str
    confirmed: bool = False


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

    def start_pairing(self, source_id: str, expected_code: str) -> None:
        """Start waiting for a pairing connection."""
        with self._lock:
            self._pairing_state = PairingState(source_id=source_id, expected_pairing_code=expected_code)

    def cancel_pairing(self) -> None:
        """Cancel the active pairing session."""
        with self._lock:
            self._pairing_state = None

    def is_pairing(self) -> bool:
        """Check if currently waiting for a pairing connection."""
        with self._lock:
            return self._pairing_state is not None

    def verify_pairing_code(self, source_id: str, pairing_code: str) -> bool:
        """
        Verify incoming pairing code.

        Returns True if pairing is confirmed, False otherwise.
        """
        callback: Callable[[str, str], None] | None = None
        with self._lock:
            if self._pairing_state is None:
                return False

            # Check if source matches
            if self._pairing_state.source_id != source_id:
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
