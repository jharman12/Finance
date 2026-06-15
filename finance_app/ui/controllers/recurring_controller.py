from __future__ import annotations

from datetime import date

from finance_app.storage import FinanceRepository


class RecurringController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def list_categories(self, kind: str):
        return self._repository.list_categories(kind)

    def list_recurring_items(self, active_only: bool = False):
        return self._repository.list_recurring_items(active_only=active_only)

    def add_recurring_item(
        self,
        kind: str,
        amount: float,
        category: str,
        description: str,
        interval_count: int,
        interval_unit: str,
        start_on: date,
    ) -> int:
        return self._repository.add_recurring_item(
            kind=kind,
            amount=amount,
            category=category,
            description=description,
            interval_count=interval_count,
            interval_unit=interval_unit,
            start_on=start_on,
        )

    def update_recurring_item(
        self,
        recurring_id: int,
        kind: str,
        amount: float,
        category: str,
        description: str,
        interval_count: int,
        start_on: date,
        is_active: bool,
    ) -> bool:
        return self._repository.update_recurring_item(
            recurring_item_id=recurring_id,
            kind=kind,
            amount=amount,
            category=category,
            description=description,
            interval_count=interval_count,
            start_on=start_on,
            is_active=is_active,
        )

    def delete_recurring_item(self, recurring_id: int) -> bool:
        return self._repository.delete_recurring_item(recurring_id)

    def list_assets(self):
        return self._repository.list_assets()

    def link_expense_to_asset(
        self,
        asset_id: int,
        source_type: str,
        source_id: int,
        payment_kind: str = "mortgage",
    ) -> int:
        return self._repository.link_expense_to_asset(asset_id, source_type, source_id, payment_kind=payment_kind)

    def get_expense_asset_link(self, source_type: str, source_id: int):
        return self._repository.get_expense_asset_link(source_type, source_id)

    def set_expense_asset_link(
        self,
        asset_id: int | None,
        source_type: str,
        source_id: int,
        payment_kind: str = "mortgage",
    ) -> None:
        self._repository.set_expense_asset_link(asset_id, source_type, source_id, payment_kind=payment_kind)

    def change_transaction_category(self, from_category: str, to_category: str, description_filter: str | None = None) -> int:
        return self._repository.change_transaction_category(from_category, to_category, description_filter)
