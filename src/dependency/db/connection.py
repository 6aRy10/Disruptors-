from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    url = os.getenv("DATABASE_URL") or os.getenv("AIVEN_DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL (local) or AIVEN_DATABASE_URL (deployment).")
    return url


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
