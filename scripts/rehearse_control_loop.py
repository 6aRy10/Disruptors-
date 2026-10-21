from __future__ import annotations

import argparse
import json

from dependency.automation.orchestrator import process_pending_events
from dependency.incidents.triage import triage_event
from dependency.memory.service import get_incident_memory, similar_incidents
from dependency.services.approvals import decide_approval, request_human_approval
from dependency.services.demo_reset import reset_demo_state
from dependency.services.execution import execute_approved_action
from dependency.services.supplier_outreach import (
    confirm_supplier_reply,
    create_capacity_confirmation_request,
    record_confirmation_reply,
)
from dependency.solver.portfolio import plan_event_recovery


def heading(number: int, text: str) -> None:
    print(f"\n{'=' * 78}")
    print(f"STAGE {number}: {text}")
    print("=" * 78)


def product_row(portfolio: dict, sku: str) -> dict:
    for row in portfolio.get("products", []):
        if row["sku"] == sku:
            return row
    raise ValueError(f"SKU {sku} is not reached by this event portfolio.")


def show_product(row: dict) -> None:
    conservative = row["conservative_plan"]
    optimized = row.get("optimized_allocation") or {}
    print(
        json.dumps(
            {
                "sku": row["sku"],
                "risk_score": row["risk"]["risk_score"],
                "demand_units": conservative["demand_units"],
                "conservative_shortage_units": conservative["shortage_units"],
                "selected_backup": conservative.get("selected_backup"),
                "requires_supplier_confirmation": conservative[
                    "requires_supplier_confirmation"
                ],
                "requires_material_confirmation": conservative.get(
                    "requires_material_confirmation"
                ),
                "optimized_status": optimized.get("status"),
                "optimized_protected_units": optimized.get("protected_units"),
                "optimized_late_units": optimized.get("late_units"),
                "optimized_protected_margin_eur": optimized.get(
                    "protected_margin_eur"
                ),
                "optimized_net_protected_margin_eur": optimized.get(
                    "net_protected_margin_after_transport_eur"
                ),
            },
            indent=2,
            default=str,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the deterministic end-to-end judge rehearsal. "
            "This is a repeatable demo fixture, not product hardcoding."
        )
    )
    parser.add_argument(
        "--event-id",
        default="IDN-CIANJUR-2022-USGS-us7000ir9t",
    )
    parser.add_argument(
        "--scenario-id",
        default="SCN-CIANJUR-REPLAY-01",
    )
    parser.add_argument("--sku", default="JI2993")
    parser.add_argument("--supplier-facility-id", default="ADI26-0240")
    parser.add_argument("--radius-km", type=float, default=150.0)
    parser.add_argument(
        "--supplier-reply",
        default=(
            "Capacity has declined to 5,500 pairs per week "
            "until 2026-11-04."
        ),
    )
    parser.add_argument("--safety-stock-site", default="WH-EU")
    parser.add_argument("--safety-stock-units", type=float, default=500.0)
    parser.add_argument("--stop-after-stage", type=int, choices=range(0, 9), default=8)
    args = parser.parse_args()

    heading(0, "RESET")
    reset = reset_demo_state()
    print(json.dumps(reset, indent=2))

    if args.stop_after_stage == 0:
        return

    heading(1, "REAL EVENT -> PUBLIC NETWORK -> PRIVATE BUSINESS GRAPH")
    triage = triage_event(
        event_id=args.event_id,
        radius_km=args.radius_km,
    )
    incident_id = triage["incident"]["incident_id"]
    print(
        json.dumps(
            {
                "event_id": args.event_id,
                "incident_id": incident_id,
                "public_facilities_potentially_exposed": triage[
                    "public_facility_count"
                ],
                "business_linked_facilities": triage[
                    "business_linked_facility_count"
                ],
                "impacted_products": [
                    {
                        "sku": row["sku"],
                        "revenue_eur": row["revenue_eur"],
                        "gross_margin_eur": row["gross_margin_eur"],
                    }
                    for row in triage["impacted_products"]
                ],
                "commercial_totals": triage["commercial_totals"],
                "claim_rule": (
                    "Public proximity is POTENTIAL exposure only. "
                    "Operational state is separate private evidence."
                ),
            },
            indent=2,
            default=str,
        )
    )

    if args.stop_after_stage == 1:
        return

    heading(2, "INITIAL PORTFOLIO + DETERMINISTIC REJECTIONS")
    initial = plan_event_recovery(
        event_id=args.event_id,
        scenario_id=args.scenario_id,
        radius_km=args.radius_km,
    )
    product = product_row(initial, args.sku)
    show_product(product)

    correlated = [
        row
        for row in product["candidates"]
        if row["decision"] == "REJECTED"
        and "SHARED_UPSTREAM_DEPENDENCY" in row.get("reasons", [])
    ]
    print("\nCorrelated backup rejection:")
    print(
        json.dumps(
            correlated[0] if correlated else {"status": "not_found"},
            indent=2,
            default=str,
        )
    )

    if args.stop_after_stage == 2:
        return

    heading(3, "RECOVERY PLANNER REQUESTS FRESH SUPPLIER EVIDENCE")
    request = create_capacity_confirmation_request(
        facility_id=args.supplier_facility_id,
        sku=args.sku,
        incident_id=incident_id,
        scenario_id=args.scenario_id,
    )
    print(
        json.dumps(
            {
                "request_id": request["request_id"],
                "status": request["status"],
                "facility_id": request["facility_id"],
                "sku": request["sku"],
                "system_value": request["system_value"],
                "message_text": request["message_text"],
                "note": (
                    "The rehearsal records the same reply path used by Slack. "
                    "No external message is sent by this script."
                ),
            },
            indent=2,
            default=str,
        )
    )

    if args.stop_after_stage == 3:
        return

    heading(4, "SUPPLIER REPLY -> PARSE -> EXPLICIT CONFIRMATION")
    reply = record_confirmation_reply(
        request_id=request["request_id"],
        raw_message=args.supplier_reply,
        sender_external_id="DEMO_SUPPLIER",
        source_message_id="DEMO-SUPPLIER-REPLY-001",
    )
    print("Parsed reply; operational state has NOT changed yet:")
    print(json.dumps(reply, indent=2, default=str))

    confirmed = confirm_supplier_reply(
        request_id=request["request_id"],
        reply_id=reply["reply_id"],
        confirmed_by="DEMO_PLANNER",
    )
    print("\nConfirmed private operational evidence:")
    print(json.dumps(confirmed, indent=2, default=str))

    process_pending_events(limit=500)

    if args.stop_after_stage == 4:
        return

    heading(5, "STATE VERSION 2 -> AUTOMATIC REPLAN")
    after_capacity = plan_event_recovery(
        event_id=args.event_id,
        scenario_id=args.scenario_id,
        radius_km=args.radius_km,
    )
    product_after_capacity = product_row(after_capacity, args.sku)
    show_product(product_after_capacity)

    emergency = product_after_capacity["emergency_plan"]
    print(
        "\nEmergency safety-stock option:",
        json.dumps(
            {
                "safety_stock_used_units": emergency[
                    "safety_stock_used_units"
                ],
                "shortage_units": emergency["shortage_units"],
                "requires_planner_approval": emergency[
                    "requires_planner_approval"
                ],
            },
            indent=2,
        ),
    )

    if args.stop_after_stage == 5:
        return

    heading(6, "HUMAN APPROVAL -> EXECUTE HIGH-IMPACT ACTION")
    approval = request_human_approval(
        incident_id=incident_id,
        scenario_id=args.scenario_id,
        sku=args.sku,
        action_type="RELEASE_SAFETY_STOCK",
        action_payload={
            "site_id": args.safety_stock_site,
            "item_type": "finished_good",
            "item_id": args.sku,
            "units": args.safety_stock_units,
        },
        reason=(
            "Emergency recovery can protect additional priority demand by "
            "releasing protected finished-goods inventory."
        ),
        requested_by="Recovery Planner",
    )
    print("Pending approval:")
    print(json.dumps(approval, indent=2, default=str))

    decision = decide_approval(
        request_id=approval["request_id"],
        decision="APPROVED",
        decided_by="DEMO_JUDGE",
        decision_reason=(
            "Approve the emergency release for the deterministic rehearsal."
        ),
    )
    print("\nHuman decision:")
    print(json.dumps(decision, indent=2, default=str))

    execution = execute_approved_action(
        request_id=approval["request_id"],
        executed_by="DEMO_JUDGE",
    )
    print("\nExecuted action:")
    print(json.dumps(execution, indent=2, default=str))

    orchestrator = process_pending_events(limit=500)
    print("\nEvent-driven replanning pass:")
    print(
        json.dumps(
            {
                "attempted": orchestrator["attempted"],
                "succeeded": orchestrator["succeeded"],
                "failed": orchestrator["failed"],
            },
            indent=2,
        )
    )

    if args.stop_after_stage == 6:
        return

    heading(7, "FINAL STATE VERSION -> CUSTOMER / MARGIN RESULT")
    final = plan_event_recovery(
        event_id=args.event_id,
        scenario_id=args.scenario_id,
        radius_km=args.radius_km,
    )
    final_product = product_row(final, args.sku)
    show_product(final_product)

    optimized = final_product.get("optimized_allocation") or {}
    print("\nCustomer allocation:")
    print(
        json.dumps(
            optimized.get("orders", []),
            indent=2,
            default=str,
        )
    )

    if args.stop_after_stage == 7:
        return

    heading(8, "OPERATIONAL MEMORY")
    memory = get_incident_memory(incident_id)
    prior = similar_incidents(
        event_type=memory["incident"]["event_type"],
        event_id=args.event_id,
        limit=5,
    )
    print(
        json.dumps(
            {
                "incident_status": memory["incident"]["status"],
                "evidence_records": len(memory["evidence"]),
                "plan_snapshots": len(memory["plans"]),
                "approvals": len(memory["approvals"]),
                "executions": len(memory.get("executions", [])),
                "agent_runs": len(memory["agent_runs"]),
                "prior_run_hypotheses": prior,
            },
            indent=2,
            default=str,
        )
    )

    print("\nDEMO REHEARSAL COMPLETE")
    print(
        "The system did not infer factory damage from an earthquake. "
        "It used public evidence to find exposure, private confirmed state to "
        "change reality, deterministic code to reject bad recovery options, "
        "a human gate for a protected action, and event-driven replanning."
    )


if __name__ == "__main__":
    main()
