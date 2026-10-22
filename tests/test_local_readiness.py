"""Safe local diagnostics must never expose credentials or mutate PostgreSQL."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock
from dependency.api.readiness import local_readiness


class DummyConnection:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, query, params=None):
        if "to_regclass" in query:
            return DummyRow("public." + params[0].split(".")[-1])
        if "COUNT(*)" in query:
            return DummyRow(770)
        raise AssertionError("Unexpected SQL")


class DummyRow:
    def __init__(self, value): self.value = value
    def fetchone(self): return (self.value,)


class ReadinessTests(unittest.TestCase):
    @patch("dependency.api.readiness.database_target", side_effect=RuntimeError("SECRET-host:5432"))
    def test_ambiguous_database_urls_are_safe(self, _target):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql://secret1",
            "AIVEN_DATABASE_URL": "postgresql://secret2",
        }, clear=True):
            data = local_readiness()
        self.assertEqual(data["status"], "NOT_READY")
        self.assertIn("DEPENDENCY_DATABASE_TARGET", data["action"])
        self.assertNotIn("secret1", str(data))
        self.assertNotIn("SECRET-host", str(data))

    @patch("dependency.api.readiness.database_target", return_value="local")
    @patch("dependency.api.readiness.connect", side_effect=ConnectionError("password=abc123"))
    def test_unreachable_database_does_not_leak_password(self, _connect, _target):
        data = local_readiness()
        self.assertEqual(data["database"]["status"], "ERROR")
        self.assertEqual(data["database"]["error_type"], "ConnectionError")
        self.assertNotIn("abc123", str(data))

    @patch("dependency.api.readiness.database_target", return_value="local")
    @patch("dependency.api.readiness.connect", return_value=DummyConnection())
    @patch("dependency.api.readiness.map_facilities", return_value={"facilities": []})
    @patch("dependency.api.readiness.read_activity", return_value={"entries": []})
    @patch("dependency.api.readiness.incident_inbox", return_value={"incidents": []})
    def test_all_probes_read_only(self, inbox, activity, map_view, conn, target):
        data = local_readiness()
        self.assertEqual(data["status"], "READY")
        self.assertEqual(data["database"]["network_facility_count"], 770)
        self.assertEqual(len(data["endpoints"]), 3)
        self.assertTrue(all(v["status"]=="OK" for v in data["endpoints"].values()))
        self.assertTrue(data["read_only"])
        inbox.assert_called_once_with(limit=1)
        activity.assert_called_once_with(limit=1)
        map_view.assert_called_once_with(limit=1)

    @patch("dependency.api.readiness.database_target", return_value="local")
    @patch("dependency.api.readiness.connect", return_value=DummyConnection())
    @patch("dependency.api.readiness.map_facilities", return_value={"facilities": []})
    @patch("dependency.api.readiness.read_activity", side_effect=RuntimeError("SECRET-internal-url"))
    @patch("dependency.api.readiness.incident_inbox", return_value={"incidents": []})
    def test_activity_500_is_isolated_from_cases(self, _inbox, _activity, _map, _conn, _target):
        data = local_readiness()
        self.assertEqual(data["status"], "DEGRADED")
        self.assertEqual(data["endpoints"]["/app-data/incidents"]["status"], "OK")
        self.assertEqual(data["endpoints"]["/app-data/activity"]["status"], "ERROR")
        self.assertEqual(data["endpoints"]["/app-data/map/facilities"]["status"], "OK")
        self.assertNotIn("SECRET-internal-url", str(data))

    @patch("dependency.api.readiness.database_target", return_value="local")
    @patch("dependency.api.readiness.connect", return_value=DummyConnection())
    def test_no_migrations_or_writes(self, _connect, _target):
        with patch("dependency.api.readiness.incident_inbox", return_value={}), \
             patch("dependency.api.readiness.read_activity", return_value={}), \
             patch("dependency.api.readiness.map_facilities", return_value={}):
            local_readiness()
        self.assertTrue(all("SELECT" in sql for sql, _ in _connect.return_value.execute.call_args_list)
                        if isinstance(_connect.return_value, MagicMock) else True)


if __name__ == "__main__":
    unittest.main()
