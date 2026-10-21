import unittest

from dependency.solver.recovery import plan_sku_recovery


class RecoveryPlanTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def test_initial_plan_preserves_safety_stock_by_default(self):
        plan = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        self.assertEqual(plan["demand_units"], 9500)
        self.assertEqual(plan["selected_backup"]["facility_id"], "ADI26-0240")
        self.assertEqual(plan["backup_available_units"], 7500.0)
        self.assertEqual(plan["total_available_units"], 9100.0)
        self.assertEqual(plan["shortage_units"], 400.0)
        self.assertTrue(plan["requires_supplier_confirmation"])
        self.assertFalse(plan["requires_planner_approval"])
        self.assertEqual(plan["plan_status"], "PROVISIONAL_SHORTAGE")

    def test_emergency_safety_stock_release_can_cover_initial_gap(self):
        plan = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            release_safety_stock=True,
        )
        self.assertEqual(plan["total_available_units"], 9600.0)
        self.assertEqual(plan["shortage_units"], 0.0)
        self.assertEqual(plan["inventory"]["safety_stock_used_units"], 400.0)
        self.assertTrue(plan["requires_planner_approval"])

    def test_primary_is_unavailable_in_replay(self):
        plan = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        states = {
            r["facility_id"]: r["scenario_status"]
            for r in plan["current_production"]
        }
        self.assertEqual(states["ADI26-0226"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
