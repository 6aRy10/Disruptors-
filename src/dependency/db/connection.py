from __future__ import annotations

import os
from contextlib import contextmanager
from urllib.parse import urlsplit

import psycopg
from dotenv import load_dotenv

load_dotenv()


def database_target() -> str:
    """Explicitly select the operational database; never silently switch twins."""
    local = bool(os.getenv("DATABASE_URL"))
    aiven = bool(os.getenv("AIVEN_DATABASE_URL"))
    requested = os.getenv("DEPENDENCY_DATABASE_TARGET", "").strip().lower()
    if requested and requested not in {"local", "aiven"}:
        raise ValueError("DEPENDENCY_DATABASE_TARGET must be local or aiven.")
    if requested:
        return requested
    if local and aiven:
        raise RuntimeError(
            "Both database URLs are set. Set DEPENDENCY_DATABASE_TARGET=local "
            "or DEPENDENCY_DATABASE_TARGET=aiven explicitly."
        )
    if local:
        return "local"
    if aiven:
        return "aiven"
    raise RuntimeError("Set DATABASE_URL for local PostgreSQL or AIVEN_DATABASE_URL for Aiven.")


def database_url() -> str:
    target = database_target()
    key = "AIVEN_DATABASE_URL" if target == "aiven" else "DATABASE_URL"
    url = os.getenv(key)
    if not url and target == "aiven" and _is_aiven_runtime_injected_url(os.getenv("DATABASE_URL")):
        # Aiven Runtime service integrations inject the managed PostgreSQL URI
        # as DATABASE_URL. Accept it only when the operator explicitly selected
        # the aiven target and no AIVEN_DATABASE_URL overrides it.
        url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(f"Selected {target} database has no configured URL.")
    return url


def _is_aiven_runtime_injected_url(url: str | None) -> bool:
    """A managed Aiven URI, never a localhost/dev URL mistaken for the twin."""
    if not url:
        return False
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return bool(host) and host.endswith(".aivencloud.com")


@contextmanager
def connect():
    conn = psycopg.connect(database_url())
    try:
        yield conn
    finally:
        conn.close()


def postgis_version() -> str:
    with connect() as conn:
        row = conn.execute("SELECT PostGIS_Version()").fetchone()
        return row[0]
