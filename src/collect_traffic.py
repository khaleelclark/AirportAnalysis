import json
import requests
from datetime import datetime, timezone
from statistics import median

from db import get_connection, create_tables


# Bounding boxes (lat min, lat max, lon min, lon max)
# These are "reasonable airspace boxes" around each airport.
AIRPORT_BBOX = {
    "MCO": {"lamin": 28.10, "lamax": 28.75, "lomin": -81.75, "lomax": -80.90},
    "DEN": {"lamin": 39.55, "lamax": 40.20, "lomin": -105.20, "lomax": -104.10},
}

OPENSKY_URL = "https://opensky-network.org/api/states/all"


def percentile(values, p: float):
    """Returns the pth percentile of a list (0-100)."""
    if not values:
        return None

    values_sorted = sorted(values)
    k = (len(values_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values_sorted) - 1)

    if f == c:
        return float(values_sorted[f])

    return float(values_sorted[f] + (values_sorted[c] - values_sorted[f]) * (k - f))


def fetch_opensky_states(bbox_params: dict):
    """Calls OpenSky API and returns JSON response."""
    response = requests.get(OPENSKY_URL, params=bbox_params, timeout=20)

    if response.status_code != 200:
        raise Exception(f"OpenSky API error: {response.status_code} - {response.text}")

    return response.json()


def summarize_states(states: list):
    """
    OpenSky 'states' is a list of lists.
    Each element represents one aircraft state vector.
    We will compute summary stats from it.
    """
    aircraft_count = len(states)

    airborne_count = 0
    on_ground_count = 0

    altitudes = []
    velocities = []

    for s in states:
        # OpenSky state vector indices (important ones)
        # 5 = longitude
        # 6 = latitude
        # 7 = baro_altitude
        # 8 = on_ground (boolean)
        # 9 = velocity (m/s)
        # 13 = geo_altitude

        on_ground = s[8]
        velocity = s[9]
        baro_altitude = s[7]
        geo_altitude = s[13]

        if on_ground is True:
            on_ground_count += 1
        elif on_ground is False:
            airborne_count += 1

        # Prefer geo_altitude if available, fallback to baro_altitude
        alt = geo_altitude if geo_altitude is not None else baro_altitude
        if alt is not None:
            altitudes.append(float(alt))

        if velocity is not None:
            velocities.append(float(velocity))

    altitude_median = float(median(altitudes)) if altitudes else None
    altitude_p90 = percentile(altitudes, 90)

    velocity_median = float(median(velocities)) if velocities else None
    velocity_p90 = percentile(velocities, 90)

    return {
        "aircraft_count": aircraft_count,
        "airborne_count": airborne_count,
        "on_ground_count": on_ground_count,
        "altitude_median": altitude_median,
        "altitude_p90": altitude_p90,
        "velocity_median": velocity_median,
        "velocity_p90": velocity_p90,
    }


def insert_traffic_snapshot(airport_code: str, collected_at: str, summary: dict, raw_json: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
                INSERT OR IGNORE INTO traffic_snapshots (
            airport_code,
            collected_at,
            aircraft_count,
            airborne_count,
            on_ground_count,
            altitude_median,
            altitude_p90,
            velocity_median,
            velocity_p90,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    airport_code,
                    collected_at,
                    summary["aircraft_count"],
                    summary["airborne_count"],
                    summary["on_ground_count"],
                    summary["altitude_median"],
                    summary["altitude_p90"],
                    summary["velocity_median"],
                    summary["velocity_p90"],
                    raw_json
                ))

    conn.commit()
    conn.close()


def main():
    create_tables()

    collected_at = datetime.now(timezone.utc).isoformat()
    print(f"\nCollecting OpenSky traffic snapshots at {collected_at}\n")

    for airport_code, bbox in AIRPORT_BBOX.items():
        print(f"Fetching traffic data for {airport_code}...")

        data = fetch_opensky_states(bbox)
        states = data.get("states") or []

        summary = summarize_states(states)

        raw_debug = {
            "airport": airport_code,
            "bbox": bbox,
            "opensky_time": data.get("time"),
            "state_count": len(states)
        }

        insert_traffic_snapshot(
            airport_code=airport_code,
            collected_at=collected_at,
            summary=summary,
            raw_json=json.dumps(raw_debug)
        )

        print(f"[OK] {airport_code}: aircraft={summary['aircraft_count']} airborne={summary['airborne_count']} ground={summary['on_ground_count']}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
