import unittest
from datetime import date

from dependency.graph.exposure import facilities_within_radius
from dependency.graph.shared_dependencies import backup_independence
from dependency.solver.allocation import Order, allocate_orders, summarize
from dependency.solver.candidates import generate_recovery_candidates
from dependency.solver.feasibility import check_plan
from dependency.solver.material_timing import purchase_order_supply_by_date
from dependency.solver.recovery import plan_sku_recovery
from dependency.solver.tariff import tariff_impact
from dependency.supplier_confirmations import parse_supplier_reply


class GroundTruthTests(unittest.TestCase):
    SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"

    def test_gt02_cianjur_public_exposure(self):
        self.assertEqual(
            len(facilities_within_radius(latitude=-6.836, longitude=106.997, radius_km=50)),
            4,
        )
        rows = facilities_within_radius(
            latitude=-6.836,
            longitude=106.997,
            radius_km=150,
        )
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(r["exposure_status"] == "POTENTIALLY_EXPOSED" for r in rows))

    def test_gt03_hidden_shared_dependency(self):
        result = backup_independence(
            sku="JI2993",
            primary_facility_id="ADI26-0226",
            backup_facility_id="ADI26-0225",
        )
        self.assertEqual(result["shared_dependency_count"], 3)
        self.assertEqual(result["decision"], "REJECT_CORRELATED_BACKUP")

    def test_gt04_unapproved_substitute(self):
        plans = generate_recovery_candidates(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
        )
        plan_b = next(p for p in plans if p["plan_id"] == "PLAN-B-SUBSTITUTE-OUTSOLE")
        self.assertEqual(plan_b["decision"], "REJECTED")
        self.assertIn("SUBSTITUTE_NOT_APPROVED", plan_b["reasons"])

    def test_gt05_initial_recovery(self):
        conservative = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            release_safety_stock=False,
        )
        emergency = plan_sku_recovery(
            scenario_id=self.SCENARIO_ID,
            sku="JI2993",
            release_safety_stock=True,
        )
        self.assertEqual(conservative["total_available_units"], 9100.0)
        self.assertEqual(conservative["shortage_units"], 400.0)
        self.assertEqual(emergency["total_available_units"], 9600.0)
        self.assertEqual(emergency["shortage_units"], 0.0)
        self.assertTrue(emergency["requires_supplier_confirmation"])
        self.assertTrue(emergency["requires_planner_approval"])

    def test_gt06_supplier_reply_parse(self):
        result = parse_supplier_reply(
            "Capacity has declined to 5,500 pairs per week until 2026-11-04."
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["capacity_units"], 5500)
        self.assertEqual(result["effective_until"], "2026-11-04")
        self.assertTrue(result["requires_confirmation"])

    def test_gt07_capacity_shock_math(self):
        orders = [
            Order("ORD-JI-EU", 4000, 130, 55, 1),
            Order("ORD-JI-NA", 3000, 130, 50, 2),
            Order("ORD-JI-GC", 2500, 130, 52, 3),
        ]
        result = summarize(allocate_orders(orders, 5600))
        self.assertEqual(result["late_units"], 3900)
        self.assertEqual(result["protected_revenue_eur"], 728000.0)
        self.assertEqual(result["protected_margin_eur"], 303200.0)

    def test_gt08_inventory_fall(self):
        result = check_plan(
            required_units=9500,
            finished_units=600,
            assembly_units=7500,
        )
        self.assertFalse(result["feasible"])
        self.assertEqual(result["shortage_units"], 1400)

    def test_gt09_purchase_order_timing(self):
        too_early = purchase_order_supply_by_date(
            material_id="MAT-TEXTILE-UPPER",
            need_by=date(2026, 10, 23),
        )
        on_eta = purchase_order_supply_by_date(
            material_id="MAT-TEXTILE-UPPER",
            need_by=date(2026, 10, 24),
        )
        self.assertEqual(too_early["usable_qty"], 0)
        self.assertEqual(on_eta["usable_qty"], 6000.0)

    def test_gt10_far_event_control(self):
        rows = facilities_within_radius(
            latitude=0.0,
            longitude=-140.0,
            radius_km=100,
        )
        self.assertEqual(rows, [])

    def test_gt11_competing_commitments(self):
        orders = [
            Order("ORD-JI-EU", 4000, 130, 55, 1),
            Order("ORD-JI-NA", 3000, 130, 50, 2),
            Order("ORD-JI-GC", 2500, 130, 52, 3),
        ]
        result = summarize(allocate_orders(orders, 5600))
        by_id = {r["order_id"]: r for r in result["allocations"]}
        self.assertEqual(by_id["ORD-JI-EU"]["allocated_qty"], 4000)
        self.assertEqual(by_id["ORD-JI-GC"]["allocated_qty"], 1600)
        self.assertEqual(by_id["ORD-JI-NA"]["allocated_qty"], 0)

    def test_gt12_vietnam_tariff(self):
        result = tariff_impact(
            customs_value_per_unit=60,
            additional_rate=0.125,
            units=2500,
            baseline_unit_margin=47,
        )
        self.assertEqual(result["additional_cost_per_unit"], 7.5)
        self.assertEqual(result["total_additional_cost"], 18750.0)
        self.assertEqual(result["new_unit_margin"], 39.5)


if __name__ == "__main__":
    unittest.main()
