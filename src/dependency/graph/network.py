from __future__ import annotations

from dependency.db.connection import connect


def network_stats() -> dict:
    with connect() as conn:
        facility_count = conn.execute(
            "SELECT COUNT(*) FROM network_facilities"
        ).fetchone()[0]
        geocoded_count = conn.execute(
            "SELECT COUNT(*) FROM network_facilities WHERE geom IS NOT NULL"
        ).fetchone()[0]
        relationship_count = conn.execute(
            "SELECT COUNT(*) FROM network_list_relationships"
        ).fetchone()[0]
        parent_count = conn.execute(
            "SELECT COUNT(*) FROM network_parent_groups"
        ).fetchone()[0]
        country_count = conn.execute(
            """
            SELECT COUNT(DISTINCT country)
            FROM network_facilities
            WHERE country IS NOT NULL AND trim(country)<>''
            """
        ).fetchone()[0]
        linked_count = conn.execute(
            """
            SELECT COUNT(DISTINCT network_facility_id)
            FROM facility_network_links
            """
        ).fetchone()[0]

    return {
        "network_facilities": int(facility_count),
        "geocoded_facilities": int(geocoded_count),
        "official_list_relationships": int(relationship_count),
        "parent_groups": int(parent_count),
        "countries": int(country_count),
        "business_linked_public_facilities": int(linked_count),
        "truth_model": {
            "official_supplier_relationships": "VERIFIED_PUBLIC",
            "coordinates": "PUBLIC_DERIVED",
            "operational_links": "SIMULATED_PRIVATE",
        },
    }


def list_network_facilities(
    *,
    country: str | None = None,
    list_type: str | None = None,
    business_linked_only: bool = False,
    limit: int = 1000,
) -> list[dict]:
    limit = max(1, min(int(limit), 5000))

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              nf.network_facility_id,nf.os_id,nf.name,nf.official_name,
              nf.country,nf.city,nf.province,nf.tiers,nf.product_categories,
              nf.list_types,nf.parent_organizations,
              ST_Y(nf.geom::geometry),ST_X(nf.geom::geometry),
              nf.coordinate_provenance,nf.official_provenance,
              nf.source_url,nf.osh_url,
              COALESCE(
                array_agg(DISTINCT fnl.facility_id)
                  FILTER (WHERE fnl.facility_id IS NOT NULL),
                ARRAY[]::text[]
              ) AS operational_facility_ids
            FROM network_facilities nf
            LEFT JOIN facility_network_links fnl
              ON fnl.network_facility_id=nf.network_facility_id
            WHERE (%s::text IS NULL OR lower(nf.country)=lower(%s::text))
              AND (
                %s::text IS NULL
                OR lower(COALESCE(nf.list_types,'')) LIKE
                   '%%' || lower(%s::text) || '%%'
              )
              AND (
                NOT %s::boolean
                OR fnl.facility_id IS NOT NULL
              )
            GROUP BY
              nf.network_facility_id,nf.os_id,nf.name,nf.official_name,
              nf.country,nf.city,nf.province,nf.tiers,nf.product_categories,
              nf.list_types,nf.parent_organizations,nf.geom,
              nf.coordinate_provenance,nf.official_provenance,
              nf.source_url,nf.osh_url
            ORDER BY nf.country,nf.name,nf.network_facility_id
            LIMIT %s
            """,
            (
                country,
                country,
                list_type,
                list_type,
                bool(business_linked_only),
                limit,
            ),
        ).fetchall()

    return [
        {
            "network_facility_id": r[0],
            "os_id": r[1],
            "name": r[2],
            "official_name": r[3],
            "country": r[4],
            "city": r[5],
            "province": r[6],
            "tiers": r[7],
            "product_categories": r[8],
            "list_types": r[9],
            "parent_organizations": r[10],
            "latitude": float(r[11]) if r[11] is not None else None,
            "longitude": float(r[12]) if r[12] is not None else None,
            "coordinate_provenance": r[13],
            "official_provenance": r[14],
            "source_url": r[15],
            "osh_url": r[16],
            "operational_facility_ids": list(r[17] or []),
            "business_linked": bool(r[17]),
        }
        for r in rows
    ]
