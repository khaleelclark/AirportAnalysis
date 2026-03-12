"""Dashboard documentation/content strings.

Keeping long copy blocks out of app.py improves readability and reduces merge churn.
"""

ABOUT_MARKDOWN = """
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

CALC_MARKDOWN = """
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

HOW_TO_READ_MARKDOWN = """
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
