from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from finance_app.models import AssistantResult


@dataclass(slots=True)
class LLMRequest:
    prompt_text: str
    session_key: str
    request_source: str = "typed"
    source_id: str | None = None
    command_session_id: str | None = None


class LLMService(Protocol):
    def submit(self, request: LLMRequest) -> AssistantResult:
        ...

    def readiness_error(self) -> str | None:
        ...

    def ensure_running(self) -> None:
        ...

    def list_available_models(self) -> list[str]:
        ...

    @property
    def model(self) -> str:
        ...

    def set_model(self, model_name: str) -> None:
        ...
