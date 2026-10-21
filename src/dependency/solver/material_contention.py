"""Portfolio-wide upstream material contention audit.

This deliberately does NOT invent confirmed materials. A BOM's sourcing share
and modeled weekly source capacity are simulated private assumptions. The audit
detects contention across independently viable backup production moves; it
prevents the portfolio from claiming execution-readiness without confirmation.
"""
from __future__ import annotations

from collections import defaultdict

from dependency.db.connection import connect


def evaluate_material_contention(
    *,
    allocations: list[dict],
    source_rows: list[tuple] | None = None,
) -> dict:
    """Audit planned backup manufacturing against shared source/material nodes.

    Rows: sku, destination facility, material, source facility,
    BOM units per product, modeled allocation share, modeled weekly capacity.
    The observed modeled weekly capacity is never treated as confirmed supply.
    """
    backup_units = defaultdict(int)
    for allocation in allocations:
        if allocation.get("resource_type") == "BACKUP_ASSEMBLY":
            backup_units[(allocation["sku"],allocation["resource_id"])] += int(allocation["units"])
    if not backup_units:
        return {
            "status":"NO_BACKUP_PRODUCTION",
            "shared_source_count":0,
            "unconfirmed_shared_sources":[],
            "modeled_capacity_conflicts":[],
            "execution_materials_verified":True,
        }

    if source_rows is None:
        skus=sorted({sku for sku,_ in backup_units})
        facilities=sorted({fac for _,fac in backup_units})
        with connect() as conn:
            source_rows=conn.execute(
                """
                SELECT ma.sku,ma.destination_facility_id,ma.material_id,
                       ma.source_facility_id,b.qty_per_unit,ma.allocation_share,
                       ms.weekly_capacity_units
                FROM material_allocations ma
                JOIN bom b ON b.sku=ma.sku AND b.material_id=ma.material_id
                LEFT JOIN material_sources ms
                  ON ms.material_id=ma.material_id
                 AND ms.facility_id=ma.source_facility_id AND ms.approved=true
                WHERE ma.approved=true
                  AND ma.sku=ANY(%s)
                  AND ma.destination_facility_id=ANY(%s)
                """,
                (skus,facilities),
            ).fetchall()

    usage=defaultdict(lambda:{"demand_units":0.0,"sku_set":set(),"weekly_caps":[]})
    modeled_pairs=set()
    for sku,facility,material,source,qty_per,share,weekly_capacity in source_rows:
        quantity=backup_units.get((sku,facility),0)
        if quantity<=0:
            continue
        modeled_pairs.add((sku,facility))
        key=(material,source)
        item=usage[key]
        item["demand_units"]+=quantity*float(qty_per or 0)*float(share or 0)
        item["sku_set"].add(sku)
        if weekly_capacity is not None:
            item["weekly_caps"].append(float(weekly_capacity))

    shared=[]
    conflicts=[]
    for (material,source),record in sorted(usage.items()):
        if len(record["sku_set"])<=1:
            continue
        weekly=min(record["weekly_caps"]) if record["weekly_caps"] else None
        entry={
            "material_id":material,
            "source_facility_id":source,
            "competing_skus":sorted(record["sku_set"]),
            "planned_material_units":round(record["demand_units"],3),
            "modeled_weekly_capacity_units":weekly,
            "evidence_status":"SIMULATED_PRIVATE_UNCONFIRMED",
        }
        shared.append(entry)
        if weekly is not None and record["demand_units"]>weekly+1e-8:
            conflicts.append({
                **entry,
                "modeled_shortfall_units":round(record["demand_units"]-weekly,3),
                "reason":"JOINT_MODELED_SOURCE_CAP_EXCEEDED",
            })
    unmodeled=sorted(backup_units.keys()-modeled_pairs)
    return {
        "status": (
            "MODELED_SHARED_MATERIAL_SHORTFALL" if conflicts else
            "SHARED_MATERIAL_EVIDENCE_REQUIRED" if shared or unmodeled else
            "NO_SHARED_UPSTREAM_CONTENTION"
        ),
        "shared_source_count":len(shared),
        "unconfirmed_shared_sources":shared,
        "modeled_capacity_conflicts":conflicts,
        "unmodeled_backup_routes":[{"sku":s,"facility_id":f} for s,f in unmodeled],
        "execution_materials_verified":not(shared or unmodeled),
        "evidence_rule":"Weekly material capacities are modeled, not supplier-confirmed.",
    }
