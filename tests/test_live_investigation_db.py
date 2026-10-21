"""An unscripted event must create durable, deduplicated investigation work."""
from __future__ import annotations

import unittest
from uuid import uuid4

from dependency.db.connection import connect
from dependency.ingest.events import upsert_external_event
from dependency.automation.orchestrator import _process_external_event
from dependency.services.demo_reset import reset_demo_state


class LiveInvestigationDatabaseTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()
        self.event_id = "TEST-UNSCRIPTED-" + str(uuid4())

    def tearDown(self):
        reset_demo_state()
        with connect() as conn:
            conn.execute("DELETE FROM external_events WHERE event_id=%s", (self.event_id,))
            conn.commit()

    def test_new_facility_event_creates_real_tasks_without_auto_declaring_damage(self):
        with connect() as conn:
            row = conn.execute(
                """
                SELECT ST_Y(nf.geom::geometry),ST_X(nf.geom::geometry)
                FROM network_facilities nf
                JOIN facility_network_links fnl
                  ON fnl.network_facility_id=nf.network_facility_id
                JOIN product_facilities pf ON pf.facility_id=fnl.facility_id
                WHERE nf.geom IS NOT NULL
                ORDER BY nf.network_facility_id,pf.sku
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(row, "No linked public/private supplier with an assigned SKU.")
        upsert_external_event({
            "event_id": self.event_id, "event_type": "earthquake",
            "source": "TEST_SIMULATION", "title": "Adversarial independent event",
            "latitude": float(row[0]), "longitude": float(row[1]),
            "provenance_class": "SIMULATED_PRIVATE",
            "raw_json": {"assertion": "SIMULATED_TEST_NOT_REAL_EARTHQUAKE"},
        }, mode="REPLAY")

        first = _process_external_event(
            {"event_id": self.event_id}, run_agents=False, radius_km=5.0
        )
        self.assertEqual(first["status"], "INVESTIGATION_REQUIRED")
        self.assertIsNone(first["scenario_id"])
        self.assertGreater(first["investigation_task_count"], 0)
        self.assertEqual(first["claim_rule"], "POTENTIAL_EXPOSURE_ONLY_NOT_CONFIRMED_LOSS")

        with connect() as conn:
            saved = conn.execute(
                """
                SELECT COUNT(*),COUNT(DISTINCT task_key)
                FROM incident_investigation_tasks
                WHERE incident_id=%s AND status='OPEN'
                """,
                (first["incident_id"],),
            ).fetchone()
            self.assertEqual(saved[0], first["investigation_task_count"])
            self.assertEqual(saved[0], saved[1])
            classes = conn.execute(
                "SELECT DISTINCT provenance_class FROM incident_investigation_tasks WHERE incident_id=%s",
                (first["incident_id"],),
            ).fetchall()
        self.assertEqual({r[0] for r in classes}, {"INFERRED"})

        _process_external_event({"event_id": self.event_id}, run_agents=False, radius_km=5.0)
        with connect() as conn:
            again = conn.execute(
                "SELECT COUNT(*) FROM incident_investigation_tasks WHERE incident_id=%s",
                (first["incident_id"],),
            ).fetchone()[0]
        self.assertEqual(again, saved[0])


if __name__ == "__main__":
    unittest.main()
