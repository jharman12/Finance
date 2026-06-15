from __future__ import annotations

from datetime import date
import unittest

from finance_app.chart_models import (
    CashflowChartsPayload,
    ChartCategoryPoint,
    ChartDailyPoint,
    ChartMonthlyPoint,
    DebtCompositionPoint,
    PositionChartsPayload,
    PositionMonthlyPoint,
)


class ChartPayloadShapesTests(unittest.TestCase):
    def test_cashflow_payload_defaults_are_empty_lists(self) -> None:
        payload = CashflowChartsPayload(
            year=2026,
            month=6,
            snapshot=type("Snapshot", (), {
                "income_total": 0.0,
                "expense_total": 0.0,
                "net_total": 0.0,
                "transaction_count": 0,
            })(),
        )

        self.assertEqual(payload.daily_points, [])
        self.assertEqual(payload.monthly_points, [])
        self.assertEqual(payload.expense_breakdown, [])

    def test_cashflow_payload_series_can_be_sorted_by_month(self) -> None:
        payload = CashflowChartsPayload(
            year=2026,
            month=6,
            snapshot=type("Snapshot", (), {
                "income_total": 0.0,
                "expense_total": 0.0,
                "net_total": 0.0,
                "transaction_count": 0,
            })(),
            daily_points=[ChartDailyPoint(date(2026, 6, 2), 20.0, 10.0, 10.0)],
            monthly_points=[ChartMonthlyPoint(2026, 5, 100.0, 80.0, 20.0)],
            expense_breakdown=[ChartCategoryPoint("Groceries", 80.0)],
        )

        self.assertEqual(payload.daily_points[0].occurred_on.day, 2)
        self.assertEqual(payload.monthly_points[0].month, 5)
        self.assertEqual(payload.expense_breakdown[0].amount, 80.0)

    def test_position_payload_defaults_are_empty_lists(self) -> None:
        payload = PositionChartsPayload(
            year=2026,
            month=6,
            total_net_worth=0.0,
            total_debt=0.0,
            total_asset_value=0.0,
        )

        self.assertEqual(payload.monthly_points, [])
        self.assertEqual(payload.debt_composition, [])
        self.assertEqual(payload.assets, [])

    def test_position_payload_holds_expected_series_types(self) -> None:
        payload = PositionChartsPayload(
            year=2026,
            month=6,
            total_net_worth=100000.0,
            total_debt=250000.0,
            total_asset_value=350000.0,
            monthly_points=[
                PositionMonthlyPoint(
                    year=2026,
                    month=6,
                    estimated_net_worth=100000.0,
                    estimated_total_debt=250000.0,
                    income=8000.0,
                    expense=6000.0,
                    net_income=2000.0,
                    savings_rate=0.25,
                )
            ],
            debt_composition=[DebtCompositionPoint("House", 250000.0)],
        )

        self.assertEqual(payload.monthly_points[0].savings_rate, 0.25)
        self.assertEqual(payload.debt_composition[0].label, "House")


if __name__ == "__main__":
    unittest.main()
