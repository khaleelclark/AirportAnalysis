import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from dotenv import load_dotenv

from db import create_tables, get_connection

print("RUNNING UPDATED collect_delays.py v3")  # <-- you should SEE THIS when running

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

AIRPORTS = ["MCO", "DEN"]


def parse_hhmmss_to_minutes(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    s = value.strip()
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    parts = s.split(":")
    if len(parts) != 3:
        return None
    hh, mm, ss = parts
    try:
        total_seconds = int(hh) * 3600 + int(mm) * 60 + int(ss)
        return sign * (total_seconds / 60.0)
    except ValueError:
        return None


def as_int(x):
    return int(x) if isinstance(x, (int, float)) else None


def as_float(x):
    return float(x) if isinstance(x, (int, float)) else None


def fetch_airport_delays_iata(iata_code: str) -> dict:
    if not RAPIDAPI_KEY:
        raise RuntimeError("Missing RAPIDAPI_KEY in .env")

    url = f"{BASE_URL}/airports/iata/{iata_code}/delays"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Accept": "application/json",
    }

    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code == 204:
        return {}
    if resp.status_code != 200:
        raise RuntimeError(f"AeroDataBox error {resp.status_code}: {resp.text}")
    return resp.json()


def summarize_delay_contract(data: dict) -> dict:
    if not data:
        return {}

    dep = data.get("departuresDelayInformation") or {}
    arr = data.get("arrivalsDelayInformation") or {}

    window_from_utc = (data.get("from") or {}).get("utc")
    window_to_utc = (data.get("to") or {}).get("utc")

    dep_total = as_int(dep.get("numTotal"))
    dep_qualified_total = as_int(dep.get("numQualifiedTotal"))
    dep_cancelled = as_int(dep.get("numCancelled"))
    dep_median_delay_minutes = parse_hhmmss_to_minutes(dep.get("medianDelay"))
    dep_delay_index = as_float(dep.get("delayIndex"))

    arr_total = as_int(arr.get("numTotal"))
    arr_qualified_total = as_int(arr.get("numQualifiedTotal"))
    arr_cancelled = as_int(arr.get("numCancelled"))
    arr_median_delay_minutes = parse_hhmmss_to_minutes(arr.get("medianDelay"))
    arr_delay_index = as_float(arr.get("delayIndex"))

    total_flights = None
    if dep_total is not None or arr_total is not None:
        total_flights = (dep_total or 0) + (arr_total or 0)

    cancelled_flights = None
    if dep_cancelled is not None or arr_cancelled is not None:
        cancelled_flights = (dep_cancelled or 0) + (arr_cancelled or 0)

    idx_values = [v for v in [dep_delay_index, arr_delay_index] if v is not None]
    delay_index = (sum(idx_values) / len(idx_values)) if idx_values else None

    med_values = [v for v in [dep_median_delay_minutes, arr_median_delay_minutes] if v is not None]
    delay_median_minutes = (sum(med_values) / len(med_values)) if med_values else None

    return {
        "window_from_utc": window_from_utc,
        "window_to_utc": window_to_utc,

        "dep_total": dep_total,
        "dep_qualified_total": dep_qualified_total,
        "dep_cancelled": dep_cancelled,
        "dep_median_delay_minutes": dep_median_delay_minutes,
        "dep_delay_index": dep_delay_index,

        "arr_total": arr_total,
        "arr_qualified_total": arr_qualified_total,
        "arr_cancelled": arr_cancelled,
        "arr_median_delay_minutes": arr_median_delay_minutes,
        "arr_delay_index": arr_delay_index,

        "total_flights": total_flights,
        "cancelled_flights": cancelled_flights,
        "delay_index": delay_index,
        "delay_median_minutes": delay_median_minutes,
    }


def insert_delay_snapshot(airport_code: str, collected_at: str, summary: dict, raw_json: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR IGNORE INTO delay_snapshots (
            airport_code, collected_at,
            delay_index, delay_median_minutes,
            total_flights, cancelled_flights,

            window_from_utc, window_to_utc,

            dep_total, dep_qualified_total, dep_cancelled, dep_median_delay_minutes, dep_delay_index,
            arr_total, arr_qualified_total, arr_cancelled, arr_median_delay_minutes, arr_delay_index,

            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            airport_code, collected_at,
            summary.get("delay_index"), summary.get("delay_median_minutes"),
            summary.get("total_flights"), summary.get("cancelled_flights"),

            summary.get("window_from_utc"), summary.get("window_to_utc"),

            summary.get("dep_total"), summary.get("dep_qualified_total"), summary.get("dep_cancelled"),
            summary.get("dep_median_delay_minutes"), summary.get("dep_delay_index"),

            summary.get("arr_total"), summary.get("arr_qualified_total"), summary.get("arr_cancelled"),
            summary.get("arr_median_delay_minutes"), summary.get("arr_delay_index"),

            raw_json
        ),
    )

    conn.commit()
    conn.close()


def main():
    create_tables()

    collected_at = datetime.now(timezone.utc).isoformat()
    print(f"\nCollecting AeroDataBox delay snapshots at {collected_at}\n")

    for airport in AIRPORTS:
        print(f"Fetching delays for {airport}...")

        data = fetch_airport_delays_iata(airport)
        summary = summarize_delay_contract(data)

        raw_debug = {"airport": airport, "collected_at": collected_at, "raw": data}

        insert_delay_snapshot(
            airport_code=airport,
            collected_at=collected_at,
            summary=summary,
            raw_json=json.dumps(raw_debug),
        )

        print(
            f"[OK] {airport}: window={summary.get('window_from_utc')}→{summary.get('window_to_utc')} "
            f"dep_total={summary.get('dep_total')} arr_total={summary.get('arr_total')}"
        )

        time.sleep(2)

    print("\nDone.\n")


if __name__ == "__main__":
    main()
