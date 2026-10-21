import unittest

from dependency.graph.impact import trace_event_impact


class DatabaseImpactTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"

    def test_cianjur_traces_only_allocated_products(self):
        impact = trace_event_impact(event_id=self.EVENT_ID, radius_km=100)
        self.assertGreaterEqual(len(impact["facilities"]), 4)
        skus = {p["sku"] for p in impact["products"]}
        self.assertEqual(skus, {"JI2993", "JQ6656"})
        self.assertEqual(impact["totals"]["commitment_units"], 16000.0)
        self.assertEqual(impact["totals"]["revenue_eur"], 2405000.0)
        self.assertEqual(impact["totals"]["gross_margin_eur"], 971100.0)

    def test_thread_supplier_does_not_contaminate_unrelated_skus(self):
        impact = trace_event_impact(event_id=self.EVENT_ID, radius_km=100)
        skus = {p["sku"] for p in impact["products"]}
        self.assertNotIn("IR9492", skus)
        self.assertNotIn("IU7704", skus)
        self.assertNotIn("KS8920", skus)
        self.assertNotIn("KJ7436", skus)

    def test_exposure_is_not_claimed_as_shutdown(self):
        impact = trace_event_impact(event_id=self.EVENT_ID, radius_km=100)
        self.assertEqual(impact["exposure_status"], "POTENTIAL_ONLY")
        self.assertTrue(all(f["exposure_status"] == "POTENTIALLY_EXPOSED" for f in impact["facilities"]))


if __name__ == "__main__":
    unittest.main()
