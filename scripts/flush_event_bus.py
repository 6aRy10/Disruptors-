from __future__ import annotations

import argparse
import json
import os

from dependency.events.bus import flush_to_kafka, pending

parser = argparse.ArgumentParser()
parser.add_argument("--publish", action="store_true")
parser.add_argument("--limit", type=int, default=100)
args = parser.parse_args()

rows = pending(limit=args.limit)
print(f"Pending event-bus rows: {len(rows)}")
for row in rows[:20]:
    print(
        f"  {row['topic']} | {row['event_key']} | "
        f"attempts={row['attempts']} | {row['created_at']}"
    )

if not args.publish:
    print("\nLOCAL OUTBOX MODE")
    print("Nothing was dropped. Use --publish after Aiven Kafka credentials are configured.")
    raise SystemExit(0)

if not os.getenv("AIVEN_KAFKA_BROKERS"):
    raise SystemExit("AIVEN_KAFKA_BROKERS is not configured.")

print("\nAIVEN KAFKA FLUSH")
print(json.dumps(flush_to_kafka(limit=args.limit), indent=2))
