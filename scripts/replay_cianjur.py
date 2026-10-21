from __future__ import annotations

import json
from pathlib import Path

from dependency.graph.exposure import facilities_within_radius

ROOT = Path(__file__).resolve().parents[1]
EVENT = json.loads((ROOT / "config" / "historical_event.json").read_text(encoding="utf-8"))

for radius in (50, 100, 150):
    rows = facilities_within_radius(
        latitude=EVENT["latitude"],
        longitude=EVENT["longitude"],
        radius_km=radius,
    )
    print(f"\n{radius} km: {len(rows)} potentially exposed facilities")
    for row in rows[:10]:
        print(
            f"  {row['distance_km']:>6.1f} km  {row['facility_id']}  "
            f"{row['name']}  [{row['tier']}]"
        )
