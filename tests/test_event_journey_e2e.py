"""End-to-end event receipt -> outbox -> local worker -> investigation -> evidence.

Runs ONLY in disposable CI PostgreSQL. Refuses to mutate a user's database.
The synthetic earthquake is never represented as a live public observation.
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from dependency.db.connection import connect
from dependency.ingest.events import upsert_external_event
from dependency.graph.event_journey import event_journey
from dependency.automation.orchestrator import (
    DEFAULT_CONSUMER, process_event_envelope,
)
from dependency.services.demo_reset import reset_demo_state


class EventJourneyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("HERMES_CI_DISPOSABLE_DB") != "1":
            raise unittest.SkipTest(
                "Destructive integration fixture only runs in disposable CI database."
            )

    def setUp(self):
        self.event_id = "TEST-JOURNEY-" + str(uuid4())

    def tearDown(self):
        # Reset is permitted only under the disposable-CI guard above.
        reset_demo_state()
        with connect() as conn:
            conn.execute("DELETE FROM external_events WHERE event_id=%s", (self.event_id,))
            conn.commit()

    def _ingest(self, latitude, longitude):
        return upsert_external_event({
            "event_id": self.event_id,
            "event_type": "earthquake",
            "source": "SIMULATED_CI_EVENT",
            "title": "Independent synthetic source receipt",
            "latitude": latitude, "longitude": longitude,
            "occurred_at_iso": "2022-11-21T05:21:00+00:00",
            "provenance_class": "SIMULATED_PRIVATE",
            "raw_json": {"test_only": True, "never_public_disaster": True},
        }, mode="REPLAY")

    def _outbox(self):
        with connect() as conn:
            return conn.execute(
                """SELECT outbox_id,payload FROM event_outbox
                   WHERE topic='external.events' AND event_key=%s""",
                (self.event_id,),
            ).fetchone()

    def _deliver(self, radius_km):
        oid, payload = self._outbox()
        return process_event_envelope(
            consumer_name=DEFAULT_CONSUMER, outbox_id=oid,
            topic="external.events", payload=payload,
            run_agents=False, radius_km=radius_km,
        )

    def test_unfamiliar_event_records_entire_explainable_lifecycle(self):
        with connect() as conn:
            site = conn.execute(
                """SELECT ST_Y(nf.geom::geometry),ST_X(nf.geom::geometry)
                   FROM network_facilities nf
                   JOIN facility_network_links fnl
                     ON fnl.network_facility_id=nf.network_facility_id
                   JOIN product_facilities pf ON pf.facility_id=fnl.facility_id
                   WHERE nf.geom IS NOT NULL
                   ORDER BY nf.network_facility_id,pf.sku LIMIT 1"""
            ).fetchone()
        self.assertIsNotNone(site)
        created = self._ingest(float(site[0]), float(site[1]))
        self.assertTrue(created["created"])

        before = event_journey(event_id=self.event_id)
        self.assertEqual(before["event"]["provenance_class"], "SIMULATED_PRIVATE")
        self.assertEqual(before["outbox"]["local_processing"], "PENDING")
        self.assertEqual(
            [s["key"] for s in before["steps"]],
            ["observation", "receipt", "processing", "investigation", "evidence", "decision"],
        )
        first_receipt = before["outbox"]["first_recorded_at"]
        self.assertIsNotNone(first_receipt)
        self.assertNotEqual(before["event"]["occurred_at"], first_receipt)

        handled = self._deliver(radius_km=5.0)
        self.assertEqual(handled["status"], "SUCCESS")
        self.assertEqual(handled["result"]["status"], "INVESTIGATION_REQUIRED")
        after = event_journey(event_id=self.event_id)
        self.assertEqual(after["outbox"]["local_processing"], "SUCCESS")
        self.assertEqual(after["outbox"]["worker_outcome"], "INVESTIGATION_REQUIRED")
        self.assertEqual(after["next_action"]["code"], "VERIFY_OPERATIONS")
        self.assertIsNotNone(after["incident_id"])
        self.assertIsNone(after["scenario_id"])
        self.assertGreater(len(after["evidence_tasks"]), 0)
        self.assertTrue(any(t["status"] == "OPEN" for t in after["evidence_tasks"]))
        self.assertEqual(after["steps"][4]["status"], "ACTION_REQUIRED")
        self.assertEqual(after["steps"][5]["status"], "BLOCKED")
        self.assertEqual(after["outbox"]["kafka_broker_health"], "NOT_VERIFIED")

        # Same source event again: update source observation, NOT a new arrival.
        repeated = self._ingest(float(site[0]), float(site[1]))
        self.assertFalse(repeated["created"])
        unchanged = event_journey(event_id=self.event_id)
        self.assertEqual(unchanged["outbox"]["first_recorded_at"], first_receipt)
        oid, payload = self._outbox()
        replay = process_event_envelope(
            consumer_name=DEFAULT_CONSUMER, outbox_id=oid,
            topic="external.events", payload=payload,
            run_agents=False, radius_km=5.0,
        )
        self.assertEqual(replay["status"], "DUPLICATE_SKIPPED")
        with connect() as conn:
            counts = conn.execute(
                "SELECT COUNT(*) FROM event_outbox WHERE event_key=%s AND topic='external.events'",
                (self.event_id,),
            ).fetchone()[0]
        self.assertEqual(counts, 1)
        self.assertEqual(
            len(event_journey(event_id=self.event_id)["evidence_tasks"]),
            len(after["evidence_tasks"]),
        )

    def test_remote_event_stops_without_invented_incident(self):
        self._ingest(0.0, -140.0)
        result = self._deliver(radius_km=5.0)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["result"]["status"], "NO_NETWORK_EXPOSURE")
        path = event_journey(event_id=self.event_id)
        self.assertIsNone(path["incident_id"])
        self.assertEqual(path["steps"][3]["status"], "NOT_REQUIRED")
        self.assertEqual(path["next_action"]["code"], "MONITOR_SOURCE")
        self.assertEqual(path["steps"][5]["status"], "BLOCKED")

    def test_unknown_event_is_not_silently_created(self):
        with self.assertRaises(ValueError):
            event_journey(event_id=self.event_id)


if __name__ == "__main__":
    unittest.main()
