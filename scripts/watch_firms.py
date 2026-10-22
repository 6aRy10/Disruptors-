"""Collect NASA FIRMS satellite detections for bounded Indonesia coverage.

FIRMS_MAP_KEY must be in the backend environment. This script never prints
the key and never creates an external incident. A pixel is not a wildfire.
Use --dry-run to inspect observation counts without touching PostgreSQL.
"""
from __future__ import annotations

import argparse
import json
import os
from dependency.ingest.firms import fetch_hotspots, store_hotspots


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sensor", choices=("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"),
                   default="VIIRS_NOAA20_NRT")
    p.add_argument("--days", type=int, default=1)
    p.add_argument("--bounds", nargs=4, type=float,
                   default=[95,-11,141,6],
                   metavar=("WEST","SOUTH","EAST","NORTH"))
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    key=os.getenv("FIRMS_MAP_KEY", "").strip()
    if not key:
        print(json.dumps({
            "source":"NASA_FIRMS", "status":"NOT_CONFIGURED",
            "next_step":"Request free NASA FIRMS MAP_KEY and set FIRMS_MAP_KEY privately.",
        }))
        return 2
    try:
        rows = fetch_hotspots(map_key=key,sensor=a.sensor,
                             bounds=tuple(a.bounds),days=a.days)
        if a.dry_run:
            output={
                "source":"NASA_FIRMS","status":"DRY_RUN",
                "received_count":len(rows),"written":False,
                "interpretation":"SATELLITE_PIXELS_NOT_WILDFIRE_BOUNDARIES",
            }
        else:
            output={"status":"STORED_PIXELS_NOT_INCIDENTS",**store_hotspots(rows)}
        print(json.dumps(output))
        return 0
    except Exception as exc:
        # Never output the secret-containing HTTP URL from urllib.
        print(json.dumps({
            "source":"NASA_FIRMS", "status":"ERROR",
            "error_type":type(exc).__name__,
        }))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
