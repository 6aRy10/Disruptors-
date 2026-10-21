from __future__ import annotations

import csv
from pathlib import Path

from dependency.db.connection import connect

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config"


def _rows(name: str) -> list[dict]:
    with (CONFIG / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def reset_demo_state() -> dict:
    """Reset mutable operational data without rebuilding the public network."""
    with connect() as conn:
        for r in _rows("inventory.csv"):
            conn.execute(
                """
                UPDATE inventory
                SET qty_on_hand=%s,qty_reserved=%s,safety_stock=%s,updated_at=%s
                WHERE site_id=%s AND item_type=%s AND item_id=%s
                """,
                (
                    float(r["qty_on_hand"]),
                    float(r["qty_reserved"]),
                    float(r["safety_stock"]),
                    r["updated_at"],
                    r["site_id"],
                    r["item_type"],
                    r["item_id"],
                ),
            )

        for r in _rows("supplier_capacity.csv"):
            conn.execute(
                """
                UPDATE supplier_capacity
                SET capacity_units=%s,committed_units=%s,status=%s,
                    evidence_age_hours=%s,source=%s
                WHERE facility_id=%s AND sku=%s AND week_start=%s
                """,
                (
                    float(r["capacity_units"]),
                    float(r["committed_units"]),
                    r["status"],
                    float(r["evidence_age_hours"]),
                    r["source"],
                    r["facility_id"],
                    r["sku"],
                    r["week_start"],
                ),
            )

        for r in _rows("product_facilities.csv"):
            conn.execute(
                """
                UPDATE product_facilities
                SET role=%s,approved=%s,setup_lead_days=%s,provenance_class=%s
                WHERE sku=%s AND facility_id=%s
                """,
                (
                    r["role"],
                    _bool(r["approved"]),
                    int(r["setup_lead_days"]),
                    r["provenance_class"],
                    r["sku"],
                    r["facility_id"],
                ),
            )

        for r in _rows("purchase_orders.csv"):
            conn.execute(
                """
                UPDATE purchase_orders
                SET material_id=%s,supplier_facility_id=%s,qty=%s,eta=%s,
                    status=%s,provenance_class=%s
                WHERE po_id=%s
                """,
                (
                    r["material_id"],
                    r["supplier_facility_id"],
                    float(r["qty"]),
                    r["eta"],
                    r["status"],
                    r["provenance_class"],
                    r["po_id"],
                ),
            )

        for r in _rows("substitutions.csv"):
            conn.execute(
                """
                UPDATE substitutions
                SET approved=%s,max_ratio=%s,engineering_status=%s,
                    provenance_class=%s
                WHERE material_id=%s AND substitute_material_id=%s
                """,
                (
                    _bool(r["approved"]),
                    float(r["max_ratio"]),
                    r["engineering_status"],
                    r["provenance_class"],
                    r["material_id"],
                    r["substitute_material_id"],
                ),
            )

        conn.execute("DELETE FROM scenario_facility_state")
        for r in _rows("scenario_facility_state.csv"):
            conn.execute(
                """
                INSERT INTO scenario_facility_state(
                  scenario_id,facility_id,status,capacity_multiplier,confirmed,
                  source_type,reason,provenance_class
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    r["scenario_id"],
                    r["facility_id"],
                    r["status"],
                    float(r["capacity_multiplier"]),
                    _bool(r["confirmed"]),
                    r["source_type"],
                    r["reason"],
                    r["provenance_class"],
                ),
            )

        conn.execute("DELETE FROM supplier_capacity_observations")
        conn.execute("DELETE FROM incident_decisions")
        conn.execute("DELETE FROM incident_plan_history")
        conn.execute("DELETE FROM incident_evidence")
        conn.execute("DELETE FROM agent_runs")
        conn.execute("DELETE FROM incident_outcomes")
        conn.execute("DELETE FROM incidents")
        conn.execute("DELETE FROM event_outbox")
        conn.execute("UPDATE operational_state_version SET version=1 WHERE singleton=true")
        conn.commit()

    return {
        "ok": True,
        "state_version": 1,
        "message": "Demo operational state reset to seed values.",
    }
