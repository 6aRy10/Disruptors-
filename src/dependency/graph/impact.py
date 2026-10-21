from __future__ import annotations

from collections import defaultdict

from dependency.db.connection import connect


def trace_event_impact(*, event_id: str, radius_km: float = 100.0) -> dict:
    """Trace one geospatial event through facilities -> sourcing edges/assembly -> SKUs -> commitments.

    Proximity is treated as POTENTIALLY_EXPOSED. This function does not claim a
    facility is damaged or closed.
    """
    radius_m = float(radius_km) * 1000.0

    exposure_sql = """
        SELECT
            f.facility_id,
            f.name,
            f.tier,
            f.product_categories,
            ST_Distance(f.geom, e.geom) / 1000.0 AS distance_km
        FROM facilities f
        JOIN external_events e ON e.event_id = %s
        WHERE f.geom IS NOT NULL
          AND e.geom IS NOT NULL
          AND ST_DWithin(f.geom, e.geom, %s)
        ORDER BY distance_km, f.facility_id
    """

    with connect() as conn:
        exposed = conn.execute(exposure_sql, (event_id, radius_m)).fetchall()
        facility_ids = [r[0] for r in exposed]

        if not facility_ids:
            return {
                "event_id": event_id,
                "radius_km": radius_km,
                "exposure_status": "NO_EXPOSURE",
                "facilities": [],
                "dependency_paths": [],
                "products": [],
                "totals": {
                    "products_impacted": 0,
                    "commitment_units": 0,
                    "revenue_eur": 0.0,
                    "gross_margin_eur": 0.0,
                },
            }

        # Direct assembly exposure: exposed T1 facility -> assigned SKU.
        assembly_rows = conn.execute(
            """
            SELECT
                pf.facility_id,
                f.name,
                pf.sku,
                p.name,
                pf.role,
                pf.provenance_class
            FROM product_facilities pf
            JOIN facilities f ON f.facility_id = pf.facility_id
            JOIN products p ON p.sku = pf.sku
            WHERE pf.facility_id = ANY(%s)
            ORDER BY pf.facility_id, pf.sku
            """,
            (facility_ids,),
        ).fetchall()

        # Upstream exposure must follow an explicit source-of-supply edge.
        # A thread supplier near an event must not affect every SKU in the global BOM.
        material_rows = conn.execute(
            """
            SELECT
                ma.source_facility_id,
                sf.name,
                ma.material_id,
                m.name,
                ma.destination_facility_id,
                df.name,
                ma.sku,
                p.name,
                ma.provenance_class
            FROM material_allocations ma
            JOIN facilities sf ON sf.facility_id = ma.source_facility_id
            JOIN facilities df ON df.facility_id = ma.destination_facility_id
            JOIN materials m ON m.material_id = ma.material_id
            JOIN products p ON p.sku = ma.sku
            WHERE ma.source_facility_id = ANY(%s)
              AND ma.approved = true
            ORDER BY ma.source_facility_id, ma.material_id, ma.sku
            """,
            (facility_ids,),
        ).fetchall()

        impacted_skus = sorted({r[2] for r in assembly_rows} | {r[6] for r in material_rows})

        commitments = []
        if impacted_skus:
            commitments = conn.execute(
                """
                SELECT
                    sku,
                    COUNT(*) AS commitment_count,
                    COALESCE(SUM(qty),0) AS commitment_units,
                    COALESCE(SUM(revenue_eur),0) AS revenue_eur,
                    COALESCE(SUM(gross_margin_eur),0) AS gross_margin_eur,
                    MIN(due_date) AS earliest_due_date
                FROM fulfilment_commitments
                WHERE sku = ANY(%s)
                GROUP BY sku
                ORDER BY sku
                """,
                (impacted_skus,),
            ).fetchall()

    distances = {r[0]: round(float(r[4]), 1) for r in exposed}

    facilities = [
        {
            "facility_id": r[0],
            "name": r[1],
            "tier": r[2],
            "product_categories": r[3],
            "distance_km": round(float(r[4]), 1),
            "exposure_status": "POTENTIALLY_EXPOSED",
        }
        for r in exposed
    ]

    paths: list[dict] = []
    for r in assembly_rows:
        paths.append(
            {
                "path_type": "ASSEMBLY",
                "facility_id": r[0],
                "facility_name": r[1],
                "distance_km": distances[r[0]],
                "sku": r[2],
                "product_name": r[3],
                "relationship": r[4],
                "provenance_class": r[5],
                "exposure_status": "POTENTIALLY_EXPOSED",
            }
        )

    for r in material_rows:
        paths.append(
            {
                "path_type": "UPSTREAM_MATERIAL",
                "facility_id": r[0],
                "facility_name": r[1],
                "distance_km": distances[r[0]],
                "material_id": r[2],
                "material_name": r[3],
                "destination_facility_id": r[4],
                "destination_facility_name": r[5],
                "sku": r[6],
                "product_name": r[7],
                "relationship": "source_of_supply",
                "provenance_class": r[8],
                "exposure_status": "POTENTIALLY_EXPOSED",
            }
        )

    product_reasons: dict[str, list[dict]] = defaultdict(list)
    product_names: dict[str, str] = {}
    for path in paths:
        sku = path["sku"]
        product_names[sku] = path["product_name"]
        product_reasons[sku].append(
            {
                "path_type": path["path_type"],
                "facility_id": path["facility_id"],
                "facility_name": path["facility_name"],
                "distance_km": path["distance_km"],
                "material_id": path.get("material_id"),
                "material_name": path.get("material_name"),
                "destination_facility_id": path.get("destination_facility_id"),
                "destination_facility_name": path.get("destination_facility_name"),
            }
        )

    commitment_by_sku = {
        r[0]: {
            "commitment_count": int(r[1]),
            "commitment_units": float(r[2]),
            "revenue_eur": float(r[3]),
            "gross_margin_eur": float(r[4]),
            "earliest_due_date": r[5].isoformat() if r[5] else None,
        }
        for r in commitments
    }

    products = []
    for sku in impacted_skus:
        commercial = commitment_by_sku.get(
            sku,
            {
                "commitment_count": 0,
                "commitment_units": 0.0,
                "revenue_eur": 0.0,
                "gross_margin_eur": 0.0,
                "earliest_due_date": None,
            },
        )
        products.append(
            {
                "sku": sku,
                "name": product_names.get(sku),
                "exposure_status": "POTENTIALLY_EXPOSED",
                "reasons": product_reasons[sku],
                **commercial,
            }
        )

    return {
        "event_id": event_id,
        "radius_km": radius_km,
        "exposure_status": "POTENTIAL_ONLY",
        "facilities": facilities,
        "dependency_paths": paths,
        "products": products,
        "totals": {
            "products_impacted": len(products),
            "commitment_units": sum(p["commitment_units"] for p in products),
            "revenue_eur": round(sum(p["revenue_eur"] for p in products), 2),
            "gross_margin_eur": round(sum(p["gross_margin_eur"] for p in products), 2),
        },
    }
