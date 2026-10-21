from __future__ import annotations

from dependency.db.connection import connect


def operational_facilities_within_radius(
    *, latitude: float, longitude: float, radius_km: float
) -> list[dict]:
    """Return private operational-twin facilities within radius_km."""
    sql = """
        SELECT
            facility_id,
            name,
            country,
            city,
            tier,
            product_categories,
            parent_organization,
            ST_Distance(
                geom,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            ) / 1000.0 AS distance_km,
            provenance_class,
            source_url
        FROM facilities
        WHERE geom IS NOT NULL
          AND ST_DWithin(
                geom,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
          )
        ORDER BY distance_km ASC, facility_id ASC
    """
    radius_m = float(radius_km) * 1000.0
    params = (longitude, latitude, longitude, latitude, radius_m)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "facility_id": r[0],
            "name": r[1],
            "country": r[2],
            "city": r[3],
            "tier": r[4],
            "product_categories": r[5],
            "parent_organization": r[6],
            "distance_km": round(float(r[7]), 1),
            "provenance_class": r[8],
            "source_url": r[9],
        }
        for r in rows
    ]


def facilities_within_radius(
    *, latitude: float, longitude: float, radius_km: float
) -> list[dict]:
    """Return the full public adidas network within radius_km.

    Public proximity creates POTENTIALLY_EXPOSED nodes only. business_linked
    tells the caller whether the public node maps into the private operational
    twin and can therefore continue into BOM/orders/recovery.
    """
    sql = """
        SELECT
            nf.network_facility_id,
            nf.os_id,
            nf.name,
            nf.country,
            nf.city,
            nf.tiers,
            nf.product_categories,
            nf.parent_organizations,
            ST_Distance(
                nf.geom,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            ) / 1000.0 AS distance_km,
            nf.coordinate_provenance,
            nf.official_provenance,
            nf.source_url,
            nf.osh_url,
            ARRAY_REMOVE(ARRAY_AGG(fnl.facility_id ORDER BY fnl.facility_id), NULL)
                AS operational_facility_ids
        FROM network_facilities nf
        LEFT JOIN facility_network_links fnl
          ON fnl.network_facility_id = nf.network_facility_id
        WHERE nf.geom IS NOT NULL
          AND ST_DWithin(
                nf.geom,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                %s
          )
        GROUP BY
            nf.network_facility_id,nf.os_id,nf.name,nf.country,nf.city,nf.tiers,
            nf.product_categories,nf.parent_organizations,nf.geom,
            nf.coordinate_provenance,nf.official_provenance,nf.source_url,nf.osh_url
        ORDER BY distance_km ASC, nf.network_facility_id ASC
    """
    radius_m = float(radius_km) * 1000.0
    params = (longitude, latitude, longitude, latitude, radius_m)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "network_facility_id": r[0],
            "os_id": r[1],
            "name": r[2],
            "country": r[3],
            "city": r[4],
            "tier": r[5],
            "product_categories": r[6],
            "parent_organization": r[7],
            "distance_km": round(float(r[8]), 1),
            "coordinate_provenance": r[9],
            "provenance_class": r[10],
            "source_url": r[11],
            "osh_url": r[12],
            "operational_facility_ids": list(r[13] or []),
            "business_linked": bool(r[13]),
            "exposure_status": "POTENTIALLY_EXPOSED",
        }
        for r in rows
    ]
