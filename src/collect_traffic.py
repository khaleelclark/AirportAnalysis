import json
import os
from datetime import datetime, timezone
from statistics import median
from typing import Any, Optional

import requests

from db import create_tables, get_connection

# Center point + radius (nautical miles) around airport terminal area and approach corridors.
AIRPORT_AREAS = {
    "MCO": {"lat": 28.4312, "lon": -81.3081, "dist_nm": 35},
    "DEN": {"lat": 39.8561, "lon": -104.6737, "dist_nm": 35},
}

# ADSBExchange-compatible shape used by api.adsb.lol.
URL_TEMPLATE = os.getenv("ADSBLOL_URL_TEMPLATE", "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist_nm}")
TIMEOUT_SECONDS = 25


def percentile(values: list[float], p: float) -> Optional[float]:
    if not values:
        return None

    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)

    if f == c:
        return float(values_sorted[f])

    return float(values_sorted[f] + (values_sorted[c] - values_sorted[f]) * (k - f))


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {"", "none", "nan", "ground"}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_aircraft_list(payload: dict[str, Any]) -> list[Any]:
    if isinstance(payload.get("ac"), list):
        return payload["ac"]
    if isinstance(payload.get("aircraft"), list):
        return payload["aircraft"]
    if isinstance(payload.get("states"), list):
        return payload["states"]
    return []


def _parse_row(row: Any) -> tuple[Optional[bool], Optional[float], Optional[float]]:
    # dict style
    if isinstance(row, dict):
        on_ground = row.get("gnd")
        if on_ground is None:
            on_ground = row.get("on_ground")

        velocity = (
            row.get("gs")
            if row.get("gs") is not None
            else row.get("speed")
        )

        altitude = (
            row.get("alt_baro")
            if row.get("alt_baro") is not None
            else row.get("alt_geom")
        )
        if altitude is None:
            altitude = row.get("altitude")

        # ADSB.lol frequently uses alt_baro='ground' without an explicit gnd flag.
        if isinstance(altitude, str) and altitude.strip().lower() == "ground":
            on_ground = True

        altitude_num = _to_float(altitude)
        velocity_num = _to_float(velocity)

        # Fallback inference when no explicit ground flag is provided.
        if on_ground is None:
            if altitude_num is not None and altitude_num > 300:
                on_ground = False
            elif velocity_num is not None and velocity_num >= 80:
                on_ground = False
            elif velocity_num is not None and velocity_num < 50:
                on_ground = True

        return (bool(on_ground) if on_ground is not None else None, velocity_num, altitude_num)

    # OpenSky-like list fallback: index 8 on_ground, index 9 velocity, index 13 geo_alt, index 7 baro_alt
    if isinstance(row, list):
        on_ground = row[8] if len(row) > 8 else None
        velocity = row[9] if len(row) > 9 else None
        altitude = row[13] if len(row) > 13 and row[13] is not None else (row[7] if len(row) > 7 else None)
        return (bool(on_ground) if on_ground is not None else None, _to_float(velocity), _to_float(altitude))

    return (None, None, None)


def fetch_adsb(area: dict[str, float]) -> dict[str, Any]:
    url = URL_TEMPLATE.format(lat=area["lat"], lon=area["lon"], dist_nm=area["dist_nm"])
    resp = requests.get(url, timeout=TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"ADSB.lol error {resp.status_code}: {resp.text[:250]}")
    return resp.json()


def summarize_aircraft(rows: list[Any]) -> dict[str, Any]:
    aircraft_count = len(rows)
    airborne_count = 0
    on_ground_count = 0

    altitudes: list[float] = []
    velocities: list[float] = []

    for row in rows:
        on_ground, velocity, altitude = _parse_row(row)

        if on_ground is True:
            on_ground_count += 1
        elif on_ground is False:
            airborne_count += 1

        if velocity is not None:
            velocities.append(velocity)
        if altitude is not None:
            altitudes.append(altitude)

    return {
        "aircraft_count": aircraft_count,
        "airborne_count": airborne_count,
        "on_ground_count": on_ground_count,
        "altitude_median": float(median(altitudes)) if altitudes else None,
        "altitude_p90": percentile(altitudes, 90),
        "velocity_median": float(median(velocities)) if velocities else None,
        "velocity_p90": percentile(velocities, 90),
    }


def insert_traffic_snapshot(
    airport_code: str,
    collected_at: str,
    summary: dict[str, Any],
    query_meta: str,
    raw_json: str,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO traffic_snapshots (
            airport_code,
            collected_at,
            source,
            aircraft_count,
            airborne_count,
            on_ground_count,
            altitude_median,
            altitude_p90,
            velocity_median,
            velocity_p90,
            query_meta,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            airport_code,
            collected_at,
            "ADSB_LOL",
            summary["aircraft_count"],
            summary["airborne_count"],
            summary["on_ground_count"],
            summary["altitude_median"],
            summary["altitude_p90"],
            summary["velocity_median"],
            summary["velocity_p90"],
            query_meta,
            raw_json,
        ),
    )
    conn.commit()
    conn.close()


def main():
    create_tables()

    collected_at = datetime.now(timezone.utc).isoformat()
    print(f"\\nCollecting ADSB.lol traffic snapshots at {collected_at}\\n")

    for airport_code, area in AIRPORT_AREAS.items():
        print(f"Fetching traffic for {airport_code}...")

        data = fetch_adsb(area)
        rows = _extract_aircraft_list(data)
        summary = summarize_aircraft(rows)

        raw_debug = {
            "source": "ADSB_LOL",
            "airport": airport_code,
            "collected_at": collected_at,
            "area": area,
            "response_keys": sorted(list(data.keys())),
            "reported_count": data.get("total") or data.get("count") or len(rows),
        }
        query_meta = {
            "url_template": URL_TEMPLATE,
            "area": area,
        }

        insert_traffic_snapshot(
            airport_code=airport_code,
            collected_at=collected_at,
            summary=summary,
            query_meta=json.dumps(query_meta),
            raw_json=json.dumps(raw_debug),
        )

        print(
            f"[OK] {airport_code}: aircraft={summary['aircraft_count']} "
            f"airborne={summary['airborne_count']} ground={summary['on_ground_count']}"
        )

    print("\\nDone.\\n")


if __name__ == "__main__":
    main()
