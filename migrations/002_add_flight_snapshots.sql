-- 002_add_flight_snapshots.sql
-- Adds a table to store individual flight-level snapshots from FlightAware AeroAPI
-- so we can compute delay minutes, cancellation rate, distributions, etc.

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS flight_snapshots (
                                                id INTEGER PRIMARY KEY AUTOINCREMENT,

                                                collected_at TEXT NOT NULL,        -- when YOUR script collected this record (UTC ISO)
                                                airport_code TEXT NOT NULL,        -- e.g. KMCO, KDEN
                                                direction TEXT NOT NULL,           -- 'arrival' or 'departure'

                                                fa_flight_id TEXT NOT NULL,        -- unique ID per flight instance from FlightAware
                                                ident TEXT,                        -- airline+number like AAL123
                                                origin TEXT,                       -- ICAO or IATA
                                                destination TEXT,                  -- ICAO or IATA

                                                scheduled_time TEXT,               -- scheduled_off (dep) or scheduled_on (arr)
                                                estimated_time TEXT,               -- estimated_off/estimated_on
                                                actual_time TEXT,                  -- actual_off/actual_on

                                                delay_minutes REAL,                -- computed by you: (actual or estimated) - scheduled
                                                cancelled INTEGER DEFAULT 0,       -- 0/1
                                                diverted INTEGER DEFAULT 0,        -- 0/1 (optional if provided)
                                                raw_json TEXT,                     -- full raw FlightAware flight object for traceability

    -- prevent duplicates when you re-collect
                                                UNIQUE(fa_flight_id, direction)
);

CREATE INDEX IF NOT EXISTS idx_flight_airport_time
    ON flight_snapshots(airport_code, collected_at);

CREATE INDEX IF NOT EXISTS idx_flight_direction_time
    ON flight_snapshots(direction, collected_at);

COMMIT;
