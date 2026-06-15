from __future__ import annotations

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
