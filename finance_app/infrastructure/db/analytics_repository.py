from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, timedelta
import sqlite3

from finance_app.models import SummarySnapshot


ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection]]
MonthBoundsProvider = Callable[[int, int], tuple[date, date]]
ShiftMonthProvider = Callable[[int, int, int], tuple[int, int]]


class AnalyticsRepository:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        month_bounds_provider: MonthBoundsProvider,
        shift_month_provider: ShiftMonthProvider,
    ) -> None:
        self._connection_factory = connection_factory
        self._month_bounds = month_bounds_provider
        self._shift_month = shift_month_provider

    def daily_totals_for_month(self, year: int, month: int) -> list[tuple[date, float, float, float]]:
        start_on, end_on = self._month_bounds(year, month)

        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT occurred_on,
                       COALESCE(SUM(CASE WHEN kind = 'income' THEN amount ELSE 0 END), 0) AS income_total,
                       COALESCE(SUM(CASE WHEN kind = 'expense' THEN amount ELSE 0 END), 0) AS expense_total
                FROM transactions
                WHERE occurred_on BETWEEN ? AND ?
                GROUP BY occurred_on
                ORDER BY occurred_on ASC
                """,
                (start_on.isoformat(), end_on.isoformat()),
            ).fetchall()

        totals_by_day = {
            row["occurred_on"]: (float(row["income_total"]), float(row["expense_total"]))
            for row in rows
        }

        daily_totals: list[tuple[date, float, float, float]] = []
        current_day = start_on
        while current_day <= end_on:
            income_total, expense_total = totals_by_day.get(current_day.isoformat(), (0.0, 0.0))
            daily_totals.append((current_day, income_total, expense_total, income_total - expense_total))
            current_day += timedelta(days=1)

        return daily_totals

    def expense_breakdown_for_month(self, year: int, month: int) -> list[tuple[str, float]]:
        start_on, end_on = self._month_bounds(year, month)

        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT category, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE kind = 'expense' AND occurred_on BETWEEN ? AND ?
                GROUP BY category
                ORDER BY total DESC, category ASC
                """,
                (start_on.isoformat(), end_on.isoformat()),
            ).fetchall()

        return [(row["category"], float(row["total"])) for row in rows]

    def snapshot(self) -> SummarySnapshot:
        with self._connection_factory() as connection:
            totals = connection.execute(
                """
                SELECT kind, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                GROUP BY kind
                """
            ).fetchall()

            category_rows = connection.execute(
                """
                SELECT category, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE kind = 'expense'
                GROUP BY category
                ORDER BY total DESC, category ASC
                LIMIT 5
                """
            ).fetchall()

            transaction_count = connection.execute("SELECT COUNT(*) AS count FROM transactions").fetchone()["count"]

        income_total = 0.0
        expense_total = 0.0
        for row in totals:
            if row["kind"] == "income":
                income_total = float(row["total"])
            elif row["kind"] == "expense":
                expense_total = float(row["total"])

        return SummarySnapshot(
            income_total=income_total,
            expense_total=expense_total,
            net_total=income_total - expense_total,
            transaction_count=int(transaction_count),
            top_categories=[(row["category"], float(row["total"])) for row in category_rows],
        )

    def snapshot_for_month(self, year: int, month: int) -> SummarySnapshot:
        start_on, end_on = self._month_bounds(year, month)

        with self._connection_factory() as connection:
            totals = connection.execute(
                """
                SELECT kind, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE occurred_on BETWEEN ? AND ?
                GROUP BY kind
                """,
                (start_on.isoformat(), end_on.isoformat()),
            ).fetchall()

            category_rows = connection.execute(
                """
                SELECT category, COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE kind = 'expense' AND occurred_on BETWEEN ? AND ?
                GROUP BY category
                ORDER BY total DESC, category ASC
                LIMIT 5
                """,
                (start_on.isoformat(), end_on.isoformat()),
            ).fetchall()

            transaction_count = connection.execute(
                "SELECT COUNT(*) AS count FROM transactions WHERE occurred_on BETWEEN ? AND ?",
                (start_on.isoformat(), end_on.isoformat()),
            ).fetchone()["count"]

        income_total = 0.0
        expense_total = 0.0
        for row in totals:
            if row["kind"] == "income":
                income_total = float(row["total"])
            elif row["kind"] == "expense":
                expense_total = float(row["total"])

        return SummarySnapshot(
            income_total=income_total,
            expense_total=expense_total,
            net_total=income_total - expense_total,
            transaction_count=int(transaction_count),
            top_categories=[(row["category"], float(row["total"])) for row in category_rows],
        )

    def monthly_history(self, reference_year: int, reference_month: int, months: int = 6) -> list[tuple[int, int, float, float, float]]:
        history: list[tuple[int, int, float, float, float]] = []
        for offset in range(months - 1, -1, -1):
            year, month = self._shift_month(reference_year, reference_month, -offset)
            snapshot = self.snapshot_for_month(year, month)
            history.append((year, month, snapshot.income_total, snapshot.expense_total, snapshot.net_total))
        return history

    def compute_income_series(self, reference_year: int, reference_month: int, months: int = 6) -> list[float]:
        values: list[float] = []
        for offset in range(months - 1, -1, -1):
            year, month = self._shift_month(reference_year, reference_month, -offset)
            snapshot = self.snapshot_for_month(year, month)
            values.append(float(snapshot.income_total))
        return values

    def list_monthly_category_spend(
        self,
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
        kind: str = "expense",
    ) -> dict[str, list[tuple[int, int, float]]]:
        start_on, _ = self._month_bounds(start_year, start_month)
        _, end_on = self._month_bounds(end_year, end_month)

        with self._connection_factory() as connection:
            rows = connection.execute(
                """
                SELECT
                    CAST(strftime('%Y', occurred_on) AS INTEGER) AS year,
                    CAST(strftime('%m', occurred_on) AS INTEGER) AS month,
                    category,
                    COALESCE(SUM(amount), 0) AS total
                FROM transactions
                WHERE kind = ? AND occurred_on BETWEEN ? AND ?
                GROUP BY year, month, category
                ORDER BY year ASC, month ASC, category ASC
                """,
                (kind, start_on.isoformat(), end_on.isoformat()),
            ).fetchall()

        results: dict[str, list[tuple[int, int, float]]] = {}
        for row in rows:
            category = str(row["category"])
            series = results.setdefault(category, [])
            series.append((int(row["year"]), int(row["month"]), float(row["total"])))

        return results

    def count_full_history_months(self, reference_year: int, reference_month: int, kind: str = "expense") -> int:
        reference_start, _ = self._month_bounds(reference_year, reference_month)

        with self._connection_factory() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS month_count
                FROM (
                    SELECT strftime('%Y-%m', occurred_on) AS year_month
                    FROM transactions
                    WHERE kind = ? AND occurred_on < ?
                    GROUP BY year_month
                )
                """,
                (kind, reference_start.isoformat()),
            ).fetchone()

        return int(row["month_count"]) if row else 0

    def personal_position_history(
        self,
        reference_year: int,
        reference_month: int,
        months: int = 12,
    ) -> list[tuple[int, int, float, float, float]]:
        _, reference_end_on = self._month_bounds(reference_year, reference_month)
        history: list[tuple[int, int, float, float, float]] = []

        with self._connection_factory() as connection:
            house_row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(house_value), 0) AS total_house_value,
                    COALESCE(SUM(current_principal), 0) AS total_current_debt
                FROM assets
                WHERE asset_type = 'house'
                """
            ).fetchone()

            total_house_value = float(house_row["total_house_value"]) if house_row else 0.0
            total_current_debt = float(house_row["total_current_debt"]) if house_row else 0.0

            for offset in range(months - 1, -1, -1):
                year, month = self._shift_month(reference_year, reference_month, -offset)
                _, month_end_on = self._month_bounds(year, month)

                investment_row = connection.execute(
                    """
                    SELECT COALESCE(SUM(
                        COALESCE(
                            (
                                SELECT s.value
                                FROM asset_value_snapshots s
                                WHERE s.asset_id = a.id
                                  AND s.valued_on <= ?
                                ORDER BY s.valued_on DESC, s.id DESC
                                LIMIT 1
                            ),
                            a.investment_worth
                        )
                    ), 0) AS total_investment_value
                    FROM assets a
                    WHERE a.asset_type = 'investment'
                    """,
                    (month_end_on.isoformat(),),
                ).fetchone()

                principal_paid_after_row = connection.execute(
                    """
                    SELECT COALESCE(SUM(t.amount), 0) AS total_principal_paid_after
                    FROM transactions t
                    JOIN asset_expense_links l
                      ON l.source_type = 'transaction'
                     AND l.source_id = t.id
                    JOIN assets a
                      ON a.id = l.asset_id
                     AND a.asset_type = 'house'
                    WHERE t.kind = 'expense'
                      AND l.payment_kind = 'principal'
                      AND t.occurred_on > ?
                      AND t.occurred_on <= ?
                    """,
                    (month_end_on.isoformat(), reference_end_on.isoformat()),
                ).fetchone()

                total_investment_value = float(investment_row["total_investment_value"]) if investment_row else 0.0
                principal_paid_after = float(principal_paid_after_row["total_principal_paid_after"]) if principal_paid_after_row else 0.0
                total_debt = total_current_debt + principal_paid_after
                total_asset_value = total_house_value + total_investment_value
                net_worth = total_asset_value - total_debt

                history.append((year, month, net_worth, total_debt, total_asset_value))

        return history
