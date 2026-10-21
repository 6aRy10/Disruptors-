"""Regression for nested safety-stock evidence in the recovery contract."""
from __future__ import annotations

import unittest

from dependency.solver.recovery import plan_sku_recovery


class RehearsalRecoveryContractTests(unittest.TestCase):
    def test_emergency_plan_reports_safety_stock_in_inventory(self):
        result = plan_sku_recovery(
            scenario_id="SCN-CIANJUR-REPLAY-01",
            sku="JI2993",
            release_safety_stock=True,
        )
        self.assertIn("inventory", result)
        self.assertIn("safety_stock_used_units", result["inventory"])
        self.assertGreaterEqual(result["inventory"]["safety_stock_used_units"], 0)
        self.assertIn("requires_planner_approval", result)


if __name__ == "__main__":
    unittest.main()
