"""Never let introducing Aiven credentials switch the active enterprise twin."""
import unittest
from unittest.mock import patch

from dependency.db.connection import database_target,database_url


class ExplicitDatabaseSelectionTests(unittest.TestCase):
    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://local.internal/demo",
        "AIVEN_DATABASE_URL":"postgresql://remote.internal/demo",
        "DEPENDENCY_DATABASE_TARGET":"",
    })
    def test_ambiguous_database_fails_closed(self):
        with self.assertRaises(RuntimeError):
            database_url()

    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://local.internal/demo",
        "AIVEN_DATABASE_URL":"postgresql://remote.internal/demo",
        "DEPENDENCY_DATABASE_TARGET":"local",
    })
    def test_local_data_not_switched(self):
        self.assertEqual(database_target(),"local")
        self.assertEqual(database_url(),"postgresql://local.internal/demo")

    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://local.internal/demo",
        "AIVEN_DATABASE_URL":"postgresql://remote.internal/demo",
        "DEPENDENCY_DATABASE_TARGET":"aiven",
    })
    def test_managed_requires_explicit_choice(self):
        self.assertEqual(database_url(),"postgresql://remote.internal/demo")

    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://local.internal/demo",
        "AIVEN_DATABASE_URL":"",
        "DEPENDENCY_DATABASE_TARGET":"",
    })
    def test_existing_local_only_setup_unchanged(self):
        self.assertEqual(database_url(),"postgresql://local.internal/demo")


if __name__=="__main__":
    unittest.main()
