from __future__ import annotations

import re
from dataclasses import dataclass

from finance_app.agents.base_agent import AgentResponse, BaseAgent
from finance_app.models import AssistantResult
from finance_app.services.llm_service import LLMRequest, LLMService

MIN_CONFIDENCE = 0.35

# "hey calendar, ..." or "calendar: ..."
_ADDRESS_PATTERN = re.compile(
    r"^\s*(?:hey|hi|ok|okay|yo)?[\s,]*([a-z][a-z\-]{1,20})\s*[,:]\s*(.+)$",
    re.IGNORECASE,
)


@dataclass(slots=True)
class RoutingDecision:
    agent: BaseAgent | None
    confidence: float
    reason: str
    prompt_text: str


class AgentOrchestrator:
    """Routes each request to exactly one agent. Implements the LLMService protocol."""

    def __init__(self, llm_service: LLMService, default_agent_name: str = "finance") -> None:
        self._llm_service = llm_service
        self._agents: dict[str, BaseAgent] = {}
        self._default_agent_name = default_agent_name
        self.last_response: AgentResponse | None = None
        self.last_decision: RoutingDecision | None = None

    def register(self, agent: BaseAgent) -> None:
        key = agent.name.strip().lower()
        if not key:
            raise ValueError("Agent name must be non-empty")
        if key in self._agents:
            raise ValueError(f"Agent already registered: {key}")
        self._agents[key] = agent

    def list_agents(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def route(self, request: LLMRequest) -> RoutingDecision:
        prompt_text = str(request.prompt_text or "")

        if not self._agents:
            return RoutingDecision(None, 0.0, "no_agent", prompt_text)

        # With one agent registered, routing is a deliberate no-op so behavior
        # stays identical to the pre-orchestrator pipeline.
        if len(self._agents) == 1:
            only_agent = next(iter(self._agents.values()))
            return RoutingDecision(only_agent, 1.0, "sole_agent", prompt_text)

        addressed = _ADDRESS_PATTERN.match(prompt_text)
        if addressed:
            alias = addressed.group(1).strip().lower()
            agent = self._agents.get(alias)
            if agent is not None:
                return RoutingDecision(agent, 1.0, "explicit", addressed.group(2).strip())

        best_agent: BaseAgent | None = None
        best_score = 0.0
        for agent in self._agents.values():
            try:
                score = float(agent.can_handle(request))
            except Exception:
                score = 0.0
            if score > best_score:
                best_agent = agent
                best_score = score

        if best_agent is not None and best_score >= MIN_CONFIDENCE:
            return RoutingDecision(best_agent, best_score, "keyword", prompt_text)

        fallback = self._agents.get(self._default_agent_name)
        if fallback is not None:
            return RoutingDecision(fallback, best_score, "default", prompt_text)

        return RoutingDecision(None, 0.0, "no_agent", prompt_text)

    def submit(self, request: LLMRequest) -> AssistantResult:
        decision = self.route(request)
        self.last_decision = decision
        agent = decision.agent

        if agent is None:
            result = AssistantResult(reply="No agent is available to handle that request.", actions=[])
            self.last_response = AgentResponse(result=result, agent_name="none", confidence=0.0)
            return result

        agent_request = request
        if decision.reason == "explicit" and decision.prompt_text != request.prompt_text:
            agent_request = LLMRequest(
                prompt_text=decision.prompt_text,
                session_key=request.session_key,
                request_source=request.request_source,
                source_id=request.source_id,
                command_session_id=request.command_session_id,
            )

        try:
            response = agent.handle(agent_request)
        except Exception as exc:
            result = AssistantResult(
                reply=f"The {agent.name} agent failed to handle that request.\n\nDetails: {exc}",
                actions=[],
            )
            response = AgentResponse(result=result, agent_name=agent.name)

        response.confidence = decision.confidence
        self.last_response = response
        return response.result

    @property
    def last_outcome(self):
        return getattr(self._llm_service, "last_outcome", None)

    def readiness_error(self) -> str | None:
        return self._llm_service.readiness_error()

    def ensure_running(self) -> None:
        self._llm_service.ensure_running()

    def list_available_models(self) -> list[str]:
        return self._llm_service.list_available_models()

    @property
    def model(self) -> str:
        return self._llm_service.model

    def set_model(self, model_name: str) -> None:
        self._llm_service.set_model(model_name)
