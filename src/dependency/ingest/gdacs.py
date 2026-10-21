from __future__ import annotations

import json
from urllib.request import Request, urlopen

GDACS_EVENTS4APP = "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/EVENTS4APP"

TYPE_MAP = {
    "EQ": "earthquake",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "VO": "volcano",
    "DR": "drought",
    "WF": "wildfire",
}


def _get_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "disruptors-hackathon/0.2"})
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def recent_events() -> list[dict]:
    payload = _get_json(GDACS_EVENTS4APP)
    return payload.get("features", [])


def normalize(feature: dict) -> dict | None:
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates") or []
    if geometry.get("type") != "Point" or len(coords) < 2:
        return None

    props = feature.get("properties") or {}
    event_type_code = str(props.get("eventtype") or "").upper()
    event_id = props.get("eventid")
    if not event_id or event_type_code not in TYPE_MAP:
        return None

    severity = props.get("severitydata") or {}
    detail_url = None
    url_value = props.get("url")
    if isinstance(url_value, dict):
        detail_url = url_value.get("report") or url_value.get("details")
    elif isinstance(url_value, str):
        detail_url = url_value

    return {
        "event_id": f"GDACS-{event_type_code}-{event_id}",
        "provider_event_id": str(event_id),
        "source": "GDACS",
        "event_type": TYPE_MAP[event_type_code],
        "event_type_code": event_type_code,
        "title": props.get("name") or props.get("eventname") or props.get("description"),
        "alert_level": props.get("alertlevel"),
        "alert_score": props.get("alertscore"),
        "severity_value": severity.get("severity"),
        "severity_unit": severity.get("severityunit"),
        "severity_text": severity.get("severitytext"),
        "country": props.get("country"),
        "iso3": props.get("iso3"),
        "occurred_at_iso": props.get("fromdate"),
        "is_current": str(props.get("iscurrent", "")).lower() == "true",
        "longitude": float(coords[0]),
        "latitude": float(coords[1]),
        "detail_url": detail_url,
        "raw_json": feature,
    }
