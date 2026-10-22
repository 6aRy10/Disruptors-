"""Safe, read-only local backend diagnostic for HERMES.

No credentials, exception messages, SQL query contents or hostnames are returned.
Never alters the configured database or automatically runs migrations.
"""
from __future__ import annotations

import os

from dependency.db.connection import connect, database_target
from dependency.graph.app_views import incident_inbox, map_facilities
from dependency.graph.activity_stream import read_activity

CRITICAL_TABLES = (
    "network_facilities", "external_events", "event_outbox",
    "event_consumptions", "incidents", "incident_investigation_tasks",
)


def _safe_error(exc: Exception) -> dict:
    result = {"status": "ERROR", "error_type": type(exc).__name__}
    code = getattr(exc, "sqlstate", None)
    if code and isinstance(code, str) and len(code) == 5 and code.isalnum():
        result["sqlstate"] = code
    return result


def local_readiness() -> dict:
    """Diagnose the backend without writing to PostgreSQL.

    A GET with 200 is returned even for NOT_READY so the UI and PowerShell can
    show the structured reason instead of discarding a non-JSON HTTP 500 page.
    This endpoint must remain read-only and avoid private network metadata.
    """
    configured_local = bool(os.getenv("DATABASE_URL"))
    configured_aiven = bool(os.getenv("AIVEN_DATABASE_URL"))
    requested = os.getenv("DEPENDENCY_DATABASE_TARGET", "").strip().lower()
    result = {
        "status": "NOT_READY",
        "database_selection": {
            "local_url_present": configured_local,
            "aiven_url_present": configured_aiven,
            "explicit_target": requested or None,
            "selected_target": None,
        },
        "database": {"status": "NOT_CHECKED"},
        "schema": {"status": "NOT_CHECKED"},
        "endpoints": {},
        "read_only": True,
    }

    try:
        target = database_target()
        result["database_selection"]["selected_target"] = target
    except Exception as exc:
        result["database"] = _safe_error(exc)
        if configured_local and configured_aiven and not requested:
            result["action"] = (
                "Both URLs are configured. Set DEPENDENCY_DATABASE_TARGET=local "
                "or aiven explicitly, then restart the backend. Do not reseed."
            )
        elif not configured_local and not configured_aiven:
            result["action"] = (
                "Configure DATABASE_URL or AIVEN_DATABASE_URL in the existing "
                "backend environment. Never paste the URL into chat."
            )
        else:
            result["action"] = "Check the selected database target in the backend environment."
        return result

    try:
        with connect() as conn:
            # These queries only inspect the schema. Do not use a seed loader.
            tables = [conn.execute("SELECT to_regclass(%s)",
                                   ("public." + name,)).fetchone()[0]
                      for name in CRITICAL_TABLES]
            count = (int(conn.execute("SELECT COUNT(*) FROM network_facilities").fetchone()[0])
                     if tables[0] is not None else None)
    except Exception as exc:
        result["database"] = _safe_error(exc)
        result["action"] = (
            "The selected PostgreSQL connection failed. Check whether its server "
            "is running and whether the URL points to the intended populated database."
        )
        return result

    result["database"] = {"status": "CONNECTED", "network_facility_count": count}
    missing = [name for name, table in zip(CRITICAL_TABLES, tables) if table is None]
    result["schema"] = {
        "status": "INCOMPLETE" if missing else "READY",
        "missing_tables": missing,
    }
    if missing:
        result["action"] = (
            "This selected database has missing required tables. Verify the "
            "database target; do not run the seed loader on populated data."
        )
        return result

    probes = (
        ("/app-data/incidents", lambda: incident_inbox(limit=1)),
        ("/app-data/activity", lambda: read_activity(limit=1)),
        ("/app-data/map/facilities", lambda: map_facilities(limit=1)),
    )
    for path, probe in probes:
        try:
            probe()
            result["endpoints"][path] = {"status": "OK"}
        except Exception as exc:
            result["endpoints"][path] = _safe_error(exc)

    errors = [p for p, info in result["endpoints"].items()
              if info["status"] == "ERROR"]
    if errors:
        result["status"] = "DEGRADED"
        result["action"] = (
            "PostgreSQL is connected, but one or more read-only API queries fail. "
            "Use the endpoint and SQLSTATE above with the Uvicorn traceback "
            "to identify a schema or data mismatch. Do not reset the database."
        )
    elif count == 0:
        result["status"] = "NOT_READY"
        result["action"] = (
            "The selected network_facilities table is empty. Verify you selected "
            "the existing populated database. Do not automatically load seed data."
        )
    else:
        result["status"] = "READY"
        result["action"] = "Read-only checks passed; retry the application."
    return result
