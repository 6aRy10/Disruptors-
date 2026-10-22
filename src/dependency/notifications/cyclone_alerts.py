"""Idempotent Slack cyclone *potential exposure* alert.

Runs only after the locally processed event has an incident and fresh LIVE
source occurrence. A warning does not assert landfall, loss or plant closure.
No webhook, no permission switch, no outbound message.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from dependency.db.connection import connect
from dependency.graph.event_impact import trace_business_event_impact
from dependency.notifications.slack import send_webhook


def build_cyclone_message(event: dict, impact: dict) -> dict:
    products = impact.get("products") or []
    totals = impact.get("totals") or {}
    sites = impact.get("facilities") or []
    names = [str(x.get("name") or x.get("facility_id")) for x in sites[:5]]
    title = str(event.get("title") or "Cyclone report")
    event_id = str(event["event_id"])
    model_units = float(totals.get("commitment_units") or 0)
    model_revenue = float(totals.get("revenue_eur") or 0)
    date = str(event.get("occurred_at") or "Unknown source date")
    source = str(event.get("source") or "Source not stated")
    lines = [
        ":cyclone: *HERMES | Cyclone source report — investigation*",
        "*" + title[:160] + "*",
        "Event: `" + event_id + "`  |  " + source + "  |  " + date[:25],
        "Public signal intersects our supplier investigation network. "
        "*Proximity is not a confirmed factory closure or storm landfall.*",
        "Modeled linked products: " + str(len(products)) +
        " | Potential connected commitment units: " + f"{model_units:,.0f}" +
        " | Potential modeled revenue: EUR " + f"{model_revenue:,.0f}",
        "Facility leads: " + (", ".join(names) if names else "Investigate public facility identity"),
        "What we do not know: real factory operating status, available capacity, "
        "shipment delays, and whether supply is actually disrupted.",
        "*Next action:* open incident evidence tasks, validate supplier status, "
        "then run recovery only on confirmed operational data.",
    ]
    url = str(event.get("source_url") or "")
    if url.startswith("https://"):
        lines.append("Source: " + url)
    return {
        "text": "\n".join(lines),
        "blocks": [
            {"type": "header", "text": {"type": "plain_text",
                "text": "HERMES | Cyclone investigation", "emoji": False}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": "\n".join(lines[1:6])[:2900]}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": "\n".join(lines[6:8])[:2900]}},
        ],
    }


def pending_cyclone_events(*, limit: int = 10, recent_hours: int = 72) -> list[dict]:
    """Select locally processed incidents only; exclude replay, old observations."""
    if not 1 <= limit <= 40 or not 1 <= recent_hours <= 168:
        raise ValueError("Invalid poll bounds.")
    with connect() as conn:
        rows = conn.execute("""
            SELECT DISTINCT e.event_id,e.title,e.source,
                   e.occurred_or_effective_at,e.source_url
            FROM external_events e
            JOIN incidents i ON i.event_id=e.event_id
            JOIN event_outbox o
              ON o.topic='external.events' AND o.event_key=e.event_id
            JOIN event_consumptions c
              ON c.outbox_id=o.outbox_id
             AND c.consumer_name='incident-orchestrator' AND c.status='SUCCESS'
            LEFT JOIN slack_cyclone_alert_deliveries d ON d.event_id=e.event_id
            WHERE e.event_type='tropical_cyclone'
              AND e.mode='LIVE'
              AND e.occurred_or_effective_at >= now() - (%s * interval '1 hour')
              AND e.occurred_or_effective_at <= now() + interval '2 hours'
              AND (d.event_id IS NULL
                OR (d.status='FAILED' AND d.claimed_at < now() - interval '10 minutes'))
            ORDER BY e.occurred_or_effective_at DESC,e.event_id
            LIMIT %s
        """, (recent_hours, limit)).fetchall()
    return [
        {"event_id": row[0], "title": row[1], "source": row[2],
         "occurred_at":row[3].isoformat() if row[3] else None,
         "source_url":row[4]}
        for row in rows
    ]


def notify_pending_cyclones(*, limit: int = 10, enabled: bool | None = None) -> dict:
    """Run from existing watcher after local worker. Never call Slack by default."""
    authorized = os.getenv("DEPENDENCY_ALLOW_EXTERNAL_MESSAGES") == "1"
    if enabled is False or not authorized:
        return {"status": "DISABLED", "sent": 0, "reason": "EXTERNAL_MESSAGES_DISABLED"}
    url = os.getenv("SLACK_INCIDENT_WEBHOOK_URL")
    if not url:
        return {"status": "NOT_CONFIGURED", "sent": 0,
                "reason": "SLACK_INCIDENT_WEBHOOK_URL_REQUIRED"}
    if not url.startswith("https://hooks.slack.com/services/"):
        return {"status": "NOT_CONFIGURED", "sent": 0,
                "reason": "INVALID_SLACK_WEBHOOK_HOST"}
    sent, failed = 0, 0
    for event in pending_cyclone_events(limit=limit):
        with connect() as conn:
            claimed = conn.execute("""
                INSERT INTO slack_cyclone_alert_deliveries(
                    event_id,status,attempts,claimed_at)
                VALUES (%s,'SENDING',1,now())
                ON CONFLICT (event_id) DO UPDATE SET
                    status='SENDING',
                    attempts=slack_cyclone_alert_deliveries.attempts+1,
                    claimed_at=now(),
                    last_error_type=NULL
                WHERE slack_cyclone_alert_deliveries.status='FAILED'
                  AND slack_cyclone_alert_deliveries.claimed_at
                      < now()-interval '10 minutes'
                RETURNING event_id
            """, (event["event_id"],)).fetchone()
            conn.commit()
        if not claimed:
            continue
        try:
            impact = trace_business_event_impact(
                event_id=event["event_id"],radius_km=150.0
            )
            payload = build_cyclone_message(event, impact)
            send_webhook(payload, webhook_url=url)
        except Exception as exc:
            # No URL, payload, secret or SMTP endpoint in stored errors.
            with connect() as conn:
                conn.execute("""
                    UPDATE slack_cyclone_alert_deliveries
                       SET status='FAILED',last_error_type=%s
                     WHERE event_id=%s
                """, (type(exc).__name__, event["event_id"]))
                conn.commit()
            failed += 1
        else:
            with connect() as conn:
                conn.execute("""
                    UPDATE slack_cyclone_alert_deliveries
                       SET status='SENT',sent_at=now(),last_error_type=NULL
                     WHERE event_id=%s
                """, (event["event_id"],))
                conn.commit()
            sent += 1
    return {"status": "OK" if not failed else "DEGRADED",
            "sent": sent,"failed": failed,
            "meaning": "CYCLONE_SOURCE_REPORT_POTENTIAL_EXPOSURE_ONLY"}


def cyclone_preview(*, event_id: str) -> dict:
    """Read-only operator preview, no Slack network calls."""
    with connect() as conn:
        row = conn.execute("""
            SELECT event_id,title,source,event_type,mode,
                   occurred_or_effective_at,source_url
            FROM external_events WHERE event_id=%s
        """,(event_id,)).fetchone()
    if not row:
        raise ValueError("Unknown event.")
    if row[3] != "tropical_cyclone":
        raise ValueError("Selected event is not a cyclone.")
    e = {"event_id":row[0],"title":row[1],"source":row[2],
         "occurred_at":row[5].isoformat() if row[5] else None,
         "source_url":row[6]}
    impact = trace_business_event_impact(event_id=event_id,radius_km=150)
    return {"event_id":event_id,"mode":row[4],"preview_only":True,
            "would_send":False,"payload":build_cyclone_message(e,impact)}
