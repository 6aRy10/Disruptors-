from __future__ import annotations

import json
import os
from uuid import uuid4

from dependency.db.connection import connect

TOPIC_EXTERNAL_EVENTS = "external.events"
TOPIC_BUSINESS_STATE = "business.state.updated"
TOPIC_SUPPLIER_CAPACITY = "supplier.capacity.updated"
TOPIC_INCIDENT_DETECTED = "incident.detected"
TOPIC_PLAN_GENERATED = "plan.generated"
TOPIC_PLAN_INVALIDATED = "plan.invalidated"
TOPIC_APPROVAL_REQUESTED = "approval.requested"
TOPIC_SUPPLIER_CONFIRMATION_REQUESTED = "supplier.confirmation.requested"
TOPIC_SUPPLIER_CONFIRMATION_REPLY = "supplier.confirmation.reply_received"
TOPIC_DECISION_CONFIRMED = "decision.confirmed"
TOPIC_ACTION_EXECUTED = "action.executed"


def kafka_routing_mode() -> str:
    """Use one physical topic by default to fit the free Aiven Kafka limit."""
    mode = os.getenv("AIVEN_KAFKA_ROUTING_MODE", "single").strip().lower()
    if mode not in {"single", "logical"}:
        raise ValueError("AIVEN_KAFKA_ROUTING_MODE must be single or logical.")
    return mode


def physical_topic_for(logical_topic: str) -> str:
    if not logical_topic or not logical_topic.strip():
        raise ValueError("Logical topic must be provided.")
    if kafka_routing_mode() == "logical":
        return logical_topic
    topic = os.getenv("AIVEN_KAFKA_PHYSICAL_TOPIC", "dependency.events").strip()
    if not topic or len(topic) > 249:
        raise ValueError("Invalid Kafka physical topic.")
    return topic


def enqueue_outbox(conn, *, topic: str, event_key: str, payload: dict) -> str:
    """Write an event to the transactional outbox using an existing DB connection."""
    outbox_id = f"OUT-{uuid4()}"
    conn.execute(
        """
        INSERT INTO event_outbox(outbox_id,topic,event_key,payload)
        VALUES (%s,%s,%s,%s::jsonb)
        """,
        (outbox_id, topic, event_key, json.dumps(payload, default=str)),
    )
    return outbox_id


def enqueue(*, topic: str, event_key: str, payload: dict) -> str:
    with connect() as conn:
        outbox_id = enqueue_outbox(
            conn,
            topic=topic,
            event_key=event_key,
            payload=payload,
        )
        conn.commit()
    return outbox_id


def pending(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT outbox_id,topic,event_key,payload,created_at,attempts
            FROM event_outbox
            WHERE published_at IS NULL
            ORDER BY created_at,outbox_id
            LIMIT %s
            """,
            (int(limit),),
        ).fetchall()
    return [
        {
            "outbox_id": r[0],
            "topic": r[1],
            "event_key": r[2],
            "payload": r[3],
            "created_at": r[4].isoformat(),
            "attempts": int(r[5]),
        }
        for r in rows
    ]


def build_event_envelope(row: dict) -> dict:
    """Create the transport envelope used by Kafka consumers.

    The outbox_id is preserved so downstream consumers can apply the same
    idempotency rule as the local PostgreSQL worker.
    """
    return {
        "outbox_id": row["outbox_id"],
        "topic": row["topic"],
        "event_key": row["event_key"],
        "payload": row["payload"],
        "created_at": row.get("created_at"),
    }


def outbox_exists(outbox_id: str) -> bool:
    """True when this database owns the event; consumers must not apply foreign events."""
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM event_outbox WHERE outbox_id=%s", (outbox_id,)
        ).fetchone() is not None


def outbox_backlog() -> dict:
    """Read-only outbox statistics used by health checks; no secrets involved."""
    with connect() as conn:
        pending_count, oldest_age, retrying = conn.execute(
            """
            SELECT COUNT(*),
                   EXTRACT(EPOCH FROM (now()-MIN(created_at))),
                   COUNT(*) FILTER (WHERE attempts>0)
            FROM event_outbox
            WHERE published_at IS NULL
            """
        ).fetchone()
        published_last_hour = conn.execute(
            """
            SELECT COUNT(*) FROM event_outbox
            WHERE published_at IS NOT NULL AND published_at>now()-interval '1 hour'
            """
        ).fetchone()[0]
    return {
        "pending": int(pending_count),
        "pending_with_failed_attempts": int(retrying),
        "oldest_pending_age_seconds": (
            round(float(oldest_age), 1) if oldest_age is not None else None
        ),
        "published_last_hour": int(published_last_hour),
    }


def _kafka_config() -> dict:
    """Base librdkafka config shared by producer, consumer and admin probes."""
    from dependency.events.kafka_settings import load_kafka_settings

    return load_kafka_settings().librdkafka()


def kafka_producer_config() -> dict:
    """At-least-once, ordered delivery: the outbox marks rows only on ack."""
    config = _kafka_config()
    config.update(
        {
            "enable.idempotence": True,
            "acks": "all",
            "message.timeout.ms": int(os.getenv("AIVEN_KAFKA_MESSAGE_TIMEOUT_MS", "20000")),
            "socket.timeout.ms": 10000,
            "compression.type": "lz4",
        }
    )
    return config


def flush_to_kafka(limit: int = 100, *, flush_timeout: float = 25.0) -> dict:
    """Publish pending outbox events to Aiven Kafka.

    If Aiven is not configured, callers should keep the rows in the local
    outbox. Nothing is silently dropped: a row is marked published only after
    the broker acknowledges it, otherwise its attempt count and last_error grow.
    """
    try:
        from confluent_kafka import Producer
    except ImportError as exc:
        raise RuntimeError("confluent-kafka is not installed.") from exc

    rows = pending(limit=limit)
    if not rows:
        return {"attempted": 0, "published": 0, "failed": 0}

    producer = Producer(kafka_producer_config())
    results: dict[str, str | None] = {}

    def delivery(err, msg, outbox_id):
        results[outbox_id] = str(err) if err else None

    for row in rows:
        try:
            producer.produce(
                physical_topic_for(row["topic"]),
                key=row["event_key"].encode("utf-8"),
                value=json.dumps(
                    build_event_envelope(row),
                    default=str,
                ).encode("utf-8"),
                callback=lambda err, msg, oid=row["outbox_id"]: delivery(err, msg, oid),
            )
        except Exception as exc:  # BufferError, KafkaException, ValueError
            results[row["outbox_id"]] = f"{type(exc).__name__}: {exc}"

    producer.flush(flush_timeout)

    published = 0
    failed = 0
    with connect() as conn:
        for row in rows:
            outbox_id = row["outbox_id"]
            err = results.get(outbox_id)
            if err is None and outbox_id in results:
                conn.execute(
                    """
                    UPDATE event_outbox
                    SET published_at=now(),attempts=attempts+1,last_error=NULL
                    WHERE outbox_id=%s
                    """,
                    (outbox_id,),
                )
                published += 1
            else:
                conn.execute(
                    """
                    UPDATE event_outbox
                    SET attempts=attempts+1,last_error=%s
                    WHERE outbox_id=%s
                    """,
                    (err or "delivery callback not received", outbox_id),
                )
                failed += 1
        conn.commit()

    return {
        "attempted": len(rows),
        "published": published,
        "failed": failed,
    }
