from __future__ import annotations

from datetime import date

from dependency.db.connection import connect


def purchase_order_supply_by_date(*, material_id: str, need_by: date) -> dict:
    """Return confirmed inbound material that arrives on or before need_by."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT po_id, qty, eta, status
            FROM purchase_orders
            WHERE material_id = %s
            ORDER BY eta, po_id
            """,
            (material_id,),
        ).fetchall()

    usable = []
    late = []
    for po_id, qty, eta, status in rows:
        record = {
            "po_id": po_id,
            "qty": float(qty),
            "eta": eta.isoformat() if eta else None,
            "status": status,
        }
        if status == "confirmed" and eta and eta.date() <= need_by:
            usable.append(record)
        else:
            late.append(record)

    return {
        "material_id": material_id,
        "need_by": need_by.isoformat(),
        "usable_qty": sum(r["qty"] for r in usable),
        "usable_purchase_orders": usable,
        "excluded_purchase_orders": late,
    }
