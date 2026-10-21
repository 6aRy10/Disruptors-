from __future__ import annotations

from datetime import timedelta

from dependency.db.connection import connect


OPEN_LANE_STATUSES = {"open", "available", "active"}


def evaluate_recovery_transport(
    *,
    scenario_id: str,
    sku: str,
    origin_facility_id: str,
) -> dict:
    """Check whether a proposed assembly site can reach each commitment on time.

    Transport lanes are private digital-twin facts. Missing lanes remain
    unknown; they are never replaced with an assumed zero-day route.
    """
    with connect() as conn:
        scenario = conn.execute(
            "SELECT as_of FROM scenarios WHERE scenario_id=%s",
            (scenario_id,),
        ).fetchone()
        if not scenario:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")

        facility = conn.execute(
            """
            SELECT f.name,pf.setup_lead_days,pf.approved,pf.provenance_class
            FROM product_facilities pf
            JOIN facilities f ON f.facility_id=pf.facility_id
            WHERE pf.sku=%s AND pf.facility_id=%s
            """,
            (sku, origin_facility_id),
        ).fetchone()
        if not facility:
            raise ValueError(
                f"No product-facility assignment for sku={sku} "
                f"facility={origin_facility_id}"
            )

        commitments = conn.execute(
            """
            SELECT commitment_id,customer_or_market,market,qty,due_date,
                   priority,revenue_eur,gross_margin_eur,provenance_class
            FROM fulfilment_commitments
            WHERE sku=%s
            ORDER BY due_date,priority,commitment_id
            """,
            (sku,),
        ).fetchall()

        lanes = conn.execute(
            """
            SELECT lane_id,destination_market,mode,transit_days,
                   cost_eur_per_unit,status,port_unlocode,port_name,
                   provenance_class
            FROM transport_lanes
            WHERE origin_facility_id=%s
            ORDER BY destination_market,transit_days,cost_eur_per_unit,lane_id
            """,
            (origin_facility_id,),
        ).fetchall()

    as_of = scenario[0]
    setup_days = int(facility[1] or 0)
    ready_date = as_of + timedelta(days=setup_days)

    lanes_by_market: dict[str, list[dict]] = {}
    for row in lanes:
        market = row[1]
        arrival = ready_date + timedelta(days=int(row[3] or 0))
        record = {
            "lane_id": row[0],
            "destination_market": market,
            "mode": row[2],
            "transit_days": int(row[3] or 0),
            "cost_eur_per_unit": float(row[4] or 0),
            "status": row[5],
            "port_unlocode": row[6],
            "port_name": row[7],
            "provenance_class": row[8],
            "ready_date": ready_date.isoformat(),
            "arrival_date": arrival.isoformat(),
        }
        lanes_by_market.setdefault(market, []).append(record)

    commitment_results = []
    on_time_units = 0.0
    uncovered_units = 0.0
    estimated_transport_cost = 0.0

    for row in commitments:
        due_date = row[4]
        options = lanes_by_market.get(row[2], [])
        on_time_options = [
            option
            for option in options
            if str(option["status"]).lower() in OPEN_LANE_STATUSES
            and option["arrival_date"] <= due_date.isoformat()
        ]
        on_time_options.sort(
            key=lambda option: (
                option["cost_eur_per_unit"],
                option["arrival_date"],
                option["lane_id"],
            )
        )
        best = on_time_options[0] if on_time_options else None
        qty = float(row[3])

        if best:
            status = "ON_TIME_ROUTE_AVAILABLE"
            on_time_units += qty
            estimated_transport_cost += qty * best["cost_eur_per_unit"]
        elif options:
            status = "NO_ON_TIME_ROUTE"
            uncovered_units += qty
        else:
            status = "NO_ROUTE_MODELED"
            uncovered_units += qty

        commitment_results.append(
            {
                "commitment_id": row[0],
                "customer_or_market": row[1],
                "market": row[2],
                "qty": qty,
                "due_date": due_date.isoformat() if due_date else None,
                "priority": int(row[5] or 0),
                "revenue_eur": float(row[6] or 0),
                "gross_margin_eur": float(row[7] or 0),
                "provenance_class": row[8],
                "status": status,
                "best_on_time_lane": best,
                "all_modeled_lanes": options,
            }
        )

    total_units = on_time_units + uncovered_units
    avg_cost = (
        estimated_transport_cost / on_time_units
        if on_time_units > 0
        else None
    )

    if not commitments:
        decision = "NO_COMMITMENTS"
    elif on_time_units == 0:
        decision = "NO_ON_TIME_TRANSPORT"
    elif uncovered_units > 0:
        decision = "PARTIAL_TRANSPORT_COVERAGE"
    else:
        decision = "ALL_COMMITMENTS_REACHABLE"

    return {
        "scenario_id": scenario_id,
        "sku": sku,
        "origin_facility_id": origin_facility_id,
        "origin_facility_name": facility[0],
        "facility_approved": bool(facility[2]),
        "product_facility_provenance_class": facility[3],
        "as_of": as_of.isoformat(),
        "setup_lead_days": setup_days,
        "ready_date": ready_date.isoformat(),
        "decision": decision,
        "total_commitment_units": total_units,
        "on_time_commitment_units": on_time_units,
        "uncovered_commitment_units": uncovered_units,
        "estimated_transport_cost_eur_if_all_on_time_routes_used": round(
            estimated_transport_cost,
            2,
        ),
        "weighted_average_transport_cost_eur_per_unit": (
            round(avg_cost, 2) if avg_cost is not None else None
        ),
        "commitments": commitment_results,
        "rule": (
            "A recovery site is useful only where an explicit open transport lane "
            "can arrive after setup and before the customer due date. Missing "
            "routes remain unknown rather than being assumed instant."
        ),
    }
