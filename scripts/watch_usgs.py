from __future__ import annotations

import argparse
import time

from dependency.graph.exposure import facilities_within_radius
from dependency.ingest.events import upsert_external_event
from dependency.ingest.usgs import normalize, recent_events


def poll_once(*, min_magnitude: float, radius_km: float) -> None:
    features = recent_events()
    normalized = [normalize(f) for f in features]
    normalized.sort(key=lambda e: e.get("occurred_at_epoch_ms") or 0, reverse=True)

    print(f"USGS events received: {len(normalized)}")
    qualifying = 0
    hits = 0

    for event in normalized:
        mag = event.get("magnitude")
        if mag is None or float(mag) < min_magnitude:
            continue

        qualifying += 1
        stored = upsert_external_event(event, mode="LIVE")
        exposed = facilities_within_radius(
            latitude=float(event["latitude"]),
            longitude=float(event["longitude"]),
            radius_km=radius_km,
        )

        if exposed:
            hits += 1
            print(
                f"\nALERT {event['event_id']} | M{float(mag):.1f} | "
                f"{event.get('place')} | {len(exposed)} facilities within {radius_km:.0f} km"
            )
            for facility in exposed[:10]:
                print(
                    f"  {facility['distance_km']:>6.1f} km  "
                    f"{facility['facility_id']}  {facility['name']}"
                )
        elif stored["created"]:
            print(
                f"stored {event['event_id']} | M{float(mag):.1f} | no network exposure"
            )

    print(f"\nQualifying events: {qualifying}; network alerts: {hits}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poll USGS automatically and match events to supply-chain facilities."
    )
    parser.add_argument("--min-mag", type=float, default=4.5)
    parser.add_argument("--radius-km", type=float, default=150.0)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    while True:
        try:
            poll_once(min_magnitude=args.min_mag, radius_km=args.radius_km)
            if not args.watch:
                return
            print(f"\nNext poll in {args.interval}s. Press Ctrl+C to stop.")
            time.sleep(max(10, args.interval))
        except KeyboardInterrupt:
            print("\nStopped.")
            return


if __name__ == "__main__":
    main()
