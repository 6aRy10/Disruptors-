"""Live collectors must not report a failed PortWatch source as healthy."""
import unittest
from unittest.mock import patch
from scripts.run_live_stack import run_cycle

class PollReceiptsTests(unittest.TestCase):
    @patch("scripts.run_live_stack.record_collector_check",return_value=True)
    @patch("scripts.run_live_stack.poll_gdacs_once")
    @patch("scripts.run_live_stack.poll_usgs_once")
    def test_poll_counts_are_recorded_once_per_source(self,usgs,gdacs,record):
        usgs.return_value={"received_count":6,"created_count":2}
        gdacs.return_value={"received_count":100,"created_count":3}
        result=run_cycle(worker=False)
        self.assertEqual(result["status"],"OK")
        self.assertEqual(result["sources"]["USGS"]["created_count"],2)
        self.assertEqual(result["sources"]["GDACS"]["received_count"],100)
        self.assertEqual(record.call_count,2)
        self.assertTrue(all(c.kwargs["status"]=="OK" for c in record.call_args_list))

    @patch("scripts.run_live_stack.record_collector_check",return_value=True)
    @patch("scripts.run_live_stack.poll_portwatch_once")
    def test_partial_portwatch_errors_are_failed_checks(self,portwatch,record):
        portwatch.return_value={
            "checked_port_count":3,"modeled_port_count":8,"created_events":[],
            "source_errors":[{"unlocode":"IDJKT","error_type":"TimeoutError"}],
            "unresolved_ports":[],"stale_signals":[],
        }
        result=run_cycle(usgs=False,gdacs=False,portwatch=True,worker=False)
        self.assertEqual(result["status"],"DEGRADED")
        self.assertEqual(result["sources"]["PORTWATCH"]["status"],"ERROR")
        self.assertEqual(record.call_args.kwargs["status"],"ERROR")
        self.assertEqual(record.call_args.kwargs["error_type"],"PartialSourceError")

    @patch("scripts.run_live_stack.record_collector_check",return_value=True)
    @patch("scripts.run_live_stack.poll_usgs_once",side_effect=TimeoutError("private provider URL"))
    def test_source_error_does_not_leak_sensitive_text(self,usgs,record):
        result=run_cycle(gdacs=False,worker=False)
        self.assertEqual(result["status"],"DEGRADED")
        self.assertEqual(result["sources"]["USGS"]["error_type"],"TimeoutError")
        self.assertNotIn("private provider URL",str(result))
        self.assertEqual(record.call_args.kwargs["status"],"ERROR")

if __name__=="__main__":
    unittest.main()
