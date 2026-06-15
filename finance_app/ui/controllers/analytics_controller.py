from __future__ import annotations

from finance_app.storage import FinanceRepository


class AnalyticsController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def snapshot_for_month(self, year: int, month: int):
        return self._repository.snapshot_for_month(year, month)

    def daily_totals_for_month(self, year: int, month: int):
        return self._repository.daily_totals_for_month(year, month)

    def expense_breakdown_for_month(self, year: int, month: int):
        return self._repository.expense_breakdown_for_month(year, month)

    def monthly_history(self, year: int, month: int, months: int = 6):
        return self._repository.monthly_history(year, month, months=months)
