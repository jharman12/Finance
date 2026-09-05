from __future__ import annotations

import unittest

from finance_app.services.llm_request_queue import (
    LOCAL_PRIORITY,
    REMOTE_PRIORITY,
    VoiceRequestQueue,
    base_priority_for_source,
)
from finance_app.services.llm_service import LLMRequest


def _request(source_id: str, text: str) -> LLMRequest:
    return LLMRequest(
        prompt_text=text,
        session_key=f"voice::{source_id}",
        request_source="voice",
        source_id=source_id,
    )


class BasePriorityTests(unittest.TestCase):
    def test_local_outranks_remote(self) -> None:
        self.assertEqual(base_priority_for_source("local-usb-mic"), LOCAL_PRIORITY)
        self.assertEqual(base_priority_for_source("node-1"), REMOTE_PRIORITY)

    def test_blank_source_treated_as_local(self) -> None:
        self.assertEqual(base_priority_for_source(""), LOCAL_PRIORITY)
        self.assertEqual(base_priority_for_source(None), LOCAL_PRIORITY)


class VoiceRequestQueueTests(unittest.TestCase):
    def test_local_dequeues_before_remote(self) -> None:
        queue = VoiceRequestQueue()
        queue.enqueue(_request("node-1", "remote first"), now=100.0)
        queue.enqueue(_request("local-usb-mic", "local second"), now=100.0)

        first = queue.pop_next(now=100.0)

        self.assertIsNotNone(first)
        self.assertEqual(first.prompt_text, "local second")

    def test_fifo_within_same_priority(self) -> None:
        queue = VoiceRequestQueue()
        queue.enqueue(_request("node-1", "first"), now=100.0)
        queue.enqueue(_request("node-2", "second"), now=100.0)

        self.assertEqual(queue.pop_next(now=100.0).prompt_text, "first")
        self.assertEqual(queue.pop_next(now=100.0).prompt_text, "second")

    def test_aged_remote_overtakes_fresh_local(self) -> None:
        queue = VoiceRequestQueue(age_boost_per_second=1.0)
        queue.enqueue(_request("node-1", "waiting remote"), now=0.0)
        queue.enqueue(_request("local-usb-mic", "fresh local"), now=10.0)

        # Remote waited 10s (6 + 10 = 16) vs fresh local (10).
        self.assertEqual(queue.pop_next(now=10.0).prompt_text, "waiting remote")

    def test_remote_does_not_starve_under_local_load(self) -> None:
        queue = VoiceRequestQueue(age_boost_per_second=1.0)
        queue.enqueue(_request("node-1", "remote"), now=0.0)

        dispatched: list[str] = []
        for tick in range(10):
            queue.enqueue(_request("local-usb-mic", f"local-{tick}"), now=float(tick))
            popped = queue.pop_next(now=float(tick))
            dispatched.append(popped.prompt_text)
            if popped.prompt_text == "remote":
                break

        self.assertIn("remote", dispatched)

    def test_empty_queue_returns_none(self) -> None:
        queue = VoiceRequestQueue()

        self.assertFalse(queue.has_pending())
        self.assertIsNone(queue.pop_next(now=0.0))

    def test_clear_removes_pending_items(self) -> None:
        queue = VoiceRequestQueue()
        queue.enqueue(_request("node-1", "one"), now=0.0)
        queue.enqueue(_request("node-2", "two"), now=0.0)

        queue.clear()

        self.assertEqual(len(queue), 0)
        self.assertFalse(queue.has_pending())


if __name__ == "__main__":
    unittest.main()
