"""Long-running outbox relay: PostgreSQL event_outbox -> Aiven Kafka.

The relay is the only process that marks outbox rows as published, so the
API, collectors and workers never need Kafka credentials themselves.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable

from dependency.events.bus import flush_to_kafka
from dependency.events.consumer import Heartbeat


def run_kafka_publisher(
    *,
    interval_seconds: float = 2.0,
    batch_limit: int = 100,
    max_cycles: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    heartbeat_path: str | os.PathLike[str] | None = None,
    flush: Callable[..., dict] = flush_to_kafka,
    sleep: Callable[[float], Any] = time.sleep,
) -> dict:
    """Flush the outbox repeatedly until stopped.

    A failed cycle (broker unreachable, TLS error) is counted and retried on
    the next tick; rows stay in the outbox with their attempt count increased
    by ``flush_to_kafka`` when the failure is per-message. Nothing is dropped.
    """
    heartbeat = Heartbeat(heartbeat_path)
    totals = {
        "cycles": 0, "attempted": 0, "published": 0, "failed": 0,
        "cycle_errors": 0, "last_error_type": None, "stopped_by": None,
    }
    while True:
        if should_stop is not None and should_stop():
            totals["stopped_by"] = "stop_requested"
            break
        if max_cycles is not None and totals["cycles"] >= max_cycles:
            totals["stopped_by"] = "max_cycles"
            break

        heartbeat.beat()
        totals["cycles"] += 1
        try:
            result = flush(limit=batch_limit)
            for key in ("attempted", "published", "failed"):
                totals[key] += int(result.get(key, 0))
        except Exception as exc:
            # Error text from librdkafka can embed broker hostnames; keep the type only.
            totals["cycle_errors"] += 1
            totals["last_error_type"] = type(exc).__name__
            result = {"attempted": 0}

        if result.get("attempted", 0) < batch_limit:
            sleep(interval_seconds)
    return totals
