from __future__ import annotations

import argparse
import time

from dependency.graph.exposure import facilities_within_radius
from dependency.ingest.events import upsert_external_event
from dependency.ingest.gdacs import normalize, recent_events


def poll_once(
    *,
    radius_km: float,
    event_types: set[str],
    alert_levels: set[str],
) -> None:
    features = recent_events()
    events = [e for e in (normalize(f) for f in features) if e is not None]

    print(f"GDACS events received: {len(events)}")
    qualifying = 0
    hits = 0
    created = 0

    for event in events:
        if event["event_type_code"] not in event_types:
            continue
        level = str(event.get("alert_level") or "").title()
        if alert_levels and level not in alert_levels:
            continue

        qualifying += 1
        stored = upsert_external_event(event, mode="LIVE")
        created += int(bool(stored["created"]))
        exposed = facilities_within_radius(
            latitude=event["latitude"],
            longitude=event["longitude"],
            radius_km=radius_km,
        )

        if exposed:
            hits += 1
            print(
                f"\nALERT {event['event_id']} | {event['event_type']} | "
                f"{level or 'Unknown'} | {event.get('title')} | "
                f"{len(exposed)} facilities within {radius_km:.0f} km"
            )
            for facility in exposed[:10]:
                print(
                    f"  {facility['distance_km']:>6.1f} km  "
                    f"{facility.get('network_facility_id', facility.get('facility_id'))}  "
                    f"{facility['name']}"
                )
            if stored["created"]:
                print("  queued: external.events -> incident orchestrator")
        elif stored["created"]:
            print(
                f"stored {event['event_id']} | {event['event_type']} | "
                f"{level or 'Unknown'} | no network exposure"
            )

    print(f"\nQualifying events: {qualifying}; network alerts: {hits}")
    return {"received_count": len(events), "qualifying_count": qualifying,
            "created_count": created, "nearby_reports": hits}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poll GDACS multi-hazard events and match them to the supply network."
    )
    parser.add_argument("--radius-km", type=float, default=150.0)
    parser.add_argument("--types", default="TC,FL,VO,WF")
    parser.add_argument("--alert-levels", default="Green,Orange,Red")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    args = parser.parse_args()

    event_types = {x.strip().upper() for x in args.types.split(",") if x.strip()}
    alert_levels = {x.strip().title() for x in args.alert_levels.split(",") if x.strip()}

    while True:
        try:
            poll_once(
                radius_km=args.radius_km,
                event_types=event_types,
                alert_levels=alert_levels,
            )
            if not args.watch:
                return
            print(f"\nNext poll in {args.interval}s. Press Ctrl+C to stop.")
            time.sleep(max(30, args.interval))
        except KeyboardInterrupt:
            print("\nStopped.")
            return


if __name__ == "__main__":
    main()
