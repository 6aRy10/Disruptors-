from __future__ import annotations

from datetime import date
from typing import Any

from dependency.db.connection import connect
from dependency.graph.exposure import facilities_within_radius
from dependency.graph.impact import trace_event_impact
from dependency.graph.shared_dependencies import backup_independence
from dependency.risk.operational import scenario_product_risk
from dependency.solver.candidates import generate_recovery_candidates
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


def dispatch_tool(name: str, args: dict[str, Any]) -> Any:
    tools = {
        "get_event": lambda: get_event(**args),
        "find_facilities_near_event": lambda: find_facilities_near_event(**args),
        "trace_downstream_impact": lambda: trace_event_impact(**args),
        "get_customer_commitments": lambda: get_customer_commitments(**args),
        "get_supplier_capacity": lambda: get_supplier_capacity(**args),
        "get_open_purchase_orders": lambda: get_open_purchase_orders(**args),
        "check_backup_independence": lambda: backup_independence(**args),
        "generate_recovery_candidates": lambda: generate_recovery_candidates(**args),
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
