"""Reconcile pre-existing live incidents created before evidence tasks existed.

Default is read-only preview. --apply creates only missing investigation tasks.
Never resets data, publishes events, contacts suppliers or confirms disruption.
"""
from __future__ import annotations

import argparse
import json

from dependency.db.connection import connect
from dependency.incidents.triage import triage_event
from dependency.investigation.tasks import create_investigation_tasks


def candidates(
    *, event_id: str | None = None, include_non_live: bool = False, limit: int = 100
) -> list[dict]:
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    with connect() as conn:
        rows=conn.execute(
            """
            SELECT i.incident_id,i.event_id,e.mode
            FROM incidents i
            JOIN external_events e ON e.event_id=i.event_id
            WHERE i.status IN ('OPEN','INVESTIGATING')
              AND i.scenario_id IS NULL
              AND (%s OR e.mode='LIVE')
              AND (%s::text IS NULL OR i.event_id=%s)
              AND NOT EXISTS (
                 SELECT 1 FROM incident_investigation_tasks t
                 WHERE t.incident_id=i.incident_id
              )
            ORDER BY i.detected_at,i.incident_id
            LIMIT %s
            """,
            (include_non_live,event_id,event_id,limit),
        ).fetchall()
    return [
        {"incident_id":row[0],"event_id":row[1],"mode":row[2]}
        for row in rows
    ]


def reconcile(
    *, event_id: str | None = None, apply: bool = False,
    include_non_live: bool = False, radius_km: float = 150.0,
    limit: int = 100,
) -> dict:
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    rows=candidates(event_id=event_id,include_non_live=include_non_live,limit=limit)
    result={
        "status":"APPLIED" if apply else "PREVIEW_ONLY",
        "candidate_incidents":len(rows),
        "created_task_count":0,
        "incidents":[],
        "effects":{
            "reset_database":False,
            "send_supplier_messages":False,
            "change_private_operational_state":False,
            "publish_events":False,
            "invoke_paid_agents":False,
        },
    }
    for row in rows:
        entry=dict(row)
        if not apply:
            entry["result"]="NOT_CHANGED"
        else:
            try:
                triage=triage_event(event_id=row["event_id"],radius_km=radius_km)
                incident=triage.get("incident")
                if not incident or incident["incident_id"]!=row["incident_id"]:
                    entry["result"]="SKIPPED_IDENTITY_OR_CURRENT_EXPOSURE_MISMATCH"
                elif triage.get("scenario_id") is not None:
                    entry["result"]="SKIPPED_OPERATIONAL_SCENARIO_PRESENT"
                else:
                    created=create_investigation_tasks(
                        incident_id=row["incident_id"],triage=triage,
                    )
                    entry["result"]="TASKS_CREATED" if created else "NO_EVIDENCE_TASKS_PROPOSED"
                    entry["task_count"]=len(created)
                    entry["task_types"]=sorted({t["task_type"] for t in created})
                    result["created_task_count"]+=len(created)
            except Exception as exc:
                # Do not print raw database/provider exceptions or credentials.
                entry["result"]="ERROR"
                entry["error_type"]=type(exc).__name__
                result["status"]="PARTIAL_FAILURE"
        result["incidents"].append(entry)
    return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true",
                        help="Create missing tasks for eligible existing incidents.")
    parser.add_argument("--event-id",default=None)
    parser.add_argument("--include-non-live",action="store_true",
                        help="Also include open REPLAY and policy incidents.")
    parser.add_argument("--radius-km",type=float,default=150.0)
    parser.add_argument("--limit",type=int,default=100)
    args=parser.parse_args()
    result=reconcile(
        event_id=args.event_id,apply=args.apply,
        include_non_live=args.include_non_live,
        radius_km=args.radius_km,limit=args.limit,
    )
    print(json.dumps(result,indent=2))
    return 1 if result["status"]=="PARTIAL_FAILURE" else 0


if __name__=="__main__":
    raise SystemExit(main())
