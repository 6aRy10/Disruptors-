from __future__ import annotations

import json
from datetime import UTC, datetime
from statistics import mean
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PORTS_REF = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "PortWatch_ports_database/FeatureServer/0/query"
)
DAILY_PORTS = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
    "Daily_Ports_Data/FeatureServer/0/query"
)
PORTWATCH_URL = "https://portwatch.imf.org/"


def _get_json(base: str, params: dict) -> dict:
    url = f"{base}?{urlencode(params)}"
    req = Request(
        url,
        headers={"User-Agent": "disruptors-hackathon/0.3"},
    )
    with urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def search_ports(name: str) -> list[dict]:
    safe = name.replace("'", "''").upper()
    payload = _get_json(
        PORTS_REF,
        {
            "where": (
                f"UPPER(portname) LIKE '%{safe}%' "
                f"OR UPPER(fullname) LIKE '%{safe}%'"
            ),
            "outFields": "portid,portname,fullname,country,ISO3,lat,lon,LOCODE",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 100,
        },
    )
    return [f.get("attributes", {}) for f in payload.get("features", [])]


def ports_by_unlocode(unlocode: str) -> list[dict]:
    normalized = "".join(str(unlocode or "").upper().split())
    safe = normalized.replace("'", "''")
    payload = _get_json(
        PORTS_REF,
        {
            "where": (
                "REPLACE(UPPER(LOCODE), ' ', '') "
                f"= '{safe}'"
            ),
            "outFields": "portid,portname,fullname,country,ISO3,lat,lon,LOCODE",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 20,
        },
    )
    return [f.get("attributes", {}) for f in payload.get("features", [])]


def recent_activity(portid: str, days: int = 31) -> list[dict]:
    safe = portid.replace("'", "''")
    payload = _get_json(
        DAILY_PORTS,
        {
            "where": f"portid = '{safe}'",
            "outFields": (
                "date,portid,portname,country,ISO3,portcalls_container,"
                "portcalls_dry_bulk,portcalls_general_cargo,portcalls_roro,"
                "portcalls_tanker,export_container,export_cargo,export,import"
            ),
            "orderByFields": "date DESC",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": max(2, min(int(days), 90)),
        },
    )
    return [f.get("attributes", {}) for f in payload.get("features", [])]


def container_call_anomaly(portid: str, baseline_days: int = 30) -> dict:
    rows = recent_activity(portid, days=baseline_days + 1)
    if len(rows) < 2:
        return {
            "portid": portid,
            "status": "INSUFFICIENT_DATA",
            "observations": len(rows),
        }

    latest = rows[0]
    history = rows[1:]
    latest_calls = float(latest.get("portcalls_container") or 0)
    history_calls = [float(r.get("portcalls_container") or 0) for r in history]
    baseline = mean(history_calls) if history_calls else 0.0
    pct_change = (
        None
        if baseline == 0
        else ((latest_calls - baseline) / baseline) * 100.0
    )

    if pct_change is None:
        status = "UNKNOWN"
    elif pct_change <= -40:
        status = "SEVERE_DROP"
    elif pct_change <= -20:
        status = "MATERIAL_DROP"
    else:
        status = "WITHIN_BASELINE"

    return {
        "portid": portid,
        "portname": latest.get("portname"),
        "date": latest.get("date"),
        "latest_container_calls": latest_calls,
        "baseline_container_calls": round(baseline, 2),
        "pct_change_vs_baseline": (
            round(pct_change, 1) if pct_change is not None else None
        ),
        "status": status,
        "observations": len(rows),
        "baseline_days": len(history),
        "source": "IMF PortWatch",
    }


def _date_parts(value) -> tuple[str, dict]:
    if isinstance(value, (int, float)):
        # ArcGIS date fields normally use Unix epoch milliseconds.
        dt = datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
        return dt.date().isoformat(), {"occurred_at_epoch_ms": float(value)}

    text = str(value or "").strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.date().isoformat(), {
                "occurred_at_iso": parsed.isoformat()
            }
        except ValueError:
            pass

    return "unknown-date", {}


def normalize_anomaly_event(
    *,
    port: dict,
    anomaly: dict,
) -> dict | None:
    """Convert a material PortWatch anomaly into the common external-event form."""
    if anomaly.get("status") not in {"MATERIAL_DROP", "SEVERE_DROP"}:
        return None

    lat = port.get("lat")
    lon = port.get("lon")
    if lat is None or lon is None:
        return None

    locode = "".join(str(port.get("LOCODE") or "").upper().split())
    if not locode:
        return None

    date_key, occurred = _date_parts(anomaly.get("date"))
    portid = str(port.get("portid") or anomaly.get("portid") or "unknown")
    port_name = port.get("portname") or anomaly.get("portname") or locode

    raw = {
        **anomaly,
        "portid": portid,
        "port_unlocode": locode,
        "port_name": port_name,
        "country": port.get("country"),
        "iso3": port.get("ISO3"),
        "signal_method": (
            "Latest daily container port calls compared with the preceding "
            f"{anomaly.get('baseline_days', 0)} observations."
        ),
        "claim_rule": (
            "A material port-call drop is an external logistics signal. "
            "Business exposure requires an explicit private transport lane."
        ),
    }

    return {
        "event_id": f"PORTWATCH-{portid}-{date_key}",
        "event_type": "port_activity_anomaly",
        "source": "IMF PortWatch",
        "provenance_class": "PUBLIC_DERIVED",
        "title": (
            f"{anomaly['status']} in container port calls at {port_name}"
        ),
        "place": port_name,
        "longitude": float(lon),
        "latitude": float(lat),
        "detail_url": PORTWATCH_URL,
        "raw_json": raw,
        **occurred,
    }
