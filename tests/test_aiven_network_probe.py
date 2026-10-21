"""Kafka network preflight is read-only and can detect a missing physical topic."""
import unittest
from unittest.mock import patch,MagicMock

from scripts.aiven_preflight import probe_kafka_network


class KafkaProbeTests(unittest.TestCase):
    @patch("scripts.aiven_preflight.check_kafka",
           return_value={"status":"NOT_CONFIGURED"})
    def test_unconfigured_is_not_connected(self, config):
        self.assertEqual(probe_kafka_network()["status"],"NOT_READY")

    @patch("scripts.aiven_preflight.check_kafka",
           return_value={"status":"CONFIGURED_NOT_CONNECTED"})
    @patch("dependency.events.consumer.kafka_subscription_topics",
           return_value=("dependency.events",))
    @patch("dependency.events.bus._kafka_config",
           return_value={"bootstrap.servers":"broker.test:9092"})
    @patch("confluent_kafka.admin.AdminClient")
    def test_existing_topic_passes_readonly_probe(self, admin_cls, config, topics, status):
        admin=MagicMock()
        admin.list_topics.return_value=MagicMock(
            topics={"dependency.events":MagicMock(error=None)},
            brokers={1:MagicMock()},
        )
        admin_cls.return_value=admin
        result=probe_kafka_network()
        self.assertEqual(result["status"],"READY_TO_STREAM")
        self.assertFalse(result["changed_remote_state"])
        admin.list_topics.assert_called_once()

    @patch("scripts.aiven_preflight.check_kafka",
           return_value={"status":"CONFIGURED_NOT_CONNECTED"})
    @patch("dependency.events.consumer.kafka_subscription_topics",
           return_value=("dependency.events",))
    @patch("dependency.events.bus._kafka_config",
           return_value={"bootstrap.servers":"broker.test:9092"})
    @patch("confluent_kafka.admin.AdminClient")
    def test_missing_topic_never_claims_ready(self, admin_cls, config, topics, status):
        admin=MagicMock()
        admin.list_topics.return_value=MagicMock(topics={},brokers={1:MagicMock()})
        admin_cls.return_value=admin
        result=probe_kafka_network()
        self.assertEqual(result["status"],"MISSING_TOPICS")
        self.assertEqual(result["missing_topics"],["dependency.events"])


if __name__=="__main__":
    unittest.main()
