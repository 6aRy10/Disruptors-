import unittest

from dependency.services.capacity import confirm_supplier_capacity
from dependency.services.demo_reset import reset_demo_state
from dependency.solver.optimization import optimize_recovery_allocation


class RecoveryOptimizationTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"
    SKU = "JI2993"

    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_optimizer_protects_explicit_priority_before_lower_priority_margin(self):
        result = optimize_recovery_allocation(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            release_safety_stock=False,
            include_provisional=True,
        )
        self.assertEqual(result["protected_units"], 9100)
        self.assertEqual(result["late_units"], 400)
        self.assertEqual(result["protected_margin_eur"], 479200.0)

        by_order = {row["order_id"]: row for row in result["orders"]}
        self.assertEqual(by_order["ORD-JI-EU"]["protected_units"], 4000)
        self.assertEqual(by_order["ORD-JI-NA"]["protected_units"], 3000)
        self.assertEqual(by_order["ORD-JI-GC"]["protected_units"], 2100)
        self.assertGreater(result["incremental_transport_cost_eur"], 0)
        self.assertIn("ADI26-0240", result["provisional_resources_used"])

    def test_unconfirmed_recovery_resources_can_be_excluded(self):
        result = optimize_recovery_allocation(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            release_safety_stock=False,
            include_provisional=False,
        )
        self.assertEqual(result["protected_units"], 1600)
        self.assertEqual(result["late_units"], 7900)
        self.assertEqual(result["provisional_resources_used"], [])

    def test_capacity_shock_and_safety_stock_reoptimize_business_value(self):
        confirm_supplier_capacity(
            facility_id="ADI26-0240",
            sku=self.SKU,
            capacity_units=5500,
            valid_until="2026-11-04",
            source_channel="test",
            raw_message="Capacity is 5500 pairs per week until 2026-11-04.",
        )
        result = optimize_recovery_allocation(
            scenario_id=self.SCENARIO_ID,
            sku=self.SKU,
            release_safety_stock=True,
            include_provisional=True,
        )
        self.assertEqual(result["state_version"], 2)
        self.assertEqual(result["protected_units"], 5600)
        self.assertEqual(result["late_units"], 3900)
        self.assertEqual(result["protected_margin_eur"], 300000.0)
        self.assertIn("SAFETY_STOCK", result["approval_resources_used"])

        by_order = {row["order_id"]: row for row in result["orders"]}
        self.assertEqual(by_order["ORD-JI-EU"]["protected_units"], 4000)
        self.assertEqual(by_order["ORD-JI-NA"]["protected_units"], 1600)
        self.assertEqual(by_order["ORD-JI-GC"]["protected_units"], 0)


if __name__ == "__main__":
    unittest.main()
