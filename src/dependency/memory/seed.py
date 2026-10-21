from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config"


def _rows() -> list[dict]:
    with (CONFIG / "incident_memory_seed.csv").open(
        newline="",
        encoding="utf-8-sig",
    ) as f:
        return list(csv.DictReader(f))


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def load_seed_memory(conn) -> int:
    """Load clearly-labelled simulated-private prior-run memory.

    These rows demonstrate learning from prior runs. They are not public Adidas
    incident outcomes and must never be presented as such.
    """
    rows = _rows()
    for row in rows:
        scenario_id = row.get("scenario_id") or None
        conn.execute(
            """
            INSERT INTO incidents(
              incident_id,event_id,scenario_id,event_type,status,summary,
              initial_assessment,provenance_class
            ) VALUES (%s,%s,%s,%s,'CLOSED',%s,%s,%s)
            ON CONFLICT (incident_id) DO UPDATE SET
              event_id=EXCLUDED.event_id,
              scenario_id=EXCLUDED.scenario_id,
              event_type=EXCLUDED.event_type,
              status='CLOSED',
              summary=EXCLUDED.summary,
              initial_assessment=EXCLUDED.initial_assessment,
              provenance_class=EXCLUDED.provenance_class,
              updated_at=now()
            """,
            (
                row["incident_id"],
                row["event_id"],
                scenario_id,
                row["event_type"],
                row["summary"],
                row["initial_assessment"],
                row["provenance_class"],
            ),
        )
        conn.execute(
            """
            INSERT INTO incident_outcomes(
              incident_id,actual_supplier_delay_days,actual_shortage_units,
              actual_cost_eur,customer_impact_json,success,lesson
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)
            ON CONFLICT (incident_id) DO UPDATE SET
              actual_supplier_delay_days=EXCLUDED.actual_supplier_delay_days,
              actual_shortage_units=EXCLUDED.actual_shortage_units,
              actual_cost_eur=EXCLUDED.actual_cost_eur,
              customer_impact_json=EXCLUDED.customer_impact_json,
              success=EXCLUDED.success,
              lesson=EXCLUDED.lesson,
              updated_at=now()
            """,
            (
                row["incident_id"],
                _optional_float(row.get("actual_supplier_delay_days")),
                _optional_float(row.get("actual_shortage_units")),
                _optional_float(row.get("actual_cost_eur")),
                json.dumps(
                    json.loads(row.get("customer_impact_json") or "{}")
                ),
                _bool(row.get("success")),
                row["lesson"],
            ),
        )
    return len(rows)
