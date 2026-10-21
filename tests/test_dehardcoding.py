import unittest

from dependency.incidents.triage import triage_event
from dependency.solver.candidates import generate_recovery_candidates


class DehardcodingTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def test_recovery_candidates_are_discovered_for_second_sku(self):
        plans = generate_recovery_candidates(
            scenario_id=self.SCENARIO_ID,
            sku="JQ6656",
        )
        backup_ids = {
            p["evidence"]["backup_facility_id"]
            for p in plans
            if p["plan_type"] == "ASSEMBLY_REALLOCATION"
        }
        self.assertTrue(
            {"ADI26-0228", "ADI26-0403", "ADI26-0104"}.issubset(backup_ids)
        )
        self.assertTrue(all("JI2993" not in p["title"] for p in plans))

    def test_event_triage_derives_business_products_and_scenario(self):
        result = triage_event(
            event_id="IDN-CIANJUR-2022-USGS-us7000ir9t",
            radius_km=150,
        )
        skus = {p["sku"] for p in result["impacted_products"]}
        self.assertEqual(result["public_facility_count"], 20)
        self.assertIn("JI2993", skus)
        self.assertIn("JQ6656", skus)
        self.assertEqual(result["scenario_id"], self.SCENARIO_ID)
        self.assertTrue(result["recovery_ready"])


if __name__ == "__main__":
    unittest.main()
