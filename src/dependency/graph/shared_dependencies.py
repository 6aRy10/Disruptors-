from __future__ import annotations

from dependency.db.connection import connect


def shared_material_dependencies(
    *,
    sku: str,
    facility_a: str,
    facility_b: str,
) -> list[dict]:
    """Return upstream material sources shared by two assembly facilities.

    These edges are private digital-twin relationships. They are not inferred
    from public adidas supplier disclosure.
    """
    sql = """
        SELECT
          a.material_id,
          m.name AS material_name,
          a.source_facility_id,
          sf.name AS source_facility_name,
          a.provenance_class
        FROM material_allocations a
        JOIN material_allocations b
          ON b.sku = a.sku
         AND b.material_id = a.material_id
         AND b.source_facility_id = a.source_facility_id
        JOIN materials m ON m.material_id = a.material_id
        JOIN facilities sf ON sf.facility_id = a.source_facility_id
        WHERE a.sku = %s
          AND a.destination_facility_id = %s
          AND b.destination_facility_id = %s
          AND a.approved = true
          AND b.approved = true
        ORDER BY a.material_id, a.source_facility_id
    """
    with connect() as conn:
        rows = conn.execute(sql, (sku, facility_a, facility_b)).fetchall()

    return [
        {
            "sku": sku,
            "facility_a": facility_a,
            "facility_b": facility_b,
            "material_id": r[0],
            "material_name": r[1],
            "shared_source_facility_id": r[2],
            "shared_source_facility_name": r[3],
            "provenance_class": r[4],
            "resilience_warning": "SHARED_UPSTREAM_DEPENDENCY",
        }
        for r in rows
    ]


def backup_independence(
    *,
    sku: str,
    primary_facility_id: str,
    backup_facility_id: str,
) -> dict:
    shared = shared_material_dependencies(
        sku=sku,
        facility_a=primary_facility_id,
        facility_b=backup_facility_id,
    )
    return {
        "sku": sku,
        "primary_facility_id": primary_facility_id,
        "backup_facility_id": backup_facility_id,
        "independent": len(shared) == 0,
        "shared_dependency_count": len(shared),
        "shared_dependencies": shared,
        "decision": (
            "PASS_INDEPENDENT_BACKUP"
            if not shared
            else "REJECT_CORRELATED_BACKUP"
        ),
    }
