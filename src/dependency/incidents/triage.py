from __future__ import annotations

from dependency.db.connection import connect
from dependency.graph.exposure import facilities_within_radius
from dependency.graph.impact import trace_event_impact
from dependency.memory.service import ensure_incident, record_evidence


def _event(event_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              event_id,event_type,mode,source,title,occurred_or_effective_at,
              ST_Y(geom::geometry),ST_X(geom::geometry),provenance_class,source_url
            FROM external_events
            WHERE event_id = %s
            """,
            (event_id,),
        ).fetchone()
    if not row:
        raise ValueError(f"Unknown event_id: {event_id}")
    return {
        "event_id": row[0],
        "event_type": row[1],
        "mode": row[2],
        "source": row[3],
        "title": row[4],
        "occurred_at": row[5].isoformat() if row[5] else None,
        "latitude": float(row[6]) if row[6] is not None else None,
        "longitude": float(row[7]) if row[7] is not None else None,
        "provenance_class": row[8],
        "source_url": row[9],
    }


def _scenario_for_event(event_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT scenario_id
            FROM scenarios
            WHERE event_id = %s
            ORDER BY
              CASE WHEN mode = 'LIVE' THEN 0 ELSE 1 END,
              as_of DESC,
              scenario_id
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
    return row[0] if row else None


def triage_event(*, event_id: str, radius_km: float = 150.0) -> dict:
    """Turn one external event into an auditable incident if it intersects the network.

    This is deterministic triage. It does not claim that any nearby facility is
    damaged or unavailable.
    """
    event = _event(event_id)
    if event["latitude"] is None or event["longitude"] is None:
        raise ValueError(f"Event {event_id} has no geospatial point.")

    public_exposure = facilities_within_radius(
        latitude=event["latitude"],
        longitude=event["longitude"],
        radius_km=radius_km,
    )

    if not public_exposure:
        return {
            "event": event,
            "radius_km": radius_km,
            "status": "NO_NETWORK_EXPOSURE",
            "incident": None,
            "public_facility_count": 0,
            "business_linked_facility_count": 0,
            "impacted_products": [],
            "scenario_id": None,
            "recovery_ready": False,
        }

    linked_operational_ids = sorted(
        {
            facility_id
            for row in public_exposure
            for facility_id in row.get("operational_facility_ids", [])
        }
    )

    scenario_id = _scenario_for_event(event_id)
    impact = trace_event_impact(event_id=event_id, radius_km=radius_km)

    incident = ensure_incident(
        event_id=event_id,
        scenario_id=scenario_id,
        summary=(
            f"{event['event_type']} event intersects {len(public_exposure)} public "
            f"supply-network facilities within {radius_km:g} km."
        ),
        initial_assessment=(
            "Public geospatial intersection is POTENTIAL exposure only. "
            "Operational impact requires explicit company graph edges and confirmed "
            "private state."
        ),
        provenance_class="PUBLIC_DERIVED",
    )

    # Polling is idempotent at incident level. Do not create duplicate evidence
    # every time the same live feed item is seen again.
    if incident["created"]:
        record_evidence(
            incident_id=incident["incident_id"],
            evidence_type="PUBLIC_GEOSPATIAL_EXPOSURE",
            source_name=event["source"],
            source_url=event["source_url"],
            fact={
                "event_id": event_id,
                "radius_km": radius_km,
                "public_facility_count": len(public_exposure),
                "facilities": [
                    {
                        "network_facility_id": row["network_facility_id"],
                        "name": row["name"],
                        "distance_km": row["distance_km"],
                        "business_linked": row["business_linked"],
                    }
                    for row in public_exposure[:100]
                ],
                "claim_rule": "POTENTIALLY_EXPOSED_ONLY",
            },
            confidence=100.0,
            provenance_class="PUBLIC_DERIVED",
        )

        if impact.get("products"):
            record_evidence(
                incident_id=incident["incident_id"],
                evidence_type="BUSINESS_GRAPH_EXPOSURE",
                source_name="Private operational digital twin",
                fact={
                    "event_id": event_id,
                    "products": impact["products"],
                    "totals": impact["totals"],
                    "dependency_paths": impact["dependency_paths"],
                    "claim_rule": "CONNECTED_VALUE_IS_NOT_GUARANTEED_LOSS",
                },
                confidence=100.0,
                provenance_class="SIMULATED_PRIVATE",
            )

    impacted_products = sorted(
        impact.get("products", []),
        key=lambda row: (
            -float(row.get("gross_margin_eur") or 0),
            -float(row.get("revenue_eur") or 0),
            row.get("sku") or "",
        ),
    )

    return {
        "event": event,
        "radius_km": radius_km,
        "status": (
            "BUSINESS_GRAPH_EXPOSURE"
            if impacted_products
            else "PUBLIC_NETWORK_EXPOSURE"
        ),
        "incident": incident,
        "public_facility_count": len(public_exposure),
        "business_linked_facility_count": len(linked_operational_ids),
        "business_linked_facility_ids": linked_operational_ids,
        "impacted_products": impacted_products,
        "commercial_totals": impact.get("totals", {}),
        "scenario_id": scenario_id,
        "recovery_ready": bool(scenario_id and impacted_products),
        "next_required_evidence": (
            []
            if scenario_id
            else [
                "CONFIRMED_OPERATIONAL_FACILITY_STATE",
                "CURRENT_SUPPLIER_CAPACITY",
            ]
        ),
    }
