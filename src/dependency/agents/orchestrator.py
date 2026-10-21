from __future__ import annotations

from dependency.agents.runtime import run_agent
from dependency.agents.specs import (
    IMPACT_INVESTIGATOR,
    RECOVERY_PLANNER,
    SIGNAL_INVESTIGATOR,
)
from dependency.db.connection import connect
from dependency.memory.service import ensure_incident, record_agent_run, save_plan_snapshot
from dependency.solver.candidates import generate_recovery_candidates


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
