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


def allocate_orders(orders: list[Order], available_units: int) -> list[dict]:
    ranked = sorted(orders, key=lambda o: (0 if o.priority == 1 else 1, -o.unit_margin_eur, o.order_id))
    remaining=max(0,int(available_units)); out=[]
    for o in ranked:
        alloc=min(o.qty,remaining) if o.partial_allowed else (o.qty if remaining>=o.qty else 0)
        remaining-=alloc
        out.append({'order_id':o.order_id,'allocated_qty':alloc,'late_qty':o.qty-alloc,
                    'protected_revenue_eur':round(alloc*o.unit_revenue_eur,2),
                    'protected_margin_eur':round(alloc*o.unit_margin_eur,2)})
    return sorted(out,key=lambda x:x['order_id'])


def summarize(rows:list[dict])->dict:
    return {'protected_units':sum(x['allocated_qty'] for x in rows),'late_units':sum(x['late_qty'] for x in rows),
            'protected_revenue_eur':round(sum(x['protected_revenue_eur'] for x in rows),2),
            'protected_margin_eur':round(sum(x['protected_margin_eur'] for x in rows),2),'allocations':rows}
