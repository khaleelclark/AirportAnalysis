from pathlib import Path
import sqlite3
from datetime import datetime
import subprocess

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
        Are the delays experienced at MCO (Orlando International Airport) proportionate to it's operational load, or does the airport exhibit disproportionate delay patterns when compared to another airport that has more negative delay factors contributing to it, like DEN (Denver International Airport)?
        
        ### Project Hypothesis
        Based on repeated personal travel experience, MCO appears to deliver a worse operational experience than DEN.
        This project tests that claim objectively by comparing live delay severity, airline delay impact, traffic load,
        and longest-delay events across both airports over time.

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
        - **Operational Stress Score:** combined measure of traffic pressure and delay severity.

        ### Scope Notes
        - This dashboard is intentionally scoped to **MCO** and **DEN** for the capstone.
        - FAA severity and airline delay severity are related but distinct signals; both are shown for transparency.
        """
    )

with calc_tab:
    st.markdown(
        """
        ### Calculation Details
        This page documents how dashboard metrics are computed from live data.

        ### 1) FAA Delay Severity Index (Operational)
        Derived from FAA NASStatus event types:
        - `0`: No active FAA restriction
        - `2`: Arrival/Departure delay program
        - `3`: Ground Delay Program
        - `4`: Ground Stop
        - `5`: Airport closure
        If multiple FAA events exist at once, the index uses the **maximum** severity.

        ### 2) Airline Delay Severity Index (AirLabs, 0-5)
        Computed per airport from the latest AirLabs delay snapshot:
        - `avg_delay_min = mean(max(delay_minutes, 0))`
        - `cancel_rate = cancelled_flights / total_flights`
        - `divert_rate = diverted_flights / total_flights`

        Score components:
        - Delay component: `min(avg_delay_min / 20, 3.0)`
        - Cancellation component: `min(cancel_rate * 4.0, 1.5)`
        - Diversion component: `min(divert_rate * 2.0, 0.5)`

        Final score:
        - `airline_severity = min(delay_component + cancellation_component + diversion_component, 5.0)`

        ### 3) Traffic Load
        Primary load signal is live aircraft count from traffic snapshots:
        - `traffic_load_effective = aircraft_count`
        Fallback when needed:
        - `traffic_load_effective = dep_total + arr_total`

        ### 4) Operational Stress Score
        Baseline traffic pressure + FAA severity:
        - `operational_stress_score = (1 + faa_delay_severity_index) * (traffic_load_effective / 100)`

        ### 5) Load-Adjusted Stress Score
        Normalizes operational stress by relative load at each timestamp:
        - `peer_avg_load = mean(traffic_load_effective across airports at same timestamp)`
        - `relative_load_factor = traffic_load_effective / peer_avg_load`
        - `load_adjusted_stress_score = operational_stress_score / relative_load_factor`

        Interpretation:
        - If an airport stays worse after this adjustment, that suggests disproportionate operational pain beyond just being busier.

        ### 6) Longest Delay Metrics
        - **Longest Airline Delay Today**: max flight `delay_minutes` today (local date).
        - **Longest Delay Today (Any Source)**: max of:
          airline longest delay,
          FAA event delay range (max delay, fallback to min delay).
        """
    )

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
            - **Load-Adjusted Stress Score**: Operational stress normalized by relative load at that moment.
              Use this for the fairest MCO vs DEN comparison when traffic differs.
            - **Longest Delay Today Metrics**:
              `Longest Airline Delay Today` comes from AirLabs flight delays.
              `Longest Delay Today (Any Source)` takes the larger value between airline delays and FAA event delay ranges.
            - **How To Interpret Quickly**:
              If MCO has a higher **Load-Adjusted Stress Score** over multiple snapshots/days, that supports the hypothesis that MCO is disproportionately worse.
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
    
    def get_last_updated() -> dict:
        q = """
            SELECT
                    (SELECT MAX(collected_at) FROM delay_snapshots)  AS last_faa,
                    (SELECT MAX(collected_at) FROM traffic_snapshots) AS last_traffic,
                    (SELECT MAX(collected_at) FROM flight_snapshots) AS last_airline_delay
            """
        row = load_df(q).iloc[0].to_dict()
        # Convert to timestamps (UTC)
        out = {}
        for k, v in row.items():
            out[k] = pd.to_datetime(v, utc=True) if v else None
        return out
    
    def safe_float(x):
        try:
            return float(x)
        except Exception:
            return None
    
    
    LOCAL_TZ = datetime.now().astimezone().tzinfo
    
    
    def format_local_snapshot_time(ts: pd.Timestamp | None) -> str:
        if ts is None or pd.isna(ts):
            return "—"
        return ts.tz_convert(LOCAL_TZ).strftime("%I:%M %p %b %d")
    
    
    def format_faa_update_time_local(value) -> str:
        if value is None or pd.isna(value):
            return "—"
        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return "—"
        return format_local_snapshot_time(ts)
    
    
    def format_minutes_hr_min(value) -> str:
        if value is None or pd.isna(value):
            return "N/A"
        total_min = max(int(round(float(value))), 0)
        hours = total_min // 60
        minutes = total_min % 60
        return f"{hours} hr {minutes} min"
    
    
    def prettify_columns(df: pd.DataFrame) -> pd.DataFrame:
        return df.rename(columns=lambda c: str(c).replace("_", " ").title())
    
    
    def format_time_axis_12h(fig):
        fig.update_xaxes(tickformat="%I:%M %p<br>%b %d", hoverformat="%I:%M %p %b %d")
        return fig
    
    
    def run_manual_sync_collectors() -> list[dict]:
        commands = [
            ("FAA Delays", [str(PROJECT_ROOT / ".venv" / "bin" / "python"), "src/collect_delays.py"]),
            ("Live Airspace Traffic", [str(PROJECT_ROOT / ".venv" / "bin" / "python"), "src/collect_traffic.py"]),
            ("Airline Delay", [str(PROJECT_ROOT / ".venv" / "bin" / "python"), "src/collect_flights.py"]),
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
    delay_df = load_df("""
                       SELECT
                           id,
                           airport_code,
                           collected_at,
                           window_from_utc,
                           window_to_utc,
                           CASE
                               WHEN raw_json LIKE '%FAA_NASSTATUS%' THEN 'FAA_NASSTATUS'
                               ELSE 'AERODATABOX'
                           END AS source,
    
                           delay_index,
                           delay_median_minutes,
    
                           dep_total,
                           arr_total,
                           dep_delay_index,
                           dep_median_delay_minutes,
    
                           arr_delay_index,
                           arr_median_delay_minutes,
                           faa_update_time,
                           faa_event_count,
                           json_extract(raw_json, '$.airport.status') AS faa_status
                       FROM delay_snapshots
                       ORDER BY collected_at ASC
                       """)
    
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
                         ORDER BY collected_at ASC
                         """)
    
    flight_df = load_df("""
                        SELECT
                            airport_code,
                            collected_at,
                            delay_minutes,
                            cancelled,
                            diverted
                        FROM flight_snapshots
                        ORDER BY collected_at ASC
                        """)
    
    faa_events_df = load_df("""
                            SELECT
                                airport_code,
                                collected_at,
                                min_delay_minutes,
                                max_delay_minutes
                            FROM faa_events
                            ORDER BY collected_at ASC
                            """)
    
    if delay_df.empty:
        st.warning("No delay data found yet. Run `python src/collect_delays.py` a few times first.")
        st.stop()
    
    delay_df["collected_at"] = pd.to_datetime(delay_df["collected_at"], utc=True)
    delay_df["collected_at_local"] = delay_df["collected_at"].dt.tz_convert(LOCAL_TZ)
    delay_df["collected_at_local_label"] = delay_df["collected_at_local"].dt.strftime("%I:%M %p %b %d")
    
    if not traffic_df.empty:
        traffic_df["collected_at"] = pd.to_datetime(traffic_df["collected_at"], utc=True)
        traffic_df["collected_at_local"] = traffic_df["collected_at"].dt.tz_convert(LOCAL_TZ)
        traffic_df["collected_at_local_label"] = traffic_df["collected_at_local"].dt.strftime("%I:%M %p %b %d")
    
    if not flight_df.empty:
        flight_df["collected_at"] = pd.to_datetime(flight_df["collected_at"], utc=True)
        flight_df["collected_at_local"] = flight_df["collected_at"].dt.tz_convert(LOCAL_TZ)
        flight_df["delay_minutes"] = pd.to_numeric(flight_df["delay_minutes"], errors="coerce")
        flight_df["cancelled"] = pd.to_numeric(flight_df["cancelled"], errors="coerce").fillna(0)
        flight_df["diverted"] = pd.to_numeric(flight_df["diverted"], errors="coerce").fillna(0)
    
    if not faa_events_df.empty:
        faa_events_df["collected_at"] = pd.to_datetime(faa_events_df["collected_at"], utc=True)
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
        if popover_fn:
            with st.popover("Sync Data Now (API Calls)"):
                st.warning("This will immediately call FAA, Live Airspace Traffic, and AirLabs APIs.")
                confirm_sync = st.checkbox("I understand this triggers live API requests now.", key="confirm_manual_sync")
                if st.button("Run Manual Sync Now", key="run_manual_sync_button"):
                    if not confirm_sync:
                        st.error("Please confirm before running manual sync.")
                    else:
                        with st.spinner("Running collectors..."):
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
                        with st.spinner("Running collectors..."):
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
    filtered["load_total"] = pd.NA
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
                filtered[filtered["airport_code"] == airport]
                .sort_values("collected_at")
                .copy()
            )
            if "aircraft_count_for_score" in d_a.columns:
                d_a = d_a.drop(columns=["aircraft_count_for_score"])
            t_a = (
                traffic_df[
                    (traffic_df["airport_code"] == airport) &
                    (traffic_df["aircraft_count"].notna())
                ][["collected_at", "aircraft_count"]]
                .sort_values("collected_at")
                .copy()
            )
    
            if t_a.empty:
                d_a["aircraft_count_for_score"] = pd.NA
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
    
        if merged_parts:
            filtered = pd.concat(merged_parts, ignore_index=True)
    
    if "aircraft_count_for_score" not in filtered.columns:
        filtered["aircraft_count_for_score"] = pd.NA
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

    # Load-adjusted score normalizes stress by relative load at each snapshot timestamp.
    filtered["peer_avg_load"] = filtered.groupby("collected_at")["traffic_load_effective"].transform("mean")
    filtered["relative_load_factor"] = filtered["traffic_load_effective"] / filtered["peer_avg_load"]
    filtered["relative_load_factor"] = pd.to_numeric(filtered["relative_load_factor"], errors="coerce")
    filtered.loc[
        filtered["relative_load_factor"].isna() | (filtered["relative_load_factor"] <= 0),
        "relative_load_factor"
    ] = 1.0
    filtered["load_adjusted_stress_score"] = filtered["operational_stress_score"] / filtered["relative_load_factor"]
    filtered["load_adjusted_stress_score"] = pd.to_numeric(filtered["load_adjusted_stress_score"], errors="coerce")
    
    # Convenience time features (Local)
    filtered["date_utc"] = filtered["collected_at_local"].dt.date
    filtered["hour_utc"] = filtered["collected_at_local"].dt.hour
    filtered["dow_utc"] = filtered["collected_at_local"].dt.day_name()
    
    # -----------------------
    # At A Glance
    # -----------------------
    st.subheader("At A Glance")
    
    latest_by_airport = (
        filtered.sort_values("collected_at")
        .groupby("airport_code", as_index=False)
        .tail(1)
        .sort_values("airport_code")
    )
    
    airline_severity_map = {}
    if not flight_df.empty:
        flights_selected = flight_df[flight_df["airport_code"].isin(selected_airports)].copy()
        if not flights_selected.empty:
            latest_flight_snapshots = (
                flights_selected.sort_values("collected_at")
                .groupby("airport_code", as_index=False)
                .tail(1)[["airport_code", "collected_at"]]
            )
    
            latest_snapshot_rows = flights_selected.merge(
                latest_flight_snapshots,
                on=["airport_code", "collected_at"],
                how="inner"
            )
    
            for airport, grp in latest_snapshot_rows.groupby("airport_code"):
                flights_n = len(grp)
                if flights_n == 0:
                    continue
    
                positive_delay = grp["delay_minutes"].clip(lower=0)
                avg_delay = float(positive_delay.mean()) if positive_delay.notna().any() else 0.0
                cancel_rate = float(grp["cancelled"].mean())
                divert_rate = float(grp["diverted"].mean())
    
                delay_component = min(avg_delay / 20.0, 3.0)
                cancel_component = min(cancel_rate * 4.0, 1.5)
                divert_component = min(divert_rate * 2.0, 0.5)
                airline_severity = min(delay_component + cancel_component + divert_component, 5.0)
    
                airline_severity_map[airport] = {
                    "score": round(airline_severity, 3),
                    "flights_n": flights_n,
                    "avg_delay_min": round(avg_delay, 1),
                    "cancel_rate_pct": round(cancel_rate * 100.0, 1),
                    "divert_rate_pct": round(divert_rate * 100.0, 1),
                    "snapshot_time": grp["collected_at"].max(),
                }
    
    today_local = pd.Timestamp.now(tz=LOCAL_TZ).date()
    longest_airline_today_map = {}
    if not flight_df.empty:
        flights_today = flight_df.copy()
        flights_today["collected_at_local"] = flights_today["collected_at"].dt.tz_convert(LOCAL_TZ)
        flights_today = flights_today[flights_today["collected_at_local"].dt.date == today_local]
        if not flights_today.empty:
            airline_max = (
                flights_today.groupby("airport_code", as_index=False)["delay_minutes"]
                .max()
                .rename(columns={"delay_minutes": "longest_airline_delay_today"})
            )
            longest_airline_today_map = {
                r["airport_code"]: (r["longest_airline_delay_today"] if pd.notna(r["longest_airline_delay_today"]) else None)
                for r in airline_max.to_dict(orient="records")
            }
    
    longest_faa_today_map = {}
    if not faa_events_df.empty:
        faa_today = faa_events_df.copy()
        faa_today["collected_at_local"] = faa_today["collected_at"].dt.tz_convert(LOCAL_TZ)
        faa_today = faa_today[faa_today["collected_at_local"].dt.date == today_local]
        if not faa_today.empty:
            faa_today["faa_delay_for_max"] = faa_today["max_delay_minutes"]
            faa_today.loc[faa_today["faa_delay_for_max"].isna(), "faa_delay_for_max"] = faa_today["min_delay_minutes"]
            faa_max = (
                faa_today.groupby("airport_code", as_index=False)["faa_delay_for_max"]
                .max()
                .rename(columns={"faa_delay_for_max": "longest_faa_delay_today"})
            )
            longest_faa_today_map = {
                r["airport_code"]: (r["longest_faa_delay_today"] if pd.notna(r["longest_faa_delay_today"]) else None)
                for r in faa_max.to_dict(orient="records")
            }
    
    overview_rows = []
    for row in latest_by_airport.to_dict(orient="records"):
        airport = row["airport_code"]
        airline_score = (airline_severity_map.get(airport) or {}).get("score")
        airline_today = longest_airline_today_map.get(airport)
        faa_today = longest_faa_today_map.get(airport)
        any_today = max([v for v in [airline_today, faa_today] if v is not None], default=None)
        overview_rows.append(
            {
                "airport_code": airport,
            "operational_stress_score": safe_float(row.get("operational_stress_score")),
            "load_adjusted_stress_score": safe_float(row.get("load_adjusted_stress_score")),
            "airline_delay_severity_index": safe_float(airline_score),
            "traffic_load": safe_float(row.get("traffic_load_effective")),
            "longest_delay_today": safe_float(any_today),
        }
    )
    
    overview_df = pd.DataFrame(overview_rows)
    if not overview_df.empty:
        o1, o2, o3, o4 = st.columns(4)
        top_stress = overview_df.sort_values("load_adjusted_stress_score", ascending=False).iloc[0]
        top_airline = overview_df.sort_values("airline_delay_severity_index", ascending=False).iloc[0]
        top_longest = overview_df.sort_values("longest_delay_today", ascending=False).iloc[0]
    
        traffic_gap_text = "N/A"
        if len(overview_df) >= 2 and overview_df["traffic_load"].notna().sum() >= 2:
            top_two = overview_df.sort_values("traffic_load", ascending=False).head(2)
            gap = top_two.iloc[0]["traffic_load"] - top_two.iloc[1]["traffic_load"]
            traffic_gap_text = f"{int(round(gap))} aircraft"
    
        with o1:
            st.metric(
                "Highest Load-Adjusted Stress",
                "N/A" if pd.isna(top_stress["load_adjusted_stress_score"]) else top_stress["airport_code"],
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
            if not pd.isna(top_longest["longest_delay_today"]):
                longest_text = f"{top_longest['airport_code']} ({format_minutes_hr_min(top_longest['longest_delay_today'])})"
            st.metric("Longest Delay Today", longest_text)
        
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
                traffic_cards.sort_values("collected_at")
                .groupby("airport_code", as_index=False)
                .tail(1)
            )
            traffic_latest_map = {
                r["airport_code"]: r for r in latest_traffic_by_airport.to_dict(orient="records")
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
        
        for i, row in enumerate(latest_by_airport.to_dict(orient="records")):
            collected_local = format_local_snapshot_time(pd.to_datetime(row["collected_at"], utc=True))
            traffic_row = traffic_latest_map.get(row["airport_code"])
            airline_row = airline_severity_map.get(row["airport_code"])
            airline_max_today = longest_airline_today_map.get(row["airport_code"])
            faa_max_today = longest_faa_today_map.get(row["airport_code"])
            longest_any_today = max(
                [v for v in [airline_max_today, faa_max_today] if v is not None],
                default=None
            )
            with card_cols[i]:
                st.markdown("<div style='padding: 0 12px;'>", unsafe_allow_html=True)
                st.write(f"**Snapshot Time (Local):** {collected_local}")
                st.metric(
                    label=f"{row['airport_code']} Delay Severity Index (FAA)",
                    value="—" if pd.isna(row["delay_index_best"]) else round(float(row["delay_index_best"]), 3),
                )
                st.metric(
                    label=f"{row['airport_code']} Airline Delay Severity Index",
                    value="N/A" if airline_row is None else airline_row["score"],
                )
                st.metric(
                    label=f"{row['airport_code']} Traffic Load (Live Aircraft)",
                    value=int(row["traffic_load_effective"]) if pd.notna(row["traffic_load_effective"]) else "N/A",
                )
                st.metric(
                    label=f"{row['airport_code']} Operational Stress Score",
                    value="—" if pd.isna(row["operational_stress_score"]) else round(float(row["operational_stress_score"]), 3),
                )
                st.metric(
                    label=f"{row['airport_code']} Load-Adjusted Stress Score",
                    value="—" if pd.isna(row["load_adjusted_stress_score"]) else round(float(row["load_adjusted_stress_score"]), 3),
                )
                st.metric(
                    label=f"{row['airport_code']} Longest Delay Today (Any Source)",
                    value=format_minutes_hr_min(longest_any_today),
                )
                st.metric(
                    label=f"{row['airport_code']} Longest Airline Delay Today",
                    value=format_minutes_hr_min(airline_max_today),
                )
                st.write(f"**FAA Update Time (Local):** {format_faa_update_time_local(row.get('faa_update_time'))}")
                st.write(f"**Active FAA Restrictions:** {int(row['faa_event_count']) if pd.notna(row.get('faa_event_count')) else 0}")
                st.write(f"**FAA Status:** {row.get('faa_status', '—') if row.get('faa_status') else '—'}")
                avg_delay_value = None if airline_row is None else airline_row.get("avg_delay_min")
                st.write(
                    f"**Average Delay:** {format_minutes_hr_min(avg_delay_value)}"
                    if avg_delay_value is not None and pd.notna(avg_delay_value)
                    else "**Average Delay:** N/A"
                )
                if airline_row is None:
                    st.write("**Airline Snapshot:** N/A")
                else:
                    airline_time = format_local_snapshot_time(pd.to_datetime(airline_row["snapshot_time"], utc=True))
                    st.write(f"**Airline Snapshot Time (Local):** {airline_time}")
                    st.write(
                        f"**Airline Inputs:** Flights {airline_row['flights_n']}, "
                        f"Avg Delay {airline_row['avg_delay_min']} min, "
                        f"Cancelled {airline_row['cancel_rate_pct']}%, "
                        f"Diverted {airline_row['divert_rate_pct']}%"
                    )
                st.markdown("#### Current Operational Load")
                if traffic_row is None:
                    st.write("No traffic snapshot available for this airport in selected time range.")
                else:
                    traffic_time_local = format_local_snapshot_time(pd.to_datetime(traffic_row["collected_at"], utc=True))
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
                        avg_delay_min=("delay_positive", "mean"),
                        max_delay_min=("delay_positive", "max"),
                        cancel_rate=("cancelled", "mean"),
                        divert_rate=("diverted", "mean"),
                    )
                )
                airline_snap["airline_delay_severity_index"] = (
                    (airline_snap["avg_delay_min"].fillna(0) / 20.0).clip(upper=3.0) +
                    (airline_snap["cancel_rate"].fillna(0) * 4.0).clip(upper=1.5) +
                    (airline_snap["divert_rate"].fillna(0) * 2.0).clip(upper=0.5)
                ).clip(upper=5.0)
        
                a1, a2 = st.columns(2)
                with a1:
                    fig = px.line(
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
                    format_time_axis_12h(fig)
                    st.plotly_chart(fig, width="stretch")
        
                with a2:
                    fig = px.line(
                        airline_snap,
                        x="collected_at_local",
                        y="max_delay_min",
                        color="airport_code",
                        markers=True,
                        title="Longest Airline Delay By Snapshot",
                        labels={
                            "collected_at_local": "Snapshot Time (Local)",
                            "max_delay_min": "Longest Airline Delay (Minutes)",
                            "airport_code": "Airport",
                        },
                    )
                    format_time_axis_12h(fig)
                    st.plotly_chart(fig, width="stretch")
        
                today_rows = []
                for airport in selected_airports:
                    airline_today = longest_airline_today_map.get(airport)
                    any_today = max([v for v in [airline_today, longest_faa_today_map.get(airport)] if v is not None], default=None)
                    today_rows.append({"airport_code": airport, "metric": "Longest Airline Delay Today", "delay_minutes": airline_today})
                    today_rows.append({"airport_code": airport, "metric": "Longest Delay Today (Any Source)", "delay_minutes": any_today})
        
                today_df = pd.DataFrame(today_rows)
                today_df = today_df[today_df["delay_minutes"].notna()]
                if not today_df.empty:
                    fig = px.bar(
                        today_df,
                        x="airport_code",
                        y="delay_minutes",
                        color="metric",
                        barmode="group",
                        title="Longest Delay Today Comparison",
                        labels={
                            "airport_code": "Airport",
                            "delay_minutes": "Delay (Minutes)",
                            "metric": "Metric",
                        },
                    )
                    st.plotly_chart(fig, width="stretch")
        
        st.divider()
        
        
        # -----------------------
        # Trends + Rolling Average
        # -----------------------
        st.subheader("Trend Lines")
        st.caption("Use this section to see whether one airport consistently runs worse over time.")
        
        rolling_window = 6
        
        trend = filtered.sort_values(["airport_code", "collected_at"]).copy()
        trend["delay_index_roll"] = (
            trend.groupby("airport_code")["delay_index_best"]
            .transform(lambda s: s.rolling(rolling_window, min_periods=1).mean())
        )
        
        trend["load_roll"] = (
            trend.groupby("airport_code")["traffic_load_effective"]
            .transform(lambda s: s.rolling(rolling_window, min_periods=1).mean())
        )
        
        trend["sucks_roll"] = (
            trend.groupby("airport_code")["operational_stress_score"]
            .transform(lambda s: s.rolling(rolling_window, min_periods=1).mean())
        )
        trend["load_adjusted_sucks_roll"] = (
            trend.groupby("airport_code")["load_adjusted_stress_score"]
            .transform(lambda s: s.rolling(rolling_window, min_periods=1).mean())
        )
        
        c1, c2, c3 = st.columns(3)
        
        with c1:
            fig = px.line(
                trend,
                x="collected_at_local",
                y="delay_index_best",
                color="airport_code",
                markers=True,
                title="Delay Severity Index Over Time (Raw)",
                labels={
                    "collected_at_local": "Snapshot Time (Local)",
                    "delay_index_best": "Delay Severity Index",
                    "airport_code": "Airport",
                },
            )
            format_time_axis_12h(fig)
            st.plotly_chart(fig, width='stretch')
        
        with c2:
            fig = px.line(
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
            )
            format_time_axis_12h(fig)
            st.plotly_chart(fig, width='stretch')
        
        with c3:
            fig = px.line(
                trend,
                x="collected_at_local",
                y="load_adjusted_sucks_roll",
                color="airport_code",
                markers=True,
                title=f"Load-Adjusted Stress Score (Rolling Average, {rolling_window} Points)",
                labels={
                    "collected_at_local": "Snapshot Time (Local)",
                    "load_adjusted_sucks_roll": "Load-Adjusted Stress Score",
                    "airport_code": "Airport",
                },
            )
            format_time_axis_12h(fig)
            st.plotly_chart(fig, width='stretch')
        
        st.divider()
        
        
        # -----------------------
        # Load vs Delay (Efficiency curve)
        # -----------------------
        st.subheader("Traffic Load vs Delay Severity")
        st.caption("If one airport has higher delay severity at similar load, that suggests disproportionate operational pain.")
        
        load_vs_delay = trend.dropna(subset=["traffic_load_effective", "delay_index_best"]).copy()
        
        if load_vs_delay.empty:
            st.info("Not enough valid load + delay data points yet to plot this chart.")
        else:
            fig = px.scatter(
                load_vs_delay,
                x="traffic_load_effective",
                y="delay_index_best",
                color="airport_code",
                hover_data=["collected_at_local_label", "window_from_utc", "window_to_utc", "dep_total", "arr_total"],
                title="Delay Severity Index vs Traffic Load (Each Point = One Snapshot)",
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
            )
            st.plotly_chart(fig, width='stretch')
        
        st.divider()
        
        
        # -----------------------
        # Heatmap: Hour x Day-of-week
        # -----------------------
        st.subheader("Delay Heatmap (Hour × Day Of Week)")
        st.caption("Highlights when disruption typically happens.")
        
        if filtered["date_utc"].nunique() < 2:
            st.info("Heatmap will be much more meaningful after you collect at least a couple days of data.")
        else:
            # Order DOW nicely
            dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
            hm_cols = st.columns(len(selected_airports))
            for i, airport in enumerate(selected_airports):
                with hm_cols[i]:
                    df_a = filtered[filtered["airport_code"] == airport].copy()
                    df_a["dow_utc"] = pd.Categorical(df_a["dow_utc"], categories=dow_order, ordered=True)
        
                    pivot = df_a.pivot_table(
                        index="hour_utc",
                        columns="dow_utc",
                        values="delay_index_best",
                        aggfunc="mean"
                    )
        
                    fig = px.imshow(
                        pivot,
                        aspect="auto",
                        title=f"{airport} Average Delay Severity By Hour And Day Of Week (Local)"
                    )
                    st.plotly_chart(fig, width='stretch')
        
        st.divider()
        
        
        # -----------------------
        # Worst Day / Worst Hour
        # -----------------------
        st.subheader("Worst Time Periods")
        
        worst_day = (
            filtered.groupby(["airport_code", "date_utc"], as_index=False)
            .agg(avg_delay_index=("delay_index_best", "mean"),
                 avg_sucks=("operational_stress_score", "mean"),
                 avg_load=("traffic_load_effective", "mean"),
                 samples=("id", "count"))
            .sort_values(["avg_sucks", "avg_delay_index"], ascending=False)
        )
        
        worst_hour = (
            filtered.groupby(["airport_code", "dow_utc", "hour_utc"], as_index=False)
            .agg(avg_delay_index=("delay_index_best", "mean"),
                 avg_sucks=("operational_stress_score", "mean"),
                 avg_load=("traffic_load_effective", "mean"),
                 samples=("id", "count"))
            .sort_values(["avg_sucks", "avg_delay_index"], ascending=False)
        )
        
        w1, w2 = st.columns(2)
        with w1:
            st.write("### Worst Days (highest stress)")
            st.dataframe(prettify_columns(worst_day.head(10)), width='stretch')
        
        with w2:
            st.write("### Worst Hour Blocks (Local, highest stress)")
            st.dataframe(prettify_columns(worst_hour.head(10)), width='stretch')
        
        st.divider()
        
        
        # -----------------------
        # Traffic correlation: aircraft_count vs delay index
        # -----------------------
        st.subheader("Traffic vs Delay Relationship")
        st.caption("Positive correlation means higher aircraft volume tends to coincide with higher delay severity.")
        
        if traffic_df.empty:
            st.info("No traffic data found yet. Run `python src/collect_traffic.py` a few times.")
        else:
            # Filter traffic to selected airports and time range
            t = traffic_df[traffic_df["airport_code"].isin(selected_airports)].copy()
            t = t[t["collected_at_local"].between(start_dt, end_dt)].sort_values(["airport_code", "collected_at"])
        
            # We'll align by nearest timestamp per airport using merge_asof
            d = filtered.sort_values(["airport_code", "collected_at"]).copy()
        
            merged_list = []
            for airport in selected_airports:
                d_a = d[d["airport_code"] == airport].sort_values("collected_at")
                t_a = t[t["airport_code"] == airport].sort_values("collected_at")
        
                if d_a.empty or t_a.empty:
                    continue
        
                # Nearest traffic snapshot within 20 minutes
                m = pd.merge_asof(
                    d_a,
                    t_a,
                    on="collected_at",
                    direction="nearest",
                    tolerance=pd.Timedelta("20min"),
                    suffixes=("", "_traffic")
                )
                merged_list.append(m)
        
            if not merged_list:
                st.info("Not enough overlapping delay+traffic data yet (need both collectors running).")
            else:
                merged = pd.concat(merged_list, ignore_index=True)
        
                # Correlation per airport
                corr_rows = []
                for airport in selected_airports:
                    sub = merged[merged["airport_code"] == airport].dropna(subset=["aircraft_count", "delay_index_best"])
                    if len(sub) < 3:
                        corr = None
                    elif sub["aircraft_count"].nunique() < 2 or sub["delay_index_best"].nunique() < 2:
                        # Avoid NumPy divide warnings from zero-variance correlation inputs.
                        corr = None
                    else:
                        corr = sub["aircraft_count"].corr(sub["delay_index_best"])
                    corr_rows.append({"airport_code": airport, "corr_aircraft_vs_delay": corr, "points": len(sub)})
        
                st.write("### Correlation Summary (Aircraft Count Vs Delay Severity)")
                st.dataframe(prettify_columns(pd.DataFrame(corr_rows)), width='stretch')
        
                fig = px.scatter(
                    merged,
                    x="aircraft_count",
                    y="delay_index_best",
                    color="airport_code",
                    hover_data=["collected_at_local_label", "traffic_load_effective", "airborne_count", "on_ground_count"],
                    title="Delay Severity Vs Aircraft Count (Nearest Timestamp Match Within 20 Minutes)",
                    labels={
                        "aircraft_count": "Aircraft Count",
                        "delay_index_best": "Delay Severity Index",
                        "airport_code": "Airport",
                        "collected_at_local_label": "Snapshot Time (Local)",
                        "traffic_load_effective": "Traffic Load",
                        "airborne_count": "Airborne Count",
                        "on_ground_count": "On Ground Count",
                    },
                )
                st.plotly_chart(fig, width='stretch')
        
        st.divider()
        
        
        # -----------------------
        # Raw table expander
        # -----------------------
        with st.expander("Show raw delay_snapshots (filtered)"):
            filtered_raw = filtered.copy()
            filtered_raw["collected_at_local_label"] = filtered_raw["collected_at_local"].dt.strftime("%I:%M %p %b %d")
            show_cols = [
                "airport_code", "collected_at_local_label",
                "source",
                "window_from_utc", "window_to_utc",
                "delay_index", "dep_delay_index", "arr_delay_index",
                "delay_index_best",
                "delay_median_minutes", "dep_median_delay_minutes", "arr_median_delay_minutes",
                "dep_total", "arr_total",
                "traffic_load_effective",
                "operational_stress_score",
            ]
            st.dataframe(
                prettify_columns(filtered_raw.sort_values("collected_at_local", ascending=False)[show_cols]),
                width='stretch'
            )
