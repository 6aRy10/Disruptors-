"""Measured mission preview timing comes from actual sample records."""
import unittest
from scripts.benchmark_mission_preview import summarize


class MissionMeasurementTests(unittest.TestCase):
    def test_no_unsupported_claims_or_fake_time_savings(self):
        samples = [
            {"metrics": {"total_elapsed_ms":12,"tool_calls":4,"tool_errors":0},
             "decision_gate": {"status":"EVIDENCE_REQUIRED"}},
            {"metrics": {"total_elapsed_ms":40,"tool_calls":5,"tool_errors":0},
             "decision_gate": {"status":"BACKUP_CHALLENGED"}},
            {"metrics": {"total_elapsed_ms":20,"tool_calls":5,"tool_errors":1},
             "decision_gate": {"status":"INCOMPLETE_TOOL_ERROR"}},
        ]
        result=summarize(samples)
        self.assertEqual(result["samples"],3)
        self.assertEqual(result["latency_ms_median"],20)
        self.assertEqual(result["latency_ms_p95_nearest_rank"],40)
        self.assertEqual(result["tool_calls_total"],14)
        self.assertEqual(result["tool_errors_total"],1)
        self.assertEqual(result["model_cost_usd"],0.0)
        self.assertIn("not a measured manual analyst comparison",result["note"])

    def test_empty_sample_is_rejected(self):
        with self.assertRaises(ValueError):
            summarize([])


if __name__ == "__main__":
    unittest.main()
