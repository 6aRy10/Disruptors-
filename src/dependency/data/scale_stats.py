from __future__ import annotations

from dependency.db.connection import connect


TABLES = (
    ("public_network_facilities", "network_facilities"),
    ("public_supplier_relationships", "network_facility_relationships"),
    ("operational_facilities", "facilities"),
    ("products", "products"),
    ("materials", "materials"),
    ("product_facility_edges", "product_facilities"),
    ("bom_rows", "bom"),
    ("material_sources", "material_sources"),
    ("material_allocations", "material_allocations"),
    ("substitutions", "substitutions"),
    ("inventory_rows", "inventory"),
    ("supplier_capacity_rows", "supplier_capacity"),
    ("production_orders", "production_orders"),
    ("customer_commitments", "fulfilment_commitments"),
    ("purchase_orders", "purchase_orders"),
    ("transport_lanes", "transport_lanes"),
)


def enterprise_data_stats() -> dict:
    """Return the actual loaded data scale from PostgreSQL.

    Counts are computed from the database. They are not pre-written demo numbers.
    """
    counts: dict[str, int] = {}
    with connect() as conn:
        for label, table in TABLES:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[label] = int(row[0])

        simulated = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM products
                WHERE provenance_class='SIMULATED_PRIVATE')
              + (SELECT COUNT(*) FROM bom
                WHERE provenance_class='SIMULATED_PRIVATE')
              + (SELECT COUNT(*) FROM material_allocations
                WHERE provenance_class='SIMULATED_PRIVATE')
              + (SELECT COUNT(*) FROM fulfilment_commitments
                WHERE provenance_class='SIMULATED_PRIVATE')
              + (SELECT COUNT(*) FROM purchase_orders
                WHERE provenance_class='SIMULATED_PRIVATE')
              + (SELECT COUNT(*) FROM supplier_capacity
                WHERE provenance_class='SIMULATED_PRIVATE')
              + (SELECT COUNT(*) FROM inventory
                WHERE provenance_class='SIMULATED_PRIVATE')
            """
        ).fetchone()[0]

        public_links = conn.execute(
            """
            SELECT COUNT(*)
            FROM facility_network_links
            WHERE provenance_class='PUBLIC_DERIVED'
            """
        ).fetchone()[0]

    operational_records = sum(
        counts[key]
        for key in (
            "products",
            "materials",
            "product_facility_edges",
            "bom_rows",
            "material_sources",
            "material_allocations",
            "substitutions",
            "inventory_rows",
            "supplier_capacity_rows",
            "production_orders",
            "customer_commitments",
            "purchase_orders",
            "transport_lanes",
        )
    )

    return {
        "counts": counts,
        "operational_record_count": operational_records,
        "simulated_private_core_record_count": int(simulated),
        "public_to_private_facility_links": int(public_links),
        "truth_rule": (
            "Public facility identities and coordinates are separate from the "
            "generated SIMULATED_PRIVATE ERP/BOM/order/capacity relationships."
        ),
    }
