"""Opt-in, bounded, model-driven specialist runs for HERMES missions.

The deterministic mission controller remains the source of decision truth.
This module never offers a state-changing tool to any LLM. Each run requires
both a server policy switch and an explicit caller opt-in.
"""
from __future__ import annotations

import os
from time import perf_counter

from dependency.agents.runtime import run_agent
from dependency.agents.specs import AgentSpec
from dependency.assistant.mission_controller import mission_preview


READ_ONLY_TOOLS = frozenset({
    "get_event",
    "find_facilities_near_event",
    "search_event_evidence",
    "get_event_investigation_tasks",
    "trace_downstream_impact",
    "trace_upstream_dependencies",
    "explode_bom",
    "get_customer_commitments",
    "check_backup_independence",
    "get_open_purchase_orders",
    "get_supplier_capacity",
    "get_event_portfolio",
    "find_similar_incidents",
    "get_pending_approvals",
})

BASE_GUARDRAILS = (
    "You are one specialist in a supply-chain investigation. Public hazard "
    "proximity is NOT damage. Private data is modeled. Only tools establish "
    "numerical facts and exact graph edges. Do not create inferred source-"
    "to-order assignments or use a common material node as a physical "
    "source-to-destination route. Stop rather than guess missing evidence. "
    "Never contact suppliers, request approvals, write state, or claim to "
    "have executed an action. Keep claims source-based and concise. "
)

SIGNAL = AgentSpec(
    name="Signal Investigator",
    role="Verify public event observations and distinguish exposure from damage.",
    instructions=BASE_GUARDRAILS + (
        "Inspect the selected event, its stored evidence, and near-source "
        "facilities. Stop when the verified source, source event time, "
        "potential exposure and missing operational evidence are clear."
    ),
    tool_names=(
        "get_event", "find_facilities_near_event", "search_event_evidence"
    ),
)
EVIDENCE = AgentSpec(
    name="Evidence Investigator",
    role="Find exact unconfirmed operational facts that block decisions.",
    instructions=BASE_GUARDRAILS + (
        "Retrieve the case's actual stored evidence tasks. Do NOT create "
        "new tasks or prepare outreach. Name task IDs and required facts. "
        "Stop when the next fact and who must verify it are clear."
    ),
    tool_names=("get_event_investigation_tasks", "search_event_evidence"),
)
IMPACT = AgentSpec(
    name="Impact Investigator",
    role="Connect approved source/material/destination paths to modeled demand.",
    instructions=BASE_GUARDRAILS + (
        "Inspect the SKU's destination-qualified upstream allocation records, "
        "BOM and SKU-level customer commitments. Supplier-to-order assignment "
        "is NOT established by a shared material node. Show explicit IDs. "
        "Stop when the exact modeled routes and unverified claims are clear."
    ),
    tool_names=(
        "trace_upstream_dependencies", "explode_bom",
        "get_customer_commitments", "trace_downstream_impact",
    ),
)
CHALLENGER = AgentSpec(
    name="Recovery Challenger",
    role="Try to falsify an attractive recovery route using hard constraints.",
    instructions=BASE_GUARDRAILS + (
        "Use backup independence and the deterministic event portfolio to "
        "challenge proposed recovery. Identify shared upstream dependencies, "
        "missing material, stale capacity, rejected options and approval "
        "boundaries. A scenario without confirmed facts must stay provisional. "
        "Never override deterministic rejection or suggest execution."
    ),
    tool_names=(
        "check_backup_independence",
        "get_event_portfolio",
        "get_supplier_capacity",
        "get_open_purchase_orders",
    ),
)


def choose_specialists(baseline: dict) -> list[AgentSpec]:
    """Evidence and scope decide selection; not arbitrary round-robin chat."""
    if baseline.get("decision_gate", {}).get("status") == "INCOMPLETE_TOOL_ERROR":
        return []
    if not baseline.get("scenario_id"):
        return [SIGNAL, IMPACT, EVIDENCE] if baseline.get("sku") else [SIGNAL, EVIDENCE]
    if baseline.get("sku"):
        return [SIGNAL, IMPACT, CHALLENGER]
    return [SIGNAL, EVIDENCE]


def run_supervised_agents(*, event_id: str, question: str, sku: str | None = None,
                          caller_opt_in: bool = False) -> dict:
    """Allow real model calls ONLY when user and server explicitly opted in.

    No method here mutates an incident or writes session state. Agent outputs
    are hypotheses beside the deterministic decision gate; they are not
    automatic execution permission.
    """
    if not caller_opt_in:
        raise ValueError("Model execution requires explicit caller opt-in.")
    if os.getenv("DEPENDENCY_MISSION_MODEL_ENABLED") != "1":
        raise ValueError("Model execution is disabled by server policy.")
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("No model API key is configured on the server.")
    baseline = mission_preview(event_id=event_id, question=question, sku=sku)
    specs = choose_specialists(baseline)
    if any(not set(spec.tool_names) <= READ_ONLY_TOOLS for spec in specs):
        raise RuntimeError("Unsafe tool found in supervised agent manifest.")

    runs = []
    started = perf_counter()
    context = (
        f"Event ID: {event_id}\n"
        f"Selected SKU: {baseline.get('sku') or 'not selected'}\n"
        f"Question: {question}\n"
        f"Deterministic gate: {baseline['decision_gate']['status']}\n"
        f"Recorded blocking issues: {baseline['decision_gate'].get('issues', [])}\n"
        f"Scenario ID: {baseline.get('scenario_id') or 'NOT_CONFIRMED'}\n"
        "Use only your approved read-only tools. Stop if evidence is missing. "
        "No action may be approved or executed."
    )
    for spec in specs:
        try:
            run = run_agent(
                spec=spec, task=context,
                max_tool_rounds=3,
            )
            traces = run.get("tool_trace") or []
            runs.append({
                "agent": spec.name,
                "status": ("MAX_TOOL_ROUNDS" if run.get("warning") else "COMPLETED"),
                "output": str(run.get("output_text") or "")[:3500],
                "tool_trace": [
                    {"tool": row.get("tool"),
                     "arguments": row.get("arguments"),
                     # Raw result values may contain large private modeled data;
                     # references, source queries and deterministic gate stay
                     # accessible via existing read-only API paths.
                     "result_type": type(row.get("result")).__name__}
                    for row in traces[:20]
                ],
                "tool_rounds": run.get("tool_rounds"),
            })
        except Exception as exc:
            runs.append({
                "agent": spec.name, "status": "ERROR",
                "error_type": type(exc).__name__,
            })
            break  # Fail closed: no silent delegation to another agent.

    return {
        "mode": "OPT_IN_MODEL_SPECIALISTS",
        "model_invoked": bool(runs),
        "read_only": True,
        "selection_strategy": "EVIDENCE_AND_SCENARIO_GATED",
        "termination_strategy": (
            "NO_CONFIRMED_SCENARIO_OR_SPECIALIST_COMPLETION_OR_ERROR; "
            "MAX_3_TOOL_ROUNDS_PER_SPECIALIST"
        ),
        "baseline": baseline,
        "agent_runs": runs,
        "metrics": {
            "agents_selected": len(specs),
            "agents_executed": len(runs),
            "tool_calls": sum(len(run.get("tool_trace") or []) for run in runs),
            "elapsed_ms": round((perf_counter()-started)*1000,2),
            "model_cost_usd": None,
            "cost_status": "NOT_YET_INSTRUMENTED",
        },
        "execution_allowed": False,
        "claim_rule": (
            "Model narratives do not override deterministic feasibility, "
            "evidence requirements, supplier identity, or human approvals."
        ),
    }
