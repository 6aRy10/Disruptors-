"""Check live feeds and orchestrator remain isolated and observable."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.run_live_stack import run_cycle


class LiveStackTests(unittest.TestCase):
    @patch("scripts.run_live_stack.process_pending_events")
    @patch("scripts.run_live_stack.poll_gdacs_once")
    @patch("scripts.run_live_stack.poll_usgs_once")
    def test_sources_and_orchestrator_run_together(self, usgs, gdacs, worker):
        worker.return_value = {"attempted": 2, "succeeded": 2, "failed": 0}
        result = run_cycle()
        usgs.assert_called_once()
        gdacs.assert_called_once()
        worker.assert_called_once()
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["sources"]["ORCHESTRATOR"]["succeeded"], 2)
        self.assertFalse(worker.call_args.kwargs["run_agents"])

    @patch("scripts.run_live_stack.process_pending_events")
    @patch("scripts.run_live_stack.poll_gdacs_once")
    @patch("scripts.run_live_stack.poll_usgs_once")
    def test_feed_failure_does_not_stop_outbox(self, usgs, gdacs, worker):
        usgs.side_effect = TimeoutError("feed unavailable")
        worker.return_value = {"attempted": 1, "succeeded": 1, "failed": 0}
        result = run_cycle()
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["sources"]["USGS"]["error_type"], "TimeoutError")
        gdacs.assert_called_once()
        worker.assert_called_once()

    @patch("scripts.run_live_stack.process_pending_events")
    def test_consumer_errors_are_visible(self, worker):
        worker.return_value = {"attempted": 1, "succeeded": 0, "failed": 1}
        result = run_cycle(usgs=False, gdacs=False)
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["sources"]["ORCHESTRATOR"]["status"], "FAILED_EVENTS")


if __name__ == "__main__":
    unittest.main()
