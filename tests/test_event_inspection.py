"""Cross-source inspection reports observed outcomes without invented damage."""
import unittest
from unittest.mock import patch, MagicMock
from datetime import UTC, datetime

from scripts.inspect_event import inspect_event


class EventInspectionTests(unittest.TestCase):
    @patch("scripts.inspect_event.trace_business_event_impact")
    @patch("scripts.inspect_event.connect")
    def test_public_exposure_without_private_orders_is_not_reported_as_loss(self, connect, impact):
        now = datetime.now(UTC)
        db = MagicMock()
        db.execute.side_effect = [
            MagicMock(fetchone=lambda: ("GDACS-WF-TEST", "wildfire", "GDACS", "LIVE", "VERIFIED_PUBLIC", now, now)),
            MagicMock(fetchone=lambda: ("SUCCESS", "OUT-1", None)),
            MagicMock(fetchone=lambda: None),
        ]
        connect.return_value.__enter__.return_value = db
        impact.return_value = {
            "exposure_basis": "GEOSPATIAL_PROXIMITY",
            "exposure_status": "POTENTIALLY_EXPOSED",
            "facilities": [{"facility_id": "F1"}],
            "dependency_paths": [], "products": [], "totals": {},
        }
        result = inspect_event("GDACS-WF-TEST")
        self.assertEqual(result["event_queue"]["status"], "SUCCESS")
        self.assertEqual(result["business_exposure"]["connected_product_count"], 0)
        self.assertIn("public proximity", result["next_evidence"])

    @patch("scripts.inspect_event.connect")
    def test_missing_event_does_not_invent_state(self, connect):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        connect.return_value.__enter__.return_value = db
        self.assertEqual(inspect_event("NONE")["status"], "EVENT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
