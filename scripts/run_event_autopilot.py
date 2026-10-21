from __future__ import annotations

import argparse
import json

from dependency.agents.orchestrator import run_event_autopilot

parser = argparse.ArgumentParser(
    description="Run the agent chain from an event ID without supplying a SKU or scenario."
)
parser.add_argument("--event-id", required=True)
parser.add_argument("--radius-km", type=float, default=150.0)
parser.add_argument("--model")
parser.add_argument("--no-persist", action="store_true")
args = parser.parse_args()

result = run_event_autopilot(
    event_id=args.event_id,
    radius_km=args.radius_km,
    model=args.model,
    persist=not args.no_persist,
)
print(json.dumps(result, indent=2, default=str))
