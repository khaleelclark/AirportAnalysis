# MCO vs DEN Airport Operations Dashboard

Capstone project comparing Orlando (MCO) vs Denver (DEN) with live operational restrictions, live traffic load, and airline delay impact.

## Overview

This project tests a practical hypothesis:

> Is MCO performing worse than DEN in ways not fully explained by traffic volume alone?

To evaluate that, the pipeline continuously collects and visualizes:
- FAA operational restrictions (delay programs, ground stops, closures)
- Live airspace traffic snapshots near each airport
- Flight-level airline delay/cancel/diversion signals

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
- `src/db.py`: schema/bootstrap
- `src/collect_delays.py`: FAA collector
- `src/collect_traffic.py`: traffic collector
- `src/collect_flights.py`: AirLabs collector
- `migrations/*.sql`: schema updates
- `scripts/*.sh`: scheduled collector wrappers
- `tests/test_basic.py`: parser/scoring unit tests

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

Metric definitions and formulas are documented directly in the Calculation Details tab.

## Tests

```bash
.venv/bin/pytest -q
```

Current tests are deterministic parser/scoring checks and do not call live APIs.

## Scheduling (Cron)

```cron
*/10 * * * * /path/to/project/scripts/collect_traffic.sh
*/10 * * * * /path/to/project/scripts/collect_delays.sh
0 9-23/2 * * * /path/to/project/scripts/collect_flights.sh
```

- Traffic and FAA: every 10 minutes
- AirLabs: every 2 hours from 9 AM to 11 PM

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
