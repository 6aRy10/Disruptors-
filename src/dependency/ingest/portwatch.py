from __future__ import annotations

import json
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


def _get_json(base: str, params: dict) -> dict:
    url = f"{base}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "disruptors-hackathon/0.2"})
    with urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def search_ports(name: str) -> list[dict]:
    safe = name.replace("'", "''").upper()
    payload = _get_json(
        PORTS_REF,
        {
            "where": f"UPPER(portname) LIKE '%{safe}%' OR UPPER(fullname) LIKE '%{safe}%'",
            "outFields": "portid,portname,fullname,country,ISO3,lat,lon,LOCODE",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 100,
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
    pct_change = None if baseline == 0 else ((latest_calls - baseline) / baseline) * 100.0

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
        "pct_change_vs_baseline": round(pct_change, 1) if pct_change is not None else None,
        "status": status,
        "observations": len(rows),
        "source": "IMF PortWatch",
    }
