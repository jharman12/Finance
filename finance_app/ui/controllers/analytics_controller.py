from __future__ import annotations

from finance_app.chart_models import (
    CashflowChartsPayload,
    ChartCategoryPoint,
    ChartDailyPoint,
    ChartMonthlyPoint,
    DebtCompositionPoint,
    PositionChartsPayload,
    PositionMonthlyPoint,
)
from finance_app.storage import FinanceRepository


class AnalyticsController:
    def __init__(self, repository: FinanceRepository) -> None:
        self._repository = repository

    def snapshot_for_month(self, year: int, month: int):
        return self._repository.snapshot_for_month(year, month)

    def daily_totals_for_month(self, year: int, month: int):
        return self._repository.daily_totals_for_month(year, month)

    def expense_breakdown_for_month(self, year: int, month: int):
        return self._repository.expense_breakdown_for_month(year, month)

    def monthly_history(self, year: int, month: int, months: int = 6):
        return self._repository.monthly_history(year, month, months=months)

    def get_cashflow_charts_payload(self, year: int, month: int, months_history: int = 6) -> CashflowChartsPayload:
        snapshot = self._repository.snapshot_for_month(year, month)
        daily_totals = self._repository.daily_totals_for_month(year, month)
        expense_breakdown = self._repository.expense_breakdown_for_month(year, month)
        monthly_history = self._repository.monthly_history(year, month, months=months_history)

        return CashflowChartsPayload(
            year=year,
            month=month,
            snapshot=snapshot,
            daily_points=[
                ChartDailyPoint(
                    occurred_on=entry[0],
                    income=float(entry[1]),
                    expense=float(entry[2]),
                    net=float(entry[3]),
                )
                for entry in daily_totals
            ],
            monthly_points=[
                ChartMonthlyPoint(
                    year=int(entry[0]),
                    month=int(entry[1]),
                    income=float(entry[2]),
                    expense=float(entry[3]),
                    net=float(entry[4]),
                )
                for entry in monthly_history
            ],
            expense_breakdown=[
                ChartCategoryPoint(category=str(entry[0]), amount=float(entry[1]))
                for entry in expense_breakdown
            ],
        )

    def get_position_charts_payload(self, year: int, month: int, months_history: int = 12) -> PositionChartsPayload:
        assets = self._repository.list_assets()
        position_history = self._repository.personal_position_history(year, month, months=months_history)
        monthly_history = self._repository.monthly_history(year, month, months=months_history)

        debt_composition: list[DebtCompositionPoint] = []
        for asset in assets:
            if asset.asset_type == "house":
                debt_amount = float(asset.current_principal)
                if debt_amount > 0:
                    debt_composition.append(
                        DebtCompositionPoint(label=asset.name, amount=debt_amount)
                    )

        monthly_cash_map = {
            (int(entry[0]), int(entry[1])): (float(entry[2]), float(entry[3]), float(entry[4]))
            for entry in monthly_history
        }

        monthly_points: list[PositionMonthlyPoint] = []
        for position_entry in position_history:
            point_year, point_month, net_worth, total_debt, _total_asset_value = position_entry
            income, expense, net_income = monthly_cash_map.get((int(point_year), int(point_month)), (0.0, 0.0, 0.0))
            monthly_points.append(
                PositionMonthlyPoint(
                    year=int(point_year),
                    month=int(point_month),
                    estimated_net_worth=float(net_worth),
                    estimated_total_debt=float(total_debt),
                    income=float(income),
                    expense=float(expense),
                    net_income=float(net_income),
                    savings_rate=(float(net_income) / float(income)) if float(income) > 0 else 0.0,
                )
            )

        if position_history:
            _cur_year, _cur_month, current_net_worth, current_total_debt, total_asset_value = position_history[-1]
        else:
            assets_overview = self._repository.assets_overview()
            current_net_worth = float(assets_overview.get("total_net_worth", 0.0))
            current_total_debt = float(assets_overview.get("total_debt", 0.0))
            total_asset_value = float(assets_overview.get("total_value", 0.0))

        return PositionChartsPayload(
            year=year,
            month=month,
            total_net_worth=current_net_worth,
            total_debt=current_total_debt,
            total_asset_value=float(total_asset_value),
            monthly_points=monthly_points,
            debt_composition=debt_composition,
            assets=assets,
        )
