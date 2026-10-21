"""Unscripted public event -> evidence task -> confirmed state -> same incident -> replan.

These tests use a disposable PostgreSQL/PostGIS CI database. They never
assert that geographic exposure alone proves a supplier shutdown.
"""
from __future__ import annotations

import unittest
from uuid import uuid4

from dependency.db.connection import connect
from dependency.ingest.events import upsert_external_event
from dependency.automation.orchestrator import _process_external_event
from dependency.incidents.triage import triage_event
from dependency.investigation.tasks import confirm_facility_investigation
from dependency.services.demo_reset import reset_demo_state


class UnscriptedEvidenceToRecoveryTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()
        self.event_id = f"TEST-EVIDENCE-{uuid4()}"

    def tearDown(self):
        reset_demo_state()
        with connect() as conn:
            conn.execute("DELETE FROM scenarios WHERE event_id=%s", (self.event_id,))
            conn.execute("DELETE FROM external_events WHERE event_id=%s", (self.event_id,))
            conn.commit()

    def test_confirmed_unfamiliar_supplier_event_keeps_incident_and_replans(self):
        with connect() as conn:
            site = conn.execute(
                """
                SELECT nf.network_facility_id,fnl.facility_id,
                       ST_Y(nf.geom::geometry),ST_X(nf.geom::geometry)
                FROM network_facilities nf
                JOIN facility_network_links fnl
                  ON fnl.network_facility_id=nf.network_facility_id
                JOIN production_orders po ON po.facility_id=fnl.facility_id
                WHERE nf.geom IS NOT NULL
                ORDER BY nf.network_facility_id,fnl.facility_id
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(site)
        upsert_external_event({
            "event_id": self.event_id, "event_type": "earthquake",
            "source": "TEST_SIMULATED_OPERATOR_FLOW",
            "title": "Adversarial arbitrary event at linked production facility",
            "latitude": float(site[2]), "longitude": float(site[3]),
            "provenance_class": "SIMULATED_PRIVATE",
            "raw_json": {"type": "TEST_ONLY_NOT_A_REAL_EARTHQUAKE"},
        }, mode="REPLAY")

        initial = _process_external_event(
            {"event_id": self.event_id},run_agents=False,radius_km=1.0,
        )
        self.assertEqual(initial["status"], "INVESTIGATION_REQUIRED")
        incident_id = initial["incident_id"]
        with connect() as conn:
            task = conn.execute(
                """
                SELECT task_id FROM incident_investigation_tasks
                WHERE incident_id=%s AND task_type='CONFIRM_FACILITY_STATUS'
                  AND target_id=%s
                LIMIT 1
                """,
                (incident_id,site[1]),
            ).fetchone()
        self.assertIsNotNone(task)
        kwargs = {
            "task_id": task[0],"status":"UNAVAILABLE","capacity_multiplier":0.0,
            "confirmed_by":"Test authorized planner",
            "evidence_source":"SIMULATED_PRIVATE_TEST_CONFIRMATION",
            "evidence_reference":"TEST-EVIDENCE-RESPONSE-1",
            "reason":"Test fixture models a confirmed supplier closure, not a public claim.",
        }
        confirmed = confirm_facility_investigation(**kwargs)
        self.assertEqual(confirmed["status"], "RESOLVED")
        self.assertEqual(confirmed["incident_id"], incident_id)
        self.assertEqual(confirmed["resolution"]["state_version"], 2)
        self.assertIn(site[1], confirmed["resolution"]["facility_id"])

        repeated = confirm_facility_investigation(**kwargs)
        self.assertEqual(repeated["status"], "ALREADY_RESOLVED")
        with connect() as conn:
            version = conn.execute(
                "SELECT version FROM operational_state_version WHERE singleton=true"
            ).fetchone()[0]
            scenario = conn.execute(
                "SELECT scenario_id FROM incidents WHERE incident_id=%s", (incident_id,)
            ).fetchone()[0]
            confirmed_state = conn.execute(
                """
                SELECT status,confirmed FROM scenario_facility_state
                WHERE scenario_id=%s AND facility_id=%s
                """,
                (scenario,site[1]),
            ).fetchone()
            count = conn.execute(
                """
                SELECT COUNT(*) FROM incident_evidence
                WHERE incident_id=%s AND evidence_type='OPERATOR_CONFIRMED_FACILITY_STATE'
                """,
                (incident_id,),
            ).fetchone()[0]
        self.assertEqual(version, 2)
        self.assertEqual(confirmed_state, ("UNAVAILABLE", True))
        self.assertEqual(count, 1)

        post = triage_event(event_id=self.event_id,radius_km=1.0)
        self.assertEqual(post["incident"]["incident_id"], incident_id)
        self.assertEqual(post["scenario_id"], scenario)
        planned = _process_external_event(
            {"event_id": self.event_id},run_agents=False,radius_km=1.0
        )
        self.assertEqual(planned["status"], "PORTFOLIO_REPLANNED")
        self.assertEqual(planned["incident_id"], incident_id)
        self.assertGreater(planned["saved_plan_count"], 0)

    def test_invalid_evidence_cannot_mutate_status(self):
        with self.assertRaises(ValueError):
            confirm_facility_investigation(
                task_id="UNKNOWN",status="UNAVAILABLE",capacity_multiplier=0.4,
                confirmed_by="Planner",evidence_source="Test",evidence_reference="X",
                reason="Mismatch must be rejected",
            )


if __name__ == "__main__":
    unittest.main()
