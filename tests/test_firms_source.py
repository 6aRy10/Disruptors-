"""NASA FIRMS adapter must not invent a fire or dispatch incident tasks."""
from __future__ import annotations
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

from dependency.ingest.firms import fetch_hotspots, parse_viirs_csv, store_hotspots

CSV = (
    "latitude,longitude,acq_date,acq_time,satellite,confidence,frp\n"
    "-6.21000,106.85000,2026-10-21,0815,N20,n,12.4\n"
    "-6.21000,106.85000,2026-10-21,0815,N20,n,12.4\n"
    "95.1,106.8,2026-10-21,0815,N20,l,3.1\n"
    "-6.30000,107.10000,2026-10-21,0920,N20,h,28.2\n"
)

class FakeReader:
    def __init__(self, contents): self.contents=contents
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self, limit): return self.contents

class FakeCursor:
    def __init__(self, value): self.value=value
    def fetchone(self): return (self.value,)

class FakeConnection:
    def __init__(self): self.queries=[]; self.committed=False
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self, sql, params):
        self.queries.append((sql,params))
        if "to_regclass" in sql: return FakeCursor("source_observations")
        if "INSERT INTO source_observations" in sql: return FakeCursor(True)
        raise AssertionError("Unexpected SQL")
    def commit(self): self.committed=True

class FirmsContracts(unittest.TestCase):
    def test_csv_deduplicates_pixels_without_calling_them_wildfires(self):
        pixels=parse_viirs_csv(CSV,sensor="VIIRS_NOAA20_NRT")
        self.assertEqual(len(pixels),2)
        self.assertEqual(pixels[0]["observed_at"],
                         datetime(2026,10,21,8,15,tzinfo=timezone.utc))
        self.assertEqual(pixels[0]["observation_type"],
                         "ACTIVE_FIRE_SATELLITE_PIXEL")
        self.assertNotIn("wildfire",pixels[0]["observation_type"].lower())
        self.assertEqual(
            parse_viirs_csv(CSV,sensor="VIIRS_NOAA20_NRT")[0]["observation_id"],
            pixels[0]["observation_id"],
        )
        self.assertEqual(pixels[0]["data_provenance"],"VERIFIED_PUBLIC")

    @patch("dependency.ingest.firms.urlopen")
    def test_request_bounded_and_no_key_in_returned_data(self, urlopen):
        urlopen.return_value = FakeReader(CSV.encode())
        result=fetch_hotspots(map_key="SECRETKEY",bounds=(95,-11,141,6),days=1)
        self.assertEqual(len(result),2)
        self.assertNotIn("SECRETKEY",str(result))
        request=urlopen.call_args.args[0]
        self.assertIn("VIIRS_NOAA20_NRT",request.full_url)
        self.assertIn("/95,-11,141,6/1",request.full_url)
        with self.assertRaises(ValueError):
            fetch_hotspots(map_key="BAD/KEY")

    @patch("dependency.ingest.firms.connect")
    def test_saves_pixels_separately_without_external_event_or_outbox(self, connect):
        db=FakeConnection()
        connect.return_value=db
        result=store_hotspots(parse_viirs_csv(CSV,sensor="VIIRS_NOAA20_NRT"))
        self.assertEqual(result["created_count"],2)
        self.assertEqual(result["incident_tasks_created"],0)
        self.assertTrue(db.committed)
        all_sql=" ".join(sql for sql,_ in db.queries)
        self.assertIn("INSERT INTO source_observations",all_sql)
        self.assertNotIn("event_outbox",all_sql)
        self.assertNotIn("external_events",all_sql)
        self.assertNotIn("incidents",all_sql)

    def test_reject_bad_or_oversized_inputs(self):
        with self.assertRaises(ValueError):
            parse_viirs_csv("bad,data\n1,2",sensor="VIIRS_NOAA20_NRT")
        with self.assertRaises(ValueError):
            parse_viirs_csv(CSV,sensor="VIIRS_SNPP_NRT")
        with self.assertRaises(ValueError):
            store_hotspots([{"x":1}]*5001)
        with self.assertRaises(ValueError):
            fetch_hotspots(map_key="KEY",days=6)
        with self.assertRaises(ValueError):
            fetch_hotspots(map_key="KEY",bounds=(50,80,60,30))

if __name__=="__main__":
    unittest.main()
