from __future__ import annotations

from dependency.solver.recovery import plan_sku_recovery

SCENARIO_ID = "SCN-CIANJUR-REPLAY-01"
SKU = "JI2993"

conservative = plan_sku_recovery(
    scenario_id=SCENARIO_ID,
    sku=SKU,
    release_safety_stock=False,
)

emergency = plan_sku_recovery(
    scenario_id=SCENARIO_ID,
    sku=SKU,
    release_safety_stock=True,
)

print("\nJI2993 RECOVERY PLAN")
print("=" * 72)
print(f"Scenario: {conservative['scenario_id']}")
print(f"State version: {conservative['state_version']}")
print(f"Demand: {conservative['demand_units']} units")
print(f"Lost primary production: {conservative['lost_primary_units']:.0f}")

backup = conservative["selected_backup"]
if backup:
    print(
        "Selected backup: "
        f"{backup['facility_id']} {backup['facility_name']} | "
        f"available {backup['available_capacity_units']:.0f} | "
        f"evidence age {backup['evidence_age_hours']:.0f}h"
    )
    print(f"Supplier confirmation required: {backup['requires_supplier_confirmation']}")

print("\nOPTION A - PRESERVE SAFETY STOCK")
print(f"Status: {conservative['plan_status']}")
print(f"Usable finished inventory: {conservative['inventory']['usable_inventory_units']:.0f}")
print(f"Backup available: {conservative['backup_available_units']:.0f}")
print(f"Total available: {conservative['total_available_units']:.0f}")
print(f"Shortage: {conservative['shortage_units']:.0f}")
print("Planner approval required: False")

print("\nOPTION B - RELEASE SAFETY STOCK")
print(f"Status: {emergency['plan_status']}")
print(f"Usable finished inventory: {emergency['inventory']['usable_inventory_units']:.0f}")
print(f"Safety stock used: {emergency['inventory']['safety_stock_used_units']:.0f}")
print(f"Backup available: {emergency['backup_available_units']:.0f}")
print(f"Total available: {emergency['total_available_units']:.0f}")
print(f"Shortage: {emergency['shortage_units']:.0f}")
print(f"Planner approval required: {emergency['requires_planner_approval']}")
