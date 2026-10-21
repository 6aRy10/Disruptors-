from __future__ import annotations

import json
from uuid import uuid4

from dependency.db.connection import connect
from dependency.events.bus import (
    TOPIC_DECISION_CONFIRMED,
    TOPIC_INCIDENT_DETECTED,
    TOPIC_PLAN_GENERATED,
    enqueue_outbox,
)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def ensure_incident(
    *,
    event_id: str,
    scenario_id: str | None,
    summary: str,
    initial_assessment: str | None = None,
    provenance_class: str = "SIMULATED_PRIVATE",
) -> dict:
    with connect() as conn:
        event = conn.execute(
            "SELECT event_type FROM external_events WHERE event_id = %s",
            (event_id,),
        ).fetchone()
        if not event:
            raise ValueError(f"Unknown event_id: {event_id}")

        existing = conn.execute(
            """
            SELECT incident_id,status,detected_at,updated_at
            FROM incidents
            WHERE event_id = %s
              AND scenario_id IS NOT DISTINCT FROM %s
              AND status IN ('OPEN','INVESTIGATING')
            ORDER BY detected_at DESC
            LIMIT 1
            """,
            (event_id, scenario_id),
        ).fetchone()

        if existing:
            return {
                "incident_id": existing[0],
                "status": existing[1],
                "detected_at": existing[2].isoformat(),
                "updated_at": existing[3].isoformat(),
                "created": False,
            }

        incident_id = _id("INC")
        row = conn.execute(
            """
            INSERT INTO incidents(
              incident_id,event_id,scenario_id,event_type,status,summary,
              initial_assessment,provenance_class
            ) VALUES (%s,%s,%s,%s,'INVESTIGATING',%s,%s,%s)
            RETURNING detected_at,updated_at
            """,
            (
                incident_id,
                event_id,
                scenario_id,
                event[0],
                summary,
                initial_assessment,
                provenance_class,
            ),
        ).fetchone()
        enqueue_outbox(
            conn,
            topic=TOPIC_INCIDENT_DETECTED,
            event_key=incident_id,
            payload={
                "incident_id": incident_id,
                "event_id": event_id,
                "scenario_id": scenario_id,
                "event_type": event[0],
                "status": "INVESTIGATING",
                "provenance_class": provenance_class,
            },
        )
        conn.commit()

    return {
        "incident_id": incident_id,
        "status": "INVESTIGATING",
        "detected_at": row[0].isoformat(),
        "updated_at": row[1].isoformat(),
        "created": True,
    }


def record_evidence(
    *,
    incident_id: str,
    evidence_type: str,
    fact: dict,
    provenance_class: str,
    source_name: str | None = None,
    source_url: str | None = None,
    confidence: float | None = None,
) -> dict:
    evidence_id = _id("EVD")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO incident_evidence(
              evidence_id,incident_id,evidence_type,source_name,source_url,
              fact_json,confidence,provenance_class
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
            """,
            (
                evidence_id,
                incident_id,
                evidence_type,
                source_name,
                source_url,
                json.dumps(fact, default=str),
                confidence,
                provenance_class,
            ),
        )
        conn.execute(
            "UPDATE incidents SET updated_at = now() WHERE incident_id = %s",
            (incident_id,),
        )
        conn.commit()
    return {"evidence_id": evidence_id, "incident_id": incident_id}


def record_agent_run(
    *,
    incident_id: str,
    agent_name: str,
    model: str,
    output_text: str,
    tool_trace: list[dict],
    state_version: int | None = None,
) -> dict:
    run_id = _id("ARUN")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_runs(
              run_id,incident_id,agent_name,model,output_text,tool_trace,state_version
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
            """,
            (
                run_id,
                incident_id,
                agent_name,
                model,
                output_text,
                json.dumps(tool_trace, default=str),
                state_version,
            ),
        )
        conn.execute(
            "UPDATE incidents SET updated_at = now() WHERE incident_id = %s",
            (incident_id,),
        )
        conn.commit()
    return {"run_id": run_id, "incident_id": incident_id}


def save_plan_snapshot(
    *,
    incident_id: str,
    state_version: int,
    sku: str,
    plan: dict,
) -> dict:
    plan_record_id = _id("PLANREC")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO incident_plan_history(
              plan_record_id,incident_id,state_version,sku,plan_id,decision,reasons,metrics
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
            """,
            (
                plan_record_id,
                incident_id,
                state_version,
                sku,
                plan.get("plan_id"),
                plan.get("decision", "UNKNOWN"),
                json.dumps(plan.get("reasons", []), default=str),
                json.dumps(plan.get("evidence", {}), default=str),
            ),
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_PLAN_GENERATED,
            event_key=plan_record_id,
            payload={
                "plan_record_id": plan_record_id,
                "incident_id": incident_id,
                "state_version": state_version,
                "sku": sku,
                "plan_id": plan.get("plan_id"),
                "decision": plan.get("decision", "UNKNOWN"),
                "reasons": plan.get("reasons", []),
            },
        )
        conn.commit()
    return {"plan_record_id": plan_record_id, "incident_id": incident_id}


def record_decision(
    *,
    incident_id: str,
    action: str,
    reason: str,
    approved_by: str,
    plan_record_id: str | None = None,
    outcome: dict | None = None,
) -> dict:
    decision_id = _id("DEC")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO incident_decisions(
              decision_id,incident_id,plan_record_id,action,approved_by,reason,outcome_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                decision_id,
                incident_id,
                plan_record_id,
                action,
                approved_by,
                reason,
                json.dumps(outcome or {}, default=str),
            ),
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_DECISION_CONFIRMED,
            event_key=decision_id,
            payload={
                "decision_id": decision_id,
                "incident_id": incident_id,
                "plan_record_id": plan_record_id,
                "action": action,
                "approved_by": approved_by,
                "reason": reason,
            },
        )
        conn.commit()
    return {"decision_id": decision_id, "incident_id": incident_id}


def close_incident(
    *,
    incident_id: str,
    actual_supplier_delay_days: float | None,
    actual_shortage_units: float | None,
    actual_cost_eur: float | None,
    customer_impact: dict,
    success: bool,
    lesson: str,
) -> dict:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO incident_outcomes(
              incident_id,actual_supplier_delay_days,actual_shortage_units,
              actual_cost_eur,customer_impact_json,success,lesson
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT (incident_id) DO UPDATE SET
              actual_supplier_delay_days=EXCLUDED.actual_supplier_delay_days,
              actual_shortage_units=EXCLUDED.actual_shortage_units,
              actual_cost_eur=EXCLUDED.actual_cost_eur,
              customer_impact_json=EXCLUDED.customer_impact_json,
              success=EXCLUDED.success,
              lesson=EXCLUDED.lesson,
              updated_at=now()
            """,
            (
                incident_id,
                actual_supplier_delay_days,
                actual_shortage_units,
                actual_cost_eur,
                json.dumps(customer_impact, default=str),
                success,
                lesson,
            ),
        )
        conn.execute(
            """
            UPDATE incidents
            SET status='CLOSED',updated_at=now()
            WHERE incident_id=%s
            """,
            (incident_id,),
        )
        conn.commit()
    return {"incident_id": incident_id, "status": "CLOSED"}


def similar_incidents(*, event_type: str, limit: int = 5) -> list[dict]:
    """Retrieve same-type closed incidents as hypotheses, never current proof."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              i.incident_id,i.event_id,i.summary,o.actual_supplier_delay_days,
              o.actual_shortage_units,o.actual_cost_eur,o.success,o.lesson
            FROM incidents i
            JOIN incident_outcomes o ON o.incident_id = i.incident_id
            WHERE i.event_type = %s AND i.status = 'CLOSED'
            ORDER BY o.updated_at DESC
            LIMIT %s
            """,
            (event_type, int(limit)),
        ).fetchall()

    return [
        {
            "incident_id": r[0],
            "event_id": r[1],
            "summary": r[2],
            "actual_supplier_delay_days": float(r[3]) if r[3] is not None else None,
            "actual_shortage_units": float(r[4]) if r[4] is not None else None,
            "actual_cost_eur": float(r[5]) if r[5] is not None else None,
            "success": r[6],
            "lesson": r[7],
            "usage_rule": "HYPOTHESIS_ONLY_RECHECK_CURRENT_STATE",
        }
        for r in rows
    ]


def get_incident_memory(incident_id: str) -> dict:
    with connect() as conn:
        incident = conn.execute(
            """
            SELECT incident_id,event_id,scenario_id,event_type,status,summary,
                   initial_assessment,detected_at,updated_at,provenance_class
            FROM incidents
            WHERE incident_id = %s
            """,
            (incident_id,),
        ).fetchone()
        if not incident:
            raise ValueError(f"Unknown incident_id: {incident_id}")

        evidence = conn.execute(
            """
            SELECT evidence_id,evidence_type,source_name,source_url,fact_json,
                   confidence,observed_at,provenance_class
            FROM incident_evidence
            WHERE incident_id = %s
            ORDER BY observed_at,evidence_id
            """,
            (incident_id,),
        ).fetchall()

        plans = conn.execute(
            """
            SELECT plan_record_id,state_version,sku,plan_id,decision,reasons,metrics,created_at
            FROM incident_plan_history
            WHERE incident_id = %s
            ORDER BY created_at,plan_record_id
            """,
            (incident_id,),
        ).fetchall()

        decisions = conn.execute(
            """
            SELECT decision_id,plan_record_id,action,approved_by,reason,made_at,outcome_json
            FROM incident_decisions
            WHERE incident_id = %s
            ORDER BY made_at,decision_id
            """,
            (incident_id,),
        ).fetchall()

        approvals = conn.execute(
            """
            SELECT
              request_id,scenario_id,plan_record_id,sku,action_type,action_payload,
              reason,requested_by,status,requested_at,decided_at,decided_by,
              decision_reason
            FROM approval_requests
            WHERE incident_id=%s
            ORDER BY requested_at,request_id
            """,
            (incident_id,),
        ).fetchall()

        runs = conn.execute(
            """
            SELECT run_id,agent_name,model,output_text,tool_trace,state_version,created_at
            FROM agent_runs
            WHERE incident_id = %s
            ORDER BY created_at,run_id
            """,
            (incident_id,),
        ).fetchall()

        outcome = conn.execute(
            """
            SELECT actual_supplier_delay_days,actual_shortage_units,actual_cost_eur,
                   customer_impact_json,success,lesson,updated_at
            FROM incident_outcomes
            WHERE incident_id = %s
            """,
            (incident_id,),
        ).fetchone()

    return {
        "incident": {
            "incident_id": incident[0],
            "event_id": incident[1],
            "scenario_id": incident[2],
            "event_type": incident[3],
            "status": incident[4],
            "summary": incident[5],
            "initial_assessment": incident[6],
            "detected_at": incident[7].isoformat(),
            "updated_at": incident[8].isoformat(),
            "provenance_class": incident[9],
        },
        "evidence": [
            {
                "evidence_id": r[0],
                "evidence_type": r[1],
                "source_name": r[2],
                "source_url": r[3],
                "fact": r[4],
                "confidence": float(r[5]) if r[5] is not None else None,
                "observed_at": r[6].isoformat(),
                "provenance_class": r[7],
            }
            for r in evidence
        ],
        "plans": [
            {
                "plan_record_id": r[0],
                "state_version": int(r[1]),
                "sku": r[2],
                "plan_id": r[3],
                "decision": r[4],
                "reasons": r[5],
                "metrics": r[6],
                "created_at": r[7].isoformat(),
            }
            for r in plans
        ],
        "decisions": [
            {
                "decision_id": r[0],
                "plan_record_id": r[1],
                "action": r[2],
                "approved_by": r[3],
                "reason": r[4],
                "made_at": r[5].isoformat(),
                "outcome": r[6],
            }
            for r in decisions
        ],
        "approvals": [
            {
                "request_id": r[0],
                "scenario_id": r[1],
                "plan_record_id": r[2],
                "sku": r[3],
                "action_type": r[4],
                "action_payload": r[5],
                "reason": r[6],
                "requested_by": r[7],
                "status": r[8],
                "requested_at": r[9].isoformat(),
                "decided_at": r[10].isoformat() if r[10] else None,
                "decided_by": r[11],
                "decision_reason": r[12],
            }
            for r in approvals
        ],
        "agent_runs": [
            {
                "run_id": r[0],
                "agent_name": r[1],
                "model": r[2],
                "output_text": r[3],
                "tool_trace": r[4],
                "state_version": int(r[5]) if r[5] is not None else None,
                "created_at": r[6].isoformat(),
            }
            for r in runs
        ],
        "outcome": (
            {
                "actual_supplier_delay_days": float(outcome[0]) if outcome[0] is not None else None,
                "actual_shortage_units": float(outcome[1]) if outcome[1] is not None else None,
                "actual_cost_eur": float(outcome[2]) if outcome[2] is not None else None,
                "customer_impact": outcome[3],
                "success": outcome[4],
                "lesson": outcome[5],
                "updated_at": outcome[6].isoformat(),
            }
            if outcome
            else None
        ),
    }
