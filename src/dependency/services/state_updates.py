from __future__ import annotations

from datetime import datetime

from dependency.db.connection import connect
from dependency.events.bus import (
    TOPIC_BUSINESS_STATE,
    TOPIC_PLAN_INVALIDATED,
    enqueue_outbox,
)

VALID_FACILITY_STATES = {"AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN"}


def _bump_state(
    conn,
    *,
    change_type: str,
    payload: dict,
    affected_skus: list[str] | None = None,
) -> int:
    version = int(
        conn.execute(
            """
            UPDATE operational_state_version
            SET version = version + 1
            WHERE singleton = true
            RETURNING version
            """
        ).fetchone()[0]
    )
    event_payload = {
        "state_version": version,
        "change_type": change_type,
        **payload,
    }
    enqueue_outbox(
        conn,
        topic=TOPIC_BUSINESS_STATE,
        event_key=f"state:{version}",
        payload=event_payload,
    )
    for sku in sorted(set(affected_skus or [])):
        enqueue_outbox(
            conn,
            topic=TOPIC_PLAN_INVALIDATED,
            event_key=f"{sku}:{version}",
            payload={
                "sku": sku,
                "new_state_version": version,
                "reason": change_type,
                "change": payload,
            },
        )
    return version


def update_inventory(
    *,
    site_id: str,
    item_type: str,
    item_id: str,
    qty_on_hand: float,
    qty_reserved: float,
    safety_stock: float,
) -> dict:
    if min(qty_on_hand, qty_reserved, safety_stock) < 0:
        raise ValueError("Inventory quantities must be >= 0.")

    with connect() as conn:
        old = conn.execute(
            """
            SELECT qty_on_hand,qty_reserved,safety_stock
            FROM inventory
            WHERE site_id=%s AND item_type=%s AND item_id=%s
            FOR UPDATE
            """,
            (site_id, item_type, item_id),
        ).fetchone()
        if not old:
            raise ValueError(
                f"Unknown inventory row: {site_id}/{item_type}/{item_id}"
            )

        conn.execute(
            """
            UPDATE inventory
            SET qty_on_hand=%s,qty_reserved=%s,safety_stock=%s,updated_at=now()
            WHERE site_id=%s AND item_type=%s AND item_id=%s
            """,
            (
                qty_on_hand,
                qty_reserved,
                safety_stock,
                site_id,
                item_type,
                item_id,
            ),
        )
        affected = [item_id] if item_type == "finished_good" else []
        version = _bump_state(
            conn,
            change_type="INVENTORY_UPDATED",
            payload={
                "site_id": site_id,
                "item_type": item_type,
                "item_id": item_id,
                "old": {
                    "qty_on_hand": float(old[0]),
                    "qty_reserved": float(old[1]),
                    "safety_stock": float(old[2]),
                },
                "new": {
                    "qty_on_hand": float(qty_on_hand),
                    "qty_reserved": float(qty_reserved),
                    "safety_stock": float(safety_stock),
                },
            },
            affected_skus=affected,
        )
        conn.commit()

    return {
        "state_version": version,
        "site_id": site_id,
        "item_type": item_type,
        "item_id": item_id,
        "qty_on_hand": float(qty_on_hand),
        "qty_reserved": float(qty_reserved),
        "safety_stock": float(safety_stock),
    }


def update_setup_lead_time(
    *,
    sku: str,
    facility_id: str,
    setup_lead_days: int,
) -> dict:
    if setup_lead_days < 0:
        raise ValueError("setup_lead_days must be >= 0.")

    with connect() as conn:
        old = conn.execute(
            """
            SELECT setup_lead_days
            FROM product_facilities
            WHERE sku=%s AND facility_id=%s
            FOR UPDATE
            """,
            (sku, facility_id),
        ).fetchone()
        if not old:
            raise ValueError(f"Unknown SKU/facility assignment: {sku}/{facility_id}")

        conn.execute(
            """
            UPDATE product_facilities
            SET setup_lead_days=%s
            WHERE sku=%s AND facility_id=%s
            """,
            (setup_lead_days, sku, facility_id),
        )
        version = _bump_state(
            conn,
            change_type="SETUP_LEAD_TIME_UPDATED",
            payload={
                "sku": sku,
                "facility_id": facility_id,
                "old_setup_lead_days": int(old[0] or 0),
                "new_setup_lead_days": int(setup_lead_days),
            },
            affected_skus=[sku],
        )
        conn.commit()

    return {
        "state_version": version,
        "sku": sku,
        "facility_id": facility_id,
        "setup_lead_days": int(setup_lead_days),
    }


def update_purchase_order_eta(
    *,
    po_id: str,
    eta: str,
) -> dict:
    parsed = datetime.fromisoformat(eta.replace("Z", "+00:00"))

    with connect() as conn:
        old = conn.execute(
            """
            SELECT material_id,eta
            FROM purchase_orders
            WHERE po_id=%s
            FOR UPDATE
            """,
            (po_id,),
        ).fetchone()
        if not old:
            raise ValueError(f"Unknown purchase order: {po_id}")

        conn.execute(
            "UPDATE purchase_orders SET eta=%s WHERE po_id=%s",
            (parsed, po_id),
        )
        sku_rows = conn.execute(
            "SELECT DISTINCT sku FROM bom WHERE material_id=%s",
            (old[0],),
        ).fetchall()
        skus = [r[0] for r in sku_rows]
        version = _bump_state(
            conn,
            change_type="PURCHASE_ORDER_ETA_UPDATED",
            payload={
                "po_id": po_id,
                "material_id": old[0],
                "old_eta": old[1].isoformat() if old[1] else None,
                "new_eta": parsed.isoformat(),
            },
            affected_skus=skus,
        )
        conn.commit()

    return {
        "state_version": version,
        "po_id": po_id,
        "material_id": old[0],
        "eta": parsed.isoformat(),
        "affected_skus": skus,
    }


def update_facility_state(
    *,
    scenario_id: str,
    facility_id: str,
    status: str,
    capacity_multiplier: float,
    confirmed: bool,
    source_type: str,
    reason: str,
) -> dict:
    status = status.upper()
    if status not in VALID_FACILITY_STATES:
        raise ValueError(f"Invalid facility status: {status}")
    if not 0 <= capacity_multiplier <= 1:
        raise ValueError("capacity_multiplier must be between 0 and 1.")

    with connect() as conn:
        exists = conn.execute(
            """
            SELECT 1 FROM scenarios WHERE scenario_id=%s
            """,
            (scenario_id,),
        ).fetchone()
        if not exists:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")

        conn.execute(
            """
            INSERT INTO scenario_facility_state(
              scenario_id,facility_id,status,capacity_multiplier,confirmed,
              source_type,reason,provenance_class
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,'SIMULATED_PRIVATE')
            ON CONFLICT (scenario_id,facility_id) DO UPDATE SET
              status=EXCLUDED.status,
              capacity_multiplier=EXCLUDED.capacity_multiplier,
              confirmed=EXCLUDED.confirmed,
              source_type=EXCLUDED.source_type,
              reason=EXCLUDED.reason,
              provenance_class=EXCLUDED.provenance_class
            """,
            (
                scenario_id,
                facility_id,
                status,
                capacity_multiplier,
                confirmed,
                source_type,
                reason,
            ),
        )
        sku_rows = conn.execute(
            """
            SELECT DISTINCT sku
            FROM product_facilities
            WHERE facility_id=%s
            """,
            (facility_id,),
        ).fetchall()
        skus = [r[0] for r in sku_rows]
        version = _bump_state(
            conn,
            change_type="FACILITY_STATE_UPDATED",
            payload={
                "scenario_id": scenario_id,
                "facility_id": facility_id,
                "status": status,
                "capacity_multiplier": float(capacity_multiplier),
                "confirmed": bool(confirmed),
                "source_type": source_type,
                "reason": reason,
            },
            affected_skus=skus,
        )
        conn.commit()

    return {
        "state_version": version,
        "scenario_id": scenario_id,
        "facility_id": facility_id,
        "status": status,
        "capacity_multiplier": float(capacity_multiplier),
        "confirmed": bool(confirmed),
        "affected_skus": skus,
    }


def update_substitution_approval(
    *,
    material_id: str,
    substitute_material_id: str,
    approved: bool,
    engineering_status: str,
) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM substitutions
            WHERE material_id=%s AND substitute_material_id=%s
            FOR UPDATE
            """,
            (material_id, substitute_material_id),
        ).fetchone()
        if not row:
            raise ValueError(
                f"Unknown substitution: {material_id}/{substitute_material_id}"
            )

        conn.execute(
            """
            UPDATE substitutions
            SET approved=%s,engineering_status=%s
            WHERE material_id=%s AND substitute_material_id=%s
            """,
            (
                approved,
                engineering_status,
                material_id,
                substitute_material_id,
            ),
        )
        sku_rows = conn.execute(
            "SELECT DISTINCT sku FROM bom WHERE material_id=%s",
            (material_id,),
        ).fetchall()
        skus = [r[0] for r in sku_rows]
        version = _bump_state(
            conn,
            change_type="SUBSTITUTION_APPROVAL_UPDATED",
            payload={
                "material_id": material_id,
                "substitute_material_id": substitute_material_id,
                "approved": bool(approved),
                "engineering_status": engineering_status,
            },
            affected_skus=skus,
        )
        conn.commit()

    return {
        "state_version": version,
        "material_id": material_id,
        "substitute_material_id": substitute_material_id,
        "approved": bool(approved),
        "engineering_status": engineering_status,
        "affected_skus": skus,
    }
