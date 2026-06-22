from __future__ import annotations

import json
import unittest
from pathlib import Path

from finance_app.services.voice.asr_provider import AsrResult
from finance_app.services.voice.vad_endpointing import EndpointDecision
from finance_app.services.voice_pipeline import VoiceCoordinator


class _FakeWakeDetector:
    name = "fake"

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def detect(self, chunk: bytes) -> bool:
        return chunk == b"WAKE"


class _FakeAsrRouter:
    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int) -> AsrResult:  # noqa: ARG002
        return AsrResult(
            text=self.text,
            provider="fake",
            confidence_0_1=0.95,
            latency_ms=42,
            is_final=True,
        )


class _FakeEndpoint:
    def process_chunk(self, chunk: bytes, sample_rate: int) -> EndpointDecision:  # noqa: ARG002
        if chunk == b"SILENCE":
            return EndpointDecision(speech_started=True, utterance_complete=True, reason="silence", speech_ms=600)
        return EndpointDecision(speech_started=True, utterance_complete=False, reason="listening", speech_ms=600)

    def is_speech_chunk(self, chunk: bytes) -> bool:
        return chunk == b"SPEECH"

    def reset(self) -> None:
        return


class VoicePipelineIntegrationTests(unittest.TestCase):
    def _build_coordinator(self) -> VoiceCoordinator:
        coordinator = VoiceCoordinator(wake_phrase="hey steven")
        coordinator._wake_detector = _FakeWakeDetector()  # noqa: SLF001
        coordinator._initialize_partial_preview_recognizer_locked = lambda: None  # noqa: SLF001
        coordinator._partial_preview_recognizer = None  # noqa: SLF001
        coordinator.endpoint = _FakeEndpoint()
        coordinator.asr_router = _FakeAsrRouter("add grocery expense")
        coordinator._continuation_window_seconds = 0.5  # noqa: SLF001
        coordinator._cooldown_seconds = 0.0  # noqa: SLF001
        return coordinator

    def _run_fixture(self, fixture_name: str) -> list[str]:
        root = Path(__file__).parent / "fixtures" / "voice"
        payload = json.loads((root / fixture_name).read_text(encoding="utf-8"))

        chunk_map = {
            "noise": b"NOISE",
            "wake": b"WAKE",
            "speech": b"SPEECH",
            "silence": b"SILENCE",
        }

        commands: list[str] = []
        diagnostics: list[dict[str, object]] = []
        coordinator = self._build_coordinator()
        coordinator.on_command = commands.append
        coordinator.on_diagnostic = diagnostics.append

        for token in payload["chunks"]:
            coordinator._handle_audio_chunk(chunk_map[token])  # noqa: SLF001
            if token == "silence" and coordinator._awaiting_continuation:  # noqa: SLF001
                # Force timeout on next silence token to close continuation window deterministically.
                coordinator._continuation_deadline = 0.0  # noqa: SLF001

        return commands, diagnostics

    def test_noisy_pause_resume_fixture_dispatches_command(self) -> None:
        commands, diagnostics = self._run_fixture("noisy_pause_resume.json")
        self.assertEqual(commands, ["add groceries expense"])
        dispatch_events = [event for event in diagnostics if event.get("stage") == "dispatch"]
        self.assertEqual(len(dispatch_events), 1)
        self.assertEqual(dispatch_events[0].get("provider"), "fake")

    def test_noisy_trailing_pause_fixture_dispatches_command(self) -> None:
        commands, _ = self._run_fixture("noisy_trailing_pause.json")
        self.assertEqual(commands, ["add groceries expense"])

    def test_dispatch_emits_structured_command_event(self) -> None:
        coordinator = self._build_coordinator()
        events: list[object] = []
        coordinator.on_command_event = events.append

        coordinator._handle_audio_chunk(b"WAKE")  # noqa: SLF001
        coordinator._handle_audio_chunk(b"SPEECH")  # noqa: SLF001
        coordinator._handle_audio_chunk(b"SILENCE")  # noqa: SLF001
        if coordinator._awaiting_continuation:  # noqa: SLF001
            coordinator._continuation_deadline = 0.0  # noqa: SLF001
            coordinator._handle_audio_chunk(b"SILENCE")  # noqa: SLF001

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(getattr(event, "text", None), "add groceries expense")
        self.assertEqual(getattr(event, "provider", None), "fake")
        self.assertEqual(getattr(event, "source_id", None), "local-usb-mic")
        self.assertTrue(str(getattr(event, "session_id", "")).startswith("voice-"))

    def test_remote_audio_dispatches_without_second_wake(self) -> None:
        coordinator = self._build_coordinator()
        events: list[object] = []
        diagnostics: list[dict[str, object]] = []
        coordinator.on_command_event = events.append
        coordinator.on_diagnostic = diagnostics.append

        coordinator._handle_remote_audio_chunk("remote-node", b"SPEECH")  # noqa: SLF001
        coordinator._handle_remote_audio_chunk("remote-node", b"SILENCE")  # noqa: SLF001
        if coordinator._awaiting_continuation:  # noqa: SLF001
            coordinator._continuation_deadline = 0.0  # noqa: SLF001
            coordinator._handle_remote_audio_chunk("remote-node", b"SILENCE")  # noqa: SLF001

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(getattr(event, "text", None), "add groceries expense")
        self.assertEqual(getattr(event, "source_id", None), "remote-node")
        remote_start = [entry for entry in diagnostics if entry.get("stage") == "remote_capture_start"]
        self.assertEqual(len(remote_start), 1)
        self.assertEqual(remote_start[0].get("source_id"), "remote-node")


if __name__ == "__main__":
    unittest.main()
