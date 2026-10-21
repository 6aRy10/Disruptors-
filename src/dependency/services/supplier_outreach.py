from __future__ import annotations

import json
import os
from uuid import uuid4

from dependency.db.connection import connect
from dependency.events.bus import (
    TOPIC_SUPPLIER_CONFIRMATION_REPLY,
    TOPIC_SUPPLIER_CONFIRMATION_REQUESTED,
    enqueue_outbox,
)
from dependency.notifications.slack import post_message, supplier_capacity_request
from dependency.services.capacity import confirm_supplier_capacity
from dependency.supplier_confirmations import parse_supplier_reply


ACTIVE_REQUEST_STATUSES = {
    "PENDING_DISPATCH",
    "SENT",
    "REPLY_RECEIVED",
    "PARSE_FAILED",
}


def create_capacity_confirmation_request(
    *,
    facility_id: str,
    sku: str,
    incident_id: str | None = None,
    scenario_id: str | None = None,
    recipient_contact_id: str | None = None,
) -> dict:
    """Create one data-driven supplier capacity confirmation request.

    The request is durable. Creating it never changes supplier capacity.
    """
    with connect() as conn:
        facility = conn.execute(
            "SELECT name FROM facilities WHERE facility_id=%s",
            (facility_id,),
        ).fetchone()
        if not facility:
            raise ValueError(f"Unknown facility_id: {facility_id}")

        capacity = conn.execute(
            """
            SELECT capacity_units,committed_units,evidence_age_hours,source,week_start
            FROM supplier_capacity
            WHERE facility_id=%s AND sku=%s
            ORDER BY week_start DESC
            LIMIT 1
            """,
            (facility_id, sku),
        ).fetchone()
        if not capacity:
            raise ValueError(
                f"No supplier capacity row for facility={facility_id} sku={sku}"
            )

        if incident_id:
            incident = conn.execute(
                "SELECT 1 FROM incidents WHERE incident_id=%s",
                (incident_id,),
            ).fetchone()
            if not incident:
                raise ValueError(f"Unknown incident_id: {incident_id}")

        if scenario_id:
            scenario = conn.execute(
                "SELECT 1 FROM scenarios WHERE scenario_id=%s",
                (scenario_id,),
            ).fetchone()
            if not scenario:
                raise ValueError(f"Unknown scenario_id: {scenario_id}")

        contact = None
        if recipient_contact_id:
            contact = conn.execute(
                """
                SELECT contact_id,name,channel,address,can_confirm_operational_data
                FROM operational_contacts
                WHERE contact_id=%s
                """,
                (recipient_contact_id,),
            ).fetchone()
            if not contact:
                raise ValueError(
                    f"Unknown recipient_contact_id: {recipient_contact_id}"
                )
            if not bool(contact[4]):
                raise ValueError(
                    f"Contact {recipient_contact_id} is not authorized to confirm "
                    "operational data."
                )
        else:
            contact = conn.execute(
                """
                SELECT contact_id,name,channel,address,can_confirm_operational_data
                FROM operational_contacts
                WHERE entity_type='supplier_facility'
                  AND entity_id=%s
                  AND can_confirm_operational_data=true
                ORDER BY contact_id
                LIMIT 1
                """,
                (facility_id,),
            ).fetchone()

        current_capacity = int(float(capacity[0]))
        message = supplier_capacity_request(
            sku=sku,
            current_capacity=current_capacity,
            facility_name=facility[0],
        )["text"]

        request_id = f"REQ-CAP-{uuid4()}"
        status = "PENDING_DISPATCH" if contact else "DRAFT"
        contact_id = contact[0] if contact else None

        system_value = {
            "capacity_units": float(capacity[0]),
            "committed_units": float(capacity[1]),
            "available_capacity_units": max(
                0.0,
                float(capacity[0]) - float(capacity[1]),
            ),
            "evidence_age_hours": float(capacity[2] or 0),
            "source": capacity[3],
            "week_start": capacity[4].isoformat(),
        }

        conn.execute(
            """
            INSERT INTO supplier_confirmation_requests(
              request_id,incident_id,scenario_id,facility_id,sku,field_requested,
              system_value_json,recipient_contact_id,message_text,status,
              provenance_class
            ) VALUES (
              %s,%s,%s,%s,%s,'weekly_capacity_units',%s::jsonb,%s,%s,%s,
              'SIMULATED_PRIVATE'
            )
            """,
            (
                request_id,
                incident_id,
                scenario_id,
                facility_id,
                sku,
                json.dumps(system_value),
                contact_id,
                message,
                status,
            ),
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_SUPPLIER_CONFIRMATION_REQUESTED,
            event_key=request_id,
            payload={
                "request_id": request_id,
                "incident_id": incident_id,
                "scenario_id": scenario_id,
                "facility_id": facility_id,
                "sku": sku,
                "field_requested": "weekly_capacity_units",
                "system_value": system_value,
                "recipient_contact_id": contact_id,
                "status": status,
            },
        )
        conn.commit()

    return {
        "request_id": request_id,
        "incident_id": incident_id,
        "scenario_id": scenario_id,
        "facility_id": facility_id,
        "facility_name": facility[0],
        "sku": sku,
        "field_requested": "weekly_capacity_units",
        "system_value": system_value,
        "recipient_contact_id": contact_id,
        "message_text": message,
        "status": status,
    }


def get_confirmation_request(request_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              r.request_id,r.incident_id,r.scenario_id,r.facility_id,f.name,
              r.sku,r.field_requested,r.system_value_json,
              r.recipient_contact_id,c.name,c.channel,c.address,
              r.message_text,r.status,r.external_channel_id,
              r.external_thread_ts,r.requested_at,r.sent_at,r.replied_at,
              r.confirmed_at,r.last_error,r.provenance_class
            FROM supplier_confirmation_requests r
            JOIN facilities f ON f.facility_id=r.facility_id
            LEFT JOIN operational_contacts c
              ON c.contact_id=r.recipient_contact_id
            WHERE r.request_id=%s
            """,
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown supplier confirmation request: {request_id}")

        replies = conn.execute(
            """
            SELECT
              reply_id,sender_external_id,source_message_id,raw_message,
              parsed_json,parse_ok,supplier_confirmed,received_at,applied_at
            FROM supplier_confirmation_replies
            WHERE request_id=%s
            ORDER BY received_at,reply_id
            """,
            (request_id,),
        ).fetchall()

    return {
        "request_id": row[0],
        "incident_id": row[1],
        "scenario_id": row[2],
        "facility_id": row[3],
        "facility_name": row[4],
        "sku": row[5],
        "field_requested": row[6],
        "system_value": row[7],
        "recipient_contact_id": row[8],
        "recipient_name": row[9],
        "channel": row[10],
        "address": row[11],
        "message_text": row[12],
        "status": row[13],
        "external_channel_id": row[14],
        "external_thread_ts": row[15],
        "requested_at": row[16].isoformat(),
        "sent_at": row[17].isoformat() if row[17] else None,
        "replied_at": row[18].isoformat() if row[18] else None,
        "confirmed_at": row[19].isoformat() if row[19] else None,
        "last_error": row[20],
        "provenance_class": row[21],
        "replies": [
            {
                "reply_id": r[0],
                "sender_external_id": r[1],
                "source_message_id": r[2],
                "raw_message": r[3],
                "parsed": r[4],
                "parse_ok": bool(r[5]),
                "supplier_confirmed": bool(r[6]),
                "received_at": r[7].isoformat(),
                "applied_at": r[8].isoformat() if r[8] else None,
            }
            for r in replies
        ],
    }


def dispatch_confirmation_request(
    *,
    request_id: str,
    allow_external: bool | None = None,
) -> dict:
    """Send a pending request through Slack when external messaging is enabled."""
    request = get_confirmation_request(request_id)

    enabled = (
        str(os.getenv("DEPENDENCY_ALLOW_EXTERNAL_MESSAGES", "")).lower()
        in {"1", "true", "yes"}
        if allow_external is None
        else bool(allow_external)
    )
    if not enabled:
        return {
            "request_id": request_id,
            "status": request["status"],
            "dispatched": False,
            "reason": "EXTERNAL_MESSAGES_DISABLED",
        }

    if request["channel"] not in {"Slack", "Slack Connect"}:
        raise ValueError(
            f"Unsupported confirmation channel: {request['channel']}"
        )
    if not request["address"]:
        raise ValueError("Confirmation request has no Slack address.")

    try:
        result = post_message(
            address=request["address"],
            text=request["message_text"],
        )
    except Exception as exc:
        with connect() as conn:
            conn.execute(
                """
                UPDATE supplier_confirmation_requests
                SET status='FAILED',last_error=%s
                WHERE request_id=%s
                """,
                (f"{type(exc).__name__}: {exc}", request_id),
            )
            conn.commit()
        raise

    with connect() as conn:
        conn.execute(
            """
            UPDATE supplier_confirmation_requests
            SET status='SENT',
                external_channel_id=%s,
                external_thread_ts=%s,
                sent_at=now(),
                last_error=NULL
            WHERE request_id=%s
            """,
            (result["channel_id"], result["ts"], request_id),
        )
        conn.commit()

    return {
        "request_id": request_id,
        "status": "SENT",
        "dispatched": True,
        "external_channel_id": result["channel_id"],
        "external_thread_ts": result["ts"],
    }


def record_confirmation_reply(
    *,
    request_id: str,
    raw_message: str,
    sender_external_id: str | None = None,
    source_message_id: str | None = None,
) -> dict:
    """Store and parse a supplier reply without changing operational state."""
    request = get_confirmation_request(request_id)
    if request["status"] in {"CONFIRMED", "REJECTED"}:
        raise ValueError(
            f"Supplier request {request_id} is already closed with "
            f"status={request['status']}"
        )

    parsed = parse_supplier_reply(raw_message)
    reply_id = f"RESP-CAP-{uuid4()}"
    new_status = "REPLY_RECEIVED" if parsed.get("ok") else "PARSE_FAILED"

    with connect() as conn:
        if source_message_id:
            existing = conn.execute(
                """
                SELECT reply_id
                FROM supplier_confirmation_replies
                WHERE source_message_id=%s
                """,
                (source_message_id,),
            ).fetchone()
            if existing:
                return {
                    "reply_id": existing[0],
                    "request_id": request_id,
                    "duplicate": True,
                    "parsed": parsed,
                }

        conn.execute(
            """
            INSERT INTO supplier_confirmation_replies(
              reply_id,request_id,sender_external_id,source_message_id,
              raw_message,parsed_json,parse_ok,supplier_confirmed
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,false)
            """,
            (
                reply_id,
                request_id,
                sender_external_id,
                source_message_id,
                raw_message,
                json.dumps(parsed),
                bool(parsed.get("ok")),
            ),
        )
        conn.execute(
            """
            UPDATE supplier_confirmation_requests
            SET status=%s,replied_at=now(),last_error=NULL
            WHERE request_id=%s
            """,
            (new_status, request_id),
        )
        enqueue_outbox(
            conn,
            topic=TOPIC_SUPPLIER_CONFIRMATION_REPLY,
            event_key=request_id,
            payload={
                "request_id": request_id,
                "reply_id": reply_id,
                "facility_id": request["facility_id"],
                "sku": request["sku"],
                "parse_ok": bool(parsed.get("ok")),
                "parsed": parsed,
                "status": new_status,
            },
        )
        conn.commit()

    return {
        "reply_id": reply_id,
        "request_id": request_id,
        "duplicate": False,
        "status": new_status,
        "parsed": parsed,
        "requires_confirmation": bool(parsed.get("ok")),
    }


def record_slack_reply(
    *,
    channel_id: str,
    thread_ts: str | None,
    raw_message: str,
    sender_external_id: str | None,
    source_message_id: str | None,
) -> dict:
    """Map one Slack message to a pending confirmation request."""
    with connect() as conn:
        if thread_ts:
            rows = conn.execute(
                """
                SELECT request_id
                FROM supplier_confirmation_requests
                WHERE external_channel_id=%s
                  AND external_thread_ts=%s
                  AND status IN ('SENT','REPLY_RECEIVED','PARSE_FAILED')
                ORDER BY sent_at DESC,requested_at DESC
                LIMIT 2
                """,
                (channel_id, thread_ts),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT request_id
                FROM supplier_confirmation_requests
                WHERE external_channel_id=%s
                  AND status IN ('SENT','REPLY_RECEIVED','PARSE_FAILED')
                ORDER BY sent_at DESC,requested_at DESC
                LIMIT 2
                """,
                (channel_id,),
            ).fetchall()

    if not rows:
        return {
            "matched": False,
            "reason": "NO_ACTIVE_CONFIRMATION_REQUEST",
        }
    if len(rows) > 1 and not thread_ts:
        return {
            "matched": False,
            "reason": "AMBIGUOUS_UNTHREADED_REPLY",
        }

    request_id = rows[0][0]
    result = record_confirmation_reply(
        request_id=request_id,
        raw_message=raw_message,
        sender_external_id=sender_external_id,
        source_message_id=source_message_id,
    )
    return {
        "matched": True,
        **result,
    }


def confirm_supplier_reply(
    *,
    request_id: str,
    reply_id: str | None = None,
    confirmed_by: str,
) -> dict:
    """Apply a parsed supplier reply only after explicit confirmation."""
    request = get_confirmation_request(request_id)

    with connect() as conn:
        if reply_id:
            reply = conn.execute(
                """
                SELECT reply_id,raw_message,parsed_json,parse_ok
                FROM supplier_confirmation_replies
                WHERE request_id=%s AND reply_id=%s
                """,
                (request_id, reply_id),
            ).fetchone()
        else:
            reply = conn.execute(
                """
                SELECT reply_id,raw_message,parsed_json,parse_ok
                FROM supplier_confirmation_replies
                WHERE request_id=%s
                ORDER BY received_at DESC,reply_id DESC
                LIMIT 1
                """,
                (request_id,),
            ).fetchone()

    if not reply:
        raise ValueError(f"No supplier reply exists for request {request_id}")
    if not bool(reply[3]):
        raise ValueError("Latest supplier reply could not be parsed.")

    parsed = reply[2] or {}
    if not parsed.get("ok"):
        raise ValueError("Parsed supplier reply is not valid.")
    capacity_units = int(parsed["capacity_units"])

    update = confirm_supplier_capacity(
        facility_id=request["facility_id"],
        sku=request["sku"],
        capacity_units=capacity_units,
        valid_until=parsed.get("effective_until"),
        source_channel="Slack supplier confirmation",
        raw_message=reply[1],
    )

    with connect() as conn:
        conn.execute(
            """
            UPDATE supplier_confirmation_replies
            SET supplier_confirmed=true,applied_at=now()
            WHERE reply_id=%s
            """,
            (reply[0],),
        )
        conn.execute(
            """
            UPDATE supplier_confirmation_requests
            SET status='CONFIRMED',confirmed_at=now(),last_error=NULL
            WHERE request_id=%s
            """,
            (request_id,),
        )
        conn.commit()

    return {
        "request_id": request_id,
        "reply_id": reply[0],
        "confirmed_by": confirmed_by,
        "parsed": parsed,
        "capacity_update": update,
        "status": "CONFIRMED",
    }


def reject_supplier_reply(
    *,
    request_id: str,
    reason: str,
) -> dict:
    get_confirmation_request(request_id)
    with connect() as conn:
        conn.execute(
            """
            UPDATE supplier_confirmation_requests
            SET status='REJECTED',last_error=%s
            WHERE request_id=%s
            """,
            (reason, request_id),
        )
        conn.commit()
    return {
        "request_id": request_id,
        "status": "REJECTED",
        "reason": reason,
    }
