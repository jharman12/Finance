from __future__ import annotations

import csv
import json
import sqlite3
from datetime import date, datetime
from contextlib import contextmanager
from calendar import monthrange
from pathlib import Path
from typing import Iterator

from finance_app.config import DEFAULT_CATEGORY_SEEDS, DEFAULT_DB_PATH
from finance_app.infrastructure.db.analytics_repository import AnalyticsRepository
from finance_app.infrastructure.db.budget_repository import BudgetRepository
from finance_app.infrastructure.db.paired_device_repository import PairedRemoteDeviceRepository
from finance_app.infrastructure.db.recurring_repository import RecurringRepository
from finance_app.infrastructure.db.settings_repository import SettingsRepository
from finance_app.infrastructure.db.transactions_repository import TransactionsRepository
from finance_app.models import Asset, Budget, Category, PairedRemoteDevice, RecurringItem, SummarySnapshot, Transaction


class FinanceRepository:
    def __init__(self, database_path: Path = DEFAULT_DB_PATH) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_repository = SettingsRepository(self._connection)
        self._paired_device_repository = PairedRemoteDeviceRepository(self._connection)
        self._budget_repository = BudgetRepository(
            connection_factory=self._connection,
            month_bounds_provider=self._month_bounds,
            advance_months_provider=self._advance_months,
            ensure_category_provider=self.ensure_category,
        )
        self._transactions_repository = TransactionsRepository(
            connection_factory=self._connection,
            ensure_category_provider=self.ensure_category,
        )
        self._analytics_repository = AnalyticsRepository(
            connection_factory=self._connection,
            month_bounds_provider=self._month_bounds,
            shift_month_provider=self.shift_month,
        )
        self._recurring_repository = RecurringRepository(
            connection_factory=self._connection,
            ensure_category_provider=self.ensure_category,
            month_bounds_provider=self._month_bounds,
        )
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

                CREATE TABLE IF NOT EXISTS budget_reallocation_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reference_year INTEGER NOT NULL,
                    reference_month INTEGER NOT NULL CHECK(reference_month >= 1 AND reference_month <= 12),
                    target_year INTEGER NOT NULL,
                    target_month INTEGER NOT NULL CHECK(target_month >= 1 AND target_month <= 12),
                    status TEXT NOT NULL DEFAULT 'ready',
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    asset_type TEXT NOT NULL CHECK(asset_type IN ('house', 'investment')),
                    amount_invested REAL NOT NULL DEFAULT 0 CHECK(amount_invested >= 0),
                    current_value REAL NOT NULL DEFAULT 0 CHECK(current_value >= 0),
                    debt_principal REAL NOT NULL DEFAULT 0 CHECK(debt_principal >= 0),
                    rate_percent REAL NOT NULL DEFAULT 0,
                    house_value REAL NOT NULL DEFAULT 0 CHECK(house_value >= 0),
                    current_principal REAL NOT NULL DEFAULT 0 CHECK(current_principal >= 0),
                    interest_rate_percent REAL NOT NULL DEFAULT 0,
                    total_mortgage_years REAL NOT NULL DEFAULT 30 CHECK(total_mortgage_years >= 0),
                    loan_start_on TEXT,
                    escrow_amount REAL NOT NULL DEFAULT 0 CHECK(escrow_amount >= 0),
                    house_base_total_paid REAL NOT NULL DEFAULT 0 CHECK(house_base_total_paid >= 0),
                    house_base_interest_paid REAL NOT NULL DEFAULT 0 CHECK(house_base_interest_paid >= 0),
                    house_base_principal_paid REAL NOT NULL DEFAULT 0 CHECK(house_base_principal_paid >= 0),
                    investment_worth REAL NOT NULL DEFAULT 0 CHECK(investment_worth >= 0),
                    base_total_invested REAL NOT NULL DEFAULT 0 CHECK(base_total_invested >= 0),
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS asset_expense_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL CHECK(source_type IN ('transaction', 'recurring')),
                    source_id INTEGER NOT NULL,
                    payment_kind TEXT NOT NULL DEFAULT 'mortgage' CHECK(payment_kind IN ('mortgage', 'principal')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_type, source_id),
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS asset_value_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    valued_on TEXT NOT NULL,
                    value REAL NOT NULL CHECK(value >= 0),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(asset_id, valued_on),
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS paired_remote_devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL UNIQUE,
                    device_name TEXT NOT NULL,
                    host_ip TEXT NOT NULL,
                    port INTEGER NOT NULL CHECK(port > 0),
                    role TEXT NOT NULL,
                    protocol_version TEXT NOT NULL,
                    paired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_connected_at TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
                """
            )

        self._ensure_assets_schema()

        for category_name, category_kind in DEFAULT_CATEGORY_SEEDS:
            self.ensure_category(category_name, category_kind)

        self._rename_category("Rent", "Mortgage", "expense")

    def _ensure_assets_schema(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_value_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id INTEGER NOT NULL,
                    valued_on TEXT NOT NULL,
                    value REAL NOT NULL CHECK(value >= 0),
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(asset_id, valued_on),
                    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
                )
                """
            )

            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(assets)").fetchall()
            }
            link_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(asset_expense_links)").fetchall()
            }

            alter_statements: list[str] = []
            if "house_value" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN house_value REAL NOT NULL DEFAULT 0")
            if "current_principal" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN current_principal REAL NOT NULL DEFAULT 0")
            if "interest_rate_percent" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN interest_rate_percent REAL NOT NULL DEFAULT 0")
            if "total_mortgage_years" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN total_mortgage_years REAL NOT NULL DEFAULT 30")
            if "loan_start_on" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN loan_start_on TEXT")
            if "escrow_amount" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN escrow_amount REAL NOT NULL DEFAULT 0")
            if "house_base_total_paid" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN house_base_total_paid REAL NOT NULL DEFAULT 0")
            if "house_base_interest_paid" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN house_base_interest_paid REAL NOT NULL DEFAULT 0")
            if "house_base_principal_paid" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN house_base_principal_paid REAL NOT NULL DEFAULT 0")
            if "investment_worth" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN investment_worth REAL NOT NULL DEFAULT 0")
            if "base_total_invested" not in columns:
                alter_statements.append("ALTER TABLE assets ADD COLUMN base_total_invested REAL NOT NULL DEFAULT 0")

            if "payment_kind" not in link_columns:
                connection.execute("ALTER TABLE asset_expense_links ADD COLUMN payment_kind TEXT NOT NULL DEFAULT 'mortgage'")

            for statement in alter_statements:
                connection.execute(statement)

            # Backfill specialized columns from legacy generic columns when present.
            connection.execute(
                """
                UPDATE assets
                SET
                    house_value = CASE WHEN house_value = 0 THEN current_value ELSE house_value END,
                    current_principal = CASE WHEN current_principal = 0 THEN debt_principal ELSE current_principal END,
                    interest_rate_percent = CASE WHEN interest_rate_percent = 0 THEN rate_percent ELSE interest_rate_percent END,
                    investment_worth = CASE WHEN investment_worth = 0 THEN current_value ELSE investment_worth END,
                    base_total_invested = CASE WHEN base_total_invested = 0 THEN amount_invested ELSE base_total_invested END
                """
            )

            link_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(asset_expense_links)").fetchall()
            }
            if "payment_kind" not in link_columns:
                connection.execute("ALTER TABLE asset_expense_links ADD COLUMN payment_kind TEXT NOT NULL DEFAULT 'mortgage'")
                connection.execute(
                    "UPDATE asset_expense_links SET payment_kind = 'mortgage' WHERE payment_kind IS NULL OR payment_kind = ''"
                )

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
        return self._settings_repository.get_setting(key, default)

    def set_setting(self, key: str, value: str) -> None:
        self._settings_repository.set_setting(key, value)

    def get_category_budget_caps_floors(self) -> dict[str, dict[str, float]]:
        return self._settings_repository.get_category_budget_caps_floors()

    def set_category_budget_caps_floors(self, caps_floors: dict[str, dict[str, float]]) -> None:
        self._settings_repository.set_category_budget_caps_floors(caps_floors)

    def get_monthly_savings_goal(self, year: int, month: int, default: float = 0.0) -> float:
        return self._settings_repository.get_monthly_savings_goal(year, month, default)

    def set_monthly_savings_goal(self, year: int, month: int, value: float) -> None:
        self._settings_repository.set_monthly_savings_goal(year, month, value)

    def save_budget_reallocation_audit(self, payload: dict) -> int:
        """Persist a generated reallocation plan/audit payload."""
        reference_year = int(payload.get("reference_year", 0) or 0)
        reference_month = int(payload.get("reference_month", 0) or 0)
        target_year = int(payload.get("target_year", 0) or 0)
        target_month = int(payload.get("target_month", 0) or 0)
        status = str(payload.get("status", "ready") or "ready")
        payload_json = json.dumps(payload)

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO budget_reallocation_audits (
                    reference_year, reference_month, target_year, target_month, status, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (reference_year, reference_month, target_year, target_month, status, payload_json),
            )
            return int(cursor.lastrowid)

    def list_budget_reallocation_audits(self, limit: int = 50) -> list[dict]:
        """List recent reallocation audits."""
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, reference_year, reference_month, target_year, target_month, status, payload_json, created_at
                FROM budget_reallocation_audits
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(max(1, limit)),),
            ).fetchall()

        results: list[dict] = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = {"raw_payload": row["payload_json"]}

            results.append(
                {
                    "id": int(row["id"]),
                    "reference_year": int(row["reference_year"]),
                    "reference_month": int(row["reference_month"]),
                    "target_year": int(row["target_year"]),
                    "target_month": int(row["target_month"]),
                    "status": row["status"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )

        return results

    def add_asset(
        self,
        name: str,
        asset_type: str,
        house_value: float = 0.0,
        current_principal: float = 0.0,
        interest_rate_percent: float = 0.0,
        total_mortgage_years: float = 30.0,
        loan_start_on: date | None = None,
        escrow_amount: float = 0.0,
        house_base_total_paid: float = 0.0,
        house_base_interest_paid: float = 0.0,
        house_base_principal_paid: float = 0.0,
        investment_worth: float = 0.0,
        base_total_invested: float = 0.0,
        notes: str = "",
    ) -> int:
        cleaned_name = name.strip()
        cleaned_type = asset_type.strip().lower()
        cleaned_notes = notes.strip()

        if not cleaned_name:
            raise ValueError("Asset name is required.")
        if cleaned_type not in ("house", "investment"):
            raise ValueError("Asset type must be 'house' or 'investment'.")
        if min(
            house_value,
            current_principal,
            house_base_total_paid,
            house_base_interest_paid,
            house_base_principal_paid,
            escrow_amount,
            investment_worth,
            base_total_invested,
        ) < 0:
            raise ValueError("Asset amounts must be non-negative.")

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO assets (
                    name, asset_type, house_value, current_principal, interest_rate_percent,
                    total_mortgage_years, loan_start_on, escrow_amount, house_base_total_paid, house_base_interest_paid,
                    house_base_principal_paid, investment_worth, base_total_invested,
                    amount_invested, current_value, debt_principal, rate_percent, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cleaned_name,
                    cleaned_type,
                    float(house_value),
                    float(current_principal),
                    float(interest_rate_percent),
                    float(total_mortgage_years),
                    loan_start_on.isoformat() if loan_start_on else None,
                    float(escrow_amount),
                    float(house_base_total_paid),
                    float(house_base_interest_paid),
                    float(house_base_principal_paid),
                    float(investment_worth),
                    float(base_total_invested),
                    float(base_total_invested),
                    float(house_value if cleaned_type == "house" else investment_worth),
                    float(current_principal),
                    float(interest_rate_percent),
                    cleaned_notes,
                ),
            )
            return int(cursor.lastrowid)

    def update_asset(
        self,
        asset_id: int,
        name: str,
        asset_type: str,
        house_value: float,
        current_principal: float,
        interest_rate_percent: float,
        total_mortgage_years: float,
        loan_start_on: date | None,
        escrow_amount: float,
        house_base_total_paid: float,
        house_base_interest_paid: float,
        house_base_principal_paid: float,
        investment_worth: float,
        base_total_invested: float,
        notes: str = "",
    ) -> bool:
        cleaned_name = name.strip()
        cleaned_type = asset_type.strip().lower()
        cleaned_notes = notes.strip()

        if not cleaned_name or cleaned_type not in ("house", "investment"):
            return False
        if min(
            house_value,
            current_principal,
            escrow_amount,
            house_base_total_paid,
            house_base_interest_paid,
            house_base_principal_paid,
            investment_worth,
            base_total_invested,
        ) < 0:
            return False

        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE assets
                SET
                    name = ?,
                    asset_type = ?,
                    house_value = ?,
                    current_principal = ?,
                    interest_rate_percent = ?,
                    total_mortgage_years = ?,
                    loan_start_on = ?,
                    escrow_amount = ?,
                    house_base_total_paid = ?,
                    house_base_interest_paid = ?,
                    house_base_principal_paid = ?,
                    investment_worth = ?,
                    base_total_invested = ?,
                    amount_invested = ?,
                    current_value = ?,
                    debt_principal = ?,
                    rate_percent = ?,
                    notes = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    cleaned_name,
                    cleaned_type,
                    float(house_value),
                    float(current_principal),
                    float(interest_rate_percent),
                    float(total_mortgage_years),
                    loan_start_on.isoformat() if loan_start_on else None,
                    float(escrow_amount),
                    float(house_base_total_paid),
                    float(house_base_interest_paid),
                    float(house_base_principal_paid),
                    float(investment_worth),
                    float(base_total_invested),
                    float(base_total_invested),
                    float(house_value if cleaned_type == "house" else investment_worth),
                    float(current_principal),
                    float(interest_rate_percent),
                    cleaned_notes,
                    int(asset_id),
                ),
            )
            return cursor.rowcount > 0

    def delete_asset(self, asset_id: int) -> bool:
        with self._connection() as connection:
            connection.execute("DELETE FROM asset_expense_links WHERE asset_id = ?", (int(asset_id),))
            connection.execute("DELETE FROM asset_value_snapshots WHERE asset_id = ?", (int(asset_id),))
            cursor = connection.execute("DELETE FROM assets WHERE id = ?", (int(asset_id),))
            return cursor.rowcount > 0

    def record_investment_value_snapshot(
        self,
        asset_id: int,
        value: float,
        valued_on: date | None = None,
        notes: str = "",
    ) -> bool:
        cleaned_value = float(value)
        if cleaned_value < 0:
            return False

        snapshot_date = valued_on or date.today()
        with self._connection() as connection:
            asset = connection.execute(
                "SELECT asset_type FROM assets WHERE id = ?",
                (int(asset_id),),
            ).fetchone()
            if asset is None or asset["asset_type"] != "investment":
                return False

            connection.execute(
                """
                INSERT INTO asset_value_snapshots (asset_id, valued_on, value, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(asset_id, valued_on)
                DO UPDATE SET value = excluded.value, notes = excluded.notes
                """,
                (int(asset_id), snapshot_date.isoformat(), cleaned_value, notes.strip()),
            )

            cursor = connection.execute(
                """
                UPDATE assets
                SET investment_worth = ?,
                    current_value = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND asset_type = 'investment'
                """,
                (cleaned_value, cleaned_value, int(asset_id)),
            )
            return cursor.rowcount > 0

    def list_asset_value_snapshots(self, asset_id: int, limit: int = 24) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, valued_on, value, notes, created_at
                FROM asset_value_snapshots
                WHERE asset_id = ?
                ORDER BY valued_on DESC, id DESC
                LIMIT ?
                """,
                (int(asset_id), int(limit)),
            ).fetchall()

        return [
            {
                "id": int(row["id"]),
                "valued_on": date.fromisoformat(row["valued_on"]),
                "value": float(row["value"]),
                "notes": row["notes"] or "",
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_asset_by_id(self, asset_id: int) -> Asset | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, name, asset_type, house_value, current_principal, interest_rate_percent,
                        total_mortgage_years, loan_start_on, escrow_amount, house_base_total_paid, house_base_interest_paid,
                      house_base_principal_paid, investment_worth, base_total_invested, notes
                FROM assets
                WHERE id = ?
                """,
                (int(asset_id),),
            ).fetchone()
        if not row:
            return None
        return Asset(
            id=int(row["id"]),
            name=row["name"],
            asset_type=row["asset_type"],
            house_value=float(row["house_value"]),
            current_principal=float(row["current_principal"]),
            interest_rate_percent=float(row["interest_rate_percent"]),
            total_mortgage_years=float(row["total_mortgage_years"]),
            loan_start_on=date.fromisoformat(row["loan_start_on"]) if row["loan_start_on"] else None,
            escrow_amount=float(row["escrow_amount"]),
            house_base_total_paid=float(row["house_base_total_paid"]),
            house_base_interest_paid=float(row["house_base_interest_paid"]),
            house_base_principal_paid=float(row["house_base_principal_paid"]),
            investment_worth=float(row["investment_worth"]),
            base_total_invested=float(row["base_total_invested"]),
            notes=row["notes"] or "",
        )

    def list_assets(self, asset_type: str | None = None) -> list[Asset]:
        query = (
            "SELECT id, name, asset_type, house_value, current_principal, interest_rate_percent, "
            "total_mortgage_years, loan_start_on, escrow_amount, house_base_total_paid, house_base_interest_paid, "
            "house_base_principal_paid, investment_worth, base_total_invested, notes "
            "FROM assets"
        )
        parameters: list[object] = []
        if asset_type:
            query += " WHERE asset_type = ?"
            parameters.append(asset_type.strip().lower())
        query += " ORDER BY asset_type ASC, name ASC"

        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()

        return [
            Asset(
                id=int(row["id"]),
                name=row["name"],
                asset_type=row["asset_type"],
                house_value=float(row["house_value"]),
                current_principal=float(row["current_principal"]),
                interest_rate_percent=float(row["interest_rate_percent"]),
                total_mortgage_years=float(row["total_mortgage_years"]),
                loan_start_on=date.fromisoformat(row["loan_start_on"]) if row["loan_start_on"] else None,
                escrow_amount=float(row["escrow_amount"]),
                house_base_total_paid=float(row["house_base_total_paid"]),
                house_base_interest_paid=float(row["house_base_interest_paid"]),
                house_base_principal_paid=float(row["house_base_principal_paid"]),
                investment_worth=float(row["investment_worth"]),
                base_total_invested=float(row["base_total_invested"]),
                notes=row["notes"] or "",
            )
            for row in rows
        ]

    def list_expense_transactions(self, limit: int = 250) -> list[Transaction]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, kind, amount, category, description, occurred_on, created_at
                FROM transactions
                WHERE kind = 'expense'
                ORDER BY occurred_on DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [
            Transaction(
                id=int(row["id"]),
                kind=row["kind"],
                amount=float(row["amount"]),
                category=row["category"],
                description=row["description"],
                occurred_on=date.fromisoformat(row["occurred_on"]),
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )
            for row in rows
        ]

    def link_expense_to_asset(
        self,
        asset_id: int,
        source_type: str,
        source_id: int,
        payment_kind: str = "mortgage",
    ) -> int:
        cleaned_type = source_type.strip().lower()
        if cleaned_type not in ("transaction", "recurring"):
            raise ValueError("Unsupported source type.")
        cleaned_kind = payment_kind.strip().lower()
        if cleaned_kind not in ("mortgage", "principal"):
            raise ValueError("Unsupported payment kind.")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO asset_expense_links (asset_id, source_type, source_id, payment_kind)
                VALUES (?, ?, ?, ?)
                """,
                (int(asset_id), cleaned_type, int(source_id), cleaned_kind),
            )
            return int(cursor.lastrowid)

    def unlink_expense_from_asset(self, link_id: int) -> bool:
        with self._connection() as connection:
            cursor = connection.execute("DELETE FROM asset_expense_links WHERE id = ?", (int(link_id),))
            return cursor.rowcount > 0

    def get_expense_asset_link(self, source_type: str, source_id: int) -> dict[str, object] | None:
        cleaned_type = source_type.strip().lower()
        if cleaned_type not in ("transaction", "recurring"):
            raise ValueError("Unsupported source type.")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, asset_id, payment_kind
                FROM asset_expense_links
                WHERE source_type = ? AND source_id = ?
                """,
                (cleaned_type, int(source_id)),
            ).fetchone()
        if row is None:
            return None
        return {"link_id": int(row["id"]), "asset_id": int(row["asset_id"]), "payment_kind": row["payment_kind"]}

    def set_expense_asset_link(
        self,
        asset_id: int | None,
        source_type: str,
        source_id: int,
        payment_kind: str = "mortgage",
    ) -> None:
        cleaned_type = source_type.strip().lower()
        if cleaned_type not in ("transaction", "recurring"):
            raise ValueError("Unsupported source type.")
        cleaned_kind = payment_kind.strip().lower()
        if cleaned_kind not in ("mortgage", "principal"):
            raise ValueError("Unsupported payment kind.")
        with self._connection() as connection:
            if asset_id is None:
                connection.execute(
                    "DELETE FROM asset_expense_links WHERE source_type = ? AND source_id = ?",
                    (cleaned_type, int(source_id)),
                )
                return

            connection.execute(
                """
                INSERT INTO asset_expense_links (asset_id, source_type, source_id, payment_kind)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(source_type, source_id)
                DO UPDATE SET asset_id = excluded.asset_id, payment_kind = excluded.payment_kind
                """,
                (int(asset_id), cleaned_type, int(source_id), cleaned_kind),
            )

    def list_asset_expense_links(self, asset_id: int) -> list[dict[str, object]]:
        with self._connection() as connection:
            link_rows = connection.execute(
                """
                SELECT id, source_type, source_id, payment_kind
                FROM asset_expense_links
                WHERE asset_id = ?
                ORDER BY id DESC
                """,
                (int(asset_id),),
            ).fetchall()

        linked: list[dict[str, object]] = []
        for row in link_rows:
            source_type = row["source_type"]
            source_id = int(row["source_id"])
            payment_kind = row["payment_kind"]
            if source_type == "transaction":
                tx = self.get_transaction_by_id(source_id)
                if tx is None or tx.kind != "expense":
                    continue
                linked.append(
                    {
                        "link_id": int(row["id"]),
                        "source_type": "transaction",
                        "source_id": tx.id,
                        "payment_kind": payment_kind,
                        "amount": tx.amount,
                        "label": f"{tx.occurred_on.isoformat()} | {tx.category} | {tx.description} | {payment_kind.title()}",
                        "date": tx.occurred_on,
                        "interval_count": None,
                    }
                )
            else:
                recurring = next((item for item in self.list_recurring_items() if item.id == source_id and item.kind == "expense"), None)
                if recurring is None:
                    continue
                occurrence_date = recurring.start_on
                today = date.today()
                while occurrence_date <= today:
                    linked.append(
                        {
                            "link_id": int(row["id"]),
                            "source_type": "recurring",
                            "source_id": recurring.id,
                            "payment_kind": payment_kind,
                            "amount": recurring.amount,
                            "label": f"Recurring | {recurring.category} | {recurring.description} | {payment_kind.title()} | {occurrence_date.isoformat()}",
                            "date": occurrence_date,
                            "interval_count": recurring.interval_count,
                        }
                    )
                    occurrence_date = self._advance_months(occurrence_date, recurring.interval_count)

        linked.sort(key=lambda item: (item["date"] if isinstance(item["date"], date) else date.today()), reverse=True)
        return linked

    def list_unlinked_expense_transactions(self, asset_id: int | None = None, limit: int = 250) -> list[Transaction]:
        query = (
            """
            SELECT t.id, t.kind, t.amount, t.category, t.description, t.occurred_on, t.created_at
            FROM transactions t
            WHERE t.kind = 'expense'
              AND t.id NOT IN (
                  SELECT source_id FROM asset_expense_links WHERE source_type = 'transaction'
              )
            ORDER BY t.occurred_on DESC, t.id DESC
            LIMIT ?
            """
        )
        with self._connection() as connection:
            rows = connection.execute(query, (int(limit),)).fetchall()

        return [
            Transaction(
                id=int(row["id"]),
                kind=row["kind"],
                amount=float(row["amount"]),
                category=row["category"],
                description=row["description"],
                occurred_on=date.fromisoformat(row["occurred_on"]),
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )
            for row in rows
        ]

    def list_unlinked_recurring_expenses(self) -> list[RecurringItem]:
        linked_ids: set[int] = set()
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT source_id FROM asset_expense_links WHERE source_type = 'recurring'"
            ).fetchall()
            linked_ids = {int(row["source_id"]) for row in rows}

        return [
            item
            for item in self.list_recurring_items(active_only=True)
            if item.kind == "expense" and item.id is not None and int(item.id) not in linked_ids
        ]

    def assets_overview(self) -> dict[str, float]:
        assets = self.list_assets()
        total_invested = 0.0
        total_value = 0.0
        total_debt = 0.0
        for asset in assets:
            if asset.asset_type == "house":
                total_value += asset.house_value
                total_debt += asset.current_principal
            else:
                linked_contributions = 0.0
                if asset.id is not None:
                    linked_contributions = sum(
                        float(link["amount"]) for link in self.list_asset_expense_links(int(asset.id))
                    )
                total_value += asset.investment_worth
                total_invested += asset.base_total_invested + linked_contributions
                continue
            total_invested += asset.base_total_invested
        return {
            "total_invested": total_invested,
            "total_value": total_value,
            "total_debt": total_debt,
            "total_net_worth": total_value - total_debt,
        }

    def add_transaction(
        self,
        kind: str,
        amount: float,
        category: str,
        description: str,
        occurred_on: date | None = None,
    ) -> int:
        occurred_date = occurred_on or date.today()
        return self._transactions_repository.add_transaction(
            kind=kind,
            amount=amount,
            category=category,
            description=description,
            occurred_on=occurred_date,
        )

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
        return self._transactions_repository.delete_transaction(transaction_id)

    def get_transaction_by_id(self, transaction_id: int) -> Transaction | None:
        return self._transactions_repository.get_transaction_by_id(transaction_id)

    def update_transaction(
        self,
        transaction_id: int,
        amount: float,
        category: str,
        description: str,
        occurred_on: date,
    ) -> bool:
        return self._transactions_repository.update_transaction(
            transaction_id=transaction_id,
            amount=amount,
            category=category,
            description=description,
            occurred_on=occurred_on,
        )

    def _month_bounds(self, year: int, month: int) -> tuple[date, date]:
        start_on = date(year, month, 1)
        end_day = monthrange(year, month)[1]
        end_on = date(year, month, end_day)
        return start_on, end_on

    def shift_month(self, year: int, month: int, offset: int) -> tuple[int, int]:
        absolute_month = (year * 12) + (month - 1) + offset
        shifted_year = absolute_month // 12
        shifted_month = absolute_month % 12 + 1
        return shifted_year, shifted_month

    def _shift_month(self, year: int, month: int, offset: int) -> tuple[int, int]:
        return self.shift_month(year, month, offset)

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
        return self._recurring_repository.add_recurring_item(
            kind=kind,
            amount=amount,
            category=category,
            description=description,
            interval_count=interval_count,
            interval_unit=interval_unit,
            start_on=start_on,
            is_active=is_active,
        )

    def list_recurring_items(self, active_only: bool = False) -> list[RecurringItem]:
        return self._recurring_repository.list_recurring_items(active_only=active_only)

    def delete_recurring_item(self, recurring_item_id: int) -> bool:
        return self._recurring_repository.delete_recurring_item(recurring_item_id)

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
        return self._recurring_repository.update_recurring_item(
            recurring_item_id=recurring_item_id,
            kind=kind,
            amount=amount,
            category=category,
            description=description,
            interval_count=interval_count,
            start_on=start_on,
            is_active=is_active,
        )

    def apply_due_recurring_items(self, as_of: date | None = None) -> int:
        return self._recurring_repository.apply_due_recurring_items(as_of)

    def materialize_due_recurring_items(self, as_of: date | None = None) -> int:
        """Explicit entry point for recurring materialization from orchestration layers."""
        return self.apply_due_recurring_items(as_of)

    def _advance_months(self, value: date, interval_count: int) -> date:
        month_index = value.month - 1 + interval_count
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)

    def list_transactions(self, limit: int = 100) -> list[Transaction]:
        self.apply_due_recurring_items()
        return self._transactions_repository.list_transactions(limit=limit)

    def list_transactions_for_month(self, year: int, month: int, limit: int = 100) -> list[Transaction]:
        start_on, end_on = self._month_bounds(year, month)
        return self._transactions_repository.list_transactions_for_month(start_on=start_on, end_on=end_on, limit=limit)

    def daily_totals_for_month(self, year: int, month: int) -> list[tuple[date, float, float, float]]:
        return self._analytics_repository.daily_totals_for_month(year, month)

    def expense_breakdown_for_month(self, year: int, month: int) -> list[tuple[str, float]]:
        return self._analytics_repository.expense_breakdown_for_month(year, month)

    def snapshot(self) -> SummarySnapshot:
        return self._analytics_repository.snapshot()

    def snapshot_for_month(self, year: int, month: int) -> SummarySnapshot:
        return self._analytics_repository.snapshot_for_month(year, month)

    def monthly_history(self, reference_year: int, reference_month: int, months: int = 6) -> list[tuple[int, int, float, float, float]]:
        return self._analytics_repository.monthly_history(reference_year, reference_month, months)

    def personal_position_history(
        self,
        reference_year: int,
        reference_month: int,
        months: int = 12,
    ) -> list[tuple[int, int, float, float, float]]:
        return self._analytics_repository.personal_position_history(reference_year, reference_month, months)

    def compute_income_series(self, reference_year: int, reference_month: int, months: int = 6) -> list[float]:
        return self._analytics_repository.compute_income_series(reference_year, reference_month, months)

    def get_current_month_budget_map(self, year: int, month: int, kind: str = "expense") -> dict[str, float]:
        """Return the monthly budgeted amount map keyed by category."""
        rows = self.list_budgets_for_month(year, month, kind=kind)
        return {row.category: float(row.budgeted_amount) for row in rows}

    def list_monthly_category_spend(
        self,
        start_year: int,
        start_month: int,
        end_year: int,
        end_month: int,
        kind: str = "expense",
    ) -> dict[str, list[tuple[int, int, float]]]:
        return self._analytics_repository.list_monthly_category_spend(
            start_year=start_year,
            start_month=start_month,
            end_year=end_year,
            end_month=end_month,
            kind=kind,
        )

    def count_full_history_months(self, reference_year: int, reference_month: int, kind: str = "expense") -> int:
        return self._analytics_repository.count_full_history_months(reference_year, reference_month, kind)

    def get_recurring_totals_for_month(self, year: int, month: int) -> tuple[float, float]:
        return self._recurring_repository.get_recurring_totals_for_month(year, month)

    def get_projected_recurring_totals_for_month(self, year: int, month: int) -> tuple[float, float]:
        return self._recurring_repository.get_projected_recurring_totals_for_month(year, month)

    def add_or_update_budget(
        self, year: int, month: int, category: str, kind: str, budgeted_amount: float, notes: str = ""
    ) -> int:
        return self._budget_repository.add_or_update_budget(year, month, category, kind, budgeted_amount, notes)

    def delete_budget(self, budget_id: int) -> bool:
        return self._budget_repository.delete_budget(budget_id)

    def list_budgets_for_month(self, year: int, month: int, kind: str | None = None) -> list[Budget]:
        return self._budget_repository.list_budgets_for_month(year, month, kind)

    def get_actual_spent_for_category(self, year: int, month: int, category: str, kind: str) -> float:
        return self._budget_repository.get_actual_spent_for_category(year, month, category, kind)

    def _get_actual_spent_for_category(self, year: int, month: int, category: str, kind: str) -> float:
        return self.get_actual_spent_for_category(year, month, category, kind)

    def get_active_recurring_items_for_month(self, year: int, month: int, kind: str | None = None) -> list[RecurringItem]:
        return self._budget_repository.get_active_recurring_items_for_month(year, month, kind)

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

        # assets.csv
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT name, asset_type, house_value, current_principal, interest_rate_percent,
                       total_mortgage_years, loan_start_on, escrow_amount, house_base_total_paid,
                       house_base_interest_paid, house_base_principal_paid, investment_worth,
                       base_total_invested, notes
                FROM assets
                ORDER BY asset_type ASC, name ASC
                """
            ).fetchall()
        with open(output_dir / "assets.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "name",
                    "asset_type",
                    "house_value",
                    "current_principal",
                    "interest_rate_percent",
                    "total_mortgage_years",
                    "loan_start_on",
                    "escrow_amount",
                    "house_base_total_paid",
                    "house_base_interest_paid",
                    "house_base_principal_paid",
                    "investment_worth",
                    "base_total_invested",
                    "notes",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        counts["assets"] = len(rows)

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
                conn.execute("DELETE FROM assets")
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

        # assets.csv
        assets_file = input_dir / "assets.csv"
        if assets_file.exists():
            imported = 0
            with open(assets_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        loan_start_text = row.get("loan_start_on", "").strip()
                        self.add_asset(
                            name=row["name"].strip(),
                            asset_type=row["asset_type"].strip().lower(),
                            house_value=float(row.get("house_value", row.get("current_value", 0)) or 0),
                            current_principal=float(row.get("current_principal", row.get("debt_principal", 0)) or 0),
                            interest_rate_percent=float(row.get("interest_rate_percent", row.get("rate_percent", 0)) or 0),
                            total_mortgage_years=float(row.get("total_mortgage_years", 30) or 30),
                            loan_start_on=date.fromisoformat(loan_start_text) if loan_start_text else None,
                            escrow_amount=float(row.get("escrow_amount", 0) or 0),
                            house_base_total_paid=float(row.get("house_base_total_paid", 0) or 0),
                            house_base_interest_paid=float(row.get("house_base_interest_paid", 0) or 0),
                            house_base_principal_paid=float(row.get("house_base_principal_paid", 0) or 0),
                            investment_worth=float(row.get("investment_worth", row.get("current_value", 0)) or 0),
                            base_total_invested=float(row.get("base_total_invested", row.get("amount_invested", 0)) or 0),
                            notes=row.get("notes", "").strip(),
                        )
                        imported += 1
                    except (KeyError, ValueError):
                        continue
            counts["assets"] = imported

        return counts

    def list_paired_remote_devices(self, active_only: bool = True) -> list[PairedRemoteDevice]:
        """List paired remote voice devices."""
        if active_only:
            return self._paired_device_repository.list_active()
        return self._paired_device_repository.list_all()

    def get_paired_remote_device(self, source_id: str) -> PairedRemoteDevice | None:
        """Get a paired remote device by source ID."""
        return self._paired_device_repository.get_by_source_id(source_id)

    def save_paired_remote_device(self, device: PairedRemoteDevice) -> PairedRemoteDevice:
        """Save or update a paired remote device."""
        return self._paired_device_repository.save(device)

    def update_paired_device_connection_time(self, source_id: str) -> None:
        """Update the last connected timestamp for a device."""
        self._paired_device_repository.update_last_connected(source_id)

    def remove_paired_remote_device(self, source_id: str) -> None:
        """Soft delete (deactivate) a paired remote device."""
        self._paired_device_repository.delete(source_id)
