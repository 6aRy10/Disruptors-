from __future__ import annotations

from dependency.db.connection import connect


def product_dependency_graph(sku: str) -> dict:
    """Return an explicit, provenance-preserving graph for one SKU."""
    with connect() as conn:
        product = conn.execute(
            """
            SELECT sku,name,category,provenance_class,source_url
            FROM products
            WHERE sku=%s
            """,
            (sku,),
        ).fetchone()
        if not product:
            raise ValueError(f"Unknown sku: {sku}")

        bom_rows = conn.execute(
            """
            SELECT b.material_id,m.name,m.criticality,b.qty_per_unit,
                   b.provenance_class
            FROM bom b
            JOIN materials m ON m.material_id=b.material_id
            WHERE b.sku=%s
            ORDER BY b.material_id
            """,
            (sku,),
        ).fetchall()

        facility_rows = conn.execute(
            """
            SELECT pf.facility_id,f.name,f.country,f.tier,pf.role,pf.approved,
                   pf.setup_lead_days,pf.provenance_class
            FROM product_facilities pf
            JOIN facilities f ON f.facility_id=pf.facility_id
            WHERE pf.sku=%s
            ORDER BY
              CASE WHEN pf.role='primary_assembly' THEN 0 ELSE 1 END,
              pf.facility_id
            """,
            (sku,),
        ).fetchall()

        allocation_rows = conn.execute(
            """
            SELECT ma.material_id,ma.source_facility_id,sf.name,sf.country,
                   sf.tier,ma.destination_facility_id,df.name,ma.allocation_share,
                   ma.provenance_class
            FROM material_allocations ma
            JOIN facilities sf ON sf.facility_id=ma.source_facility_id
            JOIN facilities df ON df.facility_id=ma.destination_facility_id
            WHERE ma.sku=%s AND ma.approved=true
            ORDER BY ma.material_id,ma.destination_facility_id,
                     ma.source_facility_id
            """,
            (sku,),
        ).fetchall()

        commitment_rows = conn.execute(
            """
            SELECT commitment_id,customer_or_market,market,qty,due_date,
                   revenue_eur,gross_margin_eur,priority,provenance_class
            FROM fulfilment_commitments
            WHERE sku=%s
            ORDER BY priority,due_date,commitment_id
            """,
            (sku,),
        ).fetchall()

    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(node_id: str, **attrs):
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, **attrs}
        else:
            for key, value in attrs.items():
                if nodes[node_id].get(key) in {None, ""} and value not in {None, ""}:
                    nodes[node_id][key] = value

    def add_edge(edge_id: str, source: str, target: str, **attrs):
        if edge_id not in edges:
            edges[edge_id] = {
                "id": edge_id,
                "source": source,
                "target": target,
                **attrs,
            }

    product_id = f"product:{sku}"
    add_node(
        product_id,
        node_type="PRODUCT",
        label=f"{product[1]} ({sku})",
        sku=sku,
        category=product[2],
        provenance_class=product[3],
        source_url=product[4],
    )

    material_names = {}
    for row in bom_rows:
        material_id = row[0]
        material_names[material_id] = row[1]
        node_id = f"material:{material_id}"
        add_node(
            node_id,
            node_type="MATERIAL",
            label=row[1],
            material_id=material_id,
            criticality=row[2],
            provenance_class=row[4],
        )
        add_edge(
            f"bom:{sku}:{material_id}",
            node_id,
            product_id,
            edge_type="BOM",
            qty_per_unit=float(row[3]),
            provenance_class=row[4],
        )

    for row in facility_rows:
        facility_id = row[0]
        node_id = f"facility:{facility_id}"
        add_node(
            node_id,
            node_type="ASSEMBLY_FACILITY",
            label=row[1],
            facility_id=facility_id,
            country=row[2],
            tier=row[3],
            role=row[4],
            approved=bool(row[5]),
            setup_lead_days=int(row[6] or 0),
            provenance_class=row[7],
        )
        add_edge(
            f"assembly:{facility_id}:{sku}",
            node_id,
            product_id,
            edge_type="ASSEMBLES",
            role=row[4],
            approved=bool(row[5]),
            provenance_class=row[7],
        )

    for row in allocation_rows:
        material_id = row[0]
        source_id = row[1]
        destination_id = row[5]
        source_node = f"facility:{source_id}"
        destination_node = f"facility:{destination_id}"
        material_node = f"material:{material_id}"

        add_node(
            source_node,
            node_type="UPSTREAM_FACILITY",
            label=row[2],
            facility_id=source_id,
            country=row[3],
            tier=row[4],
            provenance_class=row[8],
        )
        add_node(
            destination_node,
            node_type="ASSEMBLY_FACILITY",
            label=row[6],
            facility_id=destination_id,
            provenance_class=row[8],
        )
        add_edge(
            f"source:{source_id}:{material_id}:{destination_id}:{sku}",
            source_node,
            material_node,
            edge_type="SUPPLIES_MATERIAL",
            destination_facility_id=destination_id,
            allocation_share=float(row[7] or 0),
            provenance_class=row[8],
        )
        add_edge(
            f"material-flow:{material_id}:{destination_id}:{sku}",
            material_node,
            destination_node,
            edge_type="MATERIAL_FLOW_TO_ASSEMBLY",
            provenance_class=row[8],
        )

    for row in commitment_rows:
        commitment_id = row[0]
        node_id = f"commitment:{commitment_id}"
        add_node(
            node_id,
            node_type="CUSTOMER_COMMITMENT",
            label=f"{row[1]} · {int(float(row[3])):,} units",
            commitment_id=commitment_id,
            customer_or_market=row[1],
            market=row[2],
            qty=float(row[3]),
            due_date=row[4].isoformat() if row[4] else None,
            revenue_eur=float(row[5] or 0),
            gross_margin_eur=float(row[6] or 0),
            priority=int(row[7] or 0),
            provenance_class=row[8],
        )
        add_edge(
            f"commitment:{sku}:{commitment_id}",
            product_id,
            node_id,
            edge_type="FULFILLS_COMMITMENT",
            provenance_class=row[8],
        )

    source_destinations: dict[str, set[str]] = {}
    for row in allocation_rows:
        key = row[1]
        source_destinations.setdefault(key, set()).add(row[5])

    shared_sources = [
        {
            "source_facility_id": source_id,
            "source_facility_name": nodes[f"facility:{source_id}"]["label"],
            "destination_facility_ids": sorted(destinations),
            "destination_count": len(destinations),
        }
        for source_id, destinations in source_destinations.items()
        if len(destinations) > 1
    ]
    shared_sources.sort(
        key=lambda row: (
            -row["destination_count"],
            row["source_facility_id"],
        )
    )

    return {
        "sku": sku,
        "product_name": product[1],
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "shared_upstream_sources": shared_sources,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "material_count": len(bom_rows),
            "assembly_facility_count": len(facility_rows),
            "explicit_allocation_count": len(allocation_rows),
            "commitment_count": len(commitment_rows),
            "shared_upstream_source_count": len(shared_sources),
        },
        "rule": (
            "Only stored explicit dependency edges are shown. Shared upstream "
            "sources are reported only when one source has explicit allocations "
            "to multiple assembly facilities for this SKU."
        ),
    }
