from __future__ import annotations

from datetime import date

from dependency.db.connection import connect
from dependency.graph.shared_dependencies import backup_independence
from dependency.solver.recovery import plan_sku_recovery


HARD_REJECTION_REASONS = {
    "BACKUP_FACILITY_UNAVAILABLE",
    "BACKUP_NOT_READY_BY_DUE_DATE",
    "BACKUP_CAPACITY_NOT_AVAILABLE",
    "SHARED_UPSTREAM_DEPENDENCY",
    "CRITICAL_MATERIAL_SOURCE_UNAVAILABLE",
}


def _product_name(sku: str) -> str:
    with connect() as conn:
        row = conn.execute(
            "SELECT name FROM products WHERE sku = %s",
            (sku,),
        ).fetchone()
    return row[0] if row else sku


def _substitution_candidates(sku: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              b.material_id,
              m.name,
              s.substitute_material_id,
              sm.name,
              s.approved,
              s.max_ratio,
              s.engineering_status,
              s.provenance_class
            FROM bom b
            JOIN materials m ON m.material_id = b.material_id
            JOIN substitutions s ON s.material_id = b.material_id
            JOIN materials sm ON sm.material_id = s.substitute_material_id
            WHERE b.sku = %s
            ORDER BY b.material_id, s.substitute_material_id
            """,
            (sku,),
        ).fetchall()

    plans = []
    for row in rows:
        reasons = []
        if not bool(row[4]):
            reasons.append("SUBSTITUTE_NOT_APPROVED")
        if row[6] != "APPROVED":
            reasons.append("ENGINEERING_VALIDATION_INCOMPLETE")

        plans.append(
            {
                "plan_id": f"PLAN-SUBSTITUTE-{row[0]}-{row[2]}",
                "plan_type": "MATERIAL_SUBSTITUTION",
                "title": f"Substitute {row[1]} with {row[3]}",
                "decision": "REJECTED" if reasons else "CONDITIONALLY_FEASIBLE",
                "reasons": reasons or ["SUBSTITUTION_QUANTITY_CHECK_REQUIRED"],
                "evidence": {
                    "sku": sku,
                    "material_id": row[0],
                    "material_name": row[1],
                    "substitute_material_id": row[2],
                    "substitute_material_name": row[3],
                    "approved": bool(row[4]),
                    "max_ratio": float(row[5] or 0),
                    "engineering_status": row[6],
                    "provenance_class": row[7],
                },
            }
        )
    return plans


def _purchase_order_candidates(sku: str, earliest_due: date) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              po.po_id,
              po.material_id,
              m.name,
              po.supplier_facility_id,
              f.name,
              po.qty,
              po.eta,
              po.status,
              po.provenance_class
            FROM bom b
            JOIN purchase_orders po ON po.material_id = b.material_id
            JOIN materials m ON m.material_id = po.material_id
            LEFT JOIN facilities f ON f.facility_id = po.supplier_facility_id
            WHERE b.sku = %s
              AND po.status IN ('confirmed','open','released','in_transit')
            ORDER BY po.eta, po.po_id
            """,
            (sku,),
        ).fetchall()

    plans = []
    for row in rows:
        eta = row[6].date() if hasattr(row[6], "date") else row[6]
        if eta is None:
            continue
        days_late = max(0, (eta - earliest_due).days)
        if days_late <= 0:
            decision = "FEASIBLE"
            reasons = []
            title = f"Use inbound PO {row[0]} for {row[2]}"
        else:
            decision = "CONDITIONALLY_FEASIBLE"
            reasons = ["PO_ETA_AFTER_CUSTOMER_NEED_DATE", "EXPEDITE_ACTION_REQUIRED"]
            title = f"Expedite PO {row[0]} for {row[2]}"

        plans.append(
            {
                "plan_id": f"PLAN-PO-{row[0]}",
                "plan_type": "PURCHASE_ORDER",
                "title": title,
                "decision": decision,
                "reasons": reasons,
                "evidence": {
                    "sku": sku,
                    "po_id": row[0],
                    "material_id": row[1],
                    "material_name": row[2],
                    "supplier_facility_id": row[3],
                    "supplier_facility_name": row[4],
                    "qty": float(row[5]),
                    "eta": eta.isoformat(),
                    "earliest_due_date": earliest_due.isoformat(),
                    "days_late": days_late,
                    "status": row[7],
                    "provenance_class": row[8],
                },
            }
        )
    return plans


def _backup_candidate(
    *,
    sku: str,
    backup: dict,
    affected_current_facilities: list[str],
    base_gap_units: float,
) -> dict:
    reasons: list[str] = []
    shared_dependencies: list[dict] = []

    if backup["scenario_status"] == "UNAVAILABLE":
        reasons.append("BACKUP_FACILITY_UNAVAILABLE")
    if not backup["due_feasible"]:
        reasons.append("BACKUP_NOT_READY_BY_DUE_DATE")
    if backup["capacity_status"] != "available" or backup["available_capacity_units"] <= 0:
        reasons.append("BACKUP_CAPACITY_NOT_AVAILABLE")
    if backup.get("material_path_blocked"):
        reasons.append("CRITICAL_MATERIAL_SOURCE_UNAVAILABLE")
    if backup.get("requires_material_confirmation"):
        reasons.append("MATERIAL_PATH_CONFIRMATION_REQUIRED")

    for primary_facility_id in affected_current_facilities:
        independence = backup_independence(
            sku=sku,
            primary_facility_id=primary_facility_id,
            backup_facility_id=backup["facility_id"],
        )
        if not independence["independent"]:
            shared_dependencies.extend(independence["shared_dependencies"])

    if shared_dependencies:
        reasons.append("SHARED_UPSTREAM_DEPENDENCY")

    available = float(backup["available_capacity_units"])
    residual_shortage = max(0.0, float(base_gap_units) - available)
    coverage_units = min(float(base_gap_units), available)
    coverage_ratio = 1.0 if base_gap_units <= 0 else min(1.0, coverage_units / base_gap_units)

    if backup["requires_supplier_confirmation"]:
        reasons.append("SUPPLIER_CAPACITY_CONFIRMATION_REQUIRED")
    if residual_shortage > 0:
        reasons.append("RESIDUAL_SHORTAGE")

    hard_rejected = any(reason in HARD_REJECTION_REASONS for reason in reasons)
    if hard_rejected:
        decision = "REJECTED"
    elif (
        residual_shortage > 0
        or backup["requires_supplier_confirmation"]
        or backup.get("requires_material_confirmation")
    ):
        decision = "CONDITIONALLY_FEASIBLE"
    else:
        decision = "FEASIBLE"

    return {
        "plan_id": f"PLAN-BACKUP-{backup['facility_id']}",
        "plan_type": "ASSEMBLY_REALLOCATION",
        "title": f"Reallocate {sku} to {backup['facility_name']}",
        "decision": decision,
        "reasons": list(dict.fromkeys(reasons)),
        "score": round(
            (coverage_ratio * 100)
            - (10 if backup["requires_supplier_confirmation"] else 0)
            - (10 if backup.get("requires_material_confirmation") else 0)
            - (2 * float(backup["setup_lead_days"]))
            - (35 if shared_dependencies else 0),
            1,
        ),
        "evidence": {
            "sku": sku,
            "backup_facility_id": backup["facility_id"],
            "backup_facility_name": backup["facility_name"],
            "role": backup["role"],
            "scenario_status": backup["scenario_status"],
            "status_confirmed": backup["status_confirmed"],
            "setup_lead_days": backup["setup_lead_days"],
            "ready_date": backup["ready_date"],
            "earliest_due_date": backup["earliest_due_date"],
            "available_capacity_units": available,
            "capacity_evidence_age_hours": backup["evidence_age_hours"],
            "base_gap_units": float(base_gap_units),
            "coverage_units": coverage_units,
            "coverage_ratio": round(coverage_ratio, 4),
            "residual_shortage_units": residual_shortage,
            "shared_dependency_count": len(shared_dependencies),
            "shared_dependencies": shared_dependencies,
            "material_path": backup.get("material_path"),
            "provenance_class": backup["provenance_class"],
        },
    }


def _split_backup_candidate(
    *,
    sku: str,
    backup_plans: list[dict],
    base_gap_units: float,
) -> dict | None:
    eligible = [
        p
        for p in backup_plans
        if not any(reason in HARD_REJECTION_REASONS for reason in p["reasons"])
        and p["evidence"]["available_capacity_units"] > 0
    ]
    if len(eligible) < 2 or base_gap_units <= 0:
        return None

    eligible.sort(
        key=lambda p: (
            "SUPPLIER_CAPACITY_CONFIRMATION_REQUIRED" in p["reasons"],
            "MATERIAL_PATH_CONFIRMATION_REQUIRED" in p["reasons"],
            -p["evidence"]["available_capacity_units"],
            p["evidence"]["setup_lead_days"],
            p["evidence"]["backup_facility_id"],
        )
    )

    remaining = float(base_gap_units)
    allocations = []
    selected_ids: list[str] = []
    requires_confirmation = False
    requires_material_confirmation = False

    for plan in eligible:
        if remaining <= 0:
            break

        candidate_id = plan["evidence"]["backup_facility_id"]

        # Do not combine two backups that share the same explicit upstream source.
        correlated = False
        for selected_id in selected_ids:
            pair = backup_independence(
                sku=sku,
                primary_facility_id=selected_id,
                backup_facility_id=candidate_id,
            )
            if not pair["independent"]:
                correlated = True
                break
        if correlated:
            continue

        capacity = float(plan["evidence"]["available_capacity_units"])
        allocated = min(remaining, capacity)
        if allocated <= 0:
            continue

        allocations.append(
            {
                "facility_id": candidate_id,
                "facility_name": plan["evidence"]["backup_facility_name"],
                "allocated_units": allocated,
                "available_capacity_units": capacity,
                "requires_supplier_confirmation": (
                    "SUPPLIER_CAPACITY_CONFIRMATION_REQUIRED" in plan["reasons"]
                ),
                "requires_material_confirmation": (
                    "MATERIAL_PATH_CONFIRMATION_REQUIRED" in plan["reasons"]
                ),
            }
        )
        selected_ids.append(candidate_id)
        requires_confirmation = requires_confirmation or allocations[-1][
            "requires_supplier_confirmation"
        ]
        requires_material_confirmation = (
            requires_material_confirmation
            or allocations[-1]["requires_material_confirmation"]
        )
        remaining -= allocated

    if len(allocations) < 2:
        return None

    reasons = []
    if requires_confirmation:
        reasons.append("SUPPLIER_CAPACITY_CONFIRMATION_REQUIRED")
    if requires_material_confirmation:
        reasons.append("MATERIAL_PATH_CONFIRMATION_REQUIRED")
    if remaining > 0:
        reasons.append("RESIDUAL_SHORTAGE")

    decision = (
        "FEASIBLE"
        if remaining <= 0
        and not requires_confirmation
        and not requires_material_confirmation
        else "CONDITIONALLY_FEASIBLE"
    )

    return {
        "plan_id": "PLAN-SPLIT-BACKUPS",
        "plan_type": "SPLIT_REALLOCATION",
        "title": f"Split {sku} across independent approved backups",
        "decision": decision,
        "reasons": reasons,
        "score": round(
            (100 if remaining <= 0 else max(0.0, 100 * (1 - remaining / base_gap_units)))
            - (10 if requires_confirmation else 0)
            - (10 if requires_material_confirmation else 0),
            1,
        ),
        "evidence": {
            "sku": sku,
            "base_gap_units": float(base_gap_units),
            "allocations": allocations,
            "residual_shortage_units": max(0.0, remaining),
            "requires_supplier_confirmation": requires_confirmation,
            "requires_material_confirmation": requires_material_confirmation,
        },
    }


def generate_recovery_candidates(
    *,
    scenario_id: str,
    sku: str,
) -> list[dict]:
    """Generate recovery actions from current database state.

    No facility, material, product, or substitute identifier is embedded in this
    function. Candidate actions are discovered from product_facilities, BOM,
    substitutions, purchase orders, inventory, scenario state, and supplier
    capacity.
    """

    product_name = _product_name(sku)
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

    base_gap_units = max(
        0.0,
        float(conservative["demand_units"])
        - float(conservative["inventory"]["usable_inventory_units"])
        - float(conservative["available_current_production_units"]),
    )

    affected_current_facilities = [
        row["facility_id"]
        for row in conservative["current_production"]
        if row["scenario_status"] in {"UNAVAILABLE", "DEGRADED"}
        or float(row["available_units"]) < float(row["planned_units"])
    ]
    if not affected_current_facilities:
        affected_current_facilities = [
            row["facility_id"] for row in conservative["current_production"]
        ]

    plans: list[dict] = []

    backup_plans = [
        _backup_candidate(
            sku=sku,
            backup=backup,
            affected_current_facilities=affected_current_facilities,
            base_gap_units=base_gap_units,
        )
        for backup in conservative["backup_candidates"]
    ]
    plans.extend(backup_plans)

    split = _split_backup_candidate(
        sku=sku,
        backup_plans=backup_plans,
        base_gap_units=base_gap_units,
    )
    if split:
        plans.append(split)

    plans.extend(_substitution_candidates(sku))

    safety_stock_improvement = max(
        0.0,
        float(conservative["shortage_units"]) - float(emergency["shortage_units"]),
    )
    if float(emergency["inventory"]["safety_stock_units"]) > 0:
        reasons = ["PLANNER_APPROVAL_REQUIRED"]
        if emergency["requires_supplier_confirmation"]:
            reasons.append("SUPPLIER_CAPACITY_CONFIRMATION_REQUIRED")
        if emergency["shortage_units"] > 0:
            reasons.append("RESIDUAL_SHORTAGE")

        plans.append(
            {
                "plan_id": "PLAN-RELEASE-SAFETY-STOCK",
                "plan_type": "INVENTORY_POLICY",
                "title": f"Release protected safety stock for {product_name}",
                "decision": (
                    "CONDITIONALLY_FEASIBLE"
                    if safety_stock_improvement > 0
                    else "REJECTED"
                ),
                "reasons": (
                    reasons
                    if safety_stock_improvement > 0
                    else ["NO_SHORTAGE_IMPROVEMENT"]
                ),
                "score": round(safety_stock_improvement, 1),
                "evidence": {
                    "sku": sku,
                    "safety_stock_units": emergency["inventory"]["safety_stock_units"],
                    "safety_stock_used_units": emergency["inventory"][
                        "safety_stock_used_units"
                    ],
                    "shortage_before_units": conservative["shortage_units"],
                    "shortage_after_units": emergency["shortage_units"],
                    "shortage_reduction_units": safety_stock_improvement,
                    "requires_planner_approval": True,
                },
            }
        )

    earliest_due = min(
        date.fromisoformat(row["earliest_due_date"])
        for row in conservative["backup_candidates"]
        if row.get("earliest_due_date")
    ) if conservative["backup_candidates"] else None

    if earliest_due is None:
        with connect() as conn:
            row = conn.execute(
                "SELECT MIN(due_date) FROM fulfilment_commitments WHERE sku = %s",
                (sku,),
            ).fetchone()
        earliest_due = row[0] if row and row[0] else None

    if earliest_due:
        plans.extend(_purchase_order_candidates(sku, earliest_due))

    decision_rank = {
        "FEASIBLE": 0,
        "CONDITIONALLY_FEASIBLE": 1,
        "REJECTED": 2,
    }
    plans.sort(
        key=lambda p: (
            decision_rank.get(p["decision"], 9),
            -float(p.get("score", 0)),
            p["plan_id"],
        )
    )

    return plans
