from __future__ import annotations

import argparse
import json

from dependency.agents.orchestrator import run_incident_agents

parser = argparse.ArgumentParser()
parser.add_argument(
    "--event-id",
    default="IDN-CIANJUR-2022-USGS-us7000ir9t",
)
parser.add_argument(
    "--scenario-id",
    default="SCN-CIANJUR-REPLAY-01",
)
parser.add_argument("--sku", default="JI2993")
parser.add_argument("--radius-km", type=float, default=150.0)
parser.add_argument("--model")
args = parser.parse_args()

result = run_incident_agents(
    event_id=args.event_id,
    scenario_id=args.scenario_id,
    sku=args.sku,
    radius_km=args.radius_km,
    model=args.model,
)

for key in ("signal", "impact", "recovery"):
    run = result["agents"][key]
    print("\n" + "=" * 78)
    print(run["agent"].upper())
    print("=" * 78)
    print(run["output_text"])
    print("\nTOOL TRACE")
    for item in run["tool_trace"]:
        print(
            json.dumps(
                {
                    "tool": item["tool"],
                    "arguments": item["arguments"],
                },
                indent=2,
            )
        )
