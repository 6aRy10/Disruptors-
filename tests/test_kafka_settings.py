"""Kafka settings accept project and Aiven Runtime variables, fail closed, leak nothing."""
import unittest
from unittest.mock import patch

from dependency.events.kafka_settings import load_kafka_settings

CLEAR = {k: "" for k in (
    "AIVEN_KAFKA_BROKERS", "AIVEN_KAFKA_SECURITY_PROTOCOL", "AIVEN_KAFKA_CA_FILE",
    "AIVEN_KAFKA_CERT_FILE", "AIVEN_KAFKA_KEY_FILE", "AIVEN_KAFKA_USERNAME",
    "AIVEN_KAFKA_PASSWORD", "AIVEN_KAFKA_CA_PEM", "AIVEN_KAFKA_CERT_PEM",
    "AIVEN_KAFKA_KEY_PEM", "AIVEN_KAFKA_ALLOW_PLAINTEXT", "KAFKA_BOOTSTRAP_SERVERS",
    "KAFKA_SECURITY_PROTOCOL", "KAFKA_ACCESS_KEY", "KAFKA_ACCESS_CERT", "KAFKA_CA_CERT",
    "AIVEN_KAFKA_SASL_MECHANISM",
)}


@patch("dependency.events.kafka_settings.os.path.isfile", new=lambda path: True)
class KafkaSettingsTests(unittest.TestCase):
    @patch.dict("os.environ", CLEAR)
    def test_unconfigured_is_invalid_and_raises_on_config(self):
        settings = load_kafka_settings()
        description = settings.describe()
        self.assertFalse(description["configured"])
        self.assertFalse(description["valid"])
        with self.assertRaises(RuntimeError):
            settings.librdkafka()

    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "k1.aivencloud.com:12345,k2.aivencloud.com:12345",
        "AIVEN_KAFKA_CA_FILE": "/certs/ca.pem",
        "AIVEN_KAFKA_CERT_FILE": "/certs/service.cert",
        "AIVEN_KAFKA_KEY_FILE": "/certs/service.key"})
    def test_file_based_mtls(self):
        settings = load_kafka_settings()
        config = settings.librdkafka()
        self.assertEqual(config["security.protocol"], "SSL")
        self.assertEqual(config["ssl.ca.location"], "/certs/ca.pem")
        self.assertEqual(config["ssl.certificate.location"], "/certs/service.cert")
        self.assertNotIn("sasl.username", config)
        description = settings.describe()
        self.assertEqual(description["auth_method"], "MTLS")
        self.assertEqual(description["broker_count"], 2)
        self.assertEqual(description["credential_format"], "file")
        self.assertTrue(description["valid"])

    @patch.dict("os.environ", {**CLEAR,
        "KAFKA_BOOTSTRAP_SERVERS": "runtime-kafka.aivencloud.com:12345",
        "KAFKA_SECURITY_PROTOCOL": "SSL",
        "KAFKA_CA_CERT": "-----BEGIN CERTIFICATE-----\\nCA\\n-----END CERTIFICATE-----",
        "KAFKA_ACCESS_CERT": "-----BEGIN CERTIFICATE-----\nCERT\n-----END CERTIFICATE-----",
        "KAFKA_ACCESS_KEY": "-----BEGIN PRIVATE KEY-----\nSECRETKEY\n-----END PRIVATE KEY-----"})
    def test_aiven_runtime_inline_pem_variables(self):
        settings = load_kafka_settings()
        config = settings.librdkafka()
        self.assertEqual(settings.source, "KAFKA_BOOTSTRAP_SERVERS")
        self.assertIn("ssl.ca.pem", config)
        self.assertIn("\nCA\n", config["ssl.ca.pem"], "escaped newlines are restored")
        self.assertEqual(config["ssl.key.pem"].splitlines()[1], "SECRETKEY")
        self.assertNotIn("ssl.ca.location", config)
        description = settings.describe()
        self.assertEqual(description["credential_format"], "inline_pem")
        self.assertTrue(description["valid"])
        self.assertNotIn("SECRETKEY", str(description))
        self.assertNotIn("SECRETKEY", repr(settings))

    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "k.aivencloud.com:12346",
        "AIVEN_KAFKA_CA_FILE": "/certs/ca.pem",
        "AIVEN_KAFKA_USERNAME": "avnadmin", "AIVEN_KAFKA_PASSWORD": "hunter2",
        "AIVEN_KAFKA_SASL_MECHANISM": "scram-sha-256"})
    def test_sasl_defaults_to_sasl_ssl(self):
        settings = load_kafka_settings()
        config = settings.librdkafka()
        self.assertEqual(config["security.protocol"], "SASL_SSL")
        self.assertEqual(config["sasl.mechanism"], "SCRAM-SHA-256")
        self.assertEqual(config["sasl.password"], "hunter2")
        self.assertNotIn("hunter2", str(settings.describe()))

    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "k.aivencloud.com:12346",
        "AIVEN_KAFKA_SECURITY_PROTOCOL": "SSL",
        "AIVEN_KAFKA_CA_FILE": "/certs/ca.pem",
        "AIVEN_KAFKA_USERNAME": "avnadmin", "AIVEN_KAFKA_PASSWORD": "x"})
    def test_sasl_with_ssl_protocol_is_rejected(self):
        problems = load_kafka_settings().validate()
        self.assertTrue(any("SASL_SSL" in p for p in problems))

    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "localhost:9092",
        "AIVEN_KAFKA_SECURITY_PROTOCOL": "PLAINTEXT"})
    def test_plaintext_requires_explicit_opt_in(self):
        self.assertFalse(load_kafka_settings().describe()["valid"])
        with patch.dict("os.environ", {"AIVEN_KAFKA_ALLOW_PLAINTEXT": "true"}):
            settings = load_kafka_settings()
            self.assertTrue(settings.describe()["valid"])
            self.assertEqual(settings.librdkafka()["security.protocol"], "PLAINTEXT")

    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "k.aivencloud.com:12345",
        "AIVEN_KAFKA_CERT_FILE": "/certs/service.cert",
        "AIVEN_KAFKA_KEY_FILE": "/certs/service.key"})
    def test_missing_ca_is_reported(self):
        problems = load_kafka_settings().validate()
        self.assertTrue(any("CA certificate" in p for p in problems))

    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "k.aivencloud.com:12345",
        "AIVEN_KAFKA_CA_FILE": "/certs/ca.pem",
        "AIVEN_KAFKA_CERT_FILE": "/certs/service.cert"})
    def test_half_configured_mtls_is_reported(self):
        problems = load_kafka_settings().validate()
        self.assertTrue(any("key files must both" in p for p in problems))


class AivenRuntimeInjectedNamesTests(unittest.TestCase):
    PEMS = {"KAFKA_CA_CERT": "-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----",
            "KAFKA_ACCESS_CERT": "-----BEGIN CERTIFICATE-----\nC\n-----END CERTIFICATE-----",
            "KAFKA_ACCESS_KEY": "-----BEGIN PRIVATE KEY-----\nK\n-----END PRIVATE KEY-----"}

    @patch.dict("os.environ", {**CLEAR, "KAFKA_BOOTSTRAP_SERVER": "rt.aivencloud.com:12345",
                               "KAFKA_SECURITY_PROTOCOL": "SSL"})
    def test_singular_bootstrap_server_is_accepted(self):
        with patch.dict("os.environ", self.PEMS):
            settings = load_kafka_settings()
        self.assertEqual(settings.source, "KAFKA_BOOTSTRAP_SERVER")
        self.assertTrue(settings.describe()["valid"])
        self.assertEqual(settings.librdkafka()["bootstrap.servers"], "rt.aivencloud.com:12345")

    @patch.dict("os.environ", {**CLEAR, "KAFKA_BOOTSTRAP_SERVER": "injected.aivencloud.com:1",
                               "KAFKA_BOOTSTRAP_SERVERS": "plural.aivencloud.com:2",
                               "AIVEN_KAFKA_BROKERS": "explicit.aivencloud.com:3"})
    def test_explicit_project_variable_wins_over_injected_names(self):
        self.assertEqual(load_kafka_settings().brokers, "explicit.aivencloud.com:3")
        with patch.dict("os.environ", {"AIVEN_KAFKA_BROKERS": ""}):
            self.assertEqual(load_kafka_settings().brokers, "plural.aivencloud.com:2")


class InlinePemPrecedenceTests(unittest.TestCase):
    """Exact Runtime configuration: injected PEMs plus stale /certs/* file paths."""
    RUNTIME = {**CLEAR,
        "KAFKA_BOOTSTRAP_SERVER": "rt.aivencloud.com:12345",
        "KAFKA_SECURITY_PROTOCOL": "SSL",
        "KAFKA_CA_CERT": "-----BEGIN CERTIFICATE-----\nCA\n-----END CERTIFICATE-----",
        "KAFKA_ACCESS_CERT": "-----BEGIN CERTIFICATE-----\nC\n-----END CERTIFICATE-----",
        "KAFKA_ACCESS_KEY": "-----BEGIN PRIVATE KEY-----\nK\n-----END PRIVATE KEY-----",
        "AIVEN_KAFKA_CA_FILE": "/certs/ca.pem",
        "AIVEN_KAFKA_CERT_FILE": "/certs/service.cert",
        "AIVEN_KAFKA_KEY_FILE": "/certs/service.key"}

    @patch.dict("os.environ", RUNTIME)
    def test_injected_pems_beat_missing_cert_files(self):
        settings = load_kafka_settings()
        self.assertEqual((settings.ca_file, settings.cert_file, settings.key_file), ("", "", ""))
        description = settings.describe()
        self.assertTrue(description["valid"], description["problems"])
        self.assertEqual(description["credential_format"], "inline_pem")
        self.assertEqual(description["auth_method"], "MTLS")
        config = settings.librdkafka()
        self.assertIn("ssl.ca.pem", config)
        self.assertIn("ssl.certificate.pem", config)
        self.assertIn("ssl.key.pem", config)
        for key in ("ssl.ca.location", "ssl.certificate.location", "ssl.key.location"):
            self.assertNotIn(key, config)
        self.assertEqual(config["bootstrap.servers"], "rt.aivencloud.com:12345")

    @patch.dict("os.environ", {**RUNTIME, "KAFKA_ACCESS_KEY": ""})
    @patch("dependency.events.kafka_settings.os.path.isfile", new=lambda path: True)
    def test_incomplete_inline_pair_falls_back_to_files_and_is_flagged(self):
        settings = load_kafka_settings()
        self.assertEqual(settings.cert_file, "/certs/service.cert")
        self.assertFalse(settings.describe()["valid"])

    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "k.aivencloud.com:12345",
        "AIVEN_KAFKA_CA_FILE": "/certs/ca.pem",
        "AIVEN_KAFKA_CERT_FILE": "/certs/service.cert",
        "AIVEN_KAFKA_KEY_FILE": "/certs/service.key",
        "KAFKA_CA_CERT": "not-a-pem"})
    @patch("dependency.events.kafka_settings.os.path.isfile", new=lambda path: True)
    def test_file_based_docker_setup_still_works(self):
        settings = load_kafka_settings()
        self.assertEqual(settings.ca_file, "/certs/ca.pem", "non-PEM text cannot displace a path")
        config = settings.librdkafka()
        self.assertEqual(config["ssl.ca.location"], "/certs/ca.pem")
        self.assertEqual(config["ssl.certificate.location"], "/certs/service.cert")
        self.assertNotIn("ssl.ca.pem", config)


class CredentialFileTests(unittest.TestCase):
    @patch.dict("os.environ", {**CLEAR,
        "AIVEN_KAFKA_BROKERS": "k.aivencloud.com:12345",
        "AIVEN_KAFKA_CA_FILE": "certs/does-not-exist.pem",
        "AIVEN_KAFKA_USERNAME": "u", "AIVEN_KAFKA_PASSWORD": "p",
        "AIVEN_KAFKA_SECURITY_PROTOCOL": "SASL_SSL"})
    def test_missing_credential_file_is_reported_before_connecting(self):
        description = load_kafka_settings().describe()
        self.assertFalse(description["valid"])
        self.assertTrue(any("CA file does not exist" in p for p in description["problems"]))
        self.assertNotIn("does-not-exist", str(description), "paths are not echoed")


if __name__ == "__main__":
    unittest.main()
