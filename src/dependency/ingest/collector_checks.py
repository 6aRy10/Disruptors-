"""Durable per-source poll receipts. Never use an event update as a heartbeat."""
from __future__ import annotations
from dependency.db.connection import connect

SOURCES = frozenset({"USGS","GDACS","PORTWATCH"})

def record_collector_check(*, source: str, status: str, received_count: int = 0,
                           created_count: int = 0, error_type: str | None = None) -> bool:
    """Best-effort metadata write, independent of event ingestion.

    A failed metrics write does not stop the feed. Old databases without the
    additive migration continue collecting; UI reports unverified source state.
    """
    if source not in SOURCES or status not in {"OK","ERROR"}:
        raise ValueError("Unsupported collector check")
    if received_count < 0 or created_count < 0:
        raise ValueError("Counts must be nonnegative")
    with connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s)", ("public.collector_checks",)).fetchone()
        if not exists or exists[0] is None:
            return False
        conn.execute("""
            INSERT INTO collector_checks(source,status,received_count,created_count,error_type)
            VALUES (%s,%s,%s,%s,%s)
        """, (source,status,int(received_count),int(created_count),
              (error_type or "UnknownError") if status=="ERROR" else None))
        conn.commit()
    return True
