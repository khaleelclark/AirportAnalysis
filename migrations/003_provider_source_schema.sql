-- 003_provider_source_schema.sql
-- Adds provider/source fields for live APIs and FAA event detail storage.

BEGIN TRANSACTION;

-- delay_snapshots enhancements
ALTER TABLE delay_snapshots ADD COLUMN source TEXT NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE delay_snapshots ADD COLUMN faa_update_time TEXT;
ALTER TABLE delay_snapshots ADD COLUMN faa_event_count INTEGER;
CREATE INDEX IF NOT EXISTS idx_delay_source_time
    ON delay_snapshots(source, collected_at);

-- traffic_snapshots enhancements
ALTER TABLE traffic_snapshots ADD COLUMN source TEXT NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE traffic_snapshots ADD COLUMN query_meta TEXT;
CREATE INDEX IF NOT EXISTS idx_traffic_source_time
    ON traffic_snapshots(source, collected_at);

-- flight_snapshots enhancements
ALTER TABLE flight_snapshots ADD COLUMN provider TEXT NOT NULL DEFAULT 'UNKNOWN';
ALTER TABLE flight_snapshots ADD COLUMN external_flight_id TEXT;
ALTER TABLE flight_snapshots ADD COLUMN airline_code TEXT;
ALTER TABLE flight_snapshots ADD COLUMN status TEXT;

UPDATE flight_snapshots
SET external_flight_id = COALESCE(external_flight_id, fa_flight_id)
WHERE external_flight_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_flight_provider_external_direction
    ON flight_snapshots(provider, external_flight_id, direction);

-- FAA event detail rows (one airport can have multiple concurrent FAA events)
CREATE TABLE IF NOT EXISTS faa_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    airport_code TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    event_type TEXT,
    reason TEXT,
    min_delay_minutes REAL,
    max_delay_minutes REAL,
    trend TEXT,
    severity REAL,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_faa_events_airport_time
    ON faa_events(airport_code, collected_at);

COMMIT;
