from __future__ import annotations

from dependency.agents.runtime import run_agent
from dependency.agents.specs import (
    IMPACT_INVESTIGATOR,
    RECOVERY_PLANNER,
    SIGNAL_INVESTIGATOR,
)


def run_incident_agents(
    *,
    event_id: str,
    scenario_id: str,
    sku: str,
    radius_km: float = 150.0,
    model: str | None = None,
) -> dict:
    """Run the three-agent incident chain.

    Each agent chooses from a constrained tool set. Deterministic tools remain
    the source of truth for graph traversal, arithmetic, state and feasibility.
    """
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

    return {
        "event_id": event_id,
        "scenario_id": scenario_id,
        "sku": sku,
        "radius_km": radius_km,
        "agents": {
            "signal": signal,
            "impact": impact,
            "recovery": recovery,
        },
    }
