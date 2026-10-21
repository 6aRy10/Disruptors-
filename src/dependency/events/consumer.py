from __future__ import annotations

import json
import os

from dependency.automation.orchestrator import process_event_envelope
from dependency.events.bus import (
    TOPIC_APPROVAL_REQUESTED,
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
)


def kafka_consumer_config(
    *,
    group_id: str | None = None,
) -> dict:
    config = _kafka_config()
    config.update(
        {
            "group.id": group_id
            or os.getenv(
                "AIVEN_KAFKA_CONSUMER_GROUP",
                "dependency-incident-orchestrator",
            ),
            "enable.auto.commit": False,
            "auto.offset.reset": os.getenv(
                "AIVEN_KAFKA_AUTO_OFFSET_RESET",
                "earliest",
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
    topics: tuple[str, ...] = DEFAULT_TOPICS,
    consumer_name: str = "aiven-incident-orchestrator",
    run_agents: bool = False,
    radius_km: float = 150.0,
    poll_timeout: float = 1.0,
) -> None:
    """Consume Aiven Kafka events with DB-backed idempotency.

    Kafka offsets are committed only after the event is successfully handled or
    confirmed as already handled. Handler errors remain uncommitted for retry.
    """
    try:
        from confluent_kafka import Consumer, KafkaError
    except ImportError as exc:
        raise RuntimeError("confluent-kafka is not installed.") from exc

    consumer = Consumer(kafka_consumer_config())
    consumer.subscribe(list(topics))

    try:
        while True:
            message = consumer.poll(poll_timeout)
            if message is None:
                continue

            if message.error():
                if message.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(f"Kafka consumer error: {message.error()}")

            try:
                envelope = decode_envelope(message.value())
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
                raise

            if result["status"] == "ERROR":
                raise RuntimeError(result["error"])

            consumer.commit(message=message, asynchronous=False)
    finally:
        consumer.close()
