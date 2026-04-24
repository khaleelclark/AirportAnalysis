# MCO vs DEN Airport Operations Dashboard

Streamlit dashboard and data pipeline for comparing Orlando International (`MCO`) and Denver International (`DEN`) using:

- FAA restriction data
- live airspace traffic snapshots
- airline delay, cancellation, and diversion data

The main question is simple:

> Is MCO performing worse than DEN after accounting for how busy each airport is?

This README is written for someone who needs to clone, run, and deploy the project without reverse-engineering the codebase first.

## What This Repository Contains

- `dashboard/app.py`: main Streamlit app
- `dashboard/content.py`: help/about/calculation copy used by the dashboard
- `src/db.py`: SQLite schema bootstrap
- `src/collect_delays.py`: FAA collector
- `src/collect_traffic.py`: ADSB.lol traffic collector
- `src/collect_flights.py`: AirLabs collector
- `migrations/*.sql`: required schema migrations
- `scripts/*.sh`: cron-friendly collector wrappers
- `data/aviation.db`: included snapshot database
- `data/collector_state/`: AirLabs call-throttle state files
- `logs/`: collector and DB commit logs

## Runtime Model

This project is designed for a small self-hosted deployment on a Linux VM, VPS, or always-on machine.

- The app reads from a local SQLite database at `data/aviation.db`.
- Collectors write into that same database on a schedule.
- The AirLabs collector also writes throttle state to `data/collector_state/`.
- Logs are written to `logs/`.
- The repository includes a database snapshot, so the dashboard can open immediately even before you collect fresh data.

Important deployment implication:

- the deployment target must have persistent writable storage
- the app and collectors should run from the repository root
- if you deploy multiple app instances against the same SQLite file, you are adding avoidable complexity

## Requirements

- Python `3.12`
- Git
- Git LFS
- SQLite CLI

Python dependencies are listed in `requirements.txt`:

- `requests`
- `pandas`
- `numpy`
- `streamlit`
- `plotly`
- `python-dotenv`
- `pytest`

## Environment Variables

Copy `.env.example` to `.env` and set the values you need.

Required for airline collection:

```env
AIRLABS_API_KEY=your_airlabs_api_key_here
```

Useful defaults already supported by the code:

```env
AIRLABS_AIRPORTS=MCO,DEN
AIRLABS_BASE_URL=https://airlabs.co/api/v9/delays
AIRLABS_TIMEOUT_SECONDS=30
AIRLABS_REQUEST_PAUSE_SECONDS=0.5
AIRLABS_LIMIT=100
ADSBLOL_URL_TEMPLATE=https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist_nm}
```

The AirLabs collector also supports these optional controls:

- `AIRLABS_LOCAL_START_HOUR`
- `AIRLABS_LOCAL_END_HOUR`
- `AIRLABS_COLLECTION_INTERVAL_MINUTES`
- `AIRLABS_STATE_DIR`
- `AIRLABS_FORCE_SYNC`

Notes:

- FAA and ADSB collection do not require API keys for the current endpoints.
- If `AIRLABS_API_KEY` is missing, `src/collect_flights.py` will fail.
- `AIRLABS_FORCE_SYNC=1` bypasses the normal local-time and interval gate for manual refreshes.

## Local Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd CapstoneProject
git lfs install
git lfs pull
```

### 2. Create a virtual environment

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Then set `AIRLABS_API_KEY` in `.env`.

### 4. Initialize the database

Run these commands from the repository root:

```bash
.venv/bin/python src/db.py
sqlite3 data/aviation.db ".read migrations/002_add_flight_snapshots.sql"
sqlite3 data/aviation.db ".read migrations/003_provider_source_schema.sql"
sqlite3 data/aviation.db ".read migrations/004_add_delay_legacy_columns.sql"
```

If you are on Windows, use the equivalent Python path and an installed `sqlite3` CLI.

### 5. Run the collectors once

```bash
.venv/bin/python src/collect_delays.py
.venv/bin/python src/collect_traffic.py
.venv/bin/python src/collect_flights.py
```

### 6. Start the dashboard

```bash
.venv/bin/streamlit run dashboard/app.py
```

Then open the local Streamlit URL shown in the terminal.

## Deployment Checklist

Use this checklist for a real deployment:

1. Clone the repo with Git LFS enabled.
2. Create `.venv` and install dependencies.
3. Create `.env` and set `AIRLABS_API_KEY`.
4. Initialize `data/aviation.db` and apply all migrations.
5. Confirm the following paths are writable:
   `data/`, `data/collector_state/`, and `logs/`
6. Run each collector once successfully.
7. Start the Streamlit app bound to the server interface.
8. Add cron entries for ongoing collection.
9. Verify the dashboard shows fresh timestamps in `Last Synced`.

## Production Run Command

For a simple server deployment:

```bash
.venv/bin/streamlit run dashboard/app.py --server.address 0.0.0.0 --server.port 8501
```

Recommended:

- run this behind a reverse proxy if exposing it publicly
- keep the working directory at the repository root
- use a process manager such as `systemd`, `supervisord`, or your platform equivalent

This repository does not currently include Docker files, systemd unit files, or infrastructure manifests. The app is still deployable as-is on a standard Linux host.

## Scheduling Collectors

The included shell scripts are cron-friendly and already:

- `cd` into the repo root
- activate `.venv`
- create `logs/`
- use `flock` when available to avoid overlapping runs

Example cron:

```cron
*/10 * * * * /path/to/project/scripts/collect_delays.sh
*/10 * * * * /path/to/project/scripts/collect_traffic.sh
*/10 * * * * /path/to/project/scripts/collect_flights.sh
15 0 * * * /path/to/project/scripts/commit_aviation_db.sh
```

What these do:

- FAA collector: every 10 minutes
- Traffic collector: every 10 minutes
- AirLabs wrapper: every 10 minutes, but the Python collector self-throttles by airport
- DB commit script: once per day

AirLabs throttle behavior:

- only calls during each airport's local collection window
- defaults to `9 AM` through `11 PM` local airport time
- enforces a minimum `120` minutes between call attempts per airport
- stores last-attempt state in `data/collector_state/`

## Database Notes

The repository includes `data/aviation.db` so the dashboard can render immediately.

- No API keys are stored in the database.
- The file is tracked with Git LFS.
- You can keep the included snapshot, or replace it with a fresh local database.

To rebuild from scratch:

```bash
rm -f data/aviation.db
.venv/bin/python src/db.py
sqlite3 data/aviation.db ".read migrations/002_add_flight_snapshots.sql"
sqlite3 data/aviation.db ".read migrations/003_provider_source_schema.sql"
sqlite3 data/aviation.db ".read migrations/004_add_delay_legacy_columns.sql"
```

## Testing

Run the automated tests with:

```bash
.venv/bin/pytest -q
```

These tests cover parsing and scoring logic and do not hit live APIs.

Useful smoke checks:

```bash
.venv/bin/python -m py_compile dashboard/app.py
.venv/bin/python -m py_compile src/collect_delays.py
.venv/bin/python -m py_compile src/collect_traffic.py
.venv/bin/python -m py_compile src/collect_flights.py
```

## Common Operational Issues

### Dashboard opens but data is stale

- Check the `Last Synced` timestamps in the UI.
- Verify cron is running.
- Check `logs/delays.log`, `logs/traffic.log`, and `logs/flights.log`.

### Flight collector fails

- Confirm `AIRLABS_API_KEY` is set.
- Check AirLabs quota and account limits.
- Check `data/collector_state/` if calls appear to be throttled.

### Dashboard shows no data

- Confirm `data/aviation.db` exists.
- Confirm all migrations were applied.
- Run each collector manually once before blaming the dashboard.

### Git clone is missing the DB snapshot

- Install Git LFS.
- Run `git lfs pull`.

### Cron jobs work manually but fail on schedule

- Use absolute paths in cron.
- Make sure the scripts are executable:

```bash
chmod +x scripts/*.sh
```

- Make sure `.venv` exists on the deployed machine.

## Dashboard Sections

The UI currently contains:

- `Dashboard Overview`
- `About This Project`
- `Calculation Details`

The main dashboard includes:

- `At A Glance`
- `Latest Airport Snapshot`
- `Hypothesis Check`
- `FAA Status History`
- `Airline Delay Impact`
- `Delay Timing Breakdown`

## Known Limitations

- SQLite is simple and effective here, but it is not the right choice for multi-instance write-heavy deployment.
- FAA severity and airline severity measure different things and should be interpreted together.
- Single snapshots are noisy; trend sections matter more than a single point in time.
- Upstream APIs may change shape and require collector maintenance.
- The repository is self-host deployment ready, but it does not yet ship with container, proxy, or IaC assets.

## Additional Documentation

- `API.md`: source-to-storage contract and collector/storage details
- `GUIDE.md`: project walkthrough and explanation material
