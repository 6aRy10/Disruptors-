"""Joint recovery must use dated confirmed factory-wide ceilings, not SKU sums."""
import unittest
from unittest.mock import patch
from dependency.solver.joint_optimization import optimize_joint_recovery


def orders(sku):
    return [{"order_id":sku+"-O","qty":80,"priority":1,"unit_margin_eur":20,
             "partial_allowed":True}]


def candidates(*,scenario_id,sku,release_safety_stock,include_provisional):
    return ([{"resource_id":"FAC-TEST","resource_type":"BACKUP_ASSEMBLY",
              "capacity_units":70,"provisional":False,"requires_approval":False,
              "transport_by_order":{sku+"-O":{"cost_eur_per_unit":1.0}}}],
            {"state_version":4})


class ConfirmedFacilityCapTests(unittest.TestCase):
    @patch("dependency.solver.joint_optimization._orders",side_effect=orders)
    @patch("dependency.solver.joint_optimization._resource_candidates",side_effect=candidates)
    @patch("dependency.solver.joint_optimization.confirmed_capacity_for_scenario")
    def test_confirmed_ceiling_changes_joint_allocation(self, caps, resources, get_orders):
        caps.return_value={"FAC-TEST":{"available_units":25,"week_start":"2026-10-19",
                    "valid_until":"2026-10-25","evidence_reference":"CONFIRMED-1"}}
        result=optimize_joint_recovery(scenario_id="S",skus=["A","B"])
        self.assertEqual(result["protected_units"],25)
        self.assertEqual(result["late_units"],135)
        self.assertEqual(result["shared_facility_allocated"]["FAC-TEST"],25)
        self.assertEqual(result["unverified_shared_capacity_facilities"],[])
        self.assertEqual(result["capacity_limit_source"]["FAC-TEST"],"CONFIRMED_DATED_FACILITY_CAPACITY")

    @patch("dependency.solver.joint_optimization._orders",side_effect=orders)
    @patch("dependency.solver.joint_optimization._resource_candidates",side_effect=candidates)
    @patch("dependency.solver.joint_optimization.confirmed_capacity_for_scenario",return_value={})
    def test_no_confirmation_never_marks_shared_ceiling_verified(self,caps,resources,get_orders):
        result=optimize_joint_recovery(scenario_id="S",skus=["A","B"])
        self.assertEqual(result["shared_facility_capacity"]["FAC-TEST"],70)
        self.assertFalse(result["portfolio_allocation_verified"])
        self.assertIn("FAC-TEST",result["unverified_shared_capacity_facilities"])

    @patch("dependency.solver.joint_optimization._orders",side_effect=orders)
    @patch("dependency.solver.joint_optimization._resource_candidates",side_effect=candidates)
    @patch("dependency.solver.joint_optimization.confirmed_capacity_for_scenario")
    def test_test_override_is_not_conflated_with_real_evidence(self,caps,resources,get_orders):
        caps.return_value={}
        result=optimize_joint_recovery(scenario_id="S",skus=["A","B"],
                                        shared_capacity_limits={"FAC-TEST":19})
        self.assertEqual(result["protected_units"],19)
        self.assertFalse(result["portfolio_allocation_verified"])
        self.assertEqual(result["capacity_limit_source"]["FAC-TEST"],"UNVERIFIED_CALLER_OVERRIDE")


if __name__=="__main__":
    unittest.main()
