from __future__ import annotations

import argparse
import json

from dependency.incidents.triage import triage_event

parser = argparse.ArgumentParser(
    description="Triage any stored external event against the public and private supply graph."
)
parser.add_argument("--event-id", required=True)
parser.add_argument("--radius-km", type=float, default=150.0)
args = parser.parse_args()

result = triage_event(
    event_id=args.event_id,
    radius_km=args.radius_km,
)
print(json.dumps(result, indent=2, default=str))
