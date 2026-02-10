import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aviation.db"

NEW_COLUMNS = [
    ("window_from_utc", "TEXT"),
    ("window_to_utc", "TEXT"),

    ("arr_total", "INTEGER"),
    ("arr_qualified_total", "INTEGER"),
    ("arr_cancelled", "INTEGER"),
    ("arr_median_delay_minutes", "REAL"),
    ("arr_delay_index", "REAL"),

    ("dep_total", "INTEGER"),
    ("dep_qualified_total", "INTEGER"),
    ("dep_cancelled", "INTEGER"),
    ("dep_median_delay_minutes", "REAL"),
    ("dep_delay_index", "REAL"),
]


def column_exists(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == col for row in cur.fetchall())


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    table = "delay_snapshots"

    for col_name, col_type in NEW_COLUMNS:
        if column_exists(cur, table, col_name):
            print(f"[SKIP] {col_name} already exists")
            continue

        sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type};"
        cur.execute(sql)
        print(f"[ADD] {col_name} {col_type}")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
