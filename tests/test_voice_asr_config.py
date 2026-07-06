from __future__ import annotations

import unittest
from unittest.mock import patch

from finance_app.services.voice_pipeline import VoiceCoordinator


class VoiceAsrConfigTests(unittest.TestCase):
    @patch("finance_app.services.voice_pipeline.AsrRouter")
    @patch("finance_app.services.voice_pipeline.FasterWhisperAsrProvider")
    @patch("finance_app.services.voice_pipeline.VoskAsrProvider")
    @patch("finance_app.services.voice_pipeline.VoskPhraseWakeDetector")
    @patch("finance_app.services.voice_pipeline.MicStreamSource")
    @patch("finance_app.services.voice_pipeline.VoiceActivityEndpoint")
    @patch("finance_app.services.voice_pipeline.VoiceTelemetryLogger")
    @patch("finance_app.services.voice_pipeline.RemoteStreamSource", return_value=None)
    def test_fallback_disabled_by_default(
        self,
        _mock_remote,
        _mock_telemetry,
        _mock_endpoint,
        _mock_mic,
        _mock_wake,
        mock_vosk,
        mock_fw,
        mock_router,
    ) -> None:
        with patch.dict("os.environ", {}, clear=False), patch("finance_app.services.voice_pipeline.os.name", "nt"):
            VoiceCoordinator(wake_phrase="hey steven")

        self.assertTrue(mock_router.called)
        kwargs = mock_router.call_args.kwargs
        self.assertIsNotNone(kwargs.get("primary"))
        self.assertIsNone(kwargs.get("fallback"))

    @patch("finance_app.services.voice_pipeline.AsrRouter")
    @patch("finance_app.services.voice_pipeline.FasterWhisperAsrProvider")
    @patch("finance_app.services.voice_pipeline.VoskAsrProvider")
    @patch("finance_app.services.voice_pipeline.VoskPhraseWakeDetector")
    @patch("finance_app.services.voice_pipeline.MicStreamSource")
    @patch("finance_app.services.voice_pipeline.VoiceActivityEndpoint")
    @patch("finance_app.services.voice_pipeline.VoiceTelemetryLogger")
    @patch("finance_app.services.voice_pipeline.RemoteStreamSource", return_value=None)
    def test_fallback_enabled_by_env(
        self,
        _mock_remote,
        _mock_telemetry,
        _mock_endpoint,
        _mock_mic,
        _mock_wake,
        _mock_vosk,
        _mock_fw,
        mock_router,
    ) -> None:
        with patch.dict(
            "os.environ",
            {
                "FINANCE_APP_VOICE_ASR_PRIMARY": "vosk",
                "FINANCE_APP_VOICE_ASR_ENABLE_FALLBACK": "1",
            },
            clear=False,
        ):
            VoiceCoordinator(wake_phrase="hey steven")

        self.assertTrue(mock_router.called)
        kwargs = mock_router.call_args.kwargs
        self.assertIsNotNone(kwargs.get("primary"))
        self.assertIsNotNone(kwargs.get("fallback"))


if __name__ == "__main__":
    unittest.main()
