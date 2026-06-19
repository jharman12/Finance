from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from finance_app.services.voice.asr_faster_whisper import FasterWhisperAsrProvider
from finance_app.services.voice.asr_router import AsrRouter
from finance_app.services.voice.asr_vosk import VoskAsrProvider
from finance_app.services.voice.command_event import VoiceCommandEvent
from finance_app.services.voice.postprocess import normalize_command_text
from finance_app.services.voice.remote_stream_source import RemoteStreamSource
from finance_app.services.voice.session_state import VoiceSessionState
from finance_app.services.voice.stream_source import MicStreamSource
from finance_app.services.voice.telemetry import VoiceTelemetryLogger
from finance_app.services.voice.vad_endpointing import VoiceActivityEndpoint
from finance_app.services.voice.wake_detector import OpenWakeWordDetector, VoskPhraseWakeDetector


@dataclass(slots=True)
class VoiceTextEvent:
    text: str
    is_final: bool
    source_id: str


class WakeWordCommandRouter:
    """Turns streaming transcripts into wake + command events.

    This router is input-source agnostic: local USB mic today, remote nodes later.
    """

    def __init__(self, wake_phrase: str = "hey steven", command_timeout_seconds: float = 20.0) -> None:
        self.wake_phrase = self._normalize(wake_phrase)
        self.command_timeout_seconds = command_timeout_seconds
        self._armed = False
        self._armed_at = 0.0

        self.on_status: Callable[[str], None] | None = None
        self.on_wake: Callable[[str], None] | None = None
        self.on_command: Callable[[str], None] | None = None

    def process_text(self, event: VoiceTextEvent) -> None:
        normalized = self._normalize(event.text)
        if not normalized:
            self._check_timeout()
            return

        if not self._armed:
            if self._contains_wake_phrase(normalized):
                self._armed = True
                self._armed_at = time.monotonic()
                if self.on_wake:
                    self.on_wake(event.source_id)
                if self.on_status:
                    self.on_status("Wake word detected. Listening for command...")

                immediate_command = self._remove_wake_phrase(normalized).strip()
                if event.is_final and immediate_command:
                    if self.on_command:
                        self.on_command(immediate_command)
                    self._reset_armed("Command received from wake phrase sentence.")
            return

        # Armed state: wait for a final command utterance.
        if event.is_final:
            command_text = self._remove_wake_phrase(normalized).strip()
            if command_text:
                if self.on_command:
                    self.on_command(command_text)
                self._reset_armed("Command captured.")
                return

        self._check_timeout()

    def _check_timeout(self) -> None:
        if not self._armed:
            return
        elapsed = time.monotonic() - self._armed_at
        if elapsed > self.command_timeout_seconds:
            self._reset_armed("Wake timed out. Say wake phrase again.")

    def _reset_armed(self, status: str) -> None:
        self._armed = False
        self._armed_at = 0.0
        if self.on_status:
            self.on_status(status)

    def _contains_wake_phrase(self, text: str) -> bool:
        if self.wake_phrase in text:
            return True
        # Tolerate common mis-hearings of "Steven".
        return "hey stephen" in text or "hey steven" in text or "hey steven." in text

    def _remove_wake_phrase(self, text: str) -> str:
        candidates = [self.wake_phrase, "hey stephen", "hey steven"]
        result = text
        for candidate in candidates:
            result = result.replace(candidate, " ")
        return " ".join(result.split())

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = text.lower().strip()
        cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in lowered)
        return " ".join(cleaned.split())


class VoiceCoordinator:
    """Coordinates voice input nodes and wake-word routing.

    Future nodes can be added by creating another node class that emits VoiceTextEvent.
    """

    def __init__(self, wake_phrase: str = "hey steven") -> None:
        self.router = WakeWordCommandRouter(wake_phrase=wake_phrase)
        self.sample_rate = 16000
        self.source_id = "local-usb-mic"
        self._active_source_id = self.source_id
        self.model_path = os.getenv("FINANCE_APP_VOSK_MODEL_PATH", "models/vosk-model-en-us-0.22-lgraph")

        self.stream = MicStreamSource(sample_rate=self.sample_rate, blocksize=1600)
        self._local_mic_enabled = os.getenv("FINANCE_APP_LOCAL_MIC_ENABLED", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._remote_audio_enabled = os.getenv("FINANCE_APP_REMOTE_AUDIO_ENABLED", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.remote_stream: RemoteStreamSource | None = self._build_remote_stream_source()
        self.endpoint = VoiceActivityEndpoint(
            min_speech_ms=int(os.getenv("FINANCE_APP_VOICE_MIN_UTTERANCE_MS", "300")),
            end_silence_ms=int(os.getenv("FINANCE_APP_VOICE_ENDPOINT_SILENCE_MS", "700")),
            max_utterance_ms=int(os.getenv("FINANCE_APP_VOICE_MAX_UTTERANCE_MS", "12000")),
            energy_threshold=float(os.getenv("FINANCE_APP_VOICE_ENERGY_THRESHOLD", "450")),
        )
        self.state = VoiceSessionState.IDLE
        self._capture_chunks: list[bytes] = []
        self._preroll_chunks: deque[bytes] = deque(maxlen=8)
        self._state_lock = threading.Lock()
        self._utterance_id = 0
        self._cooldown_seconds = float(os.getenv("FINANCE_APP_VOICE_COOLDOWN_SECONDS", "0.7"))
        self._cooldown_until = 0.0
        self._partial_preview_recognizer = None
        self._last_partial_preview = ""
        self._partial_emit_interval_seconds = float(os.getenv("FINANCE_APP_VOICE_PARTIAL_INTERVAL_SECONDS", "0.2"))
        self._last_partial_emit_at = 0.0
        self._continuation_window_seconds = float(os.getenv("FINANCE_APP_VOICE_CONTINUATION_SECONDS", "0.7"))
        self._awaiting_continuation = False
        self._continuation_deadline = 0.0

        telemetry_path = os.getenv("FINANCE_APP_VOICE_TELEMETRY_PATH", str(Path("logs") / "voice_events.jsonl"))
        self.telemetry = VoiceTelemetryLogger(Path(telemetry_path))

        asr_primary = os.getenv("FINANCE_APP_VOICE_ASR_PRIMARY", "faster_whisper").strip().lower()
        fw_provider = FasterWhisperAsrProvider(
            model_size=os.getenv("FINANCE_APP_FW_MODEL_SIZE", "small.en"),
            device=os.getenv("FINANCE_APP_FW_DEVICE", "cpu"),
            compute_type=os.getenv("FINANCE_APP_FW_COMPUTE_TYPE", "int8"),
            cpu_threads=int(os.getenv("FINANCE_APP_FW_CPU_THREADS", "4")),
        )
        vosk_provider = VoskAsrProvider(self.model_path)

        if asr_primary == "vosk":
            primary_provider = vosk_provider
            fallback_provider = fw_provider
        else:
            primary_provider = fw_provider
            fallback_provider = vosk_provider

        self.asr_router = AsrRouter(primary=primary_provider, fallback=fallback_provider)

        self.wake_mode = os.getenv("FINANCE_APP_WAKE_MODE", "phrase_vosk").strip().lower()
        self._wake_detector = self._build_wake_detector()

        self.on_status: Callable[[str], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self.on_wake: Callable[[str], None] | None = None
        self.on_command: Callable[[str], None] | None = None
        self.on_command_event: Callable[[VoiceCommandEvent], None] | None = None
        self.on_partial: Callable[[str], None] | None = None
        self.on_diagnostic: Callable[[dict[str, Any]], None] | None = None

        self.router.on_status = self._emit_status
        self.router.on_wake = self._emit_wake
        self.router.on_command = self._emit_command

    def start(self) -> None:
        if not self._initialize_wake_detector():
            return

        with self._state_lock:
            self.state = VoiceSessionState.IDLE
            self.endpoint.reset()
            self._capture_chunks.clear()
            self._preroll_chunks.clear()
            self._cooldown_until = 0.0
            self._partial_preview_recognizer = None
            self._last_partial_preview = ""
            self._last_partial_emit_at = 0.0
            self._awaiting_continuation = False
            self._continuation_deadline = 0.0
            self._active_source_id = self.source_id

        if self._local_mic_enabled:
            self.stream.start(
                on_audio_chunk=self._handle_audio_chunk,
                on_status=self._emit_status,
                on_error=self._handle_stream_error,
            )

        if self.remote_stream is not None:
            try:
                self.remote_stream.start(
                    on_audio_chunk=self._handle_remote_audio_chunk,
                    on_status=self._emit_status,
                    on_error=self._handle_stream_error,
                    on_diagnostic=self._emit_diagnostic,
                )
            except Exception as exc:
                self._handle_stream_error(f"Remote audio server failed to start: {exc}")
                return

        self.telemetry.log("voice_started", wake_mode=self.wake_mode)
        if self.remote_stream is not None:
            self.telemetry.log(
                "remote_audio_started",
                bind_port=self.remote_stream.bound_port,
                local_mic_enabled=self._local_mic_enabled,
            )
        self._emit_diagnostic(stage="started", wake_mode=self.wake_mode)

    def stop(self) -> None:
        self.stream.stop()
        if self.remote_stream is not None:
            self.remote_stream.stop()
        if self._wake_detector is not None:
            try:
                self._wake_detector.stop()
            except Exception:
                pass
        with self._state_lock:
            self.state = VoiceSessionState.IDLE
            self._capture_chunks.clear()
            self._preroll_chunks.clear()
            self.endpoint.reset()
            self._cooldown_until = 0.0
            self._partial_preview_recognizer = None
            self._last_partial_preview = ""
            self._last_partial_emit_at = 0.0
            self._awaiting_continuation = False
            self._continuation_deadline = 0.0
            self._active_source_id = self.source_id
        self.telemetry.log("voice_stopped")
        self._emit_diagnostic(stage="stopped")

    def ingest_remote_text(self, text: str, source_id: str = "remote-node", is_final: bool = True) -> None:
        """Future expansion point for remote Alexa-like devices."""
        self.router.process_text(VoiceTextEvent(text=text, is_final=is_final, source_id=source_id))

    def _build_wake_detector(self):
        if self.wake_mode == "openwakeword":
            return OpenWakeWordDetector(
                sample_rate=self.sample_rate,
                threshold=float(os.getenv("FINANCE_APP_WAKE_THRESHOLD", "0.5")),
                model_path=os.getenv("FINANCE_APP_OPENWAKEWORD_MODEL_PATH"),
            )
        return VoskPhraseWakeDetector(
            model_path=self.model_path,
            sample_rate=self.sample_rate,
            wake_phrase=self.router.wake_phrase,
        )

    def _initialize_wake_detector(self) -> bool:
        detector = self._wake_detector
        if detector is None:
            self._emit_error("No wake detector configured.")
            return False

        try:
            detector.start()
            return True
        except Exception as exc:
            self._emit_error(f"Failed to initialize wake detector ({getattr(detector, 'name', 'unknown')}): {exc}")
            # Fallback to phrase wake if optional detector fails.
            if self.wake_mode == "openwakeword":
                self.wake_mode = "phrase_vosk"
                self._wake_detector = self._build_wake_detector()
                return self._initialize_wake_detector()
            return False

    def _handle_audio_chunk(self, chunk: bytes) -> None:
        self._handle_audio_chunk_from_source(self.source_id, chunk)

    def _handle_remote_audio_chunk(self, source_id: str, chunk: bytes) -> None:
        self._handle_audio_chunk_from_source(source_id, chunk)

    def _handle_audio_chunk_from_source(self, source_id: str, chunk: bytes) -> None:
        if not chunk:
            return

        with self._state_lock:
            self._preroll_chunks.append(chunk)
            state = self.state
            in_cooldown = self._in_cooldown_locked()
            self._active_source_id = source_id or self.source_id

        if state in (VoiceSessionState.DECODING, VoiceSessionState.DISPATCHING, VoiceSessionState.ERROR):
            return

        if in_cooldown:
            return

        if state == VoiceSessionState.IDLE:
            self._process_wake_chunk(chunk, source_id=self._active_source_id)
            return

        if state == VoiceSessionState.CAPTURING:
            self._process_capture_chunk(chunk)

    def _process_wake_chunk(self, chunk: bytes, source_id: str) -> None:
        detector = self._wake_detector
        if detector is None:
            return

        try:
            detected = bool(detector.detect(chunk))
        except Exception as exc:
            self._emit_error(f"Wake detection failed: {exc}")
            self.telemetry.log("wake_error", error=str(exc))
            return

        if not detected:
            return

        with self._state_lock:
            self.state = VoiceSessionState.WAKE_DETECTED
            self.state = VoiceSessionState.CAPTURING
            self.endpoint.reset()
            self._capture_chunks = list(self._preroll_chunks)
            self._utterance_id += 1
            utterance_id = self._utterance_id
            self._initialize_partial_preview_recognizer_locked()
            self._last_partial_preview = ""
            self._last_partial_emit_at = 0.0
            self._awaiting_continuation = False
            self._continuation_deadline = 0.0
            self._active_source_id = source_id or self.source_id

        self._emit_wake(self._active_source_id)
        self._emit_status("Wake detected. Listening for command...")
        self._emit_diagnostic(
            stage="wake",
            source_id=self._active_source_id,
            wake_mode=self.wake_mode,
            utterance_id=utterance_id,
        )
        self.telemetry.log(
            "wake_detected",
            source_id=self._active_source_id,
            wake_mode=self.wake_mode,
            utterance_id=utterance_id,
        )

    def _process_capture_chunk(self, chunk: bytes) -> None:
        self._emit_partial_preview(chunk)

        now = time.monotonic()
        is_speech = self.endpoint.is_speech_chunk(chunk)

        with self._state_lock:
            if self.state != VoiceSessionState.CAPTURING:
                return
            self._capture_chunks.append(chunk)
            decision = self.endpoint.process_chunk(chunk, self.sample_rate)
            waiting_for_continuation = self._awaiting_continuation
            continuation_deadline = self._continuation_deadline

        if waiting_for_continuation:
            if is_speech:
                with self._state_lock:
                    self._awaiting_continuation = False
                    self._continuation_deadline = 0.0
                self._emit_status("Speech resumed. Continuing capture...")
                self._emit_diagnostic(stage="continuation_resumed", utterance_id=self._utterance_id)
                self.telemetry.log("continuation_resumed", utterance_id=self._utterance_id)
                return

            if now < continuation_deadline:
                return

            self.telemetry.log(
                "continuation_timeout",
                utterance_id=self._utterance_id,
                waited_seconds=self._continuation_window_seconds,
            )
            decision.utterance_complete = True
            decision.reason = "continuation_timeout"
            with self._state_lock:
                self._awaiting_continuation = False
                self._continuation_deadline = 0.0

        if not decision.utterance_complete:
            return

        if decision.reason == "silence" and self._continuation_window_seconds > 0.0:
            with self._state_lock:
                if self.state == VoiceSessionState.CAPTURING:
                    self._awaiting_continuation = True
                    self._continuation_deadline = now + self._continuation_window_seconds
            self._emit_status("Pause detected. Waiting briefly for continuation...")
            self._emit_diagnostic(
                stage="continuation_wait",
                utterance_id=self._utterance_id,
                seconds=self._continuation_window_seconds,
            )
            self.telemetry.log(
                "continuation_window_started",
                utterance_id=self._utterance_id,
                seconds=self._continuation_window_seconds,
            )
            return

        with self._state_lock:
            if self.state != VoiceSessionState.CAPTURING:
                return
            self.state = VoiceSessionState.DECODING
            utterance_audio = b"".join(self._capture_chunks)
            self._capture_chunks.clear()
            utterance_id = self._utterance_id
            self._partial_preview_recognizer = None
            self._last_partial_preview = ""
            self._awaiting_continuation = False
            self._continuation_deadline = 0.0

        self._emit_status("Transcribing command...")
        self._emit_diagnostic(
            stage="endpoint",
            utterance_id=utterance_id,
            endpoint_reason=decision.reason,
            speech_ms=decision.speech_ms,
        )
        self.telemetry.log(
            "endpoint_complete",
            utterance_id=utterance_id,
            reason=decision.reason,
            speech_ms=decision.speech_ms,
        )
        self._decode_and_dispatch(utterance_audio, utterance_id)

    def _decode_and_dispatch(self, utterance_audio: bytes, utterance_id: int) -> None:
        try:
            result = self.asr_router.transcribe_pcm16(utterance_audio, self.sample_rate)
        except Exception as exc:
            with self._state_lock:
                self.state = VoiceSessionState.ERROR
            self._emit_error(f"Voice transcription failed: {exc}")
            self._emit_diagnostic(stage="decode_error", utterance_id=utterance_id, error=str(exc))
            self.telemetry.log("decode_error", utterance_id=utterance_id, error=str(exc))
            with self._state_lock:
                self.state = VoiceSessionState.IDLE
                self.endpoint.reset()
            return

        with self._state_lock:
            self.state = VoiceSessionState.DISPATCHING

        command_text = normalize_command_text(result.text)
        command_text = self.router._remove_wake_phrase(command_text).strip()
        if command_text:
            command_event = VoiceCommandEvent(
                text=command_text,
                source_id=self._active_source_id,
                session_id=f"voice-{utterance_id}",
                provider=result.provider,
                confidence_0_1=result.confidence_0_1,
                latency_ms=result.latency_ms,
                used_fallback=result.used_fallback,
                fallback_reason=result.fallback_reason,
            )
            provider_status = f"Command captured by {result.provider}"
            if result.used_fallback and result.fallback_reason:
                provider_status += f" (fallback: {result.fallback_reason})"
            self._emit_status(provider_status)
            self._emit_command(command_event)
            self._emit_diagnostic(
                stage="dispatch",
                utterance_id=utterance_id,
                provider=result.provider,
                confidence=result.confidence_0_1,
                latency_ms=result.latency_ms,
                fallback_reason=result.fallback_reason or "none",
                used_fallback=result.used_fallback,
            )
            self.telemetry.log(
                "command_dispatch",
                utterance_id=utterance_id,
                source_id=self._active_source_id,
                provider=result.provider,
                confidence=result.confidence_0_1,
                latency_ms=result.latency_ms,
                used_fallback=result.used_fallback,
                fallback_reason=result.fallback_reason,
                chars=len(command_text),
            )
        else:
            self._emit_status("I heard audio, but couldn't transcribe a command. Please try again.")
            self._emit_diagnostic(
                stage="empty",
                utterance_id=utterance_id,
                provider=result.provider,
                confidence=result.confidence_0_1,
                latency_ms=result.latency_ms,
            )
            self.telemetry.log(
                "command_empty",
                utterance_id=utterance_id,
                source_id=self._active_source_id,
                provider=result.provider,
                confidence=result.confidence_0_1,
                latency_ms=result.latency_ms,
            )

        with self._state_lock:
            self.state = VoiceSessionState.COOLDOWN
            self._cooldown_until = time.monotonic() + max(0.0, self._cooldown_seconds)
            self.endpoint.reset()

        self.telemetry.log("cooldown_started", utterance_id=utterance_id, seconds=self._cooldown_seconds)
        self._emit_diagnostic(stage="cooldown", utterance_id=utterance_id, seconds=self._cooldown_seconds)
        self._emit_partial("")

        with self._state_lock:
            self.state = VoiceSessionState.IDLE

    def _handle_stream_error(self, message: str) -> None:
        with self._state_lock:
            self.state = VoiceSessionState.ERROR
        self._emit_error(message)
        self._emit_diagnostic(stage="stream_error", error=message)
        self.telemetry.log("stream_error", error=message)
        with self._state_lock:
            self.state = VoiceSessionState.IDLE
            self.endpoint.reset()
            self._partial_preview_recognizer = None
            self._last_partial_preview = ""
            self._awaiting_continuation = False
            self._continuation_deadline = 0.0

    def _initialize_partial_preview_recognizer_locked(self) -> None:
        if self.wake_mode == "openwakeword":
            # openwakeword path might not have Vosk imported yet; preview is optional.
            pass
        try:
            from vosk import KaldiRecognizer, Model

            if self.model_path:
                if not hasattr(self, "_preview_model") or self._preview_model is None:
                    self._preview_model = Model(self.model_path)
                self._partial_preview_recognizer = KaldiRecognizer(self._preview_model, self.sample_rate)
        except Exception:
            self._partial_preview_recognizer = None

    def _emit_partial_preview(self, chunk: bytes) -> None:
        with self._state_lock:
            recognizer = self._partial_preview_recognizer
            if recognizer is None:
                return

        try:
            if recognizer.AcceptWaveform(chunk):
                payload = json.loads(recognizer.Result())
                preview = str(payload.get("text", "")).strip()
            else:
                payload = json.loads(recognizer.PartialResult())
                preview = str(payload.get("partial", "")).strip()
        except Exception:
            return

        if not preview:
            return

        normalized_preview = self.router._remove_wake_phrase(self.router._normalize(preview)).strip()
        if not normalized_preview:
            return

        with self._state_lock:
            if normalized_preview == self._last_partial_preview:
                return
            now = time.monotonic()
            if (now - self._last_partial_emit_at) < max(0.0, self._partial_emit_interval_seconds):
                return
            self._last_partial_preview = normalized_preview
            self._last_partial_emit_at = now

        self._emit_partial(normalized_preview)

    def _emit_partial(self, partial_text: str) -> None:
        if self.on_partial:
            self.on_partial(partial_text)

    def _emit_diagnostic(self, **payload: Any) -> None:
        if self.on_diagnostic:
            self.on_diagnostic(payload)

    def _build_remote_stream_source(self) -> RemoteStreamSource | None:
        if not self._remote_audio_enabled:
            return None

        auth_token = os.getenv("FINANCE_APP_REMOTE_AUDIO_TOKEN", "").strip()
        if len(auth_token) < 16:
            telemetry = getattr(self, "telemetry", None)
            if telemetry is not None:
                telemetry.log(
                    "remote_audio_disabled",
                    reason="missing_or_short_token",
                    min_token_chars=16,
                )
            return None

        host = os.getenv("FINANCE_APP_REMOTE_AUDIO_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = int(os.getenv("FINANCE_APP_REMOTE_AUDIO_PORT", "45881"))
        max_chunk_bytes = int(os.getenv("FINANCE_APP_REMOTE_AUDIO_MAX_CHUNK_BYTES", "32768"))
        max_mps = int(os.getenv("FINANCE_APP_REMOTE_AUDIO_MAX_MESSAGES_PER_SECOND", "120"))
        tls_cert_path = os.getenv("FINANCE_APP_REMOTE_AUDIO_TLS_CERT", "").strip() or None
        tls_key_path = os.getenv("FINANCE_APP_REMOTE_AUDIO_TLS_KEY", "").strip() or None

        return RemoteStreamSource(
            host=host,
            port=port,
            auth_token=auth_token,
            max_chunk_bytes=max_chunk_bytes,
            max_messages_per_second=max_mps,
            tls_cert_path=tls_cert_path,
            tls_key_path=tls_key_path,
        )

    def _in_cooldown_locked(self) -> bool:
        if self._cooldown_until <= 0.0:
            return False
        now = time.monotonic()
        if now < self._cooldown_until:
            return True
        self._cooldown_until = 0.0
        return False

    def _in_cooldown(self, now: float | None = None) -> bool:
        with self._state_lock:
            if self._cooldown_until <= 0.0:
                return False
            current = time.monotonic() if now is None else now
            if current < self._cooldown_until:
                return True
            self._cooldown_until = 0.0
            return False

    def _emit_status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def _emit_error(self, message: str) -> None:
        if self.on_error:
            self.on_error(message)

    def _emit_wake(self, source_id: str) -> None:
        if self.on_wake:
            self.on_wake(source_id)

    def _emit_command(self, command_event: VoiceCommandEvent) -> None:
        if self.on_command_event:
            self.on_command_event(command_event)
        if self.on_command:
            self.on_command(command_event.text)
