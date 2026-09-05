from __future__ import annotations

import unittest
from unittest.mock import Mock

from finance_app.models import AssistantResult
from finance_app.services.assistant_llm_service import AssistantLLMService
from finance_app.services.llm_service import LLMRequest


class AssistantLlmServiceTests(unittest.TestCase):
    def test_submit_delegates_to_assistant_service(self) -> None:
        assistant_service = Mock()
        expected = AssistantResult(reply="ok", actions=[])
        assistant_service.handle_prompt.return_value = expected

        llm = AssistantLLMService(assistant_service)
        result = llm.submit(LLMRequest(prompt_text="hello", session_key="voice::node-1"))

        assistant_service.handle_prompt.assert_called_once_with("hello", session_key="voice::node-1")
        self.assertIs(result, expected)

    def test_model_and_readiness_passthrough(self) -> None:
        assistant_service = Mock()
        assistant_service.client.model = "qwen"
        assistant_service.client.readiness_error.return_value = None
        assistant_service.client.list_available_models.return_value = ["qwen"]

        llm = AssistantLLMService(assistant_service)

        self.assertIsNone(llm.readiness_error())
        self.assertEqual(llm.model, "qwen")
        self.assertEqual(llm.list_available_models(), ["qwen"])

        llm.set_model("llama")
        llm.ensure_running()
        assistant_service.client.set_model.assert_called_once_with("llama")
        assistant_service.client.ensure_running.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
