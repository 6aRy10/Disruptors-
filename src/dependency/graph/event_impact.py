from __future__ import annotations

from collections import defaultdict

from dependency.db.connection import connect
from dependency.graph.impact import trace_event_impact as trace_geospatial_event_impact


PHYSICAL_EVENT_TYPES = {
    "earthquake",
    "tropical_cyclone",
    "flood",
    "volcano",
    "wildfire",
}


def _event_context(event_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT event_id,event_type,mode,source,title,raw_json,
                   provenance_class,source_url
            FROM external_events
            WHERE event_id=%s
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
        "raw_json": row[5] or {},
        "provenance_class": row[6],
        "source_url": row[7],
    }


def _commitments_for_paths(path_keys: set[tuple[str, str]]) -> list[dict]:
    if not path_keys:
        return []

    skus = sorted({sku for sku, _ in path_keys})
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              commitment_id,sku,customer_or_market,market,qty,due_date,
              revenue_eur,gross_margin_eur,priority,provenance_class
            FROM fulfilment_commitments
            WHERE sku=ANY(%s)
            ORDER BY due_date,priority,commitment_id
            """,
            (skus,),
        ).fetchall()

    return [
        {
            "commitment_id": r[0],
            "sku": r[1],
            "customer_or_market": r[2],
            "market": r[3],
            "qty": float(r[4]),
            "due_date": r[5].isoformat() if r[5] else None,
            "revenue_eur": float(r[6] or 0),
            "gross_margin_eur": float(r[7] or 0),
            "priority": int(r[8] or 0),
            "provenance_class": r[9],
        }
        for r in rows
        if (r[1], r[3]) in path_keys
    ]


def _products_from_paths(
    *,
    paths: list[dict],
    commitments: list[dict],
    exposure_status: str,
) -> list[dict]:
    reasons: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, str] = {}
    for path in paths:
        sku = path["sku"]
        names[sku] = path["product_name"]
        reasons[sku].append(path)

    commitment_by_sku: dict[str, list[dict]] = defaultdict(list)
    for row in commitments:
        commitment_by_sku[row["sku"]].append(row)

    products = []
    for sku in sorted(reasons):
        orders = commitment_by_sku.get(sku, [])
        products.append(
            {
                "sku": sku,
                "name": names.get(sku),
                "exposure_status": exposure_status,
                "reasons": reasons[sku],
                "commitment_count": len(orders),
                "commitment_units": sum(o["qty"] for o in orders),
                "revenue_eur": round(sum(o["revenue_eur"] for o in orders), 2),
                "gross_margin_eur": round(
                    sum(o["gross_margin_eur"] for o in orders),
                    2,
                ),
                "earliest_due_date": min(
                    (o["due_date"] for o in orders if o["due_date"]),
                    default=None,
                ),
                "commitments": orders,
            }
        )
    return products


def _totals(products: list[dict]) -> dict:
    return {
        "products_impacted": len(products),
        "commitment_units": round(
            sum(float(p["commitment_units"]) for p in products),
            2,
        ),
        "revenue_eur": round(
            sum(float(p["revenue_eur"]) for p in products),
            2,
        ),
        "gross_margin_eur": round(
            sum(float(p["gross_margin_eur"]) for p in products),
            2,
        ),
    }


def trace_port_event_impact(*, event_id: str) -> dict:
    event = _event_context(event_id)
    port_unlocode = (event["raw_json"] or {}).get("port_unlocode")
    if not port_unlocode:
        return {
            "event_id": event_id,
            "event_type": event["event_type"],
            "exposure_basis": "TRANSPORT_LANE",
            "exposure_status": "INSUFFICIENT_EVENT_CONTEXT",
            "facilities": [],
            "dependency_paths": [],
            "products": [],
            "totals": _totals([]),
            "missing_context": ["port_unlocode"],
        }

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT
              tl.lane_id,tl.origin_facility_id,f.name,tl.port_unlocode,
              tl.port_name,tl.destination_market,tl.mode,tl.transit_days,
              tl.cost_eur_per_unit,tl.status,tl.provenance_class,
              po.sku,p.name,po.prod_id,po.qty,po.status,po.provenance_class
            FROM transport_lanes tl
            JOIN facilities f ON f.facility_id=tl.origin_facility_id
            JOIN production_orders po
              ON po.facility_id=tl.origin_facility_id
             AND po.status IN ('planned','released','in_progress')
            JOIN products p ON p.sku=po.sku
            WHERE upper(tl.port_unlocode)=upper(%s)
            ORDER BY tl.lane_id,po.sku
            """,
            (port_unlocode,),
        ).fetchall()

    paths = [
        {
            "path_type": "TRANSPORT_LANE",
            "lane_id": r[0],
            "facility_id": r[1],
            "facility_name": r[2],
            "port_unlocode": r[3],
            "port_name": r[4],
            "destination_market": r[5],
            "mode": r[6],
            "transit_days": int(r[7] or 0),
            "cost_eur_per_unit": float(r[8] or 0),
            "lane_status": r[9],
            "lane_provenance_class": r[10],
            "sku": r[11],
            "product_name": r[12],
            "production_order_id": r[13],
            "production_units": float(r[14]),
            "production_status": r[15],
            "production_provenance_class": r[16],
            "exposure_status": "POTENTIALLY_DELAYED",
        }
        for r in rows
    ]
    path_keys = {
        (path["sku"], path["destination_market"])
        for path in paths
    }
    commitments = _commitments_for_paths(path_keys)
    products = _products_from_paths(
        paths=paths,
        commitments=commitments,
        exposure_status="POTENTIALLY_DELAYED",
    )

    facilities = []
    seen_facilities = set()
    for path in paths:
        facility_id = path["facility_id"]
        if facility_id in seen_facilities:
            continue
        seen_facilities.add(facility_id)
        facilities.append(
            {
                "facility_id": facility_id,
                "name": path["facility_name"],
                "exposure_status": "ROUTE_USES_AFFECTED_PORT",
                "provenance_class": "SIMULATED_PRIVATE",
            }
        )

    return {
        "event_id": event_id,
        "event_type": event["event_type"],
        "exposure_basis": "EXPLICIT_TRANSPORT_LANE",
        "exposure_status": (
            "POTENTIAL_ROUTE_DISRUPTION"
            if paths
            else "NO_EXPLICIT_ROUTE_EXPOSURE"
        ),
        "port_unlocode": port_unlocode,
        "facilities": facilities,
        "dependency_paths": paths,
        "products": products,
        "totals": _totals(products),
        "claim_rule": (
            "The public port event is verified. Route assignment and commercial "
            "impact come from the private digital twin. Affected port usage means "
            "potential delay, not proof that every order is late."
        ),
    }


def trace_policy_event_impact(*, event_id: str) -> dict:
    event = _event_context(event_id)
    context = event["raw_json"] or {}
    policy_tag = context.get("policy_tag")
    if not policy_tag:
        return {
            "event_id": event_id,
            "event_type": event["event_type"],
            "exposure_basis": "TRADE_POLICY",
            "exposure_status": "INSUFFICIENT_EVENT_CONTEXT",
            "facilities": [],
            "dependency_paths": [],
            "products": [],
            "totals": _totals([]),
            "missing_context": ["policy_tag"],
        }

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT
              tl.lane_id,tl.origin_facility_id,f.name,f.country,
              tl.port_unlocode,tl.port_name,tl.destination_market,tl.mode,
              tl.transit_days,tl.cost_eur_per_unit,tl.policy_tag,
              tl.provenance_class,po.sku,p.name,p.hs_code,
              po.prod_id,po.qty,po.status,po.provenance_class
            FROM transport_lanes tl
            JOIN facilities f ON f.facility_id=tl.origin_facility_id
            JOIN production_orders po
              ON po.facility_id=tl.origin_facility_id
             AND po.status IN ('planned','released','in_progress')
            JOIN products p ON p.sku=po.sku
            WHERE tl.policy_tag=%s
            ORDER BY tl.lane_id,po.sku
            """,
            (policy_tag,),
        ).fetchall()

    applicability = context.get("applicability_status") or "UNKNOWN"
    rate = context.get("additional_rate")

    paths = [
        {
            "path_type": "TRADE_POLICY_LANE",
            "lane_id": r[0],
            "facility_id": r[1],
            "facility_name": r[2],
            "origin_country": r[3],
            "port_unlocode": r[4],
            "port_name": r[5],
            "destination_market": r[6],
            "mode": r[7],
            "transit_days": int(r[8] or 0),
            "transport_cost_eur_per_unit": float(r[9] or 0),
            "policy_tag": r[10],
            "lane_provenance_class": r[11],
            "sku": r[12],
            "product_name": r[13],
            "hs_code": r[14],
            "production_order_id": r[15],
            "production_units": float(r[16]),
            "production_status": r[17],
            "production_provenance_class": r[18],
            "policy_applicability_status": applicability,
            "additional_rate": float(rate) if rate is not None else None,
            "exposure_status": "CLASSIFICATION_REVIEW_REQUIRED",
        }
        for r in rows
    ]
    path_keys = {
        (path["sku"], path["destination_market"])
        for path in paths
    }
    commitments = _commitments_for_paths(path_keys)
    products = _products_from_paths(
        paths=paths,
        commitments=commitments,
        exposure_status="POTENTIAL_COST_EXPOSURE",
    )

    facilities = []
    seen_facilities = set()
    for path in paths:
        facility_id = path["facility_id"]
        if facility_id in seen_facilities:
            continue
        seen_facilities.add(facility_id)
        facilities.append(
            {
                "facility_id": facility_id,
                "name": path["facility_name"],
                "country": path["origin_country"],
                "exposure_status": "POLICY_ORIGIN_MATCH",
                "provenance_class": "SIMULATED_PRIVATE",
            }
        )

    return {
        "event_id": event_id,
        "event_type": event["event_type"],
        "exposure_basis": "EXPLICIT_POLICY_TAGGED_TRANSPORT_LANE",
        "exposure_status": (
            "POTENTIAL_COST_EXPOSURE_REQUIRES_CLASSIFICATION"
            if paths
            else "NO_EXPLICIT_POLICY_ROUTE_EXPOSURE"
        ),
        "policy_tag": policy_tag,
        "additional_rate": float(rate) if rate is not None else None,
        "applicability_status": applicability,
        "facilities": facilities,
        "dependency_paths": paths,
        "products": products,
        "totals": _totals(products),
        "claim_rule": (
            "Origin/destination route exposure is explicit private data. The "
            "tariff rate is a verified public policy fact. Product-level duty "
            "impact is not confirmed until customs classification and exemptions "
            "are checked."
        ),
    }


def trace_business_event_impact(
    *,
    event_id: str,
    radius_km: float = 100.0,
) -> dict:
    event = _event_context(event_id)
    event_type = event["event_type"]

    if event_type == "port_disruption" or event_type == "port_activity_anomaly":
        return trace_port_event_impact(event_id=event_id)

    if event_type == "tariff_policy":
        return trace_policy_event_impact(event_id=event_id)

    result = trace_geospatial_event_impact(
        event_id=event_id,
        radius_km=radius_km,
    )
    result["event_type"] = event_type
    result["exposure_basis"] = "GEOSPATIAL_PROXIMITY"
    result["claim_rule"] = (
        "Geographic proximity means potentially exposed only. Operational "
        "disruption requires separate confirmed private state."
    )
    return result
