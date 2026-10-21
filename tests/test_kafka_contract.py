import json
import unittest

from dependency.automation.orchestrator import process_event_envelope
from dependency.events.bus import build_event_envelope, enqueue, pending
from dependency.events.consumer import decode_envelope
from dependency.services.demo_reset import reset_demo_state


class KafkaContractTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()

    def tearDown(self):
        reset_demo_state()

    def test_outbox_transport_envelope_preserves_idempotency_key(self):
        outbox_id = enqueue(
            topic="test.event",
            event_key="TEST-KEY",
            payload={"value": 42},
        )
        row = next(
            item for item in pending(limit=100)
            if item["outbox_id"] == outbox_id
        )
        envelope = build_event_envelope(row)
        decoded = decode_envelope(json.dumps(envelope).encode("utf-8"))

        self.assertEqual(decoded["outbox_id"], outbox_id)
        self.assertEqual(decoded["topic"], "test.event")
        self.assertEqual(decoded["event_key"], "TEST-KEY")
        self.assertEqual(decoded["payload"]["value"], 42)

    def test_same_outbox_event_is_not_applied_twice(self):
        outbox_id = enqueue(
            topic="test.event",
            event_key="IDEMPOTENT",
            payload={"value": 1},
        )

        first = process_event_envelope(
            consumer_name="ci-kafka-consumer",
            outbox_id=outbox_id,
            topic="test.event",
            payload={"value": 1},
        )
        second = process_event_envelope(
            consumer_name="ci-kafka-consumer",
            outbox_id=outbox_id,
            topic="test.event",
            payload={"value": 1},
        )

        self.assertEqual(first["status"], "SUCCESS")
        self.assertEqual(second["status"], "DUPLICATE_SKIPPED")

    def test_invalid_transport_envelope_is_rejected(self):
        with self.assertRaises(ValueError):
            decode_envelope(
                json.dumps(
                    {
                        "topic": "external.events",
                        "payload": {},
                    }
                ).encode("utf-8")
            )


if __name__ == "__main__":
    unittest.main()
