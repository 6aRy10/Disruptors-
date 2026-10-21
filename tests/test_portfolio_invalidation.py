"""State changes must replan the entire shared-resource portfolio."""
import unittest
from unittest.mock import patch

from dependency.automation.orchestrator import _process_plan_invalidated


class PortfolioInvalidationTests(unittest.TestCase):
    @patch("dependency.automation.orchestrator._save_portfolio_plans")
    @patch("dependency.automation.orchestrator.plan_event_recovery")
    @patch("dependency.automation.orchestrator._open_incidents")
    def test_one_sku_change_repersists_all_skus(self, open_incidents, plan, save):
        open_incidents.return_value = [{
            "incident_id": "INC-X", "event_id": "EVENT-X", "scenario_id": "SCN-X"
        }]
        plan.return_value = {
            "products": [{"sku": "DYNAMIC-A"}, {"sku": "DYNAMIC-B"}],
            "portfolio_status": "PROVISIONAL",
            "summary": {"joint_late_units": 12},
        }
        save.return_value = [{"plan_record_id": "P1"}, {"plan_record_id": "P2"}]
        result = _process_plan_invalidated(
            {"sku": "DYNAMIC-A", "new_state_version": 3}, radius_km=150
        )
        self.assertEqual(result["status"], "REPLANNED_OPEN_INCIDENTS")
        self.assertEqual(result["replans"][0]["saved_plan_count"], 2)
        self.assertNotIn("only_sku", save.call_args.kwargs)
        self.assertIs(save.call_args.kwargs["portfolio"], plan.return_value)

    @patch("dependency.automation.orchestrator._save_portfolio_plans")
    @patch("dependency.automation.orchestrator.plan_event_recovery")
    @patch("dependency.automation.orchestrator._open_incidents")
    def test_unrelated_sku_does_not_change_other_incidents(self, open_incidents, plan, save):
        open_incidents.return_value = [{
            "incident_id": "INC-X", "event_id": "EVENT-X", "scenario_id": "SCN-X"
        }]
        plan.return_value = {"products": [{"sku": "DYNAMIC-B"}]}
        result = _process_plan_invalidated(
            {"sku": "DYNAMIC-A"}, radius_km=150,
        )
        self.assertEqual(result["replans"], [])
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
