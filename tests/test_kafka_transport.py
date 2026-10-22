"""Outbox publisher and Kafka consumer loop behaviour with a fake broker (no network, no DB)."""
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

from dependency.events import bus, consumer as consumer_mod, publisher
from dependency.events.bus import TOPIC_EXTERNAL_EVENTS, build_event_envelope
from dependency.events.consumer import Heartbeat, run_kafka_consumer

FAKE_CONFIG = {"bootstrap.servers": "broker.test:9092", "security.protocol": "SSL"}
ROWS = [
    {"outbox_id": "OUT-1", "topic": TOPIC_EXTERNAL_EVENTS, "event_key": "K1",
     "payload": {"v": 1}, "created_at": "2026-10-22T00:00:00+00:00", "attempts": 0},
    {"outbox_id": "OUT-2", "topic": "plan.generated", "event_key": "K2",
     "payload": {"v": 2}, "created_at": "2026-10-22T00:00:01+00:00", "attempts": 1},
]


class FakeProducer:
    """Delivers on flush; messages whose key is in ``fail_keys`` report an error."""
    fail_keys: set = set()
    raise_keys: set = set()
    instances: list = []

    def __init__(self, config):
        self.config = config
        self.produced = []
        self.pending = []
        FakeProducer.instances.append(self)

    def produce(self, topic, key, value, callback):
        if key.decode() in self.raise_keys:
            raise BufferError("Local: Queue full")
        self.produced.append((topic, key, value))
        self.pending.append((key, callback))

    def flush(self, timeout):
        for key, callback in self.pending:
            err = "KafkaError{code=_MSG_TIMED_OUT}" if key.decode() in self.fail_keys else None
            callback(err, MagicMock())
        self.pending.clear()
        return 0


class FakeMessage:
    def __init__(self, value=None, error=None):
        self._value, self._error = value, error

    def value(self):
        return self._value

    def error(self):
        return self._error


class FakeConsumer:
    def __init__(self, config, messages=()):
        self.config = config
        self.messages = list(messages)
        self.subscribed = None
        self.commits = []
        self.closed = False

    def subscribe(self, topics):
        self.subscribed = topics

    def poll(self, timeout):
        return self.messages.pop(0) if self.messages else None

    def commit(self, message=None, asynchronous=True):
        self.commits.append(message)

    def close(self):
        self.closed = True


def fake_connect_factory(executed):
    @contextmanager
    def fake_connect():
        conn = MagicMock()
        conn.execute.side_effect = lambda sql, params=None: executed.append((sql, params))
        yield conn
    return fake_connect


class FlushToKafkaTests(unittest.TestCase):
    def setUp(self):
        FakeProducer.fail_keys, FakeProducer.raise_keys, FakeProducer.instances = set(), set(), []

    @patch.dict("os.environ", {"AIVEN_KAFKA_ROUTING_MODE": "single",
                               "AIVEN_KAFKA_PHYSICAL_TOPIC": "dependency.events"})
    @patch("dependency.events.bus._kafka_config", return_value=dict(FAKE_CONFIG))
    @patch("dependency.events.bus.pending", return_value=ROWS)
    def test_all_rows_published_to_single_topic_and_marked(self, _pending, _config):
        executed = []
        with patch("dependency.events.bus.connect", fake_connect_factory(executed)), \
             patch("confluent_kafka.Producer", FakeProducer):
            result = bus.flush_to_kafka(limit=10)
        self.assertEqual(result, {"attempted": 2, "published": 2, "failed": 0})
        producer = FakeProducer.instances[0]
        self.assertTrue(producer.config["enable.idempotence"])
        self.assertEqual(producer.config["acks"], "all")
        self.assertEqual({t for t, _, _ in producer.produced}, {"dependency.events"})
        envelope = json.loads(producer.produced[1][2])
        self.assertEqual(envelope["topic"], "plan.generated")
        self.assertEqual(envelope["outbox_id"], "OUT-2")
        marks = [p for sql, p in executed if "published_at=now()" in sql]
        self.assertEqual([p[0] for p in marks], ["OUT-1", "OUT-2"])

    @patch("dependency.events.bus._kafka_config", return_value=dict(FAKE_CONFIG))
    @patch("dependency.events.bus.pending", return_value=ROWS)
    def test_failed_and_raised_rows_stay_in_outbox_with_error(self, _pending, _config):
        FakeProducer.fail_keys = {"K1"}
        FakeProducer.raise_keys = {"K2"}
        executed = []
        with patch("dependency.events.bus.connect", fake_connect_factory(executed)), \
             patch("confluent_kafka.Producer", FakeProducer):
            result = bus.flush_to_kafka(limit=10)
        self.assertEqual(result, {"attempted": 2, "published": 0, "failed": 2})
        failures = {p[1]: p[0] for sql, p in executed if "last_error=%s" in sql}
        self.assertIn("_MSG_TIMED_OUT", failures["OUT-1"])
        self.assertIn("BufferError", failures["OUT-2"])
        self.assertFalse(any("published_at=now()" in sql for sql, _ in executed))

    @patch("dependency.events.bus.pending", return_value=[])
    def test_empty_outbox_never_builds_a_producer(self, _pending):
        with patch("dependency.events.bus._kafka_config") as config:
            self.assertEqual(bus.flush_to_kafka(), {"attempted": 0, "published": 0, "failed": 0})
        config.assert_not_called()


@patch("dependency.events.consumer.outbox_exists", new=lambda outbox_id: True)
class ConsumerLoopTests(unittest.TestCase):
    def _envelope(self, outbox_id, topic=TOPIC_EXTERNAL_EVENTS):
        return json.dumps(build_event_envelope({
            "outbox_id": outbox_id, "topic": topic, "event_key": "K", "payload": {"v": 1},
        })).encode()

    @patch.dict("os.environ", {"AIVEN_KAFKA_ROUTING_MODE": "single",
                               "AIVEN_KAFKA_PHYSICAL_TOPIC": "dependency.events"})
    @patch("dependency.events.consumer._kafka_config", return_value=dict(FAKE_CONFIG))
    def test_commits_only_after_success_and_counts_duplicates(self, _config):
        messages = [None, FakeMessage(self._envelope("OUT-1")),
                    FakeMessage(self._envelope("OUT-1")), FakeMessage(self._envelope("OUT-2"))]
        holder = {}
        statuses = iter(["SUCCESS", "DUPLICATE_SKIPPED", "SUCCESS"])

        def factory(config):
            holder["consumer"] = FakeConsumer(config, messages)
            return holder["consumer"]

        with patch("dependency.events.consumer.process_event_envelope",
                   side_effect=lambda **kw: {"status": next(statuses)}) as handler:
            stats = run_kafka_consumer(max_messages=3, consumer_factory=factory, poll_timeout=0)
        consumer = holder["consumer"]
        self.assertEqual(consumer.subscribed, ["dependency.events"])
        self.assertEqual(consumer.config["group.id"], "dependency-incident-orchestrator")
        self.assertFalse(consumer.config["enable.auto.commit"])
        self.assertEqual(stats["handled"], 2)
        self.assertEqual(stats["duplicates"], 1)
        self.assertEqual(stats["stopped_by"], "max_messages")
        self.assertEqual(len(consumer.commits), 3)
        self.assertTrue(consumer.closed)
        self.assertEqual(handler.call_args.kwargs["consumer_name"], "incident-orchestrator")

    @patch("dependency.events.consumer._kafka_config", return_value=dict(FAKE_CONFIG))
    def test_handler_error_leaves_offset_uncommitted_and_stops(self, _config):
        holder = {}

        def factory(config):
            holder["c"] = FakeConsumer(config, [FakeMessage(self._envelope("OUT-9"))])
            return holder["c"]

        with patch("dependency.events.consumer.process_event_envelope",
                   return_value={"status": "ERROR", "error": "boom"}):
            with self.assertRaises(RuntimeError):
                run_kafka_consumer(consumer_factory=factory, poll_timeout=0)
        self.assertEqual(holder["c"].commits, [])
        self.assertTrue(holder["c"].closed)

    @patch("dependency.events.consumer._kafka_config", return_value=dict(FAKE_CONFIG))
    def test_unknown_logical_topic_is_skipped_not_processed(self, _config):
        holder = {}

        def factory(config):
            holder["c"] = FakeConsumer(config, [
                FakeMessage(self._envelope("PROBE-1", topic="hermes.transport.probe"))])
            return holder["c"]

        stop = iter([False, False, True])
        with patch("dependency.events.consumer.process_event_envelope") as handler:
            stats = run_kafka_consumer(consumer_factory=factory, poll_timeout=0,
                                       should_stop=lambda: next(stop))
        handler.assert_not_called()
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(len(holder["c"].commits), 1)
        self.assertEqual(stats["stopped_by"], "stop_requested")

    @patch("dependency.events.consumer._kafka_config", return_value=dict(FAKE_CONFIG))
    def test_heartbeat_written_each_poll(self, _config):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run" / "heartbeat"
            stop = iter([False, True])
            run_kafka_consumer(consumer_factory=lambda c: FakeConsumer(c), poll_timeout=0,
                               should_stop=lambda: next(stop), heartbeat_path=path)
            age = Heartbeat.age_seconds(path)
            self.assertIsNotNone(age)
            self.assertLess(age, 5)
        self.assertIsNone(Heartbeat.age_seconds(Path(tmp) / "missing"))


@patch("dependency.events.consumer._kafka_config", return_value=dict(FAKE_CONFIG))
@patch("dependency.events.consumer.outbox_exists", new=lambda outbox_id: outbox_id == "OUT-LIVE")
class OrphanedEventTests(unittest.TestCase):
    """Topic retention outlives a reloaded database; stale events must not crash-loop."""

    def _messages(self):
        return [FakeMessage(json.dumps(build_event_envelope({
            "outbox_id": oid, "topic": TOPIC_EXTERNAL_EVENTS, "event_key": "K", "payload": {},
        })).encode()) for oid in ("OUT-GONE", "OUT-LIVE")]

    def test_default_policy_skips_commits_and_counts_orphans(self, _config):
        holder = {}

        def factory(config):
            holder["c"] = FakeConsumer(config, self._messages())
            return holder["c"]

        with patch("dependency.events.consumer.process_event_envelope",
                   return_value={"status": "SUCCESS"}) as handler, \
             patch.dict("os.environ", {"AIVEN_KAFKA_ORPHAN_POLICY": ""}):
            stats = run_kafka_consumer(max_messages=2, consumer_factory=factory, poll_timeout=0)
        self.assertEqual(stats["orphaned"], 1)
        self.assertEqual(stats["handled"], 1)
        self.assertEqual(len(holder["c"].commits), 2)
        self.assertEqual(handler.call_args.kwargs["outbox_id"], "OUT-LIVE")

    def test_fail_policy_stops_without_commit(self, _config):
        holder = {}

        def factory(config):
            holder["c"] = FakeConsumer(config, self._messages())
            return holder["c"]

        with patch("dependency.events.consumer.process_event_envelope") as handler:
            with self.assertRaises(RuntimeError):
                run_kafka_consumer(consumer_factory=factory, poll_timeout=0, orphan_policy="fail")
        handler.assert_not_called()
        self.assertEqual(holder["c"].commits, [])

    def test_unknown_policy_rejected(self, _config):
        with self.assertRaises(ValueError):
            run_kafka_consumer(consumer_factory=FakeConsumer, orphan_policy="ignore")


class PublisherLoopTests(unittest.TestCase):
    def test_loop_accumulates_and_survives_cycle_errors(self):
        outcomes = iter([
            {"attempted": 2, "published": 2, "failed": 0},
            RuntimeError("broker down"),
            {"attempted": 1, "published": 0, "failed": 1},
        ])

        def flush(limit):
            item = next(outcomes)
            if isinstance(item, Exception):
                raise item
            return item

        sleeps = []
        totals = publisher.run_kafka_publisher(max_cycles=3, flush=flush, sleep=sleeps.append,
                                               interval_seconds=0.5)
        self.assertEqual(totals["cycles"], 3)
        self.assertEqual(totals["published"], 2)
        self.assertEqual(totals["failed"], 1)
        self.assertEqual(totals["cycle_errors"], 1)
        self.assertEqual(totals["last_error_type"], "RuntimeError")
        self.assertEqual(totals["stopped_by"], "max_cycles")
        self.assertEqual(sleeps, [0.5, 0.5, 0.5])

    def test_full_batch_skips_sleep_to_drain_backlog(self):
        sleeps = []
        publisher.run_kafka_publisher(
            max_cycles=1, batch_limit=5, sleep=sleeps.append,
            flush=lambda limit: {"attempted": 5, "published": 5, "failed": 0})
        self.assertEqual(sleeps, [])

    def test_stop_predicate_halts_before_flushing(self):
        totals = publisher.run_kafka_publisher(
            should_stop=lambda: True, flush=lambda limit: self.fail("must not flush"))
        self.assertEqual(totals["stopped_by"], "stop_requested")
        self.assertEqual(totals["cycles"], 0)


if __name__ == "__main__":
    unittest.main()
