from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime, timedelta

from dependency.db.connection import connect
from dependency.ingest.events import upsert_external_event
from dependency.ingest.portwatch import (
    container_call_anomaly,
    normalize_anomaly_event,
    ports_by_unlocode,
)


def modeled_ports() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT upper(port_unlocode)
            FROM transport_lanes
            WHERE port_unlocode IS NOT NULL
              AND trim(port_unlocode) <> ''
            ORDER BY upper(port_unlocode)
            """
        ).fetchall()
    return [row[0] for row in rows]


def _fresh_enough(event: dict, *, max_age_days: int = 14) -> bool:
    """An old observed port signal is not evidence of a new live incident."""
    value = event.get("occurred_at_epoch_ms")
    if value is None:
        value = event.get("occurred_at_iso")
        if value is None:
            return False
        try:
            observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=UTC)
        except ValueError:
            return False
    else:
        observed = datetime.fromtimestamp(float(value) / 1000.0, UTC)
    now = datetime.now(UTC)
    return now - timedelta(days=max_age_days) <= observed <= now + timedelta(days=1)


def poll_once(*, baseline_days: int, max_ports: int | None = None) -> dict:
    all_ports = modeled_ports()
    if max_ports is not None and max_ports < 1:
        raise ValueError("max_ports must be positive")
    ports = all_ports
    if max_ports is not None and len(all_ports) > max_ports:
        # Rotate a bounded batch hourly instead of making hundreds of
        # external API calls in one foreground invocation.
        offset = (int(time.time() // 3600) * max_ports) % len(all_ports)
        ports = [all_ports[(offset + i) % len(all_ports)] for i in range(max_ports)]
    created = []
    signals = []
    unresolved = []
    errors = []
    stale_signals = []

    print(f"Modeled transport ports: {len(ports)}")

    for unlocode in ports:
        try:
            matches = ports_by_unlocode(unlocode)
        except Exception as exc:
            errors.append({"unlocode": unlocode, "error_type": type(exc).__name__})
            continue
        if len(matches) != 1:
            unresolved.append(
                {
                    "unlocode": unlocode,
                    "match_count": len(matches),
                }
            )
            print(
                f"{unlocode}: PortWatch reference match count={len(matches)}; "
                "skipping automatic event creation."
            )
            continue

        port = matches[0]
        try:
            anomaly = container_call_anomaly(
                str(port["portid"]),
                baseline_days=baseline_days,
            )
        except Exception as exc:
            errors.append({"unlocode": unlocode, "error_type": type(exc).__name__})
            continue
        signals.append(
            {
                "unlocode": unlocode,
                "portid": port.get("portid"),
                "portname": port.get("portname"),
                **anomaly,
            }
        )

        print(
            f"{unlocode} | {port.get('portname')} | "
            f"{anomaly.get('status')} | "
            f"{anomaly.get('pct_change_vs_baseline')}%"
        )

        event = normalize_anomaly_event(
            port=port,
            anomaly=anomaly,
        )
        if not event:
            continue
        if not _fresh_enough(event):
            stale_signals.append(unlocode)
            print(f"{unlocode}: signal date is stale or unavailable; no live event created.")
            continue

        stored = upsert_external_event(event, mode="LIVE")
        if stored["created"]:
            created.append(stored)
            print(
                f"  queued {event['event_id']} -> external.events"
            )

    return {
        "modeled_port_count": len(all_ports),
        "checked_port_count": len(ports),
        "modeled_ports": ports,
        "signals": signals,
        "created_events": created,
        "unresolved_ports": unresolved,
        "source_errors": errors,
        "stale_signals": stale_signals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor every port used by the private transport graph with "
            "real IMF PortWatch activity."
        )
    )
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--max-ports", type=int, default=None)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=3600)
    args = parser.parse_args()

    while True:
        try:
            poll_once(baseline_days=args.baseline_days, max_ports=args.max_ports)
            if not args.watch:
                return
            print(
                f"\nNext PortWatch pass in {args.interval}s. "
                "Press Ctrl+C to stop."
            )
            time.sleep(max(300, args.interval))
        except KeyboardInterrupt:
            print("\nStopped.")
            return


if __name__ == "__main__":
    main()
