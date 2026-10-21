"""Kafka and local event workers preserve transport-independent identity."""
import unittest
from dependency.automation.orchestrator import DEFAULT_CONSUMER
from dependency.events.consumer import DEFAULT_TOPICS, run_kafka_consumer
from dependency.events.bus import TOPIC_ACTION_EXECUTED

class TransportConsistencyTests(unittest.TestCase):
    def test_same_consumer_name_for_local_and_kafka(self):
        self.assertEqual(run_kafka_consumer.__kwdefaults__["consumer_name"], DEFAULT_CONSUMER)

    def test_action_executions_included_once(self):
        self.assertIn(TOPIC_ACTION_EXECUTED, DEFAULT_TOPICS)
        self.assertEqual(len(DEFAULT_TOPICS), len(set(DEFAULT_TOPICS)))

if __name__ == "__main__":
    unittest.main()
