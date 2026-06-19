from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from finance_app.services.assistant_service import AssistantService
from finance_app.services.ollama_client import OllamaMessage


@dataclass
class _FakeCategory:
    name: str
    kind: str


@dataclass
class _FakeRecurring:
    description: str
    kind: str
    category: str
    amount: float
    cadence_label: str
    next_run_on: object


class _FakeSnapshot:
    income_total = 1000.0
    expense_total = 250.0
    net_total = 750.0
    transaction_count = 3
    top_categories = [("Groceries", 120.0)]


class _FakeRepository:
    def snapshot(self):
        return _FakeSnapshot()

    def list_categories(self):
        return [_FakeCategory(name="Groceries", kind="expense")]

    def list_recurring_items(self):
        return []


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[list[OllamaMessage]] = []
        self._count = 0

    def chat(self, messages: list[OllamaMessage], json_mode: bool = True) -> str:  # noqa: ARG002
        self.calls.append(list(messages))
        self._count += 1
        return json.dumps({"reply": f"ok-{self._count}", "actions": []})


class AssistantSessionIsolationTests(unittest.TestCase):
    def test_history_is_scoped_per_session_key(self) -> None:
        service = AssistantService(repository=_FakeRepository(), client=_FakeClient())
        client = service.client

        service.handle_prompt("first voice", session_key="voice::node-1")
        service.handle_prompt("second voice", session_key="voice::node-1")

        second_call_roles = [message.role for message in client.calls[1]]
        self.assertEqual(second_call_roles, ["system", "user", "assistant", "user"])

        service.handle_prompt("first typed", session_key="typed-assistant")
        third_call_roles = [message.role for message in client.calls[2]]
        self.assertEqual(third_call_roles, ["system", "user"])

    def test_clear_conversation_history_can_target_one_session(self) -> None:
        service = AssistantService(repository=_FakeRepository(), client=_FakeClient())
        service.handle_prompt("voice one", session_key="voice::node-1")
        service.handle_prompt("typed one", session_key="typed-assistant")

        self.assertIn("1 exchanges", service.get_conversation_summary(session_key="voice::node-1"))

        service.clear_conversation_history(session_key="voice::node-1")

        self.assertIn("No conversation history yet", service.get_conversation_summary(session_key="voice::node-1"))
        self.assertIn("1 exchanges", service.get_conversation_summary(session_key="typed-assistant"))


if __name__ == "__main__":
    unittest.main()
