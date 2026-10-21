"""Prepare reviewable evidence requests from graph-linked incident tasks.

No automatic email, Slack dispatch, or factory-state change. Contacts are
selected only from explicit private operational contact records.
"""
from __future__ import annotations

from uuid import uuid4
from dependency.db.connection import connect


def build_evidence_question(
    *,
    task_type: str,
    target_id: str,
    required_fact: str,
    event_id: str,
    event_title: str,
    skus: list[str],
) -> str:
    """The supplier receives a question, never a fabricated shutdown claim."""
    if not required_fact.strip() or not target_id.strip():
        raise ValueError("Missing required evidence details.")
    products=", ".join(skus[:12]) if skus else "unverified linked products"
    return (
        f"Subject: Supply continuity verification — {event_id}\n\n"
        f"Our monitoring recorded the event '{event_title}' ({event_id}). "
        "A public event or derived activity signal does not prove that your "
        "facility, route or material supply is disrupted.\n\n"
        f"Please verify: {required_fact}\n"
        f"Reference: {task_type} / {target_id}\n"
        f"Private dependency references: {products}\n\n"
        "Please provide the effective date, available quantity or operating "
        "status, expected recovery time, and a verifiable reference. "
        "Our planner will review the reply before changing any orders or capacity."
    )


def prepare_investigation_outreach(*, task_id: str) -> dict:
    """Idempotently create a contact-bound draft. Never sends anything."""
    with connect() as conn:
        row=conn.execute(
            """
            SELECT t.task_id,t.task_type,t.target_type,t.target_id,
                   t.required_fact,t.connected_skus,t.status,
                   e.event_id,e.title
            FROM incident_investigation_tasks t
            JOIN incidents i ON i.incident_id=t.incident_id
            JOIN external_events e ON e.event_id=i.event_id
            WHERE t.task_id=%s FOR UPDATE OF t
            """,
            (task_id,),
        ).fetchone()
        if not row:
            raise ValueError("Unknown investigation task.")
        task_id,task_type,target_type,target_id,fact,skus,status,event_id,title=row
        if status!="OPEN":
            raise ValueError("Outreach drafts require an OPEN evidence task.")
        facility=None
        if target_type=="facility":
            facility=target_id
        elif target_type=="facility_material":
            facility=target_id.split(":",1)[0]
        contact=None
        if facility:
            contact=conn.execute(
                """
                SELECT contact_id,name,channel,address,provenance_class
                FROM operational_contacts
                WHERE entity_type='supplier_facility' AND entity_id=%s
                  AND can_confirm_operational_data=true
                ORDER BY contact_id
                LIMIT 1
                """,
                (facility,),
            ).fetchone()
        # Even a modeled, authorized contact is not permission to dispatch.
        new_status="REVIEW_REQUIRED" if contact else "CONTACT_NOT_MODELED"
        message=build_evidence_question(
            task_type=task_type,target_id=target_id,required_fact=fact,
            event_id=event_id,event_title=title,skus=skus or [],
        )
        draft_id=f"DRAFT-INV-{uuid4()}"
        saved=conn.execute(
            """
            INSERT INTO investigation_outreach_drafts(
              draft_id,task_id,contact_id,status,message_text
            ) VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (task_id) DO UPDATE SET
              contact_id=EXCLUDED.contact_id,
              status=EXCLUDED.status,
              message_text=EXCLUDED.message_text,
              updated_at=now()
            WHERE investigation_outreach_drafts.status != 'EVIDENCE_RECORDED'
            RETURNING draft_id,contact_id,status,message_text
            """,
            (draft_id,task_id,contact[0] if contact else None,new_status,message),
        ).fetchone()
        if not saved:
            raise ValueError("Task outreach was already completed.")
        conn.commit()

    return {
        "draft_id":saved[0],"task_id":task_id,"status":saved[2],
        "contact_id":saved[1],
        "recipient_name":contact[1] if contact else None,
        "channel":contact[2] if contact else None,
        "address":contact[3] if contact else None,
        "contact_provenance":contact[4] if contact else None,
        "message_text":saved[3],
        "dispatched":False,
        "next_action":"HUMAN_REVIEW_CONTACT_AND_SEND_THROUGH_AUTHORIZED_WORKFLOW",
        "provenance_class":"INFERRED",
    }
