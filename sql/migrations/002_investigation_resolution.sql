-- Preserve existing incident tasks and decisions while adding resolution evidence.
ALTER TABLE incident_investigation_tasks
  ADD COLUMN IF NOT EXISTS resolution_json jsonb,
  ADD COLUMN IF NOT EXISTS resolved_at timestamptz,
  ADD COLUMN IF NOT EXISTS resolved_by text;
