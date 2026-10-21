"""Source claims must keep observed facts distinct from derived anomalies."""
import unittest
from unittest.mock import patch, MagicMock

from dependency.ingest.events import upsert_external_event
from dependency.ingest.portwatch import normalize_anomaly_event


class EventProvenanceTests(unittest.TestCase):
    @patch("dependency.ingest.events.connect")
    def test_upsert_persists_derived_provenance(self, connect):
        conn = MagicMock()
        conn.execute.return_value.fetchone.return_value = (True,)
        connect.return_value.__enter__.return_value = conn
        item = {
            "event_id": "PORTWATCH-EXAMPLE",
            "event_type": "port_activity_anomaly",
            "source": "IMF PortWatch",
            "longitude": 114.2, "latitude": 22.5,
            "provenance_class": "PUBLIC_DERIVED",
            "raw_json": {"port_unlocode": "CNYTN"},
        }
        upsert_external_event(item)
        params = conn.execute.call_args_list[1].args[1]
        self.assertEqual(params[-2], "PUBLIC_DERIVED")
        conn.commit.assert_called_once()

    def test_portwatch_derived_class(self):
        event = normalize_anomaly_event(
            port={"portid": "1", "LOCODE": "CN YTN", "lat": 22.1, "lon": 114.2},
            anomaly={"status": "MATERIAL_DROP", "date": 1609459200000, "pct_change_vs_baseline": -35}
        )
        self.assertEqual(event["provenance_class"], "PUBLIC_DERIVED")

    def test_invalid_provenance_fails_closed(self):
        with self.assertRaises(ValueError):
            upsert_external_event({"provenance_class": "IMAGINED"})


if __name__ == "__main__":
    unittest.main()
