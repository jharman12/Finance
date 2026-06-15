from __future__ import annotations

from datetime import date

from finance_app.storage import FinanceRepository


class TransactionController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def list_categories(self, kind: str):
        return self._repository.list_categories(kind)

    def list_transactions_for_month(self, year: int, month: int, limit: int = 250):
        return self._repository.list_transactions_for_month(year, month, limit=limit)

    def add_expense(self, amount: float, category: str, description: str, occurred_on: date) -> int:
        return self._repository.add_expense(amount, category, description, occurred_on)

    def add_income(self, amount: float, category: str, description: str, occurred_on: date) -> int:
        return self._repository.add_income(amount, category, description, occurred_on)

    def link_expense_to_asset(
        self,
        asset_id: int,
        source_type: str,
        source_id: int,
        payment_kind: str = "mortgage",
    ) -> int:
        return self._repository.link_expense_to_asset(asset_id, source_type, source_id, payment_kind=payment_kind)

    def get_transaction_by_id(self, transaction_id: int):
        return self._repository.get_transaction_by_id(transaction_id)

    def update_transaction(
        self,
        transaction_id: int,
        amount: float,
        category: str,
        description: str,
        occurred_on: date,
    ) -> bool:
        return self._repository.update_transaction(
            transaction_id=transaction_id,
            amount=amount,
            category=category,
            description=description,
            occurred_on=occurred_on,
        )

    def delete_transaction(self, transaction_id: int) -> bool:
        return self._repository.delete_transaction(transaction_id)
