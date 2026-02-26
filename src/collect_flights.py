import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

try:
    from db import get_connection  # type: ignore
except Exception:
    DB_PATH = Path("data/aviation.db")

    def get_connection():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


load_dotenv()

API_KEY = os.getenv("AIRLABS_API_KEY")
BASE_URL = os.getenv("AIRLABS_BASE_URL", "https://airlabs.co/api/v9/delays")
AIRPORTS = [a.strip().upper() for a in os.getenv("AIRLABS_AIRPORTS", "MCO,DEN").split(",") if a.strip()]
TIMEOUT_SECONDS = int(os.getenv("AIRLABS_TIMEOUT_SECONDS", "30"))
REQUEST_PAUSE_SECONDS = float(os.getenv("AIRLABS_REQUEST_PAUSE_SECONDS", "0.5"))
LIMIT = int(os.getenv("AIRLABS_LIMIT", "100"))
LOCAL_COLLECTION_START_HOUR = int(os.getenv("AIRLABS_LOCAL_START_HOUR", "9"))
LOCAL_COLLECTION_END_HOUR = int(os.getenv("AIRLABS_LOCAL_END_HOUR", "23"))
COLLECTION_INTERVAL_MINUTES = int(os.getenv("AIRLABS_COLLECTION_INTERVAL_MINUTES", "120"))
STATE_DIR = Path(os.getenv("AIRLABS_STATE_DIR", "data/collector_state"))
FORCE_SYNC = os.getenv("AIRLABS_FORCE_SYNC", "").strip().lower() in {"1", "true", "yes", "on"}

AIRPORT_TIMEZONES = {
    "MCO": ZoneInfo("America/New_York"),
    "DEN": ZoneInfo("America/Denver"),
}


def iso_to_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def airport_local_now(now_utc: datetime, airport: str) -> datetime:
    tz = AIRPORT_TIMEZONES.get(airport, timezone.utc)
    return now_utc.astimezone(tz)


def in_local_collection_window(local_dt: datetime) -> bool:
    return LOCAL_COLLECTION_START_HOUR <= local_dt.hour <= LOCAL_COLLECTION_END_HOUR


def get_last_collected_at(conn: sqlite3.Connection, airport: str) -> Optional[datetime]:
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT MAX(collected_at) AS last_collected_at
        FROM flight_snapshots
        WHERE airport_code = ?
        """,
        (airport,),
    ).fetchone()
    if row is None:
        return None
    raw_val = row[0] if not isinstance(row, sqlite3.Row) else row["last_collected_at"]
    if not raw_val:
        return None
    last_dt = iso_to_dt(str(raw_val))
    if last_dt is None:
        return None
    if last_dt.tzinfo is None:
        return last_dt.replace(tzinfo=timezone.utc)
    return last_dt.astimezone(timezone.utc)


def get_last_api_call_attempt(airport: str) -> Optional[datetime]:
    state_file = STATE_DIR / f"airlabs_last_call_{airport}.txt"
    if not state_file.exists():
        return None
    try:
        raw_val = state_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    last_dt = iso_to_dt(raw_val)
    if last_dt is None:
        return None
    if last_dt.tzinfo is None:
        return last_dt.replace(tzinfo=timezone.utc)
    return last_dt.astimezone(timezone.utc)


def record_api_call_attempt(airport: str, attempted_at: datetime) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = STATE_DIR / f"airlabs_last_call_{airport}.txt"
    state_file.write_text(attempted_at.astimezone(timezone.utc).isoformat(), encoding="utf-8")


def should_collect_for_airport(conn: sqlite3.Connection, airport: str, now_utc: datetime) -> tuple[bool, str]:
    if FORCE_SYNC:
        return True, "manual override (AIRLABS_FORCE_SYNC)"

    local_now = airport_local_now(now_utc, airport)
    if not in_local_collection_window(local_now):
        return False, f"outside local collection window ({local_now.strftime('%H:%M %Z')})"

    last_attempt = get_last_api_call_attempt(airport)
    last_collected = get_last_collected_at(conn, airport)
    reference_time = last_attempt or last_collected
    if reference_time is None:
        return True, "no previous snapshots"

    elapsed_min = (now_utc - reference_time).total_seconds() / 60.0
    source = "last API call" if last_attempt is not None else "last stored snapshot"
    if elapsed_min < COLLECTION_INTERVAL_MINUTES:
        return False, f"interval not reached since {source} ({elapsed_min:.0f}m < {COLLECTION_INTERVAL_MINUTES}m)"
    return True, f"interval reached since {source} ({elapsed_min:.0f}m)"


def minutes_between(late: Optional[datetime], early: Optional[datetime]) -> Optional[float]:
    if not late or not early:
        return None
    return (late - early).total_seconds() / 60.0


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_non_empty(flight: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        v = flight.get(k)
        if v is not None and v != "":
            return v
    return None


def make_external_id(f: Dict[str, Any], direction: str, airport: str) -> str:
    raw_key = "|".join(
        [
            "airlabs",
            direction,
            airport,
            str(first_non_empty(f, ["flight_iata", "flight_icao", "flight_number", "hex"]) or ""),
            str(first_non_empty(f, ["airline_iata", "airline_icao"]) or ""),
            str(first_non_empty(f, ["dep_iata", "dep_icao"]) or ""),
            str(first_non_empty(f, ["arr_iata", "arr_icao"]) or ""),
            str(first_non_empty(f, ["dep_time", "dep_estimated", "dep_actual"]) or ""),
            str(first_non_empty(f, ["arr_time", "arr_estimated", "arr_actual"]) or ""),
        ]
    )
    return "airlabs:" + hashlib.sha1(raw_key.encode("utf-8")).hexdigest()


def compute_delay_minutes(direction: str, f: Dict[str, Any]) -> Optional[float]:
    if direction == "departure":
        direct = to_float(first_non_empty(f, ["dep_delayed", "dep_delay", "delayed"]))
        sched = iso_to_dt(first_non_empty(f, ["dep_time", "dep_scheduled"]))
        est = iso_to_dt(first_non_empty(f, ["dep_estimated"]))
        act = iso_to_dt(first_non_empty(f, ["dep_actual"]))
    else:
        direct = to_float(first_non_empty(f, ["arr_delayed", "arr_delay", "delayed"]))
        sched = iso_to_dt(first_non_empty(f, ["arr_time", "arr_scheduled"]))
        est = iso_to_dt(first_non_empty(f, ["arr_estimated"]))
        act = iso_to_dt(first_non_empty(f, ["arr_actual"]))

    if direct is not None:
        return direct
    if act and sched:
        return minutes_between(act, sched)
    if est and sched:
        return minutes_between(est, sched)
    return None


def airlabs_get(params: Dict[str, Any]) -> Dict[str, Any]:
    if not API_KEY:
        raise RuntimeError("Missing AIRLABS_API_KEY in .env")

    q = dict(params)
    q["api_key"] = API_KEY

    resp = requests.get(BASE_URL, params=q, timeout=TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"AirLabs error {resp.status_code}: {resp.text[:500]}")

    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(f"AirLabs API error: {payload.get('error')}")
    return payload


def normalize_flight_row(airport: str, direction: str, collected_at: str, f: Dict[str, Any]) -> Dict[str, Any]:
    ident = first_non_empty(f, ["flight_iata", "flight_icao", "flight_number"])
    airline_code = first_non_empty(f, ["airline_iata", "airline_icao"])

    origin = first_non_empty(f, ["dep_iata", "dep_icao"])
    destination = first_non_empty(f, ["arr_iata", "arr_icao"])

    if direction == "departure":
        scheduled_time = first_non_empty(f, ["dep_time", "dep_scheduled"])
        estimated_time = first_non_empty(f, ["dep_estimated"])
        actual_time = first_non_empty(f, ["dep_actual"])
    else:
        scheduled_time = first_non_empty(f, ["arr_time", "arr_scheduled"])
        estimated_time = first_non_empty(f, ["arr_estimated"])
        actual_time = first_non_empty(f, ["arr_actual"])

    status = str(first_non_empty(f, ["status"]) or "").lower()
    external_id = make_external_id(f, direction=direction, airport=airport)
    cancelled = 1 if ("cancel" in status) else 0
    diverted = 1 if ("divert" in status) else 0

    return {
        "collected_at": collected_at,
        "airport_code": airport,
        "direction": direction,
        "provider": "AIRLABS",
        "external_flight_id": external_id,
        "fa_flight_id": external_id,
        "ident": ident,
        "airline_code": airline_code,
        "status": status,
        "origin": origin,
        "destination": destination,
        "scheduled_time": scheduled_time,
        "estimated_time": estimated_time,
        "actual_time": actual_time,
        "delay_minutes": compute_delay_minutes(direction, f),
        "cancelled": cancelled,
        "diverted": diverted,
        "raw_json": json.dumps({"source": "AIRLABS", "flight": f}),
    }


def insert_rows(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> int:
    cur = conn.cursor()
    saved = 0

    for r in rows:
        cur.execute(
            """
            INSERT OR IGNORE INTO flight_snapshots (
                collected_at,
                airport_code,
                direction,
                provider,
                external_flight_id,
                fa_flight_id,
                ident,
                airline_code,
                status,
                origin,
                destination,
                scheduled_time,
                estimated_time,
                actual_time,
                delay_minutes,
                cancelled,
                diverted,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["collected_at"],
                r["airport_code"],
                r["direction"],
                r.get("provider"),
                r.get("external_flight_id"),
                r["fa_flight_id"],
                r.get("ident"),
                r.get("airline_code"),
                r.get("status"),
                r.get("origin"),
                r.get("destination"),
                r.get("scheduled_time"),
                r.get("estimated_time"),
                r.get("actual_time"),
                r.get("delay_minutes"),
                r.get("cancelled"),
                r.get("diverted"),
                r.get("raw_json"),
            ),
        )
        saved += cur.rowcount

    conn.commit()
    return saved


def fetch_and_store_for_airport(conn: sqlite3.Connection, airport: str, direction: str, collected_at: str) -> Tuple[int, int]:
    params: Dict[str, Any] = {
        "type": "departures" if direction == "departure" else "arrivals",
        "limit": LIMIT,
    }
    if direction == "departure":
        params["dep_iata"] = airport
    else:
        params["arr_iata"] = airport

    data = airlabs_get(params)
    flights = data.get("response") or data.get("data") or []
    if not isinstance(flights, list):
        flights = []

    rows = [normalize_flight_row(airport, direction, collected_at, f) for f in flights if isinstance(f, dict)]
    inserted = insert_rows(conn, rows)
    return len(flights), inserted


def main():
    now_utc = datetime.now(timezone.utc)
    collected_at = now_utc.isoformat()
    print(f"\nCollecting AirLabs flight snapshots at {collected_at}")
    print(f"Airports={AIRPORTS}\n")

    conn = get_connection()

    try:
        total_fetched = 0
        total_inserted = 0

        for airport in AIRPORTS:
            should_collect, reason = should_collect_for_airport(conn, airport, now_utc)
            local_now = airport_local_now(now_utc, airport)
            print(
                f"{airport} local time {local_now.strftime('%Y-%m-%d %H:%M %Z')}: "
                f"{'collecting' if should_collect else 'skipping'} ({reason})"
            )
            if not should_collect:
                continue
            record_api_call_attempt(airport, now_utc)

            for direction in ("departure", "arrival"):
                print(f"Fetching {airport} {direction}s ...")
                try:
                    fetched, inserted = fetch_and_store_for_airport(conn, airport, direction, collected_at)
                    total_fetched += fetched
                    total_inserted += inserted
                    print(f"[OK] {airport} {direction}: fetched={fetched} inserted={inserted}")
                except Exception as e:
                    print(f"[WARN] {airport} {direction} failed: {e}")
                time.sleep(REQUEST_PAUSE_SECONDS)

        print(f"\nDone. Total fetched={total_fetched} total inserted={total_inserted}\n")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
