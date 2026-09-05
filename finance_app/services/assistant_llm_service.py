from __future__ import annotations

from finance_app.models import AssistantResult
from finance_app.services.assistant_service import AssistantService
from finance_app.services.llm_error_cascade import (
    AssistantHandler,
    CascadeOutcome,
    LLMErrorCascade,
)
from finance_app.services.llm_service import LLMRequest


class AssistantLLMService:
    """Week 2 abstraction layer over AssistantService for unified local/remote requests."""

    def __init__(
        self,
        assistant_service: AssistantService,
        cloud_handler: AssistantHandler | None = None,
    ) -> None:
        self.assistant_service = assistant_service
        self.cascade = LLMErrorCascade(
            local_handler=self._handle_local,
            cloud_handler=cloud_handler,
            deterministic_handler=self._handle_deterministic,
        )
        self.last_outcome: CascadeOutcome | None = None

    def submit(self, request: LLMRequest) -> AssistantResult:
        outcome = self.cascade.run(request)
        self.last_outcome = outcome
        return outcome.result

    def _handle_local(self, request: LLMRequest) -> AssistantResult:
        return self.assistant_service.handle_prompt(request.prompt_text, session_key=request.session_key)

    def _handle_deterministic(self, request: LLMRequest) -> AssistantResult:
        return self.assistant_service.build_deterministic_result(request.prompt_text)

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
