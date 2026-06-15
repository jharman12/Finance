from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finance_app.models import Budget
from finance_app.storage import FinanceRepository


@dataclass(slots=True)
class BudgetMonthView:
    total_income: float
    recurring_expenses: float
    budgets: list[Budget]
    budgeted_discretionary: float
    actual_discretionary: float
    total_expected_spend: float
    discretionary_after_savings: float
    remaining_to_spend: float
    break_even_left_to_spend: float
    expected_net: float
    overspent_count: int
    under_budget_count: int


class BudgetController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def get_monthly_savings_goal(self, year: int, month: int, default: float = 0.0) -> float:
        return self._repository.get_monthly_savings_goal(year, month, default)

    def set_monthly_savings_goal(self, year: int, month: int, value: float) -> None:
        self._repository.set_monthly_savings_goal(year, month, value)

    def get_projected_recurring_totals_for_month(self, year: int, month: int) -> tuple[float, float]:
        return self._repository.get_projected_recurring_totals_for_month(year, month)

    def list_budgets_for_month(self, year: int, month: int, kind: str | None = None):
        return self._repository.list_budgets_for_month(year, month, kind)

    def add_or_update_budget(
        self,
        year: int,
        month: int,
        category: str,
        kind: str,
        budgeted_amount: float,
        notes: str = "",
    ) -> int:
        return self._repository.add_or_update_budget(year, month, category, kind, budgeted_amount, notes)

    def delete_budget(self, budget_id: int) -> bool:
        return self._repository.delete_budget(budget_id)

    def list_expense_categories(self):
        return self._repository.list_categories(kind="expense")

    def snapshot_for_month(self, year: int, month: int):
        return self._repository.snapshot_for_month(year, month)

    def list_budget_reallocation_audits(self, limit: int = 50) -> list[dict]:
        return self._repository.list_budget_reallocation_audits(limit=limit)

    def build_budget_month_view(self, year: int, month: int, savings_goal: float) -> BudgetMonthView:
        total_income, recurring_expenses = self._repository.get_projected_recurring_totals_for_month(year, month)
        budgets = self._repository.list_budgets_for_month(year, month, kind="expense")

        # Keep recurring auto-allocation rows separate to avoid double counting.
        discretionary_budget_rows = [b for b in budgets if b.notes != "Recurring item (auto-allocated)"]
        budgeted_discretionary = sum(b.budgeted_amount for b in discretionary_budget_rows)
        actual_discretionary = sum(b.actual_spent for b in discretionary_budget_rows)

        total_expected_spend = recurring_expenses + budgeted_discretionary
        discretionary_after_savings = total_income - savings_goal - recurring_expenses
        remaining_to_spend = discretionary_after_savings - actual_discretionary
        break_even_left_to_spend = total_income - recurring_expenses - actual_discretionary
        expected_net = total_income - recurring_expenses - budgeted_discretionary - savings_goal

        overspent_count = sum(1 for b in budgets if b.remaining < 0)
        under_budget_count = sum(1 for b in budgets if b.remaining > 0)

        return BudgetMonthView(
            total_income=total_income,
            recurring_expenses=recurring_expenses,
            budgets=budgets,
            budgeted_discretionary=budgeted_discretionary,
            actual_discretionary=actual_discretionary,
            total_expected_spend=total_expected_spend,
            discretionary_after_savings=discretionary_after_savings,
            remaining_to_spend=remaining_to_spend,
            break_even_left_to_spend=break_even_left_to_spend,
            expected_net=expected_net,
            overspent_count=overspent_count,
            under_budget_count=under_budget_count,
        )

    def export_budget_rows_for_month(self, year: int, month: int) -> list[dict[str, str]]:
        budgets = self._repository.list_budgets_for_month(year, month)
        return [
            {
                "year": str(year),
                "month": str(month),
                "category": budget.category,
                "kind": budget.kind,
                "budgeted_amount": f"{budget.budgeted_amount:.2f}",
                "notes": budget.notes,
            }
            for budget in budgets
        ]

    def import_budget_rows_for_month(
        self,
        year: int,
        month: int,
        rows: list[dict[str, Any]],
        replace_existing: bool = False,
    ) -> tuple[int, int]:
        if replace_existing:
            existing_rows = self._repository.list_budgets_for_month(year, month)
            for budget in existing_rows:
                if budget.id is not None:
                    self._repository.delete_budget(budget.id)

        imported_count = 0
        skipped_count = 0

        for row in rows:
            category = str(row.get("category", "")).strip()
            kind = str(row.get("kind", "expense")).strip().lower() or "expense"
            notes = str(row.get("notes", "")).strip()

            raw_amount = str(row.get("budgeted_amount", "")).strip().replace("$", "").replace(",", "")
            try:
                amount = float(raw_amount)
            except ValueError:
                skipped_count += 1
                continue

            if not category or amount <= 0 or kind not in ("expense", "income"):
                skipped_count += 1
                continue

            self._repository.add_or_update_budget(
                year=year,
                month=month,
                category=category,
                kind=kind,
                budgeted_amount=amount,
                notes=notes,
            )
            imported_count += 1

        return imported_count, skipped_count
