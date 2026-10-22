-- Isolated satellite observations: individual pixels are NOT disasters.
-- Additive and idempotent. Never trigger the incident consumer for raw pixels.
CREATE TABLE IF NOT EXISTS source_observations (
  source text NOT NULL,
  observation_id text NOT NULL,
  observation_type text NOT NULL,
  observed_at timestamptz NOT NULL,
  first_received_at timestamptz NOT NULL DEFAULT now(),
  last_checked_at timestamptz NOT NULL DEFAULT now(),
  latitude double precision NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude double precision NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  geom geography(Point, 4326) NOT NULL,
  raw_json jsonb NOT NULL,
  source_url text,
  provenance_class text NOT NULL,
  PRIMARY KEY (source, observation_id)
);
CREATE INDEX IF NOT EXISTS source_observations_geom_gix
  ON source_observations USING GIST (geom);
CREATE INDEX IF NOT EXISTS source_observations_source_time
  ON source_observations(source, observed_at DESC);
