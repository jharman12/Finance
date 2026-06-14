from __future__ import annotations

import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

import requests

from finance_app.config import DEFAULT_MODEL, OLLAMA_BASE_URL, OLLAMA_START_COMMAND


@dataclass(slots=True)
class OllamaMessage:
    role: str
    content: str


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = DEFAULT_MODEL,
        startup_command: tuple[str, ...] = OLLAMA_START_COMMAND,
        timeout_seconds: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.startup_command = startup_command
        self.timeout_seconds = timeout_seconds
        self._startup_process: subprocess.Popen[str] | None = None

    def is_running(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.ok
        except requests.RequestException:
            return False

    def list_available_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            response.raise_for_status()
        except requests.RequestException:
            return []

        payload = response.json()
        models = payload.get("models", []) if isinstance(payload, dict) else []
        available_models: list[str] = []
        for model in models:
            if not isinstance(model, dict):
                continue
            name = str(model.get("name") or model.get("model") or "").strip()
            if name:
                available_models.append(name)
        return available_models

    def ensure_model_available(self) -> None:
        self.ensure_running()
        available_models = self.list_available_models()
        if self.model in available_models:
            return

        if available_models:
            raise RuntimeError(
                f"Model '{self.model}' is not available. Available models: {', '.join(available_models)}"
            )

        raise RuntimeError(f"Model '{self.model}' is not available and Ollama returned no installed models.")

    def readiness_error(self) -> str | None:
        if not self.is_running():
            return "Ollama is not responding yet. Start Ollama and try again in a moment."

        available_models = self.list_available_models()
        if self.model in available_models:
            return None

        if available_models:
            return f"Model '{self.model}' is not available. Available models: {', '.join(available_models)}"

        return f"Model '{self.model}' is not available and Ollama returned no installed models."

    def wait_until_running(self, timeout_seconds: int | None = None) -> None:
        deadline = time.monotonic() + float(timeout_seconds or self.timeout_seconds)
        while time.monotonic() < deadline:
            if self.is_running():
                return
            time.sleep(1)

        raise RuntimeError("Timed out waiting for Ollama to respond.")

    def ensure_running(self) -> None:
        if self.is_running():
            return

        if not self.startup_command:
            raise RuntimeError("Ollama is not running and no startup command is configured.")

        if self._startup_process is None or self._startup_process.poll() is not None:
            self._startup_process = subprocess.Popen(
                self.startup_command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )

        self.wait_until_running()

    def chat(self, messages: list[OllamaMessage], json_mode: bool = True) -> str:
        self.ensure_model_available()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [asdict(message) for message in messages],
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        try:
            return self._chat_with_messages(payload)
        except requests.HTTPError as exc:
            response = exc.response
            if response is not None and response.status_code == 404:
                return self._generate_with_messages(messages, json_mode=json_mode)
            raise

    def _chat_with_messages(self, payload: dict[str, Any]) -> str:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return str(data["message"]["content"])

    def _generate_with_messages(self, messages: list[OllamaMessage], json_mode: bool = True) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": self._messages_to_prompt(messages),
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        response = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if response.status_code == 404:
                available_models = self.list_available_models()
                model_list = ", ".join(available_models) if available_models else "none"
                raise RuntimeError(
                    f"Model '{self.model}' was not found in Ollama. Available models: {model_list}"
                ) from exc
            raise
        data = response.json()
        return str(data.get("response", ""))

    def _messages_to_prompt(self, messages: list[OllamaMessage]) -> str:
        prompt_lines: list[str] = []
        for message in messages:
            role = message.role.strip().lower()
            if role == "system":
                prompt_lines.append(f"System: {message.content.strip()}")
            elif role == "user":
                prompt_lines.append(f"User: {message.content.strip()}")
            elif role == "assistant":
                prompt_lines.append(f"Assistant: {message.content.strip()}")
            else:
                prompt_lines.append(f"{message.role.title()}: {message.content.strip()}")

        prompt_lines.append("Assistant:")
        return "\n\n".join(prompt_lines)
