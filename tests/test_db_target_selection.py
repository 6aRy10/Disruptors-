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


class AivenRuntimeInjectedDatabaseTests(unittest.TestCase):
    """Runtime integrations inject DATABASE_URL; accept it only for an explicit aiven target."""

    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://u:p@hermes-db-x.e.aivencloud.com:19369/defaultdb?sslmode=require",
        "AIVEN_DATABASE_URL":"",
        "DEPENDENCY_DATABASE_TARGET":"aiven",
    })
    def test_injected_managed_url_used_when_aiven_selected(self):
        self.assertEqual(database_target(),"aiven")
        self.assertIn("aivencloud.com",database_url())

    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://u:p@injected.aivencloud.com:19369/defaultdb",
        "AIVEN_DATABASE_URL":"postgresql://u:p@explicit.aivencloud.com:19369/defaultdb",
        "DEPENDENCY_DATABASE_TARGET":"aiven",
    })
    def test_explicit_aiven_url_is_never_overridden(self):
        self.assertIn("explicit.aivencloud.com",database_url())

    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://postgres:x@localhost:5432/Disruptors",
        "AIVEN_DATABASE_URL":"",
        "DEPENDENCY_DATABASE_TARGET":"aiven",
    })
    def test_local_url_never_masquerades_as_aiven(self):
        with self.assertRaises(RuntimeError):
            database_url()

    @patch.dict("os.environ",{
        "DATABASE_URL":"postgresql://u:p@injected.aivencloud.com:19369/defaultdb",
        "AIVEN_DATABASE_URL":"",
        "DEPENDENCY_DATABASE_TARGET":"",
    })
    def test_without_explicit_target_injected_url_is_plain_local(self):
        self.assertEqual(database_target(),"local")


if __name__=="__main__":
    unittest.main()
