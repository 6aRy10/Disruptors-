"""NASA FIRMS VIIRS NOAA20/NOAA21 active-fire *pixel* observations.

A VIIRS pixel is NOT a certified wildfire boundary, an operational closure,
nor evidence a named supplier is damaged. It is stored in source_observations,
never in external_events and never enqueued for incident-orchestrator.
API: https://firms.modaps.eosdis.nasa.gov/api/area
"""
from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
from io import StringIO
from urllib.request import Request, urlopen

from dependency.db.connection import connect

BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
SENSORS = frozenset({"VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"})
MAX_CSV_BYTES = 5_000_000

def parse_viirs_csv(body: str, *, sensor: str, limit: int = 5000) -> list[dict]:
    if sensor not in SENSORS:
        raise ValueError("Unsupported VIIRS sensor.")
    if not 1 <= limit <= 5000:
        raise ValueError("limit must be 1..5000.")
    reader = csv.DictReader(StringIO(body))
    required = {"latitude", "longitude", "acq_date", "acq_time"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("FIRMS CSV is missing required observation fields.")
    records = []
    seen = set()
    for row in reader:
        if len(records) >= limit:
            break
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            when = datetime.strptime(
                row["acq_date"] + " " + str(row["acq_time"]).zfill(4),
                "%Y-%m-%d %H%M"
            ).replace(tzinfo=UTC)
        except (ValueError, TypeError, KeyError):
            continue
        # Stable satellite-pixel identity prevents repeat polling from
        # appearing as a fresh disaster. Fractional pixel coords retained.
        identity = f"{sensor}:{when.isoformat()}:{lat:.5f}:{lon:.5f}"
        oid = hashlib.sha256(identity.encode()).hexdigest()[:24]
        if oid in seen:
            continue
        seen.add(oid)
        records.append({
            "observation_id": oid, "source": "NASA_FIRMS",
            "observation_type": "ACTIVE_FIRE_SATELLITE_PIXEL",
            "sensor": sensor, "latitude": lat, "longitude": lon,
            "observed_at": when,
            "satellite": row.get("satellite"),
            "confidence": row.get("confidence"),
            "fire_radiative_power": row.get("frp"),
            "data_provenance": "VERIFIED_PUBLIC",
            "meaning": "SATELLITE_THERMAL_DETECTION_NOT_CONFIRMED_WILDFIRE_OR_FACTORY_CLOSURE",
            "source_url": "https://firms.modaps.eosdis.nasa.gov/",
        })
    return records


def fetch_hotspots(*, map_key: str, sensor: str = "VIIRS_NOAA20_NRT",
                   bounds: tuple[float,float,float,float] = (95,-11,141,6),
                   days: int = 1, limit: int = 5000) -> list[dict]:
    if not map_key or any(c in map_key for c in ("/","?","#"," ","\\","%")):
        raise ValueError("Missing or invalid NASA FIRMS MAP_KEY.")
    if sensor not in SENSORS:
        raise ValueError("Only NOAA20/21 VIIRS NRT is allowed.")
    w,s,e,n = map(float, bounds)
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError("Invalid longitude/latitude bounds.")
    if not 1 <= days <= 5:
        raise ValueError("NASA FIRMS supports only 1..5 day range.")
    coords = ",".join(f"{v:g}" for v in (w,s,e,n))
    # URL contains secret; NEVER print URL, raw exception or HTTP error.
    url = f"{BASE}/{map_key}/{sensor}/{coords}/{days}"
    req = Request(url, headers={
        "User-Agent": "HERMES-source-observer/1.0",
        "Accept": "text/csv",
    })
    try:
        with urlopen(req, timeout=30) as response:
            blob = response.read(MAX_CSV_BYTES + 1)
    except Exception as exc:
        raise RuntimeError("FIRMS request failed: " + type(exc).__name__) from None
    if len(blob) > MAX_CSV_BYTES:
        raise RuntimeError("FIRMS response too large; narrow geographic bounds.")
    try:
        return parse_viirs_csv(blob.decode("utf-8-sig"), sensor=sensor, limit=limit)
    except UnicodeError:
        raise RuntimeError("FIRMS response encoding invalid.") from None


def store_hotspots(records: list[dict]) -> dict:
    """Insert actual pixels with stable IDs; NO incident outbox dispatch."""
    if len(records) > 5000:
        raise ValueError("Exceeded bounded batch size.")
    inserted = 0
    with connect() as conn:
        if conn.execute("SELECT to_regclass(%s)",
                        ("public.source_observations",)).fetchone()[0] is None:
            raise RuntimeError("Migration 006 is required before source collection.")
        for rec in records:
            if rec.get("observation_type") != "ACTIVE_FIRE_SATELLITE_PIXEL":
                raise ValueError("Only satellite pixels may be stored here.")
            cur = conn.execute("""
                INSERT INTO source_observations(
                    source,observation_id,observation_type,observed_at,
                    latitude,longitude,geom,raw_json,source_url,provenance_class
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,
                    ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
                    %s::jsonb,%s,%s
                )
                ON CONFLICT (source,observation_id) DO UPDATE SET
                    last_checked_at=now()
                RETURNING (xmax=0)
            """, (
                "NASA_FIRMS",rec["observation_id"],
                rec["observation_type"],rec["observed_at"],
                rec["latitude"],rec["longitude"],
                rec["longitude"],rec["latitude"],
                __import__("json").dumps({
                    "sensor":rec["sensor"],
                    "confidence":rec["confidence"],
                    "frp":rec["fire_radiative_power"],
                    "satellite":rec["satellite"],
                    "interpretation":rec["meaning"],
                }),rec["source_url"],rec["data_provenance"],
            ))
            inserted += int(bool(cur.fetchone()[0]))
        conn.commit()
    return {
        "source": "NASA_FIRMS",
        "received_count": len(records), "created_count": inserted,
        "storage": "source_observations",
        "incident_tasks_created": 0,
        "interpretation": "FIRE_PIXEL_NOT_CONFIRMED_DISRUPTION",
    }
