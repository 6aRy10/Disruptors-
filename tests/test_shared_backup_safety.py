"""Prevent independently optimized SKUs from being presented as one verified plan."""
from __future__ import annotations

import unittest

from dependency.solver.portfolio import _shared_backup_conflicts, plan_event_recovery


class SharedBackupSafetyTests(unittest.TestCase):
    def test_flags_competing_non_rejected_backup_candidates(self):
        def product(sku, decision="FEASIBLE"):
            return {
                "sku": sku,
                "candidates": [{
                    "plan_type": "ASSEMBLY_REALLOCATION",
                    "decision": decision,
                    "evidence": {
                        "backup_facility_id": "TEST-SHARED-BACKUP",
                        "backup_facility_name": "Shared capacity",
                    },
                }],
            }
        found = _shared_backup_conflicts([product("SKU-A"), product("SKU-B")])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["candidate_skus"], ["SKU-A", "SKU-B"])
        self.assertEqual(found[0]["status"], "CAPACITY_CONFLICT_CHECK_REQUIRED")
        self.assertEqual(
            _shared_backup_conflicts([product("SKU-A"), product("SKU-B", "REJECTED")]),
            [],
        )

    def test_portfolio_discloses_joint_allocation_limitation(self):
        result = plan_event_recovery(
            event_id="IDN-CIANJUR-2022-USGS-us7000ir9t",
            scenario_id="SCN-CIANJUR-REPLAY-01",
            radius_km=150,
        )
        self.assertIn("shared_capacity_validation_required", result)
        self.assertIn("portfolio_allocation_verified", result)
        self.assertIsInstance(result["portfolio_allocation_verified"], bool)
        if result["shared_resource_conflicts"]:
            self.assertTrue(result["shared_capacity_validation_required"])
            self.assertFalse(result["portfolio_allocation_verified"])


if __name__ == "__main__":
    unittest.main()
