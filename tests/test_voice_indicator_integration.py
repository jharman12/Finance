from __future__ import annotations

import unittest
from unittest.mock import Mock

from PyQt5.QtWidgets import QApplication

from finance_app.services.voice.command_event import VoiceCommandEvent
from finance_app.ui.main_window import MainWindow


class VoiceIndicatorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_indicator_is_in_status_bar(self) -> None:
        window = MainWindow()
        try:
            self.assertIsNotNone(window.voice_indicator)
            self.assertEqual(window.voice_indicator.state(), "ready")
        finally:
            window.close()

    def test_wake_sets_listening(self) -> None:
        window = MainWindow()
        try:
            window._handle_voice_wake("node-1")

            self.assertEqual(window.voice_indicator.state(), "listening")
        finally:
            window.close()

    def test_status_message_maps_to_processing(self) -> None:
        window = MainWindow()
        try:
            window._handle_voice_status("Transcribing command...")

            self.assertEqual(window.voice_indicator.state(), "processing")
        finally:
            window.close()

    def test_pause_message_stays_listening(self) -> None:
        window = MainWindow()
        try:
            window._handle_voice_wake("node-1")
            window._handle_voice_status("Pause detected. Waiting briefly for continuation...")

            self.assertEqual(window.voice_indicator.state(), "listening")
        finally:
            window.close()

    def test_error_returns_to_ready_with_detail(self) -> None:
        window = MainWindow()
        try:
            window._handle_voice_wake("node-1")
            window._handle_voice_error("microphone unavailable")

            self.assertEqual(window.voice_indicator.state(), "ready")
            self.assertIn("microphone unavailable", window.voice_indicator.detail())
        finally:
            window.close()

    def test_testing_mode_command_marks_done(self) -> None:
        window = MainWindow()
        try:
            window._voice_active_surface = "testing"

            window._handle_voice_command(
                VoiceCommandEvent(
                    text="check balance",
                    source_id="node-1",
                    session_id="voice-indicator-1",
                    provider="fake",
                    confidence_0_1=0.95,
                )
            )

            self.assertEqual(window.voice_indicator.state(), "done")
        finally:
            window.close()

    def test_assistant_command_marks_processing(self) -> None:
        window = MainWindow()
        try:
            window.send_prompt = Mock()
            window._voice_active_surface = "assistant"

            window._handle_voice_command(
                VoiceCommandEvent(
                    text="what is my budget",
                    source_id="local-usb-mic",
                    session_id="voice-indicator-2",
                    provider="fake",
                    confidence_0_1=0.95,
                )
            )

            self.assertEqual(window.voice_indicator.state(), "processing")
        finally:
            window.close()

    def test_watchdog_resets_stuck_state(self) -> None:
        window = MainWindow()
        try:
            window._handle_voice_wake("node-1")
            self.assertEqual(window.voice_indicator.state(), "listening")

            window._handle_voice_indicator_timeout()

            self.assertEqual(window.voice_indicator.state(), "ready")
        finally:
            window.close()

    def test_watchdog_does_not_stop_the_pipeline(self) -> None:
        window = MainWindow()
        try:
            window.voice_coordinator.stop = Mock()
            window._handle_voice_wake("node-1")

            window._handle_voice_indicator_timeout()

            window.voice_coordinator.stop.assert_not_called()
        finally:
            window.close()


class DeviceStatusSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_no_devices_reports_none(self) -> None:
        window = MainWindow()
        try:
            window._known_remote_device_runtime = {}

            summary = window._remote_device_status_summary()

            self.assertEqual(summary["state"], "none")
            self.assertEqual(summary["known"], 0)
        finally:
            window.close()

    def test_connected_device_counted(self) -> None:
        window = MainWindow()
        try:
            window._known_remote_device_runtime = {
                "node-1": {"authenticated": True, "connected": True},
            }

            summary = window._remote_device_status_summary()

            self.assertEqual(summary["state"], "connected")
            self.assertEqual(summary["connected"], 1)
        finally:
            window.close()

    def test_authenticated_but_disconnected_reads_as_reconnecting(self) -> None:
        window = MainWindow()
        try:
            window._known_remote_device_runtime = {
                "node-1": {"authenticated": True, "connected": False},
            }

            summary = window._remote_device_status_summary()

            self.assertEqual(summary["state"], "reconnecting")
        finally:
            window.close()

    def test_badge_reflects_summary(self) -> None:
        window = MainWindow()
        try:
            window._known_remote_device_runtime = {
                "node-1": {"authenticated": True, "connected": True},
                "node-2": {"authenticated": True, "connected": False},
            }

            window._refresh_device_status_indicator()

            self.assertEqual(window.connection_status.state(), "connected")
            self.assertIn("1/2", window.connection_status.text_label.text())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
