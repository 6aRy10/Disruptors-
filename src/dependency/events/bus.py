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


def _kafka_config() -> dict:
    brokers = os.getenv("AIVEN_KAFKA_BROKERS", "").strip()
    if not brokers:
        raise RuntimeError("AIVEN_KAFKA_BROKERS is not configured.")

    config = {
        "bootstrap.servers": brokers,
        "client.id": os.getenv("AIVEN_KAFKA_CLIENT_ID", "disruptors-dependency"),
        "security.protocol": os.getenv("AIVEN_KAFKA_SECURITY_PROTOCOL", "SSL"),
    }

    ca = os.getenv("AIVEN_KAFKA_CA_FILE")
    cert = os.getenv("AIVEN_KAFKA_CERT_FILE")
    key = os.getenv("AIVEN_KAFKA_KEY_FILE")
    username = os.getenv("AIVEN_KAFKA_USERNAME")
    password = os.getenv("AIVEN_KAFKA_PASSWORD")

    if ca:
        config["ssl.ca.location"] = ca
    if cert:
        config["ssl.certificate.location"] = cert
    if key:
        config["ssl.key.location"] = key

    if username and password:
        config["security.protocol"] = os.getenv(
            "AIVEN_KAFKA_SECURITY_PROTOCOL",
            "SASL_SSL",
        )
        config["sasl.mechanism"] = os.getenv("AIVEN_KAFKA_SASL_MECHANISM", "PLAIN")
        config["sasl.username"] = username
        config["sasl.password"] = password

    return config


def flush_to_kafka(limit: int = 100) -> dict:
    """Publish pending outbox events to Aiven Kafka.

    If Aiven is not configured, callers should keep the rows in the local
    outbox. Nothing is silently dropped.
    """
    try:
        from confluent_kafka import Producer
    except ImportError as exc:
        raise RuntimeError("confluent-kafka is not installed.") from exc

    rows = pending(limit=limit)
    if not rows:
        return {"attempted": 0, "published": 0, "failed": 0}

    producer = Producer(_kafka_config())
    results: dict[str, str | None] = {}

    def delivery(err, msg, outbox_id):
        results[outbox_id] = str(err) if err else None

    for row in rows:
        producer.produce(
            physical_topic_for(row["topic"]),
            key=row["event_key"].encode("utf-8"),
            value=json.dumps(
                build_event_envelope(row),
                default=str,
            ).encode("utf-8"),
            callback=lambda err, msg, oid=row["outbox_id"]: delivery(err, msg, oid),
        )

    producer.flush(15)

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
