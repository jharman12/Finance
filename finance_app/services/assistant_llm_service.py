from __future__ import annotations

from finance_app.models import AssistantResult
from finance_app.services.assistant_service import AssistantService
from finance_app.services.llm_service import LLMRequest


class AssistantLLMService:
    """Week 2 abstraction layer over AssistantService for unified local/remote requests."""

    def __init__(self, assistant_service: AssistantService) -> None:
        self.assistant_service = assistant_service

    def submit(self, request: LLMRequest) -> AssistantResult:
        return self.assistant_service.handle_prompt(request.prompt_text, session_key=request.session_key)

    def readiness_error(self) -> str | None:
        return self.assistant_service.client.readiness_error()

    def ensure_running(self) -> None:
        self.assistant_service.client.ensure_running()

    def list_available_models(self) -> list[str]:
        return self.assistant_service.client.list_available_models()

    @property
    def model(self) -> str:
        return self.assistant_service.client.model

    def set_model(self, model_name: str) -> None:
        self.assistant_service.client.set_model(model_name)
