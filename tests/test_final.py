import unittest

from dependency.risk.scoring import (
    band,
    event_business_risk,
    facility_risk,
    product_risk,
)
from dependency.solver.allocation import Order, allocate_orders, summarize
from dependency.solver.feasibility import check_plan
from dependency.solver.tariff import tariff_impact
from dependency.supplier_confirmations import parse_supplier_reply


class DeterministicCoreTests(unittest.TestCase):
    def test_allocation_obeys_priority_and_partial_fulfilment(self):
        orders = [
            Order("P1", 1000, 120, 40, 1),
            Order("P2", 900, 110, 45, 2),
            Order("P3", 800, 130, 50, 3),
        ]
        result = summarize(allocate_orders(orders, 1500))
        allocations = {
            row["order_id"]: row
            for row in result["allocations"]
        }

        self.assertEqual(allocations["P1"]["allocated_qty"], 1000)
        self.assertEqual(allocations["P2"]["allocated_qty"], 500)
        self.assertEqual(allocations["P3"]["allocated_qty"], 0)
        self.assertEqual(result["late_units"], 1200)

    def test_feasibility_is_input_driven(self):
        feasible = check_plan(
            required_units=1000,
            finished_units=250,
            assembly_units=750,
        )
        shortage = check_plan(
            required_units=1000,
            finished_units=200,
            assembly_units=500,
        )

        self.assertTrue(feasible["feasible"])
        self.assertEqual(feasible["shortage_units"], 0)
        self.assertFalse(shortage["feasible"])
        self.assertEqual(shortage["shortage_units"], 300)

    def test_supplier_reply_parser_accepts_new_capacity_values(self):
        result = parse_supplier_reply(
            "Current capacity is 7,250 pairs per week until 2026-12-15."
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["capacity_units"], 7250)
        self.assertEqual(result["effective_until"], "2026-12-15")
        self.assertTrue(result["requires_confirmation"])

    def test_supplier_reply_parser_rejects_ambiguous_numbers(self):
        result = parse_supplier_reply(
            "Capacity may be 6,000 units per week, or 8,000 units per week "
            "after maintenance."
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "Multiple possible capacity values found",
        )

    def test_risk_band_boundaries(self):
        self.assertEqual(band(29), "LOW")
        self.assertEqual(band(30), "MODERATE")
        self.assertEqual(band(49.9), "MODERATE")
        self.assertEqual(band(50), "HIGH")
        self.assertEqual(band(69.9), "HIGH")
        self.assertEqual(band(70), "CRITICAL")

    def test_event_risk_formula_uses_inputs(self):
        low = event_business_risk(10, 20, 10, 20, 10)
        high = event_business_risk(90, 90, 80, 90, 80)

        self.assertLess(low, high)
        self.assertEqual(low, 14.5)
        self.assertEqual(high, 86.5)

    def test_existing_lower_level_risk_math(self):
        self.assertEqual(facility_risk(80, 90, 80, 70), 80.5)
        self.assertEqual(product_risk(85, 65, 75, 85), 77.0)

    def test_tariff_math_is_not_sku_specific(self):
        result = tariff_impact(
            customs_value_per_unit=80,
            additional_rate=0.15,
            units=1800,
            baseline_unit_margin=52,
        )
        self.assertEqual(result["additional_cost_per_unit"], 12.0)
        self.assertEqual(result["total_additional_cost"], 21600.0)
        self.assertEqual(result["new_unit_margin"], 40.0)


if __name__ == "__main__":
    unittest.main()
