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
    magnitude_pass = 0
    hits = 0

    for event in normalized:
        mag = event.get("magnitude")
        mag_value = float(mag) if mag is not None else None

        # Store the feed observation before applying alert policy. This keeps
        # detection separate from triage and prevents a global magnitude cutoff
        # from hiding a smaller event that is very close to a facility.
        stored = upsert_external_event(event, mode="LIVE")
        exposed = facilities_within_radius(
            latitude=float(event["latitude"]),
            longitude=float(event["longitude"]),
            radius_km=radius_km,
        )

        passes_magnitude = mag_value is not None and mag_value >= min_magnitude
        if passes_magnitude:
            magnitude_pass += 1

        if exposed:
            hits += 1
            reason = (
                f"M{mag_value:.1f} >= {min_magnitude:.1f}"
                if passes_magnitude
                else f"network proximity overrides M{min_magnitude:.1f} threshold"
            )
            mag_label = f"M{mag_value:.1f}" if mag_value is not None else "M?"
            print(
                f"\nALERT {event['event_id']} | {mag_label} | "
                f"{event.get('place')} | {len(exposed)} facilities within {radius_km:.0f} km"
            )
            print(f"  trigger: {reason}")
            for facility in exposed[:10]:
                print(
                    f"  {facility['distance_km']:>6.1f} km  "
                    f"{facility['facility_id']}  {facility['name']}"
                )
        elif passes_magnitude and stored["created"]:
            print(
                f"stored {event['event_id']} | M{mag_value:.1f} | "
                "magnitude threshold passed; no network exposure"
            )

    print(
        f"\nMagnitude threshold passed: {magnitude_pass}; "
        f"network alerts: {hits}"
    )


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
