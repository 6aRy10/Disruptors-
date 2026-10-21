from __future__ import annotations
import csv
from pathlib import Path
from fastapi import FastAPI
from pydantic import BaseModel, Field

from dependency.state import DemoState
from dependency.supplier_confirmations import parse_supplier_reply
from dependency.solver.allocation import Order, allocate_orders, summarize
from dependency.solver.feasibility import check_plan
from dependency.solver.tariff import tariff_impact

app = FastAPI(title="Dependency API", version="1.0.0-pre-github")
state = DemoState()
ORDERS = [
    Order("ORD-JI-EU", 4000, 130, 55, 1),
    Order("ORD-JI-NA", 3000, 130, 50, 2),
    Order("ORD-JI-GC", 2500, 130, 52, 3),
]
FINISHED = 2100
CONFIG = Path(__file__).resolve().parents[3] / "config"


class Reply(BaseModel):
    text: str


class Confirm(BaseModel):
    capacity_units: int = Field(ge=0)
    effective_until: str | None = None


def plan():
    available = FINISHED + state.hwa_available
    result = summarize(allocate_orders(ORDERS, available))
    result.update(
        {
            "state_version": state.version,
            "available_units": available,
            "feasibility": check_plan(
                required_units=9500,
                finished_units=FINISHED,
                assembly_units=state.hwa_available,
            ),
        }
    )
    return result


def ji_risk_score():
    return 90 if state.supplier_confirmed and state.hwa_capacity <= 5500 else 82


def load_events():
    with (CONFIG / "risk_events.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    integerish = {"rank", "radius_km"}
    numeric = {
        "rank",
        "radius_km",
        "business_risk_score",
        "disruption_severity",
        "dependency_criticality",
        "time_urgency",
        "commercial_exposure",
        "recovery_difficulty",
        "evidence_confidence",
    }
    for row in rows:
        for key in numeric:
            if key in row and row[key] not in {"", None}:
                row[key] = int(float(row[key])) if key in integerish else float(row[key])
    return sorted(rows, key=lambda r: r["rank"])


@app.get("/health")
def health():
    return {"ok": True, "state_version": state.version}


@app.get("/demo/events")
def events():
    return {"events": load_events()}


@app.get("/demo/plan")
def get_plan():
    return plan()


@app.get("/demo/risk")
def get_risk():
    score = ji_risk_score()
    return {
        "object_type": "product",
        "object_id": "JI2993",
        "risk_score": score,
        "band": "CRITICAL" if score >= 70 else "HIGH",
    }


@app.get("/demo/tariff")
def get_tariff_demo():
    return tariff_impact(
        customs_value_per_unit=60,
        additional_rate=0.20,
        units=2500,
        baseline_unit_margin=47,
    )


@app.post("/demo/supplier/parse-reply")
def parse_reply(body: Reply):
    return parse_supplier_reply(body.text)


@app.post("/demo/supplier/confirm")
def confirm(body: Confirm):
    version = state.confirm_capacity(body.capacity_units)
    return {"confirmed": True, "state_version": version, "risk": get_risk(), "plan": plan()}


@app.post("/demo/reset")
def reset():
    global state
    state = DemoState()
    return {"ok": True, "state_version": state.version}
