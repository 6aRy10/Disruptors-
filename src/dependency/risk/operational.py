from __future__ import annotations

from dependency.db.connection import connect
from dependency.risk.scoring import band, event_business_risk
from dependency.solver.recovery import plan_sku_recovery


def _urgency_score(days_to_due: int) -> float:
    if days_to_due <= 2:
        return 100.0
    if days_to_due <= 5:
        return 85.0
    if days_to_due <= 9:
        return 70.0
    if days_to_due <= 14:
        return 55.0
    if days_to_due <= 30:
        return 35.0
    return 20.0


def scenario_product_risk(*, scenario_id: str, sku: str) -> dict:
    plan = plan_sku_recovery(
        scenario_id=scenario_id,
        sku=sku,
        release_safety_stock=False,
    )

    demand = max(1.0, float(plan["demand_units"]))
    lost_ratio = min(1.0, float(plan["lost_primary_units"]) / demand)
    shortage_ratio = min(1.0, float(plan["shortage_units"]) / demand)

    disruption_severity = 40.0
    if any(r["scenario_status"] == "DEGRADED" for r in plan["current_production"]):
        disruption_severity = 70.0
    if any(r["scenario_status"] == "UNAVAILABLE" for r in plan["current_production"]):
        disruption_severity = 90.0

    dependency_criticality = round(lost_ratio * 100.0, 1)

    with connect() as conn:
        earliest_due = conn.execute(
            "SELECT MIN(due_date) FROM fulfilment_commitments WHERE sku = %s",
            (sku,),
        ).fetchone()[0]
        scenario_as_of = conn.execute(
            "SELECT as_of FROM scenarios WHERE scenario_id = %s",
            (scenario_id,),
        ).fetchone()[0]

    days_to_due = max(0, (earliest_due - scenario_as_of).days)
    time_urgency = _urgency_score(days_to_due)

    # Even a small shortage matters commercially because the exposed SKU has
    # customer commitments. The score rises sharply as shortage grows.
    commercial_exposure = min(100.0, 40.0 + (shortage_ratio * 100.0 * 1.3))

    recovery_difficulty = 25.0
    if plan["requires_supplier_confirmation"]:
        recovery_difficulty += 25.0
    if plan.get("requires_material_confirmation"):
        recovery_difficulty += 20.0
    if not plan["selected_backup"]:
        recovery_difficulty += 30.0
    recovery_difficulty += min(20.0, shortage_ratio * 100.0 * 0.5)
    recovery_difficulty = min(100.0, recovery_difficulty)

    score = event_business_risk(
        disruption_severity=disruption_severity,
        dependency_criticality=dependency_criticality,
        time_urgency=time_urgency,
        commercial_exposure=commercial_exposure,
        recovery_difficulty=recovery_difficulty,
    )

    return {
        "scenario_id": scenario_id,
        "sku": sku,
        "state_version": plan["state_version"],
        "risk_score": score,
        "risk_band": band(score),
        "factors": {
            "disruption_severity": disruption_severity,
            "dependency_criticality": dependency_criticality,
            "time_urgency": time_urgency,
            "commercial_exposure": round(commercial_exposure, 1),
            "recovery_difficulty": round(recovery_difficulty, 1),
        },
        "evidence": {
            "days_to_earliest_due": days_to_due,
            "lost_primary_units": plan["lost_primary_units"],
            "demand_units": plan["demand_units"],
            "shortage_units": plan["shortage_units"],
            "shortage_ratio_pct": round(shortage_ratio * 100.0, 1),
            "requires_supplier_confirmation": plan["requires_supplier_confirmation"],
            "requires_material_confirmation": plan.get(
                "requires_material_confirmation",
                False,
            ),
            "selected_backup_facility_id": (
                plan["selected_backup"]["facility_id"]
                if plan["selected_backup"]
                else None
            ),
        },
        "plan_status": plan["plan_status"],
    }
