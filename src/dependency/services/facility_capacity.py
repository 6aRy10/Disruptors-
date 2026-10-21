"""Explicit, dated facility-wide ceilings for joint product recovery.

These are operator-confirmed private enterprise facts, not conclusions inferred
from public proximity or the per-SKU supplier_capacity table.
"""
from __future__ import annotations

from datetime import date
from dependency.db.connection import connect
from dependency.services.state_updates import _bump_state


def _date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def confirm_facility_capacity(
    *,
    facility_id: str,
    week_start: str | date,
    valid_until: str | date,
    capacity_units: int,
    committed_units: int,
    evidence_source: str,
    evidence_reference: str,
    confirmed_by: str,
) -> dict:
    start, end = _date(week_start), _date(valid_until)
    if end < start:
        raise ValueError("valid_until must not precede week_start.")
    if type(capacity_units) is not int or type(committed_units) is not int:
        raise ValueError("Capacity and commitments must be integer units.")
    if capacity_units < 0 or not 0 <= committed_units <= capacity_units:
        raise ValueError("Confirmed facility commitments cannot exceed capacity.")
    if not all(isinstance(s,str) and s.strip() for s in (
        facility_id,evidence_source,evidence_reference,confirmed_by,
    )):
        raise ValueError("Facility, evidence source/reference and confirming operator are required.")

    with connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"facility-capacity:{facility_id}:{start}",))
        existing = conn.execute(
            """
            SELECT capacity_units,committed_units,valid_until,evidence_source,
                   evidence_reference,confirmed_by
            FROM confirmed_facility_capacity
            WHERE facility_id=%s AND week_start=%s FOR UPDATE
            """,
            (facility_id,start),
        ).fetchone()
        new_value = (
            capacity_units,committed_units,end,
            evidence_source.strip(),evidence_reference.strip(),confirmed_by.strip(),
        )
        if existing and tuple(existing)==new_value:
            row=conn.execute(
                "SELECT version FROM operational_state_version WHERE singleton=true"
            ).fetchone()
            return {
                "status":"UNCHANGED","facility_id":facility_id,
                "week_start":start.isoformat(),"valid_until":end.isoformat(),
                "available_capacity_units":capacity_units-committed_units,
                "state_version":int(row[0]),
            }
        conn.execute(
            """
            INSERT INTO confirmed_facility_capacity(
              facility_id,week_start,valid_until,capacity_units,committed_units,
              evidence_source,evidence_reference,confirmed_by
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (facility_id,week_start) DO UPDATE SET
              valid_until=EXCLUDED.valid_until,
              capacity_units=EXCLUDED.capacity_units,
              committed_units=EXCLUDED.committed_units,
              evidence_source=EXCLUDED.evidence_source,
              evidence_reference=EXCLUDED.evidence_reference,
              confirmed_by=EXCLUDED.confirmed_by,
              confirmed_at=now()
            """,
            (facility_id,start,end,capacity_units,committed_units,
             evidence_source.strip(),evidence_reference.strip(),confirmed_by.strip()),
        )
        # All SKUs allocated to the same physical factory must replan.
        skus=conn.execute(
            """
            SELECT sku FROM product_facilities WHERE facility_id=%s
            UNION
            SELECT sku FROM material_allocations
            WHERE source_facility_id=%s AND approved=true
            """,
            (facility_id,facility_id),
        ).fetchall()
        version=_bump_state(
            conn,change_type="FACILITY_WIDE_CAPACITY_CONFIRMED",
            payload={
                "facility_id":facility_id,"week_start":start.isoformat(),
                "valid_until":end.isoformat(),"capacity_units":capacity_units,
                "committed_units":committed_units,
                "evidence_reference":evidence_reference.strip(),
                "provenance_class":"SIMULATED_PRIVATE",
            },
            affected_skus=[r[0] for r in skus],
        )
        conn.commit()
    return {
        "status":"UPDATED","facility_id":facility_id,
        "week_start":start.isoformat(),"valid_until":end.isoformat(),
        "available_capacity_units":capacity_units-committed_units,
        "state_version":version,
        "affected_skus":sorted({r[0] for r in skus}),
    }


def confirmed_capacity_for_scenario(
    *,
    scenario_id: str,
    facility_ids: list[str],
) -> dict[str,dict]:
    """Use only confirmed ceilings whose validity covers scenario as_of."""
    if not facility_ids:
        return {}
    with connect() as conn:
        rows=conn.execute(
            """
            SELECT DISTINCT ON (c.facility_id)
                   c.facility_id,c.capacity_units,c.committed_units,
                   c.week_start,c.valid_until,c.evidence_reference
            FROM confirmed_facility_capacity c
            JOIN scenarios s ON s.scenario_id=%s
            WHERE c.facility_id=ANY(%s)
              AND c.week_start <= s.as_of
              AND c.valid_until >= s.as_of
            ORDER BY c.facility_id,c.week_start DESC
            """,
            (scenario_id,sorted(set(facility_ids))),
        ).fetchall()
    return {
        r[0]:{
            "available_units":int(r[1])-int(r[2]),
            "week_start":r[3].isoformat(),
            "valid_until":r[4].isoformat(),
            "evidence_reference":r[5],
        } for r in rows
    }
