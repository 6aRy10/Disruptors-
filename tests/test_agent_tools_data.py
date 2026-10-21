import unittest

from dependency.agents.tools import (
    explode_bom,
    get_approved_alternatives,
    get_inventory,
    get_transport_options,
    normalize_company,
    search_event_evidence,
    trace_upstream_dependencies,
)
from dependency.incidents.triage import triage_event
from dependency.services.demo_reset import reset_demo_state


class AgentDataToolTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_bom_explosion_is_deterministic(self):
        result = explode_bom("JI2993", 10)
        by_material = {row["material_id"]: row for row in result["requirements"]}
        self.assertEqual(by_material["MAT-THREAD"]["required_qty"], 140.0)
        self.assertEqual(by_material["MAT-RUBBER-OUTSOLE"]["required_qty"], 10.0)

    def test_inventory_reports_usable_stock_without_safety_stock(self):
        result = get_inventory("JI2993", "finished_good")
        self.assertEqual(len(result["sites"]), 1)
        self.assertEqual(result["sites"][0]["usable_without_safety_stock"], 1600.0)

    def test_upstream_trace_uses_explicit_allocations(self):
        result = trace_upstream_dependencies(
            "JI2993",
            "ADI26-0226",
        )
        material_ids = {row["material_id"] for row in result["allocated_paths"]}
        self.assertEqual(
            material_ids,
            {"MAT-THREAD", "MAT-TEXTILE-UPPER", "MAT-RUBBER-OUTSOLE"},
        )

    def test_company_normalization_resolves_public_network_candidate(self):
        exact = normalize_company(
            "Barna Bordados Carlos Vega",
            "Argentina",
            5,
        )
        self.assertTrue(exact["matches"])
        self.assertEqual(exact["matches"][0]["match_score"], 100.0)
        self.assertEqual(
            exact["matches"][0]["official_name"],
            "Barna Bordados Carlos Vega",
        )

        demo_relevant = normalize_company(
            "PT Glostar Indonesia PGS",
            "Indonesia",
            10,
        )
        self.assertTrue(
            any(
                "GLOSTAR" in ((row["official_name"] or row["name"]).upper())
                for row in demo_relevant["matches"]
            )
        )

    def test_transport_options_are_data_driven(self):
        result = get_transport_options(
            "ADI26-0226",
            "Europe",
        )
        lane_ids = {row["lane_id"] for row in result["options"]}
        self.assertIn("LANE-ID-JKT-EU", lane_ids)

    def test_approved_alternatives_do_not_promote_unapproved_substitute(self):
        result = get_approved_alternatives("MAT-RUBBER-OUTSOLE")
        self.assertEqual(result["approved_substitutions"], [])
        self.assertTrue(result["approved_sources"])

    def test_event_evidence_keeps_proximity_as_potential_only(self):
        triage_event(event_id=self.EVENT_ID, radius_km=150)
        result = search_event_evidence(self.EVENT_ID)
        self.assertGreaterEqual(result["evidence_count"], 1)
        self.assertTrue(
            any(
                row["evidence_type"] == "PUBLIC_GEOSPATIAL_EXPOSURE"
                for row in result["stored_evidence"]
            )
        )


if __name__ == "__main__":
    unittest.main()
