from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from finance_app.models import Asset
from finance_app.models import SummarySnapshot


@dataclass(slots=True)
class ChartDailyPoint:
    occurred_on: date
    income: float
    expense: float
    net: float


@dataclass(slots=True)
class ChartMonthlyPoint:
    year: int
    month: int
    income: float
    expense: float
    net: float


@dataclass(slots=True)
class ChartCategoryPoint:
    category: str
    amount: float


@dataclass(slots=True)
class CashflowChartsPayload:
    year: int
    month: int
    snapshot: SummarySnapshot
    daily_points: list[ChartDailyPoint] = field(default_factory=list)
    monthly_points: list[ChartMonthlyPoint] = field(default_factory=list)
    expense_breakdown: list[ChartCategoryPoint] = field(default_factory=list)


@dataclass(slots=True)
class PositionMonthlyPoint:
    year: int
    month: int
    estimated_net_worth: float
    estimated_total_debt: float
    income: float
    expense: float
    net_income: float
    savings_rate: float


@dataclass(slots=True)
class DebtCompositionPoint:
    label: str
    amount: float


@dataclass(slots=True)
class PositionChartsPayload:
    year: int
    month: int
    total_net_worth: float
    total_debt: float
    total_asset_value: float
    monthly_points: list[PositionMonthlyPoint] = field(default_factory=list)
    debt_composition: list[DebtCompositionPoint] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
