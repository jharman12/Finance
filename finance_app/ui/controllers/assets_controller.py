from __future__ import annotations

from datetime import date

from finance_app.storage import FinanceRepository


class AssetsController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def assets_overview(self):
        return self._repository.assets_overview()

    def list_assets(self):
        return self._repository.list_assets()

    def add_asset(
        self,
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
    ) -> int:
        return self._repository.add_asset(
            name=name,
            asset_type=asset_type,
            house_value=house_value,
            current_principal=current_principal,
            interest_rate_percent=interest_rate_percent,
            total_mortgage_years=total_mortgage_years,
            loan_start_on=loan_start_on,
            escrow_amount=escrow_amount,
            house_base_total_paid=house_base_total_paid,
            house_base_interest_paid=house_base_interest_paid,
            house_base_principal_paid=house_base_principal_paid,
            investment_worth=investment_worth,
            base_total_invested=base_total_invested,
        )

    def get_asset_by_id(self, asset_id: int):
        return self._repository.get_asset_by_id(asset_id)

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
        notes: str,
    ) -> bool:
        return self._repository.update_asset(
            asset_id=asset_id,
            name=name,
            asset_type=asset_type,
            house_value=house_value,
            current_principal=current_principal,
            interest_rate_percent=interest_rate_percent,
            total_mortgage_years=total_mortgage_years,
            loan_start_on=loan_start_on,
            escrow_amount=escrow_amount,
            house_base_total_paid=house_base_total_paid,
            house_base_interest_paid=house_base_interest_paid,
            house_base_principal_paid=house_base_principal_paid,
            investment_worth=investment_worth,
            base_total_invested=base_total_invested,
            notes=notes,
        )

    def delete_asset(self, asset_id: int) -> bool:
        return self._repository.delete_asset(asset_id)

    def record_investment_value_snapshot(self, asset_id: int, value: float, valued_on: date, notes: str) -> bool:
        return self._repository.record_investment_value_snapshot(
            asset_id=asset_id,
            value=value,
            valued_on=valued_on,
            notes=notes,
        )

    def list_asset_value_snapshots(self, asset_id: int, limit: int = 24):
        return self._repository.list_asset_value_snapshots(asset_id, limit=limit)

    def list_asset_expense_links(self, asset_id: int):
        return self._repository.list_asset_expense_links(asset_id)

    def list_unlinked_expense_transactions(self, limit: int = 300):
        return self._repository.list_unlinked_expense_transactions(limit=limit)

    def list_unlinked_recurring_expenses(self):
        return self._repository.list_unlinked_recurring_expenses()

    def link_expense_to_asset(
        self,
        asset_id: int,
        source_type: str,
        source_id: int,
        payment_kind: str = "mortgage",
    ) -> int:
        return self._repository.link_expense_to_asset(asset_id, source_type, source_id, payment_kind=payment_kind)

    def unlink_expense_from_asset(self, link_id: int) -> None:
        self._repository.unlink_expense_from_asset(link_id)
