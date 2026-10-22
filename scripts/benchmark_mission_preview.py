"""Read-only local mission latency benchmark for a verified case ID.

Does not run models, alter PostgreSQL, send outreach or approve actions.
Use repeated calls ONLY on a disposable dev DB for meaningful timing.
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone

from dependency.assistant.mission_controller import mission_preview


def summarize(results: list[dict]) -> dict:
    if not results:
        raise ValueError("No samples to summarize.")
    times = sorted(float(r["metrics"]["total_elapsed_ms"]) for r in results)
    rank95 = max(0, min(len(times)-1, (95*len(times) + 99)//100 - 1))
    return {
        "samples": len(results),
        "latency_ms_min": round(times[0], 2),
        "latency_ms_median": round(statistics.median(times), 2),
        "latency_ms_p95_nearest_rank": round(times[rank95], 2),
        "latency_ms_max": round(times[-1], 2),
        "tool_calls_total": sum(r["metrics"]["tool_calls"] for r in results),
        "tool_errors_total": sum(r["metrics"]["tool_errors"] for r in results),
        "decision_gate_statuses": sorted(set(
            r["decision_gate"]["status"] for r in results
        )),
        "mode": "DETERMINISTIC_SUPERVISOR_BASELINE",
        "model_cost_usd": 0.0,
        "note": (
            "Measures the current local DB/tool path only. It is not a "
            "measured manual analyst comparison or an agent accuracy rate. "
            "No live LLM or Aiven round-trip is included."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--sku", default=None)
    parser.add_argument("--question", default="Which backup is truly independent?")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error("--runs must be 1 to 10")
    results = []
    for _ in range(args.runs):
        try:
            results.append(mission_preview(event_id=args.event_id,
                                           sku=args.sku,
                                           question=args.question))
        except Exception as exc:
            raise SystemExit(
                "Mission benchmark stopped: " + type(exc).__name__
                + ". Inspect the event/SKU and backend readiness."
            ) from None
    data = summarize(results)
    data["event_id"] = args.event_id
    data["sku"] = args.sku
    data["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
