import unittest

from dependency.automation.orchestrator import process_pending_events
from dependency.db.connection import connect
from dependency.events.bus import TOPIC_EXTERNAL_EVENTS, enqueue
from dependency.services.demo_reset import reset_demo_state
from dependency.services.state_updates import update_inventory


class AutomationOrchestratorTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def _drain(self):
        for _ in range(10):
            result = process_pending_events(limit=200)
            if result["attempted"] == 0:
                return
        self.fail("local orchestrator did not drain within 10 passes")

    def test_external_event_creates_one_incident_and_persists_portfolio_plans(self):
        outbox_id = enqueue(
            topic=TOPIC_EXTERNAL_EVENTS,
            event_key=self.EVENT_ID,
            payload={"event_id": self.EVENT_ID},
        )

        first = process_pending_events(limit=50)
        self.assertGreaterEqual(first["succeeded"], 1)

        with connect() as conn:
            consumption = conn.execute(
                """
                SELECT status
                FROM event_consumptions
                WHERE consumer_name='incident-orchestrator' AND outbox_id=%s
                """,
                (outbox_id,),
            ).fetchone()
            incidents = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE event_id=%s",
                (self.EVENT_ID,),
            ).fetchone()[0]
            plans = conn.execute(
                "SELECT COUNT(*) FROM incident_plan_history"
            ).fetchone()[0]

        self.assertEqual(consumption[0], "SUCCESS")
        self.assertEqual(incidents, 1)
        self.assertGreater(plans, 0)

        self._drain()

        with connect() as conn:
            incidents_after = conn.execute(
                "SELECT COUNT(*) FROM incidents WHERE event_id=%s",
                (self.EVENT_ID,),
            ).fetchone()[0]
        self.assertEqual(incidents_after, 1)

    def test_plan_invalidation_replans_open_incident_at_new_state_version(self):
        enqueue(
            topic=TOPIC_EXTERNAL_EVENTS,
            event_key=self.EVENT_ID,
            payload={"event_id": self.EVENT_ID},
        )
        self._drain()

        update = update_inventory(
            site_id="WH-EU",
            item_type="finished_good",
            item_id="JI2993",
            qty_on_hand=1100,
            qty_reserved=0,
            safety_stock=500,
        )
        self.assertEqual(update["state_version"], 2)

        self._drain()

        with connect() as conn:
            replans = conn.execute(
                """
                SELECT COUNT(*)
                FROM incident_plan_history
                WHERE sku='JI2993' AND state_version=2
                """
            ).fetchone()[0]
            invalidations = conn.execute(
                """
                SELECT COUNT(*)
                FROM event_consumptions c
                JOIN event_outbox o ON o.outbox_id=c.outbox_id
                WHERE c.consumer_name='incident-orchestrator'
                  AND o.topic='plan.invalidated'
                  AND c.status='SUCCESS'
                """
            ).fetchone()[0]

        self.assertGreater(replans, 0)
        self.assertGreaterEqual(invalidations, 1)


if __name__ == "__main__":
    unittest.main()
