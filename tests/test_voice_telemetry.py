from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finance_app.services.voice.telemetry import VoiceTelemetryLogger


class VoiceTelemetryTests(unittest.TestCase):
    def test_log_writes_jsonl_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "voice.jsonl"
            logger = VoiceTelemetryLogger(target)

            logger.log("wake_detected", source_id="mic")

            lines = target.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["event"], "wake_detected")
            self.assertEqual(payload["source_id"], "mic")
            self.assertIn("ts", payload)


if __name__ == "__main__":
    unittest.main()
