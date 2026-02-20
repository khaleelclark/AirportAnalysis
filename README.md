# MCO vs DEN Airport Operations Dashboard

Live capstone project comparing Orlando (MCO) vs Denver (DEN) using operational data, traffic intensity, and airline delay impact.

## Quick Start (3 Commands)

### Linux / macOS

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/streamlit run dashboard/app.py
```

### Windows (PowerShell)

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run dashboard\app.py
```

### Windows (Command Prompt)

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt
streamlit run dashboard\app.py
```

Before running collectors, add your AirLabs key in `.env`:

```env
AIRLABS_API_KEY=your_key_here
AIRLABS_AIRPORTS=MCO,DEN
```

Or copy the template:

```bash
cp .env.example .env
```

## What this project does

This project tests the hypothesis that MCO can perform worse than DEN in ways that are not fully explained by traffic load alone.

It collects and visualizes:
- FAA operational restrictions (ground delays/stops/closures)
- Live airspace traffic near each airport
- Flight-level airline delay signals

## Tech stack

- Python 3.12 (venv)
- SQLite (`data/aviation.db`)
- Streamlit (`dashboard/app.py`)
- Plotly + Pandas

## Data sources

- FAA NASStatus API (airport operational events)
- Live Airspace Traffic API (aircraft counts around airports)
- AirLabs Delay API (flight-level delay/cancel/diversion)

## Current project structure

- `src/collect_delays.py`: FAA collector
- `src/collect_traffic.py`: traffic collector
- `src/collect_flights.py`: AirLabs delay collector
- `src/db.py`: schema bootstrap
- `migrations/002_add_flight_snapshots.sql`
- `migrations/003_provider_source_schema.sql`
- `migrations/004_add_delay_legacy_columns.sql`
- `dashboard/app.py`: Streamlit app
- `scripts/collect_delays.sh`
- `scripts/collect_traffic.sh`
- `scripts/collect_flights.sh`

## Metrics used in the dashboard

- `Delay Severity Index (FAA)`: operational severity from FAA events
- `Airline Delay Severity Index`: 0-5 index from live flight delay/cancel/diversion mix
- `Traffic Load`: live aircraft count in airspace
- `Operational Stress Score`: combines FAA severity and traffic load
- `Load-Adjusted Stress Score`: normalizes stress by relative load to compare airports fairly
- `Longest Airline Delay Today`
- `Longest Delay Today (Any Source)`

Detailed formulas are documented in the dashboard’s `Calculation Details` tab.

## Setup

1. Create and activate venv.

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

Windows (Command Prompt):

```bat
py -3 -m venv .venv
.venv\Scripts\activate.bat
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Configure environment.

Create/update `.env`:

```env
AIRLABS_API_KEY=your_key_here
AIRLABS_AIRPORTS=MCO,DEN
```

4. Initialize DB schema.

```bash
.venv/bin/python src/db.py
sqlite3 data/aviation.db ".read migrations/002_add_flight_snapshots.sql"
sqlite3 data/aviation.db ".read migrations/003_provider_source_schema.sql"
sqlite3 data/aviation.db ".read migrations/004_add_delay_legacy_columns.sql"
```

## Run collectors manually

Linux / macOS:

```bash
.venv/bin/python src/collect_delays.py
.venv/bin/python src/collect_traffic.py
.venv/bin/python src/collect_flights.py
```

Windows (PowerShell or Command Prompt):

```bat
.venv\Scripts\python src\collect_delays.py
.venv\Scripts\python src\collect_traffic.py
.venv\Scripts\python src\collect_flights.py
```

## Run dashboard

Linux / macOS:

```bash
.venv/bin/streamlit run dashboard/app.py
```

Windows (PowerShell or Command Prompt):

```bat
.venv\Scripts\streamlit run dashboard\app.py
```

## Testing

Run tests locally (no API calls are made by the current test suite):

Linux / macOS:

```bash
.venv/bin/pytest -q
```

Windows (PowerShell or Command Prompt):

```bat
.venv\Scripts\pytest -q
```

Notes:
- Tests in `tests/test_basic.py` validate parser/scoring logic for FAA, traffic, and AirLabs collectors.
- These tests use synthetic inputs and do not consume AirLabs request credits.

## Cron schedule (current)

```cron
*/10 * * * * /home/khaleel/PycharmProjects/CapstoneProject/scripts/collect_traffic.sh
*/10 * * * * /home/khaleel/PycharmProjects/CapstoneProject/scripts/collect_delays.sh
0 9-23/2 * * * /home/khaleel/PycharmProjects/CapstoneProject/scripts/collect_flights.sh
```

Notes:
- Traffic + FAA collect every 10 minutes.
- AirLabs runs every 2 hours from 9 AM to 11 PM to stay within API budget.

## Dashboard pages

- `Dashboard Overview`: live metrics and charts
- `About This Project`: hypothesis, scope, and source context
- `Calculation Details`: metric formulas and assumptions

## Known limitations

- FAA and airline delays represent different concepts and should be interpreted together.
- Single snapshots can be noisy; trend windows and repeated observations are stronger evidence.
- API payload shape can vary; collectors include defensive parsing but may require maintenance.

## Reset database (optional)

```bash
rm -f data/aviation.db
.venv/bin/python src/db.py
sqlite3 data/aviation.db ".read migrations/002_add_flight_snapshots.sql"
sqlite3 data/aviation.db ".read migrations/003_provider_source_schema.sql"
sqlite3 data/aviation.db ".read migrations/004_add_delay_legacy_columns.sql"
```
