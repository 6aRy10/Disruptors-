"""Non-destructive migration for the live investigation task queue."""
from __future__ import annotations

from pathlib import Path

from dependency.db.connection import connect

MIGRATIONS = Path(__file__).resolve().parents[1] / "sql" / "migrations"


def apply_migrations() -> None:
    """Apply all additive schema upgrades in filename order, idempotently."""
    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files:
        raise RuntimeError("No SQL migration files found.")
    with connect() as conn:
        for path in files:
            conn.execute(path.read_text(encoding="utf-8"))
        conn.commit()


if __name__ == "__main__":
    apply_migrations()
    print("Investigation task schema is ready. Existing operational records were preserved.")
