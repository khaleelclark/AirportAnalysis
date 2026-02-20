import sqlite3
from pathlib import Path

DB_PATH = Path("data/aviation.db")


def get_connection():
    # Ensure the data folder exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # makes query results dictionary-like
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # ============================
    # Delay Snapshots (FAA/AeroDataBox)
    # ============================
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS delay_snapshots (
                                                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                  airport_code TEXT NOT NULL,
                                                                  collected_at TEXT NOT NULL,
                                                                  source TEXT NOT NULL DEFAULT 'UNKNOWN',

                                                                  delay_mean_minutes REAL,
                                                                  delay_median_minutes REAL,
                                                                  delay_p90_minutes REAL,
                                                                  delay_p50_minutes REAL,
                                                                  delay_index REAL,

                                                                  total_flights INTEGER,
                                                                  delayed_flights INTEGER,
                                                                  cancelled_flights INTEGER,
                                                                  diverted_flights INTEGER,
                                                                  window_from_utc TEXT,
                                                                  window_to_utc TEXT,
                                                                  dep_total INTEGER,
                                                                  dep_qualified_total INTEGER,
                                                                  dep_cancelled INTEGER,
                                                                  dep_median_delay_minutes REAL,
                                                                  dep_delay_index REAL,
                                                                  arr_total INTEGER,
                                                                  arr_qualified_total INTEGER,
                                                                  arr_cancelled INTEGER,
                                                                  arr_median_delay_minutes REAL,
                                                                  arr_delay_index REAL,
                                                                  faa_update_time TEXT,
                                                                  faa_event_count INTEGER,

                                                                  raw_json TEXT,

                                                                  UNIQUE(airport_code, collected_at)
                       );
                   """)

    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_delay_airport_time
                       ON delay_snapshots(airport_code, collected_at);
                   """)
    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_delay_source_time
                       ON delay_snapshots(source, collected_at);
                   """)

    # ============================
    # Traffic Snapshots (ADSB/OpenSky-compatible)
    # ============================
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS traffic_snapshots (
                                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                    airport_code TEXT NOT NULL,
                                                                    collected_at TEXT NOT NULL,
                                                                    source TEXT NOT NULL DEFAULT 'UNKNOWN',

                                                                    aircraft_count INTEGER NOT NULL,
                                                                    airborne_count INTEGER,
                                                                    on_ground_count INTEGER,

                                                                    altitude_median REAL,
                                                                    altitude_p90 REAL,

                                                                    velocity_median REAL,
                                                                    velocity_p90 REAL,

                                                                    query_meta TEXT,
                                                                    raw_json TEXT,

                                                                    UNIQUE(airport_code, collected_at)
                       );
                   """)

    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_traffic_airport_time
                       ON traffic_snapshots(airport_code, collected_at);
                   """)
    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_traffic_source_time
                       ON traffic_snapshots(source, collected_at);
                   """)

    # ============================
    # FAA Event Details
    # ============================
    cursor.execute("""
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
                   """)
    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_faa_events_airport_time
                       ON faa_events(airport_code, collected_at);
                   """)

    # ============================
    # Flight Snapshots (Provider-neutral)
    # ============================
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS flight_snapshots (
                                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                    collected_at TEXT NOT NULL,
                                                                    airport_code TEXT NOT NULL,
                                                                    direction TEXT NOT NULL,

                                                                    provider TEXT NOT NULL DEFAULT 'UNKNOWN',
                                                                    external_flight_id TEXT NOT NULL,
                                                                    fa_flight_id TEXT,
                                                                    ident TEXT,
                                                                    airline_code TEXT,
                                                                    status TEXT,
                                                                    origin TEXT,
                                                                    destination TEXT,

                                                                    scheduled_time TEXT,
                                                                    estimated_time TEXT,
                                                                    actual_time TEXT,

                                                                    delay_minutes REAL,
                                                                    cancelled INTEGER DEFAULT 0,
                                                                    diverted INTEGER DEFAULT 0,
                                                                    raw_json TEXT
                       );
                   """)
    cursor.execute("""
                   CREATE UNIQUE INDEX IF NOT EXISTS idx_flight_provider_external_direction
                       ON flight_snapshots(provider, external_flight_id, direction);
                   """)
    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_flight_airport_time
                       ON flight_snapshots(airport_code, collected_at);
                   """)
    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_flight_direction_time
                       ON flight_snapshots(direction, collected_at);
                   """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables()
    print("Database tables created successfully.")
