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
    # Delay Snapshots (AeroDataBox)
    # ============================
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS delay_snapshots (
                                                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                  airport_code TEXT NOT NULL,
                                                                  collected_at TEXT NOT NULL,

                                                                  delay_mean_minutes REAL,
                                                                  delay_median_minutes REAL,
                                                                  delay_p90_minutes REAL,
                                                                  delay_p50_minutes REAL,
                                                                  delay_index REAL,

                                                                  total_flights INTEGER,
                                                                  delayed_flights INTEGER,
                                                                  cancelled_flights INTEGER,
                                                                  diverted_flights INTEGER,

                                                                  raw_json TEXT,

                                                                  UNIQUE(airport_code, collected_at)
                       );
                   """)

    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_delay_airport_time
                       ON delay_snapshots(airport_code, collected_at);
                   """)

    # ============================
    # Traffic Snapshots (OpenSky)
    # ============================
    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS traffic_snapshots (
                                                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                    airport_code TEXT NOT NULL,
                                                                    collected_at TEXT NOT NULL,

                                                                    aircraft_count INTEGER NOT NULL,
                                                                    airborne_count INTEGER,
                                                                    on_ground_count INTEGER,

                                                                    altitude_median REAL,
                                                                    altitude_p90 REAL,

                                                                    velocity_median REAL,
                                                                    velocity_p90 REAL,

                                                                    raw_json TEXT,

                                                                    UNIQUE(airport_code, collected_at)
                       );
                   """)

    cursor.execute("""
                   CREATE INDEX IF NOT EXISTS idx_traffic_airport_time
                       ON traffic_snapshots(airport_code, collected_at);
                   """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables()
    print("Database tables created successfully.")
