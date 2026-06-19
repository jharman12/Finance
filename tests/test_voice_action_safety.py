from __future__ import annotations

import unittest

from finance_app.services.voice.action_safety import (
    evaluate_voice_command_event,
    is_confirmation_phrase,
    is_rejection_phrase,
)
from finance_app.services.voice.command_event import VoiceCommandEvent


class VoiceActionSafetyTests(unittest.TestCase):
    def test_mutation_medium_confidence_requires_confirm(self) -> None:
        event = VoiceCommandEvent(
            text="add expense 25 groceries",
            source_id="node-1",
            session_id="voice-1",
            provider="fake",
            confidence_0_1=0.72,
        )

        decision = evaluate_voice_command_event(event)
        self.assertEqual(decision.mode, "confirm")

    def test_low_confidence_requires_clarify(self) -> None:
        event = VoiceCommandEvent(
            text="add expense 25 groceries",
            source_id="node-1",
            session_id="voice-1",
            provider="fake",
            confidence_0_1=0.42,
        )

        decision = evaluate_voice_command_event(event)
        self.assertEqual(decision.mode, "clarify")

    def test_readonly_medium_confidence_executes(self) -> None:
        event = VoiceCommandEvent(
            text="show me my spending summary",
            source_id="node-1",
            session_id="voice-1",
            provider="fake",
            confidence_0_1=0.70,
        )

        decision = evaluate_voice_command_event(event)
        self.assertEqual(decision.mode, "execute")

    def test_confirmation_and_rejection_phrases(self) -> None:
        self.assertTrue(is_confirmation_phrase("confirm"))
        self.assertTrue(is_confirmation_phrase("go ahead"))
        self.assertTrue(is_rejection_phrase("cancel"))
        self.assertTrue(is_rejection_phrase("never mind"))


if __name__ == "__main__":
    unittest.main()
