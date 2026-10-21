from __future__ import annotations

import argparse
import json

from dependency.services.capacity import confirm_supplier_capacity
from dependency.supplier_confirmations import parse_supplier_reply
from dependency.solver.recovery import plan_sku_recovery

SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"
FACILITY_ID = "ADI26-0240"
SKU = "JI2993"

parser = argparse.ArgumentParser()
parser.add_argument(
    "--text",
    default="Capacity has declined to 5,500 pairs per week until 2026-11-04.",
)
parser.add_argument(
    "--confirm",
    action="store_true",
    help="Apply the parsed capacity to PostgreSQL after explicit confirmation.",
)
args = parser.parse_args()

parsed = parse_supplier_reply(args.text)
print("\nPARSED SUPPLIER REPLY")
print(json.dumps(parsed, indent=2))

if not parsed.get("ok"):
    raise SystemExit(1)

if not args.confirm:
    print("\nNOT APPLIED.")
    print("Review the parsed values, then rerun with --confirm.")
    raise SystemExit(0)

update = confirm_supplier_capacity(
    facility_id=FACILITY_ID,
    sku=SKU,
    capacity_units=parsed["capacity_units"],
    valid_until=parsed["effective_until"],
    source_channel="Slack Connect demo",
    raw_message=args.text,
)

print("\nCONFIRMED DATABASE UPDATE")
print(json.dumps(update, indent=2))

plan = plan_sku_recovery(scenario_id=SCENARIO_ID, sku=SKU)
print("\nREPLANNED")
print(json.dumps({
    "state_version": plan["state_version"],
    "plan_status": plan["plan_status"],
    "backup_available_units": plan["backup_available_units"],
    "total_available_units": plan["total_available_units"],
    "shortage_units": plan["shortage_units"],
    "requires_supplier_confirmation": plan["requires_supplier_confirmation"],
    "protected_revenue_eur": plan["allocation"]["protected_revenue_eur"],
    "protected_margin_eur": plan["allocation"]["protected_margin_eur"],
}, indent=2))
