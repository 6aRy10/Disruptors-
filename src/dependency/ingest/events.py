from __future__ import annotations

import json
from datetime import UTC, datetime

from dependency.db.connection import connect
from dependency.events.bus import TOPIC_EXTERNAL_EVENTS, enqueue_outbox


def _parse_occurred_at(event: dict):
    occurred_ms = event.get("occurred_at_epoch_ms")
    if occurred_ms is not None:
        return datetime.fromtimestamp(float(occurred_ms) / 1000.0, tz=UTC)

    occurred_iso = event.get("occurred_at_iso")
    if occurred_iso:
        text = str(occurred_iso).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    return None


def upsert_external_event(event: dict, *, mode: str = "LIVE") -> dict:
    if event.get("provenance_class", "VERIFIED_PUBLIC") not in {
        "VERIFIED_PUBLIC", "PUBLIC_DERIVED", "INFERRED", "SIMULATED_PRIVATE"
    }:
        raise ValueError("Invalid event provenance_class")
    occurred_at = _parse_occurred_at(event)
    ingested_at = datetime.now(UTC)
    source_url = event.get("detail_url")
    title = event.get("title") or event.get("place") or event.get("event_id")

    with connect() as conn:
        existed = conn.execute(
            "SELECT 1 FROM external_events WHERE event_id = %s",
            (event["event_id"],),
        ).fetchone() is not None

        conn.execute(
            """
            INSERT INTO external_events(
              event_id,event_type,mode,source,title,occurred_or_effective_at,
              ingested_at,current_as_of,geom,raw_json,provenance_class,source_url
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,
              ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,
              %s::jsonb,%s,%s
            )
            ON CONFLICT (event_id) DO UPDATE SET
              event_type=EXCLUDED.event_type,
              mode=EXCLUDED.mode,
              source=EXCLUDED.source,
              title=EXCLUDED.title,
              occurred_or_effective_at=EXCLUDED.occurred_or_effective_at,
              ingested_at=EXCLUDED.ingested_at,
              current_as_of=EXCLUDED.current_as_of,
              geom=EXCLUDED.geom,
              raw_json=EXCLUDED.raw_json,
              provenance_class=EXCLUDED.provenance_class,
              source_url=EXCLUDED.source_url
            """,
            (
                event["event_id"], event["event_type"], mode, event["source"], title,
                occurred_at, ingested_at, ingested_at.date(),
                float(event["longitude"]), float(event["latitude"]),
                json.dumps(event.get("raw_json", event)),
                event.get("provenance_class", "VERIFIED_PUBLIC"), source_url,
            ),
        )
        if not existed:
            enqueue_outbox(
                conn,
                topic=TOPIC_EXTERNAL_EVENTS,
                event_key=event["event_id"],
                payload={
                    "event_id": event["event_id"],
                    "event_type": event["event_type"],
                    "source": event["source"],
                    "mode": mode,
                    "occurred_at": occurred_at.isoformat() if occurred_at else None,
                    "latitude": float(event["latitude"]),
                    "longitude": float(event["longitude"]),
                    "provenance_class": "VERIFIED_PUBLIC",
                },
            )

        conn.commit()

    return {
        "event_id": event["event_id"],
        "created": not existed,
        "mode": mode,
        "occurred_at": occurred_at.isoformat() if occurred_at else None,
        "ingested_at": ingested_at.isoformat(),
    }


def list_recent_events(limit: int = 50) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT event_id,event_type,mode,source,title,occurred_or_effective_at,
                   ingested_at,current_as_of,source_url
            FROM external_events
            ORDER BY ingested_at DESC
            LIMIT %s
            """,
            (int(limit),),
        ).fetchall()

    return [
        {
            "event_id": r[0],
            "event_type": r[1],
            "mode": r[2],
            "source": r[3],
            "title": r[4],
            "occurred_or_effective_at": r[5].isoformat() if r[5] else None,
            "ingested_at": r[6].isoformat() if r[6] else None,
            "current_as_of": r[7].isoformat() if r[7] else None,
            "source_url": r[8],
        }
        for r in rows
    ]
