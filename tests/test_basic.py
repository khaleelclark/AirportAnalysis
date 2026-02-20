from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import collect_delays as delays  # noqa: E402
import collect_flights as flights  # noqa: E402
import collect_traffic as traffic  # noqa: E402


def test_parse_duration_minutes_handles_hours_and_minutes():
    assert delays._parse_duration_minutes("1 hour and 9 minutes") == 69.0
    assert delays._parse_duration_minutes("38 minutes") == 38.0


def test_parse_airports_builds_severity_and_average_delay():
    xml = """
    <AirportStatus>
      <Update_Time>02/20/2026 18:00 UTC</Update_Time>
      <Delay_type>
        <Name>Ground Delay Programs</Name>
        <Program>
          <ARPT>MCO</ARPT>
          <Reason>Volume</Reason>
          <Avg>45 minutes</Avg>
        </Program>
      </Delay_type>
    </AirportStatus>
    """

    parsed, update_time = delays.parse_airports(xml)

    assert update_time == "02/20/2026 18:00 UTC"
    assert parsed["MCO"]["delay_index"] == 3.0
    assert parsed["MCO"]["delay_median_minutes"] == 45.0
    assert parsed["DEN"]["delay_index"] == 0.0
    assert parsed["DEN"]["delay_median_minutes"] is None


def test_parse_row_marks_ground_when_altitude_is_ground():
    row = {"alt_baro": "ground", "gs": 12}
    on_ground, velocity, altitude = traffic._parse_row(row)
    assert on_ground is True
    assert velocity == 12.0
    assert altitude is None


def test_summarize_aircraft_counts_ground_and_airborne():
    rows = [
        {"alt_baro": "ground", "gs": 8},
        {"alt_baro": 2500, "gs": 140},
        {"gnd": False, "alt_baro": 12000, "gs": 320},
    ]
    summary = traffic.summarize_aircraft(rows)

    assert summary["aircraft_count"] == 3
    assert summary["on_ground_count"] == 1
    assert summary["airborne_count"] == 2
    assert summary["velocity_median"] == 140.0


def test_compute_delay_minutes_prefers_direct_delay():
    flight = {"dep_delayed": 27, "dep_time": "2026-02-20T10:00:00Z", "dep_estimated": "2026-02-20T10:30:00Z"}
    assert flights.compute_delay_minutes("departure", flight) == 27.0


def test_compute_delay_minutes_falls_back_to_sched_vs_estimated():
    flight = {"arr_time": "2026-02-20T11:00:00Z", "arr_estimated": "2026-02-20T11:42:00Z"}
    assert flights.compute_delay_minutes("arrival", flight) == 42.0


def test_normalize_flight_row_sets_flags_and_provider_fields():
    row = {
        "flight_iata": "DL123",
        "airline_iata": "DL",
        "dep_iata": "MCO",
        "arr_iata": "DEN",
        "dep_time": "2026-02-20T10:00:00Z",
        "dep_estimated": "2026-02-20T11:00:00Z",
        "status": "cancelled",
    }
    out = flights.normalize_flight_row("MCO", "departure", "2026-02-20T09:00:00+00:00", row)
    assert out["provider"] == "AIRLABS"
    assert out["cancelled"] == 1
    assert out["diverted"] == 0
    assert out["delay_minutes"] == 60.0
    assert out["ident"] == "DL123"
