-- One dated capacity ceiling for the whole facility, never one per SKU.
-- Always distinct from a SKU's supplier_capacity observations.
CREATE TABLE IF NOT EXISTS confirmed_facility_capacity (
  facility_id text NOT NULL REFERENCES facilities(facility_id),
  week_start date NOT NULL,
  valid_until date NOT NULL,
  capacity_units integer NOT NULL CHECK (capacity_units >= 0),
  committed_units integer NOT NULL DEFAULT 0
    CHECK (committed_units >= 0 AND committed_units <= capacity_units),
  evidence_source text NOT NULL CHECK (length(trim(evidence_source)) > 0),
  evidence_reference text NOT NULL CHECK (length(trim(evidence_reference)) > 0),
  confirmed_by text NOT NULL CHECK (length(trim(confirmed_by)) > 0),
  provenance_class text NOT NULL DEFAULT 'SIMULATED_PRIVATE',
  confirmed_at timestamptz NOT NULL DEFAULT now(),
  CHECK (valid_until >= week_start),
  PRIMARY KEY (facility_id, week_start)
);
CREATE INDEX IF NOT EXISTS confirmed_facility_capacity_window_idx
  ON confirmed_facility_capacity(facility_id, valid_until, week_start DESC);
