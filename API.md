# API.md - External API Integration and Storage Contract

This document is a deep handoff spec for how this project calls external APIs, how responses are normalized, and exactly how data is stored in SQLite.

It is written to let a new engineer answer, with confidence:
- What API endpoints are being called?
- With what parameters and cadence?
- What response fields are used?
- How are those fields transformed?
- Which tables/columns receive the data?
- What deduplication and throttling rules are in place?
- How can I verify each stage quickly?

---

## 1) System at a Glance

### 1.1 Data sources

The project currently ingests three external feeds:

1. **FAA NASStatus** (XML)
- Endpoint: `https://nasstatus.faa.gov/api/airport-status-information`
- Used by: `src/collect_delays.py`
- Output tables: `delay_snapshots`, `faa_events`

2. **ADSB.lol** (JSON)
- Endpoint template: `https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist_nm}`
- Used by: `src/collect_traffic.py`
- Output table: `traffic_snapshots`

3. **AirLabs delays** (JSON)
- Endpoint: `https://airlabs.co/api/v9/delays`
- Used by: `src/collect_flights.py`
- Output table: `flight_snapshots`

### 1.2 Target airports

Collectors are scoped to:
- `MCO`
- `DEN`

### 1.3 Runtime scheduling

The wrappers in `scripts/` are intended for cron and include lockfile protection:
- `scripts/collect_delays.sh`
- `scripts/collect_traffic.sh`
- `scripts/collect_flights.sh`

Current common cron pattern (example):
- `*/10 * * * *` for each collector script

Important nuance:
- FAA and ADSB calls are made each script run.
- AirLabs collector script may run every 10 minutes, but API calls are self-throttled to **minimum 120 minutes per airport** and **only during local 9:00-23:00** unless forced manually.

---

## 2) Execution Flow and Files

### 2.1 Main code paths

- DB bootstrap/schema: `src/db.py`
- FAA collector: `src/collect_delays.py`
- Traffic collector: `src/collect_traffic.py`
- Flight collector: `src/collect_flights.py`
- Dashboard manual sync trigger: `dashboard/app.py` (`run_manual_sync_collectors`)

### 2.2 Persistence location

- SQLite DB file: `data/aviation.db`

### 2.3 State and logs

- AirLabs call-attempt state files:
  - `data/collector_state/airlabs_last_call_MCO.txt`
  - `data/collector_state/airlabs_last_call_DEN.txt`
- Script logs:
  - `logs/delays.log`
  - `logs/traffic.log`
  - `logs/flights.log`

---

## 3) FAA NASStatus Integration

## 3.1 Request contract

Collector: `src/collect_delays.py`

- Method: `GET`
- URL: `https://nasstatus.faa.gov/api/airport-status-information`
- Timeout: `30s` (`TIMEOUT_SECONDS = 30`)
- Auth: none in current implementation

Failure behavior:
- Non-200 returns raise `RuntimeError` with status and first 300 chars.

## 3.2 Response shape used

The collector parses XML using `xml.etree.ElementTree` and is tolerant to tag naming variants.

Top-level fields used:
- `Update_Time` or `UpdateTime`

Per-delay sections:
- loops through `<Delay_type>` blocks
- reads section `<Name>` as event category (e.g., Ground Delay, Ground Stop, etc.)

Per-airport event details (from tags encountered under each section):
- `ARPT` airport code
- `Reason`
- `Avg`
- `Min`
- `Max`
- `Trend`
- `Start`
- `Reopen`
- `End_Time`
- optional nested `Arrival_Departure` with `Type`, `Min`, `Max`, `Trend`

## 3.3 Transformations

### 3.3.1 Airport filtering
Only events for `MCO` and `DEN` are kept.

### 3.3.2 Duration parsing
`_parse_duration_minutes()` accepts text like:
- `"16 minutes"`
- `"1 hour 20 minutes"`
- phrases containing average/min keywords

Fallback chain for event minutes:
1. parsed `average`
2. parsed `min`
3. parsed `Arrival_Departure Min`

### 3.3.3 Severity mapping
Severity assigned from section name:
- contains `ground stop` -> `4.0`
- contains `ground delay` -> `3.0`
- contains `arrival/departure delay` -> `2.0`
- contains `closure` -> `5.0`
- otherwise -> `1.0`

### 3.3.4 Snapshot summary per airport
For each airport at a collection timestamp:
- `status`: semicolon-joined distinct event type names
- `delay_index`: max event severity
- `delay_median_minutes`: mean of parsed event minutes (name is historical)

No-event case:
- `status = "No active FAA NAS restriction listed."`
- `delay_index = 0.0`
- `delay_median_minutes = NULL`

## 3.4 Storage writes

### 3.4.1 `delay_snapshots` (summary row per airport per run)
Insert mode: `INSERT OR IGNORE`

Written columns:
- `airport_code`
- `collected_at` (UTC ISO string)
- `source = 'FAA_NASSTATUS'`
- `delay_index`
- `delay_median_minutes`
- `faa_update_time`
- `faa_event_count`
- `raw_json`

`raw_json` structure (summary envelope):
```json
{
  "source": "FAA_NASSTATUS",
  "collected_at": "...",
  "airport": { ...parsed airport payload... },
  "xml_head": "first 5000 chars of XML"
}
```

### 3.4.2 `faa_events` (detail row per event)
Insert mode: plain `INSERT` (no dedupe constraint)

Written columns:
- `airport_code`
- `collected_at`
- `event_type`
- `reason`
- `min_delay_minutes`
- `max_delay_minutes`
- `trend`
- `severity`
- `raw_json` (event payload)

---

## 4) ADSB.lol Traffic Integration

## 4.1 Request contract

Collector: `src/collect_traffic.py`

For each airport area:
- Method: `GET`
- URL template: `https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist_nm}`
- Timeout: `25s`
- Auth: none in current implementation

Airport query areas:
- MCO: lat `28.4312`, lon `-81.3081`, radius `35` nm
- DEN: lat `39.8561`, lon `-104.6737`, radius `35` nm

Failure behavior:
- Non-200 raises `RuntimeError` with status and first 250 chars.

## 4.2 Response shape used

Aircraft list is extracted from first matching key:
1. `ac`
2. `aircraft`
3. `states`

Each row can be dict-style or list-style.

### Dict-style fields interpreted
- `gnd` or `on_ground`
- speed: `gs` else `speed`
- altitude: `alt_baro` else `alt_geom` else `altitude`

Ground inference rules:
- altitude string `"ground"` -> on-ground true
- if no explicit ground flag:
  - altitude > 300 ft -> airborne
  - speed >= 80 -> airborne
  - speed < 50 -> on-ground

### List-style fallback (OpenSky-like)
- index 8: `on_ground`
- index 9: velocity
- index 13 geo altitude else index 7 baro altitude

## 4.3 Transformations

Computed summary per airport per run:
- `aircraft_count = len(rows)`
- `airborne_count`
- `on_ground_count`
- `altitude_median`
- `altitude_p90`
- `velocity_median`
- `velocity_p90`

Percentile is linear interpolation on sorted values.

## 4.4 Storage writes

Table: `traffic_snapshots`
Insert mode: `INSERT OR IGNORE`

Written columns:
- `airport_code`
- `collected_at` (UTC ISO)
- `source = 'ADSB_LOL'`
- `aircraft_count`
- `airborne_count`
- `on_ground_count`
- `altitude_median`
- `altitude_p90`
- `velocity_median`
- `velocity_p90`
- `query_meta`
- `raw_json`

`query_meta` structure:
```json
{
  "url_template": "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist_nm}",
  "area": {"lat": ..., "lon": ..., "dist_nm": ...}
}
```

`raw_json` stores debug metadata (not full aircraft payload), including:
- source
- airport
- collected_at
- area
- response_keys
- reported_count

---

## 5) AirLabs Delays Integration

## 5.1 Request contract

Collector: `src/collect_flights.py`

Base endpoint:
- `GET https://airlabs.co/api/v9/delays`

Per airport, collector performs two calls when allowed:
1. departures call
2. arrivals call

Request params:
- `api_key` (from env `AIRLABS_API_KEY`)
- `type` in `{departures, arrivals}`
- `limit` (`AIRLABS_LIMIT`, default `100`)
- one airport filter:
  - departures: `dep_iata=<airport>`
  - arrivals: `arr_iata=<airport>`

Timeout:
- `AIRLABS_TIMEOUT_SECONDS` default `30`

Inter-request pause:
- `AIRLABS_REQUEST_PAUSE_SECONDS` default `0.5`

Success checks:
- HTTP status must be 200
- payload must not contain `error`

Flights array fallback:
- prefer `response`
- else `data`
- else `[]`

## 5.2 Throttle and collection guardrails

Per-airport gating in `should_collect_for_airport()`:

1. **Force override**
- If `AIRLABS_FORCE_SYNC` is truthy (`1/true/yes/on`), collect immediately.

2. **Local time window**
- airport local time must be between `AIRLABS_LOCAL_START_HOUR` and `AIRLABS_LOCAL_END_HOUR`
- defaults: `9` to `23` (inclusive by hour)

3. **Minimum interval**
- default `AIRLABS_COLLECTION_INTERVAL_MINUTES = 120`
- reference point is:
  - last API call attempt time from state file, or
  - if missing, last stored snapshot time in DB

State files used:
- `data/collector_state/airlabs_last_call_<AIRPORT>.txt`

Important detail:
- collector records API attempt timestamp **before** performing departures/arrivals calls for that airport.
- if a direction call fails afterward, interval still counts from that attempt.

## 5.3 Flight normalization rules

Each upstream flight dict is normalized into one row.

Identity fields:
- `provider = AIRLABS`
- `external_flight_id` generated via SHA1 over stable field bundle
- `fa_flight_id` set equal to `external_flight_id` for backward compatibility

Common selected fields:
- `ident`: first of `flight_iata`, `flight_icao`, `flight_number`
- `airline_code`: first of `airline_iata`, `airline_icao`
- `origin`: first of `dep_iata`, `dep_icao`
- `destination`: first of `arr_iata`, `arr_icao`
- `status` lowercased

Times:
- departure row uses dep_* fields
- arrival row uses arr_* fields

`delay_minutes` fallback order:
- departure: `dep_delayed`/`dep_delay`/`delayed`
- arrival: `arr_delayed`/`arr_delay`/`delayed`
- if absent, compute `(actual - scheduled)`
- else `(estimated - scheduled)`

Flags:
- `cancelled = 1` if status contains `cancel`
- `diverted = 1` if status contains `divert`

## 5.4 Storage writes

Table: `flight_snapshots`
Insert mode: `INSERT OR IGNORE`

Written columns:
- `collected_at`
- `airport_code`
- `direction`
- `provider`
- `external_flight_id`
- `fa_flight_id`
- `ident`
- `airline_code`
- `status`
- `origin`
- `destination`
- `scheduled_time`
- `estimated_time`
- `actual_time`
- `delay_minutes`
- `cancelled`
- `diverted`
- `raw_json` (`{"source":"AIRLABS","flight":{...}}`)

---

## 6) SQLite Storage Contract (Actual Schema)

The following reflects the live schema in `data/aviation.db` (via `PRAGMA table_info`).

## 6.1 `delay_snapshots`

Purpose:
- airport-level FAA snapshot summary (and legacy delay columns retained for compatibility)

Columns:
- `id INTEGER PK`
- `airport_code TEXT NOT NULL`
- `collected_at TEXT NOT NULL`
- `delay_mean_minutes REAL`
- `delay_median_minutes REAL`
- `delay_p90_minutes REAL`
- `delay_p50_minutes REAL`
- `delay_index REAL`
- `total_flights INTEGER`
- `delayed_flights INTEGER`
- `cancelled_flights INTEGER`
- `diverted_flights INTEGER`
- `raw_json TEXT`
- `source TEXT NOT NULL DEFAULT 'UNKNOWN'`
- `faa_update_time TEXT`
- `faa_event_count INTEGER`
- `window_from_utc TEXT`
- `window_to_utc TEXT`
- `dep_total INTEGER`
- `dep_qualified_total INTEGER`
- `dep_cancelled INTEGER`
- `dep_median_delay_minutes REAL`
- `dep_delay_index REAL`
- `arr_total INTEGER`
- `arr_qualified_total INTEGER`
- `arr_cancelled INTEGER`
- `arr_median_delay_minutes REAL`
- `arr_delay_index REAL`

Uniqueness and indexes:
- UNIQUE `(airport_code, collected_at)`
- index `(airport_code, collected_at)`
- index `(source, collected_at)`

## 6.2 `faa_events`

Purpose:
- one row per FAA event observed at a snapshot timestamp

Columns:
- `id INTEGER PK`
- `airport_code TEXT NOT NULL`
- `collected_at TEXT NOT NULL`
- `event_type TEXT`
- `reason TEXT`
- `min_delay_minutes REAL`
- `max_delay_minutes REAL`
- `trend TEXT`
- `severity REAL`
- `raw_json TEXT`

Indexes:
- index `(airport_code, collected_at)`

## 6.3 `traffic_snapshots`

Purpose:
- airport-level airspace traffic summary per poll

Columns:
- `id INTEGER PK`
- `airport_code TEXT NOT NULL`
- `collected_at TEXT NOT NULL`
- `aircraft_count INTEGER NOT NULL`
- `airborne_count INTEGER`
- `on_ground_count INTEGER`
- `altitude_median REAL`
- `altitude_p90 REAL`
- `velocity_median REAL`
- `velocity_p90 REAL`
- `raw_json TEXT`
- `source TEXT NOT NULL DEFAULT 'UNKNOWN'`
- `query_meta TEXT`

Uniqueness and indexes:
- UNIQUE `(airport_code, collected_at)`
- index `(airport_code, collected_at)`
- index `(source, collected_at)`

## 6.4 `flight_snapshots`

Purpose:
- normalized flight-level delay/cancellation/diversion rows

Columns:
- `id INTEGER PK`
- `collected_at TEXT NOT NULL`
- `airport_code TEXT NOT NULL`
- `direction TEXT NOT NULL`
- `fa_flight_id TEXT NOT NULL`
- `ident TEXT`
- `origin TEXT`
- `destination TEXT`
- `scheduled_time TEXT`
- `estimated_time TEXT`
- `actual_time TEXT`
- `delay_minutes REAL`
- `cancelled INTEGER DEFAULT 0`
- `diverted INTEGER DEFAULT 0`
- `raw_json TEXT`
- `provider TEXT NOT NULL DEFAULT 'UNKNOWN'`
- `external_flight_id TEXT`
- `airline_code TEXT`
- `status TEXT`

Uniqueness and indexes:
- legacy UNIQUE autoindex `(fa_flight_id, direction)`
- unique index `(provider, external_flight_id, direction)`
- index `(airport_code, collected_at)`
- index `(direction, collected_at)`

Operational implication:
- There are effectively two uniqueness constraints in play for flight rows. The normalized code writes both `fa_flight_id` and `external_flight_id` as the same generated ID, so constraints align.

---

## 7) Dashboard Data Consumption Contract

The dashboard reads directly from SQLite and expects these fields:

- FAA summary (`delay_snapshots`):
  - `airport_code`, `collected_at`, `source`, `delay_index`, `delay_median_minutes`,
  - `dep_total`, `arr_total`, `dep_delay_index`, `dep_median_delay_minutes`,
  - `arr_delay_index`, `arr_median_delay_minutes`,
  - `faa_update_time`, `faa_event_count`, `raw_json` status extraction

- FAA details (`faa_events`):
  - `airport_code`, `collected_at`, `min_delay_minutes`, `max_delay_minutes`

- Traffic (`traffic_snapshots`):
  - `airport_code`, `collected_at`, `aircraft_count`, `airborne_count`, `on_ground_count`, `altitude_median`, `velocity_median`

- Flights (`flight_snapshots`):
  - `airport_code`, `collected_at`, `delay_minutes`, `cancelled`, `diverted`

Manual sync in dashboard (`Run Manual Sync Now`) runs:
1. FAA collector
2. Traffic collector
3. Flight collector with env override `AIRLABS_FORCE_SYNC=1`

This means manual sync intentionally bypasses normal AirLabs time-window and 2-hour gating.

---

## 8) Data Lineage by Metric

### 8.1 FAA Delay Severity Index (snapshot)
- Source: FAA XML event categories
- Transform: category -> severity mapping, take max
- Stored: `delay_snapshots.delay_index`

### 8.2 FAA event delays
- Source: event `Min`/`Max` strings
- Transform: duration parser to float minutes
- Stored: `faa_events.min_delay_minutes`, `faa_events.max_delay_minutes`

### 8.3 Traffic load
- Source: ADSB aircraft list length
- Transform: count rows
- Stored: `traffic_snapshots.aircraft_count`

### 8.4 Airline delay minutes
- Source: AirLabs direct delay fields or derived from schedule vs estimate/actual times
- Transform: fallback chain in `compute_delay_minutes`
- Stored: `flight_snapshots.delay_minutes`

### 8.5 Airline cancellation/diversion
- Source: AirLabs status string
- Transform: substring match (`cancel`, `divert`)
- Stored: `flight_snapshots.cancelled`, `flight_snapshots.diverted`

---

## 9) Environment Variables Reference

From `.env.example` and code:

### AirLabs
- `AIRLABS_API_KEY`
- `AIRLABS_AIRPORTS` (default `MCO,DEN`)
- `AIRLABS_BASE_URL` (default `https://airlabs.co/api/v9/delays`)
- `AIRLABS_TIMEOUT_SECONDS` (default `30`)
- `AIRLABS_REQUEST_PAUSE_SECONDS` (default `0.5`)
- `AIRLABS_LIMIT` (default `100`)
- `AIRLABS_LOCAL_START_HOUR` (default `9`)
- `AIRLABS_LOCAL_END_HOUR` (default `23`)
- `AIRLABS_COLLECTION_INTERVAL_MINUTES` (default `120`)
- `AIRLABS_STATE_DIR` (default `data/collector_state`)
- `AIRLABS_FORCE_SYNC` (manual override)

### ADSB
- `ADSBLOL_URL_TEMPLATE`

---

## 10) Idempotency, Dedupe, and Failure Semantics

## 10.1 FAA summary and traffic snapshots
- Use `INSERT OR IGNORE` with unique `(airport_code, collected_at)`.
- Duplicate timestamps for same airport are ignored.

## 10.2 FAA events
- No unique constraint by default.
- Re-running the same FAA poll at identical timestamp would insert duplicate event rows unless prevented externally.

## 10.3 Flight snapshots
- Use `INSERT OR IGNORE` with unique constraints on identifiers.
- Generated `external_flight_id` stabilizes dedupe across repeated polls.

## 10.4 Error handling model
- Collectors generally fail fast on top-level request errors.
- AirLabs collector isolates failures by airport and direction; one failure does not abort all remaining pulls.

---

## 11) Verification Queries (Copy/Paste)

### 11.1 Latest rows by source
```sql
SELECT airport_code, collected_at, source, delay_index, faa_event_count
FROM delay_snapshots
ORDER BY collected_at DESC
LIMIT 10;
```

```sql
SELECT airport_code, collected_at, source, aircraft_count, airborne_count, on_ground_count
FROM traffic_snapshots
ORDER BY collected_at DESC
LIMIT 10;
```

```sql
SELECT airport_code, collected_at, direction, provider, ident, delay_minutes, cancelled, diverted, status
FROM flight_snapshots
ORDER BY collected_at DESC
LIMIT 20;
```

### 11.2 Check AirLabs call pacing state
```bash
cat data/collector_state/airlabs_last_call_MCO.txt
cat data/collector_state/airlabs_last_call_DEN.txt
```

### 11.3 Confirm flight uniqueness behavior
```sql
SELECT provider, external_flight_id, direction, COUNT(*)
FROM flight_snapshots
GROUP BY provider, external_flight_id, direction
HAVING COUNT(*) > 1;
```

### 11.4 Inspect FAA event detail richness
```sql
SELECT airport_code, collected_at, event_type, reason, min_delay_minutes, max_delay_minutes, severity
FROM faa_events
ORDER BY collected_at DESC
LIMIT 50;
```

---

## 12) Known Gaps / Important Handoff Notes

1. `delay_median_minutes` in FAA summary is currently computed as arithmetic mean of event minutes, despite its name.
2. `faa_events` has no dedupe key; duplicates are possible if same snapshot is inserted more than once.
3. AirLabs attempt timestamp is recorded before per-direction calls, so a failed call still advances throttle window.
4. Traffic collector stores summary/debug metadata, not full raw aircraft payload.
5. Dashboard behavior depends on legacy columns still present in `delay_snapshots`.

---

## 13) Change Checklist for Future API Swaps

If replacing any provider, update all of:
1. Collector request contract and parser (`src/collect_*.py`)
2. Normalization mapping to current DB columns
3. Dedupe keys/uniqueness assumptions
4. Dashboard field expectations in `dashboard/app.py`
5. `.env.example` variable docs
6. This `API.md`

