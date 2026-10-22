"""End-to-end Kafka transport verification against real brokers.

Publishes ONE synthetic probe envelope to the configured physical topic and
reads it back with a throwaway consumer group. The probe never touches
PostgreSQL: its logical topic is ``hermes.transport.probe`` which no
orchestrator handles, and the production consumer group is not used, so the
real consumer sees the probe as an unsupported topic and commits past it.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from dependency.events.bus import build_event_envelope, kafka_producer_config, physical_topic_for
from dependency.events.consumer import decode_envelope, kafka_consumer_config

PROBE_TOPIC = "hermes.transport.probe"


def probe_envelope(run_id: str) -> dict:
    return build_event_envelope({
        "outbox_id": f"PROBE-{run_id}",
        "topic": PROBE_TOPIC,
        "event_key": f"probe:{run_id}",
        "payload": {"run_id": run_id, "purpose": "aiven kafka roundtrip verification"},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def kafka_roundtrip(
    *,
    timeout_seconds: float = 30.0,
    producer_factory=None,
    consumer_factory=None,
) -> dict:
    """Publish one probe and consume it back. Returns a secret-free report."""
    if producer_factory is None or consumer_factory is None:
        from confluent_kafka import Consumer, Producer

        producer_factory = producer_factory or Producer
        consumer_factory = consumer_factory or Consumer

    run_id = uuid4().hex
    topic = physical_topic_for(PROBE_TOPIC)
    group = f"hermes-roundtrip-{run_id[:12]}"
    report = {"run_id": run_id, "physical_topic": topic, "consumer_group": group,
              "published": False, "consumed": False, "status": "FAILED"}

    # Subscribe before publishing so auto.offset.reset=latest cannot skip the probe.
    consumer_config = kafka_consumer_config(group_id=group)
    consumer_config["auto.offset.reset"] = "earliest"
    consumer = consumer_factory(consumer_config)
    consumer.subscribe([topic])
    started = time.monotonic()
    try:
        delivery: dict = {}
        producer = producer_factory(kafka_producer_config())
        producer.produce(
            topic,
            key=f"probe:{run_id}".encode("utf-8"),
            value=json.dumps(probe_envelope(run_id)).encode("utf-8"),
            callback=lambda err, msg: delivery.update(
                error=str(err) if err else None,
                partition=None if err else msg.partition(),
                offset=None if err else msg.offset(),
            ),
        )
        producer.flush(timeout_seconds)
        if not delivery or delivery.get("error"):
            report["error_type"] = "DeliveryFailed" if delivery else "DeliveryTimeout"
            return report
        report.update(published=True, partition=delivery["partition"],
                      offset=delivery["offset"],
                      publish_ms=round((time.monotonic() - started) * 1000))

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            message = consumer.poll(1.0)
            if message is None or message.error():
                continue
            try:
                envelope = decode_envelope(message.value())
            except ValueError:
                continue
            if envelope["outbox_id"] == f"PROBE-{run_id}":
                consumer.commit(message=message, asynchronous=False)
                report.update(consumed=True, status="VERIFIED",
                              roundtrip_ms=round((time.monotonic() - started) * 1000),
                              envelope_topic=envelope["topic"])
                return report
        report["error_type"] = "ConsumeTimeout"
        return report
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        return report
    finally:
        consumer.close()
