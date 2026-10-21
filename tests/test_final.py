import unittest

from dependency.risk.scoring import band, event_business_risk, facility_risk, product_risk
from dependency.solver.allocation import Order, allocate_orders, summarize
from dependency.solver.feasibility import check_plan
from dependency.solver.tariff import tariff_impact
from dependency.state import DemoState
from dependency.supplier_confirmations import parse_supplier_reply

ORDERS = [
    Order("ORD-JI-EU", 4000, 130, 55, 1),
    Order("ORD-JI-NA", 3000, 130, 50, 2),
    Order("ORD-JI-GC", 2500, 130, 52, 3),
]


class DependencyFinalTests(unittest.TestCase):
    def test_baseline_all_demand_protected(self):
        result = summarize(allocate_orders(ORDERS, 9600))
        self.assertEqual(result["late_units"], 0)

    def test_supplier_capacity_shock(self):
        result = summarize(allocate_orders(ORDERS, 5600))
        self.assertEqual(result["late_units"], 3900)
        self.assertEqual(result["protected_margin_eur"], 303200)

    def test_feasibility_shortage(self):
        result = check_plan(required_units=9500, finished_units=2100, assembly_units=3500)
        self.assertFalse(result["feasible"])
        self.assertEqual(result["shortage_units"], 3900)

    def test_supplier_reply_parse_requires_confirmation(self):
        result = parse_supplier_reply("Capacity has declined to 5,500 pairs per week until 2026-11-04.")
        self.assertTrue(result["ok"])
        self.assertEqual(result["capacity_units"], 5500)
        self.assertTrue(result["requires_confirmation"])

    def test_confirm_changes_state(self):
        state = DemoState()
        old_version = state.version
        state.confirm_capacity(5500)
        self.assertGreater(state.version, old_version)
        self.assertEqual(state.hwa_available, 3500)

    def test_risk_bands(self):
        self.assertEqual(band(29), "LOW")
        self.assertEqual(band(30), "MODERATE")
        self.assertEqual(band(79), "CRITICAL")

    def test_event_risk_math(self):
        self.assertEqual(event_business_risk(82, 86, 74, 72, 88), 80.3)
        self.assertEqual(event_business_risk(60, 76, 45, 72, 62), 63.7)
        self.assertEqual(event_business_risk(70, 68, 58, 50, 65), 62.4)

    def test_existing_lower_level_risk_math(self):
        self.assertEqual(facility_risk(80, 90, 80, 70), 80.5)
        self.assertEqual(product_risk(85, 65, 75, 85), 77.0)

    def test_tariff_ground_truth(self):
        result = tariff_impact(
            customs_value_per_unit=60,
            additional_rate=0.20,
            units=2500,
            baseline_unit_margin=47,
        )
        self.assertEqual(result["additional_cost_per_unit"], 12.0)
        self.assertEqual(result["total_additional_cost"], 30000.0)
        self.assertEqual(result["new_unit_margin"], 35.0)


if __name__ == "__main__":
    unittest.main()
