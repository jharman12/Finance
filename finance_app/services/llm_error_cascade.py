from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from finance_app.models import AssistantResult
from finance_app.services.llm_service import LLMRequest

TIER_LOCAL = "local_llm"
TIER_CLOUD = "cloud_llm"
TIER_DETERMINISTIC = "deterministic"
TIER_ERROR = "error"

DEFAULT_ERROR_REPLY = (
    "I could not reach the assistant and could not build an answer from your local data. "
    "Check that Ollama is running, then try again."
)

AssistantHandler = Callable[[LLMRequest], AssistantResult]


@dataclass(slots=True)
class CascadeOutcome:
    result: AssistantResult
    tier: str
    tier_errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def used_fallback(self) -> bool:
        return self.tier != TIER_LOCAL

    @property
    def degraded(self) -> bool:
        return self.tier in (TIER_DETERMINISTIC, TIER_ERROR)


class LLMErrorCascade:
    """Four-level response cascade so the assistant always returns something."""

    def __init__(
        self,
        local_handler: AssistantHandler,
        cloud_handler: AssistantHandler | None = None,
        deterministic_handler: AssistantHandler | None = None,
        error_reply: str = DEFAULT_ERROR_REPLY,
    ) -> None:
        self.local_handler = local_handler
        self.cloud_handler = cloud_handler
        self.deterministic_handler = deterministic_handler
        self.error_reply = error_reply

    def run(self, request: LLMRequest) -> CascadeOutcome:
        tier_errors: list[tuple[str, str]] = []

        for tier, handler in (
            (TIER_LOCAL, self.local_handler),
            (TIER_CLOUD, self.cloud_handler),
            (TIER_DETERMINISTIC, self.deterministic_handler),
        ):
            if handler is None:
                continue
            try:
                result = handler(request)
            except Exception as exc:
                tier_errors.append((tier, str(exc)))
                continue

            if self._is_usable(result):
                return CascadeOutcome(result=result, tier=tier, tier_errors=tier_errors)

            tier_errors.append((tier, "empty_response"))

        detail = "; ".join(f"{tier}: {message}" for tier, message in tier_errors)
        reply = f"{self.error_reply}\n\nDetails: {detail}" if detail else self.error_reply
        return CascadeOutcome(
            result=AssistantResult(reply=reply, actions=[]),
            tier=TIER_ERROR,
            tier_errors=tier_errors,
        )

    @staticmethod
    def _is_usable(result: AssistantResult | None) -> bool:
        if result is None:
            return False
        if str(result.reply or "").strip():
            return True
        return bool(result.actions) or bool(result.applied_actions)
