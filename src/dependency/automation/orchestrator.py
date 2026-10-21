from __future__ import annotations

import json
from typing import Any

from dependency.db.connection import connect
from dependency.incidents.triage import triage_event
from dependency.investigation.tasks import create_investigation_tasks
from dependency.memory.service import save_plan_snapshot
from dependency.solver.portfolio import plan_event_recovery


DEFAULT_CONSUMER = "incident-orchestrator"


def pending_events(
    *,
    consumer_name: str = DEFAULT_CONSUMER,
    limit: int = 50,
) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              o.outbox_id,o.topic,o.event_key,o.payload,o.created_at
            FROM event_outbox o
            LEFT JOIN event_consumptions c
              ON c.consumer_name=%s
             AND c.outbox_id=o.outbox_id
             AND c.status='SUCCESS'
            WHERE c.outbox_id IS NULL
            ORDER BY o.created_at,o.outbox_id
            LIMIT %s
            """,
            (consumer_name, int(limit)),
        ).fetchall()
    return [
        {
            "outbox_id": r[0],
            "topic": r[1],
            "event_key": r[2],
            "payload": r[3],
            "created_at": r[4].isoformat(),
        }
        for r in rows
    ]


def _open_incidents() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT incident_id,event_id,scenario_id
            FROM incidents
            WHERE status IN ('OPEN','INVESTIGATING')
              AND scenario_id IS NOT NULL
            ORDER BY detected_at,incident_id
            """
        ).fetchall()
    return [
        {
            "incident_id": r[0],
            "event_id": r[1],
            "scenario_id": r[2],
        }
        for r in rows
    ]


def _save_portfolio_plans(
    *,
    incident_id: str,
    portfolio: dict,
    only_sku: str | None = None,
) -> list[dict]:
    saved = []
    versions = portfolio.get("state_versions") or []
    state_version = int(max(versions)) if versions else 0

    for product in portfolio.get("products", []):
        sku = product["sku"]
        if only_sku and sku != only_sku:
            continue
        for plan in product.get("candidates", []):
            saved.append(
                save_plan_snapshot(
                    incident_id=incident_id,
                    state_version=state_version,
                    sku=sku,
                    plan=plan,
                )
            )
    return saved


def _process_external_event(
    payload: dict,
    *,
    run_agents: bool,
    radius_km: float,
) -> dict:
    event_id = payload.get("event_id")
    if not event_id:
        return {"status": "IGNORED", "reason": "MISSING_EVENT_ID"}

    triage = triage_event(
        event_id=event_id,
        radius_km=radius_km,
    )
    if not triage.get("incident"):
        return {
            "status": triage["status"],
            "event_id": event_id,
            "triage": triage,
        }

    scenario_id = triage.get("scenario_id")
    if not scenario_id:
        # No event-specific operational state is known. Create evidence work;
        # never invent a disruption, supplier capacity or recovery scenario.
        tasks = create_investigation_tasks(
            incident_id=triage["incident"]["incident_id"],
            triage=triage,
        )
        return {
            "status": "INVESTIGATION_REQUIRED",
            "event_id": event_id,
            "incident_id": triage["incident"]["incident_id"],
            "scenario_id": None,
            "investigation_task_count": len(tasks),
            "priority_tasks": tasks[:10],
            "required_evidence": triage.get("next_required_evidence", []),
            "business_exposure": triage.get("commercial_totals", {}),
            "claim_rule": "POTENTIAL_EXPOSURE_ONLY_NOT_CONFIRMED_LOSS",
        }

    if run_agents:
        # Deterministic ingestion must not depend on optional AI tool imports.
        from dependency.agents.orchestrator import run_event_autopilot

        result = run_event_autopilot(
            event_id=event_id,
            radius_km=radius_km,
            persist=True,
        )
        return {
            "status": "AGENTS_RUN",
            "event_id": event_id,
            "incident_id": triage["incident"]["incident_id"],
            "result": result,
        }

    portfolio = plan_event_recovery(
        event_id=event_id,
        scenario_id=scenario_id,
        radius_km=radius_km,
    )
    saved = _save_portfolio_plans(
        incident_id=triage["incident"]["incident_id"],
        portfolio=portfolio,
    )
    return {
        "status": "PORTFOLIO_REPLANNED",
        "event_id": event_id,
        "incident_id": triage["incident"]["incident_id"],
        "scenario_id": scenario_id,
        "portfolio_summary": portfolio["summary"],
        "saved_plan_count": len(saved),
    }


def _process_plan_invalidated(
    payload: dict,
    *,
    radius_km: float,
) -> dict:
    sku = payload.get("sku")
    if not sku:
        return {"status": "IGNORED", "reason": "MISSING_SKU"}

    replans = []
    for incident in _open_incidents():
        try:
            portfolio = plan_event_recovery(
                event_id=incident["event_id"],
                scenario_id=incident["scenario_id"],
                radius_km=radius_km,
            )
        except ValueError:
            continue

        product_skus = {row["sku"] for row in portfolio.get("products", [])}
        if sku not in product_skus:
            continue

        # Shared upstream and backup capacity couple SKUs. Persist the full
        # recomputed portfolio; saving only the changed SKU leaves related
        # products with stale plans despite the joint optimizer rerunning.
        saved = _save_portfolio_plans(
            incident_id=incident["incident_id"],
            portfolio=portfolio,
        )
        replans.append(
            {
                "incident_id": incident["incident_id"],
                "event_id": incident["event_id"],
                "scenario_id": incident["scenario_id"],
                "sku": sku,
                "saved_plan_count": len(saved),
                "portfolio_status": portfolio["portfolio_status"],
                "summary": portfolio["summary"],
            }
        )

    return {
        "status": "REPLANNED_OPEN_INCIDENTS",
        "sku": sku,
        "new_state_version": payload.get("new_state_version"),
        "reason": payload.get("reason"),
        "replans": replans,
    }


def handle_event(
    *,
    topic: str,
    payload: dict,
    run_agents: bool = False,
    radius_km: float = 150.0,
) -> dict:
    """Handle one business event independently of its transport.

    The same function can be called by the local transactional-outbox worker
    today and by an Aiven Kafka consumer later.
    """
    if topic == "external.events":
        return _process_external_event(
            payload,
            run_agents=run_agents,
            radius_km=radius_km,
        )
    if topic == "plan.invalidated":
        return _process_plan_invalidated(
            payload,
            radius_km=radius_km,
        )

    if topic in {
        "business.state.updated",
        "supplier.capacity.updated",
        "supplier.confirmation.requested",
        "supplier.confirmation.reply_received",
        "incident.detected",
        "plan.generated",
        "approval.requested",
        "decision.confirmed",
        "action.executed",
    }:
        return {
            "status": "OBSERVED",
            "topic": topic,
            "reason": "NO_DIRECT_ACTION_FOR_THIS_CONSUMER",
        }

    return {
        "status": "IGNORED",
        "topic": topic,
        "reason": "UNSUPPORTED_TOPIC",
    }


def _record_consumption(
    *,
    consumer_name: str,
    outbox_id: str,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO event_consumptions(
              consumer_name,outbox_id,status,result_json,error_text
            ) VALUES (%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (consumer_name,outbox_id) DO UPDATE SET
              status=EXCLUDED.status,
              processed_at=now(),
              result_json=EXCLUDED.result_json,
              error_text=EXCLUDED.error_text
            """,
            (
                consumer_name,
                outbox_id,
                status,
                json.dumps(result or {}, default=str),
                error,
            ),
        )
        conn.commit()


def consumption_status(
    *,
    consumer_name: str,
    outbox_id: str,
) -> str | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT status
            FROM event_consumptions
            WHERE consumer_name=%s AND outbox_id=%s
            """,
            (consumer_name, outbox_id),
        ).fetchone()
    return row[0] if row else None


def process_event_envelope(
    *,
    consumer_name: str,
    outbox_id: str,
    topic: str,
    payload: dict,
    run_agents: bool = False,
    radius_km: float = 150.0,
) -> dict:
    """Idempotently process one transported outbox event.

    Both the local PostgreSQL worker and the Aiven Kafka consumer use this
    function. A successful outbox_id is never applied twice by the same
    consumer.
    """
    if consumption_status(
        consumer_name=consumer_name,
        outbox_id=outbox_id,
    ) == "SUCCESS":
        return {
            "outbox_id": outbox_id,
            "topic": topic,
            "status": "DUPLICATE_SKIPPED",
        }

    try:
        result = handle_event(
            topic=topic,
            payload=payload,
            run_agents=run_agents,
            radius_km=radius_km,
        )
        _record_consumption(
            consumer_name=consumer_name,
            outbox_id=outbox_id,
            status="SUCCESS",
            result=result,
        )
        return {
            "outbox_id": outbox_id,
            "topic": topic,
            "status": "SUCCESS",
            "result": result,
        }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _record_consumption(
            consumer_name=consumer_name,
            outbox_id=outbox_id,
            status="ERROR",
            error=error,
        )
        return {
            "outbox_id": outbox_id,
            "topic": topic,
            "status": "ERROR",
            "error": error,
        }


def process_pending_events(
    *,
    consumer_name: str = DEFAULT_CONSUMER,
    limit: int = 50,
    run_agents: bool = False,
    radius_km: float = 150.0,
) -> dict:
    rows = pending_events(
        consumer_name=consumer_name,
        limit=limit,
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        results.append(
            process_event_envelope(
                consumer_name=consumer_name,
                outbox_id=row["outbox_id"],
                topic=row["topic"],
                payload=row["payload"],
                run_agents=run_agents,
                radius_km=radius_km,
            )
        )

    return {
        "consumer_name": consumer_name,
        "attempted": len(rows),
        "succeeded": sum(1 for row in results if row["status"] == "SUCCESS"),
        "failed": sum(1 for row in results if row["status"] == "ERROR"),
        "results": results,
    }
