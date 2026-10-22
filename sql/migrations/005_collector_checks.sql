-- Additive audit of source poll attempts. Stores no source credentials.
CREATE TABLE IF NOT EXISTS collector_checks (
    check_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source text NOT NULL CHECK (source IN ('USGS','GDACS','PORTWATCH')),
    checked_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL CHECK (status IN ('OK','ERROR')),
    received_count integer NOT NULL DEFAULT 0 CHECK (received_count >= 0),
    created_count integer NOT NULL DEFAULT 0 CHECK (created_count >= 0),
    error_type text,
    CHECK ((status='ERROR' AND error_type IS NOT NULL)
        OR (status='OK' AND error_type IS NULL))
);
CREATE INDEX IF NOT EXISTS collector_checks_source_time
    ON collector_checks(source,checked_at DESC,check_id DESC);
