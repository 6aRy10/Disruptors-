from __future__ import annotations

from datetime import timedelta

from dependency.db.connection import connect
from dependency.graph.material_paths import assess_material_paths
from dependency.solver.allocation import Order, allocate_orders, summarize


def plan_sku_recovery(
    *,
    scenario_id: str,
    sku: str,
    stale_after_hours: float = 48.0,
    release_safety_stock: bool = False,
) -> dict:
    with connect() as conn:
        scenario = conn.execute(
            "SELECT as_of FROM scenarios WHERE scenario_id = %s",
            (scenario_id,),
        ).fetchone()
        if not scenario:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")
        as_of = scenario[0]

        state_version = conn.execute(
            "SELECT version FROM operational_state_version WHERE singleton = true"
        ).fetchone()[0]

        order_rows = conn.execute(
            """
            SELECT commitment_id, qty, unit_revenue_eur, unit_margin_eur, priority, partial_allowed, due_date
            FROM fulfilment_commitments
            WHERE sku = %s
            ORDER BY priority, due_date, commitment_id
            """,
            (sku,),
        ).fetchall()
        if not order_rows:
            raise ValueError(f"No fulfilment commitments for sku={sku}")

        demand_units = int(sum(float(r[1]) for r in order_rows))
        earliest_due = min(r[6] for r in order_rows if r[6] is not None)

        inv = conn.execute(
            """
            SELECT
              COALESCE(SUM(qty_on_hand),0),
              COALESCE(SUM(qty_reserved),0),
              COALESCE(SUM(safety_stock),0)
            FROM inventory
            WHERE item_type = 'finished_good' AND item_id = %s
            """,
            (sku,),
        ).fetchone()
        on_hand = float(inv[0])
        reserved = float(inv[1])
        safety_stock = float(inv[2])
        inventory_without_safety = max(0.0, on_hand - reserved - safety_stock)
        usable_inventory = (
            max(0.0, on_hand - reserved)
            if release_safety_stock
            else inventory_without_safety
        )

        state_rows = conn.execute(
            """
            SELECT facility_id, status, capacity_multiplier, confirmed, reason
            FROM scenario_facility_state
            WHERE scenario_id = %s
            """,
            (scenario_id,),
        ).fetchall()
        scenario_state = {
            r[0]: {
                "status": r[1],
                "capacity_multiplier": float(r[2]),
                "confirmed": bool(r[3]),
                "reason": r[4],
            }
            for r in state_rows
        }

        current_prod_rows = conn.execute(
            """
            SELECT po.prod_id, po.facility_id, f.name, po.qty, po.due_date
            FROM production_orders po
            JOIN facilities f ON f.facility_id = po.facility_id
            WHERE po.sku = %s AND po.status IN ('planned','released','in_progress')
            ORDER BY po.due_date, po.prod_id
            """,
            (sku,),
        ).fetchall()

        lost_primary_units = 0.0
        available_current_production = 0.0
        current_production = []
        current_facility_ids = set()
        for row in current_prod_rows:
            current_facility_ids.add(row[1])
            state = scenario_state.get(
                row[1],
                {
                    "status": "AVAILABLE",
                    "capacity_multiplier": 1.0,
                    "confirmed": False,
                    "reason": None,
                },
            )
            qty = float(row[3])
            if state["status"] == "UNAVAILABLE":
                available_qty = 0.0
                lost_primary_units += qty
            elif state["status"] == "DEGRADED":
                available_qty = qty * state["capacity_multiplier"]
                available_current_production += available_qty
                lost_primary_units += qty - available_qty
            else:
                available_qty = qty
                available_current_production += available_qty

            current_production.append(
                {
                    "prod_id": row[0],
                    "facility_id": row[1],
                    "facility_name": row[2],
                    "planned_units": qty,
                    "available_units": available_qty,
                    "scenario_status": state["status"],
                    "status_confirmed": state["confirmed"],
                    "reason": state["reason"],
                }
            )

        candidate_rows = conn.execute(
            """
            SELECT
              pf.facility_id,
              f.name,
              pf.role,
              pf.setup_lead_days,
              sc.capacity_units,
              sc.committed_units,
              sc.evidence_age_hours,
              sc.status,
              pf.provenance_class
            FROM product_facilities pf
            JOIN facilities f ON f.facility_id = pf.facility_id
            JOIN LATERAL (
              SELECT capacity_units, committed_units, evidence_age_hours, status
              FROM supplier_capacity sc
              WHERE sc.facility_id = pf.facility_id AND sc.sku = pf.sku
              ORDER BY sc.week_start DESC
              LIMIT 1
            ) sc ON true
            WHERE pf.sku = %s
              AND pf.approved = true
            ORDER BY pf.setup_lead_days, pf.facility_id
            """,
            (sku,),
        ).fetchall()

        candidates = []
        for row in candidate_rows:
            facility_id = row[0]
            if facility_id in current_facility_ids:
                continue

            state = scenario_state.get(
                facility_id,
                {
                    "status": "AVAILABLE",
                    "capacity_multiplier": 1.0,
                    "confirmed": False,
                    "reason": None,
                },
            )
            if state["status"] == "UNAVAILABLE":
                available_capacity = 0.0
            else:
                base_available = max(0.0, float(row[4]) - float(row[5]))
                available_capacity = base_available * state["capacity_multiplier"]

            setup_days = int(row[3] or 0)
            ready_date = as_of + timedelta(days=setup_days)
            due_feasible = ready_date <= earliest_due
            stale = float(row[6] or 0) > stale_after_hours
            material_path = assess_material_paths(
                scenario_id=scenario_id,
                sku=sku,
                destination_facility_id=facility_id,
            )

            candidates.append(
                {
                    "facility_id": facility_id,
                    "facility_name": row[1],
                    "role": row[2],
                    "setup_lead_days": setup_days,
                    "ready_date": ready_date.isoformat(),
                    "earliest_due_date": earliest_due.isoformat(),
                    "capacity_units": float(row[4]),
                    "committed_units": float(row[5]),
                    "available_capacity_units": available_capacity,
                    "evidence_age_hours": float(row[6] or 0),
                    "capacity_status": row[7],
                    "scenario_status": state["status"],
                    "status_confirmed": state["confirmed"],
                    "due_feasible": due_feasible,
                    "requires_supplier_confirmation": stale,
                    "requires_material_confirmation": material_path[
                        "requires_confirmation"
                    ],
                    "material_path_blocked": material_path["blocked"],
                    "material_path": material_path,
                    "provenance_class": row[8],
                }
            )

        viable = [
            c
            for c in candidates
            if c["scenario_status"] != "UNAVAILABLE"
            and not c["material_path_blocked"]
            and c["due_feasible"]
            and c["available_capacity_units"] > 0
            and c["capacity_status"] == "available"
        ]
        viable.sort(
            key=lambda c: (
                0 if c["role"] == "independent_backup" else 1,
                c["requires_supplier_confirmation"],
                c["requires_material_confirmation"],
                -c["available_capacity_units"],
                c["setup_lead_days"],
                c["facility_id"],
            )
        )
        selected = viable[0] if viable else None
        backup_units = selected["available_capacity_units"] if selected else 0.0

        total_available = usable_inventory + available_current_production + backup_units
        fulfillable_units = min(float(demand_units), total_available)
        shortage_units = max(0.0, float(demand_units) - total_available)

        inventory_needed = max(
            0.0,
            min(
                usable_inventory,
                float(demand_units) - available_current_production - backup_units,
            ),
        )
        safety_stock_used = (
            max(0.0, inventory_needed - inventory_without_safety)
            if release_safety_stock
            else 0.0
        )

        orders = [
            Order(
                order_id=r[0],
                qty=int(r[1]),
                unit_revenue_eur=float(r[2]),
                unit_margin_eur=float(r[3]),
                priority=int(r[4]),
                partial_allowed=bool(r[5]),
            )
            for r in order_rows
        ]
        allocation = summarize(allocate_orders(orders, int(fulfillable_units)))

        requires_confirmation = bool(
            selected and selected["requires_supplier_confirmation"]
        )
        requires_material_confirmation = bool(
            selected and selected["requires_material_confirmation"]
        )
        requires_planner_approval = safety_stock_used > 0
        provisional = requires_confirmation or requires_material_confirmation

        if shortage_units > 0 and provisional:
            plan_status = "PROVISIONAL_SHORTAGE"
        elif shortage_units > 0:
            plan_status = "SHORTAGE"
        elif provisional and requires_planner_approval:
            plan_status = "PROVISIONAL_REQUIRES_CONFIRMATION_AND_APPROVAL"
        elif provisional:
            plan_status = "PROVISIONAL_AWAITING_CONFIRMATION"
        elif requires_planner_approval:
            plan_status = "FEASIBLE_REQUIRES_APPROVAL"
        else:
            plan_status = "FEASIBLE"

        return {
            "scenario_id": scenario_id,
            "sku": sku,
            "as_of": as_of.isoformat(),
            "state_version": int(state_version),
            "plan_status": plan_status,
            "demand_units": demand_units,
            "inventory": {
                "on_hand_units": on_hand,
                "reserved_units": reserved,
                "safety_stock_units": safety_stock,
                "release_safety_stock": release_safety_stock,
                "usable_inventory_units": usable_inventory,
                "safety_stock_used_units": safety_stock_used,
            },
            "current_production": current_production,
            "lost_primary_units": lost_primary_units,
            "available_current_production_units": available_current_production,
            "selected_backup": selected,
            "backup_candidates": candidates,
            "backup_available_units": backup_units,
            "total_available_units": total_available,
            "shortage_units": shortage_units,
            "requires_supplier_confirmation": requires_confirmation,
            "requires_material_confirmation": requires_material_confirmation,
            "requires_planner_approval": requires_planner_approval,
            "allocation": allocation,
        }
