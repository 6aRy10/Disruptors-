"""Local team status must be read-only, credential safe, and incomplete-safe."""
import unittest
from unittest.mock import MagicMock, patch
from scripts.team_status import status_report


class TeamStatusTests(unittest.TestCase):
    @patch("scripts.team_status.connect")
    def test_missing_connection_redacts_secrets(self, connect):
        connect.side_effect = RuntimeError("PASSWORD=secret")
        result = status_report()
        self.assertEqual(result["status"], "NOT_READY")
        self.assertNotIn("secret", str(result))

    @patch("scripts.team_status.connect")
    def test_incomplete_schema_does_not_query_missing_tables(self, connect):
        connection = MagicMock()
        def query(sql, params=None):
            if "current_database()" in sql:
                return MagicMock(fetchone=lambda: ("Disruptors",))
            if "to_regclass" in sql:
                return MagicMock(fetchone=lambda: (None,))
            raise AssertionError("Must not inspect an absent table")
        connection.execute.side_effect = query
        connect.return_value.__enter__.return_value = connection
        result = status_report()
        self.assertEqual(result["status"], "SCHEMA_INCOMPLETE")
        self.assertIn("open_evidence_tasks", result["database"]["missing_components"])
        self.assertEqual(result["records"], {})


if __name__ == "__main__":
    unittest.main()
