from __future__ import annotations

import json

from dependency.solver.candidates import generate_recovery_candidates

plans = generate_recovery_candidates(
    scenario_id="SCN-CIANJUR-REPLAY-01",
    sku="JI2993",
)

print("\nRECOVERY CANDIDATES")
print("=" * 72)
for plan in plans:
    print(f"\n{plan['plan_id']} | {plan['decision']}")
    print(plan["title"])
    for reason in plan["reasons"]:
        print(f"  - {reason}")
    print(json.dumps(plan["evidence"], indent=2))
