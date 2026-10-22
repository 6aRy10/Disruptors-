from __future__ import annotations

from pathlib import Path
from datetime import datetime
import os
from dependency.api.write_guard import require_write_authorization

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dependency.db.connection import connect, postgis_version
from dependency.dashboard.snapshot import dashboard_snapshot
from dependency.data.scale_stats import enterprise_data_stats
from dependency.agents.orchestrator import run_event_autopilot, run_incident_agents
from dependency.memory.service import get_incident_memory, similar_incidents
from dependency.incidents.triage import triage_event
from dependency.investigation.tasks import (
    list_investigation_tasks,
    confirm_facility_investigation,
)
from dependency.investigation.outreach import prepare_investigation_outreach
from dependency.graph.exposure import facilities_within_radius
from dependency.graph.event_impact import PHYSICAL_EVENT_TYPES, trace_business_event_impact
from dependency.ingest.events import list_recent_events
from dependency.services.capacity import confirm_supplier_capacity
from dependency.services.facility_capacity import confirm_facility_capacity
from dependency.services.supplier_outreach import (
    confirm_supplier_reply,
    create_capacity_confirmation_request,
    dispatch_confirmation_request,
    get_confirmation_request,
    record_confirmation_reply,
    record_slack_reply,
    reject_supplier_reply,
)
from dependency.notifications.slack import verify_slack_signature
from dependency.services.approvals import (
    decide_approval,
    list_approval_requests,
    request_human_approval,
)
from dependency.services.execution import (
    execute_approved_action,
    list_action_executions,
)
from dependency.services.demo_reset import reset_demo_state
from dependency.services.scenarios import confirm_event_facility_state
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
from dependency.solver.component_feasibility import evaluate_component_feasibility
from dependency.solver.transport_feasibility import evaluate_recovery_transport
from dependency.solver.portfolio import plan_event_recovery
from dependency.solver.optimization import optimize_recovery_allocation
from dependency.graph.shared_dependencies import backup_independence
from dependency.graph.dependency_view import product_dependency_graph
from dependency.graph.network import list_network_facilities, network_stats
from dependency.graph.app_views import map_facilities, facility_profile, incident_inbox, event_context, map_hazard_reports
from dependency.graph.activity_stream import read_activity
from dependency.api.readiness import local_readiness
from dependency.graph.event_journey import event_journey
from dependency.assistant.expeditor import answer_expeditor
from dependency.assistant.mission_controller import mission_preview
from dependency.solver.tariff import tariff_impact
from dependency.supplier_confirmations import parse_supplier_reply

app = FastAPI(
    title="Disruptors Dependency API",
    version="0.2.0",
    description="Event-to-exposure-to-recovery API backed by PostgreSQL/PostGIS.",
)

@app.middleware("http")
async def protect_state_changes(request: Request, call_next):
    """Gate remote writes; Slack has its own signed webhook verifier."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.url.path != "/integrations/slack/events":
            try:
                require_write_authorization(
                    client_host=request.client.host if request.client else "",
                    authorization=request.headers.get("authorization"),
                    configured_token=os.getenv("DEPENDENCY_WRITE_TOKEN"),
                )
            except HTTPException as exc:
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                )
    return await call_next(request)


WEB_ROOT = Path(__file__).resolve().parents[3] / "web"

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


app.mount(
    "/dashboard-assets",
    StaticFiles(directory=str(WEB_ROOT)),
    name="dashboard-assets",
)


class MissionPreviewQuestion(BaseModel):
    event_id: str = Field(min_length=1, max_length=180)
    question: str = Field(min_length=2, max_length=1000)
    sku: str | None = Field(default=None, max_length=120)


class ExpeditorQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    event_id: str | None = Field(default=None, max_length=180)
    sku: str | None = Field(default=None, max_length=120)
    facility_id: str | None = Field(default=None, max_length=180)
    object_id: str | None = Field(default=None, max_length=240)


class ConfirmFacilityWideCapacity(BaseModel):
    week_start: str
    valid_until: str
    capacity_units: int = Field(ge=0)
    committed_units: int = Field(ge=0)
    evidence_source: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)
    confirmed_by: str = Field(min_length=1)


class SupplierReply(BaseModel):
    text: str


class AgentIncidentRequest(BaseModel):
    event_id: str
    scenario_id: str
    sku: str
    radius_km: float = Field(default=150.0, gt=0, le=1000)
    model: str | None = None
    persist: bool = True


class EventAutopilotRequest(BaseModel):
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




class InvestigationFacilityConfirmation(BaseModel):
    status: str
    capacity_multiplier: float = Field(ge=0, le=1)
    confirmed_by: str = Field(min_length=1, max_length=200)
    evidence_source: str = Field(min_length=1, max_length=300)
    evidence_reference: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=2000)


class EventFacilityStateUpdate(BaseModel):
    facility_ref: str
    status: str
    capacity_multiplier: float = Field(default=1.0, ge=0, le=1)
    confirmed: bool = True
    source_type: str = "PRIVATE_OPERATIONAL_CONFIRMATION"
    reason: str


class TariffImpactRequest(BaseModel):
    customs_value_per_unit: float = Field(ge=0)
    additional_rate: float = Field(ge=0)
    units: int = Field(ge=0)
    baseline_unit_margin: float

class ApprovalRequestBody(BaseModel):
    incident_id: str
    scenario_id: str | None = None
    plan_record_id: str | None = None
    sku: str | None = None
    action_type: str
    action_payload: dict = Field(default_factory=dict)
    reason: str
    requested_by: str = "Human Planner"


class ApprovalDecisionBody(BaseModel):
    decision: str
    decided_by: str
    decision_reason: str


class ActionExecuteBody(BaseModel):
    executed_by: str


class SupplierCapacityRequestBody(BaseModel):
    facility_id: str
    sku: str
    incident_id: str | None = None
    scenario_id: str | None = None
    recipient_contact_id: str | None = None
    dispatch: bool = False


class SupplierReplyConfirmBody(BaseModel):
    reply_id: str | None = None
    confirmed_by: str


class SupplierReplyRejectBody(BaseModel):
    reason: str


class SupplierRawReplyBody(BaseModel):
    text: str
    sender_external_id: str | None = None
    source_message_id: str | None = None


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


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return (WEB_ROOT / "index.html").read_text(encoding="utf-8")


@app.get("/data/scale")
def data_scale():
    return enterprise_data_stats()


@app.get("/dashboard/snapshot")
def dashboard_data(
    event_id: str | None = Query(default=None),
    scenario_id: str | None = Query(default=None),
    radius_km: float = Query(default=150.0, gt=0, le=1000),
):
    try:
        return dashboard_snapshot(
            event_id=event_id,
            scenario_id=scenario_id,
            radius_km=radius_km,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post("/app-data/mission-preview")
def mission_preview_read_only(body: MissionPreviewQuestion):
    """Read-only staged evidence, dependency and backup investigation trace.

    No model call, supplier draft, approval or business state mutation.
    """
    try:
        return mission_preview(
            event_id=body.event_id, question=body.question, sku=body.sku
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/app-data/ask")
def expeditor_read_only(body: ExpeditorQuestion):
    """Answer from approved read-only domain functions, never raw model SQL."""
    try:
        return answer_expeditor(question=body.question, event_id=body.event_id,
                                sku=body.sku, facility_id=body.facility_id,
                                object_id=body.object_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/app-data/readiness")
def app_local_readiness():
    """Read-only diagnostics; errors are structured, never credentials."""
    return local_readiness()


@app.get("/app-data/activity")
def app_event_activity(
    limit: int = Query(default=80,ge=1,le=200),
    source: str | None = Query(default=None,max_length=80),
    since: datetime | None = None,
):
    """Read-only recorded source arrivals and local outbox processing."""
    try:
        return read_activity(limit=limit,source=source,since=since)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc


@app.get("/app-data/events/{event_id}/journey")
def app_event_journey(event_id: str):
    """Trace persisted source-to-investigation checkpoints for one event."""
    try:
        return event_journey(event_id=event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/app-data/events/{event_id}")
def app_event_context(event_id: str):
    try:
        return event_context(event_id=event_id)
    except ValueError as exc:
        raise HTTPException(status_code=404,detail=str(exc)) from exc


@app.get("/app-data/incidents")
def app_incident_inbox(limit: int = Query(default=50,ge=1,le=200)):
    return incident_inbox(limit=limit)


@app.get("/app-data/map/hazards")
def app_map_hazard_reports(
    days: int = Query(default=90,ge=1,le=3650),
    limit: int = Query(default=350,ge=1,le=1000),
):
    return map_hazard_reports(days=days,limit=limit)


@app.get("/app-data/map/facilities")
def app_map_facilities(
    west: float = Query(default=-180,ge=-180,le=180),
    south: float = Query(default=-85,ge=-90,le=90),
    east: float = Query(default=180,ge=-180,le=180),
    north: float = Query(default=85,ge=-90,le=90),
    country: str | None = Query(default=None,max_length=120),
    linked_only: bool = False,
    limit: int = Query(default=1000,ge=1,le=2500),
):
    try:
        return map_facilities(
            west=west,south=south,east=east,north=north,
            country=country,business_linked_only=linked_only,limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc


@app.get("/app-data/facilities/{network_facility_id}")
def app_facility_profile(
    network_facility_id: str,
    max_products: int = Query(default=25,ge=1,le=100),
):
    try:
        return facility_profile(
            network_facility_id=network_facility_id,
            max_products=max_products,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404,detail=str(exc)) from exc


@app.get("/network/stats")
def public_network_stats():
    return network_stats()


@app.get("/network/facilities")
def public_network_facilities(
    country: str | None = Query(default=None),
    list_type: str | None = Query(default=None),
    business_linked_only: bool = False,
    limit: int = Query(default=1000, ge=1, le=5000),
):
    return {
        "facilities": list_network_facilities(
            country=country,
            list_type=list_type,
            business_linked_only=business_linked_only,
            limit=limit,
        )
    }


@app.get("/products/{sku}/graph")
def product_graph(sku: str):
    try:
        return product_dependency_graph(sku)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/investigations/tasks/{task_id}/prepare-outreach")
def draft_investigation_outreach(task_id: str):
    try:
        return prepare_investigation_outreach(task_id=task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc


@app.post("/investigations/tasks/{task_id}/confirm-facility")
def confirm_investigation_facility(task_id: str, body: InvestigationFacilityConfirmation):
    try:
        return confirm_facility_investigation(
            task_id=task_id,status=body.status,
            capacity_multiplier=body.capacity_multiplier,
            confirmed_by=body.confirmed_by,
            evidence_source=body.evidence_source,
            evidence_reference=body.evidence_reference,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/investigations/tasks")
def pending_investigation_tasks(
    incident_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    return {"tasks": list_investigation_tasks(incident_id=incident_id, limit=limit)}


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
            SELECT event_type,ST_Y(geom::geometry),ST_X(geom::geometry)
            FROM external_events
            WHERE event_id = %s
            """,
            (event_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Event not found.")

    if row[0] in PHYSICAL_EVENT_TYPES and row[1] is not None and row[2] is not None:
        facilities = facilities_within_radius(
            latitude=float(row[1]),
            longitude=float(row[2]),
            radius_km=radius_km,
        )
        return {
            "event_id": event_id,
            "event_type": row[0],
            "radius_km": radius_km,
            "exposure_basis": "GEOSPATIAL_PROXIMITY",
            "exposure_status": "POTENTIAL_ONLY",
            "facilities": facilities,
        }

    impact = trace_business_event_impact(
        event_id=event_id,
        radius_km=radius_km,
    )
    return {
        "event_id": event_id,
        "event_type": row[0],
        "radius_km": radius_km,
        "exposure_basis": impact.get("exposure_basis"),
        "exposure_status": impact.get("exposure_status"),
        "facilities": impact.get("facilities", []),
        "dependency_paths": impact.get("dependency_paths", []),
        "products": impact.get("products", []),
        "totals": impact.get("totals", {}),
    }


@app.get("/events/{event_id}/impact")
def event_impact(
    event_id: str,
    radius_km: float = Query(default=100.0, gt=0, le=1000),
):
    return trace_business_event_impact(event_id=event_id, radius_km=radius_km)


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


@app.get("/scenarios/{scenario_id}/components/{sku}")
def scenario_component_feasibility(
    scenario_id: str,
    sku: str,
    destination_facility_id: str,
    production_units: float = Query(gt=0),
    need_by: str = Query(),
):
    try:
        return evaluate_component_feasibility(
            scenario_id=scenario_id,
            sku=sku,
            destination_facility_id=destination_facility_id,
            production_units=production_units,
            need_by=need_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/scenarios/{scenario_id}/optimize/{sku}")
def scenario_optimize(
    scenario_id: str,
    sku: str,
    release_safety_stock: bool = False,
    include_provisional: bool = True,
):
    try:
        return optimize_recovery_allocation(
            scenario_id=scenario_id,
            sku=sku,
            release_safety_stock=release_safety_stock,
            include_provisional=include_provisional,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/scenarios/{scenario_id}/transport/{sku}")
def scenario_transport_feasibility(
    scenario_id: str,
    sku: str,
    origin_facility_id: str,
):
    try:
        return evaluate_recovery_transport(
            scenario_id=scenario_id,
            sku=sku,
            origin_facility_id=origin_facility_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@app.post("/supplier-confirmations/capacity")
def supplier_confirmation_create(body: SupplierCapacityRequestBody):
    try:
        request_record = create_capacity_confirmation_request(
            facility_id=body.facility_id,
            sku=body.sku,
            incident_id=body.incident_id,
            scenario_id=body.scenario_id,
            recipient_contact_id=body.recipient_contact_id,
        )
        if body.dispatch:
            request_record["dispatch"] = dispatch_confirmation_request(
                request_id=request_record["request_id"],
            )
        return request_record
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/supplier-confirmations/{request_id}")
def supplier_confirmation_get(request_id: str):
    try:
        return get_confirmation_request(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/supplier-confirmations/{request_id}/dispatch")
def supplier_confirmation_dispatch(request_id: str):
    try:
        return dispatch_confirmation_request(request_id=request_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/supplier-confirmations/{request_id}/reply")
def supplier_confirmation_record_reply(
    request_id: str,
    body: SupplierRawReplyBody,
):
    try:
        return record_confirmation_reply(
            request_id=request_id,
            raw_message=body.text,
            sender_external_id=body.sender_external_id,
            source_message_id=body.source_message_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/supplier-confirmations/{request_id}/confirm")
def supplier_confirmation_confirm(
    request_id: str,
    body: SupplierReplyConfirmBody,
):
    try:
        return confirm_supplier_reply(
            request_id=request_id,
            reply_id=body.reply_id,
            confirmed_by=body.confirmed_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/supplier-confirmations/{request_id}/reject")
def supplier_confirmation_reject(
    request_id: str,
    body: SupplierReplyRejectBody,
):
    try:
        return reject_supplier_reply(
            request_id=request_id,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/integrations/slack/events")
async def slack_events(request: Request):
    raw_body = await request.body()
    timestamp = request.headers.get("x-slack-request-timestamp", "")
    signature = request.headers.get("x-slack-signature", "")

    try:
        valid = verify_slack_signature(
            raw_body=raw_body,
            timestamp=timestamp,
            signature=signature,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not valid:
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Slack JSON.") from exc

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    event = payload.get("event") or {}
    if (
        event.get("type") != "message"
        or event.get("bot_id")
        or event.get("subtype")
    ):
        return {"ok": True, "ignored": True}

    result = record_slack_reply(
        channel_id=event.get("channel", ""),
        thread_ts=event.get("thread_ts"),
        raw_message=event.get("text", ""),
        sender_external_id=event.get("user"),
        source_message_id=event.get("ts"),
    )
    return {"ok": True, "result": result}


@app.post("/facilities/{facility_id}/capacity-confirmations")
def confirm_shared_factory_capacity(facility_id: str, body: ConfirmFacilityWideCapacity):
    try:
        return confirm_facility_capacity(
            facility_id=facility_id,
            week_start=body.week_start,
            valid_until=body.valid_until,
            capacity_units=body.capacity_units,
            committed_units=body.committed_units,
            evidence_source=body.evidence_source,
            evidence_reference=body.evidence_reference,
            confirmed_by=body.confirmed_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400,detail=str(exc)) from exc


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


@app.post("/events/{event_id}/operational-state")
def event_operational_state(event_id: str, body: EventFacilityStateUpdate):
    try:
        result = confirm_event_facility_state(
            event_id=event_id,
            facility_ref=body.facility_ref,
            status=body.status,
            capacity_multiplier=body.capacity_multiplier,
            confirmed=body.confirmed,
            source_type=body.source_type,
            reason=body.reason,
        )
        triage = triage_event(event_id=event_id, radius_km=150.0)
        scenario_id = result["scenario"]["scenario_id"]
        portfolio = plan_event_recovery(
            event_id=event_id,
            scenario_id=scenario_id,
            radius_km=150.0,
        )
        return {
            **result,
            "triage": triage,
            "portfolio": portfolio,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/events/{event_id}/portfolio/{scenario_id}")
def event_portfolio(
    event_id: str,
    scenario_id: str,
    radius_km: float = Query(default=150.0, gt=0, le=1000),
):
    try:
        return plan_event_recovery(
            event_id=event_id,
            scenario_id=scenario_id,
            radius_km=radius_km,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/events/{event_id}/triage")
def event_triage(
    event_id: str,
    radius_km: float = Query(default=150.0, gt=0, le=1000),
):
    try:
        return triage_event(event_id=event_id, radius_km=radius_km)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/agents/run-event/{event_id}")
def agents_run_event(event_id: str, body: EventAutopilotRequest):
    try:
        return run_event_autopilot(
            event_id=event_id,
            radius_km=body.radius_km,
            model=body.model,
            persist=body.persist,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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


@app.post("/approvals")
def create_approval(body: ApprovalRequestBody):
    try:
        return request_human_approval(
            incident_id=body.incident_id,
            scenario_id=body.scenario_id,
            plan_record_id=body.plan_record_id,
            sku=body.sku,
            action_type=body.action_type,
            action_payload=body.action_payload,
            reason=body.reason,
            requested_by=body.requested_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/approvals")
def approvals(
    status: str | None = Query(default="PENDING"),
    incident_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return {
        "approvals": list_approval_requests(
            status=status,
            incident_id=incident_id,
            limit=limit,
        )
    }


@app.post("/approvals/{request_id}/decision")
def approval_decision(request_id: str, body: ApprovalDecisionBody):
    try:
        return decide_approval(
            request_id=request_id,
            decision=body.decision,
            decided_by=body.decided_by,
            decision_reason=body.decision_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/approvals/{request_id}/execute")
def approval_execute(request_id: str, body: ActionExecuteBody):
    try:
        return execute_approved_action(
            request_id=request_id,
            executed_by=body.executed_by,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/executions")
def executions(
    incident_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return {
        "executions": list_action_executions(
            incident_id=incident_id,
            limit=limit,
        )
    }


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


@app.post("/analysis/tariff")
def tariff_analysis(body: TariffImpactRequest):
    return tariff_impact(
        customs_value_per_unit=body.customs_value_per_unit,
        additional_rate=body.additional_rate,
        units=body.units,
        baseline_unit_margin=body.baseline_unit_margin,
    )
