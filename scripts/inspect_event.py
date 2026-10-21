"""Inspect one real event across public evidence, private graph, and event queue."""
from __future__ import annotations

import argparse
import json

from dependency.db.connection import connect
from dependency.graph.event_impact import trace_business_event_impact


def inspect_event(event_id: str, *, radius_km: float = 150.0) -> dict:
    """Read-only diagnostic. Never infer damage from proximity."""
    with connect() as conn:
        event = conn.execute(
            """
            SELECT event_id,event_type,source,mode,provenance_class,
                   occurred_or_effective_at,ingested_at
            FROM external_events WHERE event_id=%s
            """,
            (event_id,),
        ).fetchone()
        if event is None:
            return {"event_id": event_id, "status": "EVENT_NOT_FOUND"}

        outbox = conn.execute(
            """
            SELECT c.status, o.outbox_id,
                   CASE WHEN c.status='ERROR' THEN split_part(c.error_text, ':', 1) ELSE NULL END
            FROM event_outbox o
            LEFT JOIN event_consumptions c
              ON c.outbox_id=o.outbox_id
             AND c.consumer_name='incident-orchestrator'
            WHERE o.topic='external.events' AND o.event_key=%s
            ORDER BY o.created_at DESC,o.outbox_id DESC
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        incident = conn.execute(
            """
            SELECT incident_id,status,scenario_id
            FROM incidents
            WHERE event_id=%s
            ORDER BY detected_at DESC,incident_id DESC
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()

    impact = trace_business_event_impact(event_id=event_id, radius_km=radius_km)
    products = impact.get("products") or []
    paths = impact.get("dependency_paths") or []
    facilities = impact.get("facilities") or impact.get("public_facilities") or []
    return {
        "event_id": event_id,
        "event": {
            "type": event[1],
            "source": event[2],
            "mode": event[3],
            "provenance_class": event[4],
            "occurred_at": event[5].isoformat() if event[5] else None,
            "ingested_at": event[6].isoformat() if event[6] else None,
        },
        "event_queue": {
            "status": outbox[0] or "PENDING" if outbox else "NO_OUTBOX_EVENT",
            "outbox_id": outbox[1] if outbox else None,
            "error_type": outbox[2] if outbox else None,
        },
        "incident": ({
            "incident_id": incident[0], "status": incident[1],
            "scenario_id": incident[2],
        } if incident else None),
        "business_exposure": {
            "basis": impact.get("exposure_basis"),
            "status": impact.get("exposure_status"),
            "connected_facility_count": len(facilities),
            "dependency_path_count": len(paths),
            "connected_product_count": len(products),
            "sample_skus": [p["sku"] for p in products[:10]],
            "connected_value": impact.get("totals", {}),
        },
        "next_evidence": (
            "Confirm private facility/route state and supplier capacity before claiming disruption."
            if products else
            "No explicit product exposure found; public proximity alone is not private business impact."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id", help="Existing external event ID, e.g. GDACS-WF-1032942")
    parser.add_argument("--radius-km", type=float, default=150.0)
    args = parser.parse_args()
    if args.radius_km <= 0:
        parser.error("radius-km must be positive")
    result = inspect_event(args.event_id, radius_km=args.radius_km)
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "EVENT_NOT_FOUND" else 0


if __name__ == "__main__":
    raise SystemExit(main())
