from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import date, datetime
from calendar import monthrange
import sqlite3

from finance_app.models import RecurringItem


ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection] | Iterator[sqlite3.Connection]]
EnsureCategoryProvider = Callable[[str, str], None]
MonthBoundsProvider = Callable[[int, int], tuple[date, date]]


class RecurringRepository:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        ensure_category_provider: EnsureCategoryProvider,
        month_bounds_provider: MonthBoundsProvider,
    ) -> None:
        self._connection_factory = connection_factory
        self._ensure_category = ensure_category_provider
        self._month_bounds = month_bounds_provider

    def add_recurring_item(
        self,
        kind: str,
        amount: float,
        category: str,
        description: str,
        interval_count: int,
        interval_unit: str,
        start_on: date | None = None,
        is_active: bool = True,
    ) -> int:
        del interval_unit
        start_date = start_on or date.today()
        self._ensure_category(category, kind)

        with self._connection_factory() as connection:
            cursor = connection.execute(
                """
                INSERT INTO recurring_items (
                    kind, amount, category, description, interval_count, interval_unit,
                    start_on, next_run_on, last_run_on, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    float(amount),
                    category.strip(),
                    description.strip(),
                    int(interval_count),
                    "months",
                    start_date.isoformat(),
                    start_date.isoformat(),
                    None,
                    1 if is_active else 0,
                ),
            )
            return int(cursor.lastrowid)

    def list_recurring_items(self, active_only: bool = False) -> list[RecurringItem]:
        query = (
            "SELECT id, kind, amount, category, description, interval_count, interval_unit, "
            "start_on, next_run_on, last_run_on, is_active FROM recurring_items"
        )
        parameters: tuple[object, ...] = ()
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY is_active DESC, next_run_on ASC, id DESC"

        with self._connection_factory() as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [
            RecurringItem(
                id=row["id"],
                kind=row["kind"],
                amount=float(row["amount"]),
                category=row["category"],
                description=row["description"],
                interval_count=int(row["interval_count"]),
                interval_unit="months",
                start_on=datetime.strptime(row["start_on"], "%Y-%m-%d").date(),
                next_run_on=datetime.strptime(row["next_run_on"], "%Y-%m-%d").date(),
                last_run_on=datetime.strptime(row["last_run_on"], "%Y-%m-%d").date()
                if row["last_run_on"]
                else None,
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    def delete_recurring_item(self, recurring_item_id: int) -> bool:
        with self._connection_factory() as connection:
            cursor = connection.execute("DELETE FROM recurring_items WHERE id = ?", (int(recurring_item_id),))
            return cursor.rowcount > 0

    def update_recurring_item(
        self,
        recurring_item_id: int,
        kind: str,
        amount: float,
        category: str,
        description: str,
        interval_count: int,
        start_on: date,
        is_active: bool = True,
    ) -> bool:
        self._ensure_category(category, kind)

        with self._connection_factory() as connection:
            cursor = connection.execute(
                """
                UPDATE recurring_items
                SET kind = ?, amount = ?, category = ?, description = ?,
                    interval_count = ?, start_on = ?, is_active = ?
                WHERE id = ?
                """,
                (
                    kind,
                    float(amount),
                    category.strip(),
                    description.strip(),
                    int(interval_count),
                    start_on.isoformat(),
                    1 if is_active else 0,
                    int(recurring_item_id),
                ),
            )
            return cursor.rowcount > 0

    def apply_due_recurring_items(self, as_of: date | None = None) -> int:
        current_date = as_of or date.today()
        generated_count = 0

        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, amount, category, description, interval_count, interval_unit,
                       start_on, next_run_on, last_run_on, is_active
                FROM recurring_items
                WHERE is_active = 1 AND next_run_on <= ?
                ORDER BY next_run_on ASC, id ASC
                """,
                (current_date.isoformat(),),
            ).fetchall()

            for row in rows:
                next_run_on = datetime.strptime(row["next_run_on"], "%Y-%m-%d").date()
                interval_count = int(row["interval_count"])
                last_run_on: date | None = datetime.strptime(row["last_run_on"], "%Y-%m-%d").date() if row["last_run_on"] else None

                while next_run_on <= current_date:
                    connection.execute(
                        """
                        INSERT INTO transactions (kind, amount, category, description, occurred_on)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            row["kind"],
                            float(row["amount"]),
                            row["category"],
                            row["description"],
                            next_run_on.isoformat(),
                        ),
                    )
                    generated_count += 1
                    last_run_on = next_run_on
                    next_run_on = self._advance_months(next_run_on, interval_count)

                connection.execute(
                    """
                    UPDATE recurring_items
                    SET last_run_on = ?, next_run_on = ?
                    WHERE id = ?
                    """,
                    (
                        last_run_on.isoformat() if last_run_on else None,
                        next_run_on.isoformat(),
                        row["id"],
                    ),
                )

        return generated_count

    def get_recurring_totals_for_month(self, year: int, month: int) -> tuple[float, float]:
        self.apply_due_recurring_items()
        start_on, end_on = self._month_bounds(year, month)

        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT kind, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE kind IN ('income', 'expense') AND occurred_on BETWEEN ? AND ?
                GROUP BY kind
                """,
                (start_on.isoformat(), end_on.isoformat()),
            ).fetchall()

        income_total = 0.0
        expense_total = 0.0
        for row in rows:
            if row["kind"] == "income":
                income_total = float(row["total"])
            elif row["kind"] == "expense":
                expense_total = float(row["total"])

        return income_total, expense_total

    def get_projected_recurring_totals_for_month(self, year: int, month: int) -> tuple[float, float]:
        income_total = 0.0
        expense_total = 0.0
        start_on, end_on = self._month_bounds(year, month)

        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, amount, category, description, interval_count,
                       start_on, next_run_on, is_active
                FROM recurring_items
                WHERE is_active = 1
                ORDER BY kind DESC, category ASC
                """
            ).fetchall()

        for row in rows:
            item_start_on = datetime.strptime(row["start_on"], "%Y-%m-%d").date()
            if item_start_on > end_on:
                continue

            test_date = item_start_on
            interval_count = int(row["interval_count"])
            while test_date < start_on:
                test_date = self._advance_months(test_date, interval_count)

            if test_date <= end_on:
                amount = float(row["amount"])
                if row["kind"] == "income":
                    income_total += amount
                elif row["kind"] == "expense":
                    expense_total += amount

        return income_total, expense_total

    def _advance_months(self, value: date, interval_count: int) -> date:
        month_index = value.month - 1 + interval_count
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)
