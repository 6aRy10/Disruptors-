from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    order_id: str
    qty: int
    unit_revenue_eur: float
    unit_margin_eur: float
    priority: int
    partial_allowed: bool = True


def allocate_orders(
    orders: list[Order],
    available_units: int,
) -> list[dict]:
    """Allocate scarce units by explicit business priority, then margin.

    Lower numeric priority is more important. Margin breaks ties only among
    commitments with the same priority. This prevents a lower-priority,
    slightly higher-margin order from displacing a higher-priority commitment.
    """
    ranked = sorted(
        orders,
        key=lambda order: (
            int(order.priority),
            -float(order.unit_margin_eur),
            order.order_id,
        ),
    )

    remaining = max(0, int(available_units))
    out = []
    for order in ranked:
        if order.partial_allowed:
            allocated = min(order.qty, remaining)
        else:
            allocated = order.qty if remaining >= order.qty else 0

        remaining -= allocated
        out.append(
            {
                "order_id": order.order_id,
                "allocated_qty": allocated,
                "late_qty": order.qty - allocated,
                "protected_revenue_eur": round(
                    allocated * order.unit_revenue_eur,
                    2,
                ),
                "protected_margin_eur": round(
                    allocated * order.unit_margin_eur,
                    2,
                ),
                "priority": int(order.priority),
            }
        )

    return sorted(out, key=lambda row: row["order_id"])


def summarize(rows: list[dict]) -> dict:
    return {
        "protected_units": sum(row["allocated_qty"] for row in rows),
        "late_units": sum(row["late_qty"] for row in rows),
        "protected_revenue_eur": round(
            sum(row["protected_revenue_eur"] for row in rows),
            2,
        ),
        "protected_margin_eur": round(
            sum(row["protected_margin_eur"] for row in rows),
            2,
        ),
        "allocations": rows,
    }
