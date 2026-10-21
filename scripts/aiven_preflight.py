"""Read-only Aiven readiness preflight; does not migrate data or print secrets."""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

import psycopg

REQUIRED_TABLES = (
    "network_facilities", "products", "bom", "material_allocations",
    "fulfilment_commitments", "incident_investigation_tasks", "event_outbox",
)


def check_postgresql(url: str | None = None) -> dict:
    """Check extension availability, schema and storage without changing the DB."""
    value = url if url is not None else os.getenv("AIVEN_DATABASE_URL", "")
    if not value:
        return {"status": "NOT_CONFIGURED", "action": "Set AIVEN_DATABASE_URL privately."}
    try:
        parsed = urlsplit(value)
        identity = {"host": parsed.hostname, "port": parsed.port or 5432,
                    "database": (parsed.path or "").lstrip("/")}
    except ValueError:
        return {"status": "INVALID_URL"}
    try:
        with psycopg.connect(value, connect_timeout=6) as conn:
            extensions = {
                r[0]: r[1] for r in conn.execute(
                    "SELECT name,installed_version FROM pg_available_extensions WHERE name='postgis'"
                ).fetchall()
            }
            present = [
                table for table in REQUIRED_TABLES
                if conn.execute(
                    "SELECT to_regclass(%s)", (f"public.{table}",)
                ).fetchone()[0] is not None
            ]
            bytes_used = int(conn.execute(
                "SELECT pg_database_size(current_database())"
            ).fetchone()[0])
        has_postgis = "postgis" in extensions
        schema_ready = len(present) == len(REQUIRED_TABLES)
        return {
            "status": (
                "POSTGIS_NOT_AVAILABLE" if not has_postgis
                else "POSTGIS_NOT_INSTALLED" if not extensions["postgis"]
                else "READY_WITH_SCHEMA" if schema_ready
                else "READY_FOR_SCHEMA_IMPORT"
            ),
            "target": identity,
            "postgis_available": has_postgis,
            "postgis_installed": bool(extensions.get("postgis")),
            "schema_tables_present": len(present),
            "schema_tables_required": len(REQUIRED_TABLES),
            "missing_tables": sorted(set(REQUIRED_TABLES).difference(present)),
            "current_database_bytes": bytes_used,
            "note": "No database changes performed. Confirm free-tier capacity before any import.",
        }
    except Exception as exc:
        # Network/database error strings can include credentials or private hostnames.
        return {"status": "CONNECTION_FAILED", "target": identity,
                "error_type": type(exc).__name__}


def check_kafka() -> dict:
    """Check configuration only. No network call, topic creation or billing."""
    brokers = os.getenv("AIVEN_KAFKA_BROKERS", "").strip()
    if not brokers:
        return {"status": "NOT_CONFIGURED",
                "action": "Create or connect Kafka, then set AIVEN_KAFKA_BROKERS."}
    protocol = os.getenv("AIVEN_KAFKA_SECURITY_PROTOCOL", "SSL").upper()
    if protocol not in {"SSL", "SASL_SSL"}:
        return {"status": "UNSAFE_PROTOCOL", "protocol": protocol}
    user = bool(os.getenv("AIVEN_KAFKA_USERNAME"))
    pwd = bool(os.getenv("AIVEN_KAFKA_PASSWORD"))
    cert = bool(os.getenv("AIVEN_KAFKA_CERT_FILE"))
    key = bool(os.getenv("AIVEN_KAFKA_KEY_FILE"))
    if (user != pwd) or (cert != key):
        return {"status": "PARTIAL_AUTH_CONFIGURATION", "protocol": protocol}
    if not ((user and pwd) or (cert and key)):
        return {"status": "MISSING_AUTHENTICATION", "protocol": protocol}
    if user and pwd and protocol != "SASL_SSL":
        return {"status": "PROTOCOL_MISMATCH", "expected": "SASL_SSL"}
    return {"status": "CONFIGURED_NOT_CONNECTED", "protocol": protocol,
            "note": "Kafka TLS reachability, topics and publish/consume are not yet verified."}


def probe_kafka_network() -> dict:
    """Read-only Kafka metadata query: no topics created and no event published."""
    from dependency.events.bus import _kafka_config
    from dependency.events.consumer import kafka_subscription_topics
    configured=check_kafka()
    if configured["status"]!="CONFIGURED_NOT_CONNECTED":
        return {"status":"NOT_READY","configuration":configured["status"]}
    try:
        from confluent_kafka.admin import AdminClient
        topics=kafka_subscription_topics()
        metadata=AdminClient(_kafka_config()).list_topics(timeout=8.0)
        missing=sorted(set(topics)-set(metadata.topics))
        denied=sorted(t for t in topics if t in metadata.topics
                      and metadata.topics[t].error is not None)
        return {"status":"MISSING_TOPICS" if missing else
                 "TOPIC_ACCESS_ERROR" if denied else "READY_TO_STREAM",
                "expected_topics":list(topics),"missing_topics":missing,
                "topic_errors":denied,"broker_count":len(metadata.brokers),
                "changed_remote_state":False}
    except Exception as exc:
        # librdkafka error messages can disclose private connection endpoints.
        return {"status":"CONNECTION_FAILED","error_type":type(exc).__name__,
                "changed_remote_state":False}


def report(*, probe_kafka: bool = False) -> dict:
    pg = check_postgresql()
    kafka = check_kafka()
    return {
        "aiven_postgresql": pg,
        "aiven_kafka": kafka,
        "kafka_network": probe_kafka_network() if probe_kafka else {"status":"NOT_PROBED"},
        "application_database_selection": (
            "DEPENDENCY_DATABASE_TARGET explicitly selects local or aiven. "
            "When both URLs exist and no target is selected, application connections fail closed."
        ),
        "migration_performed": False,
        "secrets_printed": False,
    }


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--probe-kafka",action="store_true",
                        help="Check broker and topic TLS reachability without publishing.")
    args=parser.parse_args()
    print(json.dumps(report(probe_kafka=args.probe_kafka), indent=2))
