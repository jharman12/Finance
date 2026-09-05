from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

from finance_app.services.llm_service import LLMRequest

LOCAL_SOURCE_ID = "local-usb-mic"
LOCAL_PRIORITY = 10
REMOTE_PRIORITY = 6

# Priority points added per second of waiting, so remote requests cannot starve.
DEFAULT_AGE_BOOST_PER_SECOND = 1.0


def base_priority_for_source(source_id: str | None) -> int:
    cleaned = str(source_id or "").strip() or LOCAL_SOURCE_ID
    return LOCAL_PRIORITY if cleaned == LOCAL_SOURCE_ID else REMOTE_PRIORITY


@dataclass(slots=True)
class QueuedLLMRequest:
    request: LLMRequest
    base_priority: int
    enqueued_at: float
    sequence: int = field(default=0)

    def effective_priority(self, now: float, age_boost_per_second: float) -> float:
        waited = max(0.0, now - self.enqueued_at)
        return float(self.base_priority) + (waited * age_boost_per_second)


class VoiceRequestQueue:
    """Priority queue for assistant requests with age-based fairness."""

    def __init__(self, age_boost_per_second: float = DEFAULT_AGE_BOOST_PER_SECOND) -> None:
        self.age_boost_per_second = max(0.0, float(age_boost_per_second))
        self._items: list[QueuedLLMRequest] = []
        self._counter = itertools.count()

    def enqueue(self, request: LLMRequest, now: float | None = None) -> QueuedLLMRequest:
        queued = QueuedLLMRequest(
            request=request,
            base_priority=base_priority_for_source(request.source_id),
            enqueued_at=time.monotonic() if now is None else float(now),
            sequence=next(self._counter),
        )
        self._items.append(queued)
        return queued

    def pop_next(self, now: float | None = None) -> LLMRequest | None:
        if not self._items:
            return None

        current = time.monotonic() if now is None else float(now)
        best_index = 0
        best_key = self._sort_key(self._items[0], current)
        for index in range(1, len(self._items)):
            key = self._sort_key(self._items[index], current)
            if key > best_key:
                best_index = index
                best_key = key

        return self._items.pop(best_index).request

    def has_pending(self) -> bool:
        return bool(self._items)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def _sort_key(self, item: QueuedLLMRequest, now: float) -> tuple[float, int]:
        return (item.effective_priority(now, self.age_boost_per_second), -item.sequence)
