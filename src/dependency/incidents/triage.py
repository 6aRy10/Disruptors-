from __future__ import annotations

from dependency.db.connection import connect
from dependency.graph.event_impact import trace_business_event_impact
from dependency.graph.exposure import facilities_within_radius
from dependency.memory.service import ensure_incident, record_evidence


PHYSICAL_EVENT_TYPES = {
    "earthquake",
    "tropical_cyclone",
    "flood",
    "volcano",
    "wildfire",
}


def _event(event_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              event_id,event_type,mode,source,title,occurred_or_effective_at,
              ST_Y(geom::geometry),ST_X(geom::geometry),provenance_class,
              source_url,raw_json
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
        "raw_json": row[10] or {},
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


def _public_geospatial_context(
    *,
    event: dict,
    radius_km: float,
) -> list[dict]:
    if event["event_type"] not in PHYSICAL_EVENT_TYPES:
        return []
    if event["latitude"] is None or event["longitude"] is None:
        return []
    return facilities_within_radius(
        latitude=event["latitude"],
        longitude=event["longitude"],
        radius_km=radius_km,
    )


def _missing_evidence(event: dict, scenario_id: str | None) -> list[str]:
    if event["event_type"] == "tariff_policy":
        missing = ["PRODUCT_CLASSIFICATION_AND_EXEMPTION_CHECK"]
        if not scenario_id:
            missing.append("CURRENT_OPERATIONAL_ROUTE_STATE")
        return missing

    if event["event_type"] in {"port_disruption", "port_activity_anomaly"}:
        return (
            []
            if scenario_id
            else [
                "CURRENT_SHIPMENT_OR_ROUTE_STATUS",
                "CONFIRMED_OPERATIONAL_DELAY",
            ]
        )

    return (
        []
        if scenario_id
        else [
            "CONFIRMED_OPERATIONAL_FACILITY_STATE",
            "CURRENT_SUPPLIER_CAPACITY",
        ]
    )


def triage_event(*, event_id: str, radius_km: float = 150.0) -> dict:
    """Turn one external event into an auditable business incident.

    Exposure logic depends on event type:
    - physical hazards use PostGIS proximity;
    - port events use explicit private transport lanes;
    - trade policy uses explicit policy-tagged routes and requires product
      classification before definite duty impact is claimed.
    """
    event = _event(event_id)
    public_exposure = _public_geospatial_context(
        event=event,
        radius_km=radius_km,
    )
    impact = trace_business_event_impact(
        event_id=event_id,
        radius_km=radius_km,
    )

    if event["event_type"] in PHYSICAL_EVENT_TYPES and not public_exposure:
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
            "exposure_basis": impact.get("exposure_basis"),
        }

    impacted_products = sorted(
        impact.get("products", []),
        key=lambda row: (
            -float(row.get("gross_margin_eur") or 0),
            -float(row.get("revenue_eur") or 0),
            row.get("sku") or "",
        ),
    )

    if event["event_type"] not in PHYSICAL_EVENT_TYPES and not impacted_products:
        return {
            "event": event,
            "radius_km": radius_km,
            "status": "NO_BUSINESS_EXPOSURE",
            "incident": None,
            "public_facility_count": 0,
            "business_linked_facility_count": 0,
            "impacted_products": [],
            "commercial_totals": impact.get("totals", {}),
            "scenario_id": None,
            "recovery_ready": False,
            "exposure_basis": impact.get("exposure_basis"),
        }

    linked_operational_ids = sorted(
        {
            facility_id
            for row in public_exposure
            for facility_id in row.get("operational_facility_ids", [])
        }
        | {
            row["facility_id"]
            for row in impact.get("facilities", [])
            if row.get("facility_id")
        }
    )

    scenario_id = _scenario_for_event(event_id)
    exposure_basis = impact.get("exposure_basis") or "UNKNOWN"

    if event["event_type"] in PHYSICAL_EVENT_TYPES:
        summary = (
            f"{event['event_type']} event intersects {len(public_exposure)} public "
            f"supply-network facilities within {radius_km:g} km."
        )
        initial_assessment = (
            "Public geospatial intersection is POTENTIAL exposure only. "
            "Operational impact requires explicit company graph edges and confirmed "
            "private state."
        )
        evidence_type = "PUBLIC_GEOSPATIAL_EXPOSURE"
        public_fact = {
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
        }
    elif event["event_type"] in {"port_disruption", "port_activity_anomaly"}:
        summary = (
            f"{event['event_type']} event intersects "
            f"{len(impact.get('dependency_paths', []))} explicit transport paths."
        )
        initial_assessment = (
            "The public port signal is verified. Company route assignments are "
            "private digital-twin facts. Route exposure means potential delay, "
            "not proof that each order is late."
        )
        evidence_type = "PUBLIC_PORT_SIGNAL"
        public_fact = {
            "event_id": event_id,
            "port_unlocode": impact.get("port_unlocode"),
            "source_fact": event["raw_json"].get("source_fact"),
            "claim_rule": impact.get("claim_rule"),
        }
    else:
        summary = (
            f"{event['event_type']} event intersects "
            f"{len(impact.get('dependency_paths', []))} policy-tagged business paths."
        )
        initial_assessment = (
            "The public policy change is verified. Company route exposure is "
            "private data. Product-level duty impact remains conditional until "
            "classification and exemptions are checked."
        )
        evidence_type = "PUBLIC_TRADE_POLICY"
        public_fact = {
            "event_id": event_id,
            "policy_tag": impact.get("policy_tag"),
            "additional_rate": impact.get("additional_rate"),
            "applicability_status": impact.get("applicability_status"),
            "source_fact": event["raw_json"].get("source_fact"),
            "claim_rule": impact.get("claim_rule"),
        }

    incident = ensure_incident(
        event_id=event_id,
        scenario_id=scenario_id,
        summary=summary,
        initial_assessment=initial_assessment,
        provenance_class="PUBLIC_DERIVED",
    )

    if incident["created"]:
        record_evidence(
            incident_id=incident["incident_id"],
            evidence_type=evidence_type,
            source_name=event["source"],
            source_url=event["source_url"],
            fact=public_fact,
            confidence=100.0,
            provenance_class=event["provenance_class"],
        )

        if impacted_products:
            record_evidence(
                incident_id=incident["incident_id"],
                evidence_type="BUSINESS_GRAPH_EXPOSURE",
                source_name="Private operational digital twin",
                fact={
                    "event_id": event_id,
                    "exposure_basis": exposure_basis,
                    "products": impacted_products,
                    "totals": impact.get("totals", {}),
                    "dependency_paths": impact.get("dependency_paths", []),
                    "claim_rule": (
                        "CONNECTED_VALUE_IS_NOT_GUARANTEED_LOSS"
                    ),
                },
                confidence=100.0,
                provenance_class="SIMULATED_PRIVATE",
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
        "exposure_basis": exposure_basis,
        "public_facility_count": len(public_exposure),
        "business_linked_facility_count": len(linked_operational_ids),
        "business_linked_facility_ids": linked_operational_ids,
        "impacted_products": impacted_products,
        "commercial_totals": impact.get("totals", {}),
        "scenario_id": scenario_id,
        "recovery_ready": bool(scenario_id and impacted_products),
        "next_required_evidence": _missing_evidence(event, scenario_id),
    }
