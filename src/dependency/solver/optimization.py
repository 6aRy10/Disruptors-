from __future__ import annotations

from dataclasses import dataclass
from math import floor

from dependency.db.connection import connect
from dependency.solver.candidates import generate_recovery_candidates
from dependency.solver.recovery import plan_sku_recovery


@dataclass
class _Edge:
    to: int
    rev: int
    capacity: int
    cost: float
    initial_capacity: int
    tag: dict | None = None


class _MinCostFlow:
    def __init__(self, node_count: int):
        self.graph: list[list[_Edge]] = [[] for _ in range(node_count)]

    def add_edge(
        self,
        source: int,
        target: int,
        capacity: int,
        cost: float,
        tag: dict | None = None,
    ) -> _Edge:
        forward = _Edge(
            to=target,
            rev=len(self.graph[target]),
            capacity=max(0, int(capacity)),
            cost=float(cost),
            initial_capacity=max(0, int(capacity)),
            tag=tag,
        )
        reverse = _Edge(
            to=source,
            rev=len(self.graph[source]),
            capacity=0,
            cost=-float(cost),
            initial_capacity=0,
            tag=None,
        )
        self.graph[source].append(forward)
        self.graph[target].append(reverse)
        return forward

    def optimize_optional_flow(self, source: int, sink: int) -> dict:
        total_flow = 0
        total_cost = 0.0
        n = len(self.graph)

        while True:
            distance = [float("inf")] * n
            previous: list[tuple[int, int] | None] = [None] * n
            distance[source] = 0.0

            # Small hackathon graphs do not need a complex potential-based
            # implementation. Bellman-Ford safely handles negative reward edges.
            for _ in range(n - 1):
                changed = False
                for u in range(n):
                    if distance[u] == float("inf"):
                        continue
                    for edge_index, edge in enumerate(self.graph[u]):
                        if edge.capacity <= 0:
                            continue
                        candidate = distance[u] + edge.cost
                        if candidate + 1e-9 < distance[edge.to]:
                            distance[edge.to] = candidate
                            previous[edge.to] = (u, edge_index)
                            changed = True
                if not changed:
                    break

            if (
                distance[sink] == float("inf")
                or distance[sink] >= -1e-9
            ):
                break

            augment = 10**18
            node = sink
            while node != source:
                step = previous[node]
                if step is None:
                    augment = 0
                    break
                u, edge_index = step
                augment = min(
                    augment,
                    self.graph[u][edge_index].capacity,
                )
                node = u

            if augment <= 0:
                break

            node = sink
            while node != source:
                u, edge_index = previous[node]
                edge = self.graph[u][edge_index]
                edge.capacity -= augment
                reverse = self.graph[edge.to][edge.rev]
                reverse.capacity += augment
                node = u

            total_flow += int(augment)
            total_cost += float(augment) * distance[sink]

        return {
            "flow": total_flow,
            "internal_objective_cost": total_cost,
        }


def _orders(sku: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              commitment_id,customer_or_market,market,qty,due_date,
              unit_revenue_eur,unit_margin_eur,priority,partial_allowed,
              provenance_class
            FROM fulfilment_commitments
            WHERE sku=%s
            ORDER BY priority,due_date,commitment_id
            """,
            (sku,),
        ).fetchall()

    return [
        {
            "order_id": r[0],
            "customer_or_market": r[1],
            "market": r[2],
            "qty": int(float(r[3])),
            "due_date": r[4].isoformat() if r[4] else None,
            "unit_revenue_eur": float(r[5] or 0),
            "unit_margin_eur": float(r[6] or 0),
            "priority": int(r[7] or 999),
            "partial_allowed": bool(r[8]),
            "provenance_class": r[9],
        }
        for r in rows
    ]


def _resource_candidates(
    *,
    scenario_id: str,
    sku: str,
    release_safety_stock: bool,
    include_provisional: bool,
) -> tuple[list[dict], dict]:
    plan = plan_sku_recovery(
        scenario_id=scenario_id,
        sku=sku,
        release_safety_stock=release_safety_stock,
    )
    candidates = generate_recovery_candidates(
        scenario_id=scenario_id,
        sku=sku,
    )

    resources: list[dict] = []

    normal_inventory = max(
        0.0,
        float(plan["inventory"]["on_hand_units"])
        - float(plan["inventory"]["reserved_units"])
        - float(plan["inventory"]["safety_stock_units"]),
    )
    if normal_inventory > 0:
        resources.append(
            {
                "resource_id": "FINISHED_INVENTORY",
                "resource_type": "FINISHED_INVENTORY",
                "capacity_units": int(floor(normal_inventory)),
                "provisional": False,
                "requires_approval": False,
                "reasons": [],
                "transport_by_order": {},
            }
        )

    if release_safety_stock:
        safety = float(plan["inventory"]["safety_stock_units"])
        if safety > 0:
            resources.append(
                {
                    "resource_id": "SAFETY_STOCK",
                    "resource_type": "SAFETY_STOCK",
                    "capacity_units": int(floor(safety)),
                    "provisional": True,
                    "requires_approval": True,
                    "reasons": ["PLANNER_APPROVAL_REQUIRED"],
                    "transport_by_order": {},
                }
            )

    current_units = float(plan["available_current_production_units"])
    if current_units > 0:
        resources.append(
            {
                "resource_id": "CURRENT_PRODUCTION",
                "resource_type": "CURRENT_PRODUCTION",
                "capacity_units": int(floor(current_units)),
                "provisional": False,
                "requires_approval": False,
                "reasons": [],
                "transport_by_order": {},
            }
        )

    for candidate in candidates:
        if candidate["plan_type"] != "ASSEMBLY_REALLOCATION":
            continue
        if candidate["decision"] == "REJECTED":
            continue
        provisional = candidate["decision"] != "FEASIBLE"
        if provisional and not include_provisional:
            continue

        evidence = candidate["evidence"]
        capacity = int(
            floor(float(evidence.get("available_capacity_units") or 0))
        )
        if capacity <= 0:
            continue

        transport = evidence.get("transport_feasibility") or {}
        transport_by_order = {}
        for commitment in transport.get("commitments", []):
            best = commitment.get("best_on_time_lane")
            if best:
                transport_by_order[commitment["commitment_id"]] = {
                    "lane_id": best["lane_id"],
                    "mode": best["mode"],
                    "arrival_date": best["arrival_date"],
                    "cost_eur_per_unit": float(
                        best["cost_eur_per_unit"]
                    ),
                }

        resources.append(
            {
                "resource_id": evidence["backup_facility_id"],
                "resource_type": "BACKUP_ASSEMBLY",
                "facility_name": evidence["backup_facility_name"],
                "capacity_units": capacity,
                "provisional": provisional,
                "requires_approval": False,
                "reasons": list(candidate.get("reasons", [])),
                "candidate_plan_id": candidate["plan_id"],
                "transport_by_order": transport_by_order,
            }
        )

    return resources, plan


def optimize_recovery_allocation(
    *,
    scenario_id: str,
    sku: str,
    release_safety_stock: bool = False,
    include_provisional: bool = True,
) -> dict:
    """Optimize scarce recovery supply across customer commitments.

    Objective order:
    1. protect lower numeric customer priorities lexicographically;
    2. within that policy, maximize protected gross margin minus incremental
       recovery transport cost.

    The solver is exact for the current partial-order model. A non-partial
    commitment is rejected rather than silently treated as divisible.
    """
    orders = _orders(sku)
    if not orders:
        raise ValueError(f"No fulfilment commitments for sku={sku}")
    if any(not order["partial_allowed"] for order in orders):
        raise ValueError(
            "Optimization currently requires partial_allowed=true for all "
            "commitments. Non-partial orders need a discrete MIP decision."
        )

    resources, recovery_plan = _resource_candidates(
        scenario_id=scenario_id,
        sku=sku,
        release_safety_stock=release_safety_stock,
        include_provisional=include_provisional,
    )
    if not resources:
        return {
            "scenario_id": scenario_id,
            "sku": sku,
            "status": "NO_AVAILABLE_RESOURCES",
            "protected_units": 0,
            "late_units": sum(order["qty"] for order in orders),
            "allocations": [],
            "resources": [],
        }

    total_demand = sum(order["qty"] for order in orders)
    priorities = sorted({order["priority"] for order in orders})
    priority_rank = {
        priority: index for index, priority in enumerate(priorities)
    }

    max_margin = max(order["unit_margin_eur"] for order in orders)
    max_transport_cost = max(
        (
            lane["cost_eur_per_unit"]
            for resource in resources
            for lane in resource["transport_by_order"].values()
        ),
        default=0.0,
    )
    max_financial_delta = max_margin + max_transport_cost + 1.0
    lexicographic_unit = max_financial_delta * (total_demand + 1)

    source = 0
    resource_offset = 1
    order_offset = resource_offset + len(resources)
    sink = order_offset + len(orders)
    flow = _MinCostFlow(sink + 1)

    resource_edges = {}
    allocation_edges = []

    for resource_index, resource in enumerate(resources):
        node = resource_offset + resource_index
        edge = flow.add_edge(
            source,
            node,
            resource["capacity_units"],
            0.0,
            tag={
                "kind": "resource_capacity",
                "resource_id": resource["resource_id"],
            },
        )
        resource_edges[resource["resource_id"]] = edge

    for order_index, order in enumerate(orders):
        order_node = order_offset + order_index
        flow.add_edge(
            order_node,
            sink,
            order["qty"],
            0.0,
            tag={"kind": "order_demand", "order_id": order["order_id"]},
        )

        rank = priority_rank[order["priority"]]
        priority_bonus = (
            len(priorities) - rank - 1
        ) * lexicographic_unit

        for resource_index, resource in enumerate(resources):
            resource_node = resource_offset + resource_index

            transport = resource["transport_by_order"].get(
                order["order_id"]
            )
            if resource["resource_type"] == "BACKUP_ASSEMBLY":
                if transport is None:
                    continue
                transport_cost = transport["cost_eur_per_unit"]
            else:
                transport_cost = 0.0

            financial_value = (
                order["unit_margin_eur"] - transport_cost
            )
            reward = priority_bonus + financial_value

            edge = flow.add_edge(
                resource_node,
                order_node,
                min(resource["capacity_units"], order["qty"]),
                -reward,
                tag={
                    "kind": "allocation",
                    "resource_id": resource["resource_id"],
                    "resource_type": resource["resource_type"],
                    "order_id": order["order_id"],
                    "unit_margin_eur": order["unit_margin_eur"],
                    "unit_revenue_eur": order["unit_revenue_eur"],
                    "transport_cost_eur_per_unit": transport_cost,
                    "transport": transport,
                    "provisional": resource["provisional"],
                    "requires_approval": resource["requires_approval"],
                    "reasons": resource["reasons"],
                },
            )
            allocation_edges.append(edge)

    flow_result = flow.optimize_optional_flow(source, sink)

    allocations = []
    protected_by_order = {order["order_id"]: 0 for order in orders}
    protected_margin = 0.0
    protected_revenue = 0.0
    transport_cost = 0.0
    provisional_resources = set()
    approval_resources = set()
    used_reasons = set()

    for edge in allocation_edges:
        used = edge.initial_capacity - edge.capacity
        if used <= 0:
            continue
        tag = edge.tag or {}
        order_id = tag["order_id"]
        protected_by_order[order_id] += used

        margin = used * float(tag["unit_margin_eur"])
        revenue = used * float(tag["unit_revenue_eur"])
        recovery_cost = used * float(
            tag["transport_cost_eur_per_unit"]
        )
        protected_margin += margin
        protected_revenue += revenue
        transport_cost += recovery_cost

        if tag["provisional"]:
            provisional_resources.add(tag["resource_id"])
        if tag["requires_approval"]:
            approval_resources.add(tag["resource_id"])
        used_reasons.update(tag.get("reasons") or [])

        allocations.append(
            {
                "resource_id": tag["resource_id"],
                "resource_type": tag["resource_type"],
                "order_id": order_id,
                "allocated_units": int(used),
                "protected_revenue_eur": round(revenue, 2),
                "protected_margin_eur": round(margin, 2),
                "transport_cost_eur": round(recovery_cost, 2),
                "transport": tag.get("transport"),
                "provisional": bool(tag["provisional"]),
                "requires_approval": bool(tag["requires_approval"]),
            }
        )

    order_results = []
    late_units = 0
    late_margin = 0.0
    for order in orders:
        protected = protected_by_order[order["order_id"]]
        late = order["qty"] - protected
        late_units += late
        late_margin += late * order["unit_margin_eur"]
        order_results.append(
            {
                **order,
                "protected_units": int(protected),
                "late_units": int(late),
                "protected_margin_eur": round(
                    protected * order["unit_margin_eur"],
                    2,
                ),
                "late_margin_eur": round(
                    late * order["unit_margin_eur"],
                    2,
                ),
            }
        )

    resources_used = []
    for resource in resources:
        edge = resource_edges[resource["resource_id"]]
        used = edge.initial_capacity - edge.capacity
        resources_used.append(
            {
                **resource,
                "used_units": int(used),
                "unused_units": int(edge.capacity),
            }
        )

    if late_units > 0:
        status = (
            "PROVISIONAL_SHORTAGE"
            if provisional_resources
            else "SHORTAGE"
        )
    elif approval_resources:
        status = "FEASIBLE_REQUIRES_APPROVAL"
    elif provisional_resources:
        status = "PROVISIONAL"
    else:
        status = "FEASIBLE"

    return {
        "scenario_id": scenario_id,
        "sku": sku,
        "state_version": recovery_plan["state_version"],
        "status": status,
        "solver": "DETERMINISTIC_MIN_COST_FLOW",
        "objective_policy": (
            "Lexicographically protect lower numeric customer priorities; "
            "then maximize protected gross margin minus incremental recovery "
            "transport cost."
        ),
        "include_provisional": include_provisional,
        "release_safety_stock": release_safety_stock,
        "demand_units": total_demand,
        "protected_units": int(flow_result["flow"]),
        "late_units": int(late_units),
        "protected_revenue_eur": round(protected_revenue, 2),
        "protected_margin_eur": round(protected_margin, 2),
        "incremental_transport_cost_eur": round(transport_cost, 2),
        "net_protected_margin_after_transport_eur": round(
            protected_margin - transport_cost,
            2,
        ),
        "late_margin_eur": round(late_margin, 2),
        "provisional_resources_used": sorted(provisional_resources),
        "approval_resources_used": sorted(approval_resources),
        "used_conditional_reasons": sorted(used_reasons),
        "orders": order_results,
        "resources": resources_used,
        "allocations": sorted(
            allocations,
            key=lambda row: (
                row["order_id"],
                row["resource_id"],
            ),
        ),
    }
