"""Unresolved incident events must remain selectable despite noisy feed volume."""
from datetime import UTC,datetime
import unittest
from unittest.mock import patch,MagicMock
from dependency.dashboard.snapshot import _event_feed_with_open_incidents


class OpenIncidentFeedTests(unittest.TestCase):
    def test_no_missing_events_skips_database_read(self):
        recent=[{"event_id":"LIVE-1"}]
        result=_event_feed_with_open_incidents(recent,[{"event_id":"LIVE-1"}])
        self.assertEqual(result,recent)

    @patch("dependency.dashboard.snapshot.connect")
    def test_old_open_incident_is_visible_even_when_not_recent(self, connect):
        now=datetime.now(UTC)
        db=MagicMock()
        db.execute.return_value.fetchall.return_value=[
            ("GDACS-WF-TEST","wildfire","LIVE","GDACS","Wildfire in Indonesia",
             now,now,None,"https://example.invalid"),
        ]
        connect.return_value.__enter__.return_value=db
        recent=[{"event_id":f"NEW-{i}"} for i in range(50)]
        opened=[{"event_id":"GDACS-WF-TEST"},{"event_id":"GDACS-WF-TEST"}]
        result=_event_feed_with_open_incidents(recent,opened)
        self.assertEqual(len(result),51)
        self.assertEqual(result[0]["event_id"],"GDACS-WF-TEST")
        self.assertEqual(sum(e["event_id"]=="GDACS-WF-TEST" for e in result),1)
        self.assertEqual(db.execute.call_args.args[1],(["GDACS-WF-TEST"],))


if __name__=="__main__":
    unittest.main()
