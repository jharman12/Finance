from __future__ import annotations

from pathlib import Path
import re
import unittest


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_main_window_budget_calls_use_controller(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        forbidden_snippets = [
            "self.repository.list_budgets_for_month",
            "self.repository.add_or_update_budget",
            "self.repository.delete_budget",
            "self.repository.get_monthly_savings_goal",
            "self.repository.set_monthly_savings_goal",
            "self.repository.get_projected_recurring_totals_for_month",
            "self.repository.list_budget_reallocation_audits",
        ]

        for snippet in forbidden_snippets:
            self.assertNotIn(snippet, content, msg=f"Budget boundary violation found: {snippet}")

    def test_storage_analytics_methods_delegate(self) -> None:
        root = Path(__file__).resolve().parents[1]
        storage_file = root / "finance_app" / "storage.py"
        content = storage_file.read_text(encoding="utf-8")

        expected_delegations = [
            "return self._analytics_repository.daily_totals_for_month(year, month)",
            "return self._analytics_repository.expense_breakdown_for_month(year, month)",
            "return self._analytics_repository.snapshot()",
            "return self._analytics_repository.snapshot_for_month(year, month)",
            "return self._analytics_repository.monthly_history(reference_year, reference_month, months=months)",
            "return self._analytics_repository.personal_position_history(reference_year, reference_month, months)",
        ]

        for snippet in expected_delegations:
            self.assertIn(snippet, content)

    def test_main_window_recurring_calls_use_controller(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        forbidden_snippets = [
            "self.repository.add_recurring_item",
            "self.repository.list_recurring_items",
            "self.repository.update_recurring_item",
            "self.repository.delete_recurring_item",
            "self.repository.get_expense_asset_link(\"recurring\"",
            "self.repository.set_expense_asset_link(",
            "self.repository.change_transaction_category(",
        ]

        for snippet in forbidden_snippets:
            self.assertNotIn(snippet, content, msg=f"Recurring boundary violation found: {snippet}")

    def test_budget_month_csv_handlers_do_not_call_repository_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        method_names = ["_export_budget_month_csv", "_import_budget_month_csv"]
        for method_name in method_names:
            method_pattern = rf"def {method_name}\(self\) -> None:\n(?:[ \t]+.*\n)+"
            match = re.search(method_pattern, content)
            self.assertIsNotNone(match, msg=f"Could not locate method body for {method_name}")
            method_body = match.group(0) if match else ""
            self.assertNotIn(
                "self.repository.",
                method_body,
                msg=f"Budget CSV handler boundary violation found in {method_name}",
            )

    def test_category_manager_handlers_do_not_call_repository_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        method_names = [
            "_open_category_manager",
            "_add_category_from_dialog",
            "_delete_category_from_dialog",
        ]
        for method_name in method_names:
            method_pattern = rf"def {method_name}\(.*\) -> None:\n(?:[ \t]+.*\n)+"
            match = re.search(method_pattern, content)
            self.assertIsNotNone(match, msg=f"Could not locate method body for {method_name}")
            method_body = match.group(0) if match else ""
            self.assertNotIn(
                "self.repository.",
                method_body,
                msg=f"Category manager boundary violation found in {method_name}",
            )

    def test_asset_handlers_do_not_call_repository_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        method_names = [
            "_handle_asset_selection_changed",
            "_save_selected_asset_details",
            "_cancel_asset_edit",
            "_delete_selected_asset",
            "_record_investment_value_snapshot",
            "_refresh_investment_snapshots",
            "_refresh_asset_links_views",
            "_link_selected_transaction_expense",
            "_link_selected_recurring_expense",
            "_unlink_selected_asset_expense",
            "_build_asset_payment_events",
            "refresh_assets",
            "_refresh_asset_link_entry_controls",
        ]
        for method_name in method_names:
            method_pattern = rf"def {method_name}\(.*\)(?: -> [^:]+)?:\n(?:[ \t]+.*\n)+"
            match = re.search(method_pattern, content)
            self.assertIsNotNone(match, msg=f"Could not locate method body for {method_name}")
            method_body = match.group(0) if match else ""
            self.assertNotIn(
                "self.repository.",
                method_body,
                msg=f"Asset boundary violation found in {method_name}",
            )

    def test_transaction_handlers_do_not_call_repository_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        method_names = [
            "refresh_category_controls",
            "refresh_ledger_tables",
            "_add_transaction",
            "edit_selected_recent_transaction",
            "delete_selected_transaction",
        ]
        for method_name in method_names:
            method_pattern = rf"def {method_name}\([\s\S]*?\)(?: -> [^:]+)?:\n(?:[ \t]+.*\n)+"
            match = re.search(method_pattern, content, flags=re.MULTILINE)
            self.assertIsNotNone(match, msg=f"Could not locate method body for {method_name}")
            method_body = match.group(0) if match else ""
            self.assertNotIn(
                "self.repository.",
                method_body,
                msg=f"Transaction boundary violation found in {method_name}",
            )

    def test_analytics_handlers_do_not_call_repository_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        method_names = [
            "refresh_dashboard",
            "refresh_charts",
        ]
        for method_name in method_names:
            method_pattern = rf"def {method_name}\(.*\)(?: -> [^:]+)?:\n(?:[ \t]+.*\n)+"
            match = re.search(method_pattern, content)
            self.assertIsNotNone(match, msg=f"Could not locate method body for {method_name}")
            method_body = match.group(0) if match else ""
            self.assertNotIn(
                "self.repository.",
                method_body,
                msg=f"Analytics boundary violation found in {method_name}",
            )

    def test_app_settings_handlers_do_not_call_repository_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        method_names = [
            "_handle_export_csv",
            "_handle_import_csv",
            "_load_ui_scale_setting",
            "_load_ui_density_setting",
            "_apply_ui_scale",
            "_set_density_mode",
            "_handle_model_changed",
        ]
        for method_name in method_names:
            method_pattern = rf"def {method_name}\([\s\S]*?\)(?: -> [^:]+)?:\n(?:[ \t]+.*\n)+"
            match = re.search(method_pattern, content, flags=re.MULTILINE)
            self.assertIsNotNone(match, msg=f"Could not locate method body for {method_name}")
            method_body = match.group(0) if match else ""
            self.assertNotIn(
                "self.repository.",
                method_body,
                msg=f"App settings boundary violation found in {method_name}",
            )

    def test_period_handlers_do_not_call_repository_directly(self) -> None:
        root = Path(__file__).resolve().parents[1]
        main_window = root / "finance_app" / "ui" / "main_window.py"
        content = main_window.read_text(encoding="utf-8")

        method_names = [
            "refresh_all",
            "_handle_period_changed",
            "_handle_chart_period_changed",
        ]
        for method_name in method_names:
            method_pattern = rf"def {method_name}\([\s\S]*?\)(?: -> [^:]+)?:\n(?:[ \t]+.*\n)+"
            match = re.search(method_pattern, content, flags=re.MULTILINE)
            self.assertIsNotNone(match, msg=f"Could not locate method body for {method_name}")
            method_body = match.group(0) if match else ""
            self.assertNotIn(
                "self.repository.",
                method_body,
                msg=f"Period handler boundary violation found in {method_name}",
            )


if __name__ == "__main__":
    unittest.main()
