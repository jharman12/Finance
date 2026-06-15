from __future__ import annotations

import queue
import threading
from typing import Callable


class MicStreamSource:
    """Captures chunks of PCM16 audio from default input device."""

    def __init__(self, sample_rate: int = 16000, blocksize: int = 1600) -> None:
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(
        self,
        on_audio_chunk: Callable[[bytes], None],
        on_status: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(on_audio_chunk, on_status, on_error),
            name="MicStreamSource",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(
        self,
        on_audio_chunk: Callable[[bytes], None],
        on_status: Callable[[str], None] | None,
        on_error: Callable[[str], None] | None,
    ) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            if on_error:
                on_error("Voice dependencies missing. Install: pip install sounddevice")
            return

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=64)

        def callback(indata, frames, time_info, status) -> None:  # type: ignore[no-untyped-def]
            del frames, time_info
            if status and on_status:
                on_status(f"Mic status: {status}")
            try:
                audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        if on_status:
            on_status("Voice listener ready. Say 'Hey Steven'...")

        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=self.blocksize,
                dtype="int16",
                channels=1,
                callback=callback,
            ):
                while not self._stop_event.is_set():
                    try:
                        chunk = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    on_audio_chunk(chunk)
        except Exception as exc:  # pragma: no cover - hardware dependent
            if on_error:
                on_error(f"Microphone capture failed: {exc}")
