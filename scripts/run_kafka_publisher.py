"""Relay the PostgreSQL transactional outbox to Aiven Kafka until stopped."""
from __future__ import annotations

import argparse
import json
import os

from dependency.events.consumer import install_signal_stop
from dependency.events.kafka_settings import load_kafka_settings
from dependency.events.publisher import run_kafka_publisher

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--interval", type=float,
                    default=float(os.getenv("HERMES_PUBLISHER_INTERVAL_SECONDS", "2")))
parser.add_argument("--limit", type=int, default=100)
parser.add_argument("--max-cycles", type=int, default=None,
                    help="Stop after N flush cycles (default: run forever).")
parser.add_argument("--heartbeat", default=os.getenv("HERMES_HEARTBEAT_FILE"))
args = parser.parse_args()

settings = load_kafka_settings().describe()
if not settings["valid"]:
    raise SystemExit("Kafka not configured: " + " ".join(settings["problems"]))

print(json.dumps({"publisher": "starting", "kafka": settings}))
totals = run_kafka_publisher(
    interval_seconds=args.interval,
    batch_limit=args.limit,
    max_cycles=args.max_cycles,
    should_stop=install_signal_stop(),
    heartbeat_path=args.heartbeat,
)
print(json.dumps({"publisher": "stopped", **totals}))
