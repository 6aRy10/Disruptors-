from __future__ import annotations

import json
from uuid import uuid4

from dependency.db.connection import connect
from dependency.events.bus import TOPIC_ACTION_EXECUTED, enqueue_outbox
from dependency.services.state_updates import (
    update_facility_state,
    update_inventory,
    update_purchase_order_eta,
    update_setup_lead_time,
    update_substitution_approval,
)


SUPPORTED_ACTIONS = {
    "RELEASE_SAFETY_STOCK",
    "APPROVE_SUBSTITUTION",
    "UPDATE_PO_ETA",
    "EXPEDITE_PO",
    "UPDATE_SETUP_LEAD_TIME",
    "SET_FACILITY_STATE",
}


def _approval(request_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              request_id,incident_id,scenario_id,plan_record_id,sku,
              action_type,action_payload,status,decided_by,decision_reason
            FROM approval_requests
            WHERE request_id=%s
            """,
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown approval request: {request_id}")

        execution = conn.execute(
            """
            SELECT
              execution_id,status,started_at,completed_at,executed_by,
              result_json,error_text
            FROM action_executions
            WHERE approval_request_id=%s
            """,
            (request_id,),
        ).fetchone()

    return {
        "request_id": row[0],
        "incident_id": row[1],
        "scenario_id": row[2],
        "plan_record_id": row[3],
        "sku": row[4],
        "action_type": row[5],
        "action_payload": row[6] or {},
        "status": row[7],
        "decided_by": row[8],
        "decision_reason": row[9],
        "execution": (
            {
                "execution_id": execution[0],
                "status": execution[1],
                "started_at": execution[2].isoformat() if execution[2] else None,
                "completed_at": execution[3].isoformat() if execution[3] else None,
                "executed_by": execution[4],
                "result": execution[5],
                "error": execution[6],
            }
            if execution
            else None
        ),
    }


def _required(payload: dict, key: str):
    value = payload.get(key)
    if value is None or value == "":
        raise ValueError(f"Action payload is missing required field: {key}")
    return value


def _release_safety_stock(approval: dict) -> dict:
    payload = approval["action_payload"]
    site_id = str(_required(payload, "site_id"))
    item_type = str(payload.get("item_type") or "finished_good")
    item_id = str(payload.get("item_id") or approval.get("sku") or "")
    if not item_id:
        raise ValueError("RELEASE_SAFETY_STOCK requires item_id or approval SKU.")

    units = float(_required(payload, "units"))
    if units <= 0:
        raise ValueError("Safety-stock release units must be > 0.")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT qty_on_hand,qty_reserved,safety_stock
            FROM inventory
            WHERE site_id=%s AND item_type=%s AND item_id=%s
            """,
            (site_id, item_type, item_id),
        ).fetchone()
    if not row:
        raise ValueError(
            f"Unknown inventory row: {site_id}/{item_type}/{item_id}"
        )

    current_safety = float(row[2])
    if units > current_safety:
        raise ValueError(
            f"Cannot release {units:g}; only {current_safety:g} safety-stock "
            "units are protected."
        )

    update = update_inventory(
        site_id=site_id,
        item_type=item_type,
        item_id=item_id,
        qty_on_hand=float(row[0]),
        qty_reserved=float(row[1]),
        safety_stock=current_safety - units,
    )
    return {
        "action": "RELEASE_SAFETY_STOCK",
        "released_units": units,
        "previous_safety_stock_units": current_safety,
        "new_safety_stock_units": current_safety - units,
        "state_update": update,
    }


def _approve_substitution(approval: dict) -> dict:
    payload = approval["action_payload"]
    material_id = str(_required(payload, "material_id"))
    substitute_material_id = str(_required(payload, "substitute_material_id"))
    engineering_status = str(
        payload.get("engineering_status") or "APPROVED_BY_PLANNER"
    )
    update = update_substitution_approval(
        material_id=material_id,
        substitute_material_id=substitute_material_id,
        approved=True,
        engineering_status=engineering_status,
    )
    return {
        "action": "APPROVE_SUBSTITUTION",
        "state_update": update,
    }


def _update_po_eta(approval: dict) -> dict:
    payload = approval["action_payload"]
    po_id = str(_required(payload, "po_id"))
    eta = str(_required(payload, "eta"))
    update = update_purchase_order_eta(
        po_id=po_id,
        eta=eta,
    )
    return {
        "action": approval["action_type"],
        "state_update": update,
    }


def _update_setup_lead_time(approval: dict) -> dict:
    payload = approval["action_payload"]
    sku = str(payload.get("sku") or approval.get("sku") or "")
    if not sku:
        raise ValueError("UPDATE_SETUP_LEAD_TIME requires sku.")
    facility_id = str(_required(payload, "facility_id"))
    setup_lead_days = int(_required(payload, "setup_lead_days"))
    update = update_setup_lead_time(
        sku=sku,
        facility_id=facility_id,
        setup_lead_days=setup_lead_days,
    )
    return {
        "action": "UPDATE_SETUP_LEAD_TIME",
        "state_update": update,
    }


def _set_facility_state(approval: dict) -> dict:
    payload = approval["action_payload"]
    scenario_id = str(
        payload.get("scenario_id") or approval.get("scenario_id") or ""
    )
    if not scenario_id:
        raise ValueError("SET_FACILITY_STATE requires scenario_id.")
    facility_id = str(_required(payload, "facility_id"))
    status = str(_required(payload, "status"))
    capacity_multiplier = float(payload.get("capacity_multiplier", 1.0))
    reason = str(
        payload.get("reason")
        or f"Approved operational action {approval['request_id']}."
    )

    update = update_facility_state(
        scenario_id=scenario_id,
        facility_id=facility_id,
        status=status,
        capacity_multiplier=capacity_multiplier,
        confirmed=True,
        source_type="APPROVED_ACTION_EXECUTION",
        reason=reason,
    )
    return {
        "action": "SET_FACILITY_STATE",
        "state_update": update,
    }


def _run_action(approval: dict) -> dict:
    action = approval["action_type"]
    if action == "RELEASE_SAFETY_STOCK":
        return _release_safety_stock(approval)
    if action == "APPROVE_SUBSTITUTION":
        return _approve_substitution(approval)
    if action in {"UPDATE_PO_ETA", "EXPEDITE_PO"}:
        return _update_po_eta(approval)
    if action == "UPDATE_SETUP_LEAD_TIME":
        return _update_setup_lead_time(approval)
    if action == "SET_FACILITY_STATE":
        return _set_facility_state(approval)
    raise ValueError(
        f"Unsupported executable action_type={action}. "
        f"Supported: {sorted(SUPPORTED_ACTIONS)}"
    )


def execute_approved_action(
    *,
    request_id: str,
    executed_by: str,
) -> dict:
    """Execute one already-approved action with an idempotent audit record.

    Approval and execution are intentionally separate. A model can request an
    approval, but only an approved request can reach this function.
    """
    approval = _approval(request_id)

    if approval["status"] != "APPROVED":
        raise ValueError(
            f"Approval request {request_id} has status={approval['status']}; "
            "only APPROVED requests can execute."
        )

    if approval["action_type"] not in SUPPORTED_ACTIONS:
        raise ValueError(
            f"Action {approval['action_type']} is not executable by the current "
            "deterministic action adapter."
        )

    existing = approval.get("execution")
    if existing:
        if existing["status"] == "SUCCEEDED":
            return {
                "request_id": request_id,
                "execution_id": existing["execution_id"],
                "status": "SUCCEEDED",
                "already_executed": True,
                "result": existing["result"],
            }
        raise ValueError(
            f"Execution already exists with status={existing['status']}. "
            "Manual reconciliation is required before retry."
        )

    execution_id = f"EXEC-{uuid4()}"
    with connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO action_executions(
                  execution_id,approval_request_id,incident_id,action_type,
                  action_payload,status,executed_by
                ) VALUES (%s,%s,%s,%s,%s::jsonb,'RUNNING',%s)
                """,
                (
                    execution_id,
                    request_id,
                    approval["incident_id"],
                    approval["action_type"],
                    json.dumps(approval["action_payload"], default=str),
                    executed_by,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            refreshed = _approval(request_id).get("execution")
            if refreshed and refreshed["status"] == "SUCCEEDED":
                return {
                    "request_id": request_id,
                    "execution_id": refreshed["execution_id"],
                    "status": "SUCCEEDED",
                    "already_executed": True,
                    "result": refreshed["result"],
                }
            raise

    try:
        result = _run_action(approval)
    except Exception as exc:
        with connect() as conn:
            conn.execute(
                """
                UPDATE action_executions
                SET status='FAILED',completed_at=now(),error_text=%s
                WHERE execution_id=%s
                """,
                (f"{type(exc).__name__}: {exc}", execution_id),
            )
            conn.commit()
        raise

    with connect() as conn:
        conn.execute(
            """
            UPDATE action_executions
            SET status='SUCCEEDED',completed_at=now(),result_json=%s::jsonb,
                error_text=NULL
            WHERE execution_id=%s
            """,
            (json.dumps(result, default=str), execution_id),
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_ACTION_EXECUTED,
            event_key=execution_id,
            payload={
                "execution_id": execution_id,
                "approval_request_id": request_id,
                "incident_id": approval["incident_id"],
                "scenario_id": approval["scenario_id"],
                "sku": approval["sku"],
                "action_type": approval["action_type"],
                "executed_by": executed_by,
                "result": result,
            },
        )
        conn.commit()

    return {
        "request_id": request_id,
        "execution_id": execution_id,
        "status": "SUCCEEDED",
        "already_executed": False,
        "action_type": approval["action_type"],
        "result": result,
    }


def list_action_executions(
    *,
    incident_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              execution_id,approval_request_id,incident_id,action_type,
              action_payload,status,started_at,completed_at,executed_by,
              result_json,error_text
            FROM action_executions
            WHERE (%s::text IS NULL OR incident_id=%s::text)
            ORDER BY started_at DESC,execution_id
            LIMIT %s
            """,
            (incident_id, incident_id, int(limit)),
        ).fetchall()

    return [
        {
            "execution_id": r[0],
            "approval_request_id": r[1],
            "incident_id": r[2],
            "action_type": r[3],
            "action_payload": r[4],
            "status": r[5],
            "started_at": r[6].isoformat() if r[6] else None,
            "completed_at": r[7].isoformat() if r[7] else None,
            "executed_by": r[8],
            "result": r[9],
            "error": r[10],
        }
        for r in rows
    ]
