"""Historic successful event consumption must not strand missing evidence."""
import unittest
from unittest.mock import patch

from scripts.reconcile_investigations import reconcile


class ReconcileInvestigationTests(unittest.TestCase):
    @patch("scripts.reconcile_investigations.create_investigation_tasks")
    @patch("scripts.reconcile_investigations.triage_event")
    @patch("scripts.reconcile_investigations.candidates",
           return_value=[{"incident_id":"INC-OLD","event_id":"GDACS-ANY","mode":"LIVE"}])
    def test_preview_is_readonly(self, rows, triage, create):
        result=reconcile()
        self.assertEqual(result["status"],"PREVIEW_ONLY")
        self.assertEqual(result["created_task_count"],0)
        triage.assert_not_called()
        create.assert_not_called()

    @patch("scripts.reconcile_investigations.create_investigation_tasks",
           return_value=[{"task_type":"CONFIRM_FACILITY_STATUS"}])
    @patch("scripts.reconcile_investigations.triage_event",
           return_value={"incident":{"incident_id":"INC-OLD"},"scenario_id":None})
    @patch("scripts.reconcile_investigations.candidates",
           return_value=[{"incident_id":"INC-OLD","event_id":"GDACS-ANY","mode":"LIVE"}])
    def test_existing_incident_reuses_identity(self, rows, triage, create):
        result=reconcile(apply=True)
        self.assertEqual(result["created_task_count"],1)
        create.assert_called_once_with(incident_id="INC-OLD",triage=triage.return_value)
        self.assertFalse(result["effects"]["send_supplier_messages"])
        self.assertFalse(result["effects"]["change_private_operational_state"])

    @patch("scripts.reconcile_investigations.create_investigation_tasks")
    @patch("scripts.reconcile_investigations.triage_event",
           return_value={"incident":{"incident_id":"INC-DIFFERENT"},"scenario_id":None})
    @patch("scripts.reconcile_investigations.candidates",
           return_value=[{"incident_id":"INC-OLD","event_id":"GDACS-ANY","mode":"LIVE"}])
    def test_identity_mismatch_cannot_attach_tasks_to_wrong_incident(self, rows, triage, create):
        result=reconcile(apply=True)
        self.assertEqual(result["created_task_count"],0)
        self.assertEqual(
            result["incidents"][0]["result"],
            "SKIPPED_IDENTITY_OR_CURRENT_EXPOSURE_MISMATCH",
        )
        create.assert_not_called()


if __name__=="__main__":
    unittest.main()
