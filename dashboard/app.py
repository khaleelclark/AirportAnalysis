from pathlib import Path
import os
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
        Based on personal travel experience, MCO appears to deliver a worse operational experience than DEN despite generally facing lower operational load and fewer environmental constraints.
        If DEN can sustain better performance under heavier and more complex conditions, then MCO's poorer outcomes suggest factors beyond external load alone.
        This project tests whether MCO has disproportionately worse operational outcomes than DEN after normalizing for load and timing context, using FAA downtime and airline disruption metrics as the primary evidence.

        ### Data Sources
        - **FAA NASStatus API** for airport-level delay programs and restrictions
        - **Live Airspace Traffic API** for aircraft activity in each airport area
        - **AirLabs Delay API** for flight-level airline delay, cancellation, and diversion signals

        ### Refresh Cadence
        - FAA Delays: every **10 minutes**
        - Traffic: every **10 minutes**
        - Airline Delay: collector runs every **10 minutes**, but AirLabs API calls are **strictly throttled to 2-hour minimum intervals per airport**, and only during each airport's **local 9 AM to 11 PM** window
        - Manual sync from the dashboard can force an immediate AirLabs call (intended for on-demand checks)

        ### Key Metrics
        - **Delay Severity Index (FAA Operational):** 0 means no active FAA restriction; higher means more severe operational restriction.
        - **Airline Delay Severity Index:** live airline-impact score from delays/cancellations/diversions.
        - **Traffic Load:** live aircraft count in airspace near each airport.
        - **Operational Stress Score:** combined measure of traffic pressure and FAA delay severity.

        ### How The Dashboard Tests The Hypothesis
        - **Decision Summary:** uses two primary core metrics:
          FAA downtime minutes per 100 traffic load (operational core) and Airline Delay Severity (passenger core).
        - **Top-Line Verdict:** combines both core metrics with reliability weighting and confidence tags.
        - **Supporting Context:** keeps secondary metrics and drill-down details without driving the headline verdict.
        - **DEN Outperformance Callouts:** explicitly flags when DEN carries higher load but still shows better delay efficiency overall and by day.
        - **Simplified Readability Pass:** timing and airline visuals were consolidated to daily-focused trends and one combined weekday timing chart to reduce chart noise.

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
        - **Hypothesis Check**:
          Decision Summary (two primary metrics + top-line verdict) plus Supporting Context.
        - **FAA Status History**:
          Restriction summary cards, daily restriction rate trend, daily peak active restrictions, and optional status-category breakdown.
        - **Airline Delay Impact**:
          Daily passenger-facing trend view from AirLabs delays, cancellations, and diversions.
        - **Trend Lines**:
          Rolling delay and rolling operational stress trends over time.
        - **Traffic Load Vs Delay Severity**:
          Raw scatter plus same-load band comparison to judge fairness at similar traffic.
        - **Delay Timing Breakdown**:
          Combined weekday comparison of overall delay (FAA + airline) for passenger-centered timing context.

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

        ### 2) Hypothesis Check Ratios
        The hypothesis section compares MCO vs DEN as:
        - `ratio = metric_at_MCO / metric_at_DEN`
        - `ratio > 1.0`: supports "MCO worse" for that metric
        - `ratio <= 1.0`: does not support "MCO worse" for that metric
        - Cross-airport comparisons use shared airport-local clock slots
          (for example, DEN 9 AM is compared against MCO 9 AM).
        - Verdicts are gated by minimum sample thresholds and include confidence tags.
        - Core ratio confidence uses bootstrap 95% confidence intervals.
        - FAA downtime normalization uses a traffic-load floor to reduce low-load blowups.
        - Combined core uses reliability-weighted evidence (not an equal average).

        Primary core metrics:
        - `operational_core = ratio(downtime_per_100_load)`
        - `airline_core = ratio(average_airline_severity)`
        - `combined_core_weighted = weighted_mean(operational_core, airline_core)` using available evidence sample sizes
        Top-line verdict is based on the weighted core and confidence gates.
        Secondary metrics are shown as supporting context only.
        Additional context callouts are shown when DEN is busier but still more efficient:
        - Snapshot-average callout: `DEN avg load >= 1.15 * MCO avg load` and `DEN downtime_per_100_load < MCO downtime_per_100_load`
        - Daily callout: by local date means, DEN busier (`>= 1.05 * MCO load`) and still lower downtime-per-100-load

        ### 3) FAA Status History
        Built from FAA snapshots in the selected range:
        - Restriction Snapshot Rate: `delayed_snapshots / snapshots`
        - Most Common Restriction: most frequent non-empty/non-"no active restriction" status string
        - Peak Active Restrictions: max `faa_event_count` seen in range
        - Daily FAA Restriction Rate trend and Daily Peak Active Restrictions trend
        - Optional status category breakdown in an expander

        ### 4) Airline Delay Impact
        Uses flight-level rows in selected range:
        - Snapshot-level airline severity is computed first, then summarized by operational day
        - Daily Airline Delay Severity Index: mean of snapshot severities per day
        - Daily Longest Airline Delay: robust daily longest-delay trend using the 90th percentile of snapshot max delays (label simplified in UI)
        - Daily Airline Cancellation Rate Comparison
        - Longest Delay Today Comparison (today airline max vs all-time any-source max)

        ### 5) Trend Lines
        Rolling time-series by airport:
        - Delay Severity Index rolling average
        - Operational Stress Score rolling average

        ### 6) Traffic Load Vs Delay Severity
        Two views in selected range:
        - Raw snapshot scatter (`traffic_load_effective` vs `delay_index_best`)
        - Same-load bucket comparison (average delay by load band)

        ### 7) Delay Timing Breakdown
        Timing is intentionally simplified:
        - FAA and airline delay rows are combined into one passenger-centric delay signal
        - One chart is shown: Average Overall Delay by Day of Week (airport-local)
        - The previous half-hour timing chart was removed to reduce skew/noise and improve readability

        ### Data Collection Cadence
        - FAA Delays: every 10 minutes
        - Traffic: every 10 minutes
        - Airline collector runs every 10 minutes but only calls AirLabs per airport when:
          - airport local time is between 9 AM and 11 PM
          - at least 2 hours have elapsed since that airport's last AirLabs call attempt
        - Manual dashboard sync can bypass this AirLabs throttle/window for immediate on-demand refresh
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
              Shows FAA restriction summary cards, daily restriction-rate trend, daily peak active restrictions, and optional status-category breakdown.
            - **Airline Delay Impact**:
              Shows daily airline severity, daily longest-delay trend, and daily cancellation rates.
            - **Hypothesis Check**:
              Starts with a Decision Summary using two primary metrics:
              FAA downtime-per-load (operational core) and airline delay severity (passenger core).
              A top-line verdict is shown only when quality gates are met; otherwise it is withheld.
              Secondary metrics are available in Supporting Context.
            - **Trend Lines**:
              Shows rolling delay severity and rolling operational stress.
            - **Traffic Load Vs Delay Severity**:
              Use raw scatter and same-load bands together to judge fairness at similar traffic levels.
            - **Delay Timing Breakdown**:
              Uses one combined FAA+airline weekday chart for easier comparison and less noise.
            - **How To Interpret Quickly**:
              For operational evidence, focus on **FAA downtime minutes per 100 traffic load** and its confidence label.
              For passenger-facing evidence, focus on **Airline Delay Severity** and its confidence label.
              If only one side supports the hypothesis, treat the result as mixed rather than definitive.
            - **Cadence**:
              FAA Delays every 10 minutes, Traffic every 10 minutes.
              Airline collector runs every 10 minutes but only calls AirLabs at 2-hour minimum intervals per airport
              during each airport's local 9 AM to 11 PM window.
              Manual sync can force AirLabs immediately; use that button sparingly to protect API quota.
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

    def bootstrap_ratio_ci(
        paired_df: pd.DataFrame,
        mco_col: str,
        den_col: str,
        *,
        iterations: int = 1000,
    ) -> tuple[float, float] | None:
        if paired_df.empty:
            return None
        work = paired_df[[mco_col, den_col]].copy()
        work[mco_col] = to_numeric_series(work[mco_col], index=work.index)
        work[den_col] = to_numeric_series(work[den_col], index=work.index)
        work = work.dropna(subset=[mco_col, den_col])
        work = work[work[den_col] > 0]
        if len(work) < 3:
            return None
        ratios: list[float] = []
        for i in range(iterations):
            sample = work.sample(n=len(work), replace=True, random_state=17 + i)
            den_mean = float(sample[den_col].mean())
            mco_mean = float(sample[mco_col].mean())
            if den_mean > 0:
                ratios.append(mco_mean / den_mean)
        if len(ratios) < 10:
            return None
        q = pd.Series(ratios).quantile([0.025, 0.975])
        return float(q.iloc[0]), float(q.iloc[1])

    def confidence_tag(
        sample_size: int,
        min_needed: int,
        ci: tuple[float, float] | None,
    ) -> str:
        if sample_size < min_needed:
            return "Low"
        if ci is None:
            return "Low"
        ci_width = float(ci[1] - ci[0])
        if sample_size >= (min_needed * 3) and ci_width <= 0.35:
            return "High"
        if sample_size >= (min_needed * 2) and ci_width <= 0.7:
            return "Medium"
        return "Low"
    
    
    LOCAL_TZ = datetime.now().astimezone().tzinfo
    OPERATIONAL_DAY_START_HOUR = 7
    AIRPORT_TIMEZONES = {
        "MCO": ZoneInfo("America/New_York"),
        "DEN": ZoneInfo("America/Denver"),
    }
    AIRPORT_COLOR_MAP = {
        "MCO": "#1f77b4",
        "DEN": "#ff7f0e",
    }

    def add_airport_local_clock_fields(df: pd.DataFrame, ts_col: str = "collected_at") -> pd.DataFrame:
        if df.empty:
            out = df.copy()
            out["airport_local_slot"] = pd.Series(dtype="object")
            out["airport_local_date"] = pd.Series(dtype="object")
            out["airport_local_hour"] = pd.Series(dtype="Int64")
            out["airport_local_half_hour"] = pd.Series(dtype="float")
            out["airport_local_dow"] = pd.Series(dtype="object")
            return out
        out = df.copy()
        out["airport_local_slot"] = ""
        out["airport_local_date"] = pd.NA
        out["airport_local_hour"] = pd.NA
        out["airport_local_half_hour"] = pd.NA
        out["airport_local_dow"] = pd.NA
        for airport_key, idx in out.groupby("airport_code").groups.items():
            tz = AIRPORT_TIMEZONES.get(str(airport_key), LOCAL_TZ)
            local_series = tz_convert_series(out.loc[idx, ts_col], tz)
            operational_local = local_series - pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
            out.loc[idx, "airport_local_slot"] = local_series.dt.strftime("%Y-%m-%d %H:00")
            out.loc[idx, "airport_local_date"] = operational_local.dt.strftime("%Y-%m-%d")
            out.loc[idx, "airport_local_hour"] = local_series.dt.hour
            out.loc[idx, "airport_local_half_hour"] = (
                local_series.dt.hour + (local_series.dt.minute >= 30).astype(int) * 0.5
            )
            out.loc[idx, "airport_local_dow"] = local_series.dt.day_name()
        out["airport_local_hour"] = pd.to_numeric(out["airport_local_hour"], errors="coerce")
        out["airport_local_half_hour"] = pd.to_numeric(out["airport_local_half_hour"], errors="coerce")
        return out

    def align_to_shared_local_slots(df: pd.DataFrame, airports: list[str]) -> pd.DataFrame:
        if df.empty:
            return df.copy()
        out = df[df["airport_code"].isin(airports)].copy()
        needed = len(airports)
        slot_counts = (
            out.groupby("airport_local_slot", as_index=False)
            .agg(airports_present=("airport_code", "nunique"))
        )
        shared_slots = set(
            slot_counts.loc[slot_counts["airports_present"] >= needed, "airport_local_slot"]
            .astype(str)
            .tolist()
        )
        return out[out["airport_local_slot"].astype(str).isin(shared_slots)].copy()
    
    
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

    def format_date_axis(chart):
        chart.update_xaxes(tickformat="%B %d", hoverformat="%I:%M %p %B %d")
        return chart

    def to_plot_local_naive(series: pd.Series) -> pd.Series:
        dt_index = pd.DatetimeIndex(series)
        if dt_index.tz is not None:
            dt_index = dt_index.tz_localize(None)
        return pd.Series(dt_index, index=series.index)
    
    
    def run_manual_sync_collectors() -> list[dict]:
        python_bin = sys.executable
        commands = [
            ("FAA Delays", [python_bin, "src/collect_delays.py"], None),
            ("Live Airspace Traffic", [python_bin, "src/collect_traffic.py"], None),
            ("Airline Delay", [python_bin, "src/collect_flights.py"], {"AIRLABS_FORCE_SYNC": "1"}),
        ]
        results = []
        for label, cmd, env_overrides in commands:
            env = None
            if env_overrides:
                env = dict(os.environ)
                env.update(env_overrides)
            proc = subprocess.run(
                cmd,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
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
        flight_df = add_airport_local_clock_fields(flight_df, ts_col="collected_at")
    
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
                st.warning(
                    "This will immediately call FAA and Live Airspace Traffic APIs. "
                    "Manual sync also forces an AirLabs call (bypasses the normal 2-hour/window throttle), so use sparingly."
                )
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
                st.warning(
                    "This will immediately call FAA and Live Airspace Traffic APIs. "
                    "Manual sync also forces an AirLabs call (bypasses the normal 2-hour/window throttle), so use sparingly."
                )
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
    
    st.markdown("#### Date Range")
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
        "Select Date Range",
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
        st.warning("No rows found for this date range.")
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

    # Convenience time features (airport-local clock)
    filtered = add_airport_local_clock_fields(filtered, ts_col="collected_at")
    filtered["faa_downtime_minutes"] = 0.0
    if not faa_events_df.empty:
        faa_events_view = faa_events_df[faa_events_df["airport_code"].isin(selected_airports)].copy()
        faa_events_view = faa_events_view[faa_events_view["collected_at"].between(start_dt, end_dt)]
        if not faa_events_view.empty:
            faa_events_view["faa_delay_for_max"] = faa_events_view["max_delay_minutes"]
            faa_events_view.loc[
                faa_events_view["faa_delay_for_max"].isna(), "faa_delay_for_max"
            ] = faa_events_view["min_delay_minutes"]
            snapshot_downtime = (
                faa_events_view.groupby(["airport_code", "collected_at"], as_index=False)
                .agg(faa_downtime_minutes=("faa_delay_for_max", "max"))
            )
            filtered = filtered.merge(
                snapshot_downtime,
                on=["airport_code", "collected_at"],
                how="left",
                suffixes=("", "_evt"),
            )
            if "faa_downtime_minutes_evt" in filtered.columns:
                filtered["faa_downtime_minutes"] = to_numeric_series(
                    filtered["faa_downtime_minutes_evt"], index=filtered.index
                ).fillna(0.0)
                filtered = filtered.drop(columns=["faa_downtime_minutes_evt"])
    
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
            st.metric("Airport Traffic Load Difference", traffic_gap_text)
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
        st.caption(
            "This section aligns MCO and DEN by shared airport-local clock slots "
            "(e.g., DEN 9 AM vs MCO 9 AM) before computing ratios."
        )

        hypothesis_df = filtered.copy()
        hypothesis_df = align_to_shared_local_slots(hypothesis_df, selected_airports)
        if hypothesis_df.empty:
            st.info("Not enough overlapping airport-local time slots in this range to compare MCO vs DEN.")
        MIN_SHARED_SLOTS = 6
        MIN_AIRLINE_FLIGHTS_PER_AIRPORT = 40
        MIN_FAA_DOWNTIME_SLOTS_PER_AIRPORT = 3
        LOAD_FLOOR_FOR_NORMALIZATION = 25.0

        hypothesis_df["delay_index_best"] = pd.to_numeric(hypothesis_df["delay_index_best"], errors="coerce")
        hypothesis_df["traffic_load_effective"] = pd.to_numeric(hypothesis_df["traffic_load_effective"], errors="coerce")
        hypothesis_df["faa_event_count"] = to_numeric_series(
            hypothesis_df["faa_event_count"], index=hypothesis_df.index
        ).fillna(0)
        hypothesis_df["has_faa_restriction"] = hypothesis_df["faa_event_count"] > 0
        hypothesis_df["load_for_norm"] = to_numeric_series(
            hypothesis_df["traffic_load_effective"], index=hypothesis_df.index
        ).clip(lower=LOAD_FLOOR_FOR_NORMALIZATION)
        hypothesis_df["downtime_per_100_load_row"] = (
            to_numeric_series(hypothesis_df["faa_downtime_minutes"], index=hypothesis_df.index).fillna(0.0) /
            (hypothesis_df["load_for_norm"] / 100.0)
        )

        hypothesis_summary = (
            hypothesis_df.groupby("airport_code", as_index=False)
            .agg(
                snapshots=("airport_code", "size"),
                average_delay_index=("delay_index_best", "mean"),
                average_traffic_load=("traffic_load_effective", "mean"),
                faa_restriction_rate=("has_faa_restriction", "mean"),
                average_faa_downtime_minutes=("faa_downtime_minutes", "mean"),
                faa_downtime_slots=("faa_downtime_minutes", lambda s: int((to_numeric_series(s, index=s.index).fillna(0) > 0).sum())),
                downtime_per_100_load=("downtime_per_100_load_row", "mean"),
            )
        )
        hypothesis_summary["average_delay_index"] = to_numeric_series(
            hypothesis_summary["average_delay_index"], index=hypothesis_summary.index
        )
        hypothesis_summary["average_traffic_load"] = to_numeric_series(
            hypothesis_summary["average_traffic_load"], index=hypothesis_summary.index
        )
        hypothesis_summary["faa_restriction_rate_percent"] = hypothesis_summary["faa_restriction_rate"] * 100.0

        airline_hypothesis = pd.DataFrame()
        airline_slot_pairs = pd.DataFrame()
        if not flight_df.empty:
            airline_hypothesis = flight_df[flight_df["airport_code"].isin(selected_airports)].copy()
            airline_hypothesis = airline_hypothesis[
                airline_hypothesis["collected_at_local"].between(start_dt, end_dt)
            ]
            airline_hypothesis = align_to_shared_local_slots(airline_hypothesis, selected_airports)
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

                airline_by_slot = (
                    airline_hypothesis.groupby(["airport_local_slot", "airport_code"], as_index=False)
                    .agg(
                        avg_delay_min=("delay_positive", "mean"),
                        cancel_rate=("cancelled", "mean"),
                        divert_rate=("diverted", "mean"),
                    )
                )
                airline_by_slot["airline_severity"] = (
                    (to_numeric_series(airline_by_slot["avg_delay_min"], index=airline_by_slot.index).fillna(0) / 20.0).clip(upper=3.0)
                    + (to_numeric_series(airline_by_slot["cancel_rate"], index=airline_by_slot.index).fillna(0) * 4.0).clip(upper=1.5)
                    + (to_numeric_series(airline_by_slot["divert_rate"], index=airline_by_slot.index).fillna(0) * 2.0).clip(upper=0.5)
                ).clip(upper=5.0)
                airline_slot_pairs = airline_by_slot.pivot(
                    index="airport_local_slot", columns="airport_code", values="airline_severity"
                ).rename(columns={"MCO": "mco_airline", "DEN": "den_airline"}).dropna(
                    subset=["mco_airline", "den_airline"], how="any"
                )
                if isinstance(airline_slot_pairs, pd.DataFrame):
                    airline_slot_pairs = airline_slot_pairs.reset_index()

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

        operational_slot_pairs = (
            hypothesis_df.groupby(["airport_local_slot", "airport_code"], as_index=False)
            .agg(downtime_per_100_load=("downtime_per_100_load_row", "mean"))
            .pivot(index="airport_local_slot", columns="airport_code", values="downtime_per_100_load")
            .rename(columns={"MCO": "mco_operational", "DEN": "den_operational"})
            .dropna(subset=["mco_operational", "den_operational"], how="any")
        )
        if isinstance(operational_slot_pairs, pd.DataFrame):
            operational_slot_pairs = operational_slot_pairs.reset_index()

        shared_slot_count = int(hypothesis_df["airport_local_slot"].nunique())
        faa_downtime_slots_mco = int(hypothesis_df[(hypothesis_df["airport_code"] == "MCO") & (hypothesis_df["faa_downtime_minutes"] > 0)]["airport_local_slot"].nunique())
        faa_downtime_slots_den = int(hypothesis_df[(hypothesis_df["airport_code"] == "DEN") & (hypothesis_df["faa_downtime_minutes"] > 0)]["airport_local_slot"].nunique())
        mco_flights = int(safe_float((hypothesis_rows_by_airport.get("MCO") or {}).get("airline_flights")) or 0)
        den_flights = int(safe_float((hypothesis_rows_by_airport.get("DEN") or {}).get("airline_flights")) or 0)

        operational_ci = bootstrap_ratio_ci(
            operational_slot_pairs if isinstance(operational_slot_pairs, pd.DataFrame) else pd.DataFrame(),
            "mco_operational",
            "den_operational",
        )
        airline_ci = bootstrap_ratio_ci(
            airline_slot_pairs if isinstance(airline_slot_pairs, pd.DataFrame) else pd.DataFrame(),
            "mco_airline",
            "den_airline",
        )

        operational_gate_ok = (
            shared_slot_count >= MIN_SHARED_SLOTS
            and faa_downtime_slots_mco >= MIN_FAA_DOWNTIME_SLOTS_PER_AIRPORT
            and faa_downtime_slots_den >= MIN_FAA_DOWNTIME_SLOTS_PER_AIRPORT
        )
        airline_gate_ok = (
            shared_slot_count >= MIN_SHARED_SLOTS
            and mco_flights >= MIN_AIRLINE_FLIGHTS_PER_AIRPORT
            and den_flights >= MIN_AIRLINE_FLIGHTS_PER_AIRPORT
        )

        st.caption(
            f"Evidence quality gates: shared slots={shared_slot_count} (min {MIN_SHARED_SLOTS}), "
            f"MCO/DEN airline flights={mco_flights}/{den_flights} (min {MIN_AIRLINE_FLIGHTS_PER_AIRPORT} each), "
            f"MCO/DEN FAA downtime slots={faa_downtime_slots_mco}/{faa_downtime_slots_den} "
            f"(min {MIN_FAA_DOWNTIME_SLOTS_PER_AIRPORT} each)."
        )

        denver_load_outperformance_note: str | None = None
        denver_daily_outperformance_note: str | None = None
        den_row = hypothesis_rows_by_airport.get("DEN")
        mco_row = hypothesis_rows_by_airport.get("MCO")
        if den_row is not None and mco_row is not None:
            den_load = safe_float(den_row.get("average_traffic_load"))
            mco_load = safe_float(mco_row.get("average_traffic_load"))
            den_delay_per_load = safe_float(den_row.get("downtime_per_100_load"))
            mco_delay_per_load = safe_float(mco_row.get("downtime_per_100_load"))

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
                    f"while maintaining better FAA downtime efficiency "
                    f"({den_delay_per_load:.2f} vs {mco_delay_per_load:.2f} downtime minutes per 100 load)."
                )

        # Daily-level outperformance signal: on days where DEN is busier than MCO,
        # count how often DEN still has lower delay-per-100-load.
        daily_ops = (
            hypothesis_df.groupby(["airport_local_date", "airport_code"], as_index=False)
            .agg(
                avg_load=("traffic_load_effective", "mean"),
                avg_faa_downtime_minutes=("faa_downtime_minutes", "mean"),
            )
        )
        if not daily_ops.empty:
            daily_ops["avg_load"] = to_numeric_series(daily_ops["avg_load"], index=daily_ops.index)
            daily_ops["avg_faa_downtime_minutes"] = to_numeric_series(
                daily_ops["avg_faa_downtime_minutes"], index=daily_ops.index
            )
            daily_ops["downtime_per_100_load"] = daily_ops["avg_faa_downtime_minutes"] / (daily_ops["avg_load"] / 100.0)

            daily_pivot = daily_ops.pivot(
                index="airport_local_date",
                columns="airport_code",
                values=["avg_load", "downtime_per_100_load"],
            )
            if isinstance(daily_pivot, pd.DataFrame) and {"DEN", "MCO"}.issubset(set(daily_pivot.columns.get_level_values(1))):
                den_load_daily = daily_pivot[("avg_load", "DEN")]
                mco_load_daily = daily_pivot[("avg_load", "MCO")]
                den_dpl_daily = daily_pivot[("downtime_per_100_load", "DEN")]
                mco_dpl_daily = daily_pivot[("downtime_per_100_load", "MCO")]
                valid_days = den_load_daily.notna() & mco_load_daily.notna() & den_dpl_daily.notna() & mco_dpl_daily.notna() & (mco_load_daily > 0)
                den_busier = den_load_daily >= (mco_load_daily * 1.05)
                den_better_eff = den_dpl_daily < mco_dpl_daily
                busier_days = int((valid_days & den_busier).sum())
                better_when_busier_days = int((valid_days & den_busier & den_better_eff).sum())
                if busier_days > 0:
                    denver_daily_outperformance_note = (
                        f"Daily view: DEN was busier than MCO on {busier_days} day(s) in this range and "
                        f"still had better downtime-per-100-load on {better_when_busier_days} of those day(s)."
                    )

        def metric_ratio(metric_key: str) -> float | None:
            den_val = safe_float((hypothesis_rows_by_airport.get("DEN") or {}).get(metric_key))
            mco_val = safe_float((hypothesis_rows_by_airport.get("MCO") or {}).get(metric_key))
            if den_val in (None, 0.0) or mco_val is None:
                return None
            return float(mco_val / den_val)

        operational_core_ratio = metric_ratio("downtime_per_100_load")
        airline_core_ratio = metric_ratio("average_airline_severity")
        operational_conf = confidence_tag(
            sample_size=len(operational_slot_pairs) if isinstance(operational_slot_pairs, pd.DataFrame) else 0,
            min_needed=MIN_SHARED_SLOTS,
            ci=operational_ci,
        )
        airline_conf = confidence_tag(
            sample_size=len(airline_slot_pairs) if isinstance(airline_slot_pairs, pd.DataFrame) else 0,
            min_needed=MIN_SHARED_SLOTS,
            ci=airline_ci,
        )

        operational_ready = operational_gate_ok and operational_core_ratio is not None
        airline_ready = airline_gate_ok and airline_core_ratio is not None

        st.markdown("### Decision Summary")
        d1, d2, d3 = st.columns(3)
        with d1:
            op_text = "Withheld"
            if operational_core_ratio is not None:
                op_text = f"{operational_core_ratio:.2f}"
            st.metric("Operational Core (MCO/DEN)", op_text)
            st.caption("FAA downtime minutes per 100 traffic load")
            st.caption(f"Confidence: **{operational_conf}**")
        with d2:
            air_text = "Withheld"
            if airline_core_ratio is not None:
                air_text = f"{airline_core_ratio:.2f}"
            st.metric("Passenger Core (MCO/DEN)", air_text)
            st.caption("Airline delay severity")
            st.caption(f"Confidence: **{airline_conf}**")
        with d3:
            if operational_ready and airline_ready:
                op_weight = float(len(operational_slot_pairs)) if isinstance(operational_slot_pairs, pd.DataFrame) else 1.0
                air_weight = float(len(airline_slot_pairs)) if isinstance(airline_slot_pairs, pd.DataFrame) else 1.0
                combined_ratio = float(
                    ((float(operational_core_ratio) * op_weight) + (float(airline_core_ratio) * air_weight))
                    / (op_weight + air_weight)
                )
                verdict = "Supports hypothesis" if combined_ratio > 1.0 else "Does not support hypothesis"
                st.metric("Top-Line Verdict", verdict)
                st.caption(f"Weighted core ratio: **{combined_ratio:.2f}**")
                if operational_conf == "High" and airline_conf == "High":
                    combined_conf = "High"
                elif operational_conf in {"Medium", "High"} and airline_conf in {"Medium", "High"}:
                    combined_conf = "Medium"
                else:
                    combined_conf = "Low"
                st.caption(f"Confidence: **{combined_conf}**")
            elif operational_ready:
                verdict = "Supports hypothesis" if float(operational_core_ratio) > 1.0 else "Does not support hypothesis"
                st.metric("Top-Line Verdict", "Operational-only")
                st.caption(f"{verdict} from operational core only")
            elif airline_ready:
                verdict = "Supports hypothesis" if float(airline_core_ratio) > 1.0 else "Does not support hypothesis"
                st.metric("Top-Line Verdict", "Passenger-only")
                st.caption(f"{verdict} from passenger core only")
            else:
                st.metric("Top-Line Verdict", "Withheld")
                st.caption("Not enough evidence to issue a reliable verdict")

        if denver_load_outperformance_note is not None:
            st.info(denver_load_outperformance_note)
        if denver_daily_outperformance_note is not None:
            st.info(denver_daily_outperformance_note)

        with st.expander("Supporting Context (Secondary Metrics)", expanded=False):
            st.caption("Use this section for drill-down after reading the Decision Summary.")
            support_cols = [
                "airport_code",
                "snapshots",
                "average_traffic_load",
                "average_faa_downtime_minutes",
                "downtime_per_100_load",
                "airline_flights",
                "average_airline_delay_min",
                "cancel_rate_percent",
                "average_airline_severity",
            ]
            present_cols = [c for c in support_cols if c in hypothesis_summary.columns]
            st.dataframe(prettify_columns(hypothesis_summary[present_cols]), width="stretch")

            ratio_rows = []
            if operational_core_ratio is not None:
                ratio_rows.append(
                    {"metric": "Operational Core: FAA Downtime Per 100 Load", "mco_vs_den_ratio": operational_core_ratio}
                )
            if airline_core_ratio is not None:
                ratio_rows.append(
                    {"metric": "Passenger Core: Airline Delay Severity", "mco_vs_den_ratio": airline_core_ratio}
                )
            if len(ratio_rows) > 0:
                core_ratio_df = pd.DataFrame(ratio_rows)
                core_ratio_df["supports_mco_worse"] = core_ratio_df["mco_vs_den_ratio"] > 1.0
                core_ratio_chart = px.bar(
                    core_ratio_df,
                    x="metric",
                    y="mco_vs_den_ratio",
                    color="supports_mco_worse",
                    labels={
                        "metric": "Core Metric",
                        "mco_vs_den_ratio": "MCO / DEN Ratio",
                        "supports_mco_worse": "Supports MCO Worse",
                    },
                    color_discrete_map={True: AIRPORT_COLOR_MAP["MCO"], False: AIRPORT_COLOR_MAP["DEN"]},
                )
                core_ratio_chart.add_hline(y=1.0, line_dash="dash", line_color="gray")
                st.plotly_chart(core_ratio_chart, width="stretch")

            if operational_ci is not None:
                st.caption(
                    f"Operational core 95% CI: [{operational_ci[0]:.2f}, {operational_ci[1]:.2f}]"
                )
            if airline_ci is not None:
                st.caption(
                    f"Passenger core 95% CI: [{airline_ci[0]:.2f}, {airline_ci[1]:.2f}]"
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
            faa_summary = (
                faa_status_history.assign(
                    has_delay=faa_status_history["faa_event_count"] > 0,
                    local_date=series_date(
                        faa_status_history["collected_at_local"] - pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                    ),
                )
                .groupby("airport_code", as_index=False)
                .agg(
                    snapshots=("airport_code", "size"),
                    delayed_snapshots=("has_delay", "sum"),
                    days_observed=("local_date", "nunique"),
                    max_active_restrictions=("faa_event_count", "max"),
                )
            )
            faa_summary["restriction_rate_percent"] = (
                to_numeric_series(faa_summary["delayed_snapshots"], index=faa_summary.index)
                / to_numeric_series(faa_summary["snapshots"], index=faa_summary.index)
                * 100.0
            ).fillna(0.0)
            faa_summary["avg_restricted_snapshots_per_day"] = (
                to_numeric_series(faa_summary["delayed_snapshots"], index=faa_summary.index)
                / to_numeric_series(faa_summary["days_observed"], index=faa_summary.index).replace(0, pd.NA)
            ).fillna(0.0)
            active_status = faa_status_history[
                ~faa_status_history["faa_status_clean"].isin(
                    ["No active FAA NAS restriction listed.", "Unknown / Missing"]
                )
            ].copy()
            common_restriction_by_airport: dict[str, str] = {}
            if not active_status.empty:
                common_status = (
                    active_status.groupby(["airport_code", "faa_status_clean"], as_index=False)
                    .agg(status_count=("faa_status_clean", "size"))
                )
                common_status = sort_values_df(
                    common_status,
                    by=["airport_code", "status_count", "faa_status_clean"],
                    ascending=[True, False, True],
                )
                top_common = common_status.groupby("airport_code", as_index=False).head(1)
                common_restriction_by_airport = {
                    str(r["airport_code"]): str(r["faa_status_clean"]) for r in records(top_common)
                }

            st.markdown("#### FAA Restriction Summary")
            summary_cols = st.columns(2)
            summary_by_airport = {str(r["airport_code"]): r for r in records(faa_summary)}
            for idx, airport in enumerate(selected_airports):
                rec = summary_by_airport.get(airport)
                with summary_cols[idx]:
                    st.markdown(f"**{airport}**")
                    if rec is None:
                        st.info("No FAA snapshots in selected range.")
                    else:
                        st.metric("Restriction Snapshot Rate", f"{float(rec['restriction_rate_percent']):.1f}%")
                        st.metric(
                            "Most Common Restriction",
                            common_restriction_by_airport.get(airport, "None"),
                        )
                        st.metric("Peak Active Restrictions", int(float(rec["max_active_restrictions"])))

            chart_col1, chart_col2 = st.columns(2)

            delayed_daily = (
                faa_status_history.assign(
                    local_date=series_date(
                        faa_status_history["collected_at_local"] - pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                    ),
                    has_delay=faa_status_history["faa_event_count"] > 0,
                )
                .groupby(["local_date", "airport_code"], as_index=False)
                .agg(
                    delayed_snapshots=("has_delay", "sum"),
                    total_snapshots=("has_delay", "size"),
                )
            )
            delayed_daily["local_date"] = pd.to_datetime(delayed_daily["local_date"])
            delayed_daily["operational_day_start_local"] = (
                delayed_daily["local_date"] + pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
            )
            delayed_daily["restriction_rate_percent"] = (
                to_numeric_series(delayed_daily["delayed_snapshots"], index=delayed_daily.index)
                / to_numeric_series(delayed_daily["total_snapshots"], index=delayed_daily.index)
                * 100.0
            ).fillna(0.0)

            with chart_col1:
                restriction_rate_chart = px.line(
                    delayed_daily,
                    x="operational_day_start_local",
                    y="restriction_rate_percent",
                    color="airport_code",
                    markers=True,
                    custom_data=["delayed_snapshots", "total_snapshots"],
                    title="Daily FAA Restriction Rate",
                    labels={
                        "operational_day_start_local": "Operational Day Start (Local)",
                        "restriction_rate_percent": "Snapshots With Restriction (%)",
                        "airport_code": "Airport",
                    },
                    color_discrete_map=AIRPORT_COLOR_MAP,
                )
                restriction_rate_chart.update_traces(
                    hovertemplate=(
                        "Date: %{x|%B %d}<br>"
                        "Airport: %{fullData.name}<br>"
                        "Restriction Rate: %{y:.1f}%<br>"
                        "Restricted Snapshots: %{customdata[0]:.0f}<br>"
                        "Total Snapshots: %{customdata[1]:.0f}<extra></extra>"
                    )
                )
                format_date_axis(restriction_rate_chart)
                st.plotly_chart(restriction_rate_chart, width="stretch")

            with chart_col2:
                daily_peak = (
                    faa_status_history.assign(
                        local_date=series_date(
                            faa_status_history["collected_at_local"] - pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                        )
                    )
                    .groupby(["local_date", "airport_code"], as_index=False)
                    .agg(peak_active_restrictions=("faa_event_count", "max"))
                )
                daily_peak["local_date"] = pd.to_datetime(daily_peak["local_date"])
                daily_peak["operational_day_start_local"] = (
                    daily_peak["local_date"] + pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                )
                peak_chart = px.bar(
                    daily_peak,
                    x="operational_day_start_local",
                    y="peak_active_restrictions",
                    color="airport_code",
                    barmode="group",
                    title="Daily Peak Active FAA Restrictions",
                    labels={
                        "operational_day_start_local": "Operational Day Start (Local)",
                        "peak_active_restrictions": "Peak Active Restrictions",
                        "airport_code": "Airport",
                    },
                    color_discrete_map=AIRPORT_COLOR_MAP,
                )
                format_date_axis(peak_chart)
                st.plotly_chart(peak_chart, width="stretch")

            with st.expander("Show FAA status category breakdown"):
                status_counts = sort_values_df(
                    faa_status_history.groupby(["airport_code", "faa_status_clean"], as_index=False)
                    .agg(snapshot_count=("faa_status_clean", "size")),
                    by=["snapshot_count", "airport_code"],
                    ascending=[False, True],
                )
                status_counts_chart = px.bar(
                    status_counts,
                    x="faa_status_clean",
                    y="snapshot_count",
                    color="airport_code",
                    barmode="group",
                    labels={
                        "faa_status_clean": "FAA Status",
                        "snapshot_count": "Snapshots",
                        "airport_code": "Airport",
                    },
                    color_discrete_map=AIRPORT_COLOR_MAP,
                )
                status_counts_chart.update_xaxes(categoryorder="total descending")
                st.plotly_chart(status_counts_chart, width="stretch")


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
                airline_daily = (
                    airline_snap.assign(
                        local_date=series_date(
                            airline_snap["collected_at_local"] - pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                        )
                    )
                    .groupby(["local_date", "airport_code"], as_index=False)
                    .agg(
                        snapshots=("airline_delay_severity_index", "size"),
                        avg_severity=("airline_delay_severity_index", "mean"),
                        p90_longest_delay_min=(
                            "max_delay_min",
                            lambda s: to_numeric_series(s, index=s.index).quantile(0.9),
                        ),
                    )
                )
                airline_daily["local_date"] = pd.to_datetime(airline_daily["local_date"])
                airline_daily["operational_day_start_local"] = (
                    airline_daily["local_date"] + pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                )
                airline_daily["p90_longest_delay_hours"] = (
                    to_numeric_series(
                        airline_daily["p90_longest_delay_min"], index=airline_daily.index
                    ).fillna(0.0)
                    / 60.0
                )
                airline_daily["p90_longest_delay_hr_min"] = (
                    to_numeric_series(
                        airline_daily["p90_longest_delay_min"], index=airline_daily.index
                    ).fillna(0.0).apply(format_minutes_hr_min)
                )

                a1, a2 = st.columns(2)
                with a1:
                    airline_severity_chart = px.line(
                        airline_daily,
                        x="operational_day_start_local",
                        y="avg_severity",
                        color="airport_code",
                        markers=True,
                        custom_data=["snapshots"],
                        title="Daily Airline Delay Severity Index",
                        labels={
                            "operational_day_start_local": "Operational Day Start (Local)",
                            "avg_severity": "Average Severity Index",
                            "airport_code": "Airport",
                        },
                        color_discrete_map=AIRPORT_COLOR_MAP,
                    )
                    airline_severity_chart.update_traces(
                        line=dict(width=2.5),
                        marker=dict(size=7),
                        hovertemplate=(
                            "Date: %{x|%B %d}<br>"
                            "Airport: %{fullData.name}<br>"
                            "Daily Avg Severity: %{y:.2f}<br>"
                            "Snapshots: %{customdata[0]:.0f}<extra></extra>"
                        ),
                    )
                    format_date_axis(airline_severity_chart)
                    st.plotly_chart(airline_severity_chart, width="stretch")

                with a2:
                    longest_delay_chart = px.line(
                        airline_daily,
                        x="operational_day_start_local",
                        y="p90_longest_delay_hours",
                        color="airport_code",
                        markers=True,
                        custom_data=["p90_longest_delay_hr_min", "snapshots"],
                        title="Daily Longest Airline Delay",
                        labels={
                            "operational_day_start_local": "Operational Day Start (Local)",
                            "p90_longest_delay_hours": "Longest Delay (Hours)",
                            "airport_code": "Airport",
                        },
                        color_discrete_map=AIRPORT_COLOR_MAP,
                    )
                    longest_delay_chart.update_traces(
                        line=dict(width=2.5),
                        marker=dict(size=7),
                        hovertemplate=(
                            "Date: %{x|%B %d}<br>"
                            "Airport: %{fullData.name}<br>"
                            "Longest Delay: %{customdata[0]}<br>"
                            "Snapshots: %{customdata[1]:.0f}<extra></extra>"
                        ),
                    )
                    format_date_axis(longest_delay_chart)
                    st.plotly_chart(longest_delay_chart, width="stretch")

                daily_cancel = (
                    flight_view.assign(
                        local_date=series_date(
                            flight_view["collected_at_local"] - pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                        )
                    )
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
                daily_cancel["operational_day_start_local"] = (
                    daily_cancel["local_date"] + pd.Timedelta(hours=OPERATIONAL_DAY_START_HOUR)
                )

                cancel_rate_chart = px.line(
                    daily_cancel,
                    x="operational_day_start_local",
                    y="cancel_rate_percent",
                    color="airport_code",
                    markers=True,
                    custom_data=["cancelled_count", "flights"],
                    title="Daily Airline Cancellation Rate Comparison",
                    labels={
                        "operational_day_start_local": "Operational Day Start (Local)",
                        "cancel_rate_percent": "Cancellation Rate (%)",
                        "airport_code": "Airport",
                    },
                    color_discrete_map=AIRPORT_COLOR_MAP,
                )
                cancel_rate_chart.update_traces(
                    line=dict(width=2.5),
                    marker=dict(size=7),
                    hovertemplate=(
                        "Date: %{x|%B %d}<br>"
                        "Airport: %{fullData.name}<br>"
                        "Cancellation Rate: %{y:.1f}%<br>"
                        "Cancelled Flights: %{customdata[0]:.0f}<br>"
                        "Flights Sampled: %{customdata[1]:.0f}<extra></extra>"
                    )
                )
                cancel_rate_chart.update_yaxes(rangemode="tozero")
                format_date_axis(cancel_rate_chart)
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
        # -----------------------
        # Delay timing breakdown
        # -----------------------
        st.subheader("Delay Timing Breakdown")
        st.caption(
            "Passenger view: FAA and airline delays are combined into one delay signal "
            "to show overall average delay by weekday and hour."
        )

        dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        combined_parts: list[pd.DataFrame] = []

        if not faa_events_df.empty:
            faa_timing = faa_events_df[faa_events_df["airport_code"].isin(selected_airports)].copy()
            faa_timing = faa_timing[faa_timing["collected_at"].between(start_dt, end_dt)]
            if not faa_timing.empty:
                faa_timing = add_airport_local_clock_fields(faa_timing, ts_col="collected_at")
                faa_timing["delay_minutes_overall"] = faa_timing["max_delay_minutes"]
                faa_timing.loc[
                    faa_timing["delay_minutes_overall"].isna(), "delay_minutes_overall"
                ] = faa_timing["min_delay_minutes"]
                faa_timing["delay_minutes_overall"] = to_numeric_series(
                    faa_timing["delay_minutes_overall"], index=faa_timing.index
                ).clip(lower=0)
                faa_timing = faa_timing.dropna(subset=["delay_minutes_overall"])
                combined_parts.append(
                    faa_timing[
                        [
                            "airport_code",
                            "airport_local_dow",
                            "airport_local_hour",
                            "airport_local_half_hour",
                            "delay_minutes_overall",
                        ]
                    ].copy()
                )

        if not flight_df.empty:
            airline_timing = flight_df[flight_df["airport_code"].isin(selected_airports)].copy()
            airline_timing = airline_timing[airline_timing["collected_at_local"].between(start_dt, end_dt)]
            if not airline_timing.empty:
                airline_timing = add_airport_local_clock_fields(airline_timing, ts_col="collected_at")
                airline_timing["delay_minutes_overall"] = to_numeric_series(
                    airline_timing["delay_minutes"], index=airline_timing.index
                ).clip(lower=0)
                airline_timing = airline_timing.dropna(subset=["delay_minutes_overall"])
                combined_parts.append(
                    airline_timing[
                        [
                            "airport_code",
                            "airport_local_dow",
                            "airport_local_hour",
                            "airport_local_half_hour",
                            "delay_minutes_overall",
                        ]
                    ].copy()
                )

        if len(combined_parts) == 0:
            st.info("Not enough FAA or airline delay data in this range to show combined timing.")
        else:
            combined_timing = pd.concat(combined_parts, ignore_index=True)
            combined_timing["airport_local_dow"] = pd.Categorical(
                combined_timing["airport_local_dow"], categories=dow_order, ordered=True
            )

            by_dow_raw = combined_timing.groupby(
                ["airport_local_dow", "airport_code"], as_index=False, observed=True
            ).agg(
                average_delay_min=("delay_minutes_overall", "mean"),
                samples=("delay_minutes_overall", "size"),
            )
            dow_codes = pd.Categorical(by_dow_raw["airport_local_dow"], categories=dow_order, ordered=True)
            dow_order_idx = pd.Series(dow_codes.codes, index=by_dow_raw.index).argsort(kind="mergesort")
            by_dow = by_dow_raw.iloc[dow_order_idx.to_numpy()].copy()

            dow_chart = px.bar(
                by_dow,
                x="airport_local_dow",
                y="average_delay_min",
                color="airport_code",
                barmode="group",
                custom_data=["samples"],
                title="Average Overall Delay by Day of Week (FAA + Airline)",
                labels={
                    "airport_local_dow": "Day of Week (Airport Local)",
                    "average_delay_min": "Average Delay (Minutes)",
                    "airport_code": "Airport",
                },
                color_discrete_map=AIRPORT_COLOR_MAP,
            )
            dow_chart.update_traces(
                marker_line_width=1,
                marker_line_color="rgba(255,255,255,0.35)",
                hovertemplate=(
                    "Airport: %{fullData.name}<br>"
                    "Day: %{x}<br>"
                    "Average Delay: %{y:.1f} min<br>"
                    "Samples: %{customdata[0]:.0f}<extra></extra>"
                ),
            )
            st.plotly_chart(dow_chart, width="stretch")
