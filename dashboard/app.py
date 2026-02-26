from pathlib import Path
import sqlite3
from datetime import datetime
import subprocess
import sys
from typing import Any, cast
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aviation.db"
PROJECT_ROOT = DB_PATH.parent.parent

st.set_page_config(page_title="MCO vs DEN – Airport Performance", layout="wide")
st.title("MCO vs DEN – Airport Delay & Traffic Dashboard")
st.caption("Goal: Compare airport disruption at MCO vs DEN using live FAA delay programs and live traffic levels.")

overview_tab, about_tab, calc_tab = st.tabs(
    ["Dashboard Overview", "About This Project", "Calculation Details"]
)

with about_tab:
    st.markdown(
        """
        ### Central Question 
        Are delays at MCO (Orlando International Airport) proportionate to operational load, or does MCO perform disproportionately worse than DEN (Denver International Airport) after controlling for traffic pressure?
        
        ### Project Hypothesis
        Based on repeated personal travel experience, MCO appears to deliver a worse operational experience than DEN.
        This project tests that claim with live FAA restrictions, live traffic load, and airline delay/cancellation/diversion outcomes across both airports over time.

        ### Data Sources
        - **FAA NASStatus API** for airport-level delay programs and restrictions
        - **Live Airspace Traffic API** for aircraft activity in each airport area
        - **AirLabs Delay API** for flight-level airline delay, cancellation, and diversion signals

        ### Refresh Cadence
        - FAA Delays: every **10 minutes**
        - Traffic: every **10 minutes**
        - Airline Delay: every **2 hours** (from **9 AM to 11 PM** local)

        ### Key Metrics
        - **Delay Severity Index (FAA Operational):** 0 means no active FAA restriction; higher means more severe operational restriction.
        - **Airline Delay Severity Index:** live airline-impact score from delays/cancellations/diversions.
        - **Traffic Load:** live aircraft count in airspace near each airport.
        - **Operational Stress Score:** combined measure of traffic pressure and FAA delay severity.

        ### How The Dashboard Tests The Hypothesis
        - **Airline Delay Comparison:** checks passenger-facing outcomes (delay minutes, cancellation rate, airline severity).
        - **Operational Load Comparison:** checks FAA severity and operational strain.
        - **Combined Evidence Comparison:** merges airline and operational signals, then reports a dynamic verdict (supports, mixed, or does not support).

        ### Scope Notes
        - This dashboard is intentionally scoped to **MCO** and **DEN** for the capstone.
        - FAA severity and airline delay severity are related but distinct signals; both are shown for transparency.
        - One snapshot can be noisy, so trend and ratio sections are emphasized over single-point readings.
        """
    )

with calc_tab:
    st.markdown(
        """
        ### Calculation Details
        This page documents how dashboard metrics are computed from live data.

        ### Dashboard Section Guide
        - **Last Synced (FAA Delays / Traffic / Airline Delay)**:
          Shows the most recent timestamp ingested for each data source.
        - **At A Glance**:
          Quick comparison of which airport currently leads key risk indicators.
        - **Latest Airport Snapshot**:
          Per-airport live snapshot of severity, load, stress, longest delays, and FAA status.
        - **FAA Status History**:
          Status timeline, delayed-snapshot counts, and restriction log for FAA events.
        - **Airline Delay Impact**:
          Passenger-facing trend view from AirLabs delays, cancellations, and diversions.
        - **Hypothesis Check**:
          Three focused comparisons: airline-only, operational-only, and combined evidence.
        - **Trend Lines**:
          Rolling delay and rolling operational stress trends over time.
        - **Traffic Load Vs Delay Severity**:
          Raw scatter plus same-load band comparison to judge fairness at similar traffic.
        - **Delay Timing Breakdown**:
          Weekday and hour-of-day comparisons showing when each airport is usually worse.
        - **Worst Time Periods**:
          Ranked tables of highest-stress days and hour blocks.
        - **Traffic Vs Delay Relationship**:
          Correlation strength summary between aircraft volume and FAA delay severity.
          Traceability table of underlying rows used by the charts.

        ### 1) Latest Airport Snapshot Metrics
        FAA Delay Severity Index comes from FAA NASStatus event types:
        - `0`: No active FAA restriction
        - `2`: Arrival/Departure delay program
        - `3`: Ground Delay Program
        - `4`: Ground Stop
        - `5`: Airport closure
        If multiple FAA events exist at once, the index uses the **maximum** severity.

        Airline Delay Severity Index (0-5) is:
        - `average_delay_min = mean(max(delay_minutes, 0))`
        - `cancel_rate = cancelled_flights / total_flights`
        - `divert_rate = diverted_flights / total_flights`
        - `airline_severity = min(min(average_delay_min / 20, 3.0) + min(cancel_rate * 4.0, 1.5) + min(divert_rate * 2.0, 0.5), 5.0)`

        Traffic and stress metrics:
        - `traffic_load_effective = aircraft_count` (fallback: `dep_total + arr_total`)
        - `operational_stress_score = (1 + delay_severity_index) * (traffic_load_effective / 100)`

        Longest delay metrics:
        - **Longest Airline Delay Today**: max flight `delay_minutes` today (local date).
        - **Longest Recorded Delay (Any Source)**: max of:
          airline longest delay,
          FAA event delay range (max delay, fallback to min delay),
          across the full collected history.

        ### 2) FAA Status History
        Built from FAA snapshots in the selected range:
        - Status counts by airport
        - Active FAA restriction count over time
        - Daily delayed snapshots where `faa_event_count > 0`
        - Log table shows only snapshots with active restrictions

        ### 3) Airline Delay Impact
        Uses flight-level rows in selected range:
        - Airline delay severity trend over time
        - Longest airline delay trend
        - Daily cancellation rate
        - Longest delay comparison bars

        ### 4) Hypothesis Check Ratios
        The hypothesis section compares MCO vs DEN as:
        - `ratio = metric_at_MCO / metric_at_DEN`
        - `ratio > 1.0`: supports "MCO worse" for that metric
        - `ratio <= 1.0`: does not support "MCO worse" for that metric

        Airline Delay Comparison metrics:
        - `average_airline_delay_min`
        - `cancel_rate_percent`
        - `average_airline_severity`

        Operational Load Comparison metrics:
        - `average_traffic_load`
        - `average_delay_index`
        - `delay_per_100_load`
        - `faa_restriction_rate_percent`

        Combined Evidence verdict uses two core ratios:
        - `operational_core = ratio(delay_per_100_load)`
        - `airline_core = ratio(average_airline_severity)`
        - `combined_core_mean = mean(operational_core, airline_core)` when both exist
        It reports whether evidence supports operational, airline, both, mixed, or neither.

        ### 5) Trend Lines
        Rolling time-series by airport:
        - Delay Severity Index rolling average
        - Operational Stress Score rolling average

        ### 6) Traffic Load Vs Delay Severity
        Two views in selected range:
        - Raw snapshot scatter (`traffic_load_effective` vs `delay_index_best`)
        - Same-load bucket comparison (average delay by load band)

        ### 7) Delay Timing Breakdown
        Timing charts are aggregated from FAA delay severity snapshots:
        - Day-of-week chart: average delay severity by local weekday and airport
        - Hour chart: average delay severity by local hour and airport,
          restricted to hours `7-23` for readability

        ### 8) Worst Time Periods
        Ranked aggregates:
        - Worst days by average stress then average delay
        - Worst hour blocks by average stress then average delay

        ### 9) Traffic Vs Delay Relationship
        Nearest-time matched delay + traffic rows:
        - Pearson correlation by airport
        - Correlation strength comparison chart
        """
    )

# noinspection PyShadowingNames,PyShadowingNamesInspection,DuplicatedCode,PyPandasTruthValueIsAmbiguousInspection,PyArgumentList
with overview_tab:
    st.markdown(
        "This dashboard tracks live operational conditions at **MCO** and **DEN**. "
        "Use it to compare disruption, traffic pressure, and delay impact."
    )
    with st.expander("How To Read This Dashboard", expanded=True):
        st.markdown(
            """
            - **Primary Question**: Is MCO performing worse than DEN after accounting for how busy each airport is?
            - **Delay Severity Index (FAA Operational)**: `0` means no active FAA restriction. Higher values mean more severe operational restrictions (ground delay, ground stop, closures).
            - **Airline Delay Severity Index (AirLabs)**: `0-5` index based on live airline delay minutes, cancellations, and diversions.
            - **Traffic Load**: Live aircraft count in airport airspace. This is the pressure/load signal.
            - **Operational Stress Score**: `(1 + Delay Severity Index) × Traffic Load` (scaled). Higher means heavier operational strain.
            - **Longest Delay Today Metrics**:
              `Longest Airline Delay Today` comes from AirLabs flight delays.
              `Longest Recorded Delay (Any Source)` takes the largest value seen in your full collected history,
              across airline delays and FAA event delay ranges.
            - **FAA Status History**:
              Shows FAA status counts, active restriction trend, daily delayed snapshots, and restriction log history.
            - **Airline Delay Impact**:
              Shows airline severity trend, longest airline delays, and daily cancellation rates.
            - **Hypothesis Check**:
              Includes three sections in order:
              Airline Delay Comparison, Operational Load Comparison, and Combined Evidence Comparison.
              Each section shows MCO/DEN ratios and its own verdict.
            - **Trend Lines**:
              Shows rolling delay severity and rolling load-adjusted stress.
            - **Traffic Load Vs Delay Severity**:
              Use raw scatter and same-load bands together to judge fairness at similar traffic levels.
            - **Delay Timing Breakdown**:
              Day-of-week view plus hour-of-day view (hours 7-23) for easier reading.
            - **Worst Time Periods**:
              Ranked tables highlight highest average stress days and hour blocks.
            - **Traffic Vs Delay Relationship**:
              Correlation section shows how strongly traffic volume and delay severity move together.
            - **How To Interpret Quickly**:
              If MCO has a higher **Operational Stress Score** over multiple snapshots/days, that supports the hypothesis that MCO is disproportionately worse.
              If MCO is only worse when load spikes, then traffic volume may be the main driver.
            - **Cadence**:
              FAA Delays every 10 minutes, Traffic every 10 minutes, Airline Delay every 2 hours (9 AM to 11 PM local).
            - **Important Limitation**:
              One snapshot can be noisy. Use trend lines and repeated observations before drawing conclusions.
            """
        )
    
    # -----------------------
    # Helpers
    # -----------------------
    @st.cache_data(ttl=30)
    def load_df(query: str) -> pd.DataFrame:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df

    @st.cache_data(ttl=300)
    def get_table_columns(table_name: str) -> set[str]:
        conn = sqlite3.connect(DB_PATH)
        try:
            rows = pd.read_sql_query(f"PRAGMA table_info({table_name})", conn)
        finally:
            conn.close()
        if rows.empty or "name" not in rows.columns:
            return set()
        return set(rows["name"].astype(str).tolist())

    def sql_col_or_null(cols: set[str], col_name: str, alias: str | None = None) -> str:
        out = alias or col_name
        if col_name in cols:
            return f"{col_name} AS {out}"
        return f"NULL AS {out}"
    
    def get_last_updated() -> dict:
        q = """
            SELECT
                    (SELECT MAX(collected_at) FROM delay_snapshots)  AS last_faa,
                    (SELECT MAX(collected_at) FROM traffic_snapshots) AS last_traffic,
                    (SELECT MAX(collected_at) FROM flight_snapshots) AS last_airline_delay
            """
        row = load_df(q).iloc[0].to_dict()
        # Convert to timestamps (UTC)
        out: dict[str, pd.Timestamp | None] = {}
        for k, v in row.items():
            out[str(k)] = pd.to_datetime(v, utc=True) if v else None
        return out

    def to_numeric_series(values: Any, index: pd.Index | None = None) -> pd.Series:
        numeric = pd.to_numeric(values, errors="coerce")
        if isinstance(numeric, pd.Series):
            return numeric
        return pd.Series(numeric, index=index)

    def to_datetime_utc_series(values: Any, index: pd.Index | None = None) -> pd.Series:
        dt = pd.to_datetime(values, utc=True, errors="coerce")
        if isinstance(dt, pd.Series):
            return dt
        return pd.Series(dt, index=index)

    def tz_convert_series(series: pd.Series, tz: Any) -> pd.Series:
        dt_index = pd.DatetimeIndex(series)
        return pd.Series(dt_index.tz_convert(tz), index=series.index)

    def series_date(series: pd.Series) -> pd.Series:
        dt_index = pd.DatetimeIndex(series)
        return pd.Series(dt_index.date, index=series.index)

    def series_hour(series: pd.Series) -> pd.Series:
        dt_index = pd.DatetimeIndex(series)
        return pd.Series(dt_index.hour, index=series.index)

    def series_day_name(series: pd.Series) -> pd.Series:
        dt_index = pd.DatetimeIndex(series)
        return pd.Series(dt_index.day_name(), index=series.index)

    def records(df: pd.DataFrame) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], df.to_dict(orient="records"))

    def sort_values_df(
        df: Any,
        by: str | list[str],
        ascending: bool | list[bool] = True,
    ) -> pd.DataFrame:
        # noinspection PyArgumentList
        if isinstance(df, pd.Series):
            return df.to_frame().sort_values(by=by, ascending=ascending)
        return cast(pd.DataFrame, df.sort_values(by=by, ascending=ascending))

    def to_utc_timestamp(value: Any) -> pd.Timestamp | None:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts

    def safe_float(x: Any) -> float | None:
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def safe_corr(series_x: pd.Series, series_y: pd.Series) -> float | None:
        x = to_numeric_series(series_x, index=series_x.index)
        y = to_numeric_series(series_y, index=series_y.index)
        valid = x.notna() & y.notna()
        if valid.sum() < 3:
            return None
        x = x[valid]
        y = y[valid]
        if x.nunique() < 2 or y.nunique() < 2:
            return None
        return float(x.corr(y))
    
    
    LOCAL_TZ = datetime.now().astimezone().tzinfo
    AIRPORT_TIMEZONES = {
        "DEN": ZoneInfo("America/Denver"),
    }
    AIRPORT_COLOR_MAP = {
        "MCO": "#1f77b4",
        "DEN": "#ff7f0e",
    }
    
    
    def format_local_snapshot_time(ts: pd.Timestamp | None) -> str:
        ts_value = to_utc_timestamp(ts)
        if ts_value is None:
            return "—"
        return ts_value.tz_convert(LOCAL_TZ).strftime("%I:%M %p %B %d")

    def format_snapshot_time_for_airport(ts: pd.Timestamp | None, airport_code: str | None) -> str:
        ts_value = to_utc_timestamp(ts)
        if ts_value is None:
            return "—"
        tz = AIRPORT_TIMEZONES.get((airport_code or "").upper(), LOCAL_TZ)
        return ts_value.tz_convert(tz).strftime("%I:%M %p %B %d")


    def format_faa_update_time_local(value) -> str:
        if value is None or pd.isna(value):
            return "—"
        ts = to_utc_timestamp(value)
        if ts is None:
            return "—"
        return format_local_snapshot_time(ts)

    def format_faa_update_time_for_airport(value, airport_code: str | None) -> str:
        if value is None or pd.isna(value):
            return "—"
        ts = to_utc_timestamp(value)
        if ts is None:
            return "—"
        return format_snapshot_time_for_airport(ts, airport_code)
    
    
    def format_minutes_hr_min(value) -> str:
        if value is None or pd.isna(value):
            return "N/A"
        total_min = max(int(round(float(value))), 0)
        hours = total_min // 60
        minutes = total_min % 60
        return f"{hours} hr {minutes} min"
    
    
    def prettify_columns(df: pd.DataFrame) -> pd.DataFrame:
        return df.rename(columns=lambda c: str(c).replace("_", " ").title())
    
    
    def format_time_axis_12h(chart):
        chart.update_xaxes(tickformat="%I:%M %p<br>%B %d", hoverformat="%I:%M %p %B %d")
        return chart
    
    
    def run_manual_sync_collectors() -> list[dict]:
        python_bin = sys.executable
        commands = [
            ("FAA Delays", [python_bin, "src/collect_delays.py"]),
            ("Live Airspace Traffic", [python_bin, "src/collect_traffic.py"]),
            ("Airline Delay", [python_bin, "src/collect_flights.py"]),
        ]
        results = []
        for label, cmd in commands:
            proc = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
            results.append(
                {
                    "label": label,
                    "ok": proc.returncode == 0,
                    "stdout": proc.stdout[-1200:],
                    "stderr": proc.stderr[-1200:],
                }
            )
        return results
    
    
    # -----------------------
    # Load data
    # -----------------------
    delay_cols = get_table_columns("delay_snapshots")
    # noinspection SqlResolve
    delay_df = load_df(f"""
                       SELECT
                           {sql_col_or_null(delay_cols, "id")},
                           {sql_col_or_null(delay_cols, "airport_code")},
                           {sql_col_or_null(delay_cols, "collected_at")},
                           {sql_col_or_null(delay_cols, "window_from_utc")},
                           {sql_col_or_null(delay_cols, "window_to_utc")},
                           {sql_col_or_null(delay_cols, "source")},
                           {sql_col_or_null(delay_cols, "delay_index")},
                           {sql_col_or_null(delay_cols, "delay_median_minutes")},
                           {sql_col_or_null(delay_cols, "dep_total")},
                           {sql_col_or_null(delay_cols, "arr_total")},
                           {sql_col_or_null(delay_cols, "dep_delay_index")},
                           {sql_col_or_null(delay_cols, "dep_median_delay_minutes")},
                           {sql_col_or_null(delay_cols, "arr_delay_index")},
                           {sql_col_or_null(delay_cols, "arr_median_delay_minutes")},
                           {sql_col_or_null(delay_cols, "faa_update_time")},
                           {sql_col_or_null(delay_cols, "faa_event_count")},
                           CASE
                               WHEN raw_json IS NOT NULL THEN json_extract(raw_json, '$.airport.status')
                           END AS faa_status
                       FROM delay_snapshots
                       ORDER BY collected_at
                       """)
    
    # noinspection SqlResolve
    traffic_df = load_df("""
                         SELECT
                             id,
                             airport_code,
                             collected_at,
                             aircraft_count,
                             airborne_count,
                             on_ground_count,
                         altitude_median,
                         velocity_median
                         FROM traffic_snapshots
                         ORDER BY collected_at
                         """)
    
    # noinspection SqlResolve
    flight_df = load_df("""
                        SELECT
                            airport_code,
                            collected_at,
                            delay_minutes,
                            cancelled,
                            diverted
                        FROM flight_snapshots
                        ORDER BY collected_at
                        """)
    
    # noinspection SqlResolve
    faa_events_df = load_df("""
                            SELECT
                                airport_code,
                                collected_at,
                                min_delay_minutes,
                                max_delay_minutes
                            FROM faa_events
                            ORDER BY collected_at
                            """)
    
    if delay_df.empty:
        st.warning("No delay data found yet. Run `python src/collect_delays.py` a few times first.")
        st.stop()
    
    delay_df["collected_at"] = to_datetime_utc_series(delay_df["collected_at"], index=delay_df.index)
    delay_df["collected_at_local"] = tz_convert_series(delay_df["collected_at"], LOCAL_TZ)
    delay_df["collected_at_local_label"] = delay_df["collected_at_local"].dt.strftime("%I:%M %p %B %d")
    delay_df["source"] = delay_df["source"].fillna("UNKNOWN")

    for numeric_col in [
        "delay_index",
        "delay_median_minutes",
        "dep_total",
        "arr_total",
        "dep_delay_index",
        "dep_median_delay_minutes",
        "arr_delay_index",
        "arr_median_delay_minutes",
        "faa_event_count",
    ]:
        if numeric_col in delay_df.columns:
            delay_df[numeric_col] = pd.to_numeric(delay_df[numeric_col], errors="coerce")
    
    if not traffic_df.empty:
        traffic_df["collected_at"] = to_datetime_utc_series(traffic_df["collected_at"], index=traffic_df.index)
        traffic_df["collected_at_local"] = tz_convert_series(traffic_df["collected_at"], LOCAL_TZ)
        traffic_df["collected_at_local_label"] = traffic_df["collected_at_local"].dt.strftime("%I:%M %p %B %d")
        for numeric_col in ["aircraft_count", "airborne_count", "on_ground_count", "altitude_median", "velocity_median"]:
            if numeric_col in traffic_df.columns:
                traffic_df[numeric_col] = pd.to_numeric(traffic_df[numeric_col], errors="coerce")
    
    if not flight_df.empty:
        flight_df["collected_at"] = to_datetime_utc_series(flight_df["collected_at"], index=flight_df.index)
        flight_df["collected_at_local"] = tz_convert_series(flight_df["collected_at"], LOCAL_TZ)
        flight_df["delay_minutes"] = to_numeric_series(flight_df["delay_minutes"], index=flight_df.index)
        flight_df["cancelled"] = to_numeric_series(flight_df["cancelled"], index=flight_df.index).fillna(0)
        flight_df["diverted"] = to_numeric_series(flight_df["diverted"], index=flight_df.index).fillna(0)
    
    if not faa_events_df.empty:
        faa_events_df["collected_at"] = to_datetime_utc_series(faa_events_df["collected_at"], index=faa_events_df.index)
        faa_events_df["max_delay_minutes"] = pd.to_numeric(faa_events_df["max_delay_minutes"], errors="coerce")
        faa_events_df["min_delay_minutes"] = pd.to_numeric(faa_events_df["min_delay_minutes"], errors="coerce")
    
    last = get_last_updated()
    
    cA, cB, cC = st.columns(3)
    
    with cA:
        st.metric(
            "Last Synced (FAA Delays)",
            format_local_snapshot_time(last["last_faa"]),
        )
    
    with cB:
        st.metric(
            "Last Synced (Traffic)",
            format_local_snapshot_time(last["last_traffic"]),
        )
    
    with cC:
        st.metric(
            "Last Synced (Airline Delay)",
            format_local_snapshot_time(last["last_airline_delay"]),
        )
    
    st.caption("Dashboard reads directly from your local SQLite DB. If cron is running, these timestamps should keep updating.")
    
    top_controls_left, top_controls_right = st.columns([1, 1])
    with top_controls_left:
        if st.button("Refresh now"):
            st.rerun()
    
    with top_controls_right:
        popover_fn = getattr(st, "popover", None)
        if popover_fn is not None:
            with st.popover("Sync Data Now (API Calls)"):
                st.warning("This will immediately call FAA, Live Airspace Traffic, and AirLabs APIs.")
                confirm_sync = st.checkbox("I understand this triggers live API requests now.", key="confirm_manual_sync")
                if st.button("Run Manual Sync Now", key="run_manual_sync_button"):
                    if not confirm_sync:
                        st.error("Please confirm before running manual sync.")
                    else:
                        st.info("Running collectors...")
                        sync_results = run_manual_sync_collectors()
                        for r in sync_results:
                            if r["ok"]:
                                st.success(f"{r['label']} synced successfully.")
                            else:
                                st.error(f"{r['label']} sync failed.")
                            if r["stderr"]:
                                st.caption(r["stderr"])
                        st.info("Manual sync finished. Click `Refresh now` to reload latest values.")
        else:
            with st.expander("Sync Data Now (API Calls)"):
                st.warning("This will immediately call FAA, Live Airspace Traffic, and AirLabs APIs.")
                confirm_sync = st.checkbox("I understand this triggers live API requests now.", key="confirm_manual_sync_fallback")
                if st.button("Run Manual Sync Now", key="run_manual_sync_button_fallback"):
                    if not confirm_sync:
                        st.error("Please confirm before running manual sync.")
                    else:
                        st.info("Running collectors...")
                        sync_results = run_manual_sync_collectors()
                        for r in sync_results:
                            if r["ok"]:
                                st.success(f"{r['label']} synced successfully.")
                            else:
                                st.error(f"{r['label']} sync failed.")
                            if r["stderr"]:
                                st.caption(r["stderr"])
                        st.info("Manual sync finished. Click `Refresh now` to reload latest values.")
    st.divider()
    
    # Dashboard is intentionally locked to the capstone airports.
    selected_airports = ["MCO", "DEN"]
    
    available_sources = set(delay_df["source"].dropna().unique().tolist())
    if "FAA_NASSTATUS" in available_sources:
        filtered = delay_df[
            delay_df["airport_code"].isin(selected_airports) &
            (delay_df["source"] == "FAA_NASSTATUS")
        ].copy()
    else:
        filtered = delay_df[delay_df["airport_code"].isin(selected_airports)].copy()
    
    if filtered.empty:
        st.warning("No rows found for MCO/DEN yet.")
        st.stop()
    
    min_dt = filtered["collected_at_local"].min()
    max_dt = filtered["collected_at_local"].max()
    
    st.markdown("#### Time Range (Local)")
    # Streamlit slider requires min < max; widen when only one timestamp exists.
    if min_dt == max_dt:
        min_slider = (min_dt - pd.Timedelta(minutes=1)).to_pydatetime()
        max_slider = (max_dt + pd.Timedelta(minutes=1)).to_pydatetime()
        default_time_range = (min_dt.to_pydatetime(), max_dt.to_pydatetime())
    else:
        min_slider = min_dt.to_pydatetime()
        max_slider = max_dt.to_pydatetime()
        default_time_range = (min_slider, max_slider)
    
    time_range = st.slider(
        "Select Time Range",
        min_value=min_slider,
        max_value=max_slider,
        value=default_time_range,
    )
    
    start_dt = pd.to_datetime(time_range[0])
    end_dt = pd.to_datetime(time_range[1])
    if start_dt.tzinfo is None:
        start_dt = start_dt.tz_localize(LOCAL_TZ)
    else:
        start_dt = start_dt.tz_convert(LOCAL_TZ)
    if end_dt.tzinfo is None:
        end_dt = end_dt.tz_localize(LOCAL_TZ)
    else:
        end_dt = end_dt.tz_convert(LOCAL_TZ)
    
    filtered = filtered[filtered["collected_at_local"].between(start_dt, end_dt)].copy()
    if filtered.empty:
        st.warning("No rows found for this time range.")
        st.stop()
    
    # Derived load column (only when dep/arr totals are actually provided by the source)
    has_load = filtered["dep_total"].notna() | filtered["arr_total"].notna()
    filtered["load_total"] = float("nan")
    filtered.loc[has_load, "load_total"] = (
        filtered.loc[has_load, ["dep_total", "arr_total"]].fillna(0).sum(axis=1)
    )
    filtered["load_total"] = pd.to_numeric(filtered["load_total"], errors="coerce")
    
    # Use a "best available delay index":
    # prefer overall delay_index, else fall back to dep_delay_index.
    filtered["delay_index_best"] = filtered["delay_index"]
    filtered.loc[filtered["delay_index_best"].isna(), "delay_index_best"] = filtered["dep_delay_index"]
    filtered["delay_index_best"] = pd.to_numeric(filtered["delay_index_best"], errors="coerce")
    
    # Align nearest live traffic counts to delay rows, per airport.
    if not traffic_df.empty:
        merged_parts = []
        for airport in filtered["airport_code"].dropna().unique().tolist():
            d_a = (
                sort_values_df(
                    filtered[filtered["airport_code"] == airport],
                    by="collected_at",
                ).copy()
            )
            if "aircraft_count_for_score" in d_a.columns:
                d_a = d_a.drop(columns=["aircraft_count_for_score"])
            t_a = (
                sort_values_df(
                    traffic_df[
                    (traffic_df["airport_code"] == airport) &
                    (traffic_df["aircraft_count"].notna())
                    ][["collected_at", "aircraft_count"]],
                    by="collected_at",
                ).copy()
            )
    
            if t_a.empty:
                d_a["aircraft_count_for_score"] = float("nan")
                merged_parts.append(d_a)
                continue
    
            m_a = pd.merge_asof(
                d_a,
                t_a,
                on="collected_at",
                direction="nearest",
                tolerance=pd.Timedelta("30min"),
            ).rename(columns={"aircraft_count": "aircraft_count_for_score"})
            merged_parts.append(m_a)
    
        if len(merged_parts) > 0:
            filtered = pd.concat(merged_parts, ignore_index=True)
    
    if "aircraft_count_for_score" not in filtered.columns:
        filtered["aircraft_count_for_score"] = float("nan")
    filtered["aircraft_count_for_score"] = pd.to_numeric(filtered["aircraft_count_for_score"], errors="coerce")
    
    # Effective traffic load prioritizes live aircraft count.
    filtered["traffic_load_effective"] = filtered["aircraft_count_for_score"]
    filtered.loc[filtered["traffic_load_effective"].isna(), "traffic_load_effective"] = filtered["load_total"]
    filtered["traffic_load_effective"] = pd.to_numeric(filtered["traffic_load_effective"], errors="coerce")
    
    # Operational Stress Score includes baseline traffic pressure even when FAA delay severity is zero.
    filtered["operational_stress_score"] = (
        (1.0 + filtered["delay_index_best"].fillna(0.0)) * (filtered["traffic_load_effective"] / 100.0)
    )
    filtered["operational_stress_score"] = pd.to_numeric(filtered["operational_stress_score"], errors="coerce")

    # Convenience time features (Local)
    filtered["date_utc"] = series_date(filtered["collected_at_local"])
    filtered["hour_utc"] = series_hour(filtered["collected_at_local"])
    filtered["dow_utc"] = series_day_name(filtered["collected_at_local"])
    
    # -----------------------
    # At A Glance
    # -----------------------
    st.subheader("At A Glance")
    
    latest_by_airport = sort_values_df(
        sort_values_df(filtered, by="collected_at")
        .groupby("airport_code", as_index=False)
        .tail(1),
        by="airport_code",
    )
    
    airline_severity_map = {}
    airline_range_map = {}
    if not flight_df.empty:
        flights_selected = flight_df[flight_df["airport_code"].isin(selected_airports)].copy()
        if not flights_selected.empty:
            flights_selected_range = flights_selected[
                flights_selected["collected_at_local"].between(start_dt, end_dt)
            ].copy()
            if not flights_selected_range.empty:
                range_agg = (
                    flights_selected_range.groupby("airport_code", as_index=False)
                    .agg(
                        flights_n=("delay_minutes", "size"),
                        average_delay_min=("delay_minutes", lambda s: s.clip(lower=0).mean()),
                        cancel_rate=("cancelled", "mean"),
                        divert_rate=("diverted", "mean"),
                    )
                )
                airline_range_map = {
                    str(record["airport_code"]): {
                        "flights_n": int(record["flights_n"]),
                        "average_delay_min": round(float(record["average_delay_min"]) if pd.notna(record["average_delay_min"]) else 0.0, 1),
                        "cancel_rate_percent": round(float(record["cancel_rate"]) * 100.0 if pd.notna(record["cancel_rate"]) else 0.0, 1),
                        "divert_rate_percent": round(float(record["divert_rate"]) * 100.0 if pd.notna(record["divert_rate"]) else 0.0, 1),
                    }
                    for record in records(range_agg)
                }

            latest_flight_snapshots = (
                sort_values_df(flights_selected, by="collected_at")
                .groupby("airport_code", as_index=False)
                .tail(1)[["airport_code", "collected_at"]]
            )
    
            latest_snapshot_rows = flights_selected.merge(
                latest_flight_snapshots,
                on=["airport_code", "collected_at"],
                how="inner"
            )
    
            for airport_group_key, grp in latest_snapshot_rows.groupby("airport_code"):
                airport = str(airport_group_key)
                flights_n = len(grp)
                if flights_n == 0:
                    continue
    
                positive_delay = grp["delay_minutes"].clip(lower=0)
                average_delay = float(positive_delay.mean()) if positive_delay.notna().any() else 0.0
                cancel_rate = float(grp["cancelled"].mean())
                divert_rate = float(grp["diverted"].mean())
    
                delay_component = min(average_delay / 20.0, 3.0)
                cancel_component = min(cancel_rate * 4.0, 1.5)
                divert_component = min(divert_rate * 2.0, 0.5)
                airline_severity = min(delay_component + cancel_component + divert_component, 5.0)
    
                airline_severity_map[airport] = {
                    "score": round(airline_severity, 3),
                    "flights_n": flights_n,
                    "average_delay_min": round(average_delay, 1),
                    "cancel_rate_percent": round(cancel_rate * 100.0, 1),
                    "divert_rate_percent": round(divert_rate * 100.0, 1),
                    "snapshot_time": grp["collected_at"].max(),
                }
    
    today_local = pd.Timestamp.now(tz=LOCAL_TZ).date()
    longest_airline_today_map = {}
    if not flight_df.empty:
        flights_today = flight_df.copy()
        flights_today["collected_at_local"] = tz_convert_series(flights_today["collected_at"], LOCAL_TZ)
        flights_today = flights_today[series_date(flights_today["collected_at_local"]) == today_local]
        if not flights_today.empty:
            airline_max = flights_today.groupby("airport_code", as_index=False).agg(
                longest_airline_delay_today=("delay_minutes", "max")
            )
            longest_airline_today_map = {
                str(record["airport_code"]): (
                    record["longest_airline_delay_today"] if pd.notna(record["longest_airline_delay_today"]) else None
                )
                for record in records(airline_max)
            }
    
    longest_faa_today_map = {}
    if not faa_events_df.empty:
        faa_today = faa_events_df.copy()
        faa_today["collected_at_local"] = tz_convert_series(faa_today["collected_at"], LOCAL_TZ)
        faa_today = faa_today[series_date(faa_today["collected_at_local"]) == today_local]
        if not faa_today.empty:
            faa_today["faa_delay_for_max"] = faa_today["max_delay_minutes"]
            faa_today.loc[faa_today["faa_delay_for_max"].isna(), "faa_delay_for_max"] = faa_today["min_delay_minutes"]
            faa_max = faa_today.groupby("airport_code", as_index=False).agg(
                longest_faa_delay_today=("faa_delay_for_max", "max")
            )
            longest_faa_today_map = {
                str(record["airport_code"]): (
                    record["longest_faa_delay_today"] if pd.notna(record["longest_faa_delay_today"]) else None
                )
                for record in records(faa_max)
            }

    longest_airline_all_time_map = {}
    if not flight_df.empty:
        airline_all_time = flight_df.groupby("airport_code", as_index=False).agg(
            longest_airline_delay_all_time=("delay_minutes", "max")
        )
        longest_airline_all_time_map = {
            str(record["airport_code"]): (
                record["longest_airline_delay_all_time"] if pd.notna(record["longest_airline_delay_all_time"]) else None
            )
            for record in records(airline_all_time)
        }

    longest_faa_all_time_map = {}
    if not faa_events_df.empty:
        faa_all_time = faa_events_df.copy()
        faa_all_time["faa_delay_for_max"] = faa_all_time["max_delay_minutes"]
        faa_all_time.loc[faa_all_time["faa_delay_for_max"].isna(), "faa_delay_for_max"] = faa_all_time["min_delay_minutes"]
        faa_max_all = faa_all_time.groupby("airport_code", as_index=False).agg(
            longest_faa_delay_all_time=("faa_delay_for_max", "max")
        )
        longest_faa_all_time_map = {
            str(record["airport_code"]): (
                record["longest_faa_delay_all_time"] if pd.notna(record["longest_faa_delay_all_time"]) else None
            )
            for record in records(faa_max_all)
        }
    
    latest_by_airport_rows = records(latest_by_airport)
    overview_rows = []
    for airport_row in latest_by_airport_rows:
        airport = str(airport_row["airport_code"])
        airline_score = (airline_severity_map.get(airport) or {}).get("score")
        airline_today = longest_airline_today_map.get(airport)
        any_recorded = max(
            [v for v in [longest_airline_all_time_map.get(airport), longest_faa_all_time_map.get(airport)] if v is not None],
            default=None
        )
        overview_rows.append(
            {
                "airport_code": airport,
                "operational_stress_score": safe_float(airport_row.get("operational_stress_score")),
                "airline_delay_severity_index": safe_float(airline_score),
                "traffic_load": safe_float(airport_row.get("traffic_load_effective")),
                "longest_delay_recorded": safe_float(any_recorded),
            }
        )
    
    overview_df = pd.DataFrame(overview_rows)
    if not overview_df.empty:
        for numeric_col in [
            "operational_stress_score",
            "airline_delay_severity_index",
            "traffic_load",
            "longest_delay_recorded",
        ]:
            overview_df[numeric_col] = pd.to_numeric(overview_df[numeric_col], errors="coerce")

        o1, o2, o3, o4 = st.columns(4)
        top_stress_df = sort_values_df(
            overview_df.assign(
                operational_stress_score=overview_df["operational_stress_score"].fillna(float("-inf"))
            ),
            by="operational_stress_score",
            ascending=False,
        )
        top_stress = cast(dict[str, Any], top_stress_df.iloc[0].to_dict())

        top_airline_df = sort_values_df(
            overview_df.assign(
                airline_delay_severity_index=overview_df["airline_delay_severity_index"].fillna(float("-inf"))
            ),
            by="airline_delay_severity_index",
            ascending=False,
        )
        top_airline = cast(dict[str, Any], top_airline_df.iloc[0].to_dict())

        top_longest_df = sort_values_df(
            overview_df.assign(
                longest_delay_recorded=overview_df["longest_delay_recorded"].fillna(float("-inf"))
            ),
            by="longest_delay_recorded",
            ascending=False,
        )
        top_longest = cast(dict[str, Any], top_longest_df.iloc[0].to_dict())
    
        traffic_gap_text = "N/A"
        if len(overview_df) >= 2 and overview_df["traffic_load"].notna().sum() >= 2:
            top_two = sort_values_df(overview_df, by="traffic_load", ascending=False).head(2)
            gap = top_two.iloc[0]["traffic_load"] - top_two.iloc[1]["traffic_load"]
            traffic_gap_text = f"{int(round(gap))} aircraft"
    
        with o1:
            st.metric(
                "Highest Operational Stress",
                "N/A" if pd.isna(top_stress["operational_stress_score"]) else top_stress["airport_code"],
            )
        with o2:
            st.metric(
                "Highest Airline Delay Severity",
                "N/A" if pd.isna(top_airline["airline_delay_severity_index"]) else top_airline["airport_code"],
            )
        with o3:
            st.metric("Traffic Load Gap", traffic_gap_text)
        with o4:
            longest_text = "N/A"
            if not pd.isna(top_longest["longest_delay_recorded"]):
                longest_text = f"{top_longest['airport_code']} ({format_minutes_hr_min(top_longest['longest_delay_recorded'])})"
            st.metric("Longest Recorded Delay", longest_text)
        
        st.divider()
        
        
        # -----------------------
        # Latest snapshot cards
        # -----------------------
        st.subheader("Latest Airport Snapshot")
        
        traffic_latest_map = {}
        if not traffic_df.empty:
            # "Current Operational Load" should always reflect the most recent traffic snapshot,
            # regardless of the selected delay time window.
            traffic_cards = traffic_df[traffic_df["airport_code"].isin(selected_airports)].copy()
        
            latest_traffic_by_airport = (
                sort_values_df(traffic_cards, by="collected_at")
                .groupby("airport_code", as_index=False)
                .tail(1)
            )
            traffic_latest_map = {
                str(record["airport_code"]): record for record in records(latest_traffic_by_airport)
            }
        
        
        if len(latest_by_airport) == 2:
            left_col, divider_col, right_col = st.columns([1, 0.08, 1])
            with divider_col:
                st.markdown(
                    "<div style='height: 720px; border-left: 1px solid rgba(128,128,128,0.45); margin: 0 auto;'></div>",
                    unsafe_allow_html=True,
                )
            card_cols = [left_col, right_col]
        else:
            card_cols = st.columns(len(latest_by_airport))
        
        for idx, airport_row in enumerate(latest_by_airport_rows):
            airport_key = str(airport_row["airport_code"])
            collected_local = format_snapshot_time_for_airport(
                pd.to_datetime(airport_row["collected_at"], utc=True),
                airport_key,
            )
            traffic_row = traffic_latest_map.get(airport_key)
            airline_row = airline_severity_map.get(airport_key)
            airline_range_row = airline_range_map.get(airport_key)
            airline_max_today = longest_airline_today_map.get(airport_key)
            longest_any_recorded = max(
                [v for v in [longest_airline_all_time_map.get(airport_key), longest_faa_all_time_map.get(airport_key)] if v is not None],
                default=None
            )
            with card_cols[idx]:
                st.markdown("<div style='padding: 0 12px;'>", unsafe_allow_html=True)
                st.write(f"**Snapshot Time (Local):** {collected_local}")
                st.markdown("#### Snapshot Metrics")
                m11, m12 = st.columns(2)
                with m11:
                    st.metric(
                        label=f"{airport_row['airport_code']} Delay Severity Index (FAA)",
                        value="—" if pd.isna(airport_row["delay_index_best"]) else round(float(airport_row["delay_index_best"]), 3),
                    )
                with m12:
                    st.metric(
                        label=f"{airport_row['airport_code']} Airline Delay Severity Index",
                        value="N/A" if airline_row is None else airline_row["score"],
                    )

                m21, m22 = st.columns(2)
                with m21:
                    st.metric(
                        label=f"{airport_row['airport_code']} Traffic Load (Live Aircraft)",
                        value=int(airport_row["traffic_load_effective"]) if pd.notna(airport_row["traffic_load_effective"]) else "N/A",
                    )
                with m22:
                    st.metric(
                        label=f"{airport_row['airport_code']} Operational Stress Score",
                        value="—" if pd.isna(airport_row["operational_stress_score"]) else round(float(airport_row["operational_stress_score"]), 3),
                    )

                st.markdown("#### Additional Metrics")
                a11, a12 = st.columns(2)
                with a11:
                    st.metric(
                        label=f"{airport_row['airport_code']} Active FAA Restrictions",
                        value=int(airport_row["faa_event_count"]) if pd.notna(airport_row.get("faa_event_count")) else 0,
                    )
                with a12:
                    st.metric(
                        label=f"{airport_row['airport_code']} Delay Severity Index (FAA)",
                        value="—" if pd.isna(airport_row["delay_index_best"]) else round(float(airport_row["delay_index_best"]), 3),
                    )

                a21, a22 = st.columns(2)
                with a21:
                    st.metric(
                        label=f"{airport_row['airport_code']} Longest Recorded Delay (Any Source)",
                        value=format_minutes_hr_min(longest_any_recorded),
                    )
                with a22:
                    st.metric(
                        label=f"{airport_row['airport_code']} Longest Airline Delay Today",
                        value=format_minutes_hr_min(airline_max_today),
                    )
                st.write(
                    f"**FAA Update Time (Local):** "
                    f"{format_faa_update_time_for_airport(airport_row.get('faa_update_time'), airport_key)}"
                )
                st.caption("[View FAA NASStatus details](https://nasstatus.faa.gov/)")
                st.write(f"**FAA Status:** {airport_row.get('faa_status', '—') if airport_row.get('faa_status') else '—'}")
                average_delay_value = None if airline_row is None else airline_row.get("average_delay_min")
                st.write(
                    f"**Average Delay:** {format_minutes_hr_min(average_delay_value)}"
                    if pd.notna(average_delay_value)
                    else "**Average Delay:** N/A"
                )
                if airline_row is None:
                    st.write("**Airline Snapshot:** N/A")
                else:
                    airline_time = format_snapshot_time_for_airport(
                        pd.to_datetime(airline_row["snapshot_time"], utc=True),
                        airport_key,
                    )
                    st.write(f"**Airline Snapshot Time (Local):** {airline_time}")
                    range_cancel_text = "N/A"
                    if airline_range_row is not None:
                        range_cancel_text = f"{airline_range_row['cancel_rate_percent']}%"
                    st.write(
                        f"**Airline Inputs:** Flights {airline_row['flights_n']}, "
                        f"Average Delay {airline_row['average_delay_min']} min, "
                        f"Cancelled {airline_row['cancel_rate_percent']}% (Latest Snapshot), "
                        f"Cancelled {range_cancel_text} (Selected Time Range), "
                        f"Diverted {airline_row['divert_rate_percent']}%"
                    )
                st.markdown("#### Current Operational Load")
                if traffic_row is None:
                    st.write("No traffic snapshot available for this airport in selected time range.")
                else:
                    traffic_time_local = format_snapshot_time_for_airport(
                        pd.to_datetime(traffic_row["collected_at"], utc=True),
                        airport_key,
                    )
                    st.write(f"**Traffic Snapshot Time (Local):** {traffic_time_local}")
                    lc1, lc2, lc3 = st.columns(3)
                    with lc1:
                        st.metric("In Airspace", int(traffic_row["aircraft_count"]) if pd.notna(traffic_row.get("aircraft_count")) else "—")
                    with lc2:
                        st.metric("Airborne", int(traffic_row["airborne_count"]) if pd.notna(traffic_row.get("airborne_count")) else "—")
                    with lc3:
                        st.metric("On Ground", int(traffic_row["on_ground_count"]) if pd.notna(traffic_row.get("on_ground_count")) else "—")
                st.markdown("</div>", unsafe_allow_html=True)
        
        st.divider()
        # -----------------------
        # Hypothesis-focused comparison
        # -----------------------
        st.subheader("Hypothesis Check: Is MCO Disproportionately Worse Than DEN?")
        st.caption("This section combines FAA and airline-impact evidence with load-adjusted comparisons.")

        hypothesis_df = filtered.copy()
        hypothesis_df["delay_index_best"] = pd.to_numeric(hypothesis_df["delay_index_best"], errors="coerce")
        hypothesis_df["traffic_load_effective"] = pd.to_numeric(hypothesis_df["traffic_load_effective"], errors="coerce")
        hypothesis_df["faa_event_count"] = to_numeric_series(
            hypothesis_df["faa_event_count"], index=hypothesis_df.index
        ).fillna(0)
        hypothesis_df["has_faa_restriction"] = hypothesis_df["faa_event_count"] > 0

        hypothesis_summary = (
            hypothesis_df.groupby("airport_code", as_index=False)
            .agg(
                snapshots=("airport_code", "size"),
                average_delay_index=("delay_index_best", "mean"),
                average_traffic_load=("traffic_load_effective", "mean"),
                faa_restriction_rate=("has_faa_restriction", "mean"),
            )
        )
        hypothesis_summary["average_delay_index"] = to_numeric_series(
            hypothesis_summary["average_delay_index"], index=hypothesis_summary.index
        )
        hypothesis_summary["average_traffic_load"] = to_numeric_series(
            hypothesis_summary["average_traffic_load"], index=hypothesis_summary.index
        )
        hypothesis_summary["delay_per_100_load"] = (
            hypothesis_summary["average_delay_index"] /
            (hypothesis_summary["average_traffic_load"] / 100.0)
        )
        hypothesis_summary["faa_restriction_rate_percent"] = hypothesis_summary["faa_restriction_rate"] * 100.0

        airline_hypothesis = pd.DataFrame()
        if not flight_df.empty:
            airline_hypothesis = flight_df[flight_df["airport_code"].isin(selected_airports)].copy()
            airline_hypothesis = airline_hypothesis[
                airline_hypothesis["collected_at_local"].between(start_dt, end_dt)
            ]
            if not airline_hypothesis.empty:
                airline_hypothesis["delay_positive"] = airline_hypothesis["delay_minutes"].clip(lower=0)
                airline_summary = (
                    airline_hypothesis.groupby("airport_code", as_index=False)
                    .agg(
                        airline_flights=("delay_minutes", "size"),
                        average_airline_delay_min=("delay_positive", "mean"),
                        cancel_rate=("cancelled", "mean"),
                        divert_rate=("diverted", "mean"),
                    )
                )
                avg_airline_delay = to_numeric_series(
                    airline_summary["average_airline_delay_min"], index=airline_summary.index
                ).fillna(0)
                cancel_rate = to_numeric_series(
                    airline_summary["cancel_rate"], index=airline_summary.index
                ).fillna(0)
                divert_rate = to_numeric_series(
                    airline_summary["divert_rate"], index=airline_summary.index
                ).fillna(0)
                airline_summary["average_airline_severity"] = (
                    (avg_airline_delay / 20.0).clip(upper=3.0) +
                    (cancel_rate * 4.0).clip(upper=1.5) +
                    (divert_rate * 2.0).clip(upper=0.5)
                ).clip(upper=5.0)
                airline_summary["cancel_rate_percent"] = airline_summary["cancel_rate"] * 100.0
                airline_summary["divert_rate_percent"] = airline_summary["divert_rate"] * 100.0
                hypothesis_summary = hypothesis_summary.merge(airline_summary, on="airport_code", how="left")

        for col in [
            "airline_flights",
            "average_airline_delay_min",
            "cancel_rate_percent",
            "divert_rate_percent",
            "average_airline_severity",
        ]:
            if col not in hypothesis_summary.columns:
                hypothesis_summary[col] = pd.NA

        hypothesis_rows_by_airport = {
            str(rec["airport_code"]): rec for rec in records(hypothesis_summary)
        }

        denver_load_outperformance_note: str | None = None
        denver_daily_outperformance_note: str | None = None
        den_row = hypothesis_rows_by_airport.get("DEN")
        mco_row = hypothesis_rows_by_airport.get("MCO")
        if den_row is not None and mco_row is not None:
            den_load = safe_float(den_row.get("average_traffic_load"))
            mco_load = safe_float(mco_row.get("average_traffic_load"))
            den_delay_per_load = safe_float(den_row.get("delay_per_100_load"))
            mco_delay_per_load = safe_float(mco_row.get("delay_per_100_load"))

            if (
                den_load is not None
                and mco_load is not None
                and mco_load > 0
                and den_load >= (mco_load * 1.15)
                and den_delay_per_load is not None
                and mco_delay_per_load is not None
                and den_delay_per_load < mco_delay_per_load
            ):
                denver_load_outperformance_note = (
                    f"DEN is handling higher average traffic load ({den_load:.1f} vs {mco_load:.1f}) "
                    f"while maintaining better delay efficiency "
                    f"({den_delay_per_load:.2f} vs {mco_delay_per_load:.2f} delay index per 100 load)."
                )

        # Daily-level outperformance signal: on days where DEN is busier than MCO,
        # count how often DEN still has lower delay-per-100-load.
        daily_ops = (
            hypothesis_df.assign(local_date=series_date(hypothesis_df["collected_at_local"]))
            .groupby(["local_date", "airport_code"], as_index=False)
            .agg(
                avg_load=("traffic_load_effective", "mean"),
                avg_delay_index=("delay_index_best", "mean"),
            )
        )
        if not daily_ops.empty:
            daily_ops["avg_load"] = to_numeric_series(daily_ops["avg_load"], index=daily_ops.index)
            daily_ops["avg_delay_index"] = to_numeric_series(daily_ops["avg_delay_index"], index=daily_ops.index)
            daily_ops["delay_per_100_load"] = daily_ops["avg_delay_index"] / (daily_ops["avg_load"] / 100.0)

            daily_pivot = daily_ops.pivot(index="local_date", columns="airport_code", values=["avg_load", "delay_per_100_load"])
            if isinstance(daily_pivot, pd.DataFrame) and {"DEN", "MCO"}.issubset(set(daily_pivot.columns.get_level_values(1))):
                den_load_daily = daily_pivot[("avg_load", "DEN")]
                mco_load_daily = daily_pivot[("avg_load", "MCO")]
                den_dpl_daily = daily_pivot[("delay_per_100_load", "DEN")]
                mco_dpl_daily = daily_pivot[("delay_per_100_load", "MCO")]
                valid_days = den_load_daily.notna() & mco_load_daily.notna() & den_dpl_daily.notna() & mco_dpl_daily.notna() & (mco_load_daily > 0)
                den_busier = den_load_daily >= (mco_load_daily * 1.05)
                den_better_eff = den_dpl_daily < mco_dpl_daily
                busier_days = int((valid_days & den_busier).sum())
                better_when_busier_days = int((valid_days & den_busier & den_better_eff).sum())
                if busier_days > 0:
                    denver_daily_outperformance_note = (
                        f"Daily view: DEN was busier than MCO on {busier_days} day(s) in this range and "
                        f"still had better delay-per-100-load on {better_when_busier_days} of those day(s)."
                    )

        def build_ratio_df(metric_defs: list[tuple[str, str]]) -> pd.DataFrame:
            rows = []
            if {"MCO", "DEN"}.issubset(set(hypothesis_rows_by_airport)):
                for metric_key, metric_label in metric_defs:
                    den = hypothesis_rows_by_airport["DEN"].get(metric_key)
                    mco = hypothesis_rows_by_airport["MCO"].get(metric_key)
                    ratio = None
                    den_num = safe_float(den)
                    mco_num = safe_float(mco)
                    if den_num not in (None, 0.0) and mco_num is not None:
                        ratio = float(mco_num / den_num)
                    rows.append({"metric": metric_label, "mco_vs_den_ratio": ratio})
            ratio_df_local = pd.DataFrame(rows)
            if not ratio_df_local.empty:
                ratio_df_local["supports_mco_worse"] = ratio_df_local["mco_vs_den_ratio"] > 1.0
            return ratio_df_local

        st.markdown("### Airline Delay Comparison")
        st.dataframe(
            prettify_columns(
                hypothesis_summary[
                    [
                        "airport_code",
                        "airline_flights",
                        "average_airline_delay_min",
                        "cancel_rate_percent",
                        "divert_rate_percent",
                        "average_airline_severity",
                    ]
                ]
            ),
            width="stretch",
        )
        airline_ratio_df = build_ratio_df(
            [
                ("average_airline_delay_min", "Average Airline Delay (Minutes)"),
                ("cancel_rate_percent", "Cancellation Rate (%)"),
                ("average_airline_severity", "Airline Delay Severity"),
            ]
        )
        if airline_ratio_df.empty or airline_ratio_df["mco_vs_den_ratio"].dropna().empty:
            st.info("Not enough airline data in this range to compare MCO vs DEN.")
        else:
            airline_ratio_chart = px.bar(
                airline_ratio_df,
                x="metric",
                y="mco_vs_den_ratio",
                color="supports_mco_worse",
                title="Airline Delay Ratios: MCO vs DEN",
                labels={
                    "metric": "Metric",
                    "mco_vs_den_ratio": "MCO / DEN Ratio",
                    "supports_mco_worse": "Supports MCO Worse",
                },
                color_discrete_map={True: AIRPORT_COLOR_MAP["MCO"], False: AIRPORT_COLOR_MAP["DEN"]},
            )
            airline_ratio_chart.add_hline(y=1.0, line_dash="dash", line_color="gray")
            st.plotly_chart(airline_ratio_chart, width="stretch")
            airline_core = airline_ratio_df.loc[
                airline_ratio_df["metric"] == "Airline Delay Severity", "mco_vs_den_ratio"
            ].dropna()
            if not airline_core.empty:
                airline_verdict = "Supports hypothesis" if airline_core.iloc[0] > 1.0 else "Does not support hypothesis"
                st.write(
                    f"**Airline verdict:** {airline_verdict} "
                    f"(MCO/DEN airline severity ratio = {airline_core.iloc[0]:.2f})."
                )

        st.markdown("### Operational Load Comparison")
        st.dataframe(
            prettify_columns(
                hypothesis_summary[
                    [
                        "airport_code",
                        "snapshots",
                        "average_traffic_load",
                        "average_delay_index",
                        "delay_per_100_load",
                        "faa_restriction_rate_percent",
                    ]
                ]
            ),
            width="stretch",
        )
        operational_ratio_df = build_ratio_df(
            [
                ("average_traffic_load", "Average Traffic Load"),
                ("average_delay_index", "Average Delay Severity Index"),
                ("delay_per_100_load", "Delay Index Per 100 Traffic Load"),
                ("faa_restriction_rate_percent", "FAA Restriction Snapshot Rate (%)"),
            ]
        )
        if not operational_ratio_df.empty:
            operational_ratio_chart = px.bar(
                operational_ratio_df,
                x="metric",
                y="mco_vs_den_ratio",
                color="supports_mco_worse",
                title="Operational Ratios: MCO vs DEN",
                labels={
                    "metric": "Metric",
                    "mco_vs_den_ratio": "MCO / DEN Ratio",
                    "supports_mco_worse": "Supports MCO Worse",
                },
                color_discrete_map={True: AIRPORT_COLOR_MAP["MCO"], False: AIRPORT_COLOR_MAP["DEN"]},
            )
            operational_ratio_chart.add_hline(y=1.0, line_dash="dash", line_color="gray")
            st.plotly_chart(operational_ratio_chart, width="stretch")
            operational_core = operational_ratio_df.loc[
                operational_ratio_df["metric"] == "Delay Index Per 100 Traffic Load", "mco_vs_den_ratio"
            ].dropna()
            if not operational_core.empty:
                operational_verdict = "Supports hypothesis" if operational_core.iloc[0] > 1.0 else "Does not support hypothesis"
                st.write(
                    f"**Operational verdict:** {operational_verdict} "
                    f"(MCO/DEN delay-per-100-load ratio = {operational_core.iloc[0]:.2f})."
                )
                if denver_load_outperformance_note is not None:
                    st.info(denver_load_outperformance_note)
                if denver_daily_outperformance_note is not None:
                    st.info(denver_daily_outperformance_note)

        st.markdown("### Combined Evidence Comparison")
        st.dataframe(
            prettify_columns(
                hypothesis_summary[
                    [
                        "airport_code",
                        "snapshots",
                        "average_traffic_load",
                        "average_delay_index",
                        "delay_per_100_load",
                        "faa_restriction_rate_percent",
                        "airline_flights",
                        "average_airline_delay_min",
                        "cancel_rate_percent",
                        "divert_rate_percent",
                        "average_airline_severity",
                    ]
                ]
            ),
            width="stretch",
        )
        combined_ratio_df = build_ratio_df(
            [
                ("delay_per_100_load", "Delay Index Per 100 Traffic Load"),
                ("faa_restriction_rate_percent", "FAA Restriction Snapshot Rate (%)"),
                ("average_airline_delay_min", "Average Airline Delay (Minutes)"),
                ("cancel_rate_percent", "Cancellation Rate (%)"),
                ("average_airline_severity", "Airline Delay Severity"),
            ]
        )
        if not combined_ratio_df.empty:
            combined_ratio_chart = px.bar(
                combined_ratio_df,
                x="metric",
                y="mco_vs_den_ratio",
                color="supports_mco_worse",
                title="Combined Ratios: MCO vs DEN",
                labels={
                    "metric": "Metric",
                    "mco_vs_den_ratio": "MCO / DEN Ratio",
                    "supports_mco_worse": "Supports MCO Worse",
                },
                color_discrete_map={True: AIRPORT_COLOR_MAP["MCO"], False: AIRPORT_COLOR_MAP["DEN"]},
            )
            combined_ratio_chart.add_hline(y=1.0, line_dash="dash", line_color="gray")
            st.plotly_chart(combined_ratio_chart, width="stretch")

            operational_core_series = combined_ratio_df.loc[
                combined_ratio_df["metric"] == "Delay Index Per 100 Traffic Load", "mco_vs_den_ratio"
            ].dropna()
            airline_core_series = combined_ratio_df.loc[
                combined_ratio_df["metric"] == "Airline Delay Severity", "mco_vs_den_ratio"
            ].dropna()

            operational_core = float(operational_core_series.iloc[0]) if not operational_core_series.empty else None
            airline_core = float(airline_core_series.iloc[0]) if not airline_core_series.empty else None

            if operational_core is not None and airline_core is not None:
                combined_ratio = float((operational_core + airline_core) / 2.0)
                operational_supports = operational_core > 1.0
                airline_supports = airline_core > 1.0
                if operational_supports and airline_supports:
                    verdict_text = "supports the hypothesis on both operational and airline sides"
                elif operational_supports:
                    verdict_text = "is mixed: operational evidence supports the hypothesis, but airline evidence does not"
                elif airline_supports:
                    verdict_text = "is mixed: airline evidence supports the hypothesis, but operational evidence does not"
                else:
                    verdict_text = "does not support the hypothesis on either operational or airline side"

                st.write(
                    f"**Combined verdict:** Evidence {verdict_text}. "
                    f"Operational ratio = {operational_core:.2f}, airline ratio = {airline_core:.2f}, "
                    f"mean core ratio = {combined_ratio:.2f}."
                )
                if denver_load_outperformance_note is not None:
                    st.info(denver_load_outperformance_note)
                if denver_daily_outperformance_note is not None:
                    st.info(denver_daily_outperformance_note)
            elif operational_core is not None:
                verdict_text = "supports the hypothesis" if operational_core > 1.0 else "does not support the hypothesis"
                st.write(
                    f"**Combined verdict:** Airline-side core metric is unavailable in this range. "
                    f"Operational evidence {verdict_text} (ratio = {operational_core:.2f})."
                )
            elif airline_core is not None:
                verdict_text = "supports the hypothesis" if airline_core > 1.0 else "does not support the hypothesis"
                st.write(
                    f"**Combined verdict:** Operational core metric is unavailable in this range. "
                    f"Airline evidence {verdict_text} (ratio = {airline_core:.2f})."
                )

        st.divider()
        # -----------------------
        # FAA status history
        # -----------------------
        st.subheader("FAA Status History")
        st.caption("Historical FAA status snapshots for each airport in the selected time range.")

        faa_status_history = filtered.copy()
        faa_status_history["faa_event_count"] = to_numeric_series(
            faa_status_history["faa_event_count"], index=faa_status_history.index
        ).fillna(0)
        faa_status_history["faa_status_clean"] = (
            faa_status_history["faa_status"].fillna("").astype(str).str.strip()
        )
        faa_status_history.loc[
            faa_status_history["faa_status_clean"] == "",
            "faa_status_clean"
        ] = "Unknown / Missing"

        if faa_status_history.empty:
            st.info("No FAA status snapshots available in the selected range.")
        else:
            status_counts = sort_values_df(
                faa_status_history.groupby(["airport_code", "faa_status_clean"], as_index=False)
                .agg(snapshot_count=("faa_status_clean", "size")),
                by=["snapshot_count", "airport_code"],
                ascending=[False, True],
            )

            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                status_counts_chart = px.bar(
                    status_counts,
                    x="faa_status_clean",
                    y="snapshot_count",
                    color="airport_code",
                    barmode="group",
                    title="FAA Status Snapshot Counts By Airport",
                    labels={
                        "faa_status_clean": "FAA Status",
                        "snapshot_count": "Snapshots",
                        "airport_code": "Airport",
                    },
                )
                status_counts_chart.update_xaxes(categoryorder="total descending")
                st.plotly_chart(status_counts_chart, width="stretch")

            with chart_col2:
                timeline_df = sort_values_df(faa_status_history, by=["airport_code", "collected_at"]).copy()
                timeline_chart = px.line(
                    timeline_df,
                    x="collected_at_local",
                    y="faa_event_count",
                    color="airport_code",
                    markers=True,
                    title="Active FAA Restriction Count Over Time",
                    labels={
                        "collected_at_local": "Snapshot Time (Local)",
                        "faa_event_count": "Active FAA Restrictions",
                        "airport_code": "Airport",
                    },
                )
                format_time_axis_12h(timeline_chart)
                st.plotly_chart(timeline_chart, width="stretch")

            delayed_daily = (
                faa_status_history.assign(
                    local_date=series_date(faa_status_history["collected_at_local"]),
                    has_delay=faa_status_history["faa_event_count"] > 0,
                )
                .groupby(["local_date", "airport_code"], as_index=False)
                .agg(
                    delayed_snapshots=("has_delay", "sum"),
                    total_snapshots=("has_delay", "size"),
                )
            )
            delayed_daily["local_date"] = pd.to_datetime(delayed_daily["local_date"])

            delayed_daily_chart = px.bar(
                delayed_daily,
                x="local_date",
                y="delayed_snapshots",
                color="airport_code",
                barmode="group",
                custom_data=["total_snapshots"],
                title="Daily FAA Delayed Snapshot Count",
                labels={
                    "local_date": "Local Date",
                    "delayed_snapshots": "Snapshots With Active FAA Restrictions",
                    "airport_code": "Airport",
                },
            )
            delayed_daily_chart.update_traces(
                hovertemplate=(
                    "Date: %{x|%B %d}<br>"
                    "Airport: %{fullData.name}<br>"
                    "Delayed Snapshots: %{y:.0f}<br>"
                    "Total Snapshots: %{customdata[0]:.0f}<extra></extra>"
                )
            )
            delayed_daily_chart.update_xaxes(tickformat="%B %d")
            st.plotly_chart(delayed_daily_chart, width="stretch")

            with st.expander("Show FAA status log"):
                status_log = faa_status_history.copy()
                status_log = status_log[status_log["faa_event_count"] > 0].copy()
                status_log["collected_at_local_label"] = status_log["collected_at_local"].dt.strftime(
                    "%I:%M %p %B %d"
                )
                status_log["faa_update_time_local_label"] = status_log["faa_update_time"].apply(
                    format_faa_update_time_local
                )
                log_cols = [
                    "airport_code",
                    "collected_at_local_label",
                    "faa_update_time_local_label",
                    "faa_event_count",
                    "faa_status_clean",
                    "delay_index_best",
                    "delay_median_minutes",
                ]
                if status_log.empty:
                    st.info("No FAA-restricted snapshots in this selected time range.")
                else:
                    st.dataframe(
                        prettify_columns(
                            sort_values_df(status_log, by="collected_at_local", ascending=False)[log_cols]
                        ),
                        width="stretch",
                    )

        st.divider()
        # -----------------------
        # Airline Impact
        # -----------------------
        st.subheader("Airline Delay Impact")
        st.caption("This section uses live AirLabs delay feed values to show passenger-facing delay impact.")

        if flight_df.empty:
            st.info("No flight delay data found yet. Run `python src/collect_flights.py`.")
        else:
            flight_view = flight_df[flight_df["airport_code"].isin(selected_airports)].copy()
            flight_view = flight_view[flight_view["collected_at_local"].between(start_dt, end_dt)]

            if flight_view.empty:
                st.info("No flight delay rows in the selected time range.")
            else:
                flight_view["delay_positive"] = flight_view["delay_minutes"].clip(lower=0)
                airline_snap = (
                    flight_view.groupby(["airport_code", "collected_at_local"], as_index=False)
                    .agg(
                        flights=("delay_minutes", "size"),
                        average_delay_min=("delay_positive", "mean"),
                        max_delay_min=("delay_positive", "max"),
                        cancel_rate=("cancelled", "mean"),
                        divert_rate=("diverted", "mean"),
                    )
                )
                avg_delay_min = to_numeric_series(
                    airline_snap["average_delay_min"], index=airline_snap.index
                ).fillna(0)
                cancel_rate_snap = to_numeric_series(
                    airline_snap["cancel_rate"], index=airline_snap.index
                ).fillna(0)
                divert_rate_snap = to_numeric_series(
                    airline_snap["divert_rate"], index=airline_snap.index
                ).fillna(0)
                airline_snap["airline_delay_severity_index"] = (
                    (avg_delay_min / 20.0).clip(upper=3.0) +
                    (cancel_rate_snap * 4.0).clip(upper=1.5) +
                    (divert_rate_snap * 2.0).clip(upper=0.5)
                ).clip(upper=5.0)

                a1, a2 = st.columns(2)
                with a1:
                    airline_severity_chart = px.line(
                        airline_snap,
                        x="collected_at_local",
                        y="airline_delay_severity_index",
                        color="airport_code",
                        markers=True,
                        title="Airline Delay Severity Index Over Time",
                        labels={
                            "collected_at_local": "Snapshot Time (Local)",
                            "airline_delay_severity_index": "Airline Delay Severity Index",
                            "airport_code": "Airport",
                        },
                    )
                    format_time_axis_12h(airline_severity_chart)
                    st.plotly_chart(airline_severity_chart, width="stretch")

                with a2:
                    airline_snap["max_delay_hr_min"] = airline_snap["max_delay_min"].apply(format_minutes_hr_min)
                    airline_snap["max_delay_hours"] = airline_snap["max_delay_min"] / 60.0
                    longest_delay_chart = px.line(
                        airline_snap,
                        x="collected_at_local",
                        y="max_delay_hours",
                        color="airport_code",
                        markers=True,
                        title="Longest Airline Delay By Snapshot",
                        custom_data=["max_delay_hr_min", "max_delay_min"],
                        labels={
                            "collected_at_local": "Snapshot Time (Local)",
                            "max_delay_hours": "Longest Airline Delay (Hours)",
                            "airport_code": "Airport",
                        },
                    )
                    longest_delay_chart.update_traces(
                        hovertemplate=(
                            "Airport: %{fullData.name}<br>"
                            "Snapshot: %{x}<br>"
                            "Delay: %{customdata[0]}<br>"
                            "(%{customdata[1]:.0f} minutes)<extra></extra>"
                        ),
                    )
                    format_time_axis_12h(longest_delay_chart)
                    st.plotly_chart(longest_delay_chart, width="stretch")

                daily_cancel = (
                    flight_view.assign(local_date=series_date(flight_view["collected_at_local"]))
                    .groupby(["local_date", "airport_code"], as_index=False)
                    .agg(
                        flights=("delay_minutes", "size"),
                        cancelled_count=("cancelled", "sum"),
                    )
                )
                cancelled_count = to_numeric_series(
                    daily_cancel["cancelled_count"], index=daily_cancel.index
                )
                flights_count = to_numeric_series(
                    daily_cancel["flights"], index=daily_cancel.index
                )
                daily_cancel["cancel_rate_percent"] = (
                    (cancelled_count / flights_count).replace([float("inf"), float("-inf")], 0).fillna(0) * 100.0
                )
                daily_cancel["local_date"] = pd.to_datetime(daily_cancel["local_date"])

                cancel_rate_chart = px.bar(
                    daily_cancel,
                    x="local_date",
                    y="cancel_rate_percent",
                    color="airport_code",
                    barmode="group",
                    custom_data=["cancelled_count", "flights"],
                    title="Daily Airline Cancellation Rate Comparison",
                    labels={
                        "local_date": "Local Date",
                        "cancel_rate_percent": "Cancellation Rate (%)",
                        "airport_code": "Airport",
                    },
                )
                cancel_rate_chart.update_traces(
                    hovertemplate=(
                        "Date: %{x|%B %d}<br>"
                        "Airport: %{fullData.name}<br>"
                        "Cancellation Rate: %{y:.1f}%<br>"
                        "Cancelled Flights: %{customdata[0]:.0f}<br>"
                        "Flights Sampled: %{customdata[1]:.0f}<extra></extra>"
                    )
                )
                st.plotly_chart(cancel_rate_chart, width="stretch")

                today_rows = []
                for airport in selected_airports:
                    airline_today = longest_airline_today_map.get(airport)
                    any_recorded = max(
                        [v for v in [longest_airline_all_time_map.get(airport), longest_faa_all_time_map.get(airport)] if v is not None],
                        default=None
                    )
                    today_rows.append({"airport_code": airport, "metric": "Longest Airline Delay Today", "delay_minutes": airline_today})
                    today_rows.append({"airport_code": airport, "metric": "Longest Recorded Delay (Any Source)", "delay_minutes": any_recorded})

                today_df = pd.DataFrame(today_rows)
                today_df = today_df[today_df["delay_minutes"].notna()]
                if not today_df.empty:
                    today_df["delay_hours"] = today_df["delay_minutes"] / 60.0
                    today_df["delay_hr_min"] = today_df["delay_minutes"].apply(format_minutes_hr_min)
                    today_compare_chart = px.bar(
                        today_df,
                        x="airport_code",
                        y="delay_hours",
                        color="metric",
                        text="delay_hr_min",
                        custom_data=["delay_hr_min", "delay_minutes"],
                        barmode="group",
                        title="Longest Delay Today Comparison",
                        labels={
                            "airport_code": "Airport",
                            "delay_hours": "Delay (Hours)",
                            "metric": "Metric",
                        },
                    )
                    today_compare_chart.update_traces(
                        textposition="outside",
                        hovertemplate=(
                            "Airport: %{x}<br>"
                            "Metric: %{fullData.name}<br>"
                            "Delay: %{customdata[0]}<br>"
                            "(%{customdata[1]:.0f} minutes)<extra></extra>"
                        ),
                    )
                    st.plotly_chart(today_compare_chart, width="stretch")

        st.divider()
        # -----------------------
        # Trends + Rolling Average
        # -----------------------
        st.subheader("Trend Lines")
        st.caption("Use this section to see whether one airport consistently runs worse over time.")
        
        rolling_window = 6
        
        trend = sort_values_df(filtered, by=["airport_code", "collected_at"]).copy()
        for numeric_col in ["delay_index_best", "traffic_load_effective", "operational_stress_score"]:
            trend[numeric_col] = pd.to_numeric(trend[numeric_col], errors="coerce")
        def rolling_mean(series: pd.Series) -> pd.Series:
            return series.rolling(rolling_window, min_periods=1).mean()

        trend["delay_index_roll"] = trend.groupby("airport_code")["delay_index_best"].transform(rolling_mean)
        trend["load_roll"] = trend.groupby("airport_code")["traffic_load_effective"].transform(rolling_mean)
        trend["stress_roll"] = trend.groupby("airport_code")["operational_stress_score"].transform(rolling_mean)
        trend_col1, trend_col2 = st.columns(2)

        with trend_col1:
            trend_delay_chart = px.line(
                trend,
                x="collected_at_local",
                y="delay_index_roll",
                color="airport_code",
                markers=True,
                title=f"Delay Severity Index (Rolling Average, {rolling_window} Points)",
                labels={
                    "collected_at_local": "Snapshot Time (Local)",
                    "delay_index_roll": "Delay Severity Index",
                    "airport_code": "Airport",
                },
                color_discrete_map=AIRPORT_COLOR_MAP,
            )
            format_time_axis_12h(trend_delay_chart)
            st.plotly_chart(trend_delay_chart, width="stretch")

        with trend_col2:
            trend_stress_chart = px.line(
                trend,
                x="collected_at_local",
                y="stress_roll",
                color="airport_code",
                markers=True,
                title=f"Operational Stress Score (Rolling Average, {rolling_window} Points)",
                labels={
                    "collected_at_local": "Snapshot Time (Local)",
                    "stress_roll": "Operational Stress Score",
                    "airport_code": "Airport",
                },
                color_discrete_map=AIRPORT_COLOR_MAP,
            )
            format_time_axis_12h(trend_stress_chart)
            st.plotly_chart(trend_stress_chart, width="stretch")

        st.divider()
        
        
        # -----------------------
        # Load vs Delay (Efficiency curve)
        # -----------------------
        st.subheader("Traffic Load vs Delay Severity")
        st.caption("Interpretation focus: if MCO stays above DEN at similar load bands, that supports disproportionate pain.")
        
        load_vs_delay = trend.dropna(subset=["traffic_load_effective", "delay_index_best"]).copy()
        
        if load_vs_delay.empty:
            st.info("Not enough valid load + delay data points yet to plot this chart.")
        else:
            c1, c2 = st.columns(2)

            with c1:
                scatter_chart = px.scatter(
                    load_vs_delay,
                    x="traffic_load_effective",
                    y="delay_index_best",
                    color="airport_code",
                    opacity=0.45,
                    hover_data=["collected_at_local_label", "window_from_utc", "window_to_utc", "dep_total", "arr_total"],
                    title="Raw Snapshots: Delay Severity vs Traffic Load",
                    labels={
                        "traffic_load_effective": "Traffic Load",
                        "delay_index_best": "Delay Severity Index",
                        "airport_code": "Airport",
                        "collected_at_local_label": "Snapshot Time (Local)",
                        "window_from_utc": "Window From",
                        "window_to_utc": "Window To",
                        "dep_total": "Departures Counted",
                        "arr_total": "Arrivals Counted",
                    },
                    color_discrete_map=AIRPORT_COLOR_MAP,
                )
                st.plotly_chart(scatter_chart, width="stretch")

            with c2:
                bucket_input = load_vs_delay[["airport_code", "traffic_load_effective", "delay_index_best"]].copy()
                bucket_input = sort_values_df(bucket_input, by="traffic_load_effective")
                bucket_count = min(8, bucket_input["traffic_load_effective"].nunique())
                if bucket_count >= 2:
                    bucket_input["load_bucket"] = pd.qcut(
                        bucket_input["traffic_load_effective"],
                        q=bucket_count,
                        duplicates="drop",
                    )
                    by_bucket = (
                        bucket_input.groupby(["airport_code", "load_bucket"], as_index=False, observed=True)
                        .agg(
                            average_delay_index=("delay_index_best", "mean"),
                            samples=("delay_index_best", "size"),
                        )
                    )
                    by_bucket["load_bucket_mid"] = by_bucket["load_bucket"].apply(
                        lambda i: float((i.left + i.right) / 2.0)
                    )
                    sort_order = to_numeric_series(by_bucket["load_bucket_mid"], index=by_bucket.index).argsort()
                    by_bucket_sorted = by_bucket.iloc[sort_order.to_numpy()].copy()
                    bucket_chart = px.line(
                        by_bucket_sorted,
                        x="load_bucket_mid",
                        y="average_delay_index",
                        color="airport_code",
                        markers=True,
                        title="Same-Load Comparison: Average Delay by Load Band",
                        labels={
                            "load_bucket_mid": "Traffic Load Band Midpoint",
                            "average_delay_index": "Average Delay Severity Index",
                            "airport_code": "Airport",
                        },
                        color_discrete_map=AIRPORT_COLOR_MAP,
                        hover_data=["samples"],
                    )
                    st.plotly_chart(bucket_chart, width="stretch")
                else:
                    st.info("Need more variation in traffic load to build same-load comparison bands.")
        
        st.divider()
        
        
        # -----------------------
        # Delay timing breakdown
        # -----------------------
        st.subheader("Delay Timing Breakdown")
        st.caption("Easier read: where each airport tends to run worse by weekday and by hour.")

        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        timing_df = filtered.dropna(subset=["delay_index_best"]).copy()
        timing_df["dow_utc"] = pd.Categorical(timing_df["dow_utc"], categories=dow_order, ordered=True)

        if timing_df.empty:
            st.info("Not enough delay data in this range to show timing breakdown.")
        else:
            t1, t2 = st.columns(2)

            with t1:
                by_dow_raw = timing_df.groupby(
                    ["dow_utc", "airport_code"], as_index=False, observed=True
                ).agg(average_delay_index=("delay_index_best", "mean"))
                dow_codes = pd.Categorical(
                    by_dow_raw["dow_utc"], categories=dow_order, ordered=True
                )
                dow_order_idx = pd.Series(dow_codes.codes, index=by_dow_raw.index).argsort(kind="mergesort")
                by_dow = by_dow_raw.iloc[dow_order_idx.to_numpy()].copy()
                dow_chart = px.bar(
                    by_dow,
                    x="dow_utc",
                    y="average_delay_index",
                    color="airport_code",
                    barmode="group",
                    title="Average Delay Severity by Day of Week",
                    labels={
                        "dow_utc": "Day of Week (Local)",
                        "average_delay_index": "Average Delay Severity Index",
                        "airport_code": "Airport",
                    },
                    color_discrete_map=AIRPORT_COLOR_MAP,
                )
                st.plotly_chart(dow_chart, width="stretch")

            with t2:
                by_hour_raw = timing_df.groupby(
                    ["hour_utc", "airport_code"], as_index=False
                ).agg(average_delay_index=("delay_index_best", "mean"))
                hour_order_idx = to_numeric_series(by_hour_raw["hour_utc"], index=by_hour_raw.index).argsort(
                    kind="mergesort"
                )
                by_hour = by_hour_raw.iloc[hour_order_idx.to_numpy()].copy()
                by_hour = by_hour[by_hour["hour_utc"] >= 7]
                if by_hour.empty:
                    st.info("No hourly data available after restricting to hours 7-23.")
                else:
                    hour_chart = px.line(
                        by_hour,
                        x="hour_utc",
                        y="average_delay_index",
                        color="airport_code",
                        markers=True,
                        title="Average Delay Severity by Hour of Day (Hours 7-23)",
                        labels={
                            "hour_utc": "Hour of Day (Local)",
                            "average_delay_index": "Average Delay Severity Index",
                            "airport_code": "Airport",
                        },
                        color_discrete_map=AIRPORT_COLOR_MAP,
                    )
                    hour_chart.update_xaxes(dtick=1)
                    st.plotly_chart(hour_chart, width="stretch")
