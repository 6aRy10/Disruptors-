import unittest

from dependency.solver.recovery import plan_sku_recovery


class RecoveryPlanTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def test_initial_ji2993_plan_is_feasible_but_stale(self):
        plan = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        self.assertEqual(plan["demand_units"], 9500)
        self.assertEqual(plan["selected_backup"]["facility_id"], "ADI26-0240")
        self.assertEqual(plan["backup_available_units"], 7500.0)
        self.assertEqual(plan["total_available_units"], 9600.0)
        self.assertEqual(plan["shortage_units"], 0.0)
        self.assertTrue(plan["requires_supplier_confirmation"])
        self.assertEqual(plan["plan_status"], "PROVISIONAL_AWAITING_CONFIRMATION")

    def test_primary_and_nominal_backup_are_unavailable_in_replay(self):
        plan = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        states = {r["facility_id"]: r["scenario_status"] for r in plan["current_production"]}
        self.assertEqual(states["ADI26-0226"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
