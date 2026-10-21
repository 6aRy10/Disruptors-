"""Preflight must be safe when Aiven is not provisioned."""
import unittest
from unittest.mock import patch

from scripts.aiven_preflight import check_kafka, check_postgresql, report


class AivenPreflightTests(unittest.TestCase):
    @patch.dict("os.environ", {"AIVEN_DATABASE_URL": "", "AIVEN_KAFKA_BROKERS": ""})
    def test_not_configured_never_touches_network(self):
        with patch("scripts.aiven_preflight.psycopg.connect") as connect:
            result = report()
        connect.assert_not_called()
        self.assertEqual(result["aiven_postgresql"]["status"], "NOT_CONFIGURED")
        self.assertEqual(result["aiven_kafka"]["status"], "NOT_CONFIGURED")
        self.assertFalse(result["migration_performed"])

    @patch.dict("os.environ", {
        "AIVEN_KAFKA_BROKERS": "kafka.example:1234",
        "AIVEN_KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
        "AIVEN_KAFKA_USERNAME": "", "AIVEN_KAFKA_PASSWORD": "",
        "AIVEN_KAFKA_CERT_FILE": "", "AIVEN_KAFKA_KEY_FILE": "",
    })
    def test_plaintext_connection_rejected(self):
        self.assertEqual(check_kafka()["status"], "UNSAFE_PROTOCOL")

    @patch.dict("os.environ", {
        "AIVEN_KAFKA_BROKERS": "kafka.example:1234",
        "AIVEN_KAFKA_SECURITY_PROTOCOL": "SASL_SSL",
        "AIVEN_KAFKA_USERNAME": "user", "AIVEN_KAFKA_PASSWORD": "secret",
        "AIVEN_KAFKA_CERT_FILE": "", "AIVEN_KAFKA_KEY_FILE": "",
    })
    def test_auth_summary_never_contains_password(self):
        result = check_kafka()
        self.assertEqual(result["status"], "CONFIGURED_NOT_CONNECTED")
        self.assertNotIn("secret", str(result))

    def test_invalid_database_connection_redacts_credentials(self):
        with patch("scripts.aiven_preflight.psycopg.connect",
                   side_effect=RuntimeError("password leaked")):
            result = check_postgresql("postgresql://myuser:SECRET@example.test/data")
        self.assertEqual(result["status"], "CONNECTION_FAILED")
        self.assertNotIn("SECRET", str(result))
        self.assertNotIn("password leaked", str(result))


if __name__ == "__main__":
    unittest.main()
