"""Secret-free health checks for the Kafka transport and its workers.

Everything here is read-only. Error messages from psycopg/librdkafka are
reduced to exception type names because they can embed hostnames or URLs.
"""
from __future__ import annotations

import os

from dependency.automation.orchestrator import DEFAULT_CONSUMER
from dependency.db.connection import connect
from dependency.events.bus import outbox_backlog
from dependency.events.consumer import Heartbeat, kafka_subscription_topics
from dependency.events.kafka_settings import consumer_group, load_kafka_settings

HEARTBEAT_STALE_SECONDS = float(os.getenv("HERMES_HEARTBEAT_STALE_SECONDS", "90"))


def _error(exc: Exception) -> dict:
    return {"status": "ERROR", "error_type": type(exc).__name__}


def liveness() -> dict:
    """Process is up; no dependencies touched."""
    return {"status": "ALIVE"}


def database_readiness() -> dict:
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
            outbox = conn.execute("SELECT to_regclass('public.event_outbox')").fetchone()[0]
    except Exception as exc:
        return _error(exc)
    return {"status": "READY" if outbox else "SCHEMA_INCOMPLETE"}


def consumer_lag(consumer_name: str = DEFAULT_CONSUMER) -> dict:
    """Published outbox rows this consumer has not yet successfully handled."""
    with connect() as conn:
        unconsumed, errored = conn.execute(
            """
            SELECT COUNT(*) FILTER (WHERE c.status IS NULL),
                   COUNT(*) FILTER (WHERE c.status='ERROR')
            FROM event_outbox o
            LEFT JOIN event_consumptions c
              ON c.consumer_name=%s AND c.outbox_id=o.outbox_id
            WHERE o.published_at IS NOT NULL
            """,
            (consumer_name,),
        ).fetchone()
    return {"consumer_name": consumer_name,
            "published_not_consumed": int(unconsumed),
            "consumption_errors": int(errored)}


def heartbeat_status(path: str | None) -> dict:
    if not path:
        return {"status": "NOT_CONFIGURED"}
    age = Heartbeat.age_seconds(path)
    if age is None:
        return {"status": "MISSING"}
    return {"status": "FRESH" if age <= HEARTBEAT_STALE_SECONDS else "STALE",
            "age_seconds": round(age, 1)}


def probe_brokers(timeout: float = 8.0) -> dict:
    """Metadata-only broker probe: creates nothing and publishes nothing."""
    settings = load_kafka_settings()
    if not settings.describe()["valid"]:
        return {"status": "NOT_CONFIGURED"}
    try:
        from confluent_kafka.admin import AdminClient

        topics = kafka_subscription_topics()
        metadata = AdminClient(settings.librdkafka()).list_topics(timeout=timeout)
        missing = sorted(set(topics) - set(metadata.topics))
        denied = sorted(t for t in topics
                        if t in metadata.topics and metadata.topics[t].error is not None)
        return {
            "status": ("MISSING_TOPICS" if missing else
                       "TOPIC_ACCESS_ERROR" if denied else "REACHABLE"),
            "broker_count": len(metadata.brokers),
            "expected_topics": list(topics),
            "missing_topics": missing,
            "topic_errors": denied,
        }
    except Exception as exc:
        return {"status": "UNREACHABLE", "error_type": type(exc).__name__}


def kafka_health(*, probe: bool = False, consumer_name: str = DEFAULT_CONSUMER) -> dict:
    """Combined transport view for /health/kafka and the container healthcheck."""
    settings = load_kafka_settings().describe()
    result: dict = {
        "status": "NOT_CONFIGURED" if not settings["configured"]
        else "MISCONFIGURED" if not settings["valid"] else "CONFIGURED",
        "kafka": settings,
        "routing": {
            "mode": os.getenv("AIVEN_KAFKA_ROUTING_MODE", "single"),
            "subscription_topics": None,
            "consumer_group": consumer_group(),
        },
        "outbox": None,
        "consumer_lag": None,
        "brokers": {"status": "NOT_PROBED"},
        "read_only": True,
    }
    try:
        result["routing"]["subscription_topics"] = list(kafka_subscription_topics())
    except ValueError as exc:
        result["routing"]["error_type"] = type(exc).__name__
        result["status"] = "MISCONFIGURED"

    try:
        result["outbox"] = outbox_backlog()
        result["consumer_lag"] = consumer_lag(consumer_name)
    except Exception as exc:
        result["outbox"] = _error(exc)
        result["status"] = "DATABASE_ERROR"

    if probe and settings["valid"]:
        result["brokers"] = probe_brokers()
        if result["brokers"]["status"] == "REACHABLE" and result["status"] == "CONFIGURED":
            result["status"] = "STREAMING_READY"
        elif result["brokers"]["status"] != "REACHABLE":
            result["status"] = "BROKER_" + result["brokers"]["status"]
    return result


def readiness(*, probe_kafka: bool = False) -> dict:
    """Aggregate readiness for the API container."""
    database = database_readiness()
    kafka = kafka_health(probe=probe_kafka) if database["status"] == "READY" else {
        "status": "SKIPPED_DATABASE_NOT_READY"}
    ready = database["status"] == "READY" and kafka["status"] not in {
        "MISCONFIGURED", "DATABASE_ERROR"} and not kafka["status"].startswith("BROKER_")
    return {"status": "READY" if ready else "NOT_READY",
            "database": database, "kafka": kafka["status"], "read_only": True}
