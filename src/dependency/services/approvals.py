from __future__ import annotations

import json
from uuid import uuid4

from dependency.db.connection import connect
from dependency.events.bus import (
    TOPIC_APPROVAL_REQUESTED,
    TOPIC_DECISION_CONFIRMED,
    enqueue_outbox,
)


def request_human_approval(
    *,
    incident_id: str,
    scenario_id: str | None,
    sku: str | None,
    action_type: str,
    action_payload: dict,
    reason: str,
    requested_by: str = "Recovery Planner",
    plan_record_id: str | None = None,
) -> dict:
    request_id = f"APR-{uuid4()}"

    with connect() as conn:
        incident = conn.execute(
            "SELECT 1 FROM incidents WHERE incident_id=%s",
            (incident_id,),
        ).fetchone()
        if not incident:
            raise ValueError(f"Unknown incident_id: {incident_id}")

        if scenario_id:
            scenario = conn.execute(
                "SELECT 1 FROM scenarios WHERE scenario_id=%s",
                (scenario_id,),
            ).fetchone()
            if not scenario:
                raise ValueError(f"Unknown scenario_id: {scenario_id}")

        if plan_record_id:
            plan = conn.execute(
                """
                SELECT 1
                FROM incident_plan_history
                WHERE plan_record_id=%s AND incident_id=%s
                """,
                (plan_record_id, incident_id),
            ).fetchone()
            if not plan:
                raise ValueError(
                    f"Unknown plan_record_id for incident: {plan_record_id}"
                )

        conn.execute(
            """
            INSERT INTO approval_requests(
              request_id,incident_id,scenario_id,plan_record_id,sku,
              action_type,action_payload,reason,requested_by,status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,'PENDING')
            """,
            (
                request_id,
                incident_id,
                scenario_id,
                plan_record_id,
                sku,
                action_type,
                json.dumps(action_payload, default=str),
                reason,
                requested_by,
            ),
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_APPROVAL_REQUESTED,
            event_key=request_id,
            payload={
                "request_id": request_id,
                "incident_id": incident_id,
                "scenario_id": scenario_id,
                "plan_record_id": plan_record_id,
                "sku": sku,
                "action_type": action_type,
                "action_payload": action_payload,
                "reason": reason,
                "requested_by": requested_by,
                "status": "PENDING",
            },
        )
        conn.commit()

    return {
        "request_id": request_id,
        "incident_id": incident_id,
        "scenario_id": scenario_id,
        "plan_record_id": plan_record_id,
        "sku": sku,
        "action_type": action_type,
        "action_payload": action_payload,
        "reason": reason,
        "requested_by": requested_by,
        "status": "PENDING",
    }


def list_approval_requests(
    *,
    status: str | None = "PENDING",
    incident_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    status_value = status.upper() if status else None
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              request_id,incident_id,scenario_id,plan_record_id,sku,
              action_type,action_payload,reason,requested_by,status,
              requested_at,decided_at,decided_by,decision_reason
            FROM approval_requests
            WHERE (%s IS NULL OR status=%s)
              AND (%s IS NULL OR incident_id=%s)
            ORDER BY requested_at,request_id
            LIMIT %s
            """,
            (
                status_value,
                status_value,
                incident_id,
                incident_id,
                int(limit),
            ),
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
            "requested_by": r[8],
            "status": r[9],
            "requested_at": r[10].isoformat(),
            "decided_at": r[11].isoformat() if r[11] else None,
            "decided_by": r[12],
            "decision_reason": r[13],
        }
        for r in rows
    ]


def decide_approval(
    *,
    request_id: str,
    decision: str,
    decided_by: str,
    decision_reason: str,
) -> dict:
    decision = decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("decision must be APPROVED or REJECTED")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              incident_id,scenario_id,plan_record_id,sku,action_type,
              action_payload,reason,status
            FROM approval_requests
            WHERE request_id=%s
            FOR UPDATE
            """,
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown approval request: {request_id}")

        if row[7] != "PENDING":
            existing = conn.execute(
                """
                SELECT status,decided_at,decided_by,decision_reason
                FROM approval_requests
                WHERE request_id=%s
                """,
                (request_id,),
            ).fetchone()
            return {
                "request_id": request_id,
                "status": existing[0],
                "decided_at": existing[1].isoformat() if existing[1] else None,
                "decided_by": existing[2],
                "decision_reason": existing[3],
                "changed": False,
            }

        conn.execute(
            """
            UPDATE approval_requests
            SET status=%s,decided_at=now(),decided_by=%s,decision_reason=%s
            WHERE request_id=%s
            """,
            (decision, decided_by, decision_reason, request_id),
        )

        decision_id = f"DEC-{uuid4()}"
        outcome = {
            "approval_request_id": request_id,
            "approval_status": decision,
            "scenario_id": row[1],
            "sku": row[3],
            "action_type": row[4],
            "action_payload": row[5],
        }
        conn.execute(
            """
            INSERT INTO incident_decisions(
              decision_id,incident_id,plan_record_id,action,approved_by,
              reason,outcome_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                decision_id,
                row[0],
                row[2],
                f"{decision}:{row[4]}",
                decided_by,
                decision_reason,
                json.dumps(outcome, default=str),
            ),
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_DECISION_CONFIRMED,
            event_key=decision_id,
            payload={
                "decision_id": decision_id,
                "approval_request_id": request_id,
                "incident_id": row[0],
                "plan_record_id": row[2],
                "sku": row[3],
                "action_type": row[4],
                "decision": decision,
                "decided_by": decided_by,
                "decision_reason": decision_reason,
            },
        )
        conn.commit()

        decided = conn.execute(
            """
            SELECT decided_at
            FROM approval_requests
            WHERE request_id=%s
            """,
            (request_id,),
        ).fetchone()

    return {
        "request_id": request_id,
        "decision_id": decision_id,
        "incident_id": row[0],
        "scenario_id": row[1],
        "plan_record_id": row[2],
        "sku": row[3],
        "action_type": row[4],
        "action_payload": row[5],
        "status": decision,
        "decided_at": decided[0].isoformat(),
        "decided_by": decided_by,
        "decision_reason": decision_reason,
        "changed": True,
        "execution_status": "APPROVAL_RECORDED_ACTION_NOT_EXECUTED",
    }
