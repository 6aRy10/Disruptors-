from __future__ import annotations

from uuid import uuid4

from dependency.db.connection import connect
from dependency.events.bus import (
    TOPIC_BUSINESS_STATE,
    TOPIC_PLAN_INVALIDATED,
    TOPIC_SUPPLIER_CAPACITY,
    enqueue_outbox,
)


def confirm_supplier_capacity(
    *,
    facility_id: str,
    sku: str,
    capacity_units: int,
    valid_until: str | None,
    source_channel: str,
    raw_message: str | None = None,
) -> dict:
    if capacity_units < 0:
        raise ValueError("capacity_units must be >= 0")

    with connect() as conn:
        current = conn.execute(
            """
            SELECT week_start, capacity_units, committed_units
            FROM supplier_capacity
            WHERE facility_id = %s AND sku = %s
            ORDER BY week_start DESC
            LIMIT 1
            FOR UPDATE
            """,
            (facility_id, sku),
        ).fetchone()
        if not current:
            raise ValueError(f"No supplier capacity row for facility={facility_id} sku={sku}")

        week_start, old_capacity, committed_units = current
        conn.execute(
            """
            UPDATE supplier_capacity
            SET capacity_units = %s,
                evidence_age_hours = 0,
                source = %s
            WHERE facility_id = %s AND sku = %s AND week_start = %s
            """,
            (
                capacity_units,
                f"{source_channel} confirmed capacity",
                facility_id,
                sku,
                week_start,
            ),
        )

        observation_id = f"CAP-{uuid4()}"
        conn.execute(
            """
            INSERT INTO supplier_capacity_observations(
              observation_id,facility_id,sku,valid_until,capacity_units,
              committed_units,source_channel,raw_message,confirmed,provenance_class
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,true,'SIMULATED_PRIVATE')
            """,
            (
                observation_id,
                facility_id,
                sku,
                valid_until,
                capacity_units,
                committed_units,
                source_channel,
                raw_message,
            ),
        )

        new_version = conn.execute(
            """
            UPDATE operational_state_version
            SET version = version + 1
            WHERE singleton = true
            RETURNING version
            """
        ).fetchone()[0]

        capacity_event = {
            "observation_id": observation_id,
            "facility_id": facility_id,
            "sku": sku,
            "old_capacity_units": float(old_capacity),
            "new_capacity_units": int(capacity_units),
            "committed_units": float(committed_units),
            "available_capacity_units": max(
                0.0,
                float(capacity_units) - float(committed_units),
            ),
            "valid_until": valid_until,
            "state_version": int(new_version),
            "confirmed": True,
            "source_channel": source_channel,
            "provenance_class": "SIMULATED_PRIVATE",
        }
        enqueue_outbox(
            conn,
            topic=TOPIC_SUPPLIER_CAPACITY,
            event_key=f"{facility_id}:{sku}",
            payload=capacity_event,
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_BUSINESS_STATE,
            event_key=f"state:{new_version}",
            payload={
                "state_version": int(new_version),
                "change_type": "SUPPLIER_CAPACITY_CONFIRMED",
                "facility_id": facility_id,
                "sku": sku,
            },
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_PLAN_INVALIDATED,
            event_key=f"{sku}:{new_version}",
            payload={
                "sku": sku,
                "new_state_version": int(new_version),
                "reason": "SUPPLIER_CAPACITY_CHANGED",
            },
        )

        conn.commit()

    return {
        "observation_id": observation_id,
        "facility_id": facility_id,
        "sku": sku,
        "old_capacity_units": float(old_capacity),
        "new_capacity_units": int(capacity_units),
        "committed_units": float(committed_units),
        "available_capacity_units": max(0.0, float(capacity_units) - float(committed_units)),
        "valid_until": valid_until,
        "state_version": int(new_version),
        "confirmed": True,
    }
