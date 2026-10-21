from __future__ import annotations

import argparse
import json
import time

from dependency.automation.orchestrator import process_pending_events

parser = argparse.ArgumentParser(
    description="Process transactional-outbox events with the local incident orchestrator."
)
parser.add_argument("--watch", action="store_true")
parser.add_argument("--interval", type=int, default=5)
parser.add_argument("--limit", type=int, default=50)
parser.add_argument("--agents", action="store_true")
parser.add_argument("--radius-km", type=float, default=150.0)
args = parser.parse_args()

while True:
    result = process_pending_events(
        limit=args.limit,
        run_agents=args.agents,
        radius_km=args.radius_km,
    )
    print(json.dumps(result, indent=2, default=str))

    if not args.watch:
        break

    print(f"\nNext orchestration pass in {args.interval}s. Press Ctrl+C to stop.")
    try:
        time.sleep(max(1, args.interval))
    except KeyboardInterrupt:
        print("\nStopped.")
        break
