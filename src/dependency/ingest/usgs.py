from __future__ import annotations

import json
from urllib.request import urlopen, Request

USGS_ALL_HOUR = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
USGS_EVENT = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/detail/{event_id}.geojson"


def _get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "dependency-hackathon/1.0"})
    with urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def recent_events() -> list[dict]:
    """Poll the near-real-time USGS GeoJSON summary feed."""
    return _get_json(USGS_ALL_HOUR).get("features", [])


def event_detail(event_id: str) -> dict:
    """Fetch one event. Useful for deterministic historical replay."""
    return _get_json(USGS_EVENT.format(event_id=event_id))


def normalize(feature: dict) -> dict:
    coords = feature["geometry"]["coordinates"]
    props = feature.get("properties", {})
    return {
        "event_id": feature["id"],
        "source": "USGS",
        "event_type": "earthquake",
        "magnitude": props.get("mag"),
        "place": props.get("place"),
        "occurred_at_epoch_ms": props.get("time"),
        "longitude": coords[0],
        "latitude": coords[1],
        "depth_km": coords[2],
        "detail_url": props.get("detail"),
        "raw_json": feature,
    }
