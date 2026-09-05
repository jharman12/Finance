from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from finance_app.models import AssistantResult
from finance_app.services.llm_service import LLMRequest


@dataclass(slots=True)
class AgentResponse:
    result: AssistantResult
    agent_name: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


def keyword_confidence(prompt_text: str, keywords: frozenset[str]) -> float:
    """Hit-ratio score in [0, 1]; a single hit already clears the routing threshold."""
    tokens = {token.strip(".,!?;:'\"$").lower() for token in str(prompt_text or "").split()}
    if not tokens or not keywords:
        return 0.0
    hits = len(tokens & keywords)
    if hits == 0:
        return 0.0
    return min(1.0, 0.4 + 0.2 * hits)


class BaseAgent(ABC):
    """Contract every domain agent must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable lowercase identifier used as the registry key, e.g. 'finance'."""

    @property
    @abstractmethod
    def description(self) -> str:
        """One human-readable line, shown in help text."""

    @property
    @abstractmethod
    def keywords(self) -> frozenset[str]:
        """Lowercase single words hinting this agent should handle a request."""

    def can_handle(self, request: LLMRequest) -> float:
        return keyword_confidence(request.prompt_text, self.keywords)

    @abstractmethod
    def handle(self, request: LLMRequest) -> AgentResponse:
        """Process the request. Should degrade rather than raise."""
