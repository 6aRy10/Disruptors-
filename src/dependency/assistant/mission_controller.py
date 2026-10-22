"""HERMES mission control: bounded, read-only evidence and recovery challenges.

This is the deterministic *control plane* for future supervised AI agents, NOT
a multi-agent language-model run. It records actual tool calls and decisions.
No supplier contact, approval, state mutation, model credits or arbitrary SQL.
"""
from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

from dependency.graph.app_views import event_context
from dependency.graph.event_journey import event_journey
from dependency.graph.event_impact import trace_business_event_impact
from dependency.graph.dependency_view import product_dependency_graph
from dependency.graph.shared_dependencies import backup_independence
from dependency.solver.portfolio import plan_event_recovery


RECOVERY_WORDS = frozenset({
    "recover", "recovery", "backup", "alternative", "alternatives",
    "shortage", "plan", "reallocate", "protect", "feasible",
    "feasibility", "capacity", "material", "materially",
})


def _preview(value: Any) -> dict:
    """Keep trace bounded; client gets source references, not full private rows."""
    if isinstance(value, dict):
        counts = {}
        for key in (
            "nodes", "edges", "allocation_routes", "evidence_tasks",
            "steps", "products", "facilities", "rejected_actions",
            "action_queue",
        ):
            if isinstance(value.get(key), list):
                counts[key] = len(value[key])
        return {"keys": sorted(value.keys())[:30], "collection_sizes": counts}
    return {"type": type(value).__name__}


def mission_preview(*, event_id: str, question: str, sku: str | None = None,
                    max_checks: int = 3) -> dict:
    """Use stored source, graph, evidence, and optional scenario to audit a plan.

    This method never invokes the model agent runtime. Explicit stages/paths
    make a benchmarkable, transparent baseline for future AI supervision.
    """
    event_id = (event_id or "").strip()
    question = (question or "").strip()
    sku = (sku or "").strip() or None
    if not 1 <= len(event_id) <= 180:
        raise ValueError("Select one valid event ID.")
    if not 2 <= len(question) <= 1000:
        raise ValueError("Question must be 2 to 1000 characters.")
    if sku is not None and len(sku) > 120:
        raise ValueError("SKU must be at most 120 characters.")
    if not 1 <= max_checks <= 5:
        raise ValueError("max_checks must be 1 to 5.")

    started = perf_counter()
    steps: list[dict] = []
    errors: list[dict] = []

    def use(role: str, tool: str, func: Callable[..., dict],
            source: str, **arguments: Any) -> dict | None:
        tick = perf_counter()
        try:
            value = func(**arguments)
            status = "OK"
        except ValueError:
            # A nonexistent top-level event or SKU is an invalid request.
            # Never silently claim there was no risk or a feasible plan.
            raise
        except Exception as exc:
            value = None
            status = "ERROR"
            errors.append({"tool": tool, "error_type": type(exc).__name__})
        steps.append({
            "sequence": len(steps) + 1,
            "specialist": role,
            "tool": tool,
            "status": status,
            "arguments": arguments,
            "source": source,
            "elapsed_ms": round((perf_counter() - tick) * 1000, 2),
            "result_shape": _preview(value),
        })
        return value

    event = use("Signal Investigator", "event_context", event_context,
                "/app-data/events/" + event_id, event_id=event_id)
    if event is None:
        return _degraded(event_id, sku, steps, errors, started)
    journey = use("Evidence Investigator", "event_journey", event_journey,
                  "/app-data/events/" + event_id + "/journey", event_id=event_id)
    if journey is None:
        return _degraded(event_id, sku, steps, errors, started)

    incident = event.get("incident") or {}
    source_event = event.get("event") or {}
    evidence_tasks = (event.get("evidence_tasks") or [])[:20]
    scenario_id = incident.get("scenario_id")
    selected_sku = sku
    products: list[dict] = []

    if selected_sku is None:
        impact = use("Impact Investigator", "trace_business_event_impact",
                     trace_business_event_impact,
                     "/events/" + event_id + "/impact?radius_km=150",
                     event_id=event_id, radius_km=150.0)
        if impact:
            products = (impact.get("products") or [])[:30]
            if len(products) == 1:
                selected_sku = products[0].get("sku")

    graph = None
    checked: list[dict] = []
    route_warning = "NO_SKU_SELECTED"
    if selected_sku:
        graph = use("Impact Investigator", "product_dependency_graph",
                    product_dependency_graph,
                    "/products/" + selected_sku + "/graph", sku=selected_sku)
        if graph is not None:
            routes = graph.get("allocation_routes") or []
            route_warning = (
                "EXPLICIT_MODELED_ALLOCATION_ROUTES"
                if routes else "NO_DESTINATION_QUALIFIED_ROUTES"
            )

            # The challenger cannot invent a factory alternative from the
            # shared material overview. Candidates must be explicit approved
            # assembly nodes returned for THIS SKU.
            facilities = [
                n for n in graph.get("nodes", [])
                if n.get("node_type") == "ASSEMBLY_FACILITY"
                and n.get("approved") is True
                and n.get("facility_id")
            ]
            primaries = sorted(
                (n for n in facilities if n.get("role") == "primary_assembly"),
                key=lambda n: n["facility_id"],
            )
            backups = sorted(
                (n for n in facilities if n.get("role") != "primary_assembly"),
                key=lambda n: n["facility_id"],
            )

            if primaries and backups:
                primary = primaries[0]["facility_id"]
                for backup in backups[:max_checks]:
                    other = backup["facility_id"]
                    if other == primary:
                        continue
                    check = use("Recovery Challenger", "backup_independence",
                                backup_independence,
                                "/products/" + selected_sku + "/graph",
                                sku=selected_sku,
                                primary_facility_id=primary,
                                backup_facility_id=other)
                    if check is not None:
                        checked.append({
                            "sku": selected_sku,
                            "primary_facility_id": primary,
                            "backup_facility_id": other,
                            "decision": check.get("decision", "UNKNOWN"),
                            "shared_dependency_count": check.get(
                                "shared_dependency_count", 0
                            ),
                            "shared_dependencies": (
                                check.get("shared_dependencies") or []
                            )[:12],
                            "rule": (
                                "A correlated source is not an independent "
                                "recovery route. Both modeled approvals and "
                                "current operational evidence are still needed."
                            ),
                        })

    # Only evaluate recovery when a scenario exists and the question requests
    # it; otherwise prevent an apparent "feasible" answer based on proximity.
    words = set(question.lower().replace("?", " ").split())
    asks_recovery = bool(words & RECOVERY_WORDS)
    recovery = None
    if asks_recovery and scenario_id:
        portfolio = use("Recovery Planner", "plan_event_recovery",
                        plan_event_recovery,
                        "/events/" + event_id + "/portfolio/" + scenario_id,
                        event_id=event_id, scenario_id=scenario_id)
        if portfolio is not None:
            joint = portfolio.get("joint_allocation") or {}
            material = joint.get("material_constrained_allocation") or {}
            recovery = {
                "portfolio_status": portfolio.get("portfolio_status"),
                "summary": portfolio.get("summary"),
                "rejected": (portfolio.get("rejected_actions") or [])[:12],
                "action_queue": (portfolio.get("action_queue") or [])[:12],
                "material_status": material.get("status"),
                "material_feasible_units": material.get(
                    "material_feasible_units"
                ),
                "material_reduced_units": material.get(
                    "material_reduced_units"
                ),
                "allocation_verified": portfolio.get(
                    "portfolio_allocation_verified"
                ),
                "scenario_id": scenario_id,
                "ready_to_execute": False,
            }

    # Final gate is deterministic. Its status is NOT an LLM conclusion.
    rejected = [r for r in checked if r["decision"] == "REJECT_CORRELATED_BACKUP"]
    issues = []
    if rejected:
        issues.append("CORRELATED_BACKUP")
    if graph is not None and route_warning == "NO_DESTINATION_QUALIFIED_ROUTES":
        issues.append("MISSING_QUALIFIED_ROUTES")
    if evidence_tasks:
        issues.append("OPEN_EVIDENCE")
    if not scenario_id:
        issues.append("NO_CONFIRMED_OPERATIONAL_SCENARIO")
    if errors:
        issues.append("TOOL_FAILURE")

    if errors:
        status = "INCOMPLETE_TOOL_ERROR"
    elif not scenario_id:
        status = "EVIDENCE_REQUIRED"
    elif rejected:
        status = "BACKUP_CHALLENGED"
    elif recovery:
        status = "PLAN_REVIEW_REQUIRED"
    else:
        status = "READY_TO_INVESTIGATE"

    next_action = journey.get("next_action") or {
        "code": "REVIEW_EVIDENCE", "title": "Review evidence"
    }
    findings = []
    if checked:
        findings.append(
            f"{len(checked)} modeled backup(s) checked; "
            f"{len(rejected)} share disqualifying upstream dependencies "
            "under the independence rule."
        )
    if evidence_tasks:
        findings.append(
            f"{len(evidence_tasks)} open evidence task(s). "
            "Public proximity does not confirm operational harm."
        )
    if not scenario_id:
        findings.append(
            "No linked operational scenario. Do not execute a recovery plan."
        )
    if recovery:
        findings.append(
            "Deterministic portfolio evaluated; confirmation and approval "
            "still need independent checks before execution."
        )
    if not findings:
        findings.append(
            "The selected records do not establish disruption or a viable "
            "recovery route without more evidence."
        )

    return {
        "mode": "DETERMINISTIC_SUPERVISOR_BASELINE",
        "read_only": True,
        "model_invoked": False,
        "event_id": event_id,
        "sku": selected_sku,
        "event": {
            "title": source_event.get("title"),
            "source": source_event.get("source"),
            "occurred_at": source_event.get("occurred_at"),
            "mode": source_event.get("mode"),
            "provenance_class": source_event.get("provenance_class"),
        },
        "incident_id": incident.get("incident_id"),
        "scenario_id": scenario_id,
        "suggested_skus": [p.get("sku") for p in products if p.get("sku")],
        "route_basis": route_warning,
        "backup_challenges": checked,
        "open_evidence_tasks": evidence_tasks,
        "recovery": recovery,
        "decision_gate": {
            "status": status,
            "issues": issues,
            "next_action": next_action,
            "findings": findings,
            "execution_allowed": False,
            "source_to_customer_order_assignment_confirmed": False,
        },
        "tool_trace": steps,
        "metrics": {
            "tool_calls": len(steps),
            "tool_errors": len(errors),
            "total_elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "model_cost_usd": 0.0,
        },
        "tool_errors": errors,
        "guardrails": (
            "No supplier-to-customer-order assignment is inferred from shared "
            "material nodes. Recovery candidates are NOT approved actions. "
            "No model, supplier request, approval or state update was executed."
        ),
    }


def _degraded(event_id: str, sku: str | None, steps: list[dict],
              errors: list[dict], started: float) -> dict:
    return {
        "mode": "DETERMINISTIC_SUPERVISOR_BASELINE", "read_only": True,
        "model_invoked": False,
        "event_id": event_id, "sku": sku,
        "decision_gate": {
            "status": "INCOMPLETE_TOOL_ERROR",
            "issues": ["TOOL_FAILURE"],
            "execution_allowed": False,
            "next_action": {
                "code": "CHECK_PROCESSING",
                "title": "Inspect backend data/query failure",
            },
        },
        "tool_trace": steps,
        "tool_errors": errors,
        "metrics": {
            "tool_calls": len(steps), "tool_errors": len(errors),
            "total_elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "model_cost_usd": 0.0,
        },
    }
