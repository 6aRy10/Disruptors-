from __future__ import annotations

import json
from pathlib import Path

from dependency.graph.exposure import (
    facilities_within_radius,
    operational_facilities_within_radius,
)

ROOT = Path(__file__).resolve().parents[1]
EVENT = json.loads((ROOT / "config" / "historical_event.json").read_text(encoding="utf-8"))

for radius in (50, 100, 150):
    public_rows = facilities_within_radius(
        latitude=EVENT["latitude"],
        longitude=EVENT["longitude"],
        radius_km=radius,
    )
    operational_rows = operational_facilities_within_radius(
        latitude=EVENT["latitude"],
        longitude=EVENT["longitude"],
        radius_km=radius,
    )
    linked = [r for r in public_rows if r["business_linked"]]

    print(
        f"\n{radius} km: {len(public_rows)} public adidas facilities potentially exposed"
    )
    print(
        f"         {len(linked)} link into the private operational twin; "
        f"{len(operational_rows)} operational demo nodes are in-radius"
    )
    for row in public_rows[:15]:
        marker = "BUSINESS-LINKED" if row["business_linked"] else "PUBLIC-NETWORK"
        print(
            f"  {row['distance_km']:>6.1f} km  {row['network_facility_id']}  "
            f"{row['name']}  [{row['tier']}]  {marker}"
        )
