"""Kafka free tier uses one physical topic without collapsing logical events."""
import json
import unittest
from unittest.mock import patch

from dependency.events.bus import (
    physical_topic_for,build_event_envelope,
    TOPIC_EXTERNAL_EVENTS,TOPIC_ACTION_EXECUTED,
)
from dependency.events.consumer import kafka_subscription_topics,decode_envelope,DEFAULT_TOPICS


class KafkaRoutingTests(unittest.TestCase):
    @patch.dict("os.environ",{"AIVEN_KAFKA_ROUTING_MODE":"single",
                             "AIVEN_KAFKA_PHYSICAL_TOPIC":"dependency.events"})
    def test_physical_topic_and_envelope(self):
        self.assertEqual(kafka_subscription_topics(),("dependency.events",))
        for logical in (TOPIC_EXTERNAL_EVENTS,TOPIC_ACTION_EXECUTED):
            self.assertEqual(physical_topic_for(logical),"dependency.events")
            decoded=decode_envelope(json.dumps(build_event_envelope({
                "outbox_id":"OUT-1","topic":logical,"event_key":"KEY","payload":{"v":1},
            })).encode())
            self.assertEqual(decoded["topic"],logical)
            self.assertEqual(decoded["outbox_id"],"OUT-1")

    @patch.dict("os.environ",{"AIVEN_KAFKA_ROUTING_MODE":"logical"})
    def test_multitopic_mode_requires_explicit_opt_in(self):
        self.assertEqual(kafka_subscription_topics(),DEFAULT_TOPICS)
        self.assertEqual(physical_topic_for(TOPIC_ACTION_EXECUTED),TOPIC_ACTION_EXECUTED)
        self.assertGreater(len(DEFAULT_TOPICS),5)

    @patch.dict("os.environ",{"AIVEN_KAFKA_ROUTING_MODE":"invalid"})
    def test_unknown_routing_fails_closed(self):
        with self.assertRaises(ValueError):
            kafka_subscription_topics()


if __name__=="__main__":
    unittest.main()
