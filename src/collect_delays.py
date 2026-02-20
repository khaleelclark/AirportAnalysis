import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Optional

import requests

from db import create_tables, get_connection

FAA_URL = "https://nasstatus.faa.gov/api/airport-status-information"
AIRPORTS = ("MCO", "DEN")
TIMEOUT_SECONDS = 30


def _tag_name(tag: str) -> str:
    return tag.split("}")[-1].strip().lower()


def _first_text(elem: ET.Element, candidate_tags: tuple[str, ...]) -> Optional[str]:
    wanted = {t.lower() for t in candidate_tags}
    for child in list(elem):
        if _tag_name(child.tag) in wanted and child.text:
            text = child.text.strip()
            if text:
                return text
    return None


def _parse_minutes(text: Optional[str]) -> Optional[float]:
    if not text:
        return None

    t = text.lower()

    # Prefer explicit average markers if present.
    avg = re.search(r"\b(?:avg\.?|average)\s*(\d{1,3})\s*(?:min|mins|minute|minutes)\b", t)
    if avg:
        return float(avg.group(1))

    # Fall back to first minute expression.
    m = re.search(r"\b(\d{1,3})\s*(?:min|mins|minute|minutes)\b", t)
    if m:
        return float(m.group(1))

    return None


def _parse_duration_minutes(text: Optional[str]) -> Optional[float]:
    if not text:
        return None

    t = text.lower()
    hours_match = re.search(r"(\d+)\s*hour", t)
    minutes_match = re.search(r"(\d+)\s*minute", t)

    hours = int(hours_match.group(1)) if hours_match else 0
    minutes = int(minutes_match.group(1)) if minutes_match else 0

    if hours == 0 and minutes == 0:
        return _parse_minutes(text)

    return float((hours * 60) + minutes)


def fetch_faa_xml() -> str:
    resp = requests.get(FAA_URL, timeout=TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise RuntimeError(f"FAA NASStatus error {resp.status_code}: {resp.text[:300]}")
    return resp.text


def parse_airports(xml_text: str) -> tuple[dict[str, dict[str, Any]], str]:
    root = ET.fromstring(xml_text)
    update_time = _first_text(root, ("Update_Time", "UpdateTime")) or ""
    out: dict[str, dict[str, Any]] = {code: {"airport_code": code, "events": []} for code in AIRPORTS}

    for dtype in root.findall("Delay_type"):
        section_name = (_first_text(dtype, ("Name",)) or "").strip()

        for elem in dtype.iter():
            tag = _tag_name(elem.tag)
            if tag not in {"ground_delay", "program", "delay", "airport"}:
                continue

            code = _first_text(elem, ("ARPT",))
            if not code:
                continue
            code = code.upper().strip()
            if code not in out:
                continue

            reason = _first_text(elem, ("Reason",)) or ""
            avg = _first_text(elem, ("Avg",))
            min_delay = _first_text(elem, ("Min",))
            max_delay = _first_text(elem, ("Max",))
            trend = _first_text(elem, ("Trend",))
            start = _first_text(elem, ("Start",))
            reopen = _first_text(elem, ("Reopen",))
            end_time = _first_text(elem, ("End_Time",))

            arr_dep = elem.find("Arrival_Departure")
            arr_dep_type = arr_dep.get("Type") if arr_dep is not None else ""
            arr_dep_min = _first_text(arr_dep, ("Min",)) if arr_dep is not None else None
            arr_dep_max = _first_text(arr_dep, ("Max",)) if arr_dep is not None else None
            arr_dep_trend = _first_text(arr_dep, ("Trend",)) if arr_dep is not None else None

            minutes = (
                _parse_duration_minutes(avg)
                or _parse_duration_minutes(min_delay)
                or _parse_duration_minutes(arr_dep_min)
            )

            if "ground stop" in section_name.lower():
                severity = 4.0
            elif "ground delay" in section_name.lower():
                severity = 3.0
            elif "arrival/departure delay" in section_name.lower():
                severity = 2.0
            elif "closure" in section_name.lower():
                severity = 5.0
            else:
                severity = 1.0

            event = {
                "type": section_name,
                "reason": reason,
                "avg": avg,
                "min": min_delay or arr_dep_min,
                "max": max_delay or arr_dep_max,
                "trend": trend or arr_dep_trend,
                "arr_dep_type": arr_dep_type,
                "start": start,
                "reopen": reopen,
                "end_time": end_time,
                "minutes": minutes,
                "severity": severity,
            }
            out[code]["events"].append(event)

    for code, payload in out.items():
        events = payload["events"]
        if not events:
            payload["status"] = "No active FAA NAS restriction listed."
            payload["delay_index"] = 0.0
            payload["delay_median_minutes"] = None
            continue

        payload["status"] = "; ".join(sorted({e["type"] for e in events if e["type"]}))
        payload["delay_index"] = max(e["severity"] for e in events)
        mins = [e["minutes"] for e in events if e["minutes"] is not None]
        payload["delay_median_minutes"] = (sum(mins) / len(mins)) if mins else None

    return out, update_time


def insert_snapshot(airport_code: str, collected_at: str, payload: dict[str, Any], xml_head: str):
    summary_json = {
        "source": "FAA_NASSTATUS",
        "collected_at": collected_at,
        "airport": payload,
        "xml_head": xml_head,
    }

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO delay_snapshots (
            airport_code,
            collected_at,
            source,
            delay_index,
            delay_median_minutes,
            faa_update_time,
            faa_event_count,
            raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            airport_code,
            collected_at,
            "FAA_NASSTATUS",
            payload.get("delay_index"),
            payload.get("delay_median_minutes"),
            payload.get("update_time"),
            len(payload.get("events", [])),
            json.dumps(summary_json),
        ),
    )
    conn.commit()
    conn.close()


def insert_faa_events(airport_code: str, collected_at: str, events: list[dict[str, Any]]):
    if not events:
        return

    conn = get_connection()
    cur = conn.cursor()

    for event in events:
        cur.execute(
            """
            INSERT INTO faa_events (
                airport_code,
                collected_at,
                event_type,
                reason,
                min_delay_minutes,
                max_delay_minutes,
                trend,
                severity,
                raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                airport_code,
                collected_at,
                event.get("type"),
                event.get("reason"),
                _parse_duration_minutes(event.get("min")),
                _parse_duration_minutes(event.get("max")),
                event.get("trend"),
                event.get("severity"),
                json.dumps(event),
            ),
        )

    conn.commit()
    conn.close()



def main():
    create_tables()

    collected_at = datetime.now(timezone.utc).isoformat()
    print(f"\\nCollecting FAA NASStatus delay snapshots at {collected_at}\\n")

    xml_text = fetch_faa_xml()
    parsed, update_time = parse_airports(xml_text)
    xml_head = xml_text[:5000]

    for airport in AIRPORTS:
        payload = parsed[airport]
        payload["update_time"] = update_time
        insert_snapshot(airport, collected_at, payload, xml_head)
        insert_faa_events(airport, collected_at, payload.get("events", []))

        print(
            f"[OK] {airport}: delay_median_minutes={payload.get('delay_median_minutes')} "
            f"severity_index={payload.get('delay_index')}"
        )

    print("\\nDone.\\n")


if __name__ == "__main__":
    main()
