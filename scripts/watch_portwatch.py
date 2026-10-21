from __future__ import annotations

import argparse
import time

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


def poll_once(*, baseline_days: int) -> dict:
    ports = modeled_ports()
    created = []
    signals = []
    unresolved = []

    print(f"Modeled transport ports: {len(ports)}")

    for unlocode in ports:
        matches = ports_by_unlocode(unlocode)
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
        anomaly = container_call_anomaly(
            str(port["portid"]),
            baseline_days=baseline_days,
        )
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

        stored = upsert_external_event(event, mode="LIVE")
        if stored["created"]:
            created.append(stored)
            print(
                f"  queued {event['event_id']} -> external.events"
            )

    return {
        "modeled_ports": ports,
        "signals": signals,
        "created_events": created,
        "unresolved_ports": unresolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor every port used by the private transport graph with "
            "real IMF PortWatch activity."
        )
    )
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=3600)
    args = parser.parse_args()

    while True:
        try:
            poll_once(baseline_days=args.baseline_days)
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
