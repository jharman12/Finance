from __future__ import annotations

import unittest
from unittest.mock import Mock

from PyQt5.QtWidgets import QApplication

from finance_app.ui.main_window import MainWindow


class VoiceTestTabRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_testing_mode_command_does_not_send_prompt(self) -> None:
        window = MainWindow()
        try:
            window.send_prompt = Mock()
            window._voice_active_surface = "testing"  # noqa: SLF001

            window._handle_voice_command("test spoken phrase")

            self.assertEqual(window.voice_test_output.toPlainText().strip(), "test spoken phrase")
            window.send_prompt.assert_not_called()
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
