from __future__ import annotations

import unittest

from finance_app.services.budget_reallocator import generate_reallocation_plan, solve_budget_constraints


class BudgetReallocatorTests(unittest.TestCase):
    def test_generate_reallocation_plan_requires_minimum_history(self) -> None:
        payload = {
            "reference_year": 2026,
            "reference_month": 6,
            "target_year": 2026,
            "target_month": 7,
            "min_history_months": 3,
            "history_available_months": 2,
            "inputs": {
                "income_series": [5000.0, 5200.0],
                "recurring_fixed_expenses": [{"category": "Mortgage", "amount": 1800.0}],
                "savings_goal": 500.0,
                "category_history": [],
            },
        }

        result = generate_reallocation_plan(payload)

        self.assertEqual(result.get("status"), "insufficient_history")
        self.assertEqual(result.get("min_history_months"), 3)
        self.assertEqual(result.get("history_available_months"), 2)

    def test_solve_budget_constraints_matches_target_budget(self) -> None:
        preliminary = {
            "Groceries": 420.0,
            "Dining": 260.0,
            "Entertainment": 180.0,
        }
        caps_floors = {
            "Groceries": {"floor": 350.0, "cap": 500.0},
            "Dining": {"floor": 100.0, "cap": 300.0},
            "Entertainment": {"floor": 50.0, "cap": 250.0},
        }

        solved, flags = solve_budget_constraints(
            preliminary=preliminary,
            target_budget=900.0,
            caps_floors=caps_floors,
            safety_context={},
        )

        self.assertAlmostEqual(sum(solved.values()), 900.0, places=2)
        self.assertGreaterEqual(solved["Groceries"], 350.0)
        self.assertLessEqual(solved["Groceries"], 500.0)
        self.assertIn("Dining", solved)
        self.assertIsInstance(flags, list)

    def test_generate_reallocation_plan_returns_goal_message_when_ready(self) -> None:
        payload = {
            "reference_year": 2026,
            "reference_month": 6,
            "target_year": 2026,
            "target_month": 7,
            "min_history_months": 3,
            "history_available_months": 6,
            "inputs": {
                "income_series": [6200.0, 6300.0, 6400.0, 6350.0, 6420.0, 6480.0],
                "recurring_fixed_expenses": [{"category": "Mortgage", "amount": 1800.0}],
                "savings_goal": 900.0,
                "forecast_config": {
                    "alpha": 0.6,
                    "beta": 0.75,
                    "weights": [0.2, 0.3, 0.5],
                    "increase_gate_threshold": 0.65,
                },
                "category_caps_floors": {
                    "Dining": {"floor": 100.0, "cap": 320.0},
                    "Entertainment": {"floor": 80.0, "cap": 260.0},
                },
                "category_history": [
                    {
                        "category": "Dining",
                        "current_budget": 240.0,
                        "monthly_spend": [250.0, 260.0, 280.0, 290.0, 300.0, 320.0],
                        "overspent_recently": True,
                        "is_critical": False,
                    },
                    {
                        "category": "Entertainment",
                        "current_budget": 220.0,
                        "monthly_spend": [180.0, 190.0, 210.0, 230.0, 240.0, 245.0],
                        "overspent_recently": True,
                        "is_critical": False,
                    },
                ],
            },
        }

        result = generate_reallocation_plan(payload)

        self.assertEqual(result.get("status"), "ready")
        self.assertTrue(str(result.get("goal_message", "")).strip())
        self.assertIsInstance(result.get("recommendations"), list)


if __name__ == "__main__":
    unittest.main()
