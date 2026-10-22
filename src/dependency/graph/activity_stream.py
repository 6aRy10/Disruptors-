"""Read-only sourced event activity for HERMES.

The first receipt is the external.events transactional outbox creation time.
Re-polling the same provider event does NOT create new activity. Ingestion time
is not a verified collector heartbeat. Kafka broker status stays unknown.
"""
from __future__ import annotations
from datetime import datetime, timezone
from dependency.db.connection import connect

STREAM_SQL = """
SELECT o.outbox_id,e.event_id,e.source,e.event_type,e.title,e.mode,
       e.occurred_or_effective_at,o.created_at,e.source_url,
       e.provenance_class,c.status,c.processed_at,
       i.incident_id,i.status,i.open_evidence_tasks
FROM event_outbox o
JOIN external_events e ON e.event_id=o.event_key
LEFT JOIN LATERAL (
  SELECT status,processed_at FROM event_consumptions
  WHERE outbox_id=o.outbox_id AND consumer_name='incident-orchestrator'
  LIMIT 1
) c ON true
LEFT JOIN LATERAL (
  SELECT incidents.incident_id,incidents.status,
         (SELECT COUNT(*) FROM incident_investigation_tasks t
          WHERE t.incident_id=incidents.incident_id AND t.status='OPEN') AS open_evidence_tasks
  FROM incidents WHERE incidents.event_id=e.event_id
  ORDER BY incidents.detected_at DESC,incidents.incident_id LIMIT 1
) i ON true
WHERE o.topic='external.events'
  AND (%s::timestamptz IS NULL OR o.created_at >= %s::timestamptz)
  AND (%s::text IS NULL OR upper(e.source)=upper(%s::text))
ORDER BY o.created_at DESC,o.outbox_id DESC LIMIT %s
"""
SOURCE_SQL = """
SELECT source,COUNT(*),MAX(ingested_at),MAX(occurred_or_effective_at)
FROM external_events WHERE mode='LIVE'
GROUP BY source ORDER BY source
"""
QUEUE_SQL = """
SELECT COUNT(*) FILTER (WHERE NOT EXISTS (
  SELECT 1 FROM event_consumptions c WHERE c.outbox_id=o.outbox_id
    AND c.consumer_name='incident-orchestrator' AND c.status='SUCCESS'
)),
COUNT(*) FILTER (WHERE o.published_at IS NULL)
FROM event_outbox o
"""

def read_activity(*, limit: int = 80, since: datetime | None = None,
                  source: str | None = None) -> dict:
    if not 1 <= limit <= 200:
        raise ValueError('limit must be between 1 and 200')
    if source is not None and (not source.strip() or len(source) > 80):
        raise ValueError('source must be a nonempty name under 80 characters')
    if since is not None and since.tzinfo is None:
        raise ValueError('since must include a timezone')
    with connect() as conn:
        rows=conn.execute(STREAM_SQL,(since,since,source,source,limit)).fetchall()
        sources=conn.execute(SOURCE_SQL).fetchall()
        queue=conn.execute(QUEUE_SQL).fetchone()
        present=conn.execute("SELECT to_regclass(%s)",("public.collector_checks",)).fetchone()
        checks=(conn.execute("""
            SELECT DISTINCT ON (source) source,checked_at,status,
                   received_count,created_count,error_type
            FROM collector_checks ORDER BY source,checked_at DESC,check_id DESC
        """).fetchall() if present and present[0] is not None else [])
    check_by_source={row[0]:row for row in checks}
    now=datetime.now(timezone.utc)
    # PortWatch's public source attribution differs from its worker name.
    def source_key(label: str) -> str:
        return "PORTWATCH" if label.strip().lower() in {
            "imf portwatch", "portwatch"
        } else label
    source_by_name={source_key(row[0]):row for row in sources}
    names=sorted(set(source_by_name)|set(check_by_source)|{"USGS","GDACS","PORTWATCH"})
    source_view=[]
    for name in names:
        stored=source_by_name.get(name)
        checked=check_by_source.get(name)
        age_seconds=(now-checked[1]).total_seconds() if checked and checked[1] else None
        threshold={"USGS":300,"GDACS":1200,"PORTWATCH":10800}.get(name,1200)
        if not checked:
            poll_status="NOT_VERIFIED"
        elif age_seconds is None or age_seconds>threshold:
            poll_status="STALE"
        elif checked[2]=="ERROR":
            poll_status="RECENT_ERROR"
        else:
            poll_status="RECENT_SUCCESS"
        source_view.append({
            "source":"IMF PortWatch" if name=="PORTWATCH" else name,
            "stored_report_count":int(stored[1]) if stored else 0,
            "last_database_ingestion_at":stored[2].isoformat() if stored and stored[2] else None,
            "last_source_event_at":stored[3].isoformat() if stored and stored[3] else None,
            "collector_status":poll_status,
            "last_poll_at":checked[1].isoformat() if checked and checked[1] else None,
            "last_poll_received_count":int(checked[3]) if checked else None,
            "last_poll_created_count":int(checked[4]) if checked else None,
            "last_poll_error_type":checked[5] if checked else None,
        })
    entries=[{
        'entry_id':r[0], 'event_id':r[1], 'source':r[2], 'event_type':r[3],
        'title':r[4], 'mode':r[5],
        'occurred_at':r[6].isoformat() if r[6] else None,
        'first_recorded_at':r[7].isoformat() if r[7] else None,
        'source_url':r[8], 'provenance_class':r[9],
        'local_processing':r[10] or 'PENDING',
        'processed_at':r[11].isoformat() if r[11] else None,
        'incident_id':r[12], 'incident_status':r[13],
        'open_evidence_tasks':int(r[14] or 0),
        'signal_class':'SOURCE_OBSERVATION',
    } for r in rows]
    return {
        'server_time':now.isoformat(),
        'entries':entries,'returned_count':len(entries),'limit':limit,
        'sources':source_view,
        'processing':{
            'pending_local_outbox_messages':int(queue[0] or 0),
            'unpublished_kafka_outbox_messages':int(queue[1] or 0),
            'kafka_broker_status':'NOT_VERIFIED',
        },
        'refresh_contract':'HTTP_POLL_READ_ONLY',
        'freshness_rule':(
            'first_recorded_at is outbox creation, not the hazard date. '
            'Repeat source polls do not create another entry. Source poll status '
            'is backed by collector_checks; missing or stale polls are not called live.'
        ),
    }
