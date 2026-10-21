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
    def test_local_processing_and_kafka_publication_remain_separate_counts(self, connect):
        db = MagicMock()
        def query(sql, params=None):
            if "current_database()" in sql:
                return MagicMock(fetchone=lambda: ("Disruptors",))
            if "to_regclass" in sql:
                return MagicMock(fetchone=lambda: ("exists",))
            if "SELECT version FROM operational_state_version" in sql:
                return MagicMock(fetchone=lambda: (1,))
            if "published_at IS NULL" in sql:
                return MagicMock(fetchone=lambda: (107,))
            if "FROM event_consumptions" in sql and "status='ERROR'" in sql:
                return MagicMock(fetchone=lambda: (0,))
            if "FROM event_consumptions" in sql and "status='SUCCESS'" in sql:
                return MagicMock(fetchone=lambda: (26,))
            if "NOT EXISTS" in sql and "event_consumptions" in sql:
                return MagicMock(fetchone=lambda: (81,))
            if "network_facilities" in sql:
                return MagicMock(fetchone=lambda: (770,))
            if "products WHERE sku LIKE" in sql:
                return MagicMock(fetchone=lambda: (2500,))
            if "material_allocations" in sql:
                return MagicMock(fetchone=lambda: (170018,))
            return MagicMock(fetchone=lambda: (2,))
        db.execute.side_effect = query
        connect.return_value.__enter__.return_value = db
        result = status_report()
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["runtime"]["unpublished_outbox_messages"], 107)
        self.assertEqual(result["runtime"]["processed_local_outbox_messages"], 26)
        self.assertEqual(result["runtime"]["pending_local_outbox_messages"], 81)
        self.assertEqual(result["runtime"]["failed_incident_consumptions"], 0)

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
