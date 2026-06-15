from __future__ import annotations

import json
import time
from pathlib import Path

from .asr_provider import AsrResult


class VoskAsrProvider:
    name = "vosk"

    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model

        try:
            from vosk import Model
        except ImportError as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("Vosk is not installed. Install: pip install vosk") from exc

        model_dir = Path(self.model_path)
        if not model_dir.exists():
            raise RuntimeError(f"Vosk model not found at {self.model_path}")

        self._model = Model(str(model_dir))
        return self._model

    def transcribe_pcm16(self, audio_bytes: bytes, sample_rate: int) -> AsrResult:
        started = time.perf_counter()
        model = self._load_model()

        try:
            from vosk import KaldiRecognizer
        except ImportError as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("Vosk is not installed. Install: pip install vosk") from exc

        recognizer = KaldiRecognizer(model, sample_rate)
        recognizer.AcceptWaveform(audio_bytes)
        payload = json.loads(recognizer.FinalResult())

        text = str(payload.get("text", "")).strip()
        words = payload.get("result", [])
        confidences = [float(item.get("conf", 0.0)) for item in words if isinstance(item, dict)]
        confidence = sum(confidences) / len(confidences) if confidences else (0.65 if text else 0.0)

        latency_ms = int((time.perf_counter() - started) * 1000)
        return AsrResult(
            text=text,
            provider=self.name,
            confidence_0_1=max(0.0, min(1.0, confidence)),
            latency_ms=latency_ms,
            is_final=True,
        )
