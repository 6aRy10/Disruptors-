"""Container HEALTHCHECK entrypoint. Exit 0 = healthy, 1 = unhealthy.

Usage: python scripts/healthcheck.py {api|publisher|consumer}

* api       -> GET http://127.0.0.1:$PORT/health/ready must return 200.
* publisher -> heartbeat file is fresh (worker loop is ticking).
* consumer  -> heartbeat file is fresh (poll loop is ticking).

No secrets are printed; output is a one-line JSON status.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request


def check_api() -> dict:
    port = os.getenv("PORT", "8000")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/ready", timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return {"healthy": resp.status == 200, "status": body.get("status")}
    except Exception as exc:
        return {"healthy": False, "error_type": type(exc).__name__}


def check_worker() -> dict:
    from dependency.events.health import heartbeat_status

    status = heartbeat_status(os.getenv("HERMES_HEARTBEAT_FILE"))
    return {"healthy": status["status"] == "FRESH", **status}


def main(role: str) -> int:
    result = check_api() if role == "api" else check_worker()
    print(json.dumps({"role": role, **result}))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"api", "publisher", "consumer"}:
        raise SystemExit(__doc__)
    raise SystemExit(main(sys.argv[1]))
