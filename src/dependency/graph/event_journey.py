"""Trace a public report through the stored event-to-investigation lifecycle.

Read-only. No synthetic transitions, inferred damage, queue dispatch or plan
execution. A locally consumed outbox message is NOT proof of Kafka delivery.
"""
from __future__ import annotations

from dependency.db.connection import connect


def _iso(value):
    return value.isoformat() if value is not None else None


def _step(key, title, status, detail, timestamp=None, reference=None):
    return {
        "key": key, "title": title, "status": status, "detail": detail,
        "timestamp": _iso(timestamp), "reference": reference,
    }


def event_journey(*, event_id: str) -> dict:
    """Return exact database checkpoints for one stored external event."""
    if not event_id or len(event_id) > 180:
        raise ValueError("A valid event ID is required.")

    with connect() as conn:
        event = conn.execute(
            """SELECT event_id,title,source,event_type,mode,
                      occurred_or_effective_at,ingested_at,source_url,
                      provenance_class
               FROM external_events WHERE event_id=%s""",
            (event_id,),
        ).fetchone()
        if not event:
            raise ValueError("Unknown event ID.")

        delivery = conn.execute(
            """SELECT o.outbox_id,o.created_at,o.published_at,
                      c.status,c.processed_at,c.result_json,c.error_text
               FROM event_outbox o
               LEFT JOIN event_consumptions c
                 ON c.outbox_id=o.outbox_id
                AND c.consumer_name='incident-orchestrator'
               WHERE o.topic='external.events' AND o.event_key=%s
               ORDER BY o.created_at,o.outbox_id LIMIT 1""",
            (event_id,),
        ).fetchone()

        incident = conn.execute(
            """SELECT incident_id,status,scenario_id,detected_at,updated_at
               FROM incidents WHERE event_id=%s
               ORDER BY detected_at DESC,incident_id LIMIT 1""",
            (event_id,),
        ).fetchone()

        tasks = (conn.execute(
            """SELECT task_id,task_type,target_type,target_id,status,
                      required_fact,created_at,resolved_at
               FROM incident_investigation_tasks
               WHERE incident_id=%s
               ORDER BY CASE WHEN status='OPEN' THEN 0 ELSE 1 END,
                        created_at,task_id LIMIT 100""",
            (incident[0],),
        ).fetchall() if incident else [])

    outbox_id = delivery[0] if delivery else None
    consumption_status = delivery[3] if delivery else None
    worker_result = (delivery[5] if delivery and isinstance(delivery[5], dict) else {})
    outcome = worker_result.get("result", {}) if isinstance(worker_result, dict) else {}
    worker_outcome = outcome.get("status") if isinstance(outcome, dict) else None
    open_tasks = [t for t in tasks if t[4] == "OPEN"]
    resolved_tasks = [t for t in tasks if t[4] == "RESOLVED"]

    steps = [
        _step("observation", "Source observation", "RECORDED",
              "Report stored with its source, event date and provenance.",
              event[6], event_id),
    ]

    if delivery:
        steps.append(_step(
            "receipt", "First receipt", "RECORDED",
            "One external.events outbox entry was created for this event ID.",
            delivery[1], outbox_id,
        ))
    else:
        steps.append(_step(
            "receipt", "First receipt", "NOT_RECORDED",
            "No external.events outbox receipt is stored for this event.",
        ))

    if consumption_status == "SUCCESS":
        steps.append(_step(
            "processing", "Local triage", "PROCESSED",
            ("Processed without creating an incident: " + worker_outcome.replace("_", " ").lower() + "."
             if worker_outcome in {"NO_NETWORK_EXPOSURE", "NO_BUSINESS_EXPOSURE"}
             else "Local incident worker handled the event. This does not confirm supplier damage."),
            delivery[4], outbox_id,
        ))
    elif consumption_status == "ERROR":
        steps.append(_step(
            "processing", "Local triage", "ERROR",
            "The local worker recorded a processing error; inspect server logs and retry safely.",
            delivery[4], outbox_id,
        ))
    else:
        steps.append(_step(
            "processing", "Local triage", "PENDING" if delivery else "NOT_VERIFIED",
            ("An outbox receipt exists, but successful worker processing is not recorded."
             if delivery else "There is no worker receipt to verify processing."),
        ))

    if incident:
        steps.append(_step(
            "investigation", "Investigation", "OPEN" if incident[1] in {"OPEN", "INVESTIGATING"} else "RECORDED",
            "A case exists. Its stored status is " + incident[1] + ".",
            incident[3], incident[0],
        ))
    else:
        not_exposed = (consumption_status == "SUCCESS" and
                       worker_outcome in {"NO_NETWORK_EXPOSURE", "NO_BUSINESS_EXPOSURE"})
        steps.append(_step(
            "investigation", "Investigation",
            "NOT_REQUIRED" if not_exposed else "NOT_RECORDED",
            ("Local triage found no modeled exposure under its configured rules."
             if not_exposed else "No incident record is linked to this event."),
        ))

    if open_tasks:
        steps.append(_step(
            "evidence", "Operational evidence", "ACTION_REQUIRED",
            str(len(open_tasks)) + " open verification task(s). Public hazard proximity does not prove disruption.",
            open_tasks[0][6], open_tasks[0][0],
        ))
    elif resolved_tasks:
        steps.append(_step(
            "evidence", "Operational evidence", "RECORDED",
            "The listed evidence tasks are resolved. Review their recorded sources before making a decision.",
            resolved_tasks[-1][7], resolved_tasks[-1][0],
        ))
    else:
        steps.append(_step(
            "evidence", "Operational evidence", "NOT_REQUIRED" if not incident else "NOT_RECORDED",
            "No open evidence task is recorded for this event.",
        ))

    scenario_id = incident[2] if incident else None
    if scenario_id:
        steps.append(_step(
            "decision", "Recovery decision", "REVIEW_REQUIRED",
            "An operational scenario is linked. Its data and approvals require independent review.",
            incident[4], scenario_id,
        ))
    else:
        steps.append(_step(
            "decision", "Recovery decision", "BLOCKED",
            "No linked operational scenario. Exposure alone cannot authorize a recovery action.",
        ))

    if consumption_status == "ERROR":
        action = ("CHECK_PROCESSING", "Inspect failed local processing",
                  "Review the worker error and retry without creating duplicate event IDs.")
    elif delivery and consumption_status != "SUCCESS":
        action = ("RUN_LOCAL_WORKER", "Process the pending report",
                  "Run the local incident worker. No supplier messages or AI calls are needed.")
    elif open_tasks:
        action = ("VERIFY_OPERATIONS", "Confirm the missing operational fact",
                  open_tasks[0][5])
    elif scenario_id:
        action = ("REVIEW_SCENARIO", "Review recovery feasibility",
                  "Check confirmed capacity, materials, due dates and approvals.")
    elif not incident:
        action = ("MONITOR_SOURCE", "Continue source monitoring",
                  "No modeled business incident was recorded. Do not infer safety or damage.")
    else:
        action = ("REVIEW_CASE", "Review the investigation",
                  "No open task or confirmed operational scenario is recorded.")

    return {
        "event_id": event[0],
        "event": {
            "title": event[1], "source": event[2], "event_type": event[3],
            "mode": event[4], "occurred_at": _iso(event[5]),
            "database_last_ingested_at": _iso(event[6]),
            "source_url": event[7], "provenance_class": event[8],
        },
        "outbox": {
            "outbox_id": outbox_id,
            "first_recorded_at": _iso(delivery[1]) if delivery else None,
            "kafka_publication_recorded_at": _iso(delivery[2]) if delivery else None,
            "kafka_broker_health": "NOT_VERIFIED",
            "local_processing": consumption_status or ("PENDING" if delivery else "NOT_VERIFIED"),
            "worker_outcome": worker_outcome,
        },
        "incident_id": incident[0] if incident else None,
        "scenario_id": scenario_id,
        "evidence_tasks": [{
            "task_id": t[0], "task_type": t[1], "target_type": t[2],
            "target_id": t[3], "status": t[4], "required_fact": t[5],
            "created_at": _iso(t[6]), "resolved_at": _iso(t[7]),
        } for t in tasks],
        "steps": steps,
        "next_action": {
            "code": action[0], "title": action[1], "description": action[2],
            "task_id": open_tasks[0][0] if open_tasks else None,
        },
        "basis": ("Recorded PostgreSQL facts. Source proximity does not establish "
                  "a closure, a delay or lost revenue. No action has been executed."),
    }
