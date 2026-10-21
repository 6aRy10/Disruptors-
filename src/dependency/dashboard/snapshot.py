from __future__ import annotations

from dependency.db.connection import connect
from dependency.graph.event_impact import trace_business_event_impact
from dependency.graph.network import list_network_facilities, network_stats
from dependency.ingest.events import list_recent_events
from dependency.services.approvals import list_approval_requests
from dependency.services.execution import list_action_executions
from dependency.solver.portfolio import plan_event_recovery


ACTIVE_SUPPLIER_REQUEST_STATUSES = (
    "DRAFT",
    "PENDING_DISPATCH",
    "SENT",
    "REPLY_RECEIVED",
    "PARSE_FAILED",
)


def _state_version() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT version FROM operational_state_version WHERE singleton=true"
        ).fetchone()
    return int(row[0]) if row else 0


def _open_incidents(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              incident_id,event_id,scenario_id,event_type,status,summary,
              detected_at,updated_at,provenance_class
            FROM incidents
            WHERE status IN ('OPEN','INVESTIGATING')
            ORDER BY updated_at DESC,detected_at DESC
            LIMIT %s
            """,
            (int(limit),),
        ).fetchall()
    return [
        {
            "incident_id": r[0],
            "event_id": r[1],
            "scenario_id": r[2],
            "event_type": r[3],
            "status": r[4],
            "summary": r[5],
            "detected_at": r[6].isoformat() if r[6] else None,
            "updated_at": r[7].isoformat() if r[7] else None,
            "provenance_class": r[8],
        }
        for r in rows
    ]


def _approved_unexecuted(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              a.request_id,a.incident_id,a.scenario_id,a.plan_record_id,a.sku,
              a.action_type,a.action_payload,a.reason,a.decided_by,
              a.decision_reason,a.decided_at
            FROM approval_requests a
            LEFT JOIN action_executions x
              ON x.approval_request_id=a.request_id
            WHERE a.status='APPROVED'
              AND x.execution_id IS NULL
            ORDER BY a.decided_at DESC,a.request_id
            LIMIT %s
            """,
            (int(limit),),
        ).fetchall()
    return [
        {
            "request_id": r[0],
            "incident_id": r[1],
            "scenario_id": r[2],
            "plan_record_id": r[3],
            "sku": r[4],
            "action_type": r[5],
            "action_payload": r[6],
            "reason": r[7],
            "decided_by": r[8],
            "decision_reason": r[9],
            "decided_at": r[10].isoformat() if r[10] else None,
            "status": "APPROVED_AWAITING_EXECUTION",
        }
        for r in rows
    ]


def _supplier_requests(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              r.request_id,r.incident_id,r.scenario_id,r.facility_id,f.name,
              r.sku,r.field_requested,r.status,r.requested_at,r.sent_at,
              r.replied_at,r.confirmed_at,r.last_error,r.provenance_class
            FROM supplier_confirmation_requests r
            JOIN facilities f ON f.facility_id=r.facility_id
            WHERE r.status=ANY(%s)
            ORDER BY r.requested_at DESC,r.request_id
            LIMIT %s
            """,
            (list(ACTIVE_SUPPLIER_REQUEST_STATUSES), int(limit)),
        ).fetchall()
    return [
        {
            "request_id": r[0],
            "incident_id": r[1],
            "scenario_id": r[2],
            "facility_id": r[3],
            "facility_name": r[4],
            "sku": r[5],
            "field_requested": r[6],
            "status": r[7],
            "requested_at": r[8].isoformat() if r[8] else None,
            "sent_at": r[9].isoformat() if r[9] else None,
            "replied_at": r[10].isoformat() if r[10] else None,
            "confirmed_at": r[11].isoformat() if r[11] else None,
            "last_error": r[12],
            "provenance_class": r[13],
        }
        for r in rows
    ]


def _scenario_for_event(event_id: str | None) -> str | None:
    if not event_id:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT scenario_id
            FROM scenarios
            WHERE event_id=%s
            ORDER BY
              CASE WHEN mode='LIVE' THEN 0 ELSE 1 END,
              as_of DESC,
              scenario_id
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
    return row[0] if row else None


def _selected_event_id(
    requested_event_id: str | None,
    events: list[dict],
) -> str | None:
    if requested_event_id:
        return requested_event_id

    # Prefer an event already linked to a scenario because it can show the
    # complete event -> impact -> recovery loop without mutating state.
    with connect() as conn:
        row = conn.execute(
            """
            SELECT e.event_id
            FROM external_events e
            JOIN scenarios s ON s.event_id=e.event_id
            ORDER BY
              CASE WHEN e.mode='LIVE' THEN 0
                   WHEN e.mode='ACTIVE_POLICY' THEN 1
                   ELSE 2 END,
              e.ingested_at DESC,
              e.event_id
            LIMIT 1
            """
        ).fetchone()
    if row:
        return row[0]

    return events[0]["event_id"] if events else None


def dashboard_snapshot(
    *,
    event_id: str | None = None,
    scenario_id: str | None = None,
    radius_km: float = 150.0,
) -> dict:
    """Return one side-effect-free judge dashboard payload."""
    events = list_recent_events(limit=50)
    selected_event_id = _selected_event_id(event_id, events)
    selected_scenario_id = scenario_id or _scenario_for_event(selected_event_id)

    impact = None
    portfolio = None
    error = None

    if selected_event_id:
        try:
            impact = trace_business_event_impact(
                event_id=selected_event_id,
                radius_km=radius_km,
            )
        except ValueError as exc:
            error = str(exc)

    if selected_event_id and selected_scenario_id:
        try:
            portfolio = plan_event_recovery(
                event_id=selected_event_id,
                scenario_id=selected_scenario_id,
                radius_km=radius_km,
            )
        except ValueError as exc:
            error = str(exc)

    open_incidents = _open_incidents()
    pending_approvals = list_approval_requests(
        status="PENDING",
        incident_id=None,
        limit=100,
    )
    supplier_requests = _supplier_requests()
    approved_unexecuted = _approved_unexecuted()
    executions = list_action_executions(limit=25)

    metrics = {
        "state_version": _state_version(),
        "open_incidents": len(open_incidents),
        "pending_approvals": len(pending_approvals),
        "approved_actions_waiting_execution": len(approved_unexecuted),
        "active_supplier_requests": len(supplier_requests),
        "selected_event_products": (
            len((impact or {}).get("products", []))
            if impact
            else 0
        ),
        "selected_event_revenue_eur": float(
            ((impact or {}).get("totals") or {}).get("revenue_eur") or 0
        ),
        "selected_event_margin_eur": float(
            ((impact or {}).get("totals") or {}).get("gross_margin_eur") or 0
        ),
        "selected_event_shortage_units": float(
            ((portfolio or {}).get("summary") or {}).get(
                "total_conservative_shortage_units"
            )
            or 0
        ),
    }

    return {
        "metrics": metrics,
        "network": {
            "stats": network_stats(),
            "facilities": list_network_facilities(
                business_linked_only=False,
                limit=5000,
            ),
        },
        "events": events,
        "selected": {
            "event_id": selected_event_id,
            "scenario_id": selected_scenario_id,
            "radius_km": radius_km,
            "impact": impact,
            "portfolio": portfolio,
            "error": error,
        },
        "operations": {
            "open_incidents": open_incidents,
            "pending_approvals": pending_approvals,
            "approved_actions_waiting_execution": approved_unexecuted,
            "executions": executions,
            "supplier_requests": supplier_requests,
        },
        "truth_model": {
            "VERIFIED_PUBLIC": (
                "Direct public source fact. Examples: event identity, public "
                "supplier disclosure, public policy text."
            ),
            "PUBLIC_DERIVED": (
                "Calculated or matched from public facts. Examples: PostGIS "
                "distance and public-network entity resolution."
            ),
            "INFERRED": (
                "Hypothesis only. It must not be treated as operational truth."
            ),
            "SIMULATED_PRIVATE": (
                "Realistic private ERP/BOM/order/capacity data created because "
                "the real company data is not public."
            ),
        },
        "claim_rules": [
            "Geographic proximity is potential exposure, not proof of shutdown.",
            "A public port event affects business only through an explicit private transport lane.",
            "A trade-policy event requires origin/destination and product-classification checks.",
            "LLMs may propose or investigate. Deterministic code decides arithmetic and feasibility.",
            "A pending supplier reply or human approval cannot mutate operational state.",
        ],
    }
