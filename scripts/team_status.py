"""Read-only team handoff: one report describing actual local operational state."""
from __future__ import annotations

import json

from dependency.db.connection import connect


def status_report() -> dict:
    result = {"status": "NOT_READY", "database": {}, "records": {}, "runtime": {}}
    try:
        with connect() as conn:
            result["database"]["name"] = conn.execute(
                "SELECT current_database()"
            ).fetchone()[0]
            expected = {
                "public_network_facilities": ("network_facilities", "SELECT COUNT(*) FROM network_facilities"),
                "generated_private_products": ("products", "SELECT COUNT(*) FROM products WHERE sku LIKE 'DTSKU-%'"),
                "material_allocations": ("material_allocations", "SELECT COUNT(*) FROM material_allocations"),
                "customer_commitments": ("fulfilment_commitments", "SELECT COUNT(*) FROM fulfilment_commitments"),
                "events": ("external_events", "SELECT COUNT(*) FROM external_events"),
                "open_incidents": ("incidents", "SELECT COUNT(*) FROM incidents WHERE status IN ('OPEN','INVESTIGATING')"),
                "open_evidence_tasks": ("incident_investigation_tasks", "SELECT COUNT(*) FROM incident_investigation_tasks WHERE status='OPEN'"),
                "supplier_confirmation_requests": ("supplier_confirmation_requests", "SELECT COUNT(*) FROM supplier_confirmation_requests"),
                "confirmed_facility_capacity_windows": ("confirmed_facility_capacity", "SELECT COUNT(*) FROM confirmed_facility_capacity"),
                "investigation_outreach_drafts": ("investigation_outreach_drafts", "SELECT COUNT(*) FROM investigation_outreach_drafts"),
            }
            missing = [
                name for name, (table, _) in expected.items()
                if conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0] is None
            ]
            result["database"]["missing_components"] = missing
            for name, (_, query) in expected.items():
                if name not in missing:
                    result["records"][name] = int(conn.execute(query).fetchone()[0])
            if conn.execute(
                "SELECT to_regclass('public.operational_state_version')"
            ).fetchone()[0]:
                result["runtime"]["operational_state_version"] = int(conn.execute(
                    "SELECT version FROM operational_state_version WHERE singleton=true"
                ).fetchone()[0])
            if conn.execute("SELECT to_regclass('public.event_outbox')").fetchone()[0]:
                result["runtime"]["unpublished_outbox_messages"] = int(conn.execute(
                    "SELECT COUNT(*) FROM event_outbox WHERE published_at IS NULL"
                ).fetchone()[0])
                if conn.execute("SELECT to_regclass('public.event_consumptions')").fetchone()[0]:
                    result["runtime"]["failed_incident_consumptions"] = int(conn.execute(
                        "SELECT COUNT(*) FROM event_consumptions WHERE status='ERROR' AND consumer_name='incident-orchestrator'"
                    ).fetchone()[0])
                    result["runtime"]["processed_local_outbox_messages"] = int(conn.execute(
                        """
                        SELECT COUNT(*) FROM event_consumptions
                        WHERE status='SUCCESS' AND consumer_name='incident-orchestrator'
                        """
                    ).fetchone()[0])
                    result["runtime"]["pending_local_outbox_messages"] = int(conn.execute(
                        """
                        SELECT COUNT(*) FROM event_outbox o
                        WHERE NOT EXISTS (
                          SELECT 1 FROM event_consumptions c
                          WHERE c.outbox_id=o.outbox_id
                            AND c.consumer_name='incident-orchestrator'
                            AND c.status='SUCCESS'
                        )
                        """
                    ).fetchone()[0])
            if missing:
                result["status"] = "SCHEMA_INCOMPLETE"
            elif (
                result["records"]["public_network_facilities"] < 770
                or result["records"]["generated_private_products"] < 2500
                or result["records"]["material_allocations"] < 170000
            ):
                result["status"] = "DATA_INCOMPLETE"
                result["action"] = (
                    "Verify the selected database; initialize ONLY a disposable "
                    "development database. Do not reset existing private data."
                )
            else:
                result["status"] = "READY"
            result["runtime"]["live_polling_status"] = "NOT_VERIFIED_FROM_DATABASE"
            result["runtime"]["aiven_kafka_status"] = "NOT_VERIFIED_FROM_DATABASE"
    except Exception as exc:
        # Do not leak host, usernames, passwords or full exception text.
        result["error_type"] = type(exc).__name__
    return result


if __name__ == "__main__":
    print(json.dumps(status_report(), indent=2))
