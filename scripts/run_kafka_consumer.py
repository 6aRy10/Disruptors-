from __future__ import annotations

import argparse

from dependency.events.consumer import run_kafka_consumer
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
args = parser.parse_args()

run_kafka_consumer(
    consumer_name=args.consumer_name,
    run_agents=args.agents,
    radius_km=args.radius_km,
)
