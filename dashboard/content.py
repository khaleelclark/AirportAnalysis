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
  FAA downtime minutes per 100 live aircraft (operational core) and Airline Delay Severity (passenger core).
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
This tab explains where the numbers on the main dashboard come from, in plain language.

### What appears on the main dashboard
- **Last Synced**: The most recent update time for FAA data, traffic data, and airline data.
- **At A Glance**: A quick summary of which airport currently looks worse on a few headline measures.
- **Latest Airport Snapshot**: The newest side-by-side view of MCO and DEN.
- **Hypothesis Check**: The main comparison section that asks whether MCO is doing worse than DEN after adjusting for busyness.
- **FAA Status History**: How often FAA restrictions show up and how strong they are over time.
- **Airline Delay Impact**: Passenger-facing delay, cancellation, and longest-delay trends.
- **Delay Timing Breakdown**: Which days of the week tend to have worse overall delays.

### Last Synced
These timestamps are not calculated scores. They simply show the latest time the dashboard successfully stored data from each source.

### At A Glance
This row is a quick comparison, not a separate model.
- **Highest Operational Stress**: Which airport currently has the higher Operational Stress Score.
- **Highest Airline Delay Severity**: Which airport currently has the higher airline severity score.
- **Airport Traffic Load Difference**: The difference in live aircraft count between the two airports.
- **Longest Recorded Delay**: Which airport has the biggest delay seen in the collected history, using either airline delay data or FAA delay ranges.

### Latest Airport Snapshot
This section uses the newest available snapshot for each airport.

**FAA Delay Severity**
- This is based on the FAA's active restriction level.
- `0` means no active FAA restriction.
- Higher numbers mean more serious restrictions, such as delay programs, ground stops, or closures.
- If more than one FAA restriction is active at the same time, the dashboard uses the most severe one.

**Airline Delay Severity Index**
- This is a `0` to `5` score built from three airline signals:
  average delay, cancellation rate, and diversion rate.
- Higher means worse for travelers.
- In simple terms: more delayed flights, more cancellations, and more diversions push the score up.

**Operational Stress Score**
- This combines FAA delay severity with live traffic pressure.
- Plain-language formula:
  `(1 + FAA Delay Severity) x live aircraft count`, scaled down for readability.
- The score rises when the airport is both busy and under stronger FAA restrictions.

**Other snapshot numbers**
- **Active FAA Restrictions**: How many FAA restriction records are active in that snapshot.
- **Longest Airline Delay Today**: The single longest airline delay seen today.
- **Longest Recorded Delay (Any Source)**: The biggest delay seen in the full collected history, from either airline data or FAA delay ranges.
- **Current Operational Load**: Live aircraft counts shown as In Airspace, Airborne, and On Ground.

### Hypothesis Check
This is the most important part of the dashboard.
It compares MCO and DEN using matching local time periods, so the comparison is more fair.
For example, it compares MCO at 9 AM with DEN at 9 AM rather than mixing very different times of day.

**The two main comparison numbers**
- **Operational Core (MCO/DEN)**:
  FAA downtime minutes per 100 live aircraft.
  Here, **traffic load** means the number of aircraft around the airport.
  This asks: for every 100 aircraft, which airport loses more time to FAA-related disruption?
- **Passenger Core (MCO/DEN)**:
  Airline Delay Severity.
  This asks: which airport is producing worse traveler-facing airline outcomes?

**How to read the ratio**
- A value above `1.0` means MCO is worse on that measure.
- A value below `1.0` means DEN is worse on that measure.
- A value close to `1.0` means they are performing similarly.

**Top-Line Verdict**
- The dashboard only gives a verdict when there is enough usable data.
- It combines the operational result and the passenger result.
- If there is not enough reliable data, the verdict is withheld instead of forcing an answer.

**Supporting Context**
- This table gives extra detail behind the verdict, such as average live aircraft count, average FAA downtime, airline flight counts, average airline delay, and cancellation rate.
- These numbers help explain the result, but they do not replace the main verdict.

### FAA Status History
This section looks only at FAA snapshots inside the selected time range.

- **Restriction Snapshot Rate**:
  The share of FAA snapshots that showed at least one active restriction.
  Example: if 40 out of 100 snapshots had a restriction, the rate is 40%.
- **Most Common Restriction**:
  The FAA status message that appeared most often.
- **Peak Active Restrictions**:
  The highest number of active FAA restrictions seen at one time.
- **Daily FAA Restriction Rate**:
  For each day, the percent of snapshots that had an FAA restriction.
- **Daily Peak Active FAA Restrictions**:
  For each day, the highest number of active restrictions seen.

### Airline Delay Impact
This section looks at airline delay records inside the selected time range.

- **Daily Airline Delay Severity Index**:
  The average airline severity score for each day.
- **Daily Longest Airline Delay**:
  A daily longest-delay trend based on the higher end of delays seen that day, so one extreme outlier does not dominate the chart.
- **Daily Airline Cancellation Rate Comparison**:
  The percent of sampled flights that were marked cancelled each day.
- **Longest Delay Today Comparison**:
  Compares today's longest airline delay with the longest delay ever recorded in the collected history.

### Delay Timing Breakdown
This section combines FAA delay minutes and airline delay minutes into one simple timing view.

- It groups delays by **day of week** using each airport's local time.
- It then shows the **average overall delay** for each weekday.
- This helps answer a simple question:
  which days tend to be worse for delays overall?

### Refresh timing
- FAA data updates about every 10 minutes.
- Traffic data updates about every 10 minutes.
- Airline data is more limited and may update less often.
- A manual sync can force a fresh airline pull, but normal airline calls are throttled to protect the API quota.
"""

HOW_TO_READ_MARKDOWN = """
This dashboard compares **MCO** and **DEN** to answer one simple question:
Is Orlando having worse delay problems than Denver, even after accounting for how busy each airport is?

**Start here**
- **Decision Summary**: This is the quickest read. It gives the main comparison and only shows a verdict when there is enough data.
- **Latest Airport Snapshot**: Shows what is happening right now at each airport.
- **FAA Status History** and **Airline Delay Impact**: These are more useful than a single snapshot if you want the bigger picture.

**What the main scores mean**
- **FAA Delay Severity**: How serious the FAA's current restrictions are. Higher means worse.
- **Airline Delay Severity**: A simple score based on delays, cancellations, and diversions. Higher means worse for travelers.
- **Operational Stress Score**: A combined pressure score based on airport busyness and FAA delay conditions. Higher means more strain.

**How to read the rest**
- **FAA Status History**: Shows how often each airport has FAA restrictions and how severe they are over time.
- **Airline Delay Impact**: Shows passenger-facing problems like longer delays and more cancellations.
- **Delay Timing Breakdown**: Shows which days tend to be worse.

**Quick rule of thumb**
- If **FAA downtime per 100 live aircraft** is higher, that airport is handling operations less efficiently.
- If **Airline Delay Severity** is higher, travelers are seeing worse outcomes.
- If both point in the same direction, that is stronger evidence. If they disagree, the result is mixed.

**Keep in mind**
- FAA and traffic data update about every 10 minutes.
- Airline data is slower and may refresh less often.
- One snapshot can be noisy, so trends matter more than any single moment.
"""
