from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from finance_app.storage import FinanceRepository
from finance_app.ui.controllers.budget_controller import BudgetController


class BudgetControllerCsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_db = Path(__file__).resolve().parent / "tmp_budget_controller.sqlite3"
        if self.temp_db.exists():
            self.temp_db.unlink()
        self.repository = FinanceRepository(self.temp_db)
        self.controller = BudgetController(self.repository)

    def tearDown(self) -> None:
        if self.temp_db.exists():
            self.temp_db.unlink()

    def test_export_budget_rows_formats_values_for_csv(self) -> None:
        self.repository.add_or_update_budget(2026, 6, "Rent", "expense", 1800.0, "Home")
        self.repository.add_or_update_budget(2026, 6, "Salary", "income", 5200.0, "Job")

        rows = self.controller.export_budget_rows_for_month(2026, 6)

        self.assertEqual(len(rows), 2)
        self.assertIn(
            {
                "year": "2026",
                "month": "6",
                "category": "Rent",
                "kind": "expense",
                "budgeted_amount": "1800.00",
                "notes": "Home",
            },
            rows,
        )

    def test_import_budget_rows_skips_invalid_and_imports_valid(self) -> None:
        rows = [
            {"category": "Rent", "kind": "expense", "budgeted_amount": "1800.00", "notes": "Home"},
            {"category": "Salary", "kind": "income", "budgeted_amount": "$5200", "notes": "Job"},
            {"category": "", "kind": "expense", "budgeted_amount": "100", "notes": "Invalid"},
            {"category": "Bad", "kind": "expense", "budgeted_amount": "abc", "notes": "Invalid"},
            {"category": "Oops", "kind": "other", "budgeted_amount": "100", "notes": "Invalid"},
        ]

        imported_count, skipped_count = self.controller.import_budget_rows_for_month(2026, 6, rows)

        self.assertEqual(imported_count, 2)
        self.assertEqual(skipped_count, 3)

        budgets = self.repository.list_budgets_for_month(2026, 6)
        categories = {budget.category for budget in budgets}
        self.assertEqual(categories, {"Rent", "Salary"})

    def test_import_budget_rows_replace_existing_clears_month_first(self) -> None:
        self.repository.add_or_update_budget(2026, 6, "Old", "expense", 10.0, "Old budget")

        rows = [
            {"category": "New", "kind": "expense", "budgeted_amount": "99.50", "notes": "New budget"},
        ]

        imported_count, skipped_count = self.controller.import_budget_rows_for_month(
            year=2026,
            month=6,
            rows=rows,
            replace_existing=True,
        )

        self.assertEqual(imported_count, 1)
        self.assertEqual(skipped_count, 0)
        budgets = self.repository.list_budgets_for_month(2026, 6)
        self.assertEqual(len(budgets), 1)
        self.assertEqual(budgets[0].category, "New")


if __name__ == "__main__":
    unittest.main()
