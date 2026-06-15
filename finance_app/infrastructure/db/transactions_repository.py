from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import date, datetime
import sqlite3

from finance_app.models import Transaction


ConnectionFactory = Callable[[], AbstractContextManager[sqlite3.Connection] | Iterator[sqlite3.Connection]]
EnsureCategoryProvider = Callable[[str, str], None]


class TransactionsRepository:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        ensure_category_provider: EnsureCategoryProvider,
    ) -> None:
        self._connection_factory = connection_factory
        self._ensure_category = ensure_category_provider

    def add_transaction(
        self,
        kind: str,
        amount: float,
        category: str,
        description: str,
        occurred_on: date,
    ) -> int:
        self._ensure_category(category, kind)

        with self._connection_factory() as connection:
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
                    occurred_on.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def delete_transaction(self, transaction_id: int) -> bool:
        with self._connection_factory() as connection:
            cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (int(transaction_id),))
            return cursor.rowcount > 0

    def get_transaction_by_id(self, transaction_id: int) -> Transaction | None:
        with self._connection_factory() as connection:
            row = connection.execute(
                """
                SELECT id, kind, amount, category, description, occurred_on, created_at
                FROM transactions
                WHERE id = ?
                """,
                (int(transaction_id),),
            ).fetchone()

        if not row:
            return None

        return Transaction(
            id=row["id"],
            kind=row["kind"],
            amount=float(row["amount"]),
            category=row["category"],
            description=row["description"],
            occurred_on=datetime.strptime(row["occurred_on"], "%Y-%m-%d").date(),
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    def update_transaction(
        self,
        transaction_id: int,
        amount: float,
        category: str,
        description: str,
        occurred_on: date,
    ) -> bool:
        cleaned_category = category.strip()
        cleaned_description = description.strip()
        if amount <= 0 or not cleaned_category or not cleaned_description:
            return False

        with self._connection_factory() as connection:
            kind_row = connection.execute(
                "SELECT kind FROM transactions WHERE id = ?",
                (int(transaction_id),),
            ).fetchone()
            if not kind_row:
                return False

            kind = str(kind_row["kind"]).strip() or "expense"
            self._ensure_category(cleaned_category, kind)

            cursor = connection.execute(
                """
                UPDATE transactions
                SET amount = ?, category = ?, description = ?, occurred_on = ?
                WHERE id = ?
                """,
                (
                    float(amount),
                    cleaned_category,
                    cleaned_description,
                    occurred_on.isoformat(),
                    int(transaction_id),
                ),
            )
            return cursor.rowcount > 0

    def list_transactions(self, limit: int = 100) -> list[Transaction]:
        with self._connection_factory() as connection:
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

    def list_transactions_for_month(self, start_on: date, end_on: date, limit: int = 100) -> list[Transaction]:
        with self._connection_factory() as connection:
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
