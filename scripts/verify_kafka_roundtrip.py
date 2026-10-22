"""Prove publish AND consume through the real Aiven Kafka brokers.

Default mode is read-only (config validation + broker metadata probe).
``--publish`` writes exactly one synthetic probe message to the physical topic
and reads it back with a throwaway consumer group. PostgreSQL is not touched.
"""
from __future__ import annotations

import argparse
import json

from dependency.events.health import probe_brokers
from dependency.events.kafka_settings import load_kafka_settings

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--publish", action="store_true",
                    help="Publish one probe envelope and consume it back.")
parser.add_argument("--timeout", type=float, default=30.0)
args = parser.parse_args()

settings = load_kafka_settings().describe()
report = {"configuration": settings, "brokers": {"status": "NOT_PROBED"},
          "roundtrip": {"status": "NOT_RUN"}}
if not settings["valid"]:
    print(json.dumps(report, indent=2))
    raise SystemExit(2)

report["brokers"] = probe_brokers(timeout=min(args.timeout, 10.0))
if args.publish and report["brokers"]["status"] == "REACHABLE":
    from dependency.events.roundtrip import kafka_roundtrip

    report["roundtrip"] = kafka_roundtrip(timeout_seconds=args.timeout)

print(json.dumps(report, indent=2))
ok = report["brokers"]["status"] == "REACHABLE" and (
    not args.publish or report["roundtrip"]["status"] == "VERIFIED")
raise SystemExit(0 if ok else 1)
