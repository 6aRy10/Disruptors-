from __future__ import annotations

import csv
import json
from pathlib import Path

from dependency.db.connection import connect

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
SCHEMA = ROOT / "sql" / "schema.sql"


def read_csv(name: str) -> list[dict]:
    with (CONFIG / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(value):
    if value in (None, ""):
        return None
    return float(value)


def integer(value):
    if value in (None, ""):
        return None
    return int(float(value))


def boolean(value):
    if value in (None, ""):
        return None
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def load() -> None:
    with connect() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))

        for r in read_csv("facilities_demo.csv"):
            conn.execute(
                """
                INSERT INTO facilities(
                  facility_id,name,country,city,province,tier,product_categories,
                  parent_organization,geom,provenance_class,source_url
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,
                  ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,%s)
                ON CONFLICT (facility_id) DO UPDATE SET
                  name=EXCLUDED.name,country=EXCLUDED.country,city=EXCLUDED.city,
                  province=EXCLUDED.province,tier=EXCLUDED.tier,
                  product_categories=EXCLUDED.product_categories,
                  parent_organization=EXCLUDED.parent_organization,
                  geom=EXCLUDED.geom,provenance_class=EXCLUDED.provenance_class,
                  source_url=EXCLUDED.source_url
                """,
                (
                    r["facility_id"], r["account_name"], r["country"], r["city"],
                    r["province"], r["tier"], r["product_categories"],
                    r["parent_organization"], num(r["lng"]), num(r["lat"]),
                    r["provenance_class"], r["source_url"],
                ),
            )

        for r in read_csv("products.csv"):
            conn.execute(
                """
                INSERT INTO products(
                  sku,name,category,public_material_basis,standard_unit_revenue_eur,
                  standard_unit_margin_eur,provenance_class,source_url
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (sku) DO UPDATE SET
                  name=EXCLUDED.name,category=EXCLUDED.category,
                  public_material_basis=EXCLUDED.public_material_basis,
                  standard_unit_revenue_eur=EXCLUDED.standard_unit_revenue_eur,
                  standard_unit_margin_eur=EXCLUDED.standard_unit_margin_eur,
                  provenance_class=EXCLUDED.provenance_class,source_url=EXCLUDED.source_url
                """,
                (
                    r["sku"], r["name"], r["category"], r["public_material_basis"],
                    num(r["standard_unit_revenue_eur"]), num(r["standard_unit_margin_eur"]),
                    r["provenance_class"], r["source_url"],
                ),
            )

        for r in read_csv("materials.csv"):
            conn.execute(
                """
                INSERT INTO materials(material_id,name,uom,category,criticality,provenance_class)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (material_id) DO UPDATE SET
                  name=EXCLUDED.name,uom=EXCLUDED.uom,category=EXCLUDED.category,
                  criticality=EXCLUDED.criticality,provenance_class=EXCLUDED.provenance_class
                """,
                (r["material_id"], r["name"], r["uom"], r["category"], r["criticality"], r["provenance_class"]),
            )

        for r in read_csv("product_facilities.csv"):
            conn.execute(
                """
                INSERT INTO product_facilities(sku,facility_id,role,approved,setup_lead_days,provenance_class)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (sku,facility_id) DO UPDATE SET
                  role=EXCLUDED.role,approved=EXCLUDED.approved,
                  setup_lead_days=EXCLUDED.setup_lead_days,provenance_class=EXCLUDED.provenance_class
                """,
                (r["sku"], r["facility_id"], r["role"], boolean(r["approved"]), integer(r["setup_lead_days"]), r["provenance_class"]),
            )

        for r in read_csv("bom.csv"):
            conn.execute(
                """
                INSERT INTO bom(sku,material_id,qty_per_unit,provenance_class)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (sku,material_id) DO UPDATE SET
                  qty_per_unit=EXCLUDED.qty_per_unit,provenance_class=EXCLUDED.provenance_class
                """,
                (r["sku"], r["material_id"], num(r["qty_per_unit"]), r["provenance_class"]),
            )

        for r in read_csv("material_sources.csv"):
            conn.execute(
                """
                INSERT INTO material_sources(material_id,facility_id,role,approved,lead_time_days,weekly_capacity_units,provenance_class)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (material_id,facility_id) DO UPDATE SET
                  role=EXCLUDED.role,approved=EXCLUDED.approved,
                  lead_time_days=EXCLUDED.lead_time_days,
                  weekly_capacity_units=EXCLUDED.weekly_capacity_units,
                  provenance_class=EXCLUDED.provenance_class
                """,
                (r["material_id"], r["facility_id"], r["role"], boolean(r["approved"]), integer(r["lead_time_days"]), num(r["weekly_capacity_units"]), r["provenance_class"]),
            )

        for r in read_csv("material_allocations.csv"):
            conn.execute(
                """
                INSERT INTO material_allocations(
                  material_id,source_facility_id,destination_facility_id,sku,
                  approved,allocation_share,provenance_class
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (material_id,source_facility_id,destination_facility_id,sku) DO UPDATE SET
                  approved=EXCLUDED.approved,allocation_share=EXCLUDED.allocation_share,
                  provenance_class=EXCLUDED.provenance_class
                """,
                (
                    r["material_id"], r["source_facility_id"], r["destination_facility_id"],
                    r["sku"], boolean(r["approved"]), num(r["allocation_share"]),
                    r["provenance_class"],
                ),
            )

        for r in read_csv("inventory.csv"):
            conn.execute(
                """
                INSERT INTO inventory(site_id,item_type,item_id,qty_on_hand,qty_reserved,safety_stock,updated_at,provenance_class)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (site_id,item_type,item_id) DO UPDATE SET
                  qty_on_hand=EXCLUDED.qty_on_hand,qty_reserved=EXCLUDED.qty_reserved,
                  safety_stock=EXCLUDED.safety_stock,updated_at=EXCLUDED.updated_at,
                  provenance_class=EXCLUDED.provenance_class
                """,
                (r["site_id"], r["item_type"], r["item_id"], num(r["qty_on_hand"]), num(r["qty_reserved"]), num(r["safety_stock"]), r["updated_at"], r["provenance_class"]),
            )

        for r in read_csv("supplier_capacity.csv"):
            conn.execute(
                """
                INSERT INTO supplier_capacity(
                  facility_id,sku,week_start,capacity_units,committed_units,status,
                  evidence_age_hours,source,provenance_class
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (facility_id,sku,week_start) DO UPDATE SET
                  capacity_units=EXCLUDED.capacity_units,committed_units=EXCLUDED.committed_units,
                  status=EXCLUDED.status,evidence_age_hours=EXCLUDED.evidence_age_hours,
                  source=EXCLUDED.source,provenance_class=EXCLUDED.provenance_class
                """,
                (
                    r["facility_id"], r["sku"], r["week_start"], num(r["capacity_units"]),
                    num(r["committed_units"]), r["status"], num(r["evidence_age_hours"]),
                    r["source"], r["provenance_class"],
                ),
            )

        for r in read_csv("production_orders.csv"):
            conn.execute(
                """
                INSERT INTO production_orders(prod_id,sku,facility_id,qty,start_date,due_date,status,provenance_class)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (prod_id) DO UPDATE SET
                  sku=EXCLUDED.sku,facility_id=EXCLUDED.facility_id,qty=EXCLUDED.qty,
                  start_date=EXCLUDED.start_date,due_date=EXCLUDED.due_date,
                  status=EXCLUDED.status,provenance_class=EXCLUDED.provenance_class
                """,
                (r["prod_id"], r["sku"], r["facility_id"], num(r["qty"]), r["start_date"], r["due_date"], r["status"], r["provenance_class"]),
            )

        for r in read_csv("customer_orders.csv"):
            conn.execute(
                """
                INSERT INTO fulfilment_commitments(
                  commitment_id,customer_or_market,market,sku,qty,due_date,
                  unit_revenue_eur,revenue_eur,unit_margin_eur,gross_margin_eur,
                  priority,partial_allowed,provenance_class
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (commitment_id) DO UPDATE SET
                  customer_or_market=EXCLUDED.customer_or_market,market=EXCLUDED.market,
                  sku=EXCLUDED.sku,qty=EXCLUDED.qty,due_date=EXCLUDED.due_date,
                  unit_revenue_eur=EXCLUDED.unit_revenue_eur,revenue_eur=EXCLUDED.revenue_eur,
                  unit_margin_eur=EXCLUDED.unit_margin_eur,gross_margin_eur=EXCLUDED.gross_margin_eur,
                  priority=EXCLUDED.priority,partial_allowed=EXCLUDED.partial_allowed,
                  provenance_class=EXCLUDED.provenance_class
                """,
                (
                    r["order_id"], r["customer"], r["market"], r["sku"], num(r["qty"]), r["due_date"],
                    num(r["unit_revenue_eur"]), num(r["revenue_eur"]), num(r["unit_margin_eur"]),
                    num(r["gross_margin_eur"]), integer(r["priority"]), boolean(r["partial_allowed"]),
                    r["provenance_class"],
                ),
            )

        for r in read_csv("purchase_orders.csv"):
            conn.execute(
                """
                INSERT INTO purchase_orders(po_id,material_id,supplier_facility_id,qty,eta,status,provenance_class)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (po_id) DO UPDATE SET
                  material_id=EXCLUDED.material_id,supplier_facility_id=EXCLUDED.supplier_facility_id,
                  qty=EXCLUDED.qty,eta=EXCLUDED.eta,status=EXCLUDED.status,
                  provenance_class=EXCLUDED.provenance_class
                """,
                (r["po_id"], r["material_id"], r["supplier_facility_id"], num(r["qty"]), r["eta"], r["status"], r["provenance_class"]),
            )

        for r in read_csv("transport_lanes.csv"):
            conn.execute(
                """
                INSERT INTO transport_lanes(
                  lane_id,origin_facility_id,port_unlocode,port_name,destination_market,
                  mode,transit_days,cost_eur_per_unit,status,policy_tag,provenance_class
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (lane_id) DO UPDATE SET
                  origin_facility_id=EXCLUDED.origin_facility_id,port_unlocode=EXCLUDED.port_unlocode,
                  port_name=EXCLUDED.port_name,destination_market=EXCLUDED.destination_market,
                  mode=EXCLUDED.mode,transit_days=EXCLUDED.transit_days,
                  cost_eur_per_unit=EXCLUDED.cost_eur_per_unit,status=EXCLUDED.status,
                  policy_tag=EXCLUDED.policy_tag,provenance_class=EXCLUDED.provenance_class
                """,
                (
                    r["lane_id"], r["origin_facility_id"], r["port_unlocode"], r["port_name"],
                    r["destination_market"], r["mode"], integer(r["transit_days"]),
                    num(r["cost_eur_per_unit"]), r["status"], r["policy_tag"], r["provenance_class"],
                ),
            )

        event = json.loads((CONFIG / "historical_event.json").read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO external_events(
              event_id,event_type,mode,source,title,occurred_or_effective_at,current_as_of,
              geom,raw_json,provenance_class,source_url
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,
              ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s::jsonb,%s,%s)
            ON CONFLICT (event_id) DO UPDATE SET
              event_type=EXCLUDED.event_type,mode=EXCLUDED.mode,source=EXCLUDED.source,
              title=EXCLUDED.title,occurred_or_effective_at=EXCLUDED.occurred_or_effective_at,
              current_as_of=EXCLUDED.current_as_of,geom=EXCLUDED.geom,raw_json=EXCLUDED.raw_json,
              provenance_class=EXCLUDED.provenance_class,source_url=EXCLUDED.source_url
            """,
            (
                event["event_id"], event["event_type"], event["mode"], event["source"],
                "Cianjur / Sukabumi earthquake replay", event["occurred_at"], event["current_as_of"],
                event["longitude"], event["latitude"], json.dumps(event),
                "VERIFIED_PUBLIC", event["source_url"],
            ),
        )

        conn.commit()

    print("Seed data loaded into PostgreSQL/PostGIS.")


if __name__ == "__main__":
    load()
