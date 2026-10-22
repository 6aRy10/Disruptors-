"""Read-only team export: exclude protected data, keep ZIP outside Git."""
from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.export_team_model_snapshot import MODEL_TABLES, PROJECT_ROOT, export


class Rows:
    def fetchone(self):
        return (2,)


class Stream:
    def __enter__(self):
        return iter([b"id,label\\n1,modeled\\n2,modeled\\n"])
    def __exit__(self, *args):
        return False


class Cursor:
    def __init__(self, connection):
        self.connection = connection
    def execute(self, sql):
        self.connection.commands.append(sql)
        return Rows()
    def copy(self, sql):
        self.connection.commands.append(sql)
        return Stream()
    def close(self):
        pass


class Connection:
    def __init__(self):
        self.commands = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql):
        self.commands.append(sql)
    def cursor(self):
        return Cursor(self)


class TeamExportTests(unittest.TestCase):
    def test_allowlist_excludes_contacts_approval_and_telemetry(self):
        deny = {"operational_contacts", "supplier_confirmation_replies",
                "agent_runs", "action_executions", "event_outbox", "external_events",
                "incidents", "approval_requests", "incident_evidence"}
        self.assertFalse(deny.intersection(MODEL_TABLES))
        self.assertIn("material_allocations", MODEL_TABLES)
        self.assertIn("fulfilment_commitments", MODEL_TABLES)
        self.assertNotIn("trade_union", MODEL_TABLES["network_facility_relationships"])

    def test_export_is_read_only_and_has_checksummed_manifest(self):
        fake = Connection()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "private-team-joined.zip"
            with patch("scripts.export_team_model_snapshot.connect", return_value=fake), \
                 patch("scripts.export_team_model_snapshot.database_target",
                       return_value="local"):
                manifest = export(output)
            self.assertTrue(output.exists())
            self.assertIn("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
                          fake.commands)
            self.assertTrue(all(
                cmd.startswith("SET TRANSACTION") or cmd.startswith("SELECT COUNT(*)")
                or cmd.startswith("COPY (SELECT")
                for cmd in fake.commands))
            with zipfile.ZipFile(output) as z:
                self.assertIn("MANIFEST.json", z.namelist())
                data = json.loads(z.read("MANIFEST.json"))
                self.assertEqual(len(data["tables"]), len(MODEL_TABLES))
                self.assertEqual(data["classification"],
                                 "VERIFIED_PUBLIC_OR_SIMULATED_PRIVATE")
                self.assertNotIn("tables/operational_contacts.csv", z.namelist())
                self.assertEqual(manifest["tables"]["bom"]["rows"], 2)

    def test_overwrite_and_repo_output_are_blocked_without_db_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "already.zip"
            dest.write_bytes(b"do not replace")
            with self.assertRaises(FileExistsError):
                export(dest)
            self.assertEqual(dest.read_bytes(), b"do not replace")
        with self.assertRaises(ValueError):
            export(PROJECT_ROOT / "team-output.zip")


if __name__ == "__main__":
    unittest.main()
