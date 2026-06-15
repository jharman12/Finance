from __future__ import annotations

import math
import time

from .asr_provider import AsrResult


class FasterWhisperAsrProvider:
    name = "faster_whisper"

    def __init__(
        self,
        model_size: str = "small.en",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - dependency gate
            raise RuntimeError(
                "faster-whisper is not installed. Install: pip install faster-whisper ctranslate2"
            ) from exc

        self._model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        return self._model

    def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int) -> AsrResult:
        started = time.perf_counter()
        model = self._load_model()

        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("numpy is required for faster-whisper audio conversion") from exc

        waveform = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        if sample_rate <= 0:
            raise RuntimeError("Invalid sample rate for transcription")

        segments, info = model.transcribe(
            audio=waveform,
            language="en",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        segment_list = list(segments)
        text = " ".join(str(segment.text).strip() for segment in segment_list).strip()

        avg_logprob = 0.0
        if segment_list:
            avg_logprob = sum(float(getattr(seg, "avg_logprob", -2.0)) for seg in segment_list) / len(segment_list)

        # Map avg_logprob (roughly -2.5..0) into a practical confidence band.
        confidence = 1.0 / (1.0 + math.exp(-3.0 * (avg_logprob + 1.2))) if text else 0.0
        no_speech = float(getattr(info, "no_speech_prob", 0.0)) if info is not None else 0.0

        latency_ms = int((time.perf_counter() - started) * 1000)
        return AsrResult(
            text=text,
            provider=self.name,
            confidence_0_1=max(0.0, min(1.0, confidence)),
            latency_ms=latency_ms,
            is_final=True,
            no_speech_0_1=max(0.0, min(1.0, no_speech)),
        )
