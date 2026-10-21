from __future__ import annotations

from dependency.db.connection import connect


def assess_material_paths(
    *,
    scenario_id: str,
    sku: str,
    destination_facility_id: str,
) -> dict:
    """Assess whether the BOM has explicit, currently usable source paths.

    This function does not invent missing sourcing relationships. An unmodeled
    path is a confirmation requirement, not proof that supply is impossible.
    An explicitly unavailable sole source is a deterministic blocker.
    """
    with connect() as conn:
        bom_rows = conn.execute(
            """
            SELECT b.material_id,m.name,m.criticality,b.qty_per_unit,b.provenance_class
            FROM bom b
            JOIN materials m ON m.material_id=b.material_id
            WHERE b.sku=%s
            ORDER BY
              CASE WHEN m.criticality='critical' THEN 0
                   WHEN m.criticality='medium' THEN 1
                   ELSE 2 END,
              b.material_id
            """,
            (sku,),
        ).fetchall()

        allocation_rows = conn.execute(
            """
            SELECT
              ma.material_id,
              ma.source_facility_id,
              f.name,
              ma.allocation_share,
              ma.provenance_class,
              sfs.status,
              sfs.capacity_multiplier,
              sfs.confirmed,
              sfs.reason
            FROM material_allocations ma
            JOIN facilities f ON f.facility_id=ma.source_facility_id
            LEFT JOIN scenario_facility_state sfs
              ON sfs.scenario_id=%s
             AND sfs.facility_id=ma.source_facility_id
            WHERE ma.sku=%s
              AND ma.destination_facility_id=%s
              AND ma.approved=true
            ORDER BY ma.material_id,ma.source_facility_id
            """,
            (scenario_id, sku, destination_facility_id),
        ).fetchall()

    by_material: dict[str, list[dict]] = {}
    for row in allocation_rows:
        status = row[5] or "BASELINE_AVAILABLE_UNCONFIRMED"
        by_material.setdefault(row[0], []).append(
            {
                "source_facility_id": row[1],
                "source_facility_name": row[2],
                "allocation_share": float(row[3] or 0),
                "provenance_class": row[4],
                "scenario_status": status,
                "capacity_multiplier": (
                    float(row[6]) if row[6] is not None else 1.0
                ),
                "status_confirmed": bool(row[7]) if row[7] is not None else False,
                "reason": row[8],
            }
        )

    materials = []
    missing_materials = []
    blocked_materials = []
    unconfirmed_materials = []

    for row in bom_rows:
        material_id = row[0]
        sources = by_material.get(material_id, [])
        usable_sources = [
            s
            for s in sources
            if s["scenario_status"] not in {"UNAVAILABLE"}
            and s["capacity_multiplier"] > 0
        ]
        confirmed_usable_sources = [
            s for s in usable_sources if s["status_confirmed"]
        ]

        if not sources:
            state = "PATH_NOT_MODELED"
            missing_materials.append(material_id)
        elif not usable_sources:
            state = "BLOCKED_SOURCE_UNAVAILABLE"
            blocked_materials.append(material_id)
        elif not confirmed_usable_sources:
            state = "SOURCE_STATE_UNCONFIRMED"
            unconfirmed_materials.append(material_id)
        else:
            state = "CONFIRMED_USABLE_PATH"

        materials.append(
            {
                "material_id": material_id,
                "material_name": row[1],
                "criticality": row[2],
                "qty_per_unit": float(row[3]),
                "bom_provenance_class": row[4],
                "path_state": state,
                "sources": sources,
            }
        )

    critical_ids = {
        row[0] for row in bom_rows if str(row[2]).lower() == "critical"
    }
    blocked_critical = sorted(critical_ids.intersection(blocked_materials))
    missing_critical = sorted(critical_ids.intersection(missing_materials))

    blocked = bool(blocked_critical)
    requires_confirmation = bool(
        missing_materials or unconfirmed_materials
    )

    return {
        "scenario_id": scenario_id,
        "sku": sku,
        "destination_facility_id": destination_facility_id,
        "bom_material_count": len(bom_rows),
        "modeled_material_count": len(bom_rows) - len(missing_materials),
        "missing_material_ids": missing_materials,
        "missing_critical_material_ids": missing_critical,
        "blocked_material_ids": blocked_materials,
        "blocked_critical_material_ids": blocked_critical,
        "unconfirmed_material_ids": unconfirmed_materials,
        "blocked": blocked,
        "requires_confirmation": requires_confirmation,
        "decision": (
            "REJECT_BLOCKED_CRITICAL_SOURCE"
            if blocked
            else (
                "CONDITIONALLY_USABLE_REQUIRES_SOURCE_CONFIRMATION"
                if requires_confirmation
                else "PASS_MATERIAL_PATHS"
            )
        ),
        "materials": materials,
    }
