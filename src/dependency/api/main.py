from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dependency.db.connection import connect, postgis_version
from dependency.graph.exposure import facilities_within_radius
from dependency.graph.impact import trace_event_impact
from dependency.ingest.events import list_recent_events
from dependency.services.capacity import confirm_supplier_capacity
from dependency.solver.recovery import plan_sku_recovery
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


class CapacityConfirmation(BaseModel):
    facility_id: str
    sku: str
    capacity_units: int = Field(ge=0)
    valid_until: str | None = None
    source_channel: str = "Slack Connect"
    raw_message: str | None = None
    scenario_id: str | None = None
    release_safety_stock: bool = False


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


@app.get("/demo/tariff")
def tariff_demo():
    return tariff_impact(
        customs_value_per_unit=60,
        additional_rate=0.125,
        units=2500,
        baseline_unit_margin=47,
    )
