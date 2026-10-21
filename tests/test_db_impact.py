import unittest

from dependency.graph.impact import trace_event_impact


class DatabaseImpactTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"

    def test_cianjur_traces_to_products_and_commitments(self):
        impact = trace_event_impact(event_id=self.EVENT_ID, radius_km=100)
        self.assertGreaterEqual(len(impact["facilities"]), 4)
        skus = {p["sku"] for p in impact["products"]}
        self.assertIn("JI2993", skus)
        self.assertGreater(impact["totals"]["commitment_units"], 0)
        self.assertGreater(impact["totals"]["gross_margin_eur"], 0)

    def test_exposure_is_not_claimed_as_shutdown(self):
        impact = trace_event_impact(event_id=self.EVENT_ID, radius_km=100)
        self.assertEqual(impact["exposure_status"], "POTENTIAL_ONLY")
        self.assertTrue(all(f["exposure_status"] == "POTENTIALLY_EXPOSED" for f in impact["facilities"]))


if __name__ == "__main__":
    unittest.main()
