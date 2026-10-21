import unittest

from dependency.graph.material_paths import assess_material_paths
from dependency.solver.portfolio import plan_event_recovery
from dependency.solver.recovery import plan_sku_recovery


class PortfolioRecoveryTests(unittest.TestCase):
    EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def test_backup_material_paths_are_not_silently_invented(self):
        result = assess_material_paths(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            destination_facility_id="ADI26-0240",
        )
        self.assertFalse(result["blocked"])
        self.assertTrue(result["requires_confirmation"])
        self.assertGreater(len(result["missing_material_ids"]), 0)
        self.assertEqual(
            result["decision"],
            "CONDITIONALLY_USABLE_REQUIRES_SOURCE_CONFIRMATION",
        )

    def test_recovery_plan_surfaces_material_confirmation(self):
        plan = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        self.assertEqual(plan["selected_backup"]["facility_id"], "ADI26-0240")
        self.assertTrue(plan["requires_supplier_confirmation"])
        self.assertTrue(plan["requires_material_confirmation"])
        self.assertEqual(plan["plan_status"], "PROVISIONAL_SHORTAGE")

    def test_event_portfolio_covers_all_impacted_products_but_acts_only_on_operational_impact(self):
        portfolio = plan_event_recovery(
            event_id=self.EVENT_ID,
            scenario_id=self.SCENARIO_ID,
            radius_km=150,
        )
        product_skus = {row["sku"] for row in portfolio["products"]}
        self.assertIn("JI2993", product_skus)
        self.assertIn("JQ6656", product_skus)

        self.assertIn("JI2993", portfolio["operationally_affected_skus"])
        self.assertIn("JQ6656", portfolio["exposure_only_skus"])
        self.assertEqual(
            portfolio["summary"]["total_conservative_shortage_units"],
            400.0,
        )
        self.assertEqual(
            portfolio["summary"]["total_at_risk_revenue_eur"],
            52000.0,
        )
        self.assertEqual(
            portfolio["summary"]["total_at_risk_margin_eur"],
            20800.0,
        )
        self.assertTrue(portfolio["action_queue"])
        self.assertTrue(
            all(row["sku"] == "JI2993" for row in portfolio["action_queue"])
        )


if __name__ == "__main__":
    unittest.main()
