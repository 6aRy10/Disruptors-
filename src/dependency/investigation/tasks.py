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
