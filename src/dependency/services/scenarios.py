from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from dependency.db.connection import connect
from dependency.services.state_updates import update_facility_state


def resolve_operational_facility(facility_ref: str) -> str:
    """Resolve either an operational facility ID or a public network facility ID."""
    with connect() as conn:
        direct = conn.execute(
            "SELECT facility_id FROM facilities WHERE facility_id = %s",
            (facility_ref,),
        ).fetchone()
        if direct:
            return direct[0]

        rows = conn.execute(
            """
            SELECT facility_id
            FROM facility_network_links
            WHERE network_facility_id = %s
            ORDER BY match_confidence DESC, facility_id
            """,
            (facility_ref,),
        ).fetchall()

    if not rows:
        raise ValueError(f"No operational facility is linked to {facility_ref}")
    if len(rows) > 1:
        raise ValueError(
            f"Public facility {facility_ref} maps to multiple operational facilities; "
            "select one explicitly."
        )
    return rows[0][0]


def ensure_event_scenario(
    *,
    event_id: str,
    mode: str = "LIVE",
    as_of: str | None = None,
) -> dict:
    """Return an existing event scenario or create one for confirmed private state."""
    with connect() as conn:
        event = conn.execute(
            "SELECT title,event_type FROM external_events WHERE event_id=%s",
            (event_id,),
        ).fetchone()
        if not event:
            raise ValueError(f"Unknown event_id: {event_id}")

        existing = conn.execute(
            """
            SELECT scenario_id,name,mode,as_of,provenance_class,note
            FROM scenarios
            WHERE event_id=%s
            ORDER BY
              CASE WHEN mode='LIVE' THEN 0 ELSE 1 END,
              as_of DESC,
              scenario_id
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if existing:
            return {
                "scenario_id": existing[0],
                "name": existing[1],
                "mode": existing[2],
                "as_of": existing[3].isoformat(),
                "provenance_class": existing[4],
                "note": existing[5],
                "created": False,
            }

        scenario_id = f"SCN-{uuid4()}"
        scenario_date = (
            datetime.fromisoformat(as_of).date()
            if as_of
            else datetime.now(UTC).date()
        )
        name = f"{event[1]} operational scenario: {event[0]}"
        note = (
            "Scenario created from a real external event. Facility availability, "
            "capacity and other operational states remain private evidence and are "
            "not inferred from public proximity."
        )

        conn.execute(
            """
            INSERT INTO scenarios(
              scenario_id,event_id,name,mode,as_of,provenance_class,note
            ) VALUES (%s,%s,%s,%s,%s,'SIMULATED_PRIVATE',%s)
            """,
            (scenario_id, event_id, name, mode, scenario_date, note),
        )
        conn.commit()

    return {
        "scenario_id": scenario_id,
        "name": name,
        "mode": mode,
        "as_of": scenario_date.isoformat(),
        "provenance_class": "SIMULATED_PRIVATE",
        "note": note,
        "created": True,
    }


def confirm_event_facility_state(
    *,
    event_id: str,
    facility_ref: str,
    status: str,
    capacity_multiplier: float,
    confirmed: bool,
    source_type: str,
    reason: str,
) -> dict:
    """Attach confirmed private operational state to any external event."""
    scenario = ensure_event_scenario(event_id=event_id)
    facility_id = resolve_operational_facility(facility_ref)

    update = update_facility_state(
        scenario_id=scenario["scenario_id"],
        facility_id=facility_id,
        status=status,
        capacity_multiplier=capacity_multiplier,
        confirmed=confirmed,
        source_type=source_type,
        reason=reason,
    )
    return {
        "scenario": scenario,
        "resolved_facility_id": facility_id,
        "state_update": update,
    }
