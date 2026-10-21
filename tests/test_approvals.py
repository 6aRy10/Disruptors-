import unittest

from dependency.db.connection import connect
from dependency.incidents.triage import triage_event
from dependency.services.approvals import (
    decide_approval,
    list_approval_requests,
    request_human_approval,
)
from dependency.services.demo_reset import reset_demo_state


class ApprovalWorkflowTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_human_approval_is_durable_and_does_not_execute_action(self):
        triage = triage_event(event_id=self.EVENT_ID, radius_km=150)
        incident_id = triage["incident"]["incident_id"]

        request = request_human_approval(
            incident_id=incident_id,
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            action_type="RELEASE_SAFETY_STOCK",
            action_payload={"units": 400},
            reason="Emergency plan needs protected inventory.",
            requested_by="Recovery Planner",
        )
        self.assertEqual(request["status"], "PENDING")

        pending = list_approval_requests(
            status="PENDING",
            incident_id=incident_id,
        )
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["action_payload"]["units"], 400)

        with connect() as conn:
            before = conn.execute(
                """
                SELECT qty_on_hand,qty_reserved,safety_stock
                FROM inventory
                WHERE site_id='WH-EU'
                  AND item_type='finished_good'
                  AND item_id='JI2993'
                """
            ).fetchone()

        decision = decide_approval(
            request_id=request["request_id"],
            decision="APPROVED",
            decided_by="Judge",
            decision_reason="Approve emergency release for this scenario.",
        )
        self.assertEqual(decision["status"], "APPROVED")
        self.assertEqual(
            decision["execution_status"],
            "APPROVAL_RECORDED_ACTION_NOT_EXECUTED",
        )

        with connect() as conn:
            after = conn.execute(
                """
                SELECT qty_on_hand,qty_reserved,safety_stock
                FROM inventory
                WHERE site_id='WH-EU'
                  AND item_type='finished_good'
                  AND item_id='JI2993'
                """
            ).fetchone()
            decisions = conn.execute(
                """
                SELECT COUNT(*)
                FROM incident_decisions
                WHERE incident_id=%s
                  AND action='APPROVED:RELEASE_SAFETY_STOCK'
                """,
                (incident_id,),
            ).fetchone()[0]
            topics = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT topic
                    FROM event_outbox
                    WHERE topic IN ('approval.requested','decision.confirmed')
                    """
                ).fetchall()
            }

        self.assertEqual(before, after)
        self.assertEqual(decisions, 1)
        self.assertEqual(
            topics,
            {"approval.requested", "decision.confirmed"},
        )

    def test_decision_is_idempotent_after_request_is_closed(self):
        triage = triage_event(event_id=self.EVENT_ID, radius_km=150)
        incident_id = triage["incident"]["incident_id"]
        request = request_human_approval(
            incident_id=incident_id,
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            action_type="RELEASE_SAFETY_STOCK",
            action_payload={"units": 400},
            reason="Need approval.",
        )
        first = decide_approval(
            request_id=request["request_id"],
            decision="REJECTED",
            decided_by="Planner",
            decision_reason="Preserve emergency buffer.",
        )
        second = decide_approval(
            request_id=request["request_id"],
            decision="APPROVED",
            decided_by="Another Planner",
            decision_reason="Attempted overwrite.",
        )

        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(second["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
