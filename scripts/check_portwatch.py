from __future__ import annotations

import argparse
import json

from dependency.ingest.portwatch import container_call_anomaly, search_ports

parser = argparse.ArgumentParser()
parser.add_argument("--name", default="Yantian")
parser.add_argument("--portid")
parser.add_argument("--baseline-days", type=int, default=30)
args = parser.parse_args()

portid = args.portid
if not portid:
    matches = search_ports(args.name)
    print(f"PortWatch matches for {args.name!r}: {len(matches)}")
    for row in matches[:20]:
        print(
            f"  {row.get('portid')} | {row.get('portname')} | "
            f"{row.get('country')} | LOCODE {row.get('LOCODE')}"
        )
    if len(matches) == 1:
        portid = matches[0].get("portid")
    else:
        print("\nPass --portid after selecting the correct port.")
        raise SystemExit(0)

result = container_call_anomaly(portid, baseline_days=args.baseline_days)
print("\nPORT ACTIVITY SIGNAL")
print(json.dumps(result, indent=2))
