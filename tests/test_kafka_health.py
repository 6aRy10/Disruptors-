"""Health endpoints are secret-free, read-only and degrade with structured statuses."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from dependency.events import health

BACKLOG = {"pending": 3, "pending_with_failed_attempts": 1,
           "oldest_pending_age_seconds": 12.0, "published_last_hour": 40}
LAG = {"consumer_name": "incident-orchestrator", "published_not_consumed": 2,
       "consumption_errors": 0}
MTLS_ENV = {"AIVEN_KAFKA_BROKERS": "k.aivencloud.com:12345",
            "AIVEN_KAFKA_CA_FILE": "/certs/ca.pem", "AIVEN_KAFKA_CERT_FILE": "/certs/c",
            "AIVEN_KAFKA_KEY_FILE": "/certs/k", "AIVEN_KAFKA_USERNAME": "",
            "AIVEN_KAFKA_PASSWORD": "", "AIVEN_KAFKA_SECURITY_PROTOCOL": "SSL",
            "AIVEN_KAFKA_ROUTING_MODE": "single", "KAFKA_BOOTSTRAP_SERVERS": ""}


@patch("dependency.events.kafka_settings.os.path.isfile", new=lambda path: True)
class KafkaHealthTests(unittest.TestCase):
    @patch.dict("os.environ", {"AIVEN_KAFKA_BROKERS": "", "KAFKA_BOOTSTRAP_SERVERS": ""})
    @patch("dependency.events.health.consumer_lag", return_value=LAG)
    @patch("dependency.events.health.outbox_backlog", return_value=BACKLOG)
    def test_unconfigured_kafka_still_reports_outbox(self, _b, _l):
        result = health.kafka_health()
        self.assertEqual(result["status"], "NOT_CONFIGURED")
        self.assertEqual(result["outbox"]["pending"], 3)
        self.assertEqual(result["brokers"]["status"], "NOT_PROBED")
        self.assertTrue(result["read_only"])

    @patch.dict("os.environ", MTLS_ENV)
    @patch("dependency.events.health.consumer_lag", return_value=LAG)
    @patch("dependency.events.health.outbox_backlog", return_value=BACKLOG)
    def test_probe_reachable_marks_streaming_ready_without_secrets(self, _b, _l):
        admin = MagicMock()
        admin.list_topics.return_value = MagicMock(
            topics={"dependency.events": MagicMock(error=None)}, brokers={1: MagicMock(), 2: MagicMock()})
        with patch("confluent_kafka.admin.AdminClient", return_value=admin):
            result = health.kafka_health(probe=True)
        self.assertEqual(result["status"], "STREAMING_READY")
        self.assertEqual(result["brokers"]["broker_count"], 2)
        self.assertEqual(result["routing"]["subscription_topics"], ["dependency.events"])
        self.assertNotIn("/certs", str(result))
        self.assertNotIn("aivencloud", str(result))

    @patch.dict("os.environ", MTLS_ENV)
    @patch("dependency.events.health.consumer_lag", return_value=LAG)
    @patch("dependency.events.health.outbox_backlog", return_value=BACKLOG)
    def test_unreachable_broker_hides_error_text(self, _b, _l):
        with patch("confluent_kafka.admin.AdminClient",
                   side_effect=RuntimeError("ssl handshake to k.aivencloud.com failed")):
            result = health.kafka_health(probe=True)
        self.assertEqual(result["status"], "BROKER_UNREACHABLE")
        self.assertEqual(result["brokers"]["error_type"], "RuntimeError")
        self.assertNotIn("aivencloud", str(result))

    @patch.dict("os.environ", {"AIVEN_KAFKA_BROKERS": ""})
    @patch("dependency.events.health.outbox_backlog",
           side_effect=RuntimeError("password=secret host=db.internal"))
    def test_database_failure_is_structured(self, _b):
        result = health.kafka_health()
        self.assertEqual(result["status"], "DATABASE_ERROR")
        self.assertEqual(result["outbox"]["error_type"], "RuntimeError")
        self.assertNotIn("secret", str(result))

    def test_heartbeat_status_fresh_stale_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hb"
            self.assertEqual(health.heartbeat_status(str(path))["status"], "MISSING")
            path.write_text(str(time.time()))
            self.assertEqual(health.heartbeat_status(str(path))["status"], "FRESH")
            path.write_text(str(time.time() - 10_000))
            self.assertEqual(health.heartbeat_status(str(path))["status"], "STALE")
        self.assertEqual(health.heartbeat_status(None)["status"], "NOT_CONFIGURED")

    @patch("dependency.events.health.kafka_health", return_value={"status": "CONFIGURED"})
    @patch("dependency.events.health.database_readiness", return_value={"status": "READY"})
    def test_readiness_ready(self, _db, _k):
        self.assertEqual(health.readiness()["status"], "READY")

    @patch("dependency.events.health.kafka_health")
    @patch("dependency.events.health.database_readiness",
           return_value={"status": "ERROR", "error_type": "OperationalError"})
    def test_readiness_skips_kafka_when_database_down(self, _db, kafka):
        result = health.readiness()
        self.assertEqual(result["status"], "NOT_READY")
        self.assertEqual(result["kafka"], "SKIPPED_DATABASE_NOT_READY")
        kafka.assert_not_called()


class HealthEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dependency.api.main import app
        cls.client = TestClient(app)

    def test_live_touches_nothing(self):
        with patch("dependency.events.health.connect") as connect:
            response = self.client.get("/health/live")
        connect.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ALIVE")

    def test_ready_returns_503_when_not_ready(self):
        with patch("dependency.api.main.readiness",
                   return_value={"status": "NOT_READY", "database": {"status": "ERROR"},
                                 "kafka": "SKIPPED_DATABASE_NOT_READY", "read_only": True}):
            response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "NOT_READY")

    def test_ready_returns_200_when_ready(self):
        with patch("dependency.api.main.readiness",
                   return_value={"status": "READY", "database": {"status": "READY"},
                                 "kafka": "CONFIGURED", "read_only": True}) as readiness:
            response = self.client.get("/health/ready?probe_kafka=true")
        self.assertEqual(response.status_code, 200)
        readiness.assert_called_once_with(probe_kafka=True)

    def test_kafka_endpoint_passes_probe_flag(self):
        with patch("dependency.api.main.kafka_health",
                   return_value={"status": "NOT_CONFIGURED"}) as kh:
            response = self.client.get("/health/kafka")
        self.assertEqual(response.status_code, 200)
        kh.assert_called_once_with(probe=False)


if __name__ == "__main__":
    unittest.main()
