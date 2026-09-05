from __future__ import annotations

import unittest

from finance_app.models import AssistantResult
from finance_app.services.llm_error_cascade import (
    TIER_CLOUD,
    TIER_DETERMINISTIC,
    TIER_ERROR,
    TIER_LOCAL,
    LLMErrorCascade,
)
from finance_app.services.llm_service import LLMRequest


def _request() -> LLMRequest:
    return LLMRequest(prompt_text="how am I doing?", session_key="typed-assistant")


def _ok(reply: str):
    return lambda request: AssistantResult(reply=reply, actions=[])


def _boom(message: str):
    def handler(request):
        raise RuntimeError(message)

    return handler


def _empty(request):
    return AssistantResult(reply="   ", actions=[])


class LLMErrorCascadeTests(unittest.TestCase):
    def test_local_success_skips_other_tiers(self) -> None:
        cascade = LLMErrorCascade(
            local_handler=_ok("local answer"),
            cloud_handler=_boom("cloud should not run"),
            deterministic_handler=_boom("deterministic should not run"),
        )

        outcome = cascade.run(_request())

        self.assertEqual(outcome.tier, TIER_LOCAL)
        self.assertEqual(outcome.result.reply, "local answer")
        self.assertFalse(outcome.used_fallback)
        self.assertFalse(outcome.degraded)

    def test_falls_through_to_cloud_when_local_fails(self) -> None:
        cascade = LLMErrorCascade(
            local_handler=_boom("ollama down"),
            cloud_handler=_ok("cloud answer"),
            deterministic_handler=_ok("deterministic answer"),
        )

        outcome = cascade.run(_request())

        self.assertEqual(outcome.tier, TIER_CLOUD)
        self.assertEqual(outcome.result.reply, "cloud answer")
        self.assertTrue(outcome.used_fallback)
        self.assertFalse(outcome.degraded)
        self.assertEqual(outcome.tier_errors[0][0], TIER_LOCAL)

    def test_falls_through_to_deterministic_when_no_cloud_configured(self) -> None:
        cascade = LLMErrorCascade(
            local_handler=_boom("ollama down"),
            cloud_handler=None,
            deterministic_handler=_ok("deterministic answer"),
        )

        outcome = cascade.run(_request())

        self.assertEqual(outcome.tier, TIER_DETERMINISTIC)
        self.assertTrue(outcome.degraded)

    def test_empty_reply_is_treated_as_failure(self) -> None:
        cascade = LLMErrorCascade(
            local_handler=_empty,
            deterministic_handler=_ok("deterministic answer"),
        )

        outcome = cascade.run(_request())

        self.assertEqual(outcome.tier, TIER_DETERMINISTIC)
        self.assertIn(("local_llm", "empty_response"), outcome.tier_errors)

    def test_reply_with_actions_only_is_usable(self) -> None:
        def handler(request):
            return AssistantResult(reply="", actions=[{"type": "add_expense"}])

        cascade = LLMErrorCascade(local_handler=handler)

        outcome = cascade.run(_request())

        self.assertEqual(outcome.tier, TIER_LOCAL)

    def test_error_tier_returns_message_instead_of_raising(self) -> None:
        cascade = LLMErrorCascade(
            local_handler=_boom("ollama down"),
            cloud_handler=_boom("cloud down"),
            deterministic_handler=_boom("db down"),
        )

        outcome = cascade.run(_request())

        self.assertEqual(outcome.tier, TIER_ERROR)
        self.assertTrue(outcome.degraded)
        self.assertIn("ollama down", outcome.result.reply)
        self.assertIn("db down", outcome.result.reply)
        self.assertEqual(len(outcome.tier_errors), 3)


if __name__ == "__main__":
    unittest.main()
