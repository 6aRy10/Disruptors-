from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any, Callable

from dependency.automation.orchestrator import DEFAULT_CONSUMER, process_event_envelope
from dependency.events.kafka_settings import consumer_group
from dependency.events.bus import (
    TOPIC_APPROVAL_REQUESTED,
    TOPIC_ACTION_EXECUTED,
    TOPIC_BUSINESS_STATE,
    TOPIC_DECISION_CONFIRMED,
    TOPIC_EXTERNAL_EVENTS,
    TOPIC_INCIDENT_DETECTED,
    TOPIC_PLAN_GENERATED,
    TOPIC_PLAN_INVALIDATED,
    TOPIC_SUPPLIER_CAPACITY,
    TOPIC_SUPPLIER_CONFIRMATION_REPLY,
    TOPIC_SUPPLIER_CONFIRMATION_REQUESTED,
    _kafka_config,
    kafka_routing_mode,
    outbox_exists,
    physical_topic_for,
)


DEFAULT_TOPICS = (
    TOPIC_EXTERNAL_EVENTS,
    TOPIC_BUSINESS_STATE,
    TOPIC_SUPPLIER_CAPACITY,
    TOPIC_INCIDENT_DETECTED,
    TOPIC_PLAN_GENERATED,
    TOPIC_PLAN_INVALIDATED,
    TOPIC_APPROVAL_REQUESTED,
    TOPIC_SUPPLIER_CONFIRMATION_REQUESTED,
    TOPIC_SUPPLIER_CONFIRMATION_REPLY,
    TOPIC_DECISION_CONFIRMED,
    TOPIC_ACTION_EXECUTED,
)


def kafka_subscription_topics() -> tuple[str, ...]:
    if kafka_routing_mode() == "logical":
        return DEFAULT_TOPICS
    return (physical_topic_for(TOPIC_EXTERNAL_EVENTS),)


def kafka_consumer_config(
    *,
    group_id: str | None = None,
) -> dict:
    config = _kafka_config()
    config.update(
        {
            "group.id": group_id or consumer_group(),
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": os.getenv(
                "AIVEN_KAFKA_AUTO_OFFSET_RESET",
                "earliest",
            ),
            "session.timeout.ms": 30000,
            "max.poll.interval.ms": int(
                os.getenv("AIVEN_KAFKA_MAX_POLL_INTERVAL_MS", "600000")
            ),
        }
    )
    return config


def decode_envelope(raw_value: bytes | str) -> dict:
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")
    envelope = json.loads(raw_value)

    required = {"outbox_id", "topic", "event_key", "payload"}
    missing = sorted(required.difference(envelope))
    if missing:
        raise ValueError(
            f"Kafka event envelope missing fields: {', '.join(missing)}"
        )
    if not isinstance(envelope["payload"], dict):
        raise ValueError("Kafka event envelope payload must be an object.")
    return envelope


def run_kafka_consumer(
    *,
    topics: tuple[str, ...] | None = None,
    consumer_name: str = DEFAULT_CONSUMER,
    run_agents: bool = False,
    radius_km: float = 150.0,
    poll_timeout: float = 1.0,
    max_messages: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    heartbeat_path: str | os.PathLike[str] | None = None,
    consumer_factory: Callable[[dict], Any] | None = None,
    orphan_policy: str | None = None,
) -> dict:
    """Consume Aiven Kafka events with DB-backed idempotency.

    Kafka offsets are committed only after the event is successfully handled or
    confirmed as already handled. Handler errors remain uncommitted for retry
    and stop the loop, so a crashed container is redelivered the same event.

    ``max_messages`` and ``should_stop`` bound the loop for tests and graceful
    SIGTERM shutdown. ``heartbeat_path`` receives a timestamp on every poll so
    a container HEALTHCHECK can detect a hung consumer.

    ``orphan_policy`` (``skip`` default, or ``fail``; env
    ``AIVEN_KAFKA_ORPHAN_POLICY``) decides what happens to messages whose
    outbox row does not exist in the connected database.
    """
    orphan_policy = (orphan_policy or os.getenv("AIVEN_KAFKA_ORPHAN_POLICY") or "skip").lower()
    if orphan_policy not in {"skip", "fail"}:
        raise ValueError("AIVEN_KAFKA_ORPHAN_POLICY must be skip or fail.")
    if consumer_factory is None:
        try:
            from confluent_kafka import Consumer
        except ImportError as exc:
            raise RuntimeError("confluent-kafka is not installed.") from exc
        consumer_factory = Consumer

    consumer = consumer_factory(kafka_consumer_config())
    consumer.subscribe(list(topics if topics is not None else kafka_subscription_topics()))
    heartbeat = Heartbeat(heartbeat_path)
    stats = {"handled": 0, "duplicates": 0, "skipped": 0, "orphaned": 0, "errors": 0,
             "stopped_by": None}

    try:
        while True:
            if should_stop is not None and should_stop():
                stats["stopped_by"] = "stop_requested"
                break
            consumed = sum(stats[k] for k in ("handled", "duplicates", "skipped", "orphaned"))
            if max_messages is not None and consumed >= max_messages:
                stats["stopped_by"] = "max_messages"
                break

            heartbeat.beat()
            message = consumer.poll(poll_timeout)
            if message is None:
                continue

            if message.error():
                if _is_partition_eof(message.error()):
                    continue
                raise RuntimeError(f"Kafka consumer error: {message.error()}")

            try:
                envelope = decode_envelope(message.value())
                if envelope["topic"] not in DEFAULT_TOPICS:
                    # Probes or foreign producers: not ours to handle, never poison the loop.
                    stats["skipped"] += 1
                    consumer.commit(message=message, asynchronous=False)
                    continue
                if not outbox_exists(envelope["outbox_id"]):
                    # Topic retention outlives a reloaded database: the event's
                    # outbox row is gone, so it cannot be recorded idempotently.
                    stats["orphaned"] += 1
                    if orphan_policy == "fail":
                        raise RuntimeError(
                            f"Outbox row missing for {envelope['outbox_id']}; "
                            "consumer and publisher use different databases?"
                        )
                    consumer.commit(message=message, asynchronous=False)
                    continue
                result = process_event_envelope(
                    consumer_name=consumer_name,
                    outbox_id=envelope["outbox_id"],
                    topic=envelope["topic"],
                    payload=envelope["payload"],
                    run_agents=run_agents,
                    radius_km=radius_km,
                )
            except Exception:
                # Leave the offset uncommitted so Kafka can redeliver.
                stats["errors"] += 1
                raise

            if result["status"] == "ERROR":
                stats["errors"] += 1
                raise RuntimeError(result["error"])

            stats["duplicates" if result["status"] == "DUPLICATE_SKIPPED" else "handled"] += 1
            consumer.commit(message=message, asynchronous=False)
    finally:
        consumer.close()
    return stats


def _is_partition_eof(error) -> bool:
    try:
        from confluent_kafka import KafkaError
    except ImportError:
        return False
    return error.code() == KafkaError._PARTITION_EOF


class Heartbeat:
    """Touch a file with the current epoch so a HEALTHCHECK can read its age."""

    def __init__(self, path: str | os.PathLike[str] | None):
        self.path = Path(path) if path else None

    def beat(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(str(time.time()), encoding="utf-8")
        tmp.replace(self.path)

    @staticmethod
    def age_seconds(path: str | os.PathLike[str]) -> float | None:
        try:
            return max(0.0, time.time() - float(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None


def install_signal_stop() -> Callable[[], bool]:
    """Return a ``should_stop`` predicate flipped by SIGTERM/SIGINT."""
    flag = {"stop": False}

    def _handle(signum, frame):
        flag["stop"] = True

    for name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, _handle)
    return lambda: flag["stop"]
