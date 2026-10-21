from __future__ import annotations

import argparse
import json

from dependency.solver.candidates import generate_recovery_candidates

parser = argparse.ArgumentParser(
    description="Generate recovery candidates from current database state."
)
parser.add_argument("--scenario-id", required=True)
parser.add_argument("--sku", required=True)
args = parser.parse_args()

plans = generate_recovery_candidates(
    scenario_id=args.scenario_id,
    sku=args.sku,
)

print("\nRECOVERY CANDIDATES")
print("=" * 72)
for plan in plans:
    print(f"\n{plan['plan_id']} | {plan['decision']} | {plan['plan_type']}")
    print(plan["title"])
    for reason in plan["reasons"]:
        print(f"  - {reason}")
    print(json.dumps(plan["evidence"], indent=2))
