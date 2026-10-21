-- A request draft is not a sent message and not confirmed supplier evidence.
CREATE TABLE IF NOT EXISTS investigation_outreach_drafts (
  draft_id text PRIMARY KEY,
  task_id text NOT NULL UNIQUE REFERENCES incident_investigation_tasks(task_id)
    ON DELETE CASCADE,
  contact_id text REFERENCES operational_contacts(contact_id),
  status text NOT NULL CHECK (status IN (
    'CONTACT_NOT_MODELED','REVIEW_REQUIRED','EVIDENCE_RECORDED'
  )),
  message_text text NOT NULL,
  provenance_class text NOT NULL DEFAULT 'INFERRED'
    CHECK (provenance_class='INFERRED'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS investigation_outreach_status_idx
  ON investigation_outreach_drafts(status, updated_at DESC);
