from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

TransactionKind = Literal["expense", "income"]
RecurringIntervalUnit = Literal["days", "weeks", "months", "years"]


@dataclass(slots=True)
class Transaction:
    id: int | None
    kind: TransactionKind
    amount: float
    category: str
    description: str
    occurred_on: date
    created_at: datetime | None = None

    @property
    def signed_amount(self) -> float:
        return -self.amount if self.kind == "expense" else self.amount


@dataclass(slots=True)
class Category:
    id: int | None
    name: str
    kind: TransactionKind


@dataclass(slots=True)
class RecurringItem:
    id: int | None
    kind: TransactionKind
    amount: float
    category: str
    description: str
    interval_count: int
    interval_unit: RecurringIntervalUnit
    start_on: date
    next_run_on: date
    last_run_on: date | None = None
    is_active: bool = True

    @property
    def cadence_label(self) -> str:
        return f"Every {self.interval_count} month{'s' if self.interval_count != 1 else ''}"


@dataclass(slots=True)
class Budget:
    id: int | None
    year: int
    month: int
    category: str
    kind: TransactionKind
    budgeted_amount: float
    actual_spent: float = 0.0
    notes: str = ""

    @property
    def remaining(self) -> float:
        return self.budgeted_amount - self.actual_spent

    @property
    def budget_percentage(self) -> float:
        if self.budgeted_amount <= 0:
            return 0.0
        return (self.actual_spent / self.budgeted_amount) * 100


@dataclass(slots=True)
class SummarySnapshot:
    income_total: float = 0.0
    expense_total: float = 0.0
    net_total: float = 0.0
    transaction_count: int = 0
    top_categories: list[tuple[str, float]] = field(default_factory=list)


@dataclass(slots=True)
class AssistantResult:
    reply: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    applied_actions: list[str] = field(default_factory=list)
    display_tables: list[dict[str, Any]] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)
