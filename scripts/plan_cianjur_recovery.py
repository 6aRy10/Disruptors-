from __future__ import annotations

import json

from dependency.solver.recovery import plan_sku_recovery

SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"
SKU = "JI2993"

plan = plan_sku_recovery(scenario_id=SCENARIO_ID, sku=SKU)

print("\nJI2993 RECOVERY PLAN")
print("=" * 72)
print(f"Scenario: {plan['scenario_id']}")
print(f"State version: {plan['state_version']}")
print(f"Status: {plan['plan_status']}")
print(f"Demand: {plan['demand_units']} units")
print(f"Usable finished inventory: {plan['inventory']['usable_inventory_units']:.0f}")
print(f"Lost primary production: {plan['lost_primary_units']:.0f}")

backup = plan["selected_backup"]
if backup:
    print(
        "Selected backup: "
        f"{backup['facility_id']} {backup['facility_name']} | "
        f"available {backup['available_capacity_units']:.0f} | "
        f"evidence age {backup['evidence_age_hours']:.0f}h"
    )
    print(f"Supplier confirmation required: {backup['requires_supplier_confirmation']}")
else:
    print("Selected backup: NONE")

print(f"Total available: {plan['total_available_units']:.0f}")
print(f"Shortage: {plan['shortage_units']:.0f}")
print(f"Safety stock used: {plan['inventory']['safety_stock_used_units']:.0f}")

print("\nORDER ALLOCATION")
for row in plan["allocation"]["allocations"]:
    print(
        f"  {row['order_id']}: allocated {row['allocated_qty']}, "
        f"late {row['late_qty']}, protected margin EUR {row['protected_margin_eur']:,.0f}"
    )

print("\nSUMMARY")
print(json.dumps({
    "plan_status": plan["plan_status"],
    "state_version": plan["state_version"],
    "demand_units": plan["demand_units"],
    "total_available_units": plan["total_available_units"],
    "shortage_units": plan["shortage_units"],
    "requires_supplier_confirmation": plan["requires_supplier_confirmation"],
    "protected_revenue_eur": plan["allocation"]["protected_revenue_eur"],
    "protected_margin_eur": plan["allocation"]["protected_margin_eur"],
}, indent=2))
