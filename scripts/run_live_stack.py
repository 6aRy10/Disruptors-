"""Launch both public disaster feeds and the local incident orchestrator.

Run from the repository root:
    python -m scripts.run_live_stack
    python -m scripts.run_live_stack --watch
This script does not reset the database or invoke paid LLM agents.
"""
from __future__ import annotations

import argparse
import json
import time

from dependency.automation.orchestrator import process_pending_events
from dependency.db.connection import connect
from dependency.ingest.collector_checks import record_collector_check
from scripts.watch_usgs import poll_once as poll_usgs_once
from scripts.watch_gdacs import poll_once as poll_gdacs_once
from scripts.watch_portwatch import poll_once as poll_portwatch_once


def require_database() -> None:
    """Avoid silently monitoring an uninitialized local database."""
    with connect() as conn:
        for table in ("network_facilities", "products", "external_events", "event_outbox"):
            if conn.execute(
                "SELECT to_regclass(%s)", (f"public.{table}",)
            ).fetchone()[0] is None:
                raise RuntimeError(
                    f"Missing table {table}. Initialize a disposable database first."
                )
        count = conn.execute("SELECT COUNT(*) FROM network_facilities").fetchone()[0]
        if int(count) == 0:
            raise RuntimeError("The public supply network is empty. Load seed data first.")


def run_cycle(
    *,
    usgs: bool = True,
    gdacs: bool = True,
    worker: bool = True,
    agents: bool = False,
    portwatch: bool = False,
    portwatch_max_ports: int = 3,
    radius_km: float = 150.0,
    min_magnitude: float = 4.5,
    batch_limit: int = 200,
) -> dict:
    """One observable cycle. A failed source cannot disable the other sources."""
    results = {}
    tasks = []
    if usgs:
        tasks.append(("USGS", lambda: poll_usgs_once(
            min_magnitude=min_magnitude, radius_km=radius_km
        )))
    if gdacs:
        tasks.append(("GDACS", lambda: poll_gdacs_once(
            radius_km=radius_km,
            event_types={"TC", "FL", "VO", "WF"},
            alert_levels={"Green", "Orange", "Red"},
        )))
    if portwatch:
        tasks.append(("PORTWATCH", lambda: poll_portwatch_once(
            baseline_days=30, max_ports=portwatch_max_ports,
        )))
    if worker:
        tasks.append(("ORCHESTRATOR", lambda: process_pending_events(
            limit=batch_limit, run_agents=agents, radius_km=radius_km
        )))

    for name, task in tasks:
        try:
            result = task()
            if name == "PORTWATCH":
                errors = result.get("source_errors", [])
                results[name] = {
                    "status": "ERROR" if errors else "OK",
                    "checked_ports": result.get("checked_port_count", 0),
                    "modeled_ports": result.get("modeled_port_count", 0),
                    "created_events": len(result.get("created_events", [])),
                    "unresolved_ports": len(result.get("unresolved_ports", [])),
                    "stale_signals": len(result.get("stale_signals", [])),
                    "source_errors": errors,
                }
            elif name == "ORCHESTRATOR":
                failed = int(result.get("failed", 0))
                results[name] = {
                    "status": "FAILED_EVENTS" if failed else "OK",
                    "attempted": result.get("attempted", 0),
                    "succeeded": result.get("succeeded", 0),
                    "failed": failed,
                }
            else:
                summary = result if isinstance(result, dict) else {}
                results[name] = {
                    "status": "OK",
                    "received_count": int(summary.get("received_count", 0)),
                    "created_count": int(summary.get("created_count", 0)),
                }
            if name in {"USGS", "GDACS", "PORTWATCH"}:
                summary = result if isinstance(result, dict) else {}
                created = (len(summary.get("created_events", []))
                           if name == "PORTWATCH" else int(summary.get("created_count", 0)))
                try:
                    results[name]["check_recorded"] = record_collector_check(
                        source=name, status="OK",
                        received_count=int(summary.get("received_count",
                            summary.get("checked_port_count", 0))),
                        created_count=created,
                    )
                except Exception:
                    results[name]["check_recorded"] = False
        except Exception as exc:
            # Never log connection URLs or provider credentials.
            results[name] = {"status": "ERROR", "error_type": type(exc).__name__}
            if name in {"USGS", "GDACS", "PORTWATCH"}:
                try:
                    results[name]["check_recorded"] = record_collector_check(
                        source=name, status="ERROR", error_type=type(exc).__name__,
                    )
                except Exception:
                    results[name]["check_recorded"] = False
    return {
        "status": (
            "OK"
            if all(v["status"] == "OK" for v in results.values())
            else "DEGRADED"
        ),
        "sources": results,
    }


def run_watch(
    *,
    radius_km: float,
    usgs_interval: int,
    gdacs_interval: int,
    worker_interval: int,
    portwatch: bool,
    portwatch_interval: int,
    portwatch_max_ports: int,
    agents: bool,
    min_magnitude: float,
    batch_limit: int,
) -> None:
    periods = {
        "USGS": max(30, usgs_interval),
        "GDACS": max(60, gdacs_interval),
        "ORCHESTRATOR": max(2, worker_interval),
    }
    if portwatch:
        periods["PORTWATCH"] = max(300, portwatch_interval)
    next_due = {name: 0.0 for name in periods}
    print("Live Dependency monitoring is running. Press Ctrl+C to stop.", flush=True)
    try:
        while True:
            now = time.monotonic()
            due = {name for name, when in next_due.items() if now >= when}
            if due:
                result = run_cycle(
                    usgs="USGS" in due,
                    gdacs="GDACS" in due,
                    worker="ORCHESTRATOR" in due,
                    portwatch="PORTWATCH" in due,
                    agents=agents,
                    portwatch_max_ports=portwatch_max_ports,
                    radius_km=radius_km,
                    min_magnitude=min_magnitude,
                    batch_limit=batch_limit,
                )
                print(json.dumps(result, default=str), flush=True)
                finished = time.monotonic()
                for name in due:
                    next_due[name] = finished + periods[name]
            time.sleep(min(1.0, max(0.1, min(next_due.values()) - time.monotonic())))
    except KeyboardInterrupt:
        print("Live monitoring stopped.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest USGS/GDACS events and process the PostgreSQL outbox."
    )
    parser.add_argument("--watch", action="store_true",
                        help="Keep polling. Without this flag, run one cycle.")
    parser.add_argument("--radius-km", type=float, default=150.0)
    parser.add_argument("--min-mag", type=float, default=4.5)
    parser.add_argument("--usgs-seconds", type=int, default=60)
    parser.add_argument("--gdacs-seconds", type=int, default=300)
    parser.add_argument("--worker-seconds", type=int, default=5)
    parser.add_argument("--portwatch", action="store_true", help="Also check bounded IMF PortWatch port activity.")
    parser.add_argument("--agents", action="store_true", help="Opt in to paid model investigation of new evidence tasks.")
    parser.add_argument("--portwatch-seconds", type=int, default=3600)
    parser.add_argument("--portwatch-max-ports", type=int, default=3)
    parser.add_argument("--batch-limit", type=int, default=200)
    args = parser.parse_args()

    if args.radius_km <= 0 or args.batch_limit <= 0 or args.portwatch_max_ports <= 0:
        parser.error("radius-km, batch-limit and portwatch-max-ports must be positive")

    try:
        require_database()
    except Exception as exc:
        print(json.dumps({"status": "NOT_READY", "reason_type": type(exc).__name__}))
        return 2

    if args.watch:
        run_watch(
            radius_km=args.radius_km,
            min_magnitude=args.min_mag,
            usgs_interval=args.usgs_seconds,
            gdacs_interval=args.gdacs_seconds,
            worker_interval=args.worker_seconds,
            portwatch=args.portwatch,
            portwatch_interval=args.portwatch_seconds,
            portwatch_max_ports=args.portwatch_max_ports,
            agents=args.agents,
            batch_limit=args.batch_limit,
        )
        return 0

    result = run_cycle(
        radius_km=args.radius_km,
        min_magnitude=args.min_mag,
        batch_limit=args.batch_limit,
        portwatch=args.portwatch,
        portwatch_max_ports=args.portwatch_max_ports,
        agents=args.agents,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
