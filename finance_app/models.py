from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

TransactionKind = Literal["expense", "income"]
RecurringIntervalUnit = Literal["days", "weeks", "months", "years"]
AssetType = Literal["house", "investment"]
ExpenseAllocationType = Literal["mortgage", "principal"]


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
class Asset:
    id: int | None
    name: str
    asset_type: AssetType
    house_value: float = 0.0
    current_principal: float = 0.0
    interest_rate_percent: float = 0.0
    total_mortgage_years: float = 30.0
    loan_start_on: date | None = None
    escrow_amount: float = 0.0
    house_base_total_paid: float = 0.0
    house_base_interest_paid: float = 0.0
    house_base_principal_paid: float = 0.0
    investment_worth: float = 0.0
    base_total_invested: float = 0.0
    notes: str = ""

    @property
    def net_worth(self) -> float:
        if self.asset_type == "house":
            return self.house_value - self.current_principal
        return self.investment_worth


@dataclass(slots=True)
class PairedRemoteDevice:
    """Paired remote voice device saved after successful pairing."""

    id: int | None
    source_id: str
    device_name: str
    host_ip: str
    port: int
    role: str
    protocol_version: str
    paired_at: datetime
    last_connected_at: datetime | None = None
    is_active: bool = True


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
