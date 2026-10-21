import unittest

from dependency.db.connection import connect
from dependency.incidents.triage import triage_event
from dependency.services.approvals import decide_approval, request_human_approval
from dependency.services.demo_reset import reset_demo_state
from dependency.services.execution import execute_approved_action


class ApprovedActionExecutionTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def _incident_id(self):
        triage = triage_event(event_id=self.EVENT_ID, radius_km=150)
        return triage["incident"]["incident_id"]

    def test_approved_safety_stock_release_executes_once_and_invalidates_plan(self):
        incident_id = self._incident_id()
        request = request_human_approval(
            incident_id=incident_id,
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            action_type="RELEASE_SAFETY_STOCK",
            action_payload={
                "site_id": "WH-EU",
                "item_type": "finished_good",
                "item_id": "JI2993",
                "units": 400,
            },
            reason="Protect priority commitments during confirmed disruption.",
            requested_by="Recovery Planner",
        )
        decide_approval(
            request_id=request["request_id"],
            decision="APPROVED",
            decided_by="Judge",
            decision_reason="Release 400 units of the protected buffer.",
        )

        first = execute_approved_action(
            request_id=request["request_id"],
            executed_by="Judge",
        )
        self.assertEqual(first["status"], "SUCCEEDED")
        self.assertFalse(first["already_executed"])
        self.assertEqual(
            first["result"]["new_safety_stock_units"],
            100.0,
        )
        self.assertEqual(
            first["result"]["state_update"]["state_version"],
            2,
        )

        second = execute_approved_action(
            request_id=request["request_id"],
            executed_by="Judge",
        )
        self.assertTrue(second["already_executed"])

        with connect() as conn:
            inventory = conn.execute(
                """
                SELECT safety_stock
                FROM inventory
                WHERE site_id='WH-EU'
                  AND item_type='finished_good'
                  AND item_id='JI2993'
                """
            ).fetchone()[0]
            version = conn.execute(
                "SELECT version FROM operational_state_version WHERE singleton=true"
            ).fetchone()[0]
            execution_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM action_executions
                WHERE approval_request_id=%s
                """,
                (request["request_id"],),
            ).fetchone()[0]
            invalidations = conn.execute(
                """
                SELECT COUNT(*)
                FROM event_outbox
                WHERE topic='plan.invalidated'
                  AND payload->>'sku'='JI2993'
                  AND (payload->>'new_state_version')::int=2
                """
            ).fetchone()[0]

        self.assertEqual(float(inventory), 100.0)
        self.assertEqual(int(version), 2)
        self.assertEqual(execution_count, 1)
        self.assertGreaterEqual(invalidations, 1)

    def test_rejected_action_cannot_execute(self):
        incident_id = self._incident_id()
        request = request_human_approval(
            incident_id=incident_id,
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            action_type="RELEASE_SAFETY_STOCK",
            action_payload={
                "site_id": "WH-EU",
                "item_id": "JI2993",
                "units": 400,
            },
            reason="Test rejection.",
        )
        decide_approval(
            request_id=request["request_id"],
            decision="REJECTED",
            decided_by="Judge",
            decision_reason="Preserve the emergency buffer.",
        )

        with self.assertRaises(ValueError):
            execute_approved_action(
                request_id=request["request_id"],
                executed_by="Judge",
            )

        with connect() as conn:
            version = conn.execute(
                "SELECT version FROM operational_state_version WHERE singleton=true"
            ).fetchone()[0]
            count = conn.execute(
                "SELECT COUNT(*) FROM action_executions"
            ).fetchone()[0]

        self.assertEqual(int(version), 1)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
