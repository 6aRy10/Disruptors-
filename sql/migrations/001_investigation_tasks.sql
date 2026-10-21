-- Live evidence gaps become durable tasks, never assumed operational damage.
CREATE TABLE IF NOT EXISTS incident_investigation_tasks (
  task_id text PRIMARY KEY,
  incident_id text NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
  task_key text NOT NULL,
  task_type text NOT NULL CHECK (task_type IN (
    'CONFIRM_FACILITY_STATUS',
    'CONFIRM_MATERIAL_SUPPLY',
    'CONFIRM_SHIPMENT_STATUS',
    'VERIFY_TARIFF_APPLICABILITY',
    'VERIFY_PUBLIC_SUPPLIER_LINK'
  )),
  target_type text NOT NULL,
  target_id text NOT NULL,
  required_fact text NOT NULL,
  connected_skus jsonb NOT NULL DEFAULT '[]'::jsonb,
  connected_margin_eur numeric NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'OPEN'
    CHECK (status IN ('OPEN','RESOLVED','CANCELLED')),
  provenance_class text NOT NULL DEFAULT 'INFERRED'
    CHECK (provenance_class = 'INFERRED'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(incident_id, task_key)
);
CREATE INDEX IF NOT EXISTS investigation_tasks_status_idx
  ON incident_investigation_tasks(status, created_at DESC);
CREATE INDEX IF NOT EXISTS investigation_tasks_incident_idx
  ON incident_investigation_tasks(incident_id, status);

