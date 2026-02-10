from pathlib import Path
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aviation.db"

st.set_page_config(page_title="MCO vs DEN – Airport Performance", layout="wide")
st.title("✈️ MCO vs DEN – Airport Delay & Load Dashboard")

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
                (SELECT MAX(collected_at) FROM delay_snapshots)  AS last_delay,
                (SELECT MAX(collected_at) FROM traffic_snapshots) AS last_traffic \
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

                       delay_index,
                       delay_median_minutes,

                       dep_total,
                       arr_total,
                       dep_delay_index,
                       dep_median_delay_minutes,

                       arr_delay_index,
                       arr_median_delay_minutes
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

if delay_df.empty:
    st.warning("No delay data found yet. Run `python src/collect_delays.py` a few times first.")
    st.stop()

delay_df["collected_at"] = pd.to_datetime(delay_df["collected_at"], utc=True)

if not traffic_df.empty:
    traffic_df["collected_at"] = pd.to_datetime(traffic_df["collected_at"], utc=True)

last = get_last_updated()
now = pd.Timestamp.now(tz="UTC")

cA, cB, cC = st.columns(3)

with cA:
    st.metric(
        "Last Delay Snapshot (UTC)",
        "—" if last["last_delay"] is None else last["last_delay"].strftime("%Y-%m-%d %H:%M:%SZ"),
    )

with cB:
    st.metric(
        "Last Traffic Snapshot (UTC)",
        "—" if last["last_traffic"] is None else last["last_traffic"].strftime("%Y-%m-%d %H:%M:%SZ"),
    )

with cC:
    # show “age” based on the most recent of the two
    latest_any = max([t for t in [last["last_delay"], last["last_traffic"]] if t is not None], default=None)
    age = (now - latest_any) if latest_any is not None else None
    age_min = int(age.total_seconds() // 60) if age is not None else None
    st.metric("Data Age", "—" if age_min is None else f"{age_min} min ago")

st.caption("Dashboard reads directly from your local SQLite DB. If cron is running, these timestamps should keep updating.")
if st.button("Refresh now"):
    st.rerun()
st.divider()

# -----------------------
# Sidebar filters
# -----------------------
st.sidebar.header("Filters")

airports = sorted(delay_df["airport_code"].unique().tolist())
selected_airports = st.sidebar.multiselect("Airports", options=airports, default=["MCO", "DEN"])

filtered = delay_df[delay_df["airport_code"].isin(selected_airports)].copy()

min_dt = filtered["collected_at"].min()
max_dt = filtered["collected_at"].max()

date_range = st.sidebar.slider(
    "Time range (UTC)",
    min_value=min_dt.to_pydatetime(),
    max_value=max_dt.to_pydatetime(),
    value=(min_dt.to_pydatetime(), max_dt.to_pydatetime())
)

start_dt = pd.to_datetime(date_range[0], utc=True)
end_dt = pd.to_datetime(date_range[1], utc=True)

filtered = filtered[filtered["collected_at"].between(start_dt, end_dt)].copy()

# Derived load column
filtered["load_total"] = filtered[["dep_total", "arr_total"]].fillna(0).sum(axis=1)

# Use a "best available delay index":
# prefer overall delay_index, else fall back to dep_delay_index.
filtered["delay_index_best"] = filtered["delay_index"]
filtered.loc[filtered["delay_index_best"].isna(), "delay_index_best"] = filtered["dep_delay_index"]

# MCO Sucks Score™ (scaled so it’s readable)
# Idea: higher delay index + higher load = worse passenger experience / ops handling
filtered["mco_sucks_score"] = filtered["delay_index_best"] * (filtered["load_total"] / 100.0)

# Convenience time features (UTC)
filtered["date_utc"] = filtered["collected_at"].dt.date
filtered["hour_utc"] = filtered["collected_at"].dt.hour
filtered["dow_utc"] = filtered["collected_at"].dt.day_name()


# -----------------------
# Latest snapshot cards
# -----------------------
st.subheader("Latest Snapshot")

latest_by_airport = (
    filtered.sort_values("collected_at")
    .groupby("airport_code", as_index=False)
    .tail(1)
    .sort_values("airport_code")
)

cols = st.columns(len(latest_by_airport))
for i, row in enumerate(latest_by_airport.to_dict(orient="records")):
    with cols[i]:
        st.metric(
            label=f"{row['airport_code']} Delay Index (best)",
            value="—" if pd.isna(row["delay_index_best"]) else round(float(row["delay_index_best"]), 3),
        )
        st.metric(
            label=f"{row['airport_code']} Load (dep+arr)",
            value=int(row["load_total"]) if pd.notna(row["load_total"]) else "—",
        )
        st.metric(
            label=f"{row['airport_code']} MCO Sucks Score™",
            value="—" if pd.isna(row["mco_sucks_score"]) else round(float(row["mco_sucks_score"]), 3),
        )

        st.write(f"**Window:** {row.get('window_from_utc','—')} → {row.get('window_to_utc','—')}")
        st.write(f"**Dep Total:** {int(row['dep_total']) if pd.notna(row['dep_total']) else '—'}")
        st.write(f"**Arr Total:** {int(row['arr_total']) if pd.notna(row['arr_total']) else '—'}")
        st.write(f"**Median Delay (min):** {row['delay_median_minutes'] if pd.notna(row['delay_median_minutes']) else '—'}")

st.divider()


# -----------------------
# Trends + Rolling Average
# -----------------------
st.subheader("Trends")

rolling_window = st.sidebar.select_slider(
    "Rolling window (points)",
    options=[1, 3, 6, 12],
    value=6
)

trend = filtered.sort_values(["airport_code", "collected_at"]).copy()
trend["delay_index_roll"] = (
    trend.groupby("airport_code")["delay_index_best"]
    .transform(lambda s: s.rolling(rolling_window, min_periods=1).mean())
)

trend["load_roll"] = (
    trend.groupby("airport_code")["load_total"]
    .transform(lambda s: s.rolling(rolling_window, min_periods=1).mean())
)

trend["sucks_roll"] = (
    trend.groupby("airport_code")["mco_sucks_score"]
    .transform(lambda s: s.rolling(rolling_window, min_periods=1).mean())
)

c1, c2, c3 = st.columns(3)

with c1:
    fig = px.line(
        trend,
        x="collected_at",
        y="delay_index_best",
        color="airport_code",
        markers=True,
        title="Delay Index Over Time (raw)"
    )
    st.plotly_chart(fig, width='stretch')

with c2:
    fig = px.line(
        trend,
        x="collected_at",
        y="delay_index_roll",
        color="airport_code",
        markers=True,
        title=f"Delay Index (rolling avg, {rolling_window} pts)"
    )
    st.plotly_chart(fig, width='stretch')

with c3:
    fig = px.line(
        trend,
        x="collected_at",
        y="sucks_roll",
        color="airport_code",
        markers=True,
        title=f"MCO Sucks Score™ (rolling avg, {rolling_window} pts)"
    )
    st.plotly_chart(fig, width='stretch')

st.divider()


# -----------------------
# Load vs Delay (Efficiency curve)
# -----------------------
st.subheader("Load vs Delay (Is MCO 'disproportionate'?)")

fig = px.scatter(
    trend,
    x="load_total",
    y="delay_index_best",
    color="airport_code",
    hover_data=["collected_at", "window_from_utc", "window_to_utc", "dep_total", "arr_total"],
    title="Delay Index vs Load (each point = one snapshot)"
)
st.plotly_chart(fig, width='stretch')

st.divider()


# -----------------------
# Heatmap: Hour x Day-of-week
# -----------------------
st.subheader("Delay Heatmap (Hour × Day of Week)")

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
                title=f"{airport} Avg Delay Index by Hour/DOW (UTC)"
            )
            st.plotly_chart(fig, width='stretch')

st.divider()


# -----------------------
# Worst Day / Worst Hour
# -----------------------
st.subheader("Worst Performance (Days & Hours)")

worst_day = (
    filtered.groupby(["airport_code", "date_utc"], as_index=False)
    .agg(avg_delay_index=("delay_index_best", "mean"),
         avg_sucks=("mco_sucks_score", "mean"),
         avg_load=("load_total", "mean"),
         samples=("id", "count"))
    .sort_values(["avg_sucks", "avg_delay_index"], ascending=False)
)

worst_hour = (
    filtered.groupby(["airport_code", "dow_utc", "hour_utc"], as_index=False)
    .agg(avg_delay_index=("delay_index_best", "mean"),
         avg_sucks=("mco_sucks_score", "mean"),
         avg_load=("load_total", "mean"),
         samples=("id", "count"))
    .sort_values(["avg_sucks", "avg_delay_index"], ascending=False)
)

w1, w2 = st.columns(2)
with w1:
    st.write("### Worst Days")
    st.dataframe(worst_day.head(10), width='stretch')

with w2:
    st.write("### Worst Hour Blocks (UTC)")
    st.dataframe(worst_hour.head(10), width='stretch')

st.divider()


# -----------------------
# OpenSky correlation: aircraft_count vs delay index
# -----------------------
st.subheader("OpenSky Traffic vs Delay (Correlation)")

if traffic_df.empty:
    st.info("No traffic data found yet. Run `python src/collect_traffic.py` a few times.")
else:
    # Filter traffic to selected airports and time range
    t = traffic_df[traffic_df["airport_code"].isin(selected_airports)].copy()
    t = t[t["collected_at"].between(start_dt, end_dt)].sort_values(["airport_code", "collected_at"])

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
            corr = sub["aircraft_count"].corr(sub["delay_index_best"]) if len(sub) >= 3 else None
            corr_rows.append({"airport_code": airport, "corr_aircraft_vs_delay": corr, "points": len(sub)})

        st.write("### Correlation Summary (aircraft_count vs delay_index)")
        st.dataframe(pd.DataFrame(corr_rows), width='stretch')

        fig = px.scatter(
            merged,
            x="aircraft_count",
            y="delay_index_best",
            color="airport_code",
            hover_data=["collected_at", "load_total", "airborne_count", "on_ground_count"],
            title="Delay Index vs OpenSky Aircraft Count (nearest match within 20 minutes)"
        )
        st.plotly_chart(fig, width='stretch')

st.divider()


# -----------------------
# Raw table expander
# -----------------------
with st.expander("Show raw delay_snapshots (filtered)"):
    show_cols = [
        "airport_code", "collected_at",
        "window_from_utc", "window_to_utc",
        "delay_index", "dep_delay_index", "arr_delay_index",
        "delay_index_best",
        "delay_median_minutes", "dep_median_delay_minutes", "arr_median_delay_minutes",
        "dep_total", "arr_total",
        "load_total",
        "mco_sucks_score",
    ]
    st.dataframe(filtered[show_cols].sort_values("collected_at", ascending=False), width='stretch')
