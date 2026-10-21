from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dependency.db.connection import connect, postgis_version
from dependency.agents.orchestrator import run_incident_agents
from dependency.memory.service import get_incident_memory, similar_incidents
from dependency.graph.exposure import facilities_within_radius
from dependency.graph.impact import trace_event_impact
from dependency.ingest.events import list_recent_events
from dependency.services.capacity import confirm_supplier_capacity
from dependency.services.demo_reset import reset_demo_state
from dependency.services.state_updates import (
    update_facility_state,
    update_inventory,
    update_purchase_order_eta,
    update_setup_lead_time,
    update_substitution_approval,
)
from dependency.risk.operational import scenario_product_risk
from dependency.solver.recovery import plan_sku_recovery
from dependency.solver.candidates import generate_recovery_candidates
from dependency.graph.shared_dependencies import backup_independence
from dependency.solver.tariff import tariff_impact
from dependency.supplier_confirmations import parse_supplier_reply

app = FastAPI(
    title="Disruptors Dependency API",
    version="0.2.0",
    description="Event-to-exposure-to-recovery API backed by PostgreSQL/PostGIS.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SupplierReply(BaseModel):
    text: str


class AgentIncidentRequest(BaseModel):
    event_id: str
    scenario_id: str
    sku: str
    radius_km: float = Field(default=150.0, gt=0, le=1000)
    model: str | None = None
    persist: bool = True


class InventoryUpdate(BaseModel):
    site_id: str
    item_type: str
    item_id: str
    qty_on_hand: float = Field(ge=0)
    qty_reserved: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    scenario_id: str | None = None
    sku: str | None = None


class LeadTimeUpdate(BaseModel):
    sku: str
    facility_id: str
    setup_lead_days: int = Field(ge=0)
    scenario_id: str | None = None


class PurchaseOrderEtaUpdate(BaseModel):
    po_id: str
    eta: str
    scenario_id: str | None = None
    sku: str | None = None


class FacilityStateUpdate(BaseModel):
    scenario_id: str
    facility_id: str
    status: str
    capacity_multiplier: float = Field(ge=0, le=1)
    confirmed: bool = True
    source_type: str = "JUDGE_EDIT"
    reason: str = "Judge changed facility state."
    sku: str | None = None


class SubstitutionApprovalUpdate(BaseModel):
    material_id: str
    substitute_material_id: str
    approved: bool
    engineering_status: str
    scenario_id: str | None = None
    sku: str | None = None


class CapacityConfirmation(BaseModel):
    facility_id: str
    sku: str
    capacity_units: int = Field(ge=0)
    valid_until: str | None = None
    source_channel: str = "Slack Connect"
    raw_message: str | None = None
    scenario_id: str | None = None
    release_safety_stock: bool = False


def _update_with_optional_replan(
    update: dict,
    *,
    scenario_id: str | None,
    sku: str | None,
):
    response = {"update": update}
    if scenario_id and sku:
        response["replan"] = plan_sku_recovery(
            scenario_id=scenario_id,
            sku=sku,
            release_safety_stock=False,
        )
        response["risk"] = scenario_product_risk(
            scenario_id=scenario_id,
            sku=sku,
        )
    return response


@app.get("/health")
def health():
    with connect() as conn:
        version = conn.execute(
            "SELECT version FROM operational_state_version WHERE singleton = true"
        ).fetchone()[0]
        db_version = conn.execute("SHOW server_version").fetchone()[0]

    return {
        "ok": True,
        "database": "postgresql",
        "postgres_version": db_version,
        "postgis_version": postgis_version(),
        "state_version": int(version),
    }


@app.get("/events")
def events(limit: int = Query(default=50, ge=1, le=500)):
    return {"events": list_recent_events(limit=limit)}


@app.get("/events/{event_id}/exposure")
def event_exposure(
    event_id: str,
    radius_km: float = Query(default=100.0, gt=0, le=1000),
):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT ST_Y(geom::geometry), ST_X(geom::geometry)
            FROM external_events
            WHERE event_id = %s
            """,
            (event_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Event not found.")

    facilities = facilities_within_radius(
        latitude=float(row[0]),
        longitude=float(row[1]),
        radius_km=radius_km,
    )
    return {
        "event_id": event_id,
        "radius_km": radius_km,
        "exposure_status": "POTENTIAL_ONLY",
        "facilities": facilities,
    }


@app.get("/events/{event_id}/impact")
def event_impact(
    event_id: str,
    radius_km: float = Query(default=100.0, gt=0, le=1000),
):
    return trace_event_impact(event_id=event_id, radius_km=radius_km)


@app.get("/scenarios/{scenario_id}/recovery/{sku}")
def scenario_recovery(
    scenario_id: str,
    sku: str,
    release_safety_stock: bool = False,
):
    try:
        return plan_sku_recovery(
            scenario_id=scenario_id,
            sku=sku,
            release_safety_stock=release_safety_stock,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/scenarios/{scenario_id}/candidates/{sku}")
def scenario_candidates(scenario_id: str, sku: str):
    try:
        return {
            "scenario_id": scenario_id,
            "sku": sku,
            "plans": generate_recovery_candidates(
                scenario_id=scenario_id,
                sku=sku,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/products/{sku}/backup-independence")
def product_backup_independence(
    sku: str,
    primary_facility_id: str,
    backup_facility_id: str,
):
    return backup_independence(
        sku=sku,
        primary_facility_id=primary_facility_id,
        backup_facility_id=backup_facility_id,
    )


@app.get("/scenarios/{scenario_id}/risk/{sku}")
def scenario_risk(scenario_id: str, sku: str):
    try:
        return scenario_product_risk(scenario_id=scenario_id, sku=sku)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/suppliers/capacity/parse")
def supplier_capacity_parse(body: SupplierReply):
    return parse_supplier_reply(body.text)


@app.post("/suppliers/capacity/confirm")
def supplier_capacity_confirm(body: CapacityConfirmation):
    update = confirm_supplier_capacity(
        facility_id=body.facility_id,
        sku=body.sku,
        capacity_units=body.capacity_units,
        valid_until=body.valid_until,
        source_channel=body.source_channel,
        raw_message=body.raw_message,
    )

    response = {"update": update}
    if body.scenario_id:
        response["replan"] = plan_sku_recovery(
            scenario_id=body.scenario_id,
            sku=body.sku,
            release_safety_stock=body.release_safety_stock,
        )
    return response


@app.post("/demo/reset")
def demo_reset():
    return reset_demo_state()


@app.post("/state/inventory")
def state_inventory(body: InventoryUpdate):
    try:
        update = update_inventory(
            site_id=body.site_id,
            item_type=body.item_type,
            item_id=body.item_id,
            qty_on_hand=body.qty_on_hand,
            qty_reserved=body.qty_reserved,
            safety_stock=body.safety_stock,
        )
        return _update_with_optional_replan(
            update,
            scenario_id=body.scenario_id,
            sku=body.sku,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/state/lead-time")
def state_lead_time(body: LeadTimeUpdate):
    try:
        update = update_setup_lead_time(
            sku=body.sku,
            facility_id=body.facility_id,
            setup_lead_days=body.setup_lead_days,
        )
        return _update_with_optional_replan(
            update,
            scenario_id=body.scenario_id,
            sku=body.sku,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/state/purchase-order-eta")
def state_purchase_order_eta(body: PurchaseOrderEtaUpdate):
    try:
        update = update_purchase_order_eta(
            po_id=body.po_id,
            eta=body.eta,
        )
        return _update_with_optional_replan(
            update,
            scenario_id=body.scenario_id,
            sku=body.sku,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/state/facility")
def state_facility(body: FacilityStateUpdate):
    try:
        update = update_facility_state(
            scenario_id=body.scenario_id,
            facility_id=body.facility_id,
            status=body.status,
            capacity_multiplier=body.capacity_multiplier,
            confirmed=body.confirmed,
            source_type=body.source_type,
            reason=body.reason,
        )
        return _update_with_optional_replan(
            update,
            scenario_id=body.scenario_id,
            sku=body.sku,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/state/substitution")
def state_substitution(body: SubstitutionApprovalUpdate):
    try:
        update = update_substitution_approval(
            material_id=body.material_id,
            substitute_material_id=body.substitute_material_id,
            approved=body.approved,
            engineering_status=body.engineering_status,
        )
        return _update_with_optional_replan(
            update,
            scenario_id=body.scenario_id,
            sku=body.sku,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/agents/run-incident")
def agents_run_incident(body: AgentIncidentRequest):
    try:
        return run_incident_agents(
            event_id=body.event_id,
            scenario_id=body.scenario_id,
            sku=body.sku,
            radius_km=body.radius_km,
            model=body.model,
            persist=body.persist,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/incidents/{incident_id}")
def incident_memory(incident_id: str):
    try:
        return get_incident_memory(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/memory/similar/{event_type}")
def memory_similar(event_type: str, limit: int = Query(default=5, ge=1, le=50)):
    return {
        "event_type": event_type,
        "usage_rule": "HYPOTHESIS_ONLY_RECHECK_CURRENT_STATE",
        "incidents": similar_incidents(event_type=event_type, limit=limit),
    }


@app.get("/demo/tariff")
def tariff_demo():
    return tariff_impact(
        customs_value_per_unit=60,
        additional_rate=0.125,
        units=2500,
        baseline_unit_margin=47,
    )
