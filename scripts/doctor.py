"""Read-only local setup diagnostics. Never display database credentials."""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

from dependency.db.connection import connect, database_url


def report() -> dict:
    result = {"status": "NOT_READY", "database": {}, "data": {}, "feeds": {}}
    try:
        u = urlsplit(database_url())
        result["database"] = {
            "host": u.hostname, "port": u.port or 5432,
            "name": (u.path or "").lstrip("/"),
            "source": "AIVEN_DATABASE_URL" if os.getenv("AIVEN_DATABASE_URL") else "DATABASE_URL",
            "both_urls_set": bool(os.getenv("AIVEN_DATABASE_URL") and os.getenv("DATABASE_URL")),
        }
        with connect() as conn:
            identity = conn.execute("SELECT current_database(),inet_server_addr()::text").fetchone()
            result["database"]["connected_name"] = identity[0]
            result["database"]["server_address"] = identity[1]
            queries = {
                "public_facilities": ("network_facilities", "SELECT count(*) FROM network_facilities"),
                "generated_products": ("products", "SELECT count(*) FROM products WHERE sku LIKE 'DTSKU-%'"),
                "bom_rows": ("bom", "SELECT count(*) FROM bom"),
                "material_allocations": ("material_allocations", "SELECT count(*) FROM material_allocations"),
                "commitments": ("fulfilment_commitments", "SELECT count(*) FROM fulfilment_commitments"),
            }
            missing = [
                table for table, _ in queries.values()
                if conn.execute("SELECT to_regclass(%s)", (f"public.{table}",)).fetchone()[0] is None
            ]
            result["database"]["missing_tables"] = missing
            if missing:
                result["status"] = "SCHEMA_INCOMPLETE"
                result["next_step"] = "On a disposable development database, run python scripts/load_seed_data.py"
            else:
                for label, (_, query) in queries.items():
                    result["data"][label] = int(conn.execute(query).fetchone()[0])
                result["status"] = (
                    "DATA_LOADED"
                    if result["data"]["generated_products"] >= 2500
                    and result["data"]["public_facilities"] >= 770
                    and result["data"]["material_allocations"] >= 170010
                    else "DATA_INCOMPLETE"
                )
                if result["status"] == "DATA_INCOMPLETE":
                    result["next_step"] = "On a disposable development database, run python scripts/load_seed_data.py"
    except Exception as exc:
        # Some drivers embed credentials in exceptions; never print exception text.
        result["database_error"] = type(exc).__name__

    for name, url in (
        ("USGS", "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"),
        ("GDACS", "https://www.gdacs.org/gdacsapi/api/Events/geteventlist/EVENTS4APP"),
    ):
        try:
            from urllib.request import Request, urlopen
            with urlopen(Request(url, headers={"User-Agent": "dependency-healthcheck/1.0"}), timeout=12) as response:
                payload = json.load(response)
            result["feeds"][name] = {
                "reachable": True,
                "feature_count": len(payload.get("features", [])),
                "background_worker_status": "NOT_CHECKED",
            }
        except Exception as exc:
            result["feeds"][name] = {"reachable": False, "error_type": type(exc).__name__}
    return result


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
