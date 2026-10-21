"""Data-driven investigations for live signals without confirmed private state.

An investigation task is an evidence gap, not a confirmed disruption.
Creating tasks never changes capacities, routes, inventory or sends messages.
"""
from __future__ import annotations

import json
from collections import defaultdict
from uuid import uuid4

from dependency.db.connection import connect


PHYSICAL = {"earthquake", "tropical_cyclone", "flood", "volcano", "wildfire"}


def propose_investigation_tasks(triage: dict, *, max_tasks: int = 100) -> list[dict]:
    """Construct generic tasks from explicit event-to-business dependency paths."""
    if max_tasks <= 0:
        raise ValueError("max_tasks must be positive")
    event = triage["event"]
    kind = event["event_type"]
    products = triage.get("impacted_products") or []
    margins = {p["sku"]: float(p.get("gross_margin_eur") or 0) for p in products}
    grouped: dict[str, dict] = {}

    def add(task_type: str, target_type: str, target_id: str, required_fact: str, sku: str | None):
        if not target_id:
            return
        task_key = f"{task_type}:{target_type}:{target_id}"
        record = grouped.setdefault(task_key, {
            "task_key": task_key,
            "task_type": task_type,
            "target_type": target_type,
            "target_id": target_id,
            "required_fact": required_fact,
            "connected_skus": set(),
        })
        if sku:
            record["connected_skus"].add(sku)

    if kind in PHYSICAL:
        for product in products:
            for reason in product.get("reasons") or []:
                facility = reason.get("facility_id")
                if facility:
                    add(
                        "CONFIRM_FACILITY_STATUS", "facility", str(facility),
                        "Confirm whether the facility is operating and its effective capacity. "
                        "Event proximity alone does not prove disruption.",
                        product["sku"],
                    )
                if reason.get("path_type") == "UPSTREAM_MATERIAL":
                    material = reason.get("material_id")
                    if facility and material:
                        add(
                            "CONFIRM_MATERIAL_SUPPLY", "facility_material",
                            f"{facility}:{material}",
                            "Confirm available material quantity, alternative source and delivery date.",
                            product["sku"],
                        )
        if not products:
            for facility in triage.get("public_exposure", []):
                node = facility.get("network_facility_id")
                if node:
                    add(
                        "VERIFY_PUBLIC_SUPPLIER_LINK", "public_facility", str(node),
                        "Check whether this publicly exposed site serves an active private order. "
                        "Do not invent a SKU relationship.",
                        None,
                    )
    elif kind in {"port_disruption", "port_activity_anomaly"}:
        for product in products:
            for reason in product.get("reasons") or []:
                lane = reason.get("lane_id")
                if lane:
                    add(
                        "CONFIRM_SHIPMENT_STATUS", "transport_lane", str(lane),
                        "Verify active shipments, carrier ETA and alternate routing. "
                        "Port-call anomalies do not prove late deliveries.",
                        product["sku"],
                    )
    elif kind == "tariff_policy":
        for product in products:
            add(
                "VERIFY_TARIFF_APPLICABILITY", "product", str(product["sku"]),
                "Verify HS classification, country of origin, effective date and exemptions "
                "against the official policy before calculating payable duties.",
                product["sku"],
            )

    result = []
    for record in grouped.values():
        skus = sorted(record.pop("connected_skus"))
        record["connected_skus"] = skus
        # These are connected gross margins, not predicted losses.
        record["connected_margin_eur"] = round(sum(margins.get(sku, 0) for sku in skus), 2)
        result.append(record)
    result.sort(key=lambda t: (-t["connected_margin_eur"], t["task_key"]))
    return result[:max_tasks]


def create_investigation_tasks(*, incident_id: str, triage: dict) -> list[dict]:
    """Upsert deterministic tasks; repeated event deliveries remain idempotent."""
    proposals = propose_investigation_tasks(triage)
    if not proposals:
        return []
    with connect() as conn:
        for task in proposals:
            conn.execute(
                """
                INSERT INTO incident_investigation_tasks(
                  task_id,incident_id,task_key,task_type,target_type,target_id,
                  required_fact,connected_skus,connected_margin_eur
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                ON CONFLICT (incident_id,task_key) DO UPDATE SET
                  connected_skus=EXCLUDED.connected_skus,
                  connected_margin_eur=EXCLUDED.connected_margin_eur,
                  updated_at=now()
                WHERE incident_investigation_tasks.status='OPEN'
                """,
                (
                    f"INV-{uuid4()}", incident_id, task["task_key"],
                    task["task_type"], task["target_type"], task["target_id"],
                    task["required_fact"], json.dumps(task["connected_skus"]),
                    task["connected_margin_eur"],
                ),
            )
        conn.commit()
    return proposals


def list_investigation_tasks(*, incident_id: str | None = None, limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT task_id,incident_id,task_key,task_type,target_type,target_id,
                   required_fact,connected_skus,connected_margin_eur,status,
                   provenance_class,created_at
            FROM incident_investigation_tasks
            WHERE status='OPEN' AND (%s::text IS NULL OR incident_id=%s)
            ORDER BY connected_margin_eur DESC,created_at,task_id
            LIMIT %s
            """,
            (incident_id, incident_id, limit),
        ).fetchall()
    return [{
        "task_id": r[0], "incident_id": r[1], "task_key": r[2],
        "task_type": r[3], "target_type": r[4], "target_id": r[5],
        "required_fact": r[6], "connected_skus": r[7],
        "connected_margin_eur": float(r[8]), "status": r[9],
        "provenance_class": r[10], "created_at": r[11].isoformat(),
    } for r in rows]


def confirm_facility_investigation(
    *,
    task_id: str,
    status: str,
    capacity_multiplier: float,
    confirmed_by: str,
    evidence_source: str,
    evidence_reference: str,
    reason: str,
) -> dict:
    """Apply operator-asserted private evidence and unblock a live recovery.

    This is a single PostgreSQL transaction. Do not call it with a model's
    unverified hypothesis or public proximity as evidence. The API write guard
    is the outer authorization boundary; actor names are audit text only.
    """
    from datetime import UTC, datetime
    from dependency.services.state_updates import _bump_state

    status = status.strip().upper()
    if status not in {"AVAILABLE", "DEGRADED", "UNAVAILABLE"}:
        raise ValueError("A confirmed facility status must be AVAILABLE, DEGRADED or UNAVAILABLE.")
    if status == "AVAILABLE" and capacity_multiplier != 1:
        raise ValueError("AVAILABLE requires multiplier=1.")
    if status == "UNAVAILABLE" and capacity_multiplier != 0:
        raise ValueError("UNAVAILABLE requires multiplier=0.")
    if status == "DEGRADED" and not 0 < capacity_multiplier < 1:
        raise ValueError("DEGRADED requires 0 < multiplier < 1.")
    for label, value in (
        ("confirmed_by", confirmed_by),
        ("evidence_source", evidence_source),
        ("evidence_reference", evidence_reference),
        ("reason", reason),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} is required; public proximity is not confirmation.")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT t.incident_id,t.task_type,t.target_type,t.target_id,t.status,
                   t.resolution_json,i.event_id,i.scenario_id,e.title,e.event_type,e.mode
            FROM incident_investigation_tasks t
            JOIN incidents i ON i.incident_id=t.incident_id
            JOIN external_events e ON e.event_id=i.event_id
            WHERE t.task_id=%s
            FOR UPDATE OF t,i
            """,
            (task_id,),
        ).fetchone()
        if not row:
            raise ValueError("Unknown investigation task.")
        (incident_id, task_type, target_type, facility_id,
         current_status, prior_resolution, event_id, scenario_id,
         event_title, event_type, event_mode) = row
        if current_status == "RESOLVED":
            return {
                "task_id": task_id, "incident_id": incident_id, "event_id": event_id,
                "scenario_id": scenario_id, "status": "ALREADY_RESOLVED",
                "resolution": prior_resolution,
            }
        if current_status != "OPEN":
            raise ValueError("Only an OPEN investigation can be resolved.")
        if task_type != "CONFIRM_FACILITY_STATUS" or target_type != "facility":
            raise ValueError("This evidence endpoint only confirms facility-status tasks.")
        if not conn.execute(
            "SELECT 1 FROM facilities WHERE facility_id=%s", (facility_id,)
        ).fetchone():
            raise ValueError("Task targets an unknown operational facility.")

        if scenario_id is None:
            existing = conn.execute(
                """
                SELECT scenario_id FROM scenarios
                WHERE event_id=%s
                ORDER BY CASE WHEN mode='LIVE' THEN 0 ELSE 1 END, as_of DESC
                LIMIT 1
                """,
                (event_id,),
            ).fetchone()
            if existing:
                scenario_id = existing[0]
            else:
                scenario_id = f"SCN-{uuid4()}"
                conn.execute(
                    """
                    INSERT INTO scenarios(
                      scenario_id,event_id,name,mode,as_of,provenance_class,note
                    ) VALUES (%s,%s,%s,%s,%s,'SIMULATED_PRIVATE',%s)
                    """,
                    (
                        scenario_id,event_id,
                        f"{event_type} confirmed operational assessment: {event_title}",
                        "LIVE" if event_mode == "LIVE" else "REPLAY",
                        datetime.now(UTC).date(),
                        "Explicit operator-entered private evidence. Public event does not prove damage.",
                    ),
                )
            conn.execute(
                "UPDATE incidents SET scenario_id=%s,updated_at=now() WHERE incident_id=%s",
                (scenario_id, incident_id),
            )

        conn.execute(
            """
            INSERT INTO scenario_facility_state(
              scenario_id,facility_id,status,capacity_multiplier,confirmed,
              source_type,reason,provenance_class
            ) VALUES (%s,%s,%s,%s,true,%s,%s,'SIMULATED_PRIVATE')
            ON CONFLICT (scenario_id,facility_id) DO UPDATE SET
              status=EXCLUDED.status,
              capacity_multiplier=EXCLUDED.capacity_multiplier,
              confirmed=true,source_type=EXCLUDED.source_type,
              reason=EXCLUDED.reason,provenance_class=EXCLUDED.provenance_class
            """,
            (
                scenario_id,facility_id,status,capacity_multiplier,
                evidence_source.strip(),reason.strip(),
            ),
        )
        rows = conn.execute(
            """
            SELECT sku FROM product_facilities WHERE facility_id=%s
            UNION
            SELECT sku FROM material_allocations
            WHERE source_facility_id=%s AND approved=true
            """,
            (facility_id,facility_id),
        ).fetchall()
        affected_skus = sorted({r[0] for r in rows})
        version = _bump_state(
            conn,change_type="INVESTIGATION_FACILITY_STATE_CONFIRMED",
            payload={
                "task_id":task_id,"incident_id":incident_id,
                "event_id":event_id,"scenario_id":scenario_id,
                "facility_id":facility_id,"confirmed":True,
                "status":status,"capacity_multiplier":capacity_multiplier,
                "evidence_source":evidence_source.strip(),
                "evidence_reference":evidence_reference.strip(),
                "provenance_class":"SIMULATED_PRIVATE",
            },
            affected_skus=affected_skus,
        )
        resolution = {
            "facility_id":facility_id,"scenario_id":scenario_id,
            "status":status,"capacity_multiplier":capacity_multiplier,
            "evidence_source":evidence_source.strip(),
            "evidence_reference":evidence_reference.strip(),
            "confirmed_by":confirmed_by.strip(),
            "state_version":version,
            "affected_skus":affected_skus,
            "provenance_class":"SIMULATED_PRIVATE",
        }
        conn.execute(
            """
            INSERT INTO incident_evidence(
              evidence_id,incident_id,evidence_type,source_name,source_url,
              fact_json,confidence,provenance_class
            ) VALUES (%s,%s,'OPERATOR_CONFIRMED_FACILITY_STATE',%s,NULL,
                      %s::jsonb,NULL,'SIMULATED_PRIVATE')
            """,
            (f"EVD-{uuid4()}",incident_id,evidence_source.strip(),
             json.dumps({**resolution,"reason":reason.strip()})),
        )
        conn.execute(
            """
            UPDATE incident_investigation_tasks
            SET status='RESOLVED',resolved_at=now(),resolved_by=%s,
                resolution_json=%s::jsonb,updated_at=now()
            WHERE task_id=%s
            """,
            (confirmed_by.strip(),json.dumps(resolution),task_id),
        )
        conn.commit()
    return {
        "task_id":task_id,"incident_id":incident_id,
        "event_id":event_id,"scenario_id":scenario_id,
        "status":"RESOLVED","resolution":resolution,
    }
