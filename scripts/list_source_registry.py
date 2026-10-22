"""HERMES public/enterprise live-data source backlog.

This reads a reviewed declarative registry. Listing a source is NOT proof it
is connected, licensed, operational, or currently emitting events.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "config" / "live_source_registry.json"
PRIORITIES = {"P0", "P1", "P2"}

def read_sources(path: Path = REGISTRY) -> list[dict]:
    document = json.loads(path.read_text(encoding="utf-8"))
    seen = set()
    for item in document["sources"]:
        if item["id"] in seen:
            raise ValueError("Duplicate source id: " + item["id"])
        seen.add(item["id"])
        if item["priority"] not in PRIORITIES:
            raise ValueError("Unknown source priority: " + item["id"])
        if not item["documentation"].startswith("https://"):
            raise ValueError("Missing official source URL: " + item["id"])
        if not item.get("entity_join"):
            raise ValueError("Source does not have a defined join: " + item["id"])
    return document["sources"]

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority", choices=sorted(PRIORITIES))
    parser.add_argument("--domain")
    parser.add_argument("--json", action="store_true")
    args=parser.parse_args()
    entries=read_sources()
    if args.priority:
        entries=[s for s in entries if s["priority"]==args.priority]
    if args.domain:
        entries=[s for s in entries if s["domain"].lower()==args.domain.lower()]
    if args.json:
        print(json.dumps(entries,indent=2))
        return
    print("HERMES SOURCE REGISTRY (not an uptime or connection report)")
    for s in entries:
        print(f"{s['priority']:2} | {s['id']:<23} | {s['status']:<23} | {s['suggested_cadence']:<10} | {s['domain']}")
    print("Sources listed:",len(entries))

if __name__=="__main__":
    main()
