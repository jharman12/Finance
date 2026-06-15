from __future__ import annotations

from datetime import date
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from finance_app.ui.controllers.analytics_controller import AnalyticsController
from finance_app.ui.controllers.app_controller import AppController
from finance_app.ui.controllers.assets_controller import AssetsController
from finance_app.ui.controllers.budget_controller import BudgetController
from finance_app.ui.controllers.category_controller import CategoryController
from finance_app.ui.controllers.recurring_controller import RecurringController
from finance_app.ui.controllers.transaction_controller import TransactionController


class ControllerDelegationTests(unittest.TestCase):
    def test_budget_controller_delegates_reallocation_audits(self) -> None:
        repository = Mock()
        repository.list_budget_reallocation_audits.return_value = [{"id": 1}]
        controller = BudgetController(repository)

        audits = controller.list_budget_reallocation_audits(limit=25)

        repository.list_budget_reallocation_audits.assert_called_once_with(limit=25)
        self.assertEqual(audits, [{"id": 1}])

    def test_category_controller_category_exists_case_insensitive(self) -> None:
        repository = Mock()
        repository.list_categories.return_value = [SimpleNamespace(name="Groceries")]
        controller = CategoryController(repository)

        self.assertTrue(controller.category_exists("expense", "gRoCeRiEs"))
        repository.list_categories.assert_called_once_with(kind="expense")

    def test_transaction_controller_delegates_add_income(self) -> None:
        repository = Mock()
        repository.add_income.return_value = 101
        controller = TransactionController(repository)

        result = controller.add_income(123.0, "Salary", "Paycheck", SimpleNamespace())

        repository.add_income.assert_called_once()
        self.assertEqual(result, 101)

    def test_recurring_controller_delegates_delete(self) -> None:
        repository = Mock()
        repository.delete_recurring_item.return_value = True
        controller = RecurringController(repository)

        self.assertTrue(controller.delete_recurring_item(9))
        repository.delete_recurring_item.assert_called_once_with(9)

    def test_assets_controller_delegates_unlink(self) -> None:
        repository = Mock()
        controller = AssetsController(repository)

        controller.unlink_expense_from_asset(44)

        repository.unlink_expense_from_asset.assert_called_once_with(44)

    def test_analytics_controller_delegates_snapshot(self) -> None:
        repository = Mock()
        expected = SimpleNamespace(income_total=0.0)
        repository.snapshot_for_month.return_value = expected
        controller = AnalyticsController(repository)

        result = controller.snapshot_for_month(2026, 6)

        repository.snapshot_for_month.assert_called_once_with(2026, 6)
        self.assertIs(result, expected)

    def test_analytics_controller_builds_cashflow_payload(self) -> None:
        repository = Mock()
        snapshot = SimpleNamespace(income_total=1000.0, expense_total=500.0, net_total=500.0, transaction_count=3)
        repository.snapshot_for_month.return_value = snapshot
        repository.daily_totals_for_month.return_value = [(date(2026, 6, 1), 100.0, 50.0, 50.0)]
        repository.expense_breakdown_for_month.return_value = [("Groceries", 120.0)]
        repository.monthly_history.return_value = [(2026, 6, 1000.0, 500.0, 500.0)]

        controller = AnalyticsController(repository)

        payload = controller.get_cashflow_charts_payload(2026, 6, months_history=6)

        repository.snapshot_for_month.assert_called_once_with(2026, 6)
        repository.daily_totals_for_month.assert_called_once_with(2026, 6)
        repository.expense_breakdown_for_month.assert_called_once_with(2026, 6)
        repository.monthly_history.assert_called_once_with(2026, 6, months=6)
        self.assertEqual(payload.year, 2026)
        self.assertEqual(payload.month, 6)
        self.assertIs(payload.snapshot, snapshot)
        self.assertEqual(payload.daily_points[0].occurred_on, date(2026, 6, 1))
        self.assertEqual(payload.expense_breakdown[0].category, "Groceries")
        self.assertEqual(payload.monthly_points[0].net, 500.0)

    def test_analytics_controller_builds_position_payload(self) -> None:
        repository = Mock()
        repository.list_assets.return_value = [
            SimpleNamespace(name="House", asset_type="house", current_principal=250000.0),
            SimpleNamespace(name="Brokerage", asset_type="investment", current_principal=0.0),
        ]
        repository.personal_position_history.return_value = [
            (2026, 5, 147800.0, 252000.0, 399800.0),
            (2026, 6, 150000.0, 250000.0, 400000.0),
        ]
        repository.monthly_history.return_value = [
            (2026, 5, 8000.0, 6000.0, 2000.0),
            (2026, 6, 8100.0, 5900.0, 2200.0),
        ]

        controller = AnalyticsController(repository)

        payload = controller.get_position_charts_payload(2026, 6, months_history=12)

        repository.list_assets.assert_called_once_with()
        repository.personal_position_history.assert_called_once_with(2026, 6, months=12)
        repository.monthly_history.assert_called_once_with(2026, 6, months=12)
        self.assertEqual(payload.total_net_worth, 150000.0)
        self.assertEqual(payload.total_debt, 250000.0)
        self.assertEqual(payload.total_asset_value, 400000.0)
        self.assertEqual(len(payload.debt_composition), 1)
        self.assertEqual(payload.debt_composition[0].label, "House")
        self.assertEqual(len(payload.monthly_points), 2)
        self.assertEqual(payload.monthly_points[0].estimated_net_worth, 147800.0)
        self.assertEqual(payload.monthly_points[-1].savings_rate, 2200.0 / 8100.0)

    def test_app_controller_delegates_settings_and_materialization(self) -> None:
        repository = Mock()
        repository.get_setting.return_value = "1.00"
        controller = AppController(repository)

        value = controller.get_setting("ui_scale", "1.00")
        controller.set_setting("ui_scale", "1.10")
        controller.materialize_due_recurring_items()

        repository.get_setting.assert_called_once_with("ui_scale", "1.00")
        repository.set_setting.assert_called_once_with("ui_scale", "1.10")
        repository.materialize_due_recurring_items.assert_called_once_with()
        self.assertEqual(value, "1.00")


if __name__ == "__main__":
    unittest.main()
