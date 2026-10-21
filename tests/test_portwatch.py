import unittest

from dependency.ingest.portwatch import normalize_anomaly_event


class PortWatchNormalizationTests(unittest.TestCase):
    def test_material_port_drop_becomes_normalized_external_event(self):
        event = normalize_anomaly_event(
            port={
                "portid": "TEST-YTN",
                "portname": "Yantian",
                "country": "China",
                "ISO3": "CHN",
                "lat": 22.6,
                "lon": 114.3,
                "LOCODE": "CN YTN",
            },
            anomaly={
                "portid": "TEST-YTN",
                "portname": "Yantian",
                "date": 1609459200000,
                "latest_container_calls": 40.0,
                "baseline_container_calls": 100.0,
                "pct_change_vs_baseline": -60.0,
                "status": "SEVERE_DROP",
                "observations": 31,
                "baseline_days": 30,
                "source": "IMF PortWatch",
            },
        )
        self.assertIsNotNone(event)
        self.assertEqual(
            event["event_id"],
            "PORTWATCH-TEST-YTN-2021-01-01",
        )
        self.assertEqual(event["event_type"], "port_activity_anomaly")
        self.assertEqual(event["raw_json"]["port_unlocode"], "CNYTN")
        self.assertEqual(event["occurred_at_epoch_ms"], 1609459200000.0)

    def test_normal_activity_does_not_create_incident_signal(self):
        event = normalize_anomaly_event(
            port={
                "portid": "TEST",
                "portname": "Test Port",
                "lat": 1.0,
                "lon": 2.0,
                "LOCODE": "XXABC",
            },
            anomaly={
                "portid": "TEST",
                "date": 1609459200000,
                "status": "WITHIN_BASELINE",
                "pct_change_vs_baseline": -5.0,
            },
        )
        self.assertIsNone(event)


if __name__ == "__main__":
    unittest.main()
