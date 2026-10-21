from __future__ import annotations

from dependency.db.connection import connect
from dependency.graph.shared_dependencies import backup_independence
from dependency.solver.recovery import plan_sku_recovery


def _scenario_status(scenario_id: str, facility_id: str) -> str:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT status
            FROM scenario_facility_state
            WHERE scenario_id = %s AND facility_id = %s
            """,
            (scenario_id, facility_id),
        ).fetchone()
    return row[0] if row else "AVAILABLE"


def _substitution_status(material_id: str, substitute_material_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT approved,max_ratio,engineering_status,provenance_class
            FROM substitutions
            WHERE material_id = %s AND substitute_material_id = %s
            """,
            (material_id, substitute_material_id),
        ).fetchone()
    if not row:
        return {
            "exists": False,
            "approved": False,
            "max_ratio": 0.0,
            "engineering_status": "NOT_REGISTERED",
            "provenance_class": None,
        }
    return {
        "exists": True,
        "approved": bool(row[0]),
        "max_ratio": float(row[1] or 0),
        "engineering_status": row[2],
        "provenance_class": row[3],
    }


def generate_recovery_candidates(
    *,
    scenario_id: str,
    sku: str,
    primary_facility_id: str = "ADI26-0226",
    nominal_backup_id: str = "ADI26-0225",
    independent_backup_id: str = "ADI26-0240",
) -> list[dict]:
    """Return three judge-facing recovery candidates with explicit pass/fail reasons."""

    shared = backup_independence(
        sku=sku,
        primary_facility_id=primary_facility_id,
        backup_facility_id=nominal_backup_id,
    )
    nominal_status = _scenario_status(scenario_id, nominal_backup_id)

    nominal_reasons = []
    if nominal_status == "UNAVAILABLE":
        nominal_reasons.append("BACKUP_FACILITY_UNAVAILABLE")
    if not shared["independent"]:
        nominal_reasons.append("SHARED_UPSTREAM_DEPENDENCY")

    substitute = _substitution_status(
        "MAT-RUBBER-OUTSOLE",
        "MAT-RUBBER-OUTSOLE-B",
    )
    substitute_reasons = []
    if not substitute["approved"]:
        substitute_reasons.append("SUBSTITUTE_NOT_APPROVED")
    if substitute["engineering_status"] != "APPROVED":
        substitute_reasons.append("ENGINEERING_VALIDATION_INCOMPLETE")

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

    recovery_reasons = []
    if emergency["requires_supplier_confirmation"]:
        recovery_reasons.append("SUPPLIER_CAPACITY_CONFIRMATION_REQUIRED")
    if emergency["requires_planner_approval"]:
        recovery_reasons.append("SAFETY_STOCK_RELEASE_REQUIRES_APPROVAL")
    if emergency["shortage_units"] > 0:
        recovery_reasons.append("RESIDUAL_SHORTAGE")

    if emergency["shortage_units"] > 0:
        recovery_decision = "INFEASIBLE"
    elif emergency["requires_supplier_confirmation"] or emergency["requires_planner_approval"]:
        recovery_decision = "CONDITIONALLY_FEASIBLE"
    else:
        recovery_decision = "FEASIBLE"

    return [
        {
            "plan_id": "PLAN-A-NOMINAL-BACKUP",
            "title": "Move JI2993 to nominal PGD backup",
            "decision": "REJECTED" if nominal_reasons else "FEASIBLE",
            "reasons": nominal_reasons,
            "evidence": {
                "backup_facility_id": nominal_backup_id,
                "scenario_status": nominal_status,
                "shared_dependency_count": shared["shared_dependency_count"],
                "shared_dependencies": shared["shared_dependencies"],
            },
        },
        {
            "plan_id": "PLAN-B-SUBSTITUTE-OUTSOLE",
            "title": "Use alternate outsole material",
            "decision": "REJECTED" if substitute_reasons else "FEASIBLE",
            "reasons": substitute_reasons,
            "evidence": {
                "material_id": "MAT-RUBBER-OUTSOLE",
                "substitute_material_id": "MAT-RUBBER-OUTSOLE-B",
                **substitute,
            },
        },
        {
            "plan_id": "PLAN-C-INDEPENDENT-BACKUP",
            "title": "Use independent backup plus finished inventory",
            "decision": recovery_decision,
            "reasons": recovery_reasons,
            "evidence": {
                "backup_facility_id": (
                    emergency["selected_backup"]["facility_id"]
                    if emergency["selected_backup"]
                    else independent_backup_id
                ),
                "state_version": emergency["state_version"],
                "demand_units": emergency["demand_units"],
                "preserve_safety_stock_shortage_units": conservative["shortage_units"],
                "emergency_total_available_units": emergency["total_available_units"],
                "emergency_shortage_units": emergency["shortage_units"],
                "safety_stock_used_units": emergency["inventory"]["safety_stock_used_units"],
                "requires_supplier_confirmation": emergency["requires_supplier_confirmation"],
                "requires_planner_approval": emergency["requires_planner_approval"],
                "protected_revenue_eur": emergency["allocation"]["protected_revenue_eur"],
                "protected_margin_eur": emergency["allocation"]["protected_margin_eur"],
            },
        },
    ]
