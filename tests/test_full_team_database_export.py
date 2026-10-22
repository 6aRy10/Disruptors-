"""Full team archive exporter safety tests. No real DB or backup subprocess."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from types import SimpleNamespace

from scripts.export_full_team_database import (
    export_full_database, pg_connection_environment,
)

LISTING = """1; 1 0 TABLE DATA public products alice
2; 2 0 TABLE DATA public bom alice
3; 3 0 TABLE DATA public material_allocations alice
4; 4 0 TABLE DATA public fulfilment_commitments alice
5; 5 0 TABLE DATA public external_events alice
"""


class FullArchiveSafety(TestCase):
    def test_pg_password_is_environment_not_process_argument(self):
        env, db = pg_connection_environment(
            "postgresql://user:secretpass@localhost:5432/hermes?sslmode=prefer"
        )
        self.assertEqual(db, "hermes")
        self.assertEqual(env["PGPASSWORD"], "secretpass")
        self.assertEqual(env["PGDATABASE"], "hermes")
        self.assertEqual(env["PGHOST"], "localhost")

    @patch("scripts.export_full_team_database.database_target", return_value="local")
    @patch("scripts.export_full_team_database.database_url",
           return_value="postgresql://test:secretpass@localhost:5432/hermes")
    @patch("scripts.export_full_team_database.subprocess.run")
    def test_full_dump_is_verified_with_readonly_commands(self, run, url, target):
        calls = []
        def execute(argv, **kwargs):
            calls.append(argv)
            self.assertNotIn("secretpass", " ".join(argv))
            self.assertEqual(kwargs["env"]["PGPASSWORD"], "secretpass")
            self.assertNotIn("pg_restore --dbname", " ".join(argv))
            if argv[0] == "pg_dump":
                path = Path(argv[argv.index("--file") + 1])
                path.write_bytes(b"VALID TEST ARCHIVE" * 10)
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
            return SimpleNamespace(
                returncode=0, stdout=LISTING.encode(), stderr=b"",
            )
        run.side_effect = execute
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"HERMES_FULL_TEAM_DB.dump"
            result=export_full_database(
                output, dump_path="pg_dump", restore_path="pg_restore"
            )
            self.assertEqual(result["status"],"COMPLETE_ARCHIVE_VERIFIED")
            self.assertTrue(output.exists())
            self.assertEqual(len(calls),2)
            self.assertIn("--no-owner",calls[0])
            self.assertIn("--no-acl",calls[0])
            self.assertIn("--format=custom",calls[0])
            self.assertEqual(calls[1][:2],["pg_restore","--list"])
            self.assertEqual(result["contents"],"ALL_CURRENT_TABLES_SCHEMA_AND_DATA")
            self.assertFalse(output.with_suffix(".dump.partial").exists())
            with self.assertRaises(FileExistsError):
                export_full_database(
                    output, dump_path="pg_dump", restore_path="pg_restore"
                )

    @patch("scripts.export_full_team_database.database_target", return_value="local")
    @patch("scripts.export_full_team_database.database_url",
           return_value="postgresql://test:pass@localhost/hermes")
    @patch("scripts.export_full_team_database.subprocess.run")
    def test_incomplete_dump_is_removed_and_not_shared(self, run, url, target):
        def bad(argv, **kwargs):
            if argv[0] == "pg_dump":
                Path(argv[argv.index("--file")+1]).write_bytes(b"FAILED" * 30)
                return SimpleNamespace(returncode=1, stdout=b"", stderr=b"secret password")
        run.side_effect=bad
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/"partial.dump"
            with self.assertRaises(RuntimeError):
                export_full_database(output,dump_path="pg_dump",restore_path="pg_restore")
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".dump.partial").exists())

    @patch("scripts.export_full_team_database.database_target", return_value="aiven")
    def test_refuses_wrong_target_before_connection(self, target):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                export_full_database(Path(tmp)/"wrong.dump")


if __name__=="__main__":
    import unittest
    unittest.main()
