import unittest

from dependency.services.demo_reset import reset_demo_state
from dependency.services.state_updates import update_setup_lead_time
from dependency.solver.recovery import plan_sku_recovery
from dependency.solver.transport_feasibility import evaluate_recovery_transport


class TransportFeasibilityTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"
    SKU = "JI2993"
    BACKUP = "ADI26-0240"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_independent_backup_has_explicit_on_time_recovery_routes(self):
        result = evaluate_recovery_transport(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            origin_facility_id=self.BACKUP,
        )
        self.assertEqual(result["decision"], "ALL_COMMITMENTS_REACHABLE")
        self.assertEqual(result["on_time_commitment_units"], 9500.0)
        self.assertEqual(result["uncovered_commitment_units"], 0.0)
        self.assertGreater(
            result["estimated_transport_cost_eur_if_all_on_time_routes_used"],
            0,
        )
        self.assertTrue(
            all(
                row["best_on_time_lane"] is not None
                for row in result["commitments"]
            )
        )

    def test_recovery_capacity_is_not_counted_without_on_time_transport(self):
        update_setup_lead_time(
            sku=self.SKU,
            facility_id=self.BACKUP,
            setup_lead_days=8,
        )

        transport = evaluate_recovery_transport(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            origin_facility_id=self.BACKUP,
        )
        self.assertEqual(transport["decision"], "NO_ON_TIME_TRANSPORT")
        self.assertEqual(transport["on_time_commitment_units"], 0.0)

        plan = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
        )
        self.assertIsNone(plan["selected_backup"])
        self.assertEqual(plan["backup_available_units"], 0.0)
        self.assertEqual(plan["shortage_units"], 7900.0)


if __name__ == "__main__":
    unittest.main()
