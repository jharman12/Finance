from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QMessageBox

from finance_app.services.voice.command_event import VoiceCommandEvent
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

    def test_testing_mode_structured_command_does_not_send_prompt(self) -> None:
        window = MainWindow()
        try:
            window.send_prompt = Mock()
            window._voice_active_surface = "testing"  # noqa: SLF001

            window._handle_voice_command(
                VoiceCommandEvent(
                    text="test structured phrase",
                    source_id="node-1",
                    session_id="voice-1",
                    provider="fake",
                    confidence_0_1=0.91,
                    latency_ms=37.0,
                )
            )

            self.assertEqual(window.voice_test_output.toPlainText().strip(), "test structured phrase")
            window.send_prompt.assert_not_called()
        finally:
            window.close()

    def test_authenticated_runtime_device_is_visible_and_forgettable(self) -> None:
        window = MainWindow()
        try:
            window.app_controller.list_paired_remote_devices = Mock(return_value=[])
            window.app_controller.get_paired_remote_device = Mock(return_value=None)
            window.app_controller.save_paired_remote_device = Mock()
            window.app_controller.remove_paired_remote_device = Mock()
            window.voice_coordinator.revoke_remote_device_token = Mock(return_value=True)

            window._handle_voice_diagnostic(
                {
                    "event": "client_authenticated",
                    "source_id": "node-1",
                    "auth_mode": "device_token",
                }
            )

            table = window.known_devices_table
            source_row = -1
            for row in range(table.rowCount()):
                source_item = table.item(row, 1)
                if source_item is None:
                    continue
                source_id = str(source_item.data(Qt.UserRole) or "").strip()
                if source_id == "node-1":
                    source_row = row
                    break

            self.assertGreaterEqual(source_row, 0)
            pair_auth_item = table.item(source_row, 2)
            self.assertIsNotNone(pair_auth_item)
            self.assertIn("Authenticated", pair_auth_item.text())

            table.selectRow(source_row)
            with patch("finance_app.ui.main_window.QMessageBox.question", return_value=QMessageBox.Yes):
                window._forget_selected_known_device()

            window.voice_coordinator.revoke_remote_device_token.assert_called_once_with("node-1")
            window.app_controller.remove_paired_remote_device.assert_called_once_with("node-1")
            self.assertNotIn("node-1", window._known_remote_device_runtime)
            self.assertEqual(table.rowCount(), 0)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
