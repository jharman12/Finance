from __future__ import annotations

from difflib import SequenceMatcher
import json
from pathlib import Path


class VoskPhraseWakeDetector:
    """Wake detector using Vosk partial/final text and phrase matching."""

    name = "vosk_phrase"

    def __init__(self, model_path: str, sample_rate: int, wake_phrase: str = "hey steven") -> None:
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.wake_phrase = self._normalize(wake_phrase)
        self._model = None
        self._recognizer = None

    def start(self) -> None:
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("Vosk is required for phrase wake detection") from exc

        model_dir = Path(self.model_path)
        if not model_dir.exists():
            raise RuntimeError(f"Vosk model not found at {self.model_path}")

        if self._model is None:
            self._model = Model(str(model_dir))
        self._recognizer = KaldiRecognizer(self._model, self.sample_rate)

    def stop(self) -> None:
        self._recognizer = None

    def detect(self, chunk: bytes) -> bool:
        recognizer = self._recognizer
        if recognizer is None:
            return False

        if recognizer.AcceptWaveform(chunk):
            payload = json.loads(recognizer.Result())
            text = str(payload.get("text", "")).strip()
        else:
            payload = json.loads(recognizer.PartialResult())
            text = str(payload.get("partial", "")).strip()

        normalized = self._normalize(text)
        if not normalized:
            return False

        return self._matches_wake_phrase(normalized)

    def _matches_wake_phrase(self, normalized_text: str) -> bool:
        variants = {
            self.wake_phrase,
            "hey steven",
            "hey stephen",
            "hay steven",
            "hay stephen",
        }
        if any(variant in normalized_text for variant in variants):
            return True

        wake_tokens = self.wake_phrase.split()
        text_tokens = normalized_text.split()
        if not wake_tokens or not text_tokens:
            return False

        candidate_sizes = {max(1, len(wake_tokens) - 1), len(wake_tokens), len(wake_tokens) + 1}
        for size in candidate_sizes:
            if size > len(text_tokens):
                continue
            for index in range(0, len(text_tokens) - size + 1):
                candidate = " ".join(text_tokens[index : index + size])
                similarity = SequenceMatcher(None, candidate, self.wake_phrase).ratio()
                if similarity >= 0.78:
                    return True

        return False

    @staticmethod
    def _normalize(text: str) -> str:
        lowered = text.lower().strip()
        cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in lowered)
        return " ".join(cleaned.split())


class OpenWakeWordDetector:
    """Optional wake detector using openWakeWord model.

    This detector is best-effort and falls back to phrase wake if unavailable.
    """

    name = "openwakeword"

    def __init__(self, sample_rate: int, threshold: float = 0.5, model_path: str | None = None) -> None:
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.model_path = model_path
        self._model = None

    def start(self) -> None:
        model_path = (self.model_path or "").strip()
        if not model_path:
            raise RuntimeError(
                "openwakeword mode requires FINANCE_APP_OPENWAKEWORD_MODEL_PATH for a dedicated Hey Steven model"
            )

        model_file = Path(model_path)
        if not model_file.exists():
            raise RuntimeError(f"OpenWakeWord model not found at {model_path}")

        try:
            from openwakeword.model import Model as OwwModel
        except Exception as exc:  # pragma: no cover - dependency gate
            raise RuntimeError("openwakeword is not installed. Install: pip install openwakeword") from exc

        self._model = OwwModel(wakeword_models=[str(model_file)])

    def stop(self) -> None:
        self._model = None

    def detect(self, chunk: bytes) -> bool:
        model = self._model
        if model is None:
            return False

        try:
            import numpy as np
        except Exception:
            return False

        audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return False

        try:
            scores = model.predict(audio)
        except Exception:
            return False

        if isinstance(scores, dict):
            return any(float(value) >= self.threshold for value in scores.values())
        return False
