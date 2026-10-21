"""Live event without a predeclared scenario must produce evidence work."""
import unittest
from unittest.mock import patch

from dependency.automation.orchestrator import _process_external_event


class LiveIncidentWorkflowTests(unittest.TestCase):
    @patch("dependency.automation.orchestrator.create_investigation_tasks")
    @patch("dependency.automation.orchestrator.triage_event")
    def test_live_event_creates_actionable_evidence_not_unverified_recovery(self, triage, tasks):
        triage.return_value = {
            "event": {"event_id": "DYNAMIC-EVENT", "event_type": "wildfire"},
            "status": "BUSINESS_GRAPH_EXPOSURE",
            "incident": {"incident_id": "INC-DYNAMIC"},
            "scenario_id": None,
            "impacted_products": [{"sku": "DYNAMIC-SKU"}],
            "next_required_evidence": ["CONFIRMED_OPERATIONAL_FACILITY_STATE"],
            "commercial_totals": {"revenue_eur": 1500},
        }
        tasks.return_value = [{"task_type": "CONFIRM_FACILITY_STATUS", "task_key": "DYNAMIC-TASK"}]
        result = _process_external_event(
            {"event_id": "DYNAMIC-EVENT"}, run_agents=False, radius_km=100
        )
        self.assertEqual(result["status"], "INVESTIGATION_REQUIRED")
        self.assertIsNone(result["scenario_id"])
        self.assertEqual(result["investigation_task_count"], 1)
        self.assertEqual(result["claim_rule"], "POTENTIAL_EXPOSURE_ONLY_NOT_CONFIRMED_LOSS")
        tasks.assert_called_once()

    @patch("dependency.automation.orchestrator.create_investigation_tasks")
    @patch("dependency.automation.orchestrator.triage_event")
    def test_no_exposure_cannot_generate_fake_evidence_tasks(self, triage, tasks):
        triage.return_value = {"status": "NO_NETWORK_EXPOSURE", "incident": None}
        result = _process_external_event(
            {"event_id": "DYNAMIC-OCEAN"}, run_agents=False, radius_km=100
        )
        self.assertEqual(result["status"], "NO_NETWORK_EXPOSURE")
        tasks.assert_not_called()


if __name__ == "__main__":
    unittest.main()
