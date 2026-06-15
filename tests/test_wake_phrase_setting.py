from __future__ import annotations

import unittest
from unittest.mock import Mock

from PyQt5.QtWidgets import QApplication, QLineEdit

from finance_app.ui.main_window import MainWindow


class WakePhraseSettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_apply_wake_phrase_updates_setting_and_surfaces(self) -> None:
        window = MainWindow()
        try:
            window.app_controller.set_setting = Mock()

            assistant_input = window._voice_ui["assistant"]["wake_input"]  # noqa: SLF001
            self.assertIsInstance(assistant_input, QLineEdit)
            assistant_input.setText("Computer")

            window._apply_wake_phrase_from_surface("assistant")  # noqa: SLF001

            window.app_controller.set_setting.assert_called_once_with("voice_wake_phrase", "Computer")
            self.assertEqual(window._wake_phrase, "Computer")  # noqa: SLF001
            self.assertEqual(window.voice_coordinator.router.wake_phrase, "computer")

            testing_input = window._voice_ui["testing"]["wake_input"]  # noqa: SLF001
            self.assertIsInstance(testing_input, QLineEdit)
            self.assertEqual(testing_input.text(), "Computer")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
