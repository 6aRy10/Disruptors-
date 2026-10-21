"""Joint recovery optimizer for customer orders sharing physical backup capacity.

The shared-capacity ceiling uses the smallest per-SKU available quantity as a
conservative upper bound, not as proof of true aggregate supplier capacity.
It stays provisional until a facility-wide capacity confirmation is available.
"""
from __future__ import annotations

from collections import defaultdict
from math import floor

from dependency.solver.optimization import _MinCostFlow, _orders, _resource_candidates
from dependency.services.facility_capacity import confirmed_capacity_for_scenario
from dependency.solver.material_contention import evaluate_material_contention


def optimize_joint_recovery(
    *,
    scenario_id: str,
    skus: list[str],
    include_provisional: bool = True,
    release_safety_stock: bool = False,
    shared_capacity_limits: dict[str, int] | None = None,
) -> dict:
    """Optimize all selected SKU commitments in one capacity-constrained flow.

    Explicit shared_capacity_limits are externally provided facility-wide caps
    for the planning period. Without one, competing backup routes get a
    conservative modeled cap and the result is not marked fully verified.
    """
    skus = sorted(set(skus))
    if not skus:
        raise ValueError("At least one SKU is required.")
    supplied_limits = shared_capacity_limits or {}
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in supplied_limits.values()):
        raise ValueError("Shared capacity limits must be nonnegative integer units.")

    sku_orders = {}
    sku_resources = {}
    state_versions = set()
    for sku in skus:
        orders = _orders(sku)
        if not orders:
            raise ValueError(f"No customer commitments for SKU {sku}")
        if any(not order["partial_allowed"] for order in orders):
            raise ValueError("Joint optimization requires partial_allowed=true.")
        resources, plan = _resource_candidates(
            scenario_id=scenario_id,
            sku=sku,
            release_safety_stock=release_safety_stock,
            include_provisional=include_provisional,
        )
        sku_orders[sku] = orders
        sku_resources[sku] = resources
        state_versions.add(plan["state_version"])
    if len(state_versions) != 1:
        raise ValueError("Operational state changed during joint planning; retry.")

    backup_uses = defaultdict(list)
    for sku in skus:
        for resource in sku_resources[sku]:
            if resource["resource_type"] == "BACKUP_ASSEMBLY":
                backup_uses[resource["resource_id"]].append((sku, resource))
    # One scenario-dated, operator-confirmed ceiling can constrain every
    # product that would use the same physical factory.
    confirmed_caps = confirmed_capacity_for_scenario(
        scenario_id=scenario_id, facility_ids=list(backup_uses),
    )
    physical_caps = {}
    cap_source = {}
    unverified = []
    unverified_override_facilities = []
    for facility, uses in backup_uses.items():
        if facility in supplied_limits:
            physical_caps[facility] = supplied_limits[facility]
            cap_source[facility] = "UNVERIFIED_CALLER_OVERRIDE"
            if len({sku for sku, _ in uses}) > 1:
                unverified_override_facilities.append(facility)
        elif facility in confirmed_caps:
            physical_caps[facility] = confirmed_caps[facility]["available_units"]
            cap_source[facility] = "CONFIRMED_DATED_FACILITY_CAPACITY"
        else:
            # A per-SKU ceiling is not evidence of aggregate factory capacity.
            physical_caps[facility] = min(int(row["capacity_units"]) for _, row in uses)
            cap_source[facility] = "CONSERVATIVE_PER_SKU_BOUND"
            if len({sku for sku, _ in uses}) > 1:
                unverified.append(facility)

    total_demand = sum(o["qty"] for rows in sku_orders.values() for o in rows)
    all_orders = [(sku, o) for sku in skus for o in sku_orders[sku]]
    priorities = sorted({order["priority"] for _, order in all_orders})
    ranks = {p: i for i, p in enumerate(priorities)}
    financial_bound = 1 + max(
        (o["unit_margin_eur"] for _, o in all_orders), default=0
    ) + max(
        (lane["cost_eur_per_unit"]
         for rows in sku_resources.values()
         for res in rows
         for lane in res["transport_by_order"].values()),
        default=0,
    )
    lexicographic_unit = financial_bound * (total_demand + 1)

    # Source -> physical facility -> SKU-specific resource -> order -> sink.
    next_node = 1
    physical_nodes = {}
    for facility in sorted(backup_uses):
        physical_nodes[facility] = next_node
        next_node += 1
    resource_nodes = {}
    for sku in skus:
        for idx, _ in enumerate(sku_resources[sku]):
            resource_nodes[(sku, idx)] = next_node
            next_node += 1
    order_nodes = {}
    for sku, order in all_orders:
        order_nodes[(sku, order["order_id"])] = next_node
        next_node += 1
    sink = next_node
    graph = _MinCostFlow(sink + 1)
    source = 0

    for facility, node in physical_nodes.items():
        graph.add_edge(source, node, physical_caps[facility], 0)

    for sku in skus:
        for idx, res in enumerate(sku_resources[sku]):
            node = resource_nodes[(sku, idx)]
            cap = int(floor(res["capacity_units"]))
            if res["resource_type"] == "BACKUP_ASSEMBLY":
                graph.add_edge(physical_nodes[res["resource_id"]], node, cap, 0)
            else:
                graph.add_edge(source, node, cap, 0)

    allocations = []
    for sku, order in all_orders:
        order_node = order_nodes[(sku, order["order_id"])]
        graph.add_edge(order_node, sink, int(order["qty"]), 0)
        priority_bonus = (
            len(priorities) - ranks[order["priority"]] - 1
        ) * lexicographic_unit
        for idx, resource in enumerate(sku_resources[sku]):
            lane = resource["transport_by_order"].get(order["order_id"])
            if resource["resource_type"] == "BACKUP_ASSEMBLY" and lane is None:
                continue
            transport_cost = float(lane["cost_eur_per_unit"]) if lane else 0.0
            reward = priority_bonus + order["unit_margin_eur"] - transport_cost
            edge = graph.add_edge(
                resource_nodes[(sku, idx)],
                order_node,
                min(int(resource["capacity_units"]), int(order["qty"])),
                -reward,
            )
            allocations.append((sku, order, resource, lane, edge))

    graph.optimize_optional_flow(source, sink)
    selected = []
    protected_by_sku = defaultdict(int)
    facility_used = defaultdict(int)
    protected_margin = 0.0
    transport_total = 0.0
    provisional_used = False
    approvals_needed = False
    for sku, order, resource, lane, edge in allocations:
        used = edge.initial_capacity - edge.capacity
        if used <= 0:
            continue
        protected_by_sku[sku] += used
        if resource["resource_type"] == "BACKUP_ASSEMBLY":
            facility_used[resource["resource_id"]] += used
        protected_margin += used * float(order["unit_margin_eur"])
        transport_total += used * (float(lane["cost_eur_per_unit"]) if lane else 0.0)
        provisional_used |= bool(resource["provisional"])
        approvals_needed |= bool(resource["requires_approval"])
        selected.append({
            "sku": sku,
            "order_id": order["order_id"],
            "resource_id": resource["resource_id"],
            "resource_type": resource["resource_type"],
            "units": int(used),
            "provisional": bool(resource["provisional"]),
            "requires_approval": bool(resource["requires_approval"]),
            "transport": lane,
        })

    if any(facility_used[k] > v for k, v in physical_caps.items()):
        raise AssertionError("Joint solver exceeded a shared physical cap.")
    # This audit uses the same allocation chosen by the joint factory solver.
    # Report modeled upstream conflicts; do not silently call the resulting
    # allocation physically executable.
    material_audit = evaluate_material_contention(allocations=selected)
    protected = sum(protected_by_sku.values())
    status = (
        "MODELED_SHARED_MATERIAL_SHORTFALL"
        if material_audit["modeled_capacity_conflicts"] else
        "SHORTAGE" if protected < total_demand else
        "PROVISIONAL" if (
            provisional_used or unverified or unverified_override_facilities
            or not material_audit["execution_materials_verified"]
        ) else
        "APPROVAL_REQUIRED" if approvals_needed else "FEASIBLE"
    )
    verified = (
        not unverified and not unverified_override_facilities
        and not provisional_used and not approvals_needed
        and material_audit["execution_materials_verified"]
    )
    return {
        "scenario_id": scenario_id,
        "state_version": next(iter(state_versions)),
        "skus": skus,
        "solver": "JOINT_DETERMINISTIC_MIN_COST_FLOW",
        "shared_material_audit": material_audit,
        "material_capacity_validated": material_audit["execution_materials_verified"],
        "executable_as_proposed": verified and protected == total_demand,
        "status": status,
        "portfolio_allocation_verified": verified,
        "unverified_shared_capacity_facilities": sorted(unverified),
        "unverified_override_facilities": sorted(unverified_override_facilities),
        "capacity_limit_source": {k:cap_source[k] for k in sorted(cap_source)},
        "confirmed_capacity_evidence": confirmed_caps,
        "shared_facility_capacity": physical_caps,
        "shared_facility_allocated": dict(sorted(facility_used.items())),
        "demand_units": total_demand,
        "protected_units": protected,
        "late_units": total_demand - protected,
        "protected_margin_eur": round(protected_margin, 2),
        "incremental_transport_cost_eur": round(transport_total, 2),
        "net_protected_margin_eur": round(protected_margin - transport_total, 2),
        "protected_by_sku": dict(sorted(protected_by_sku.items())),
        "allocations": sorted(selected, key=lambda x: (x["sku"], x["order_id"], x["resource_id"])),
        "assumption": (
            "Factory ceilings are jointly constrained; modeled shared-material "
            "capacity is audited, not jointly optimized. Confirmed material source "
            "quantities and human approval are required before execution."
        ),
    }
