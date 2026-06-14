from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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


class LocalUsbMicNode:
    """Captures speech from default input device and emits transcripts.

    Uses Vosk + sounddevice for local/offline STT.
    """

    def __init__(
        self,
        source_id: str = "local-usb-mic",
        sample_rate: int = 16000,
        model_path: str | None = None,
    ) -> None:
        self.source_id = source_id
        self.sample_rate = sample_rate
        self.model_path = model_path or os.getenv("FINANCE_APP_VOSK_MODEL_PATH", "models/vosk-model-en-us-0.22-lgraph")

        self.on_text: Callable[[VoiceTextEvent], None] | None = None
        self.on_status: Callable[[str], None] | None = None
        self.on_error: Callable[[str], None] | None = None

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="LocalUsbMicNode", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model
        except ImportError:
            if self.on_error:
                self.on_error(
                    "Voice dependencies missing. Install: pip install vosk sounddevice"
                )
            return

        model_dir = Path(self.model_path)
        if not model_dir.exists():
            if self.on_error:
                self.on_error(
                    "Vosk model not found. Download a model (e.g. vosk-model-en-us-0.22-lgraph) "
                    "and set FINANCE_APP_VOSK_MODEL_PATH or place it under models/."
                )
            return

        try:
            model = Model(str(model_dir))
            recognizer = KaldiRecognizer(model, self.sample_rate)
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Failed to initialize Vosk model: {exc}")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=64)

        def callback(indata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
            del frames, time_info
            if status and self.on_status:
                self.on_status(f"Mic status: {status}")
            try:
                audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        if self.on_status:
            self.on_status("Voice listener ready. Say 'Hey Steven'...")

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=8000,
                dtype="int16",
                channels=1,
                callback=callback,
            ):
                while not self._stop_event.is_set():
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    if recognizer.AcceptWaveform(chunk):
                        payload = json.loads(recognizer.Result())
                        final_text = str(payload.get("text", "")).strip()
                        if final_text and self.on_text:
                            self.on_text(VoiceTextEvent(text=final_text, is_final=True, source_id=self.source_id))
                    else:
                        payload = json.loads(recognizer.PartialResult())
                        partial = str(payload.get("partial", "")).strip()
                        if partial and self.on_text:
                            self.on_text(VoiceTextEvent(text=partial, is_final=False, source_id=self.source_id))
        except Exception as exc:
            if self.on_error:
                self.on_error(f"Microphone capture failed: {exc}")


class VoiceCoordinator:
    """Coordinates voice input nodes and wake-word routing.

    Future nodes can be added by creating another node class that emits VoiceTextEvent.
    """

    def __init__(self, wake_phrase: str = "hey steven") -> None:
        self.router = WakeWordCommandRouter(wake_phrase=wake_phrase)
        self.local_node = LocalUsbMicNode()

        self.on_status: Callable[[str], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self.on_wake: Callable[[str], None] | None = None
        self.on_command: Callable[[str], None] | None = None

        self.router.on_status = self._emit_status
        self.router.on_wake = self._emit_wake
        self.router.on_command = self._emit_command

        self.local_node.on_text = self.router.process_text
        self.local_node.on_status = self._emit_status
        self.local_node.on_error = self._emit_error

    def start(self) -> None:
        self.local_node.start()

    def stop(self) -> None:
        self.local_node.stop()

    def ingest_remote_text(self, text: str, source_id: str = "remote-node", is_final: bool = True) -> None:
        """Future expansion point for remote Alexa-like devices."""
        self.router.process_text(VoiceTextEvent(text=text, is_final=is_final, source_id=source_id))

    def _emit_status(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def _emit_error(self, message: str) -> None:
        if self.on_error:
            self.on_error(message)

    def _emit_wake(self, source_id: str) -> None:
        if self.on_wake:
            self.on_wake(source_id)

    def _emit_command(self, command_text: str) -> None:
        if self.on_command:
            self.on_command(command_text)
