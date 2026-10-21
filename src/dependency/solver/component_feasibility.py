from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from math import floor

from dependency.db.connection import connect


ACTIVE_PO_STATUSES = {"confirmed", "released", "in_transit"}


def _scenario_context(scenario_id: str) -> tuple[date, dict[str, dict]]:
    with connect() as conn:
        scenario = conn.execute(
            "SELECT as_of FROM scenarios WHERE scenario_id=%s",
            (scenario_id,),
        ).fetchone()
        if not scenario:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")

        rows = conn.execute(
            """
            SELECT facility_id,status,capacity_multiplier,confirmed,reason
            FROM scenario_facility_state
            WHERE scenario_id=%s
            """,
            (scenario_id,),
        ).fetchall()

    state = {
        r[0]: {
            "status": r[1],
            "capacity_multiplier": float(r[2]),
            "confirmed": bool(r[3]),
            "reason": r[4],
        }
        for r in rows
    }
    return scenario[0], state


def _period_capacity(
    *,
    weekly_capacity: float,
    lead_time_days: int,
    as_of: date,
    need_by: date,
    multiplier: float,
) -> float:
    """Return modeled source capacity that can be ready by need_by.

    One weekly capacity window becomes available once the source lead time has
    elapsed. Additional complete seven-day windows add another weekly tranche.
    This is modeled capacity, not a supplier confirmation.
    """
    ready = as_of + timedelta(days=max(0, int(lead_time_days)))
    if ready > need_by:
        return 0.0
    extra_days = (need_by - ready).days
    windows = 1 + floor(extra_days / 7)
    return max(0.0, float(weekly_capacity)) * windows * max(0.0, multiplier)


def evaluate_component_feasibility(
    *,
    scenario_id: str,
    sku: str,
    destination_facility_id: str,
    production_units: float,
    need_by: date | str,
) -> dict:
    """Evaluate BOM component coverage for one production move.

    Confirmed coverage uses only material inventory and eligible inbound purchase
    orders. Modeled supplier capacity is shown separately and can make a plan
    provisional, but never silently becomes confirmed supply.

    A purchase order is eligible for this destination only when its supplier is
    an explicit approved material-allocation source for the SKU/facility.
    """
    if production_units < 0:
        raise ValueError("production_units must be >= 0")
    if isinstance(need_by, str):
        need_by = date.fromisoformat(need_by)

    as_of, scenario_state = _scenario_context(scenario_id)

    with connect() as conn:
        bom_rows = conn.execute(
            """
            SELECT
              b.material_id,m.name,m.uom,m.criticality,b.qty_per_unit,
              b.provenance_class
            FROM bom b
            JOIN materials m ON m.material_id=b.material_id
            WHERE b.sku=%s
            ORDER BY
              CASE WHEN lower(m.criticality)='critical' THEN 0
                   WHEN lower(m.criticality)='medium' THEN 1
                   ELSE 2 END,
              b.material_id
            """,
            (sku,),
        ).fetchall()
        if not bom_rows:
            raise ValueError(f"No BOM for sku={sku}")

        inventory_rows = conn.execute(
            """
            SELECT item_id,site_id,qty_on_hand,qty_reserved,safety_stock,
                   updated_at,provenance_class
            FROM inventory
            WHERE item_type IN ('material','raw_material','component')
              AND item_id IN (SELECT material_id FROM bom WHERE sku=%s)
            ORDER BY item_id,site_id
            """,
            (sku,),
        ).fetchall()

        allocation_rows = conn.execute(
            """
            SELECT
              ma.material_id,ma.source_facility_id,f.name,ma.allocation_share,
              ma.provenance_class,ms.lead_time_days,ms.weekly_capacity_units,
              ms.provenance_class
            FROM material_allocations ma
            JOIN facilities f ON f.facility_id=ma.source_facility_id
            LEFT JOIN material_sources ms
              ON ms.material_id=ma.material_id
             AND ms.facility_id=ma.source_facility_id
             AND ms.approved=true
            WHERE ma.sku=%s
              AND ma.destination_facility_id=%s
              AND ma.approved=true
            ORDER BY ma.material_id,ma.source_facility_id
            """,
            (sku, destination_facility_id),
        ).fetchall()

        po_rows = conn.execute(
            """
            SELECT
              po_id,material_id,supplier_facility_id,qty,eta,status,
              provenance_class
            FROM purchase_orders
            WHERE material_id IN (SELECT material_id FROM bom WHERE sku=%s)
            ORDER BY material_id,eta,po_id
            """,
            (sku,),
        ).fetchall()

        substitution_rows = conn.execute(
            """
            SELECT
              s.material_id,s.substitute_material_id,m.name,s.approved,
              s.max_ratio,s.engineering_status,s.provenance_class
            FROM substitutions s
            JOIN materials m ON m.material_id=s.substitute_material_id
            WHERE s.material_id IN (SELECT material_id FROM bom WHERE sku=%s)
            ORDER BY s.material_id,s.substitute_material_id
            """,
            (sku,),
        ).fetchall()

    inventory_by_material: dict[str, list[dict]] = defaultdict(list)
    for row in inventory_rows:
        usable = max(
            0.0,
            float(row[2]) - float(row[3]) - float(row[4]),
        )
        inventory_by_material[row[0]].append(
            {
                "site_id": row[1],
                "qty_on_hand": float(row[2]),
                "qty_reserved": float(row[3]),
                "safety_stock": float(row[4]),
                "usable_without_safety_stock": usable,
                "updated_at": row[5].isoformat() if row[5] else None,
                "provenance_class": row[6],
            }
        )

    allocations_by_material: dict[str, list[dict]] = defaultdict(list)
    allocated_source_ids: dict[str, set[str]] = defaultdict(set)
    for row in allocation_rows:
        facility_id = row[1]
        state = scenario_state.get(
            facility_id,
            {
                "status": "AVAILABLE",
                "capacity_multiplier": 1.0,
                "confirmed": False,
                "reason": None,
            },
        )
        weekly_capacity = float(row[6]) if row[6] is not None else None
        lead_days = int(row[5]) if row[5] is not None else None
        modeled_capacity = 0.0
        if (
            weekly_capacity is not None
            and lead_days is not None
            and state["status"] != "UNAVAILABLE"
        ):
            modeled_capacity = _period_capacity(
                weekly_capacity=weekly_capacity,
                lead_time_days=lead_days,
                as_of=as_of,
                need_by=need_by,
                multiplier=state["capacity_multiplier"],
            ) * float(row[3] or 0)

        record = {
            "source_facility_id": facility_id,
            "source_facility_name": row[2],
            "allocation_share": float(row[3] or 0),
            "allocation_provenance_class": row[4],
            "lead_time_days": lead_days,
            "weekly_capacity_units": weekly_capacity,
            "source_provenance_class": row[7],
            "scenario_status": state["status"],
            "scenario_status_confirmed": state["confirmed"],
            "scenario_reason": state["reason"],
            "modeled_capacity_by_need_date": modeled_capacity,
        }
        allocations_by_material[row[0]].append(record)
        allocated_source_ids[row[0]].add(facility_id)

    pos_by_material: dict[str, list[dict]] = defaultdict(list)
    for row in po_rows:
        eta_date = row[4].date() if row[4] else None
        eligible_source = row[2] in allocated_source_ids[row[1]]
        usable = bool(
            row[5] in ACTIVE_PO_STATUSES
            and eta_date is not None
            and eta_date <= need_by
            and eligible_source
        )
        pos_by_material[row[1]].append(
            {
                "po_id": row[0],
                "supplier_facility_id": row[2],
                "qty": float(row[3]),
                "eta": row[4].isoformat() if row[4] else None,
                "status": row[5],
                "eligible_explicit_source": eligible_source,
                "usable_by_need_date": usable,
                "provenance_class": row[6],
            }
        )

    substitutions_by_material: dict[str, list[dict]] = defaultdict(list)
    for row in substitution_rows:
        substitutions_by_material[row[0]].append(
            {
                "substitute_material_id": row[1],
                "substitute_material_name": row[2],
                "approved": bool(row[3]),
                "max_ratio": float(row[4] or 0),
                "engineering_status": row[5],
                "provenance_class": row[6],
            }
        )

    materials = []
    critical_failures = []
    critical_unknowns = []
    confirmation_requirements = []

    for row in bom_rows:
        material_id = row[0]
        required_qty = float(row[4]) * float(production_units)
        inv_rows = inventory_by_material.get(material_id, [])
        allocations = allocations_by_material.get(material_id, [])
        po_list = pos_by_material.get(material_id, [])

        inventory_qty = sum(
            x["usable_without_safety_stock"] for x in inv_rows
        )
        usable_po_qty = sum(
            x["qty"] for x in po_list if x["usable_by_need_date"]
        )

        # A PO from a source is already part of that source's total capacity.
        # For provisional supply, use the larger of committed inbound PO quantity
        # or modeled source capacity for each source, not the sum of both.
        po_by_source: dict[str, float] = defaultdict(float)
        for po in po_list:
            if po["usable_by_need_date"]:
                po_by_source[po["supplier_facility_id"]] += po["qty"]

        provisional_from_sources = 0.0
        source_capacity_unknown = False
        for source in allocations:
            source_id = source["source_facility_id"]
            modeled = source["modeled_capacity_by_need_date"]
            inbound = po_by_source.get(source_id, 0.0)
            provisional_from_sources += max(modeled, inbound)
            if (
                source["weekly_capacity_units"] is None
                or source["lead_time_days"] is None
                or not source["scenario_status_confirmed"]
            ):
                source_capacity_unknown = True

        confirmed_supply = inventory_qty + usable_po_qty
        provisional_supply = inventory_qty + provisional_from_sources

        approved_substitutions = [
            s
            for s in substitutions_by_material.get(material_id, [])
            if s["approved"] and s["engineering_status"] == "APPROVED"
        ]

        if required_qty <= confirmed_supply:
            status = "CONFIRMED_COVERED"
        elif allocations and provisional_supply >= required_qty:
            status = "PROVISIONAL_COVERED"
        elif not allocations:
            status = "SOURCE_PATH_NOT_MODELED"
        else:
            status = "PROVISIONAL_SHORTAGE"

        critical = str(row[3] or "").lower() == "critical"
        if critical and status == "PROVISIONAL_SHORTAGE":
            critical_failures.append(material_id)
        elif critical and status == "SOURCE_PATH_NOT_MODELED":
            critical_unknowns.append(material_id)

        if status in {"PROVISIONAL_COVERED", "SOURCE_PATH_NOT_MODELED"}:
            confirmation_requirements.append(material_id)
        elif source_capacity_unknown and required_qty > confirmed_supply:
            confirmation_requirements.append(material_id)

        materials.append(
            {
                "material_id": material_id,
                "material_name": row[1],
                "uom": row[2],
                "criticality": row[3],
                "qty_per_unit": float(row[4]),
                "required_qty": round(required_qty, 4),
                "confirmed_supply_qty": round(confirmed_supply, 4),
                "provisional_supply_qty": round(provisional_supply, 4),
                "confirmed_material_inventory_qty": round(inventory_qty, 4),
                "eligible_inbound_po_qty": round(usable_po_qty, 4),
                "status": status,
                "bom_provenance_class": row[5],
                "inventory": inv_rows,
                "purchase_orders": po_list,
                "source_paths": allocations,
                "approved_substitutions": approved_substitutions,
            }
        )

    critical_rows = [
        row for row in materials if str(row["criticality"]).lower() == "critical"
    ]
    critical_confirmed = all(
        row["status"] == "CONFIRMED_COVERED" for row in critical_rows
    )
    critical_covered_with_provisional = all(
        row["status"] in {"CONFIRMED_COVERED", "PROVISIONAL_COVERED"}
        for row in critical_rows
    )

    if critical_failures:
        decision = "INFEASIBLE"
    elif critical_unknowns:
        decision = "INSUFFICIENT_DATA"
    elif critical_confirmed:
        decision = "FEASIBLE_CONFIRMED"
    elif critical_covered_with_provisional:
        decision = "CONDITIONALLY_FEASIBLE"
    else:
        decision = "INSUFFICIENT_DATA"

    return {
        "scenario_id": scenario_id,
        "sku": sku,
        "destination_facility_id": destination_facility_id,
        "as_of": as_of.isoformat(),
        "need_by": need_by.isoformat(),
        "production_units": float(production_units),
        "decision": decision,
        "critical_component_count": len(critical_rows),
        "critical_confirmed": critical_confirmed,
        "critical_covered_with_provisional": critical_covered_with_provisional,
        "critical_shortage_material_ids": sorted(set(critical_failures)),
        "critical_unmodeled_material_ids": sorted(set(critical_unknowns)),
        "confirmation_required_material_ids": sorted(
            set(confirmation_requirements)
        ),
        "materials": materials,
        "rules": {
            "confirmed_supply": (
                "material inventory plus confirmed/released/in-transit POs that "
                "arrive by need_by from an explicit allocated source"
            ),
            "provisional_supply": (
                "material inventory plus the larger of eligible inbound POs or "
                "modeled source capacity per explicit source"
            ),
            "modeled_capacity": (
                "approved material-source weekly capacity adjusted for lead time "
                "and scenario facility state; it is not supplier confirmation"
            ),
            "critical_rule": (
                "Every critical BOM material must be covered. Missing source "
                "paths produce INSUFFICIENT_DATA, not an invented shortage."
            ),
        },
    }
