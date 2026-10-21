"""Adversarial shared-facility competition tests with synthetic independent SKUs."""
import unittest
from unittest.mock import patch

from dependency.solver.joint_optimization import optimize_joint_recovery


def orders(sku):
    return [{
        "order_id": f"{sku}-O1", "qty": 80, "priority": 1,
        "unit_margin_eur": 20.0, "unit_revenue_eur": 50.0,
        "partial_allowed": True,
    }]


def candidates(*, scenario_id, sku, release_safety_stock, include_provisional):
    return ([{
        "resource_id": "SAME-FACTORY", "resource_type": "BACKUP_ASSEMBLY",
        "capacity_units": 60, "provisional": False, "requires_approval": False,
        "transport_by_order": {f"{sku}-O1": {
            "lane_id": "TEST-LANE", "cost_eur_per_unit": 1.0
        }},
    }], {"state_version": 7})


class JointOptimizationTests(unittest.TestCase):
    def test_same_facility_is_not_counted_twice(self):
        with patch("dependency.solver.joint_optimization._orders", side_effect=orders), \
             patch("dependency.solver.joint_optimization._resource_candidates", side_effect=candidates):
            outcome = optimize_joint_recovery(scenario_id="SCENARIO", skus=["A", "B"])
        self.assertEqual(outcome["protected_units"], 60)
        self.assertEqual(outcome["late_units"], 100)
        self.assertEqual(outcome["shared_facility_allocated"]["SAME-FACTORY"], 60)
        self.assertFalse(outcome["portfolio_allocation_verified"])
        self.assertEqual(outcome["unverified_shared_capacity_facilities"], ["SAME-FACTORY"])

    def test_explicit_lower_capacity_limit_changes_solution(self):
        with patch("dependency.solver.joint_optimization._orders", side_effect=orders), \
             patch("dependency.solver.joint_optimization._resource_candidates", side_effect=candidates):
            outcome = optimize_joint_recovery(
                scenario_id="SCENARIO", skus=["A", "B"],
                shared_capacity_limits={"SAME-FACTORY": 25},
            )
        self.assertEqual(outcome["protected_units"], 25)
        self.assertEqual(outcome["shared_facility_allocated"]["SAME-FACTORY"], 25)
        self.assertEqual(outcome["unverified_shared_capacity_facilities"], [])

    def test_invalid_capacity_is_rejected(self):
        with self.assertRaises(ValueError):
            optimize_joint_recovery(scenario_id="SCENARIO", skus=["A"], shared_capacity_limits={"X": -1})


if __name__ == "__main__":
    unittest.main()
