from __future__ import annotations

from dependency.db.connection import connect


def facilities_within_radius(*, latitude: float, longitude: float, radius_km: float) -> list[dict]:
    """Return facilities whose PostGIS point lies within radius_km of an event."""
    sql = """
        SELECT
            facility_id,
            name,
            country,
            city,
            tier,
            product_categories,
            parent_organization,
            ROUND(
                ST_Distance(
                    geom,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) / 1000.0,
                1
            ) AS distance_km,
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
        cols = [d.name for d in conn.execute(sql + " LIMIT 0", params).description] if False else None
        return [
            {
                "facility_id": r[0],
                "name": r[1],
                "country": r[2],
                "city": r[3],
                "tier": r[4],
                "product_categories": r[5],
                "parent_organization": r[6],
                "distance_km": float(r[7]),
                "provenance_class": r[8],
                "source_url": r[9],
            }
            for r in rows
        ]
