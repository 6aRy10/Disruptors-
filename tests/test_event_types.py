import unittest

from dependency.graph.event_impact import trace_business_event_impact
from dependency.incidents.triage import triage_event
from dependency.services.demo_reset import reset_demo_state


class EventTypeExposureTests(unittest.TestCase):
    CIANJUR = "IDN-CIANJUR-2022-USGS-us7000ir9t"
    YANTIAN = "CHN-YANTIAN-2021-PORT"
    VIETNAM_POLICY = "VNM-US-SECTION301-2026"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_cianjur_keeps_geospatial_dependency_logic(self):
        result = trace_business_event_impact(
            event_id=self.CIANJUR,
            radius_km=150,
        )
        self.assertEqual(result["exposure_basis"], "GEOSPATIAL_PROXIMITY")
        self.assertEqual(
            {p["sku"] for p in result["products"]},
            {"JI2993", "JQ6656"},
        )

    def test_yantian_uses_explicit_transport_lanes_not_nearby_factories(self):
        result = trace_business_event_impact(event_id=self.YANTIAN)
        self.assertEqual(
            result["exposure_basis"],
            "EXPLICIT_TRANSPORT_LANE",
        )
        self.assertEqual(result["port_unlocode"], "CNYTN")
        self.assertEqual(
            {p["sku"] for p in result["products"]},
            {"KS8920", "IU7704"},
        )
        self.assertEqual(result["totals"]["commitment_units"], 5500.0)
        self.assertEqual(result["totals"]["revenue_eur"], 330000.0)
        self.assertEqual(result["totals"]["gross_margin_eur"], 128500.0)
        self.assertTrue(
            all(
                path["port_unlocode"] == "CNYTN"
                for path in result["dependency_paths"]
            )
        )

    def test_yantian_triage_opens_incident_but_does_not_claim_late_orders(self):
        result = triage_event(event_id=self.YANTIAN, radius_km=150)
        self.assertEqual(result["status"], "BUSINESS_GRAPH_EXPOSURE")
        self.assertEqual(
            result["exposure_basis"],
            "EXPLICIT_TRANSPORT_LANE",
        )
        self.assertIsNotNone(result["incident"])
        self.assertFalse(result["recovery_ready"])
        self.assertIn(
            "CURRENT_SHIPMENT_OR_ROUTE_STATUS",
            result["next_required_evidence"],
        )

    def test_vietnam_policy_requires_product_classification(self):
        result = trace_business_event_impact(event_id=self.VIETNAM_POLICY)
        self.assertEqual(
            result["exposure_basis"],
            "EXPLICIT_POLICY_TAGGED_TRANSPORT_LANE",
        )
        self.assertEqual(result["additional_rate"], 0.125)
        self.assertEqual(
            result["applicability_status"],
            "REQUIRES_PRODUCT_CLASSIFICATION",
        )
        self.assertEqual(
            {p["sku"] for p in result["products"]},
            {"KJ7436"},
        )
        self.assertEqual(result["totals"]["commitment_units"], 2500.0)
        self.assertEqual(result["totals"]["revenue_eur"], 300000.0)
        self.assertEqual(result["totals"]["gross_margin_eur"], 117500.0)
        self.assertTrue(
            all(
                path["exposure_status"] == "CLASSIFICATION_REVIEW_REQUIRED"
                for path in result["dependency_paths"]
            )
        )

    def test_policy_triage_names_classification_as_missing_evidence(self):
        result = triage_event(event_id=self.VIETNAM_POLICY, radius_km=150)
        self.assertEqual(result["status"], "BUSINESS_GRAPH_EXPOSURE")
        self.assertIn(
            "PRODUCT_CLASSIFICATION_AND_EXEMPTION_CHECK",
            result["next_required_evidence"],
        )


if __name__ == "__main__":
    unittest.main()
