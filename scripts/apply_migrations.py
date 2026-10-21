"""Non-destructive migration for the live investigation task queue."""
from __future__ import annotations

from pathlib import Path

from dependency.db.connection import connect

MIGRATION = Path(__file__).resolve().parents[1] / "sql" / "migrations" / "001_investigation_tasks.sql"


def apply_migrations() -> None:
    with connect() as conn:
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        conn.commit()


if __name__ == "__main__":
    apply_migrations()
    print("Investigation task schema is ready. Existing operational records were preserved.")
