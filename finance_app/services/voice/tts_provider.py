from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

LOCAL_SOURCE_ID = "local-usb-mic"
DEFAULT_SAMPLE_RATE = 22050
_PLAYBACK_BLOCK_FRAMES = 640


@dataclass(frozen=True, slots=True)
class SynthesizedSpeech:
    pcm16: bytes
    sample_rate: int
    channels: int = 1
    voice: str = ""
    synth_ms: int = 0

    @property
    def audio_ms(self) -> int:
        frame_bytes = 2 * max(1, self.channels)
        frames = len(self.pcm16) // frame_bytes
        if self.sample_rate <= 0:
            return 0
        return int(frames * 1000 / self.sample_rate)


class TtsProvider(Protocol):
    name: str

    def is_available(self) -> bool: ...

    def synthesize(self, text: str, cancel: threading.Event) -> SynthesizedSpeech: ...


class AudioSink(Protocol):
    def play(self, speech: SynthesizedSpeech, cancel: threading.Event) -> None: ...

    def stop(self) -> None: ...


class NullTtsProvider:
    """Produces no audio; used when TTS is disabled or unavailable."""

    name = "null"

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, cancel: threading.Event) -> SynthesizedSpeech:
        return SynthesizedSpeech(pcm16=b"", sample_rate=DEFAULT_SAMPLE_RATE, voice=self.name)


class PiperTtsProvider:
    """Neural TTS via the standalone Piper binary, streaming raw PCM from stdout."""

    name = "piper"

    def __init__(self, exe_path: str | None = None, voice_path: str | None = None) -> None:
        self.exe_path = (exe_path or os.getenv("FINANCE_APP_PIPER_EXE", "")).strip()
        self.voice_path = (voice_path or os.getenv("FINANCE_APP_PIPER_VOICE", "")).strip()
        self._process: subprocess.Popen[bytes] | None = None

    def is_available(self) -> bool:
        if not self.exe_path or not self.voice_path:
            return False
        return Path(self.exe_path).exists() and Path(self.voice_path).exists()

    def _voice_sample_rate(self) -> int:
        config_path = Path(f"{self.voice_path}.json")
        if not config_path.exists():
            return DEFAULT_SAMPLE_RATE
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            return int(payload.get("audio", {}).get("sample_rate", DEFAULT_SAMPLE_RATE))
        except Exception:
            return DEFAULT_SAMPLE_RATE

    def synthesize(self, text: str, cancel: threading.Event) -> SynthesizedSpeech:
        cleaned = str(text or "").strip()
        if not cleaned:
            return SynthesizedSpeech(pcm16=b"", sample_rate=self._voice_sample_rate(), voice=self.name)

        started = time.perf_counter()
        command = [self.exe_path, "--model", self.voice_path, "--output-raw"]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._process = process

        chunks: list[bytes] = []
        try:
            if process.stdin is not None:
                process.stdin.write(cleaned.encode("utf-8"))
                process.stdin.close()

            while True:
                if cancel.is_set():
                    process.kill()
                    break
                if process.stdout is None:
                    break
                block = process.stdout.read(4096)
                if not block:
                    break
                chunks.append(block)
        finally:
            try:
                process.wait(timeout=2.0)
            except Exception:
                process.kill()
            self._process = None

        return SynthesizedSpeech(
            pcm16=b"".join(chunks),
            sample_rate=self._voice_sample_rate(),
            voice=self.name,
            synth_ms=int((time.perf_counter() - started) * 1000),
        )


class Pyttsx3TtsProvider:
    """SAPI5 fallback. Speaks directly and returns no PCM, so it is local-only."""

    name = "pyttsx3"

    def is_available(self) -> bool:
        try:
            import pyttsx3  # noqa: F401
        except Exception:
            return False
        return True

    def synthesize(self, text: str, cancel: threading.Event) -> SynthesizedSpeech:
        cleaned = str(text or "").strip()
        started = time.perf_counter()
        if cleaned and not cancel.is_set():
            try:
                import pyttsx3

                # COM requires the engine be created and driven on the calling thread.
                engine = pyttsx3.init()
                engine.say(cleaned)
                engine.runAndWait()
                engine.stop()
            except Exception:
                pass
        return SynthesizedSpeech(
            pcm16=b"",
            sample_rate=DEFAULT_SAMPLE_RATE,
            voice=self.name,
            synth_ms=int((time.perf_counter() - started) * 1000),
        )


class NullAudioSink:
    """Records playback requests without opening an audio device."""

    def __init__(self) -> None:
        self.played: list[SynthesizedSpeech] = []
        self.stop_calls = 0

    def play(self, speech: SynthesizedSpeech, cancel: threading.Event) -> None:
        self.played.append(speech)

    def stop(self) -> None:
        self.stop_calls += 1


class LocalSpeakerSink:
    """Blocking block-wise playback on the default output device."""

    def __init__(self) -> None:
        self._stream = None
        self._lock = threading.Lock()

    def play(self, speech: SynthesizedSpeech, cancel: threading.Event) -> None:
        if not speech.pcm16:
            return

        import sounddevice as sd

        stream = sd.RawOutputStream(
            samplerate=speech.sample_rate,
            channels=max(1, speech.channels),
            dtype="int16",
        )
        with self._lock:
            self._stream = stream

        block_bytes = _PLAYBACK_BLOCK_FRAMES * 2 * max(1, speech.channels)
        try:
            stream.start()
            for offset in range(0, len(speech.pcm16), block_bytes):
                if cancel.is_set():
                    break
                stream.write(speech.pcm16[offset : offset + block_bytes])
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            with self._lock:
                self._stream = None

    def stop(self) -> None:
        with self._lock:
            stream = self._stream
        if stream is None:
            return
        try:
            stream.abort()
        except Exception:
            pass


def build_default_provider() -> TtsProvider:
    """Piper when configured, else SAPI5, else silent."""
    piper = PiperTtsProvider()
    if piper.is_available():
        return piper

    sapi = Pyttsx3TtsProvider()
    if sapi.is_available():
        return sapi

    return NullTtsProvider()
