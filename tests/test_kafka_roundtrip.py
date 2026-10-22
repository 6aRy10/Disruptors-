"""Round-trip verifier publishes one probe, reads it back, and touches no database."""
import json
import unittest
from unittest.mock import MagicMock, patch

from dependency.events import roundtrip
from tests.test_kafka_transport import FAKE_CONFIG, FakeConsumer, FakeMessage


class LoopbackProducer:
    """Deliver each produced message straight into the paired consumer."""

    def __init__(self, consumer, fail=False):
        self.consumer, self.fail = consumer, fail

    def __call__(self, config):
        self.config = config
        return self

    def produce(self, topic, key, value, callback):
        if self.fail:
            callback("KafkaError{code=_TRANSPORT}", None)
            return
        self.consumer.messages.append(FakeMessage(value))
        callback(None, MagicMock(partition=lambda: 1, offset=lambda: 77))

    def flush(self, timeout):
        return 0


@patch.dict("os.environ", {"AIVEN_KAFKA_ROUTING_MODE": "single",
                           "AIVEN_KAFKA_PHYSICAL_TOPIC": "dependency.events"})
@patch("dependency.events.consumer._kafka_config", return_value=dict(FAKE_CONFIG))
@patch("dependency.events.bus._kafka_config", return_value=dict(FAKE_CONFIG))
class RoundtripTests(unittest.TestCase):
    def test_verified_roundtrip_uses_throwaway_group_and_probe_topic(self, _b, _c):
        holder = {}

        def consumer_factory(config):
            holder["c"] = FakeConsumer(config, [None, FakeMessage(b"not json")])
            return holder["c"]

        producer = LoopbackProducer(None)
        original = producer.produce

        def produce(topic, key, value, callback):
            producer.consumer = holder["c"]
            original(topic, key, value, callback)
        producer.produce = produce

        with patch("dependency.events.roundtrip.connect", create=True) as connect:
            report = roundtrip.kafka_roundtrip(timeout_seconds=5, producer_factory=producer,
                                               consumer_factory=consumer_factory)
        connect.assert_not_called()
        self.assertEqual(report["status"], "VERIFIED")
        self.assertTrue(report["published"] and report["consumed"])
        self.assertEqual(report["physical_topic"], "dependency.events")
        self.assertEqual(report["envelope_topic"], roundtrip.PROBE_TOPIC)
        self.assertTrue(report["consumer_group"].startswith("hermes-roundtrip-"))
        self.assertNotEqual(holder["c"].config["group.id"], "dependency-incident-orchestrator")
        self.assertEqual(holder["c"].subscribed, ["dependency.events"])
        self.assertEqual(len(holder["c"].commits), 1)
        self.assertTrue(holder["c"].closed)
        self.assertEqual(report["offset"], 77)

    def test_delivery_failure_reports_without_consuming(self, _b, _c):
        consumer = FakeConsumer(dict(FAKE_CONFIG))
        report = roundtrip.kafka_roundtrip(
            timeout_seconds=1, producer_factory=LoopbackProducer(consumer, fail=True),
            consumer_factory=lambda config: consumer)
        self.assertEqual(report["status"], "FAILED")
        self.assertFalse(report["published"])
        self.assertEqual(report["error_type"], "DeliveryFailed")
        self.assertTrue(consumer.closed)

    def test_consume_timeout_when_probe_never_arrives(self, _b, _c):
        consumer = FakeConsumer(dict(FAKE_CONFIG))
        producer = LoopbackProducer(FakeConsumer(dict(FAKE_CONFIG)))  # delivers elsewhere
        report = roundtrip.kafka_roundtrip(timeout_seconds=0.2, producer_factory=producer,
                                           consumer_factory=lambda config: consumer)
        self.assertTrue(report["published"])
        self.assertFalse(report["consumed"])
        self.assertEqual(report["error_type"], "ConsumeTimeout")

    def test_probe_envelope_is_decodable_and_not_a_business_topic(self, _b, _c):
        from dependency.events.consumer import DEFAULT_TOPICS, decode_envelope
        envelope = decode_envelope(json.dumps(roundtrip.probe_envelope("abc")).encode())
        self.assertEqual(envelope["outbox_id"], "PROBE-abc")
        self.assertNotIn(envelope["topic"], DEFAULT_TOPICS)


if __name__ == "__main__":
    unittest.main()
