"""PortWatch integration: bounded polling, data freshness, source isolation."""
from datetime import UTC, datetime, timedelta
import unittest
from unittest.mock import patch

from scripts.watch_portwatch import _fresh_enough, poll_once
from scripts.run_live_stack import run_cycle


class PortWatchWorkerTests(unittest.TestCase):
    @patch("scripts.watch_portwatch.time.time", return_value=0)
    @patch("scripts.watch_portwatch.modeled_ports", return_value=["CNYTN", "IDJKT", "VNHPH", "VNSGN"])
    @patch("scripts.watch_portwatch.ports_by_unlocode")
    @patch("scripts.watch_portwatch.container_call_anomaly")
    def test_bounded_rotating_batch(self, anomaly, match, modeled, clock):
        match.return_value = []
        result = poll_once(baseline_days=30, max_ports=2)
        self.assertEqual(result["modeled_port_count"], 4)
        self.assertEqual(result["checked_port_count"], 2)
        self.assertEqual(match.call_count, 2)
        anomaly.assert_not_called()

    @patch("scripts.watch_portwatch.modeled_ports", return_value=["CNYTN", "IDJKT"])
    @patch("scripts.watch_portwatch.ports_by_unlocode")
    def test_port_lookup_error_does_not_hide_other_ports(self, match, modeled):
        match.side_effect = [TimeoutError("remote outage"), []]
        result = poll_once(baseline_days=30)
        self.assertEqual(len(result["source_errors"]), 1)
        self.assertEqual(len(result["unresolved_ports"]), 1)

    def test_stale_signal_not_accepted_as_live(self):
        old = (datetime.now(UTC) - timedelta(days=40)).timestamp() * 1000
        recent = (datetime.now(UTC) - timedelta(days=2)).timestamp() * 1000
        self.assertFalse(_fresh_enough({"occurred_at_epoch_ms": old}))
        self.assertTrue(_fresh_enough({"occurred_at_epoch_ms": recent}))

    @patch("scripts.run_live_stack.process_pending_events")
    @patch("scripts.run_live_stack.poll_portwatch_once")
    def test_portwatch_is_included_before_worker_and_reports_errors(self, pw, worker):
        pw.return_value = {
            "checked_port_count": 3, "modeled_port_count": 8,
            "created_events": [], "unresolved_ports": [],
            "stale_signals": [], "source_errors": [{"unlocode": "X", "error_type": "TimeoutError"}],
        }
        worker.return_value = {"attempted": 0, "succeeded": 0, "failed": 0}
        result = run_cycle(usgs=False, gdacs=False, portwatch=True)
        pw.assert_called_once_with(baseline_days=30, max_ports=3)
        worker.assert_called_once()
        self.assertEqual(result["sources"]["PORTWATCH"]["status"], "ERROR")
        self.assertEqual(result["status"], "DEGRADED")


if __name__ == "__main__":
    unittest.main()
