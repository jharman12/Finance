from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import date, datetime
import sqlite3

from finance_app.models import Budget, RecurringItem


ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection] | Iterator[sqlite3.Connection]]
MonthBoundsProvider = Callable[[int, int], tuple[date, date]]
AdvanceMonthsProvider = Callable[[date, int], date]
EnsureCategoryProvider = Callable[[str, str], None]


class BudgetRepository:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        month_bounds_provider: MonthBoundsProvider,
        advance_months_provider: AdvanceMonthsProvider,
        ensure_category_provider: EnsureCategoryProvider,
    ) -> None:
        self._connection_factory = connection_factory
        self._month_bounds = month_bounds_provider
        self._advance_months = advance_months_provider
        self._ensure_category = ensure_category_provider

    def add_or_update_budget(
        self,
        year: int,
        month: int,
        category: str,
        kind: str,
        budgeted_amount: float,
        notes: str = "",
    ) -> int:
        self._ensure_category(category, kind)
        cleaned_category = category.strip()
        cleaned_notes = notes.strip()

        with self._connection_factory() as connection:
            cursor = connection.execute(
                """
                UPDATE budgets
                SET budgeted_amount = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE year = ? AND month = ? AND category = ? AND kind = ?
                """,
                (float(budgeted_amount), cleaned_notes, int(year), int(month), cleaned_category, kind),
            )

            if cursor.rowcount > 0:
                result = connection.execute(
                    "SELECT id FROM budgets WHERE year = ? AND month = ? AND category = ? AND kind = ?",
                    (int(year), int(month), cleaned_category, kind),
                ).fetchone()
                return int(result["id"])

            cursor = connection.execute(
                """
                INSERT INTO budgets (year, month, category, kind, budgeted_amount, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(year), int(month), cleaned_category, kind, float(budgeted_amount), cleaned_notes),
            )
            return int(cursor.lastrowid)

    def delete_budget(self, budget_id: int) -> bool:
        with self._connection_factory() as connection:
            cursor = connection.execute("DELETE FROM budgets WHERE id = ?", (int(budget_id),))
            return cursor.rowcount > 0

    def list_budgets_for_month(self, year: int, month: int, kind: str | None = None) -> list[Budget]:
        query = "SELECT id, year, month, category, kind, budgeted_amount, notes FROM budgets WHERE year = ? AND month = ?"
        parameters: list[object] = [int(year), int(month)]

        if kind:
            query += " AND kind = ?"
            parameters.append(kind)

        query += " ORDER BY kind DESC, category ASC"

        with self._connection_factory() as connection:
            rows = connection.execute(query, parameters).fetchall()

        budgets: list[Budget] = []
        for row in rows:
            actual_spent = self.get_actual_spent_for_category(int(year), int(month), row["category"], row["kind"])
            budgets.append(
                Budget(
                    id=int(row["id"]),
                    year=int(row["year"]),
                    month=int(row["month"]),
                    category=row["category"],
                    kind=row["kind"],
                    budgeted_amount=float(row["budgeted_amount"]),
                    actual_spent=actual_spent,
                    notes=row["notes"],
                )
            )
        return budgets

    def get_actual_spent_for_category(self, year: int, month: int, category: str, kind: str) -> float:
        start_on, end_on = self._month_bounds(year, month)

        with self._connection_factory() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE kind = ? AND category = ? AND occurred_on BETWEEN ? AND ?
                """,
                (kind, category, start_on.isoformat(), end_on.isoformat()),
            ).fetchone()

        return float(row["total"]) if row else 0.0

    def get_active_recurring_items_for_month(self, year: int, month: int, kind: str | None = None) -> list[RecurringItem]:
        query = """
            SELECT id, kind, amount, category, description, interval_count, interval_unit,
                   start_on, next_run_on, last_run_on, is_active
            FROM recurring_items
            WHERE is_active = 1 AND kind IN ('income', 'expense')
        """
        parameters: list[object] = []

        if kind:
            query += " AND kind = ?"
            parameters.append(kind)

        query += " ORDER BY category ASC"

        start_on, end_on = self._month_bounds(year, month)

        with self._connection_factory() as connection:
            rows = connection.execute(query, parameters).fetchall()

        matching_items: list[RecurringItem] = []
        for row in rows:
            item = RecurringItem(
                id=int(row["id"]),
                kind=row["kind"],
                amount=float(row["amount"]),
                category=row["category"],
                description=row["description"],
                interval_count=int(row["interval_count"]),
                interval_unit="months",
                start_on=datetime.strptime(row["start_on"], "%Y-%m-%d").date(),
                next_run_on=datetime.strptime(row["next_run_on"], "%Y-%m-%d").date(),
                last_run_on=datetime.strptime(row["last_run_on"], "%Y-%m-%d").date() if row["last_run_on"] else None,
                is_active=bool(row["is_active"]),
            )

            if item.start_on <= end_on:
                test_date = item.start_on
                while test_date < start_on:
                    test_date = self._advance_months(test_date, item.interval_count)
                if test_date <= end_on:
                    matching_items.append(item)

        return matching_items
