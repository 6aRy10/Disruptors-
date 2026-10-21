"""Bounded public-map and connected-facility views for the Hermes application.

No simulated facility-product relationship is presented as public evidence.
A facility's connected commercial value is POTENTIAL exposure, not loss.
"""
from __future__ import annotations

from math import isfinite
from dependency.db.connection import connect


def _bounds(west: float, south: float, east: float, north: float) -> None:
    if not all(isfinite(float(v)) for v in (west,south,east,north)):
        raise ValueError("Map bounds must be finite.")
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError("Longitude must be between -180 and 180.")
    if not (-90 <= south < north <= 90):
        raise ValueError("Invalid latitude bounds.")


def map_facilities(
    *, west: float = -180, south: float = -85,
    east: float = 180, north: float = 85,
    country: str | None = None,
    business_linked_only: bool = False,
    limit: int = 1000,
) -> dict:
    """Return visible geocoded sites. Dateline-crossing bounds are supported."""
    _bounds(west,south,east,north)
    if not 1 <= limit <= 2500:
        raise ValueError("limit must be between 1 and 2500.")
    if country is not None and len(country) > 120:
        raise ValueError("Country filter is too long.")
    with connect() as conn:
        rows=conn.execute(
            """
            SELECT nf.network_facility_id,
                   COALESCE(NULLIF(nf.official_name,''),nf.name),
                   nf.country,nf.city,nf.tiers,
                   ST_Y(nf.geom::geometry),ST_X(nf.geom::geometry),
                   nf.coordinate_provenance,nf.official_provenance,
                   nf.source_url,
                   COALESCE(array_agg(DISTINCT fnl.facility_id)
                     FILTER (WHERE fnl.facility_id IS NOT NULL), ARRAY[]::text[]),
                   COUNT(*) OVER()
            FROM network_facilities nf
            LEFT JOIN facility_network_links fnl
              ON fnl.network_facility_id=nf.network_facility_id
            WHERE nf.geom IS NOT NULL
              AND ST_Y(nf.geom::geometry) BETWEEN %s AND %s
              AND (
                  (%s <= %s AND ST_X(nf.geom::geometry) BETWEEN %s AND %s)
                  OR (%s > %s AND
                     (ST_X(nf.geom::geometry) >= %s
                      OR ST_X(nf.geom::geometry) <= %s))
              )
              AND (%s::text IS NULL OR lower(nf.country)=lower(%s))
            GROUP BY nf.network_facility_id
            HAVING (NOT %s::boolean OR COUNT(fnl.facility_id)>0)
            ORDER BY nf.network_facility_id
            LIMIT %s
            """,
            (
                south,north,west,east,west,east,
                west,east,west,east,country,country,
                business_linked_only,limit,
            ),
        ).fetchall()
    total=int(rows[0][11]) if rows else 0
    facilities=[{
        "id":r[0],"name":r[1],"country":r[2],"city":r[3],
        "tier":r[4],"latitude":float(r[5]),"longitude":float(r[6]),
        "coordinate_provenance":r[7],"identity_provenance":r[8],
        "source_url":r[9],
        "operational_facility_ids":list(r[10] or []),
        "business_linked":bool(r[10]),
        "operational_link_provenance": (
            "SIMULATED_PRIVATE" if r[10] else "NOT_LINKED"
        ),
    } for r in rows]
    return {
        "facilities":facilities,
        "total_in_view":total,
        "shown":len(facilities),
        "truncated":total>len(facilities),
        "bounds":{"west":west,"south":south,"east":east,"north":north},
        "truth_rule": (
            "Coordinates are public-derived. Private facility and product "
            "links are explicitly simulated; distance never proves disruption."
        ),
    }


def facility_profile(*, network_facility_id: str, max_products: int = 25) -> dict:
    """Open a map object and follow explicit downstream company dependencies."""
    if not 1 <= max_products <= 100:
        raise ValueError("max_products must be between 1 and 100.")
    with connect() as conn:
        site=conn.execute(
            """
            SELECT network_facility_id,COALESCE(NULLIF(official_name,''),name),
                   country,city,province,tiers,product_categories,
                   ST_Y(geom::geometry),ST_X(geom::geometry),
                   coordinate_provenance,official_provenance,
                   source_url,osh_url
            FROM network_facilities WHERE network_facility_id=%s
            """,
            (network_facility_id,),
        ).fetchone()
        if not site:
            raise ValueError("Unknown public network facility.")
        linked=conn.execute(
            """
            SELECT f.facility_id,f.name,f.country,f.tier,
                   fnl.match_method,fnl.match_confidence,
                   fnl.provenance_class
            FROM facility_network_links fnl
            JOIN facilities f ON f.facility_id=fnl.facility_id
            WHERE fnl.network_facility_id=%s
            ORDER BY f.facility_id
            """,
            (network_facility_id,),
        ).fetchall()
        products=conn.execute(
            """
            WITH refs AS (
                SELECT pf.sku,'ASSEMBLY'::text AS relation
                FROM facility_network_links fnl
                JOIN product_facilities pf ON pf.facility_id=fnl.facility_id
                WHERE fnl.network_facility_id=%s AND pf.approved=true
                UNION
                SELECT ma.sku,'UPSTREAM_MATERIAL'::text AS relation
                FROM facility_network_links fnl
                JOIN material_allocations ma
                  ON ma.source_facility_id=fnl.facility_id
                WHERE fnl.network_facility_id=%s AND ma.approved=true
            ),
            grouped AS (
                SELECT sku,array_agg(DISTINCT relation ORDER BY relation) AS relations
                FROM refs GROUP BY sku
            ),
            priced AS (
                SELECT g.sku,g.relations,p.name,p.category,
                       COALESCE((
                         SELECT SUM(fc.qty) FROM fulfilment_commitments fc
                         WHERE fc.sku=g.sku
                       ),0) AS commitment_units,
                       COALESCE((
                         SELECT SUM(fc.revenue_eur) FROM fulfilment_commitments fc
                         WHERE fc.sku=g.sku
                       ),0) AS connected_revenue_eur
                FROM grouped g JOIN products p ON p.sku=g.sku
            )
            SELECT sku,relations,name,category,commitment_units,
                   connected_revenue_eur,
                   COUNT(*) OVER(),
                   SUM(connected_revenue_eur) OVER()
            FROM priced ORDER BY sku LIMIT %s
            """,
            (network_facility_id,network_facility_id,max_products),
        ).fetchall()
    all_count=int(products[0][6]) if products else 0
    all_revenue=float(products[0][7] or 0) if products else 0.0
    return {
        "id":site[0],"name":site[1],"country":site[2],
        "city":site[3],"province":site[4],"tier":site[5],
        "product_categories":site[6],
        "latitude":float(site[7]) if site[7] is not None else None,
        "longitude":float(site[8]) if site[8] is not None else None,
        "coordinate_provenance":site[9],"identity_provenance":site[10],
        "source_url":site[11],"osh_url":site[12],
        "operational_links":[{
            "facility_id":r[0],"name":r[1],"country":r[2],
            "tier":r[3],"match_method":r[4],
            "match_confidence":float(r[5]),
            "provenance_class":r[6],
        } for r in linked],
        "connected_products":[{
            "sku":r[0],"relations":list(r[1] or []),"name":r[2],
            "category":r[3],"commitment_units":float(r[4] or 0),
            "connected_revenue_eur":float(r[5] or 0),
            "provenance_class":"SIMULATED_PRIVATE",
        } for r in products],
        "connected_product_count":all_count,
        "products_truncated":len(products)<all_count,
        "total_connected_revenue_eur":all_revenue,
        "commercial_exposure_status":"POTENTIAL_NOT_CONFIRMED_LOSS",
        "truth_rule":(
            "Public identity and coordinates are separate from simulated "
            "operational facility links and commercial commitments. A site "
            "selection does not confirm any disruption."
        ),
    }

def incident_inbox(*, limit: int = 50) -> dict:
    """List real unresolved incidents and outstanding tasks for first-session focus."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200.")
    with connect() as conn:
        rows=conn.execute(
            """
            SELECT i.incident_id,i.event_id,i.status,i.scenario_id,
                   i.detected_at,e.title,e.event_type,e.mode,e.source,
                   COUNT(t.task_id) FILTER (WHERE t.status='OPEN') AS open_tasks
            FROM incidents i
            JOIN external_events e ON e.event_id=i.event_id
            LEFT JOIN incident_investigation_tasks t
              ON t.incident_id=i.incident_id
            WHERE i.status IN ('OPEN','INVESTIGATING')
            GROUP BY i.incident_id,e.event_id
            ORDER BY COUNT(t.task_id) FILTER (WHERE t.status='OPEN') DESC,
                     i.detected_at DESC,i.incident_id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return {"incidents":[{
        "incident_id":r[0],"event_id":r[1],"status":r[2],
        "scenario_id":r[3],
        "detected_at":r[4].isoformat() if r[4] else None,
        "title":r[5],"event_type":r[6],"mode":r[7],"source":r[8],
        "open_evidence_tasks":int(r[9]),
    } for r in rows],
    "truth_rule":"An open incident is not proof of supplier damage."}

def event_context(*, event_id: str) -> dict:
    """One event's location, incident and outstanding evidence work."""
    with connect() as conn:
        e=conn.execute(
            """
            SELECT event_id,event_type,source,mode,title,
                   occurred_or_effective_at,source_url,provenance_class,
                   CASE WHEN geom IS NOT NULL THEN
                     ST_Y(ST_PointOnSurface(geom::geometry)) END,
                   CASE WHEN geom IS NOT NULL THEN
                     ST_X(ST_PointOnSurface(geom::geometry)) END
            FROM external_events WHERE event_id=%s
            """,
            (event_id,),
        ).fetchone()
        if not e:
            raise ValueError("Unknown event.")
        incident=conn.execute(
            """
            SELECT incident_id,status,scenario_id
            FROM incidents WHERE event_id=%s
            ORDER BY detected_at DESC,incident_id LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        tasks=[]
        if incident:
            tasks=conn.execute(
                """
                SELECT task_id,task_type,target_type,target_id,required_fact,
                       connected_skus
                FROM incident_investigation_tasks
                WHERE incident_id=%s AND status='OPEN'
                ORDER BY connected_margin_eur DESC,created_at LIMIT 50
                """,
                (incident[0],),
            ).fetchall()
    return {
        "event":{
            "event_id":e[0],"event_type":e[1],"source":e[2],"mode":e[3],
            "title":e[4],
            "occurred_at":e[5].isoformat() if e[5] else None,
            "source_url":e[6],"provenance_class":e[7],
            "latitude":float(e[8]) if e[8] is not None else None,
            "longitude":float(e[9]) if e[9] is not None else None,
        },
        "incident":({
            "incident_id":incident[0],"status":incident[1],
            "scenario_id":incident[2],
        } if incident else None),
        "evidence_tasks":[{
            "task_id":r[0],"task_type":r[1],"target_type":r[2],
            "target_id":r[3],"required_fact":r[4],
            "connected_skus":r[5],
        } for r in tasks],
        "claim_rule":"Public proximity is not confirmed operational damage.",
    }
