"""Read-only expeditor: no DB needed for deterministic grounding tests."""
import unittest
from unittest.mock import patch
from dependency.assistant.expeditor import answer_expeditor

GRAPH = {
    "sku": "TEST-SKU",
    "nodes": [
        {"id": "facility:F", "label": "Supplier F", "node_type": "UPSTREAM_FACILITY"},
        {"id": "material:M", "label": "Material M", "node_type": "MATERIAL"},
        {"id": "product:TEST-SKU", "label": "Test shoe", "node_type": "PRODUCT"},
        {"id": "commitment:O1", "commitment_id": "O1", "qty": 100, "label": "EU order",
         "node_type": "CUSTOMER_COMMITMENT"},
    ],
    "edges": [
        {"id": "E1", "source": "facility:F", "target": "material:M"},
        {"id": "E2", "source": "material:M", "target": "product:TEST-SKU"},
        {"id": "E3", "source": "product:TEST-SKU", "target": "commitment:O1"},
    ],
    "summary": {"material_count": 1, "assembly_facility_count": 0, "commitment_count": 1},
    "shared_upstream_sources": [],
}


class ExpeditorTests(unittest.TestCase):
    def test_no_context_makes_no_db_calls(self):
        with patch("dependency.assistant.expeditor.product_dependency_graph") as graph:
            result = answer_expeditor(question="Which customers depend on this site?")
            self.assertEqual(result["mode"], "CONTEXT_REQUIRED")
            graph.assert_not_called()

    def test_explicit_supplier_path_reaches_customer(self):
        with patch.dict("os.environ", {"DEPENDENCY_EXPEDITOR_MODEL": "0"}), patch(
            "dependency.assistant.expeditor.product_dependency_graph", return_value=GRAPH
        ):
            answer = answer_expeditor(
                question="Which customer orders depend on this supplier?",
                sku="TEST-SKU", object_id="facility:F",
            )
        self.assertIn("O1 (100 modeled units)", answer["answer"])
        self.assertEqual(answer["mode"], "DETERMINISTIC_READ_ONLY")
        self.assertTrue(answer["read_only"])
        self.assertEqual(answer["sources"][0]["path"], "/products/TEST-SKU/graph")

    def test_disconnected_supplier_does_not_invent_order(self):
        disconnected = {**GRAPH, "edges": []}
        with patch.dict("os.environ", {"DEPENDENCY_EXPEDITOR_MODEL": "0"}), patch(
            "dependency.assistant.expeditor.product_dependency_graph", return_value=disconnected
        ):
            answer = answer_expeditor(
                question="Which orders depend on this supplier?",
                sku="TEST-SKU", object_id="facility:F",
            )
        self.assertIn("No downstream customer commitment is reachable", answer["answer"])

    def test_event_needs_private_evidence_to_recover(self):
        event = {"event": {"title": "Reported wildfire", "source": "GDACS",
                           "occurred_at": "2026-10-15"}, "incident": {"scenario_id": None},
                 "evidence_tasks": [{"required_fact": "Confirm operating status."}]}
        impact = {"products": [{"sku": "TEST-SKU"}],
                  "totals": {"products_impacted": 1, "commitment_units": 6000,
                             "revenue_eur": 360000}}
        with patch.dict("os.environ", {"DEPENDENCY_EXPEDITOR_MODEL": "0"}), patch(
            "dependency.assistant.expeditor.event_context", return_value=event
        ), patch("dependency.assistant.expeditor.trace_business_event_impact",
                 return_value=impact), patch(
            "dependency.assistant.expeditor.plan_event_recovery"
        ) as recovery:
            result = answer_expeditor(question="Can we recover this production?",
                                      event_id="EVENT-1")
        self.assertIn("No confirmed operational scenario", result["answer"])
        recovery.assert_not_called()

    def test_very_long_question_rejected(self):
        with self.assertRaises(ValueError):
            answer_expeditor(question="x"*1001, sku="TEST-SKU")


if __name__ == "__main__":
    unittest.main()
