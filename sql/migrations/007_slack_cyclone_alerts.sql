-- Alert delivery ledger for a source-backed cyclone investigation.
-- Additive only; prevents replay/poll duplicates from spamming Slack.
CREATE TABLE IF NOT EXISTS slack_cyclone_alert_deliveries (
  event_id text PRIMARY KEY REFERENCES external_events(event_id),
  status text NOT NULL CHECK (status IN ('SENDING','SENT','FAILED')),
  attempts integer NOT NULL DEFAULT 0,
  claimed_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  last_error_type text
);
CREATE INDEX IF NOT EXISTS slack_cyclone_alert_status_idx
  ON slack_cyclone_alert_deliveries(status, claimed_at);
