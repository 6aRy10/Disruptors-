import unittest

from dependency.db.connection import connect
from dependency.services.demo_reset import reset_demo_state
from dependency.services.state_updates import (
    update_inventory,
    update_setup_lead_time,
    update_substitution_approval,
)
from dependency.solver.candidates import generate_recovery_candidates
from dependency.solver.recovery import plan_sku_recovery


class JudgeEditTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def test_judge_edits_invalidate_state_and_reset_cleanly(self):
        reset_demo_state()

        baseline = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            release_safety_stock=False,
        )
        self.assertEqual(baseline["state_version"], 1)
        self.assertEqual(baseline["shortage_units"], 400.0)

        inv = update_inventory(
            site_id="WH-EU",
            item_type="finished_good",
            item_id="JI2993",
            qty_on_hand=1100,
            qty_reserved=0,
            safety_stock=500,
        )
        self.assertEqual(inv["state_version"], 2)

        after_inventory = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            release_safety_stock=False,
        )
        self.assertEqual(after_inventory["total_available_units"], 8100.0)
        self.assertEqual(after_inventory["shortage_units"], 1400.0)

        lead = update_setup_lead_time(
            sku="JI2993",
            facility_id="ADI26-0240",
            setup_lead_days=10,
        )
        self.assertEqual(lead["state_version"], 3)

        after_lead = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            release_safety_stock=False,
        )
        self.assertIsNone(after_lead["selected_backup"])
        self.assertEqual(after_lead["total_available_units"], 600.0)
        self.assertEqual(after_lead["shortage_units"], 8900.0)

        sub = update_substitution_approval(
            material_id="MAT-RUBBER-OUTSOLE",
            substitute_material_id="MAT-RUBBER-OUTSOLE-B",
            approved=True,
            engineering_status="APPROVED",
        )
        self.assertEqual(sub["state_version"], 4)

        plans = generate_recovery_candidates(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        substitute = next(
            p
            for p in plans
            if p["plan_type"] == "MATERIAL_SUBSTITUTION"
            and p["evidence"]["material_id"] == "MAT-RUBBER-OUTSOLE"
        )
        self.assertEqual(substitute["decision"], "CONDITIONALLY_FEASIBLE")

        with connect() as conn:
            pending = conn.execute(
                """
                SELECT COUNT(*)
                FROM event_outbox
                WHERE published_at IS NULL
                  AND topic IN ('business.state.updated','plan.invalidated')
                """
            ).fetchone()[0]
        self.assertGreaterEqual(pending, 6)

        reset = reset_demo_state()
        self.assertEqual(reset["state_version"], 1)

        restored = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            release_safety_stock=False,
        )
        self.assertEqual(restored["state_version"], 1)
        self.assertEqual(restored["shortage_units"], 400.0)

        restored_plans = generate_recovery_candidates(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        restored_substitute = next(
            p
            for p in restored_plans
            if p["plan_type"] == "MATERIAL_SUBSTITUTION"
            and p["evidence"]["material_id"] == "MAT-RUBBER-OUTSOLE"
        )
        self.assertEqual(restored_substitute["decision"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
