from __future__ import annotations

from dependency.agents.runtime import run_agent
from dependency.agents.specs import (
    IMPACT_INVESTIGATOR,
    RECOVERY_PLANNER,
    SIGNAL_INVESTIGATOR,
)
from dependency.db.connection import connect
from dependency.memory.service import ensure_incident, record_agent_run, save_plan_snapshot
from dependency.incidents.triage import triage_event
from dependency.solver.candidates import generate_recovery_candidates
from dependency.solver.portfolio import plan_event_recovery


def _state_version() -> int:
    with connect() as conn:
        return int(
            conn.execute(
                "SELECT version FROM operational_state_version WHERE singleton = true"
            ).fetchone()[0]
        )


def run_incident_agents(
    *,
    event_id: str,
    scenario_id: str,
    sku: str,
    radius_km: float = 150.0,
    model: str | None = None,
    persist: bool = True,
) -> dict:
    """Run the three-agent incident chain and save an auditable trace."""
    incident = None
    if persist:
        incident = ensure_incident(
            event_id=event_id,
            scenario_id=scenario_id,
            summary=f"Agent investigation for {event_id} / {sku}",
            initial_assessment=(
                "Investigation opened. Public proximity is potential exposure only; "
                "private operational evidence is required for shutdown claims."
            ),
            provenance_class="SIMULATED_PRIVATE",
        )

    signal_task = f"""
Investigate external event {event_id}.
Use a radius of {radius_km} km for geospatial triage.
Identify public adidas network facilities that require investigation.
Do not claim shutdown from proximity. State the evidence still missing.
"""
    signal = run_agent(
        spec=SIGNAL_INVESTIGATOR,
        task=signal_task,
        model=model,
    )
    if incident:
        record_agent_run(
            incident_id=incident["incident_id"],
            agent_name=signal["agent"],
            model=signal["model"],
            output_text=signal["output_text"],
            tool_trace=signal["tool_trace"],
            state_version=_state_version(),
        )

    impact_task = f"""
Event: {event_id}
Radius: {radius_km} km
Primary deep-dive SKU: {sku}

Signal Investigator output:
{signal['output_text']}

Trace only explicit operational dependency edges into materials, products and
customer commitments. Check hidden shared dependencies where relevant.
Keep potential exposure separate from confirmed private operational state.
"""
    impact = run_agent(
        spec=IMPACT_INVESTIGATOR,
        task=impact_task,
        model=model,
    )
    if incident:
        record_agent_run(
            incident_id=incident["incident_id"],
            agent_name=impact["agent"],
            model=impact["model"],
            output_text=impact["output_text"],
            tool_trace=impact["tool_trace"],
            state_version=_state_version(),
        )

    recovery_task = f"""
Scenario: {scenario_id}
SKU: {sku}

Signal Investigator output:
{signal['output_text']}

Impact Investigator output:
{impact['output_text']}

Generate recovery alternatives. Use deterministic recovery/candidate tools.
Show rejected plans and exact rejection reasons. Do not declare stale supplier
capacity confirmed. Do not release safety stock without planner approval.
State the current shortage, protected revenue/margin, and required next action.
"""
    recovery = run_agent(
        spec=RECOVERY_PLANNER,
        task=recovery_task,
        model=model,
    )

    saved_plans = []
    if incident:
        version = _state_version()
        record_agent_run(
            incident_id=incident["incident_id"],
            agent_name=recovery["agent"],
            model=recovery["model"],
            output_text=recovery["output_text"],
            tool_trace=recovery["tool_trace"],
            state_version=version,
        )
        for plan in generate_recovery_candidates(
            scenario_id=scenario_id,
            sku=sku,
        ):
            saved_plans.append(
                save_plan_snapshot(
                    incident_id=incident["incident_id"],
                    state_version=version,
                    sku=sku,
                    plan=plan,
                )
            )

    return {
        "event_id": event_id,
        "scenario_id": scenario_id,
        "sku": sku,
        "radius_km": radius_km,
        "incident": incident,
        "saved_plan_records": saved_plans,
        "agents": {
            "signal": signal,
            "impact": impact,
            "recovery": recovery,
        },
    }




def run_event_agents(
    *,
    event_id: str,
    scenario_id: str,
    radius_km: float = 150.0,
    model: str | None = None,
    persist: bool = True,
) -> dict:
    """Run one signal/impact/recovery chain for the whole event portfolio."""
    portfolio = plan_event_recovery(
        event_id=event_id,
        scenario_id=scenario_id,
        radius_km=radius_km,
    )

    incident = None
    if persist:
        incident = ensure_incident(
            event_id=event_id,
            scenario_id=scenario_id,
            summary=(
                f"Portfolio investigation for {event_id}: "
                f"{portfolio['summary']['operationally_affected_sku_count']} "
                "operationally affected SKUs."
            ),
            initial_assessment=(
                "Public proximity is potential exposure only. The portfolio is "
                "computed from explicit business graph edges and confirmed or "
                "provisional private operational state."
            ),
            provenance_class="SIMULATED_PRIVATE",
        )

    signal = run_agent(
        spec=SIGNAL_INVESTIGATOR,
        task=f"""
Investigate external event {event_id}.
Use a radius of {radius_km} km.
Find public-network facilities that require investigation.
Do not infer shutdown from proximity. State exactly what is verified and unknown.
""",
        model=model,
    )
    if incident:
        record_agent_run(
            incident_id=incident["incident_id"],
            agent_name=signal["agent"],
            model=signal["model"],
            output_text=signal["output_text"],
            tool_trace=signal["tool_trace"],
            state_version=_state_version(),
        )

    impact = run_agent(
        spec=IMPACT_INVESTIGATOR,
        task=f"""
Event: {event_id}
Radius: {radius_km} km

Signal Investigator output:
{signal['output_text']}

Trace the event through explicit operational dependency edges into every affected
SKU and customer commitment. Do not choose one SKU in advance. Separate public
exposure from confirmed private operational state.
""",
        model=model,
    )
    if incident:
        record_agent_run(
            incident_id=incident["incident_id"],
            agent_name=impact["agent"],
            model=impact["model"],
            output_text=impact["output_text"],
            tool_trace=impact["tool_trace"],
            state_version=_state_version(),
        )

    recovery = run_agent(
        spec=RECOVERY_PLANNER,
        task=f"""
Event: {event_id}
Scenario: {scenario_id}
Radius: {radius_km} km

Signal Investigator output:
{signal['output_text']}

Impact Investigator output:
{impact['output_text']}

Deterministic portfolio summary:
{portfolio['summary']}

Operationally affected SKUs:
{portfolio['operationally_affected_skus']}

Use get_event_portfolio first. Coordinate recovery across all operationally
affected SKUs. Show the ranked action queue, rejected actions, exact rejection
reasons, missing material-path evidence, stale supplier-capacity evidence,
required human approvals, total shortage, and commercial value at risk.
Never declare a plan feasible if a deterministic tool marks it rejected.
""",
        model=model,
    )

    saved_plans = []
    if incident:
        version = _state_version()
        record_agent_run(
            incident_id=incident["incident_id"],
            agent_name=recovery["agent"],
            model=recovery["model"],
            output_text=recovery["output_text"],
            tool_trace=recovery["tool_trace"],
            state_version=version,
        )
        for product in portfolio["products"]:
            for plan in product["candidates"]:
                saved_plans.append(
                    save_plan_snapshot(
                        incident_id=incident["incident_id"],
                        state_version=version,
                        sku=product["sku"],
                        plan=plan,
                    )
                )

    return {
        "event_id": event_id,
        "scenario_id": scenario_id,
        "radius_km": radius_km,
        "incident": incident,
        "portfolio": portfolio,
        "saved_plan_records": saved_plans,
        "agents": {
            "signal": signal,
            "impact": impact,
            "recovery": recovery,
        },
    }


def run_event_autopilot(
    *,
    event_id: str,
    radius_km: float = 150.0,
    model: str | None = None,
    persist: bool = True,
) -> dict:
    """Start from an event ID and coordinate the complete affected portfolio."""
    triage = triage_event(event_id=event_id, radius_km=radius_km)

    if triage["status"] == "NO_NETWORK_EXPOSURE":
        return {
            "event_id": event_id,
            "status": "NO_NETWORK_EXPOSURE",
            "triage": triage,
            "agent_run": None,
        }

    if not triage["impacted_products"]:
        return {
            "event_id": event_id,
            "status": "PUBLIC_EXPOSURE_REQUIRES_BUSINESS_LINK",
            "triage": triage,
            "agent_run": None,
        }

    scenario_id = triage.get("scenario_id")
    if not scenario_id:
        return {
            "event_id": event_id,
            "status": "AWAITING_OPERATIONAL_CONFIRMATION",
            "impacted_skus": [p["sku"] for p in triage["impacted_products"]],
            "triage": triage,
            "agent_run": None,
        }

    result = run_event_agents(
        event_id=event_id,
        scenario_id=scenario_id,
        radius_km=radius_km,
        model=model,
        persist=persist,
    )
    return {
        "event_id": event_id,
        "status": "PORTFOLIO_AGENT_CHAIN_COMPLETED",
        "operationally_affected_skus": result["portfolio"][
            "operationally_affected_skus"
        ],
        "triage": triage,
        "agent_run": result,
    }
