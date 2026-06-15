from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from finance_app.services.voice_pipeline import VoiceCoordinator


class _FakeRecognizer:
    def __init__(self, parts: list[str]) -> None:
        self._parts = list(parts)

    def AcceptWaveform(self, chunk: bytes) -> bool:  # noqa: N802, ARG002
        return False

    def PartialResult(self) -> str:  # noqa: N802
        part = self._parts.pop(0) if self._parts else ""
        return json.dumps({"partial": part})

    def Result(self) -> str:  # noqa: N802
        return json.dumps({"text": ""})


class VoicePartialRateLimitTests(unittest.TestCase):
    def test_partial_emits_are_rate_limited(self) -> None:
        coordinator = VoiceCoordinator(wake_phrase="hey steven")
        coordinator._partial_preview_recognizer = _FakeRecognizer(["add", "add expense", "add expense today"])  # noqa: SLF001
        coordinator._partial_emit_interval_seconds = 0.2  # noqa: SLF001

        received: list[str] = []
        coordinator.on_partial = received.append

        with patch("finance_app.services.voice_pipeline.time.monotonic", side_effect=[1.0, 1.1, 1.4]):
            coordinator._emit_partial_preview(b"A")  # noqa: SLF001
            coordinator._emit_partial_preview(b"B")  # noqa: SLF001
            coordinator._emit_partial_preview(b"C")  # noqa: SLF001

        self.assertEqual(received, ["add", "add expense today"])


if __name__ == "__main__":
    unittest.main()
