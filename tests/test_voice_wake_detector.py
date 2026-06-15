from __future__ import annotations

import tempfile
import unittest

from finance_app.services.voice.wake_detector import OpenWakeWordDetector, VoskPhraseWakeDetector


class WakeDetectorSanityTests(unittest.TestCase):
    def test_phrase_normalization_helper(self) -> None:
        normalized = VoskPhraseWakeDetector._normalize(" Hey, STEVEN!!! ")
        self.assertEqual(normalized, "hey steven")

    def test_openwakeword_detector_defaults(self) -> None:
        detector = OpenWakeWordDetector(sample_rate=16000)
        self.assertEqual(detector.sample_rate, 16000)
        self.assertGreater(detector.threshold, 0.0)

    def test_phrase_matching_accepts_common_mishearing_variant(self) -> None:
        detector = VoskPhraseWakeDetector(model_path="models/vosk-model-en-us-0.22-lgraph", sample_rate=16000)

        self.assertTrue(detector._matches_wake_phrase("hay steven open the voice test"))  # noqa: SLF001
        self.assertTrue(detector._matches_wake_phrase("hey stephen start listening"))  # noqa: SLF001

    def test_openwakeword_requires_explicit_custom_model_path(self) -> None:
        detector = OpenWakeWordDetector(sample_rate=16000)

        with self.assertRaisesRegex(RuntimeError, "FINANCE_APP_OPENWAKEWORD_MODEL_PATH"):
            detector.start()

    def test_openwakeword_requires_existing_model_file(self) -> None:
        detector = OpenWakeWordDetector(sample_rate=16000, model_path="C:/missing/hey_steven.onnx")

        with self.assertRaisesRegex(RuntimeError, "OpenWakeWord model not found"):
            detector.start()


if __name__ == "__main__":
    unittest.main()
