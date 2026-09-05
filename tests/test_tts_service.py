from __future__ import annotations

import threading
import time
import unittest

from finance_app.services.voice.tts_provider import (
    LOCAL_SOURCE_ID,
    NullAudioSink,
    NullTtsProvider,
    SynthesizedSpeech,
)
from finance_app.services.voice.tts_service import TextToSpeechService


class _FakeProvider:
    name = "fake"

    def __init__(self, pcm: bytes = b"\x00\x00" * 800, synth_delay: float = 0.0) -> None:
        self.pcm = pcm
        self.synth_delay = synth_delay
        self.calls: list[str] = []

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, cancel: threading.Event) -> SynthesizedSpeech:
        self.calls.append(text)
        if self.synth_delay:
            time.sleep(self.synth_delay)
        return SynthesizedSpeech(pcm16=self.pcm, sample_rate=16000, voice=self.name)


class _BlockingSink:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.finished = threading.Event()
        self.stop_calls = 0

    def play(self, speech: SynthesizedSpeech, cancel: threading.Event) -> None:
        self.started.set()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if cancel.is_set():
                break
            time.sleep(0.005)
        self.finished.set()

    def stop(self) -> None:
        self.stop_calls += 1


class _RecordingTelemetry:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def log(self, event: str, **fields: object) -> None:
        self.events.append((event, dict(fields)))

    def event_names(self) -> list[str]:
        return [name for name, _ in self.events]


class SynthesizedSpeechTests(unittest.TestCase):
    def test_audio_ms_from_pcm_length(self) -> None:
        speech = SynthesizedSpeech(pcm16=b"\x00\x00" * 16000, sample_rate=16000)

        self.assertEqual(speech.audio_ms, 1000)

    def test_zero_sample_rate_is_safe(self) -> None:
        self.assertEqual(SynthesizedSpeech(pcm16=b"\x00\x00", sample_rate=0).audio_ms, 0)


class TextToSpeechServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = _FakeProvider()
        self.sink = NullAudioSink()
        self.telemetry = _RecordingTelemetry()
        self.service = TextToSpeechService(
            provider=self.provider,
            sink_factory=lambda source_id: self.sink,
            telemetry=self.telemetry,
        )

    def tearDown(self) -> None:
        self.service.shutdown()

    def _wait_for_idle(self, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.service.is_speaking() and self.service._queue.empty():
                return
            time.sleep(0.01)

    def test_speak_returns_immediately(self) -> None:
        self.provider.synth_delay = 0.3

        started = time.perf_counter()
        speech_id = self.service.speak("hello there")
        elapsed = time.perf_counter() - started

        self.assertTrue(speech_id)
        self.assertLess(elapsed, 0.05)

    def test_empty_text_is_ignored(self) -> None:
        self.assertEqual(self.service.speak("   "), "")
        self.assertEqual(self.provider.calls, [])

    def test_playback_reaches_sink(self) -> None:
        self.service.speak("say this")
        self._wait_for_idle()

        self.assertEqual(len(self.sink.played), 1)
        self.assertEqual(self.provider.calls, ["say this"])

    def test_callbacks_fire_in_order(self) -> None:
        events: list[str] = []
        self.service.on_speech_started = lambda sid, src: events.append("started")
        self.service.on_speech_finished = lambda sid, src, cancelled: events.append("finished")

        self.service.speak("hello")
        self._wait_for_idle()

        self.assertEqual(events, ["started", "finished"])

    def test_telemetry_records_lifecycle(self) -> None:
        self.service.speak("hello")
        self._wait_for_idle()

        names = self.telemetry.event_names()
        self.assertIn("tts_request", names)
        self.assertIn("tts_synth_complete", names)
        self.assertIn("tts_playback_started", names)
        self.assertIn("tts_playback_finished", names)

    def test_latency_target_recorded_for_local_source(self) -> None:
        self.service.speak("hi", source_id=LOCAL_SOURCE_ID, utterance_end_monotonic=time.monotonic())
        self._wait_for_idle()

        started = [fields for name, fields in self.telemetry.events if name == "tts_playback_started"]
        self.assertEqual(started[0]["target_ms"], 2000)
        self.assertTrue(started[0]["within_target"])

    def test_remote_source_uses_remote_target(self) -> None:
        self.service.speak("hi", source_id="node-1", utterance_end_monotonic=time.monotonic())
        self._wait_for_idle()

        started = [fields for name, fields in self.telemetry.events if name == "tts_playback_started"]
        self.assertEqual(started[0]["target_ms"], 2500)

    def test_missing_utterance_timestamp_yields_no_ttfa(self) -> None:
        self.service.speak("hi")
        self._wait_for_idle()

        started = [fields for name, fields in self.telemetry.events if name == "tts_playback_started"]
        self.assertIsNone(started[0]["ttfa_ms"])
        self.assertFalse(started[0]["within_target"])


class TextToSpeechCancelTests(unittest.TestCase):
    def test_cancel_stops_playback_and_reports_cancelled(self) -> None:
        sink = _BlockingSink()
        service = TextToSpeechService(provider=_FakeProvider(), sink_factory=lambda source_id: sink)
        cancelled_flags: list[bool] = []
        service.on_speech_finished = lambda sid, src, cancelled: cancelled_flags.append(cancelled)

        try:
            service.speak("a long reply")
            self.assertTrue(sink.started.wait(timeout=2.0))

            service.cancel()

            self.assertTrue(sink.finished.wait(timeout=2.0))
            deadline = time.monotonic() + 2.0
            while not cancelled_flags and time.monotonic() < deadline:
                time.sleep(0.01)

            self.assertEqual(cancelled_flags, [True])
            self.assertGreaterEqual(sink.stop_calls, 1)
        finally:
            service.shutdown()

    def test_cancel_with_mismatched_id_is_ignored(self) -> None:
        sink = _BlockingSink()
        service = TextToSpeechService(provider=_FakeProvider(), sink_factory=lambda source_id: sink)

        try:
            service.speak("keep going")
            self.assertTrue(sink.started.wait(timeout=2.0))

            service.cancel("some-other-id")

            self.assertEqual(sink.stop_calls, 0)
        finally:
            service.cancel()
            service.shutdown()

    def test_shutdown_is_idempotent_and_joins(self) -> None:
        service = TextToSpeechService(provider=NullTtsProvider(), sink_factory=lambda source_id: NullAudioSink())

        service.shutdown()
        service.shutdown()

        self.assertFalse(service._worker.is_alive())

    def test_speak_after_shutdown_is_rejected(self) -> None:
        service = TextToSpeechService(provider=_FakeProvider(), sink_factory=lambda source_id: NullAudioSink())
        service.shutdown()

        self.assertEqual(service.speak("too late"), "")


class NullProviderTests(unittest.TestCase):
    def test_null_provider_produces_no_audio(self) -> None:
        speech = NullTtsProvider().synthesize("anything", threading.Event())

        self.assertEqual(speech.pcm16, b"")
        self.assertEqual(speech.audio_ms, 0)


if __name__ == "__main__":
    unittest.main()
