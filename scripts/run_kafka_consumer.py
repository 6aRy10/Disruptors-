from __future__ import annotations

import argparse
import json
import os

from dependency.events.consumer import install_signal_stop, run_kafka_consumer
from dependency.events.kafka_settings import load_kafka_settings
from dependency.automation.orchestrator import DEFAULT_CONSUMER


parser = argparse.ArgumentParser(
    description="Run the Aiven Kafka incident orchestrator."
)
parser.add_argument("--agents", action="store_true")
parser.add_argument("--radius-km", type=float, default=150.0)
parser.add_argument(
    "--consumer-name",
    default=DEFAULT_CONSUMER,
)
parser.add_argument("--max-messages", type=int, default=None,
                    help="Stop after N handled events (default: run forever).")
parser.add_argument("--heartbeat", default=os.getenv("HERMES_HEARTBEAT_FILE"))
args = parser.parse_args()

settings = load_kafka_settings().describe()
if not settings["valid"]:
    raise SystemExit("Kafka not configured: " + " ".join(settings["problems"]))

print(json.dumps({"consumer": "starting", "kafka": settings}))
stats = run_kafka_consumer(
    consumer_name=args.consumer_name,
    run_agents=args.agents,
    radius_km=args.radius_km,
    max_messages=args.max_messages,
    should_stop=install_signal_stop(),
    heartbeat_path=args.heartbeat,
)
print(json.dumps({"consumer": "stopped", **stats}))
