import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import requests
import xml.etree.ElementTree as ET

DB_PATH = Path("data/aviation.db")
FAA_URL = "https://nasstatus.faa.gov/api/airport-status-information"

AIRPORTS = {"MCO", "DEN"}  # IATA codes


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_delay_minutes(text: Optional[str]) -> Optional[float]:
    """
    Attempts to extract an average delay in minutes from free text like:
      "avg. 33 mins." / "average delay 26 minutes" / etc.
    Returns None if not found.
    """
    if not text:
        return None
    t = text.lower()

    # common patterns: "avg. 33 mins", "avg 33 minutes", "average 33 mins"
    m = re.search(r"\bavg\.?\s*(\d+)\s*(min|mins|minutes)\b", t)
    if not m:
        m = re.search(r"\baverage\s*(\d+)\s*(min|mins|minutes)\b", t)
    if not m:
        m = re.search(r"\b(\d+)\s*(min|mins|minutes)\b", t)

    if not m:
        return None
    return float(m.group(1))


def severity_score(status_text: str) -> int:
    """
    Very simple severity heuristic -> 0..5.
    You can adjust later once you see real text patterns.
    """
    t = (status_text or "").lower()

    if "closed" in t:
        return 5
    if "ground stop" in t:
        return 4
    if "ground delay program" in t or "gdp" in t:
        return 3
    if "delay" in t:
        return 2
    if "normal" in t or "no delays" in t:
        return 0
    return 1


def fetch_faa_airport_status_xml() -> str:
    r = requests.get(FAA_URL, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"FAA NASStatus error {r.status_code}: {r.text[:200]}")
    return r.text


def parse_airports_from_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)

    def tag_ends(elem, suffix: str) -> bool:
        # Handles namespaces: "{ns}Airport" -> "Airport"
        t = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        return t.lower() == suffix.lower()

    def child_text(elem, wanted: list[str]) -> Optional[str]:
        # Search children by tag suffix (namespace-safe)
        for c in list(elem):
            ct = c.tag.split("}")[-1] if "}" in c.tag else c.tag
            if ct.lower() in [w.lower() for w in wanted]:
                if c.text:
                    return c.text.strip()
        return None

    airports_out = []

    # Find ANY element whose tag ends with "Airport" (namespace-safe)
    for ap in root.iter():
        if not tag_ends(ap, "Airport"):
            continue

        code = child_text(ap, ["ARPT", "IATA", "iata", "airportCode", "AirportCode"])
        if not code:
            continue
        code = code.strip().upper()

        name = child_text(ap, ["Name", "ARPT_NAME", "airportName", "AirportName"]) or ""
        status = child_text(ap, ["Status", "STATUS", "airportStatus", "AirportStatus"]) or ""
        reason = child_text(ap, ["Reason", "REASON", "DelayReason", "delayReason"]) or ""
        delay_text = child_text(ap, ["Delay", "DELAY", "DelayText", "delayText", "AvgDelay"]) or ""

        airports_out.append(
            {
                "airport_code": code,
                "airport_name": name.strip(),
                "status": status.strip(),
                "reason": reason.strip(),
                "delay_text": delay_text.strip(),
            }
        )

    return airports_out



def insert_snapshot(airport_code: str, collected_at: str, delay_min: Optional[float], idx: Optional[float], raw: Dict[str, Any]):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO delay_snapshots (
            airport_code,
            collected_at,
            delay_median_minutes,
            delay_index,
            raw_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (airport_code, collected_at, delay_min, idx, json.dumps(raw)),
    )
    conn.commit()
    conn.close()


def main():
    collected_at = datetime.now(timezone.utc).isoformat()
    print(f"\nCollecting FAA NASStatus snapshots at {collected_at}\n")

    xml_text = fetch_faa_airport_status_xml()
    airports = parse_airports_from_xml(xml_text)

    # Filter to our airports
    wanted = [a for a in airports if a["airport_code"] in AIRPORTS]

    if not wanted:
        # still store something for debugging
        print("No matching airport blocks found in FAA response. Saving raw XML snippet to help debug.")
        for code in AIRPORTS:
            insert_snapshot(code, collected_at, None, None, {"source": "FAA_NASSTATUS", "raw_xml_head": xml_text[:5000]})
        return

    for a in wanted:
        text_blob = " | ".join([a.get("status", ""), a.get("reason", ""), a.get("delay_text", "")]).strip()
        delay_min = parse_delay_minutes(text_blob)
        idx = float(severity_score(text_blob))

        insert_snapshot(
            a["airport_code"],
            collected_at,
            delay_min,
            idx,
            {"source": "FAA_NASSTATUS", "collected_at": collected_at, **a, "text_blob": text_blob},
        )
        print(f"[OK] {a['airport_code']}: delay_min={delay_min} severity_index={idx}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()
