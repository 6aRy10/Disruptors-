"""Reconcile an old live incident after it was successfully handled."""
from __future__ import annotations

import unittest
from uuid import uuid4

from dependency.db.connection import connect
from dependency.ingest.events import upsert_external_event
from dependency.incidents.triage import triage_event
from dependency.services.demo_reset import reset_demo_state
from scripts.reconcile_investigations import reconcile


class LegacyIncidentReconciliationTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()
        self.event_id="TEST-OLD-INCIDENT-"+str(uuid4())

    def tearDown(self):
        reset_demo_state()
        with connect() as conn:
            conn.execute("DELETE FROM external_events WHERE event_id=%s",(self.event_id,))
            conn.commit()

    def test_old_live_incident_gets_missing_tasks_only_once(self):
        with connect() as conn:
            site=conn.execute(
                """
                SELECT ST_Y(nf.geom::geometry),ST_X(nf.geom::geometry)
                FROM network_facilities nf
                JOIN facility_network_links fnl
                    ON fnl.network_facility_id=nf.network_facility_id
                JOIN product_facilities pf ON pf.facility_id=fnl.facility_id
                WHERE nf.geom IS NOT NULL
                GROUP BY nf.network_facility_id,nf.geom
                ORDER BY COUNT(DISTINCT pf.sku),nf.network_facility_id
                LIMIT 1
                """
            ).fetchone()
        self.assertIsNotNone(site)
        upsert_external_event({
            "event_id":self.event_id,"event_type":"wildfire",
            "source":"TEST_ONLY","title":"Simulated independent wildfire",
            "latitude":float(site[0]),"longitude":float(site[1]),
            "provenance_class":"SIMULATED_PRIVATE",
            "raw_json":{"test_only":True},
        },mode="LIVE")
        old=triage_event(event_id=self.event_id,radius_km=5.0)
        self.assertIsNotNone(old["incident"])
        incident_id=old["incident"]["incident_id"]
        with connect() as conn:
            count=conn.execute(
                "SELECT COUNT(*) FROM incident_investigation_tasks WHERE incident_id=%s",
                (incident_id,),
            ).fetchone()[0]
        self.assertEqual(count,0)

        preview=reconcile(event_id=self.event_id,apply=False,radius_km=5.0)
        self.assertEqual(preview["candidate_incidents"],1)
        first=reconcile(event_id=self.event_id,apply=True,radius_km=5.0)
        self.assertGreater(first["created_task_count"],0)
        self.assertEqual(first["incidents"][0]["incident_id"],incident_id)
        with connect() as conn:
            saved=conn.execute(
                "SELECT COUNT(*) FROM incident_investigation_tasks WHERE incident_id=%s",
                (incident_id,),
            ).fetchone()[0]
        self.assertEqual(saved,first["created_task_count"])
        again=reconcile(event_id=self.event_id,apply=True,radius_km=5.0)
        self.assertEqual(again["candidate_incidents"],0)
        self.assertEqual(again["created_task_count"],0)


if __name__=="__main__":
    unittest.main()
