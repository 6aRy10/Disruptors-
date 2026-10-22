"""Mission control regression: independent evidence and adversarial recovery."""
from unittest import TestCase
from unittest.mock import patch

from dependency.assistant.mission_controller import mission_preview


def event(scenario_id=None, open_tasks=True):
    return {
        "event": {
            "event_id": "EVENT-1", "title": "Public wildfire",
            "source": "GDACS", "mode": "LIVE",
            "occurred_at": "2026-10-18T08:00:00+00:00",
            "provenance_class": "VERIFIED_PUBLIC",
        },
        "incident": {
            "incident_id": "INC-1", "scenario_id": scenario_id, "status": "INVESTIGATING"
        },
        "evidence_tasks": (
            [{"task_id": "TASK-1", "required_fact": "Current factory capacity",
              "target_id": "FACTORY-B"}] if open_tasks else []
        ),
    }


def journey():
    return {
        "next_action": {
            "code": "VERIFY_OPERATIONS",
            "title": "Confirm missing operational evidence",
            "task_id": "TASK-1",
        }
    }


def graph():
    return {
        "sku": "SKU-X", "allocation_routes": [
            {"sku": "SKU-X", "material_id": "M-1",
             "source_facility_id": "SUP-1", "destination_facility_id": "FAC-A",
             "allocation_share": 1},
            {"sku": "SKU-X", "material_id": "M-1",
             "source_facility_id": "SUP-1", "destination_facility_id": "FAC-B",
             "allocation_share": 1},
        ],
        "nodes": [
            {"id": "facility:FAC-A", "node_type": "ASSEMBLY_FACILITY",
             "approved": True, "role": "primary_assembly", "facility_id": "FAC-A"},
            {"id": "facility:FAC-B", "node_type": "ASSEMBLY_FACILITY",
             "approved": True, "role": "backup_assembly", "facility_id": "FAC-B"},
            {"id": "facility:FAC-Z", "node_type": "ASSEMBLY_FACILITY",
             "approved": False, "role": "backup_assembly", "facility_id": "FAC-Z"},
        ]
    }


def plan():
    return {
        "portfolio_status": "MATERIAL_EVIDENCE_REQUIRED",
        "summary": {"shortage_units": 120},
        "rejected_actions": [
            {"plan_id": "PLAN-3", "decision": "REJECTED",
             "reasons": ["CORRELATED_BACKUP"]}
        ],
        "action_queue": [{"plan_id": "PLAN-2", "decision": "CONDITIONALLY_FEASIBLE"}],
        "portfolio_allocation_verified": False,
        "joint_allocation": {
            "material_constrained_allocation": {
                "status": "MODELED_CAP_LIMIT",
                "material_feasible_units": 80,
                "material_reduced_units": 120,
            }
        }
    }


class MissionPreviewContract(TestCase):
    @patch("dependency.assistant.mission_controller.plan_event_recovery")
    @patch("dependency.assistant.mission_controller.backup_independence")
    @patch("dependency.assistant.mission_controller.product_dependency_graph")
    @patch("dependency.assistant.mission_controller.event_journey")
    @patch("dependency.assistant.mission_controller.event_context")
    def test_evidence_required_without_scenario_even_with_nearby_supplier(
        self, context, journey_view, graph_view, independence, portfolio
    ):
        context.return_value = event()
        journey_view.return_value = journey()
        graph_view.return_value = graph()
        independence.return_value = {
            "decision": "REJECT_CORRELATED_BACKUP",
            "shared_dependency_count": 1,
            "shared_dependencies": [{"material_id": "M-1",
                                     "source_facility_id": "SUP-1"}],
        }
        value = mission_preview(
            event_id="EVENT-1", sku="SKU-X",
            question="Can we use a backup factory to recover?"
        )
        self.assertEqual(value["decision_gate"]["status"], "EVIDENCE_REQUIRED")
        self.assertIn("CORRELATED_BACKUP", value["decision_gate"]["issues"])
        self.assertIn("NO_CONFIRMED_OPERATIONAL_SCENARIO",
                      value["decision_gate"]["issues"])
        self.assertEqual(len(value["backup_challenges"]), 1)
        self.assertEqual(value["backup_challenges"][0]["backup_facility_id"], "FAC-B")
        self.assertEqual(value["route_basis"], "EXPLICIT_MODELED_ALLOCATION_ROUTES")
        self.assertEqual(value["decision_gate"]["next_action"]["code"],
                         "VERIFY_OPERATIONS")
        self.assertFalse(value["decision_gate"]["execution_allowed"])
        self.assertFalse(value["decision_gate"]["source_to_customer_order_assignment_confirmed"])
        self.assertIsNone(value["recovery"])
        self.assertFalse(value["model_invoked"])
        self.assertEqual(value["metrics"]["model_cost_usd"], 0)
        self.assertEqual(value["metrics"]["tool_calls"], 4)
        independence.assert_called_once_with(
            sku="SKU-X", primary_facility_id="FAC-A",
            backup_facility_id="FAC-B",
        )
        portfolio.assert_not_called()

    @patch("dependency.assistant.mission_controller.plan_event_recovery")
    @patch("dependency.assistant.mission_controller.backup_independence")
    @patch("dependency.assistant.mission_controller.product_dependency_graph")
    @patch("dependency.assistant.mission_controller.event_journey", return_value=journey())
    @patch("dependency.assistant.mission_controller.event_context",
           return_value=event("SCN-1", open_tasks=False))
    def test_scenario_uses_real_solver_but_never_auto_executes(
        self, context, journey_view, graph_view, independence, portfolio
    ):
        graph_view.return_value = graph()
        independence.return_value = {
            "decision": "REJECT_CORRELATED_BACKUP",
            "shared_dependency_count": 1, "shared_dependencies": []
        }
        portfolio.return_value = plan()
        value = mission_preview(event_id="EVENT-1", sku="SKU-X",
                                question="Which backup recovery plan is feasible?")
        self.assertEqual(value["decision_gate"]["status"], "BACKUP_CHALLENGED")
        self.assertEqual(value["recovery"]["material_feasible_units"], 80)
        self.assertEqual(value["recovery"]["material_reduced_units"], 120)
        self.assertFalse(value["recovery"]["allocation_verified"])
        self.assertFalse(value["recovery"]["ready_to_execute"])
        self.assertFalse(value["decision_gate"]["execution_allowed"])
        portfolio.assert_called_once_with(event_id="EVENT-1", scenario_id="SCN-1")
        self.assertEqual(value["metrics"]["tool_calls"], 5)
        self.assertEqual([t["specialist"] for t in value["tool_trace"]],
                         ["Signal Investigator", "Evidence Investigator",
                          "Impact Investigator", "Recovery Challenger",
                          "Recovery Planner"])

    @patch("dependency.assistant.mission_controller.trace_business_event_impact")
    @patch("dependency.assistant.mission_controller.product_dependency_graph")
    @patch("dependency.assistant.mission_controller.event_journey", return_value=journey())
    @patch("dependency.assistant.mission_controller.event_context",
           return_value=event(None, open_tasks=False))
    def test_no_sku_in_impact_does_not_invent_business_link(
        self, context, journey_view, graph_view, impact
    ):
        impact.return_value = {"products": [], "totals": {}}
        result = mission_preview(event_id="EVENT-1",
                                 question="Which customers are affected?")
        self.assertIsNone(result["sku"])
        self.assertEqual(result["route_basis"], "NO_SKU_SELECTED")
        self.assertEqual(result["suggested_skus"], [])
        self.assertEqual(result["decision_gate"]["status"], "EVIDENCE_REQUIRED")
        graph_view.assert_not_called()

    @patch("dependency.assistant.mission_controller.product_dependency_graph")
    @patch("dependency.assistant.mission_controller.event_journey", return_value=journey())
    @patch("dependency.assistant.mission_controller.event_context",
           return_value=event("SCN-1", open_tasks=False))
    def test_tool_failure_is_not_silently_feasible(
        self, context, journey_view, graph_view
    ):
        graph_view.side_effect = RuntimeError("private database password: badpass")
        response = mission_preview(event_id="EVENT-1", sku="SKU-X",
                                   question="Investigate backups")
        self.assertEqual(response["decision_gate"]["status"], "INCOMPLETE_TOOL_ERROR")
        self.assertEqual(response["tool_errors"][0]["error_type"], "RuntimeError")
        self.assertNotIn("badpass", str(response))
        self.assertFalse(response["decision_gate"]["execution_allowed"])

    def test_inputs_are_bounded(self):
        with self.assertRaises(ValueError):
            mission_preview(event_id="", question="Get evidence")
        with self.assertRaises(ValueError):
            mission_preview(event_id="X", question="")
        with self.assertRaises(ValueError):
            mission_preview(event_id="X", question="OK", max_checks=50)
        with self.assertRaises(ValueError):
            mission_preview(event_id="X", question="OK", sku="X"*121)


if __name__ == "__main__":
    import unittest
    unittest.main()
