"""Cross-source inspection reports observed outcomes without invented damage."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock
from datetime import UTC, datetime

from scripts.inspect_event import inspect_event, main


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

    @patch("scripts.inspect_event.trace_business_event_impact")
    @patch("scripts.inspect_event.connect")
    def test_investigating_incident_surfaces_open_evidence_tasks(self, connect, impact):
        now = datetime.now(UTC)
        conn = MagicMock()
        conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("DYN-EVENT", "wildfire", "GDACS",
                                         "LIVE", "VERIFIED_PUBLIC", now, now)),
            MagicMock(fetchone=lambda: ("SUCCESS", "OUT-9", None)),
            MagicMock(fetchone=lambda: ("INC-9", "INVESTIGATING", None)),
            MagicMock(fetchall=lambda: [("TASK-9", "CONFIRM_FACILITY_STATUS",
                                         "facility", "FAC-9", ["SKU-9"])]),
        ]
        connect.return_value.__enter__.return_value = conn
        impact.return_value = {
            "products": [{"sku": "SKU-9"}],
            "dependency_paths": [{"path_type": "ASSEMBLY"}],
            "facilities": [{"facility_id": "FAC-9"}],
            "totals": {"revenue_eur": 1000},
            "exposure_status": "POTENTIAL_ONLY",
        }
        result = inspect_event("DYN-EVENT")
        self.assertEqual(result["status"], "EVENT_INSPECTED")
        self.assertEqual(result["investigation"]["open_tasks_shown"], 1)
        self.assertEqual(result["investigation"]["tasks"][0]["task_id"], "TASK-9")
        self.assertIn("do not confirm", result["investigation"]["interpretation"])

    @patch("scripts.inspect_event.inspect_event")
    @patch("sys.argv", ["inspect_event", "DYN-EVENT"])
    def test_cli_succeeds_after_a_real_report_is_printed(self, inspect):
        inspect.return_value = {"status": "EVENT_INSPECTED", "event_id": "DYN-EVENT"}
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(main(), 0)
        self.assertIn("DYN-EVENT", printed.getvalue())

    @patch("scripts.inspect_event.inspect_event")
    @patch("sys.argv", ["inspect_event", "UNKNOWN"])
    def test_cli_returns_one_when_event_does_not_exist(self, inspect):
        inspect.return_value = {"status": "EVENT_NOT_FOUND", "event_id": "UNKNOWN"}
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 1)

    @patch("scripts.inspect_event.connect")
    def test_missing_event_does_not_invent_state(self, connect):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        connect.return_value.__enter__.return_value = db
        self.assertEqual(inspect_event("NONE")["status"], "EVENT_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
