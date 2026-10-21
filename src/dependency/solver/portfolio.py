from __future__ import annotations

from collections import defaultdict

from dependency.db.connection import connect
from dependency.graph.event_impact import trace_business_event_impact
from dependency.risk.operational import scenario_product_risk
from dependency.solver.candidates import generate_recovery_candidates
from dependency.solver.recovery import plan_sku_recovery
from dependency.solver.optimization import optimize_recovery_allocation


def _commercial_totals(sku: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              COALESCE(SUM(qty),0),
              COALESCE(SUM(revenue_eur),0),
              COALESCE(SUM(gross_margin_eur),0),
              COALESCE(SUM(CASE WHEN priority=1 THEN qty ELSE 0 END),0),
              MIN(due_date)
            FROM fulfilment_commitments
            WHERE sku=%s
            """,
            (sku,),
        ).fetchone()
    return {
        "commitment_units": float(row[0] or 0),
        "revenue_eur": float(row[1] or 0),
        "gross_margin_eur": float(row[2] or 0),
        "priority_1_units": float(row[3] or 0),
        "earliest_due_date": row[4].isoformat() if row[4] else None,
    }


def _required_next_actions(plans: list[dict]) -> list[str]:
    actions = []
    mapping = {
        "SUPPLIER_CAPACITY_CONFIRMATION_REQUIRED": "CONFIRM_SUPPLIER_CAPACITY",
        "MATERIAL_PATH_CONFIRMATION_REQUIRED": "CONFIRM_MATERIAL_SOURCE_PATHS",
        "PLANNER_APPROVAL_REQUIRED": "REQUEST_PLANNER_APPROVAL",
        "SAFETY_STOCK_RELEASE_REQUIRES_APPROVAL": "REQUEST_PLANNER_APPROVAL",
        "SUBSTITUTION_QUANTITY_CHECK_REQUIRED": "VALIDATE_SUBSTITUTION_QUANTITY",
        "EXPEDITE_ACTION_REQUIRED": "REQUEST_PO_EXPEDITE",
        "PO_ETA_AFTER_CUSTOMER_NEED_DATE": "REPLAN_MATERIAL_ARRIVAL",
    }
    for plan in plans:
        if plan["decision"] == "REJECTED":
            continue
        for reason in plan.get("reasons", []):
            action = mapping.get(reason)
            if action and action not in actions:
                actions.append(action)
    return actions


def _shared_backup_conflicts(products: list[dict]) -> list[dict]:
    uses: dict[str, set[str]] = defaultdict(set)
    names: dict[str, str] = {}
    for product in products:
        sku = product["sku"]
        for plan in product["candidates"]:
            if plan["plan_type"] != "ASSEMBLY_REALLOCATION":
                continue
            if plan["decision"] == "REJECTED":
                continue
            facility_id = plan["evidence"]["backup_facility_id"]
            uses[facility_id].add(sku)
            names[facility_id] = plan["evidence"]["backup_facility_name"]

    return [
        {
            "resource_type": "BACKUP_ASSEMBLY_FACILITY",
            "facility_id": facility_id,
            "facility_name": names[facility_id],
            "candidate_skus": sorted(skus),
            "status": "CAPACITY_CONFLICT_CHECK_REQUIRED",
        }
        for facility_id, skus in sorted(uses.items())
        if len(skus) > 1
    ]


def plan_event_recovery(
    *,
    event_id: str,
    scenario_id: str,
    radius_km: float = 150.0,
) -> dict:
    """Create one event-level recovery portfolio from current database state.

    The function evaluates every SKU reached through explicit dependency edges.
    It does not require a caller to choose a product first.
    """
    impact = trace_business_event_impact(event_id=event_id, radius_km=radius_km)
    impacted_skus = [row["sku"] for row in impact.get("products", [])]

    products = []
    for sku in impacted_skus:
        conservative = plan_sku_recovery(
            scenario_id=scenario_id,
            sku=sku,
            release_safety_stock=False,
        )
        emergency = plan_sku_recovery(
            scenario_id=scenario_id,
            sku=sku,
            release_safety_stock=True,
        )
        risk = scenario_product_risk(
            scenario_id=scenario_id,
            sku=sku,
        )
        candidates = generate_recovery_candidates(
            scenario_id=scenario_id,
            sku=sku,
        )
        commercial = _commercial_totals(sku)

        allocation = conservative["allocation"]
        at_risk_revenue = max(
            0.0,
            commercial["revenue_eur"] - float(allocation["protected_revenue_eur"]),
        )
        at_risk_margin = max(
            0.0,
            commercial["gross_margin_eur"] - float(allocation["protected_margin_eur"]),
        )
        operationally_affected = bool(
            conservative["lost_primary_units"] > 0
            or conservative["shortage_units"] > 0
            or any(
                row["scenario_status"] in {"UNAVAILABLE", "DEGRADED"}
                for row in conservative["current_production"]
            )
        )

        optimized_allocation = (
            optimize_recovery_allocation(
                scenario_id=scenario_id,
                sku=sku,
                release_safety_stock=False,
                include_provisional=True,
            )
            if operationally_affected
            else None
        )

        products.append(
            {
                "sku": sku,
                "operationally_affected": operationally_affected,
                "state_version": conservative["state_version"],
                "risk": risk,
                "commercial": {
                    **commercial,
                    "protected_revenue_eur": allocation["protected_revenue_eur"],
                    "protected_margin_eur": allocation["protected_margin_eur"],
                    "at_risk_revenue_eur": round(at_risk_revenue, 2),
                    "at_risk_margin_eur": round(at_risk_margin, 2),
                },
                "conservative_plan": conservative,
                "emergency_plan": emergency,
                "candidates": candidates,
                "optimized_allocation": optimized_allocation,
                "required_next_actions": _required_next_actions(candidates),
            }
        )

    action_queue = []
    rejected_actions = []
    for product in products:
        sku = product["sku"]
        risk_score = float(product["risk"]["risk_score"])
        at_risk_margin = float(product["commercial"]["at_risk_margin_eur"])
        shortage = float(product["conservative_plan"]["shortage_units"])
        earliest_due = product["commercial"]["earliest_due_date"]

        for plan in product["candidates"]:
            item = {
                "sku": sku,
                "plan_id": plan["plan_id"],
                "plan_type": plan["plan_type"],
                "title": plan["title"],
                "decision": plan["decision"],
                "reasons": plan.get("reasons", []),
                "candidate_score": float(plan.get("score", 0)),
                "risk_score": risk_score,
                "shortage_units": shortage,
                "at_risk_margin_eur": at_risk_margin,
                "earliest_due_date": earliest_due,
            }
            if plan["decision"] == "REJECTED":
                if product["operationally_affected"]:
                    rejected_actions.append(item)
            elif product["operationally_affected"]:
                action_queue.append(item)

    action_queue.sort(
        key=lambda row: (
            0 if row["shortage_units"] > 0 else 1,
            0 if row["decision"] == "FEASIBLE" else 1,
            -row["risk_score"],
            -row["at_risk_margin_eur"],
            row["earliest_due_date"] or "9999-12-31",
            -row["candidate_score"],
            row["sku"],
            row["plan_id"],
        )
    )
    rejected_actions.sort(
        key=lambda row: (
            -row["risk_score"],
            -row["at_risk_margin_eur"],
            row["sku"],
            row["plan_id"],
        )
    )

    operational = [p for p in products if p["operationally_affected"]]
    exposure_only = [p for p in products if not p["operationally_affected"]]

    total_shortage = sum(
        float(p["conservative_plan"]["shortage_units"]) for p in products
    )
    total_at_risk_revenue = sum(
        float(p["commercial"]["at_risk_revenue_eur"]) for p in products
    )
    total_at_risk_margin = sum(
        float(p["commercial"]["at_risk_margin_eur"]) for p in products
    )
    optimized_protected_margin = sum(
        float(p["optimized_allocation"]["protected_margin_eur"])
        for p in operational
        if p.get("optimized_allocation")
    )
    optimized_transport_cost = sum(
        float(p["optimized_allocation"]["incremental_transport_cost_eur"])
        for p in operational
        if p.get("optimized_allocation")
    )
    requires_confirmation = any(
        p["conservative_plan"]["requires_supplier_confirmation"]
        or p["conservative_plan"].get("requires_material_confirmation", False)
        for p in products
    )

    if total_shortage > 0:
        portfolio_status = "SHORTAGE"
    elif requires_confirmation:
        portfolio_status = "PROVISIONAL"
    else:
        portfolio_status = "FEASIBLE"

    versions = sorted({p["state_version"] for p in products})
    return {
        "event_id": event_id,
        "scenario_id": scenario_id,
        "radius_km": radius_km,
        "portfolio_status": portfolio_status,
        "state_versions": versions,
        "impact": impact,
        "summary": {
            "exposed_sku_count": len(products),
            "operationally_affected_sku_count": len(operational),
            "exposure_only_sku_count": len(exposure_only),
            "total_conservative_shortage_units": round(total_shortage, 2),
            "total_at_risk_revenue_eur": round(total_at_risk_revenue, 2),
            "total_at_risk_margin_eur": round(total_at_risk_margin, 2),
            "optimized_protected_margin_eur": round(
                optimized_protected_margin,
                2,
            ),
            "optimized_incremental_transport_cost_eur": round(
                optimized_transport_cost,
                2,
            ),
            "optimized_net_protected_margin_eur": round(
                optimized_protected_margin - optimized_transport_cost,
                2,
            ),
        },
        "operationally_affected_skus": [p["sku"] for p in operational],
        "exposure_only_skus": [p["sku"] for p in exposure_only],
        "products": products,
        "action_queue": action_queue,
        "rejected_actions": rejected_actions,
        "shared_resource_conflicts": _shared_backup_conflicts(products),
        "ranking_rule": (
            "shortage first; feasible before conditional; then higher risk, "
            "higher margin at risk, earlier due date, and candidate score"
        ),
    }
