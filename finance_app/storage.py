from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime, timedelta
from contextlib import contextmanager
from calendar import monthrange
from pathlib import Path
from typing import Iterator

from finance_app.config import DEFAULT_CATEGORY_SEEDS, DEFAULT_DB_PATH
from finance_app.models import Budget, Category, RecurringItem, SummarySnapshot, Transaction


class FinanceRepository:
    def __init__(self, database_path: Path = DEFAULT_DB_PATH) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('expense', 'income')),
                    UNIQUE(name, kind)
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('expense', 'income')),
                    amount REAL NOT NULL CHECK(amount >= 0),
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    occurred_on TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS recurring_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('expense', 'income')),
                    amount REAL NOT NULL CHECK(amount >= 0),
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    interval_count INTEGER NOT NULL CHECK(interval_count > 0),
                    interval_unit TEXT NOT NULL CHECK(interval_unit IN ('days', 'weeks', 'months', 'years')),
                    start_on TEXT NOT NULL,
                    next_run_on TEXT NOT NULL,
                    last_run_on TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    year INTEGER NOT NULL,
                    month INTEGER NOT NULL CHECK(month >= 1 AND month <= 12),
                    category TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('expense', 'income')),
                    budgeted_amount REAL NOT NULL CHECK(budgeted_amount >= 0),
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(year, month, category, kind)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

        for category_name, category_kind in DEFAULT_CATEGORY_SEEDS:
            self.ensure_category(category_name, category_kind)

        self._rename_category("Rent", "Mortgage", "expense")

    def _rename_category(self, old_name: str, new_name: str, kind: str) -> None:
        old_clean = old_name.strip()
        new_clean = new_name.strip()
        if not old_clean or not new_clean or old_clean == new_clean:
            return

        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO categories (name, kind) VALUES (?, ?)",
                (new_clean, kind),
            )
            connection.execute(
                "UPDATE transactions SET category = ? WHERE category = ? AND kind = ?",
                (new_clean, old_clean, kind),
            )
            connection.execute(
                "UPDATE recurring_items SET category = ? WHERE category = ? AND kind = ?",
                (new_clean, old_clean, kind),
            )
            connection.execute(
                "DELETE FROM categories WHERE name = ? AND kind = ?",
                (old_clean, kind),
            )

    def ensure_category(self, name: str, kind: str) -> None:
        cleaned_name = name.strip()
        if not cleaned_name:
            return

        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO categories (name, kind) VALUES (?, ?)",
                (cleaned_name, kind),
            )

    def list_categories(self, kind: str | None = None) -> list[Category]:
        query = "SELECT id, name, kind FROM categories"
        parameters: tuple[str, ...] = ()
        if kind:
            query += " WHERE kind = ?"
            parameters = (kind,)
        query += " ORDER BY kind, name"

        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [Category(id=row["id"], name=row["name"], kind=row["kind"]) for row in rows]

    def delete_category(self, category_name: str, kind: str) -> bool:
        """Delete a category. Returns True if successful.
        
        Note: Safe to call even if the category is used in transactions.
        Only deletes from the categories table.
        """
        cleaned_name = category_name.strip()
        if not cleaned_name:
            return False

        with self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM categories WHERE name = ? AND kind = ?",
                (cleaned_name, kind),
            )
            return cursor.rowcount > 0

    def change_transaction_category(
        self,
        from_category: str,
        to_category: str,
        description_filter: str | None = None,
    ) -> int:
        """Change category on existing transactions.
        
        Args:
            from_category: Current category name to change from
            to_category: Target category name to change to
            description_filter: Optional substring to filter transactions by description (case-insensitive)
        
        Returns:
            Count of transactions that were reassigned
        """
        from_cat = from_category.strip()
        to_cat = to_category.strip()

        if not from_cat or not to_cat:
            return 0

        with self._connection() as connection:
            if description_filter:
                filter_str = f"%{description_filter.strip()}%"
                cursor = connection.execute(
                    "UPDATE transactions SET category = ? WHERE category = ? AND LOWER(description) LIKE LOWER(?)",
                    (to_cat, from_cat, filter_str),
                )
            else:
                cursor = connection.execute(
                    "UPDATE transactions SET category = ? WHERE category = ?",
                    (to_cat, from_cat),
                )
            return cursor.rowcount

    def change_recurring_category(
        self,
        from_category: str,
        to_category: str,
        description_filter: str | None = None,
    ) -> int:
        """Change category on existing recurring items.

        Args:
            from_category: Current category name to change from
            to_category: Target category name to change to
            description_filter: Optional substring to filter by description (case-insensitive)

        Returns:
            Count of recurring items that were reassigned
        """
        from_cat = from_category.strip()
        to_cat = to_category.strip()

        if not from_cat or not to_cat:
            return 0

        # Recurring category reassignment is currently intended for expense categories.
        self.ensure_category(to_cat, "expense")

        with self._connection() as connection:
            if description_filter:
                filter_str = f"%{description_filter.strip()}%"
                cursor = connection.execute(
                    "UPDATE recurring_items SET category = ? WHERE category = ? AND LOWER(description) LIKE LOWER(?)",
                    (to_cat, from_cat, filter_str),
                )
            else:
                cursor = connection.execute(
                    "UPDATE recurring_items SET category = ? WHERE category = ?",
                    (to_cat, from_cat),
                )
            return cursor.rowcount

    def sync_recurring_with_transactions(self) -> dict[str, int]:
        """Sync all recurring items with their transactions.
        
        For each recurring item, updates all transactions with matching description
        to use the recurring item's current category.
        
        Returns dict with:
            - "total_synced": total transactions updated
            - "recurring_items_processed": number of recurring items checked
        """
        recurring_items = self.list_recurring_items(active_only=False)
        total_synced = 0
        
        for item in recurring_items:
            # Find all transactions with matching description
            with self._connection() as connection:
                cursor = connection.execute(
                    """
                    SELECT COUNT(*) as count FROM transactions 
                    WHERE description = ? AND category != ? AND kind = ?
                    """,
                    (item.description, item.category, item.kind),
                )
                result = cursor.fetchone()
                mismatch_count = result["count"] if result else 0
                
                if mismatch_count > 0:
                    # Update all transactions with this description to match the recurring item's category
                    cursor = connection.execute(
                        """
                        UPDATE transactions 
                        SET category = ? 
                        WHERE description = ? AND kind = ?
                        """,
                        (item.category, item.description, item.kind),
                    )
                    total_synced += cursor.rowcount
        
        return {
            "total_synced": total_synced,
            "recurring_items_processed": len(recurring_items),
        }

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        """Get a setting value. Returns None if key does not exist (or default if provided)."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value. Creates or updates as needed."""
        cleaned_key = key.strip()
        if not cleaned_key:
            return

        with self._connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (cleaned_key, value),
            )

    def add_transaction(
        self,
        kind: str,
        amount: float,
        category: str,
        description: str,
        occurred_on: date | None = None,
    ) -> int:
        occurred_date = occurred_on or date.today()
        self.ensure_category(category, kind)

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO transactions (kind, amount, category, description, occurred_on)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    float(amount),
                    category.strip(),
                    description.strip(),
                    occurred_date.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def add_expense(
        self,
        amount: float,
        category: str,
        description: str,
        occurred_on: date | None = None,
    ) -> int:
        return self.add_transaction("expense", amount, category, description, occurred_on)

    def add_income(
        self,
        amount: float,
        category: str,
        description: str,
        occurred_on: date | None = None,
    ) -> int:
        return self.add_transaction("income", amount, category, description, occurred_on)

    def delete_transaction(self, transaction_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (int(transaction_id),))
            return cursor.rowcount > 0

    def _month_bounds(self, year: int, month: int) -> tuple[date, date]:
        start_on = date(year, month, 1)
        end_day = monthrange(year, month)[1]
        end_on = date(year, month, end_day)
        return start_on, end_on

    def _shift_month(self, year: int, month: int, offset: int) -> tuple[int, int]:
        absolute_month = (year * 12) + (month - 1) + offset
        shifted_year = absolute_month // 12
        shifted_month = absolute_month % 12 + 1
        return shifted_year, shifted_month

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
        start_date = start_on or date.today()
        self.ensure_category(category, kind)

        with self._connection() as connection:
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

        with self._connection() as connection:
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
        """Delete a recurring item by ID."""
        with self._connection() as connection:
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
        """Update a recurring item. Returns True if successful."""
        self.ensure_category(category, kind)

        with self._connection() as connection:
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

        with self._connection() as connection:
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

    def _advance_months(self, value: date, interval_count: int) -> date:
        month_index = value.month - 1 + interval_count
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)

    def list_transactions(self, limit: int = 100) -> list[Transaction]:
        self.apply_due_recurring_items()

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, amount, category, description, occurred_on, created_at
                FROM transactions
                ORDER BY occurred_on DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            Transaction(
                id=row["id"],
                kind=row["kind"],
                amount=float(row["amount"]),
                category=row["category"],
                description=row["description"],
                occurred_on=datetime.strptime(row["occurred_on"], "%Y-%m-%d").date(),
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )
            for row in rows
        ]

    def list_transactions_for_month(self, year: int, month: int, limit: int = 100) -> list[Transaction]:
        self.apply_due_recurring_items()
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, amount, category, description, occurred_on, created_at
                FROM transactions
                WHERE occurred_on BETWEEN ? AND ?
                ORDER BY occurred_on DESC, id DESC
                LIMIT ?
                """,
                (start_on.isoformat(), end_on.isoformat(), limit),
            ).fetchall()

        return [
            Transaction(
                id=row["id"],
                kind=row["kind"],
                amount=float(row["amount"]),
                category=row["category"],
                description=row["description"],
                occurred_on=datetime.strptime(row["occurred_on"], "%Y-%m-%d").date(),
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )
            for row in rows
        ]

    def daily_totals_for_month(self, year: int, month: int) -> list[tuple[date, float, float, float]]:
        self.apply_due_recurring_items()
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
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
        self.apply_due_recurring_items()
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
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
        self.apply_due_recurring_items()

        with self._connection() as connection:
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
        self.apply_due_recurring_items()
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
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

    def get_recurring_totals_for_month(self, year: int, month: int) -> tuple[float, float]:
        """Returns (total_income, total_expense) from recurring items that occur in the given month."""
        self.apply_due_recurring_items()
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
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
        """Returns projected (total_income, total_expense) from ALL recurring items that will occur in the month.
        
        Unlike get_recurring_totals_for_month which only counts processed transactions,
        this shows what WILL occur based on recurring item schedules, accurate for budget planning.
        """
        income_total = 0.0
        expense_total = 0.0
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
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
            
            # Check if this recurring item occurs in the target month
            if item_start_on > end_on:
                # Item hasn't started yet
                continue
            
            # Calculate which date it would run in the target month
            test_date = item_start_on
            interval_count = int(row["interval_count"])
            
            # Fast-forward to the target month
            while test_date < start_on:
                test_date = self._advance_months(test_date, interval_count)
            
            # If it falls within this month, add it
            if test_date <= end_on:
                amount = float(row["amount"])
                if row["kind"] == "income":
                    income_total += amount
                elif row["kind"] == "expense":
                    expense_total += amount

        return income_total, expense_total

    def add_or_update_budget(
        self, year: int, month: int, category: str, kind: str, budgeted_amount: float, notes: str = ""
    ) -> int:
        """Add or update a budget for a specific month/category."""
        self.ensure_category(category, kind)
        cleaned_category = category.strip()
        cleaned_notes = notes.strip()

        with self._connection() as connection:
            # Try to update first
            cursor = connection.execute(
                """
                UPDATE budgets
                SET budgeted_amount = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE year = ? AND month = ? AND category = ? AND kind = ?
                """,
                (float(budgeted_amount), cleaned_notes, int(year), int(month), cleaned_category, kind),
            )

            if cursor.rowcount > 0:
                # Successfully updated, fetch the id
                result = connection.execute(
                    "SELECT id FROM budgets WHERE year = ? AND month = ? AND category = ? AND kind = ?",
                    (int(year), int(month), cleaned_category, kind),
                ).fetchone()
                return int(result["id"])
            else:
                # Insert new
                cursor = connection.execute(
                    """
                    INSERT INTO budgets (year, month, category, kind, budgeted_amount, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (int(year), int(month), cleaned_category, kind, float(budgeted_amount), cleaned_notes),
                )
                return int(cursor.lastrowid)

    def delete_budget(self, budget_id: int) -> bool:
        """Delete a budget entry."""
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM budgets WHERE id = ?", (int(budget_id),))
            return cursor.rowcount > 0

    def list_budgets_for_month(self, year: int, month: int, kind: str | None = None) -> list[Budget]:
        """Get all budgets for a specific month, optionally filtered by kind."""
        query = "SELECT id, year, month, category, kind, budgeted_amount, notes FROM budgets WHERE year = ? AND month = ?"
        parameters: list[object] = [int(year), int(month)]

        if kind:
            query += " AND kind = ?"
            parameters.append(kind)

        query += " ORDER BY kind DESC, category ASC"

        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()

        budgets = []
        for row in rows:
            actual_spent = self._get_actual_spent_for_category(int(year), int(month), row["category"], row["kind"])
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

    def _get_actual_spent_for_category(self, year: int, month: int, category: str, kind: str) -> float:
        """Get actual spending/income for a specific category in a month."""
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
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
        """Get recurring items that would occur in the given month."""
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

        # Calculate which items would run in the target month
        start_on, end_on = self._month_bounds(year, month)

        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()

        matching_items = []
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

            # Check if this item would occur in the target month
            # It occurs if start_on is before or during the month AND next_run_on hasn't passed significantly
            if item.start_on <= end_on:
                # Calculate what the next_run_on would be for this month
                test_date = item.start_on
                while test_date < start_on:
                    test_date = self._advance_months(test_date, item.interval_count)
                if test_date <= end_on:
                    matching_items.append(item)

        return matching_items

    # ------------------------------------------------------------------
    # CSV Import / Export
    # ------------------------------------------------------------------

    def export_to_csv(self, directory: str | Path) -> dict[str, int]:
        """Export all data to CSV files in the given directory.

        Returns a dict mapping table name to row count exported.
        """
        output_dir = Path(directory)
        output_dir.mkdir(parents=True, exist_ok=True)
        counts: dict[str, int] = {}

        # categories.csv
        categories = self.list_categories()
        with open(output_dir / "categories.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "kind"])
            writer.writeheader()
            for c in categories:
                writer.writerow({"name": c.name, "kind": c.kind})
        counts["categories"] = len(categories)

        # transactions.csv
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT kind, amount, category, description, occurred_on FROM transactions ORDER BY occurred_on ASC, id ASC"
            ).fetchall()
        with open(output_dir / "transactions.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["kind", "amount", "category", "description", "occurred_on"])
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        counts["transactions"] = len(rows)

        # recurring_items.csv
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT kind, amount, category, description, interval_count, interval_unit, "
                "start_on, next_run_on, last_run_on, is_active FROM recurring_items ORDER BY id ASC"
            ).fetchall()
        with open(output_dir / "recurring_items.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["kind", "amount", "category", "description", "interval_count",
                            "interval_unit", "start_on", "next_run_on", "last_run_on", "is_active"],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        counts["recurring_items"] = len(rows)

        # budgets.csv
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT year, month, category, kind, budgeted_amount, notes FROM budgets ORDER BY year ASC, month ASC, category ASC"
            ).fetchall()
        with open(output_dir / "budgets.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["year", "month", "category", "kind", "budgeted_amount", "notes"])
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        counts["budgets"] = len(rows)

        return counts

    def import_from_csv(self, directory: str | Path, clear_first: bool = False) -> dict[str, int]:
        """Import data from CSV files in the given directory.

        Args:
            directory: Path containing categories.csv, transactions.csv,
                       recurring_items.csv, and/or budgets.csv.
            clear_first: If True, wipe all existing data before importing.

        Returns a dict mapping table name to row count imported.
        """
        input_dir = Path(directory)
        counts: dict[str, int] = {}

        if clear_first:
            with self._connection() as conn:
                conn.execute("DELETE FROM budgets")
                conn.execute("DELETE FROM recurring_items")
                conn.execute("DELETE FROM transactions")
                conn.execute("DELETE FROM categories")

        # categories.csv
        cat_file = input_dir / "categories.csv"
        if cat_file.exists():
            imported = 0
            with open(cat_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    name = row.get("name", "").strip()
                    kind = row.get("kind", "").strip()
                    if name and kind in ("expense", "income"):
                        self.ensure_category(name, kind)
                        imported += 1
            counts["categories"] = imported

        # transactions.csv
        tx_file = input_dir / "transactions.csv"
        if tx_file.exists():
            imported = 0
            with open(tx_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        occurred = date.fromisoformat(row["occurred_on"].strip())
                        self.add_transaction(
                            kind=row["kind"].strip(),
                            amount=float(row["amount"]),
                            category=row["category"].strip(),
                            description=row["description"].strip(),
                            occurred_on=occurred,
                        )
                        imported += 1
                    except (KeyError, ValueError):
                        continue
            counts["transactions"] = imported

        # recurring_items.csv
        ri_file = input_dir / "recurring_items.csv"
        if ri_file.exists():
            imported = 0
            with open(ri_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        start = date.fromisoformat(row["start_on"].strip())
                        next_run = date.fromisoformat(row["next_run_on"].strip())
                        is_active = str(row.get("is_active", "1")).strip() in ("1", "True", "true")
                        with self._connection() as conn:
                            conn.execute(
                                """
                                INSERT INTO recurring_items
                                    (kind, amount, category, description, interval_count,
                                     interval_unit, start_on, next_run_on, last_run_on, is_active)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    row["kind"].strip(),
                                    float(row["amount"]),
                                    row["category"].strip(),
                                    row["description"].strip(),
                                    int(row["interval_count"]),
                                    row.get("interval_unit", "months").strip(),
                                    start.isoformat(),
                                    next_run.isoformat(),
                                    row.get("last_run_on", "").strip() or None,
                                    1 if is_active else 0,
                                ),
                            )
                        self.ensure_category(row["category"].strip(), row["kind"].strip())
                        imported += 1
                    except (KeyError, ValueError):
                        continue
            counts["recurring_items"] = imported

        # budgets.csv
        bud_file = input_dir / "budgets.csv"
        if bud_file.exists():
            imported = 0
            with open(bud_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        self.add_or_update_budget(
                            year=int(row["year"]),
                            month=int(row["month"]),
                            category=row["category"].strip(),
                            kind=row["kind"].strip(),
                            budgeted_amount=float(row["budgeted_amount"]),
                            notes=row.get("notes", "").strip(),
                        )
                        imported += 1
                    except (KeyError, ValueError):
                        continue
            counts["budgets"] = imported

        return counts
