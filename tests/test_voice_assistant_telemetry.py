from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from finance_app.models import AssistantResult
from finance_app.ui.main_window import MainWindow


class VoiceAssistantTelemetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_voice_assistant_result_logs_telemetry(self) -> None:
        window = MainWindow()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                target = Path(temp_dir) / "voice.jsonl"
                window.voice_coordinator.telemetry.file_path = target
                window._active_assistant_request_context = {
                    "request_source": "voice",
                    "assistant_session_key": "voice::node-1",
                    "source_id": "node-1",
                    "command_session_id": "voice-command-1",
                    "provider": "fake",
                    "confidence": 0.91,
                }

                window._handle_assistant_result(
                    AssistantResult(
                        reply="done",
                        actions=[{"type": "summarize", "payload": {}}],
                        applied_actions=["Income 1.00, expense 2.00, net -1.00"],
                    )
                )

                lines = target.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)
                payload = json.loads(lines[0])
                self.assertEqual(payload["event"], "assistant_voice_result")
                self.assertEqual(payload["source_id"], "node-1")
                self.assertEqual(payload["command_session_id"], "voice-command-1")
                self.assertEqual(payload["applied_actions"], 1)
                self.assertEqual(payload["action_count"], 1)
        finally:
            window.close()

    def test_voice_assistant_failure_logs_telemetry(self) -> None:
        window = MainWindow()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                target = Path(temp_dir) / "voice.jsonl"
                window.voice_coordinator.telemetry.file_path = target
                window._active_assistant_request_context = {
                    "request_source": "voice",
                    "assistant_session_key": "voice::node-2",
                    "source_id": "node-2",
                    "command_session_id": "voice-command-2",
                    "provider": "fake",
                    "confidence": 0.83,
                }

                window._handle_assistant_failure("timeout")

                lines = target.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(lines), 1)
                payload = json.loads(lines[0])
                self.assertEqual(payload["event"], "assistant_voice_failure")
                self.assertEqual(payload["source_id"], "node-2")
                self.assertEqual(payload["error"], "timeout")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
