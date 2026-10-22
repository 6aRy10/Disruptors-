"""Source-event timeline must not invent collector or broker health."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from dependency.graph.activity_stream import read_activity

NOW=datetime.now(timezone.utc)

class Cursor:
    def __init__(self, rows): self.rows=rows
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0] if self.rows else None

class Connection:
    def __init__(self, migrated=True): self.migrated=migrated; self.queries=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self, sql, params=None):
        self.queries.append((sql,params))
        if "JOIN external_events e" in sql:
            return Cursor([
                ("OUT-A","GDACS-WF-1","GDACS","wildfire","Reported wildfire","LIVE",
                 NOW-timedelta(days=7),NOW-timedelta(minutes=3),
                 "https://example.test","VERIFIED_PUBLIC","SUCCESS",NOW,
                 "INC-1","INVESTIGATING",2),
                ("OUT-B","USGS-EQ-1","USGS","earthquake","Recorded quake","LIVE",
                 NOW-timedelta(days=2),NOW-timedelta(days=2),
                 "https://example.test","VERIFIED_PUBLIC",None,None,None,None,None),
            ])
        if "GROUP BY source ORDER BY source" in sql:
            return Cursor([("GDACS",42,NOW,NOW-timedelta(days=7)),("USGS",50,NOW-timedelta(days=2),NOW-timedelta(days=2))])
        if "COUNT(*) FILTER" in sql: return Cursor([(3,120)])
        if "to_regclass" in sql: return Cursor([("collector_checks" if self.migrated else None,)])
        if "DISTINCT ON (source)" in sql:
            return Cursor([("GDACS",NOW-timedelta(minutes=1),"OK",80,1,None),
                           ("USGS",NOW-timedelta(hours=3),"ERROR",0,0,"TimeoutError")])
        raise AssertionError("Unknown query: "+sql[:90])

class SourceActivityContract(unittest.TestCase):
    def test_correct_receipt_order_and_distinct_counters(self):
        db=Connection()
        with patch("dependency.graph.activity_stream.connect",return_value=db):
            result=read_activity(limit=40)
        self.assertEqual(result["returned_count"],2)
        self.assertEqual(result["entries"][0]["entry_id"],"OUT-A")
        self.assertNotEqual(result["entries"][0]["occurred_at"],result["entries"][0]["first_recorded_at"])
        self.assertEqual(result["entries"][1]["local_processing"],"PENDING")
        self.assertEqual(result["entries"][0]["open_evidence_tasks"],2)
        self.assertEqual(result["processing"]["pending_local_outbox_messages"],3)
        self.assertEqual(result["processing"]["unpublished_kafka_outbox_messages"],120)
        self.assertEqual(result["processing"]["kafka_broker_status"],"NOT_VERIFIED")
        self.assertIn("o.created_at DESC",db.queries[0][0])
        self.assertIn("o.topic='external.events'",db.queries[0][0])

    def test_source_check_is_distinct_from_ingestion_and_staleness(self):
        db=Connection()
        with patch("dependency.graph.activity_stream.connect",return_value=db):
            result=read_activity()
        states={x["source"]:x for x in result["sources"]}
        self.assertEqual(states["GDACS"]["collector_status"],"RECENT_SUCCESS")
        self.assertEqual(states["GDACS"]["last_poll_created_count"],1)
        self.assertEqual(states["USGS"]["collector_status"],"STALE")
        self.assertEqual(states["IMF PortWatch"]["collector_status"],"NOT_VERIFIED")

    def test_old_database_without_migration_returns_not_verified(self):
        db=Connection(migrated=False)
        with patch("dependency.graph.activity_stream.connect",return_value=db):
            result=read_activity()
        self.assertTrue(all(x["collector_status"]=="NOT_VERIFIED" for x in result["sources"]))

    def test_parameterized_query_and_bounds(self):
        db=Connection()
        with patch("dependency.graph.activity_stream.connect",return_value=db):
            read_activity(limit=9,source="USGS' OR 1=1 --",since=NOW)
        sql,params=db.queries[0]
        self.assertNotIn("OR 1=1",sql)
        self.assertEqual(params[-1],9)
        self.assertEqual(params[2],"USGS' OR 1=1 --")
        with self.assertRaises(ValueError): read_activity(limit=201)
        with self.assertRaises(ValueError): read_activity(since=NOW.replace(tzinfo=None))
        with self.assertRaises(ValueError): read_activity(source=" ")

if __name__=="__main__":
    unittest.main()
