from __future__ import annotations

import json

from datetime import date
from typing import Any

from rapidfuzz.fuzz import token_set_ratio

from dependency.db.connection import connect
from dependency.graph.exposure import facilities_within_radius
from dependency.graph.impact import trace_event_impact
from dependency.graph.shared_dependencies import backup_independence
from dependency.memory.service import similar_incidents
from dependency.risk.operational import scenario_product_risk
from dependency.services.approvals import list_approval_requests, request_human_approval
from dependency.solver.candidates import generate_recovery_candidates
from dependency.solver.component_feasibility import evaluate_component_feasibility
from dependency.solver.material_timing import purchase_order_supply_by_date
from dependency.solver.portfolio import plan_event_recovery
from dependency.solver.recovery import plan_sku_recovery


def get_event(event_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              event_id,event_type,mode,source,title,occurred_or_effective_at,
              ingested_at,current_as_of,ST_Y(geom::geometry),ST_X(geom::geometry),
              provenance_class,source_url
            FROM external_events
            WHERE event_id = %s
            """,
            (event_id,),
        ).fetchone()
    if not row:
        raise ValueError(f"Unknown event_id: {event_id}")
    return {
        "event_id": row[0],
        "event_type": row[1],
        "mode": row[2],
        "source": row[3],
        "title": row[4],
        "occurred_at": row[5].isoformat() if row[5] else None,
        "ingested_at": row[6].isoformat() if row[6] else None,
        "current_as_of": row[7].isoformat() if row[7] else None,
        "latitude": float(row[8]) if row[8] is not None else None,
        "longitude": float(row[9]) if row[9] is not None else None,
        "provenance_class": row[10],
        "source_url": row[11],
    }


def find_facilities_near_event(event_id: str, radius_km: float = 150.0) -> dict:
    event = get_event(event_id)
    rows = facilities_within_radius(
        latitude=event["latitude"],
        longitude=event["longitude"],
        radius_km=radius_km,
    )
    return {
        "event_id": event_id,
        "radius_km": radius_km,
        "exposure_status": "POTENTIAL_ONLY",
        "facility_count": len(rows),
        "facilities": rows,
    }


def get_customer_commitments(sku: str) -> dict:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              commitment_id,customer_or_market,market,qty,due_date,
              revenue_eur,gross_margin_eur,priority,partial_allowed
            FROM fulfilment_commitments
            WHERE sku = %s
            ORDER BY priority,due_date,commitment_id
            """,
            (sku,),
        ).fetchall()
    return {
        "sku": sku,
        "commitments": [
            {
                "commitment_id": r[0],
                "customer_or_market": r[1],
                "market": r[2],
                "qty": float(r[3]),
                "due_date": r[4].isoformat() if r[4] else None,
                "revenue_eur": float(r[5] or 0),
                "gross_margin_eur": float(r[6] or 0),
                "priority": int(r[7] or 0),
                "partial_allowed": bool(r[8]),
            }
            for r in rows
        ],
    }


def get_supplier_capacity(facility_id: str, sku: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT week_start,capacity_units,committed_units,status,
                   evidence_age_hours,source,provenance_class
            FROM supplier_capacity
            WHERE facility_id = %s AND sku = %s
            ORDER BY week_start DESC
            LIMIT 1
            """,
            (facility_id, sku),
        ).fetchone()
    if not row:
        raise ValueError(
            f"No supplier capacity for facility_id={facility_id} sku={sku}"
        )
    return {
        "facility_id": facility_id,
        "sku": sku,
        "week_start": row[0].isoformat(),
        "capacity_units": float(row[1]),
        "committed_units": float(row[2]),
        "available_capacity_units": max(0.0, float(row[1]) - float(row[2])),
        "status": row[3],
        "evidence_age_hours": float(row[4] or 0),
        "source": row[5],
        "provenance_class": row[6],
    }


def get_open_purchase_orders(material_id: str, need_by: str) -> dict:
    return purchase_order_supply_by_date(
        material_id=material_id,
        need_by=date.fromisoformat(need_by),
    )



def search_event_evidence(event_id: str) -> dict:
    event = get_event(event_id)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              i.incident_id,i.status,e.evidence_id,e.evidence_type,e.source_name,
              e.source_url,e.fact_json,e.confidence,e.observed_at,e.provenance_class
            FROM incidents i
            LEFT JOIN incident_evidence e ON e.incident_id=i.incident_id
            WHERE i.event_id=%s
            ORDER BY i.detected_at,e.observed_at,e.evidence_id
            """,
            (event_id,),
        ).fetchall()

    evidence = [
        {
            "incident_id": r[0],
            "incident_status": r[1],
            "evidence_id": r[2],
            "evidence_type": r[3],
            "source_name": r[4],
            "source_url": r[5],
            "fact": r[6],
            "confidence": float(r[7]) if r[7] is not None else None,
            "observed_at": r[8].isoformat() if r[8] else None,
            "provenance_class": r[9],
        }
        for r in rows
        if r[2] is not None
    ]
    return {
        "event": event,
        "stored_evidence": evidence,
        "evidence_count": len(evidence),
        "rule": (
            "Stored evidence can support current claims only at its stated provenance "
            "and confidence. Public proximity alone is not proof of shutdown."
        ),
    }


def normalize_company(name: str, country: str | None = None, limit: int = 5) -> dict:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              network_facility_id,os_id,name,official_name,country,city,
              parent_organizations,source_url,osh_url,official_provenance
            FROM network_facilities
            WHERE (%s IS NULL OR lower(country)=lower(%s))
            ORDER BY network_facility_id
            """,
            (country, country),
        ).fetchall()

    scored = []
    query = str(name or "").strip().lower()
    query_key = "".join(ch for ch in query if ch.isalnum())
    for row in rows:
        candidate_text = " ".join(
            x for x in [row[2], row[3], row[6]] if x
        ).lower()
        name_key = "".join(ch for ch in str(row[2] or "").lower() if ch.isalnum())
        official_key = "".join(
            ch for ch in str(row[3] or "").lower() if ch.isalnum()
        )
        if query_key and query_key in {name_key, official_key}:
            score = 100.0
        else:
            score = float(token_set_ratio(query, candidate_text))
        scored.append(
            {
                "network_facility_id": row[0],
                "os_id": row[1],
                "name": row[2],
                "official_name": row[3],
                "country": row[4],
                "city": row[5],
                "parent_organizations": row[6],
                "source_url": row[7],
                "osh_url": row[8],
                "provenance_class": row[9],
                "match_score": round(score, 1),
            }
        )
    scored.sort(key=lambda x: (-x["match_score"], x["network_facility_id"]))
    return {
        "query": name,
        "country": country,
        "matches": scored[: max(1, min(int(limit), 20))],
        "rule": "Candidate entity matches require human or deterministic confirmation before new dependency edges are created.",
    }


def trace_upstream_dependencies(
    sku: str,
    destination_facility_id: str | None = None,
) -> dict:
    with connect() as conn:
        bom_rows = conn.execute(
            """
            SELECT b.material_id,m.name,m.criticality,b.qty_per_unit,b.provenance_class
            FROM bom b
            JOIN materials m ON m.material_id=b.material_id
            WHERE b.sku=%s
            ORDER BY b.material_id
            """,
            (sku,),
        ).fetchall()

        if destination_facility_id:
            allocation_rows = conn.execute(
                """
                SELECT
                  ma.material_id,ma.source_facility_id,sf.name,
                  ma.destination_facility_id,df.name,ma.allocation_share,
                  ma.provenance_class
                FROM material_allocations ma
                JOIN facilities sf ON sf.facility_id=ma.source_facility_id
                JOIN facilities df ON df.facility_id=ma.destination_facility_id
                WHERE ma.sku=%s
                  AND ma.destination_facility_id=%s
                  AND ma.approved=true
                ORDER BY ma.material_id,ma.source_facility_id
                """,
                (sku, destination_facility_id),
            ).fetchall()
        else:
            allocation_rows = conn.execute(
                """
                SELECT
                  ma.material_id,ma.source_facility_id,sf.name,
                  ma.destination_facility_id,df.name,ma.allocation_share,
                  ma.provenance_class
                FROM material_allocations ma
                JOIN facilities sf ON sf.facility_id=ma.source_facility_id
                JOIN facilities df ON df.facility_id=ma.destination_facility_id
                WHERE ma.sku=%s
                  AND ma.approved=true
                ORDER BY ma.destination_facility_id,ma.material_id,ma.source_facility_id
                """,
                (sku,),
            ).fetchall()

        source_rows = conn.execute(
            """
            SELECT
              ms.material_id,ms.facility_id,f.name,ms.role,ms.lead_time_days,
              ms.weekly_capacity_units,ms.provenance_class
            FROM material_sources ms
            JOIN facilities f ON f.facility_id=ms.facility_id
            WHERE ms.approved=true
              AND ms.material_id IN (
                SELECT material_id FROM bom WHERE sku=%s
              )
            ORDER BY ms.material_id,ms.facility_id
            """,
            (sku,),
        ).fetchall()

    return {
        "sku": sku,
        "destination_facility_id": destination_facility_id,
        "bom": [
            {
                "material_id": r[0],
                "material_name": r[1],
                "criticality": r[2],
                "qty_per_unit": float(r[3]),
                "provenance_class": r[4],
            }
            for r in bom_rows
        ],
        "allocated_paths": [
            {
                "material_id": r[0],
                "source_facility_id": r[1],
                "source_facility_name": r[2],
                "destination_facility_id": r[3],
                "destination_facility_name": r[4],
                "allocation_share": float(r[5] or 0),
                "provenance_class": r[6],
            }
            for r in allocation_rows
        ],
        "approved_source_catalog": [
            {
                "material_id": r[0],
                "facility_id": r[1],
                "facility_name": r[2],
                "role": r[3],
                "lead_time_days": int(r[4] or 0),
                "weekly_capacity_units": float(r[5] or 0),
                "provenance_class": r[6],
            }
            for r in source_rows
        ],
    }


def explode_bom(sku: str, units: float = 1.0) -> dict:
    if units < 0:
        raise ValueError("units must be >= 0")
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT b.material_id,m.name,m.uom,m.criticality,b.qty_per_unit,b.provenance_class
            FROM bom b
            JOIN materials m ON m.material_id=b.material_id
            WHERE b.sku=%s
            ORDER BY b.material_id
            """,
            (sku,),
        ).fetchall()
    if not rows:
        raise ValueError(f"No BOM for sku={sku}")
    return {
        "sku": sku,
        "units": float(units),
        "requirements": [
            {
                "material_id": r[0],
                "material_name": r[1],
                "uom": r[2],
                "criticality": r[3],
                "qty_per_unit": float(r[4]),
                "required_qty": round(float(r[4]) * float(units), 4),
                "provenance_class": r[5],
            }
            for r in rows
        ],
    }


def get_inventory(item_id: str, item_type: str = "finished_good") -> dict:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT site_id,qty_on_hand,qty_reserved,safety_stock,updated_at,provenance_class
            FROM inventory
            WHERE item_type=%s AND item_id=%s
            ORDER BY site_id
            """,
            (item_type, item_id),
        ).fetchall()
    return {
        "item_id": item_id,
        "item_type": item_type,
        "sites": [
            {
                "site_id": r[0],
                "qty_on_hand": float(r[1]),
                "qty_reserved": float(r[2]),
                "safety_stock": float(r[3]),
                "usable_without_safety_stock": max(
                    0.0,
                    float(r[1]) - float(r[2]) - float(r[3]),
                ),
                "updated_at": r[4].isoformat() if r[4] else None,
                "provenance_class": r[5],
            }
            for r in rows
        ],
    }


def get_approved_alternatives(material_id: str) -> dict:
    with connect() as conn:
        substitutions = conn.execute(
            """
            SELECT
              s.substitute_material_id,m.name,s.max_ratio,s.engineering_status,
              s.provenance_class
            FROM substitutions s
            JOIN materials m ON m.material_id=s.substitute_material_id
            WHERE s.material_id=%s AND s.approved=true
            ORDER BY s.substitute_material_id
            """,
            (material_id,),
        ).fetchall()
        sources = conn.execute(
            """
            SELECT
              ms.facility_id,f.name,ms.role,ms.lead_time_days,
              ms.weekly_capacity_units,ms.provenance_class
            FROM material_sources ms
            JOIN facilities f ON f.facility_id=ms.facility_id
            WHERE ms.material_id=%s AND ms.approved=true
            ORDER BY
              CASE WHEN ms.role='primary' THEN 1 ELSE 0 END,
              ms.lead_time_days,ms.facility_id
            """,
            (material_id,),
        ).fetchall()
    return {
        "material_id": material_id,
        "approved_substitutions": [
            {
                "substitute_material_id": r[0],
                "name": r[1],
                "max_ratio": float(r[2] or 0),
                "engineering_status": r[3],
                "provenance_class": r[4],
            }
            for r in substitutions
        ],
        "approved_sources": [
            {
                "facility_id": r[0],
                "facility_name": r[1],
                "role": r[2],
                "lead_time_days": int(r[3] or 0),
                "weekly_capacity_units": float(r[4] or 0),
                "provenance_class": r[5],
            }
            for r in sources
        ],
    }


def get_transport_options(
    origin_facility_id: str,
    destination_market: str,
) -> dict:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
              lane_id,port_unlocode,port_name,mode,transit_days,
              cost_eur_per_unit,status,policy_tag,provenance_class
            FROM transport_lanes
            WHERE origin_facility_id=%s
              AND lower(destination_market)=lower(%s)
            ORDER BY transit_days,cost_eur_per_unit,lane_id
            """,
            (origin_facility_id, destination_market),
        ).fetchall()
    return {
        "origin_facility_id": origin_facility_id,
        "destination_market": destination_market,
        "options": [
            {
                "lane_id": r[0],
                "port_unlocode": r[1],
                "port_name": r[2],
                "mode": r[3],
                "transit_days": int(r[4] or 0),
                "cost_eur_per_unit": float(r[5] or 0),
                "status": r[6],
                "policy_tag": r[7],
                "provenance_class": r[8],
            }
            for r in rows
        ],
    }


def find_similar_incidents(event_type: str, limit: int = 5) -> dict:
    return {
        "event_type": event_type,
        "usage_rule": "HYPOTHESIS_ONLY_RECHECK_CURRENT_STATE",
        "incidents": similar_incidents(event_type=event_type, limit=limit),
    }


def request_human_approval_tool(
    incident_id: str,
    scenario_id: str | None,
    sku: str | None,
    action_type: str,
    action_payload_json: str,
    reason: str,
    plan_record_id: str | None,
) -> dict:
    try:
        payload = json.loads(action_payload_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("action_payload_json must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("action_payload_json must decode to an object")
    return request_human_approval(
        incident_id=incident_id,
        scenario_id=scenario_id,
        sku=sku,
        action_type=action_type,
        action_payload=payload,
        reason=reason,
        requested_by="Recovery Planner",
        plan_record_id=plan_record_id,
    )


def get_pending_approvals(
    incident_id: str | None,
    limit: int = 20,
) -> dict:
    return {
        "incident_id": incident_id,
        "status": "PENDING",
        "approvals": list_approval_requests(
            status="PENDING",
            incident_id=incident_id,
            limit=limit,
        ),
    }

def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    tools = {
        "get_event": lambda: get_event(**args),
        "find_facilities_near_event": lambda: find_facilities_near_event(**args),
        "search_event_evidence": lambda: search_event_evidence(**args),
        "normalize_company": lambda: normalize_company(**args),
        "trace_upstream_dependencies": lambda: trace_upstream_dependencies(**args),
        "explode_bom": lambda: explode_bom(**args),
        "get_inventory": lambda: get_inventory(**args),
        "get_approved_alternatives": lambda: get_approved_alternatives(**args),
        "get_transport_options": lambda: get_transport_options(**args),
        "find_similar_incidents": lambda: find_similar_incidents(**args),
        "request_human_approval": lambda: request_human_approval_tool(**args),
        "get_pending_approvals": lambda: get_pending_approvals(**args),
        "trace_downstream_impact": lambda: trace_event_impact(**args),
        "get_customer_commitments": lambda: get_customer_commitments(**args),
        "get_supplier_capacity": lambda: get_supplier_capacity(**args),
        "get_open_purchase_orders": lambda: get_open_purchase_orders(**args),
        "check_backup_independence": lambda: backup_independence(**args),
        "generate_recovery_candidates": lambda: generate_recovery_candidates(**args),
        "check_component_feasibility": lambda: evaluate_component_feasibility(**args),
        "get_recovery_plan": lambda: plan_sku_recovery(**args),
        "get_product_risk": lambda: scenario_product_risk(**args),
        "get_event_portfolio": lambda: plan_event_recovery(**args),
    }
    if name not in tools:
        raise ValueError(f"Unknown agent tool: {name}")
    return tools[name]()


TOOL_SCHEMAS = [
    {
        "type": "function",
        "name": "get_event",
        "description": "Get one normalized external event and its provenance.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "find_facilities_near_event",
        "description": "Use PostGIS to find public adidas network facilities near an event. Proximity means potential exposure only.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "radius_km": {"type": "number"},
            },
            "required": ["event_id", "radius_km"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "search_event_evidence",
        "description": "Return stored evidence and provenance for an external event. This does not invent corroboration.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "normalize_company",
        "description": "Resolve a company or facility name against the public supply network and return ranked candidate matches.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "country": {"type": ["string", "null"]},
                "limit": {"type": "integer"},
            },
            "required": ["name", "country", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "trace_upstream_dependencies",
        "description": "Return the SKU BOM, explicit source-to-assembly allocations, and approved source catalog.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "destination_facility_id": {"type": ["string", "null"]},
            },
            "required": ["sku", "destination_facility_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "explode_bom",
        "description": "Calculate exact material requirements for a SKU quantity from the stored BOM.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "units": {"type": "number"},
            },
            "required": ["sku", "units"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_inventory",
        "description": "Return on-hand, reserved, safety-stock, and usable inventory by site.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "item_type": {"type": "string"},
            },
            "required": ["item_id", "item_type"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_approved_alternatives",
        "description": "Return approved material substitutions and approved supplier-source alternatives.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"material_id": {"type": "string"}},
            "required": ["material_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_transport_options",
        "description": "Return modeled transport lanes from one facility to a destination market, including transit time, cost, and status.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "origin_facility_id": {"type": "string"},
                "destination_market": {"type": "string"},
            },
            "required": ["origin_facility_id", "destination_market"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "find_similar_incidents",
        "description": "Retrieve closed same-type incidents as hypotheses only. Current state must always be rechecked.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["event_type", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "request_human_approval",
        "description": "Create a durable human-approval request. This records a request only; it does not execute the action.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "scenario_id": {"type": ["string", "null"]},
                "sku": {"type": ["string", "null"]},
                "action_type": {"type": "string"},
                "action_payload_json": {"type": "string"},
                "reason": {"type": "string"},
                "plan_record_id": {"type": ["string", "null"]},
            },
            "required": [
                "incident_id",
                "scenario_id",
                "sku",
                "action_type",
                "action_payload_json",
                "reason",
                "plan_record_id"
            ],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_pending_approvals",
        "description": "Return pending human-approval requests, optionally limited to one incident.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "incident_id": {"type": ["string", "null"]},
                "limit": {"type": "integer"},
            },
            "required": ["incident_id", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "trace_downstream_impact",
        "description": "Trace an event through operational facilities, explicit material allocations, SKUs and commercial commitments.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "radius_km": {"type": "number"},
            },
            "required": ["event_id", "radius_km"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_customer_commitments",
        "description": "Return deterministic customer commitments, due dates, revenue and margin for one SKU.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {"sku": {"type": "string"}},
            "required": ["sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_supplier_capacity",
        "description": "Return the latest stored capacity evidence for an approved facility/SKU.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "facility_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["facility_id", "sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_open_purchase_orders",
        "description": "Return confirmed purchase-order supply usable by a specified need-by date and exclude late arrivals.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "material_id": {"type": "string"},
                "need_by": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            },
            "required": ["material_id", "need_by"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "check_backup_independence",
        "description": "Check whether a proposed backup assembly facility shares explicit upstream material sources with the primary facility.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "primary_facility_id": {"type": "string"},
                "backup_facility_id": {"type": "string"},
            },
            "required": ["sku", "primary_facility_id", "backup_facility_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "check_component_feasibility",
        "description": "Verify BOM component coverage for a proposed production quantity at one facility by a need-by date. Confirmed POs count only from explicit allocated sources; modeled source capacity stays provisional.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "sku": {"type": "string"},
                "destination_facility_id": {"type": "string"},
                "production_units": {"type": "number"},
                "need_by": {"type": "string", "description": "ISO date YYYY-MM-DD"},
            },
            "required": [
                "scenario_id",
                "sku",
                "destination_facility_id",
                "production_units",
                "need_by"
            ],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "generate_recovery_candidates",
        "description": "Generate judge-facing recovery candidates with deterministic rejection reasons.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["scenario_id", "sku"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_recovery_plan",
        "description": "Run the deterministic recovery solver for one scenario/SKU.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "sku": {"type": "string"},
                "release_safety_stock": {"type": "boolean"},
            },
            "required": ["scenario_id", "sku", "release_safety_stock"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_event_portfolio",
        "description": "Evaluate every SKU reached by an event and return the deterministic event-level recovery portfolio, action queue, rejected actions, and shared-resource conflicts.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "scenario_id": {"type": "string"},
                "radius_km": {"type": "number"},
            },
            "required": ["event_id", "scenario_id", "radius_km"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_product_risk",
        "description": "Calculate the current deterministic business-risk score and factors for a scenario/SKU.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "scenario_id": {"type": "string"},
                "sku": {"type": "string"},
            },
            "required": ["scenario_id", "sku"],
            "additionalProperties": False,
        },
    },
]
