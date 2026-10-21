import unittest

from dependency.dashboard.snapshot import dashboard_snapshot
from dependency.services.demo_reset import reset_demo_state


class DashboardSnapshotTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_snapshot_is_side_effect_free_and_exposes_judge_context(self):
        first = dashboard_snapshot(
            event_id="IDN-CIANJUR-2022-USGS-us7000ir9t",
            scenario_id="SCN-CIANJUR-REPLAY-01",
            radius_km=150,
        )
        second = dashboard_snapshot(
            event_id="IDN-CIANJUR-2022-USGS-us7000ir9t",
            scenario_id="SCN-CIANJUR-REPLAY-01",
            radius_km=150,
        )

        self.assertEqual(first["metrics"]["state_version"], 1)
        self.assertEqual(second["metrics"]["state_version"], 1)
        self.assertEqual(first["network"]["stats"]["network_facilities"], 770)
        self.assertEqual(
            first["network"]["stats"]["official_list_relationships"],
            836,
        )
        self.assertEqual(len(first["network"]["facilities"]), 770)
        self.assertEqual(
            first["selected"]["event_id"],
            "IDN-CIANJUR-2022-USGS-us7000ir9t",
        )
        self.assertEqual(
            first["selected"]["scenario_id"],
            "SCN-CIANJUR-REPLAY-01",
        )
        self.assertIsNotNone(first["selected"]["impact"])
        self.assertIsNotNone(first["selected"]["portfolio"])
        self.assertIn("VERIFIED_PUBLIC", first["truth_model"])
        self.assertIn("SIMULATED_PRIVATE", first["truth_model"])
        self.assertGreaterEqual(len(first["claim_rules"]), 4)


if __name__ == "__main__":
    unittest.main()
