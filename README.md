# MCO vs DEN Airport Operations Dashboard

Capstone project comparing Orlando (MCO) vs Denver (DEN) with live operational restrictions, live traffic load, and airline delay impact.

## Overview

This project tests a practical hypothesis:

> Is MCO performing worse than DEN in ways not fully explained by traffic volume alone?

To evaluate that, the pipeline continuously collects and visualizes:
- FAA operational restrictions (delay programs, ground stops, closures)
- Live airspace traffic snapshots near each airport
- Flight-level airline delay/cancel/diversion signals

The hypothesis view also highlights when DEN is handling higher load but still delivering better delay efficiency.

## Tech Stack

- Python 3.12
- Streamlit + Plotly + Pandas
- SQLite (`data/aviation.db`)

## Data Sources

- FAA NASStatus API
- ADSB.lol (live traffic)
- AirLabs Delay API

## Project Structure

- `dashboard/app.py`: Streamlit dashboard
- `dashboard/content.py`: dashboard tab/help copy separated from app logic
- `src/db.py`: schema/bootstrap
- `src/collect_delays.py`: FAA collector
- `src/collect_traffic.py`: traffic collector
- `src/collect_flights.py`: AirLabs collector
- `migrations/*.sql`: schema updates
- `scripts/*.sh`: scheduled collector wrappers
- `tests/test_basic.py`: parser/scoring unit tests
- `API.md`: source-to-storage API contract and handoff spec

## Quick Start

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set your AirLabs key in `.env`:

```env
AIRLABS_API_KEY=your_key_here
AIRLABS_AIRPORTS=MCO,DEN
```

Initialize DB:

```bash
.venv/bin/python src/db.py
sqlite3 data/aviation.db ".read migrations/002_add_flight_snapshots.sql"
sqlite3 data/aviation.db ".read migrations/003_provider_source_schema.sql"
sqlite3 data/aviation.db ".read migrations/004_add_delay_legacy_columns.sql"
```

Run collectors once:

```bash
.venv/bin/python src/collect_delays.py
.venv/bin/python src/collect_traffic.py
.venv/bin/python src/collect_flights.py
```

Start dashboard:

```bash
.venv/bin/streamlit run dashboard/app.py
```

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Then run equivalent commands with `.venv\Scripts\python` and `.venv\Scripts\streamlit`.

## Dashboard Sections

- Dashboard Overview
- About This Project
- Calculation Details

### About This Project
- States the central MCO vs DEN question and hypothesis.
- Lists FAA, traffic, and AirLabs data sources.
- Documents collection cadence and guardrails:
  - FAA/Traffic: every 10 minutes
  - AirLabs: strict per-airport 2-hour minimum call interval, only during each airport's local 9 AM-11 PM window
- Notes readability-focused dashboard simplifications (daily-focused airline trends and a single combined weekday timing chart).

### Calculation Details
- Defines all core formulas (delay severity, airline severity, traffic load, operational stress).
- Explains ratio logic in Hypothesis Check.
- Confirms cross-airport hypothesis ratios are aligned by shared airport-local clock slots (for example, DEN 9 AM vs MCO 9 AM).
- Uses FAA downtime impact as the operational core metric (`downtime_per_100_load`).
- Applies minimum sample-size quality gates before showing verdicts.
- Reports bootstrap 95% confidence intervals and Low/Medium/High confidence tags.
- Uses reliability-weighted combined core evidence (not a simple equal average).
- Uses a Decision Summary first (two primary metrics + top-line verdict), with secondary metrics kept in supporting context.
- Documents DEN outperformance callouts when DEN carries higher load but remains more efficient.
- FAA Status History now emphasizes:
  - Restriction Snapshot Rate
  - Most Common Restriction
  - Peak Active Restrictions
  - Daily restriction-rate and daily-peak charts
- Airline Delay Impact now emphasizes daily views:
  - Daily Airline Delay Severity Index
  - Daily Longest Airline Delay (robustly summarized from snapshot maxima)
  - Daily Airline Cancellation Rate Comparison
- Delay Timing Breakdown now uses a single combined FAA+airline weekday chart (half-hour timing view removed for readability).

### How To Read This Dashboard (inside Dashboard Overview)
- Explains what each metric means and how to interpret comparisons.
- Includes cadence notes so users do not misread stale timestamps as failed collection.
- Notes that MCO vs DEN comparisons are made on matched airport-local time slots.
- Notes that verdicts can be withheld if quality gates are not met.
- Read Decision Summary first; use Supporting Context for drill-down.
- Clarifies that manual sync can run collectors immediately and can force an on-demand AirLabs call.
- Notes that the timing section is intentionally simplified to reduce skew/noise in interpretation.

## Tests

```bash
.venv/bin/pytest -q
```

Current tests are deterministic parser/scoring checks and do not call live APIs.

## Scheduling (Cron)

```cron
*/10 * * * * /path/to/project/scripts/collect_traffic.sh
*/10 * * * * /path/to/project/scripts/collect_delays.sh
*/10 * * * * /path/to/project/scripts/collect_flights.sh
```

- Traffic and FAA: every 10 minutes
- AirLabs script: runs every 10 minutes, but collector self-gates to:
  - each airport's local 9 AM-11 PM window
  - strict 2-hour minimum between AirLabs API call attempts per airport
- Manual dashboard sync can force an immediate AirLabs call for on-demand refresh

## Troubleshooting

### Dashboard shows no data

- Run collectors manually at least once.
- Confirm `data/aviation.db` exists and migrations were applied.

### AirLabs collector fails

- Confirm `AIRLABS_API_KEY` is set in `.env`.
- Verify API quota/limits.

### IDE shows stubborn pandas warnings

PyCharm can produce false positives on heavy chained pandas expressions (for example DataFrame/Series overload confusion). Runtime checks are the source of truth here:

```bash
.venv/bin/python -m py_compile dashboard/app.py
.venv/bin/pytest -q
```

## Known Limitations

- FAA severity and airline delay severity measure different concepts and should be interpreted together.
- Single snapshots are noisy; trends and repeated observations are more meaningful.
- Upstream API payloads can change and may require parser maintenance.

## Optional: Reset Database

```bash
rm -f data/aviation.db
.venv/bin/python src/db.py
sqlite3 data/aviation.db ".read migrations/002_add_flight_snapshots.sql"
sqlite3 data/aviation.db ".read migrations/003_provider_source_schema.sql"
sqlite3 data/aviation.db ".read migrations/004_add_delay_legacy_columns.sql"
```
