from __future__ import annotations

import unittest

from finance_app.agents.base_agent import AgentResponse, BaseAgent, keyword_confidence
from finance_app.agents.finance_agent import FinanceAgent
from finance_app.agents.orchestrator import AgentOrchestrator
from finance_app.models import AssistantResult
from finance_app.services.llm_service import LLMRequest


class _FakeLLMService:
    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.submitted: list[LLMRequest] = []
        self.last_outcome = None

    def submit(self, request: LLMRequest) -> AssistantResult:
        self.submitted.append(request)
        return AssistantResult(reply=self.reply, actions=[])

    def readiness_error(self) -> str | None:
        return None

    def ensure_running(self) -> None:
        return None

    def list_available_models(self) -> list[str]:
        return ["qwen"]

    @property
    def model(self) -> str:
        return "qwen"

    def set_model(self, model_name: str) -> None:
        self._model = model_name


class _StubAgent(BaseAgent):
    def __init__(self, name: str, keywords: set[str]) -> None:
        self._name = name
        self._keywords = frozenset(keywords)
        self.handled: list[LLMRequest] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} stub"

    @property
    def keywords(self) -> frozenset[str]:
        return self._keywords

    def handle(self, request: LLMRequest) -> AgentResponse:
        self.handled.append(request)
        return AgentResponse(
            result=AssistantResult(reply=f"{self._name} handled", actions=[]),
            agent_name=self._name,
        )


def _request(text: str) -> LLMRequest:
    return LLMRequest(prompt_text=text, session_key="typed-assistant")


class KeywordConfidenceTests(unittest.TestCase):
    def test_no_hits_scores_zero(self) -> None:
        self.assertEqual(keyword_confidence("what is the weather", frozenset({"budget"})), 0.0)

    def test_single_hit_clears_threshold(self) -> None:
        self.assertAlmostEqual(keyword_confidence("my budget", frozenset({"budget"})), 0.6)

    def test_punctuation_is_stripped(self) -> None:
        self.assertGreater(keyword_confidence("what's my budget?", frozenset({"budget"})), 0.0)

    def test_empty_inputs_are_safe(self) -> None:
        self.assertEqual(keyword_confidence("", frozenset({"budget"})), 0.0)
        self.assertEqual(keyword_confidence("budget", frozenset()), 0.0)


class SingleAgentOrchestratorTests(unittest.TestCase):
    """With one agent, routing must be a no-op so existing behavior is preserved."""

    def setUp(self) -> None:
        self.llm = _FakeLLMService()
        self.orchestrator = AgentOrchestrator(self.llm)
        self.orchestrator.register(FinanceAgent(self.llm))

    def test_finance_question_routes_to_finance(self) -> None:
        self.orchestrator.submit(_request("how much did I spend on groceries"))

        self.assertEqual(self.orchestrator.last_decision.reason, "sole_agent")
        self.assertEqual(self.orchestrator.last_decision.agent.name, "finance")

    def test_unrelated_question_still_routes_to_finance(self) -> None:
        self.orchestrator.submit(_request("what is the weather"))

        self.assertEqual(self.orchestrator.last_decision.reason, "sole_agent")

    def test_address_to_missing_agent_still_routes_to_finance(self) -> None:
        self.orchestrator.submit(_request("hey calendar, what's on tomorrow"))

        self.assertEqual(self.orchestrator.last_decision.reason, "sole_agent")

    def test_empty_prompt_does_not_raise(self) -> None:
        result = self.orchestrator.submit(_request("   "))

        self.assertEqual(result.reply, "ok")

    def test_result_passes_through_unchanged(self) -> None:
        result = self.orchestrator.submit(_request("what is my budget"))

        self.assertEqual(result.reply, "ok")
        self.assertEqual(len(self.llm.submitted), 1)


class MultiAgentOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.llm = _FakeLLMService()
        self.orchestrator = AgentOrchestrator(self.llm)
        self.finance = FinanceAgent(self.llm)
        self.calendar = _StubAgent("calendar", {"calendar", "meeting", "tomorrow", "schedule"})
        self.orchestrator.register(self.finance)
        self.orchestrator.register(self.calendar)

    def test_keyword_routing_selects_finance(self) -> None:
        self.orchestrator.submit(_request("how much did I spend on rent"))

        self.assertEqual(self.orchestrator.last_decision.agent.name, "finance")
        self.assertEqual(self.orchestrator.last_decision.reason, "keyword")

    def test_keyword_routing_selects_calendar(self) -> None:
        self.orchestrator.submit(_request("what meeting do I have tomorrow"))

        self.assertEqual(self.orchestrator.last_decision.agent.name, "calendar")

    def test_explicit_address_wins_and_strips_prefix(self) -> None:
        self.orchestrator.submit(_request("hey calendar, move my expense review"))

        decision = self.orchestrator.last_decision
        self.assertEqual(decision.agent.name, "calendar")
        self.assertEqual(decision.reason, "explicit")
        self.assertEqual(decision.prompt_text, "move my expense review")
        self.assertEqual(self.calendar.handled[0].prompt_text, "move my expense review")

    def test_colon_address_form(self) -> None:
        self.orchestrator.submit(_request("calendar: move my 3pm"))

        self.assertEqual(self.orchestrator.last_decision.agent.name, "calendar")
        self.assertEqual(self.orchestrator.last_decision.reason, "explicit")

    def test_unmatched_request_falls_back_to_default_agent(self) -> None:
        self.orchestrator.submit(_request("what is the weather"))

        self.assertEqual(self.orchestrator.last_decision.agent.name, "finance")
        self.assertEqual(self.orchestrator.last_decision.reason, "default")

    def test_explicit_address_to_unknown_agent_falls_through(self) -> None:
        self.orchestrator.submit(_request("hey shopping, add milk"))

        self.assertEqual(self.orchestrator.last_decision.reason, "default")

    def test_session_metadata_is_preserved_when_stripping_prefix(self) -> None:
        request = LLMRequest(
            prompt_text="hey calendar, add a meeting",
            session_key="voice::node-1",
            request_source="voice",
            source_id="node-1",
            command_session_id="voice-9",
        )

        self.orchestrator.submit(request)

        forwarded = self.calendar.handled[0]
        self.assertEqual(forwarded.session_key, "voice::node-1")
        self.assertEqual(forwarded.source_id, "node-1")
        self.assertEqual(forwarded.command_session_id, "voice-9")


class OrchestratorRobustnessTests(unittest.TestCase):
    def test_empty_registry_returns_message(self) -> None:
        orchestrator = AgentOrchestrator(_FakeLLMService())

        result = orchestrator.submit(_request("anything"))

        self.assertIn("No agent is available", result.reply)

    def test_duplicate_registration_rejected(self) -> None:
        orchestrator = AgentOrchestrator(_FakeLLMService())
        orchestrator.register(_StubAgent("finance", {"budget"}))

        with self.assertRaises(ValueError):
            orchestrator.register(_StubAgent("finance", {"budget"}))

    def test_agent_exception_is_contained(self) -> None:
        class _BoomAgent(_StubAgent):
            def handle(self, request: LLMRequest) -> AgentResponse:
                raise RuntimeError("agent exploded")

        orchestrator = AgentOrchestrator(_FakeLLMService())
        orchestrator.register(_BoomAgent("finance", {"budget"}))

        result = orchestrator.submit(_request("my budget"))

        self.assertIn("agent exploded", result.reply)

    def test_llm_service_protocol_is_forwarded(self) -> None:
        llm = _FakeLLMService()
        orchestrator = AgentOrchestrator(llm)

        self.assertIsNone(orchestrator.readiness_error())
        self.assertEqual(orchestrator.model, "qwen")
        self.assertEqual(orchestrator.list_available_models(), ["qwen"])
        self.assertIsNone(orchestrator.last_outcome)


if __name__ == "__main__":
    unittest.main()
