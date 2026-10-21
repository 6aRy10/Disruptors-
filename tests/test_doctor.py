"""Doctor must distinguish an old partial schema from an empty database."""
import unittest
from unittest.mock import patch, MagicMock

from scripts.doctor import report


class DoctorTests(unittest.TestCase):
    def test_partial_schema_reports_missing_tables(self):
        connection = MagicMock()
        def execute(sql, params=None):
            if "current_database()" in sql:
                return MagicMock(fetchone=lambda: ("Disruptors", "::1"))
            if "to_regclass" in sql:
                table = params[0]
                return MagicMock(fetchone=lambda: (table if table == "public.products" else None,))
            raise AssertionError("Missing tables must be checked before count queries")
        connection.execute.side_effect = execute
        context = MagicMock()
        context.__enter__.return_value = connection
        with patch("scripts.doctor.connect", return_value=context), \
             patch("scripts.doctor.database_url", return_value="postgresql://localhost/Disruptors"), \
             patch("urllib.request.urlopen", side_effect=OSError("offline")):
            result = report()
        self.assertEqual(result["status"], "SCHEMA_INCOMPLETE")
        self.assertIn("network_facilities", result["database"]["missing_tables"])
        self.assertEqual(result["data"], {})
        self.assertNotIn("password", str(result).lower())


if __name__ == "__main__":
    unittest.main()
