"""Read-only priority-based material repair for jointly allocated production.

The factory solver chooses order/factory assignments first. This stage limits
their backup-production units against shared modeled material-source capacity.
It is NOT a global material/factory optimum and is never execution approval.
"""
from __future__ import annotations
from collections import defaultdict
from math import floor, isfinite


def _load_rows(allocations):
    from dependency.db.connection import connect
    routes = {(str(a["sku"]), str(a["resource_id"])) for a in allocations
              if a.get("resource_type") == "BACKUP_ASSEMBLY" and int(a["units"]) > 0}
    if not routes:
        return [], []
    skus = sorted({sku for sku, _ in routes})
    facilities = sorted({facility for _, facility in routes})
    with connect() as conn:
        sources = conn.execute("""
            SELECT ma.sku,ma.destination_facility_id,ma.material_id,
                   ma.source_facility_id,b.qty_per_unit,ma.allocation_share,
                   ms.weekly_capacity_units
            FROM material_allocations ma
            JOIN bom b ON b.sku=ma.sku AND b.material_id=ma.material_id
            LEFT JOIN material_sources ms ON
                 ms.material_id=ma.material_id AND ms.facility_id=ma.source_facility_id
                 AND ms.approved=true
            WHERE ma.approved=true AND ma.sku=ANY(%s)
              AND ma.destination_facility_id=ANY(%s)
            ORDER BY ma.sku,ma.destination_facility_id,ma.material_id,
                     ma.source_facility_id
        """, (skus, facilities)).fetchall()
        bom = conn.execute(
            "SELECT sku,material_id,qty_per_unit FROM bom WHERE sku=ANY(%s) "
            "ORDER BY sku,material_id", (skus,)
        ).fetchall()
    return list(sources), list(bom)


def allocate_shared_materials(*, allocations, source_rows=None, bom_rows=None):
    """Deduct each (material,source) limit once across all SKUs.

    source_rows: sku,destination,material,source,qty_per_unit,
                 allocation_share,modeled_weekly_capacity.
    Missing BOM/source links block an allocation. Unknown source capacity is
    explicitly provisional, not treated as a confirmed quantity. Production
    from existing inventory is not charged for manufacturing materials again.
    """
    if (source_rows is None) != (bom_rows is None):
        raise ValueError("Provide both source_rows and bom_rows, or neither.")
    if source_rows is None:
        source_rows, bom_rows = _load_rows(allocations)

    backups = {(str(a["sku"]), str(a["resource_id"])) for a in allocations
               if a.get("resource_type") == "BACKUP_ASSEMBLY" and int(a["units"]) > 0}
    bom = defaultdict(dict)
    for sku, material, qty in bom_rows:
        value = float(qty)
        if not isfinite(value) or value <= 0:
            raise ValueError("BOM quantities must be positive and finite.")
        bom[str(sku)][str(material)] = value

    routes = defaultdict(dict)
    caps = {}
    users = defaultdict(set)
    for sku, destination, material, source, qty, share, weekly in source_rows:
        route = (str(sku), str(destination))
        if route not in backups:
            continue
        material, source = str(material), str(source)
        fraction = float(share)
        if not isfinite(fraction) or not 0 < fraction <= 1:
            raise ValueError("Material shares must be within (0,1].")
        if abs(float(qty) - bom[route[0]].get(material, -1)) > 1e-7:
            raise ValueError("Allocation BOM quantity differs from product BOM.")
        key = (material, source)
        old = routes[route].get(key)
        if old is not None and abs(old - fraction) > 1e-8:
            raise ValueError("Conflicting duplicate source shares.")
        routes[route][key] = fraction
        users[key].add(route[0])
        if weekly is not None:
            limit = float(weekly)
            if not isfinite(limit) or limit < 0:
                raise ValueError("Modeled weekly capacity must be nonnegative and finite.")
            caps[key] = min(caps.get(key, limit), limit)

    missing_routes = []
    needs_by_route = {}
    for route in sorted(backups):
        sku, destination = route
        requirements, missing = [], []
        if not bom.get(sku):
            missing.append("BOM_NOT_FOUND")
        for material, units_per in sorted(bom.get(sku, {}).items()):
            shares = [(src, fraction) for (mat, src), fraction in routes[route].items()
                      if mat == material]
            if not shares or abs(sum(frac for _, frac in shares) - 1) > 1e-5:
                missing.append(material)
            for src, frac in sorted(shares):
                requirements.append(((material, src), units_per * frac))
        if missing:
            missing_routes.append({
                "sku": sku, "facility_id": destination,
                "missing_or_incomplete_materials": sorted(missing),
            })
        needs_by_route[route] = (requirements, bool(missing))

    available = caps.copy()
    usage = defaultdict(float)
    unknown = set()
    sku_totals = defaultdict(int)
    lost_orders = defaultdict(int)
    repairs = []
    original_total = sum(int(a["units"]) for a in allocations)
    feasible_total = 0
    # The base flow made the original assignments. This repair only reduces
    # them. Prioritize urgent commitments, then cost-adjusted unit margin.
    ordered = sorted(enumerate(allocations), key=lambda pair: (
        int(pair[1].get("priority", 999)),
        -(float(pair[1].get("unit_margin_eur", 0)) -
          float(pair[1].get("transport_cost_eur_per_unit", 0))),
        str(pair[1]["sku"]), str(pair[1]["order_id"]),
        str(pair[1]["resource_id"]), pair[0],
    ))
    for _, allocation in ordered:
        planned = int(allocation["units"])
        if planned < 0:
            raise ValueError("Allocation units must be nonnegative.")
        allowed, reasons = planned, []
        if allocation.get("resource_type") == "BACKUP_ASSEMBLY" and planned:
            requirements, missing = needs_by_route[(
                str(allocation["sku"]), str(allocation["resource_id"])
            )]
            if missing:
                allowed = 0
                reasons.append("INCOMPLETE_MATERIAL_ROUTE")
            else:
                for key, per_unit in requirements:
                    if key not in available:
                        unknown.add(key)
                    else:
                        bound = max(0, floor((available[key] + 1e-8) / per_unit))
                        if bound < allowed:
                            allowed = bound
                            reasons.append(key[0] + " / " + key[1])
                # Deduct only AFTER finding the limiting input. This prevents
                # partially charging materials for unbuildable product units.
                for key, per_unit in requirements:
                    if key in available:
                        material_units = allowed * per_unit
                        available[key] = max(0, available[key] - material_units)
                        usage[key] += material_units
        sku = str(allocation["sku"])
        order = str(allocation["order_id"])
        feasible_total += allowed
        sku_totals[sku] += allowed
        lost_orders[(sku, order)] += planned - allowed
        repairs.append({
            "sku": sku, "order_id": order,
            "resource_id": str(allocation["resource_id"]),
            "resource_type": allocation["resource_type"],
            "priority": int(allocation.get("priority", 999)),
            "planned_units": planned, "material_feasible_units": allowed,
            "reduced_units": planned - allowed,
            "limiting_materials": sorted(set(reasons)),
        })
    source_usage = []
    for key in sorted(set(users) | set(caps)):
        limit = caps.get(key)
        used = usage[key]
        source_usage.append({
            "material_id": key[0], "source_facility_id": key[1],
            "competing_skus": sorted(users[key]),
            "modeled_weekly_capacity_units": limit,
            "allocated_material_units": round(used, 5),
            "remaining_modeled_units": round(max(0, limit-used), 5)
                                      if limit is not None else None,
            "provenance_class": "SIMULATED_PRIVATE",
        })
    reduced = original_total - feasible_total
    return {
        "method": "PRIORITY_GREEDY_SHARED_BOM_CAPACITY_REPAIR",
        "globally_optimal": False,
        "execution_materials_verified": not backups,
        "status": ("INCOMPLETE_MATERIAL_ROUTE" if missing_routes else
                   "MODELED_MATERIAL_SHORTAGE" if reduced else
                   "MODELED_CAPACITY_UNKNOWN" if unknown else
                   "MODELED_MATERIAL_FEASIBLE_UNVERIFIED" if backups else
                   "NO_BACKUP_MATERIAL_NEEDED"),
        "input_protected_units": original_total,
        "material_feasible_units": feasible_total,
        "material_reduced_units": reduced,
        "protected_by_sku_after_materials": dict(sorted(sku_totals.items())),
        "allocation_adjustments": sorted(
            repairs, key=lambda a: (a["sku"], a["order_id"], a["resource_id"])),
        "modeled_source_usage": source_usage,
        "missing_material_routes": missing_routes,
        "unverified_source_capacities": [
            {"material_id": m, "source_facility_id": s} for m, s in sorted(unknown)],
        "orders_reduced": [
            {"sku": sku, "order_id": order, "units": units}
            for (sku, order), units in sorted(lost_orders.items()) if units
        ],
        "rule": (
            "Model capacity is not supplier confirmation. One weekly source "
            "limit is shared across products. This is a feasibility repair, "
            "not a global optimum or proof of on-time arrival."
        ),
    }
