from __future__ import annotations

import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from finance_app.services.voice.telemetry import VoiceTelemetryLogger
from finance_app.services.voice.tts_provider import (
    LOCAL_SOURCE_ID,
    AudioSink,
    NullAudioSink,
    SynthesizedSpeech,
    TtsProvider,
)

LOCAL_TARGET_MS = 2000
REMOTE_TARGET_MS = 2500


@dataclass(slots=True)
class SpeechRequest:
    speech_id: str
    text: str
    source_id: str
    session_id: str
    utterance_end_monotonic: float | None
    cancel: threading.Event = field(default_factory=threading.Event)


class TextToSpeechService:
    """Serializes synthesis and playback on one worker thread; speak() never blocks."""

    def __init__(
        self,
        provider: TtsProvider,
        sink_factory: Callable[[str], AudioSink] | None = None,
        telemetry: VoiceTelemetryLogger | None = None,
    ) -> None:
        self.provider = provider
        self.sink_factory = sink_factory or (lambda source_id: NullAudioSink())
        self.telemetry = telemetry

        self._queue: queue.Queue[SpeechRequest | None] = queue.Queue()
        self._lock = threading.Lock()
        self._current: SpeechRequest | None = None
        self._current_sink: AudioSink | None = None
        self._stopping = False
        self._worker = threading.Thread(target=self._run, name="tts-worker", daemon=True)
        self._worker.start()

        self.on_speech_started: Callable[[str, str], None] | None = None
        self.on_speech_finished: Callable[[str, str, bool], None] | None = None
        self.on_error: Callable[[str], None] | None = None

    def speak(
        self,
        text: str,
        source_id: str = LOCAL_SOURCE_ID,
        session_id: str = "",
        utterance_end_monotonic: float | None = None,
    ) -> str:
        cleaned = str(text or "").strip()
        if not cleaned or self._stopping:
            return ""

        request = SpeechRequest(
            speech_id=uuid.uuid4().hex[:12],
            text=cleaned,
            source_id=str(source_id or LOCAL_SOURCE_ID).strip() or LOCAL_SOURCE_ID,
            session_id=str(session_id or ""),
            utterance_end_monotonic=utterance_end_monotonic,
        )

        # A superseded reply should never keep talking.
        self.cancel()
        self._drain_pending()
        self._queue.put(request)
        self._log(
            "tts_request",
            speech_id=request.speech_id,
            source_id=request.source_id,
            session_id=request.session_id,
            chars=len(cleaned),
            provider=getattr(self.provider, "name", "unknown"),
        )
        return request.speech_id

    def cancel(self, speech_id: str | None = None) -> None:
        with self._lock:
            current = self._current
            sink = self._current_sink
        if current is None:
            return
        if speech_id is not None and current.speech_id != speech_id:
            return
        current.cancel.set()
        if sink is not None:
            try:
                sink.stop()
            except Exception:
                pass

    def is_speaking(self) -> bool:
        with self._lock:
            return self._current is not None

    def shutdown(self, timeout: float = 2.0) -> None:
        self._stopping = True
        self.cancel()
        self._drain_pending()
        self._queue.put(None)
        self._worker.join(timeout=timeout)

    def _drain_pending(self) -> None:
        while True:
            try:
                pending = self._queue.get_nowait()
            except queue.Empty:
                return
            if pending is None:
                self._queue.put(None)
                return

    def _run(self) -> None:
        while True:
            request = self._queue.get()
            if request is None:
                return
            try:
                self._process(request)
            except Exception as exc:
                self._emit_error(f"Speech failed: {exc}")
            finally:
                with self._lock:
                    self._current = None
                    self._current_sink = None

    def _process(self, request: SpeechRequest) -> None:
        if request.cancel.is_set():
            return

        sink = self.sink_factory(request.source_id)
        with self._lock:
            self._current = request
            self._current_sink = sink

        speech: SynthesizedSpeech = self.provider.synthesize(request.text, request.cancel)
        self._log(
            "tts_synth_complete",
            speech_id=request.speech_id,
            synth_ms=speech.synth_ms,
            audio_ms=speech.audio_ms,
        )

        if request.cancel.is_set():
            self._finish(request, cancelled=True, playback_ms=0)
            return

        if self.on_speech_started:
            self.on_speech_started(request.speech_id, request.source_id)

        ttfa_ms = self._time_to_first_audio_ms(request)
        target_ms = LOCAL_TARGET_MS if request.source_id == LOCAL_SOURCE_ID else REMOTE_TARGET_MS
        self._log(
            "tts_playback_started",
            speech_id=request.speech_id,
            source_id=request.source_id,
            ttfa_ms=ttfa_ms,
            target_ms=target_ms,
            within_target=(ttfa_ms is not None and ttfa_ms <= target_ms),
        )

        started = time.perf_counter()
        try:
            sink.play(speech, request.cancel)
        except Exception as exc:
            self._emit_error(f"Speech playback failed: {exc}")

        playback_ms = int((time.perf_counter() - started) * 1000)
        self._finish(request, cancelled=request.cancel.is_set(), playback_ms=playback_ms)

    def _time_to_first_audio_ms(self, request: SpeechRequest) -> int | None:
        if request.utterance_end_monotonic is None:
            return None
        return int((time.monotonic() - request.utterance_end_monotonic) * 1000)

    def _finish(self, request: SpeechRequest, cancelled: bool, playback_ms: int) -> None:
        self._log(
            "tts_playback_finished",
            speech_id=request.speech_id,
            cancelled=cancelled,
            playback_ms=playback_ms,
        )
        if self.on_speech_finished:
            self.on_speech_finished(request.speech_id, request.source_id, cancelled)

    def _emit_error(self, message: str) -> None:
        if self.on_error:
            self.on_error(message)

    def _log(self, event: str, **fields: object) -> None:
        if self.telemetry is None:
            return
        try:
            self.telemetry.log(event, **fields)
        except Exception:
            return


def tts_enabled() -> bool:
    return os.getenv("FINANCE_APP_TTS_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}


def speak_typed_enabled() -> bool:
    return os.getenv("FINANCE_APP_TTS_SPEAK_TYPED", "0").strip().lower() in {"1", "true", "yes", "on"}
