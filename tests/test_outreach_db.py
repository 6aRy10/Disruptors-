"""Outreach drafts must be persisted and deduplicated without sending messages."""
import unittest
from uuid import uuid4
from unittest.mock import patch

from dependency.db.connection import connect
from dependency.investigation.outreach import prepare_investigation_outreach


class OutreachDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.incident_id="INC-OUTREACH-"+str(uuid4())
        self.task_id="TASK-OUTREACH-"+str(uuid4())
        with connect() as conn:
            event=conn.execute(
                "SELECT event_id,event_type FROM external_events ORDER BY event_id LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(event)
            contact=conn.execute(
                """
                SELECT entity_id FROM operational_contacts
                WHERE entity_type='supplier_facility'
                  AND can_confirm_operational_data=true
                ORDER BY entity_id LIMIT 1
                """
            ).fetchone()
            self.facility=contact[0] if contact else "UNMODELED-TEST-FACILITY"
            self.has_contact=contact is not None
            conn.execute(
                """
                INSERT INTO incidents(incident_id,event_id,event_type,status,
                  summary,provenance_class)
                VALUES (%s,%s,%s,'INVESTIGATING','CI outreach test','SIMULATED_PRIVATE')
                """,
                (self.incident_id,event[0],event[1]),
            )
            conn.execute(
                """
                INSERT INTO incident_investigation_tasks(
                  task_id,incident_id,task_key,task_type,target_type,target_id,
                  required_fact,connected_skus,connected_margin_eur
                ) VALUES (%s,%s,%s,'CONFIRM_FACILITY_STATUS',
                          'facility',%s,'Confirm operating capacity','[]'::jsonb,0)
                """,
                (self.task_id,self.incident_id,self.task_id,self.facility),
            )
            conn.commit()

    def tearDown(self):
        with connect() as conn:
            conn.execute("DELETE FROM investigation_outreach_drafts WHERE task_id=%s",(self.task_id,))
            conn.execute("DELETE FROM incident_investigation_tasks WHERE task_id=%s",(self.task_id,))
            conn.execute("DELETE FROM incidents WHERE incident_id=%s",(self.incident_id,))
            conn.commit()

    def test_draft_is_durable_deduplicated_and_never_sent(self):
        with patch("dependency.notifications.slack.post_message") as post:
            one=prepare_investigation_outreach(task_id=self.task_id)
            two=prepare_investigation_outreach(task_id=self.task_id)
            post.assert_not_called()
        self.assertFalse(one["dispatched"])
        self.assertEqual(one["draft_id"],two["draft_id"])
        self.assertEqual(one["provenance_class"],"INFERRED")
        self.assertIn("does not prove",one["message_text"])
        self.assertEqual(
            one["status"],
            "REVIEW_REQUIRED" if self.has_contact else "CONTACT_NOT_MODELED",
        )
        with connect() as conn:
            n=conn.execute(
                "SELECT COUNT(*) FROM investigation_outreach_drafts WHERE task_id=%s",
                (self.task_id,),
            ).fetchone()[0]
        self.assertEqual(n,1)


if __name__=="__main__":
    unittest.main()
