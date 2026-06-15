from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from finance_app.services.assistant_service import AssistantService
from finance_app.storage import FinanceRepository


class FakeOllamaClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def chat(self, messages, json_mode: bool = True):  # noqa: ANN001
        self.calls += 1
        if not self._responses:
            raise RuntimeError("No fake responses left")
        return self._responses.pop(0)


class Phase0RecurringMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._temp_dir.name) / "phase0_recurring.db"
        self.repo = FinanceRepository(database_path=db_path)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _transaction_count(self) -> int:
        with self.repo._connection() as conn:  # noqa: SLF001
            row = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()
        return int(row["n"])

    def test_list_transactions_for_month_is_read_only_without_explicit_materialize(self) -> None:
        today = date.today()
        self.repo.add_recurring_item(
            kind="expense",
            amount=25.0,
            category="Groceries",
            description="Phase0 recurring",
            interval_count=1,
            interval_unit="months",
            start_on=today,
            is_active=True,
        )

        self.assertEqual(self._transaction_count(), 0)

        rows_first = self.repo.list_transactions_for_month(today.year, today.month, limit=100)
        self.assertEqual(self._transaction_count(), 0)
        self.assertEqual(len([t for t in rows_first if t.description == "Phase0 recurring"]), 0)

        generated = self.repo.materialize_due_recurring_items()
        self.assertEqual(generated, 1)

        rows_after = self.repo.list_transactions_for_month(today.year, today.month, limit=100)
        self.assertEqual(self._transaction_count(), 1)
        self.assertEqual(len([t for t in rows_after if t.description == "Phase0 recurring"]), 1)

        rows_second = self.repo.list_transactions_for_month(today.year, today.month, limit=100)
        self.assertEqual(self._transaction_count(), 1)
        self.assertEqual(len([t for t in rows_second if t.description == "Phase0 recurring"]), 1)

    def test_expense_breakdown_for_month_is_read_only_without_explicit_materialize(self) -> None:
        today = date.today()
        self.repo.add_recurring_item(
            kind="expense",
            amount=18.0,
            category="Dining",
            description="Breakdown recurring",
            interval_count=1,
            interval_unit="months",
            start_on=today,
            is_active=True,
        )

        before = self.repo.expense_breakdown_for_month(today.year, today.month)
        self.assertEqual(self._transaction_count(), 0)
        self.assertTrue(all(category != "Dining" for category, _ in before))

        generated = self.repo.materialize_due_recurring_items()
        self.assertEqual(generated, 1)

        after = self.repo.expense_breakdown_for_month(today.year, today.month)
        self.assertEqual(self._transaction_count(), 1)
        self.assertTrue(any(category == "Dining" for category, _ in after))

    def test_snapshot_for_month_is_read_only_without_explicit_materialize(self) -> None:
        today = date.today()
        self.repo.add_recurring_item(
            kind="expense",
            amount=33.0,
            category="Groceries",
            description="Snapshot recurring",
            interval_count=1,
            interval_unit="months",
            start_on=today,
            is_active=True,
        )

        snapshot_before = self.repo.snapshot_for_month(today.year, today.month)
        self.assertEqual(self._transaction_count(), 0)
        self.assertEqual(snapshot_before.transaction_count, 0)

        generated = self.repo.materialize_due_recurring_items()
        self.assertEqual(generated, 1)

        snapshot_after = self.repo.snapshot_for_month(today.year, today.month)
        self.assertEqual(self._transaction_count(), 1)
        self.assertEqual(snapshot_after.transaction_count, 1)

    def test_snapshot_is_read_only_without_explicit_materialize(self) -> None:
        today = date.today()
        self.repo.add_recurring_item(
            kind="expense",
            amount=41.0,
            category="Utilities",
            description="Snapshot global recurring",
            interval_count=1,
            interval_unit="months",
            start_on=today,
            is_active=True,
        )

        snapshot_before = self.repo.snapshot()
        self.assertEqual(self._transaction_count(), 0)
        self.assertEqual(snapshot_before.transaction_count, 0)

        generated = self.repo.materialize_due_recurring_items()
        self.assertEqual(generated, 1)

        snapshot_after = self.repo.snapshot()
        self.assertEqual(self._transaction_count(), 1)
        self.assertEqual(snapshot_after.transaction_count, 1)

    def test_daily_totals_for_month_is_read_only_without_explicit_materialize(self) -> None:
        today = date.today()
        self.repo.add_recurring_item(
            kind="expense",
            amount=27.0,
            category="Dining",
            description="Daily totals recurring",
            interval_count=1,
            interval_unit="months",
            start_on=today,
            is_active=True,
        )

        totals_before = self.repo.daily_totals_for_month(today.year, today.month)
        expense_before = sum(entry[2] for entry in totals_before)
        self.assertEqual(self._transaction_count(), 0)
        self.assertEqual(expense_before, 0.0)

        generated = self.repo.materialize_due_recurring_items()
        self.assertEqual(generated, 1)

        totals_after = self.repo.daily_totals_for_month(today.year, today.month)
        expense_after = sum(entry[2] for entry in totals_after)
        self.assertEqual(self._transaction_count(), 1)
        self.assertGreater(expense_after, 0.0)


class Phase0AssistantActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self._temp_dir.name) / "phase0_assistant.db"
        self.repo = FinanceRepository(database_path=db_path)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_handle_prompt_applies_add_expense_action(self) -> None:
        payload = {
            "reply": "Added your expense.",
            "actions": [
                {
                    "type": "add_expense",
                    "payload": {
                        "amount": 12.5,
                        "category": "Dining",
                        "description": "Lunch",
                        "occurred_on": date.today().isoformat(),
                    },
                }
            ],
        }
        fake_client = FakeOllamaClient([json.dumps(payload)])
        service = AssistantService(repository=self.repo, client=fake_client)

        result = service.handle_prompt("Add lunch expense")

        self.assertTrue(any(msg.startswith("Added expense #") for msg in result.applied_actions))
        tx_rows = self.repo.list_transactions(limit=20)
        self.assertEqual(len(tx_rows), 1)
        self.assertEqual(tx_rows[0].description, "Lunch")

    def test_handle_prompt_retries_when_mutation_has_no_actions(self) -> None:
        first_payload = {"reply": "I will create it.", "actions": []}
        second_payload = {
            "reply": "Created category.",
            "actions": [
                {"type": "add_category", "payload": {"name": "Coffee", "kind": "expense"}}
            ],
        }
        fake_client = FakeOllamaClient([json.dumps(first_payload), json.dumps(second_payload)])
        service = AssistantService(repository=self.repo, client=fake_client)

        result = service.handle_prompt("Create a coffee category")

        self.assertGreaterEqual(fake_client.calls, 2)
        self.assertIn("Added category Coffee", result.applied_actions)
        expense_categories = [c.name for c in self.repo.list_categories(kind="expense")]
        self.assertIn("Coffee", expense_categories)

    def test_show_table_action_returns_table_payload(self) -> None:
        future_start = date.today() + timedelta(days=14)
        self.repo.add_recurring_item(
            kind="expense",
            amount=55.0,
            category="Utilities",
            description="Future utility",
            interval_count=1,
            interval_unit="months",
            start_on=future_start,
            is_active=True,
        )

        payload = {
            "reply": "Here is the table.",
            "actions": [
                {
                    "type": "show_table",
                    "payload": {
                        "table": "upcoming_recurring",
                        "kind": "expense",
                        "status": "not_occurred_yet",
                    },
                }
            ],
        }

        fake_client = FakeOllamaClient([json.dumps(payload)])
        service = AssistantService(repository=self.repo, client=fake_client)

        result = service.handle_prompt("Show upcoming recurring expenses")

        self.assertEqual(len(result.display_tables), 1)
        table = result.display_tables[0]
        self.assertEqual(table.get("title"), "Upcoming Recurring Items")
        self.assertTrue(any("Future utility" in str(row) for row in table.get("rows", [])))


if __name__ == "__main__":
    unittest.main()
