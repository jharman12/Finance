from __future__ import annotations

import unittest
from unittest.mock import Mock

from PyQt5.QtWidgets import QApplication

from finance_app.services.voice.command_event import VoiceCommandEvent
from finance_app.ui.main_window import MainWindow


class VoiceAssistantConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_medium_confidence_mutation_requires_confirmation(self) -> None:
        window = MainWindow()
        try:
            window.send_prompt = Mock()
            window._voice_active_surface = "assistant"  # noqa: SLF001

            window._handle_voice_command(
                VoiceCommandEvent(
                    text="add expense 25 groceries",
                    source_id="node-1",
                    session_id="voice-1",
                    provider="fake",
                    confidence_0_1=0.72,
                    latency_ms=25.0,
                )
            )

            window.send_prompt.assert_not_called()
            self.assertTrue(window._voice_pending_confirmations)  # noqa: SLF001

            window._handle_voice_command(
                VoiceCommandEvent(
                    text="confirm",
                    source_id="node-1",
                    session_id="voice-2",
                    provider="fake",
                    confidence_0_1=0.95,
                )
            )

            window.send_prompt.assert_called_once()
            self.assertFalse(window._voice_pending_confirmations)  # noqa: SLF001
            self.assertEqual(window.chat_input.text().strip(), "add expense 25 groceries")
        finally:
            window.close()

    def test_rejection_cancels_pending_command(self) -> None:
        window = MainWindow()
        try:
            window.send_prompt = Mock()
            window._voice_active_surface = "assistant"  # noqa: SLF001

            window._handle_voice_command(
                VoiceCommandEvent(
                    text="delete transaction 10",
                    source_id="node-2",
                    session_id="voice-3",
                    provider="fake",
                    confidence_0_1=0.72,
                )
            )
            self.assertTrue(window._voice_pending_confirmations)  # noqa: SLF001

            window._handle_voice_command(
                VoiceCommandEvent(
                    text="cancel",
                    source_id="node-2",
                    session_id="voice-4",
                    provider="fake",
                    confidence_0_1=0.94,
                )
            )

            window.send_prompt.assert_not_called()
            self.assertFalse(window._voice_pending_confirmations)  # noqa: SLF001
        finally:
            window.close()

    def test_duplicate_session_id_is_ignored(self) -> None:
        window = MainWindow()
        try:
            window.send_prompt = Mock()
            window._voice_active_surface = "assistant"  # noqa: SLF001

            event = VoiceCommandEvent(
                text="show me my spending summary",
                source_id="node-3",
                session_id="voice-dup-1",
                provider="fake",
                confidence_0_1=0.95,
            )

            window._handle_voice_command(event)
            window._handle_voice_command(event)

            window.send_prompt.assert_called_once()
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
