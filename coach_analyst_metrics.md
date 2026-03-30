# Coach and Analyst Metrics

The following metrics are designed specifically for coaches and performance analysts to derive actionable insights from match data. They go beyond standard averages and strike rates to measure true match impact, contextual performance, and specific player roles.

## 1. Inverse Pressure Index (IPI)

**Definition:**
Evaluates a player's ability to perform in "clutch" situations by assigning a higher value to runs scored when a team is under pressure (i.e., when multiple wickets have fallen). 

**Calculation:**
*   For each delivery, a multiplier is applied based on the number of wickets that have fallen and the Current Run Rate (CRR).
    *   `Pressure Points = Runs Scored × (1 + Wickets Fallen × 0.5) × (8.0 / Smoothed CRR)`
    *   The wickets fallen multiplier is dampened (× 0.5) to avoid over-rewarding tailenders who only face a few balls at the death.
*   **Pressure Index** = `(Total Pressure Points / Total Balls Faced) × log10(Runs + 10)`
    *   The formula uses a volume-weighted average to reward batsmen who stay on the pitch, ensuring that an opener anchoring the innings is not overshadowed by a lower-order batsman hitting a single six.
*   **Clutch Score:** The Pressure Index normalized to a 1–10 scale.

**Scouting Tags (Context-Aware):**
*   **Match Winner (Score > 8.0):** Outstanding clutch performer; stands tall during collapses.
*   **Crisis Manager (Score 6.0-8.0):** Steady under pressure; holds the innings together.
*   **Handy Cameo / Lower Order:** Assigned to players who score < 10 runs and face < 6 balls, acknowledging their limited opportunity.
*   **Tempo Setter:** Assigned to players who maintain a high Strike Rate (> 140) over at least 10 balls, driving the innings momentum.
*   **Anchor / Accumulator:** Assigned to top-order or steady players who face > 15 balls, laying a solid foundation.
*   **Role Player:** Assigned when no extreme criteria are met, representing a standard contribution.

---

## 2. Batting Acceleration Rate (BAR)

**Definition:**
Measures how a batter’s scoring rate changes as the innings progresses, specifically comparing their Death Overs Strike Rate to their Powerplay Strike Rate.

**Calculation:**
*   `BAR = Death_SR - Powerplay_SR`
*   Only considers batters who have faced balls in at least two different phases and a minimum of 10 total balls.

**Scouting Labels (Player DNA):**
*   **The Finisher (BAR > 20):** Accelerates heavily at the death. Ideal for No. 4/5 roles.
*   **The Engine (-10 ≤ BAR ≤ 5):** Consistent tempo across phases. Ideal No. 3 anchor.
*   **PP Specialist (BAR < -10):** Dominates the Powerplay but decelerates later. Best as an opener.
*   **Balanced:** Falls outside the above extremes, adapting to situations.

---

## 3. Bowling Spell Efficiency

**Definition:**
Analyzes a bowler's effectiveness during continuous stints rather than looking at an aggregated match total. 

**Calculation:**
*   Deliveries are grouped into "spells". A spell is continuous as long as the gap between overs bowled by the same bowler is $\le 2$ overs.
*   For each multi-over spell (minimum 2 overs), the metric calculates:
    *   **Total Runs Conceded** (excluding byes and leg-byes)
    *   **Wickets Taken**
    *   **Dot balls** and **Dot Ball %**
    *   **Economy Rate** = `Runs / (Balls / 6)`
*   **Coaching Application:** Helps determine if a bowler is more effective bowling in long, continuous blocks (e.g., 3-over spells) or when broken up into 1-over spells. High dot % and low economy indicate pressure-building spells.

---

## 4. Collapse Detector

**Definition:**
Automatically identifies fatal batting collapses, pinpointing exactly when and how a team lost momentum.

**Calculation:**
*   Uses a sliding window approach across ball-by-ball data.
*   A collapse is defined as **3 or more wickets falling within a span of 24 legal deliveries (~4 overs).**
*   Calculates:
    *   `Runs Lost` during the collapse window.
    *   `Over Range` of the collapse.
    *   The `Bowlers` involved in triggering the collapse.
*   **Coaching Application:** Highlights "collapse-prone" teams that need to stabilize their middle order and identifies "trigger" bowlers who have a knack for taking wickets in clusters.

---

## 5. Player Absence Impact (PAI)

**Definition:**
Quantifies a player's true value to their team by comparing the team's performance *with* the player in the Playing XI versus *without* them.

**Calculation:**
*   Requires minimum criteria (e.g., played $\ge 5$ matches and missed $\ge 3$ matches).
*   Excluded "No Result" and abandoned matches.
*   **Win% Δ:** `Team Win% (With Player) - Team Win% (Without Player)`
*   **Run Rate Δ:** `Team Avg RR (With Player) - Team Avg RR (Without Player)`
*   **Impact Score:** `Win% Δ + (Run Rate Δ × 5)`
*   **Coaching Application:** Identifies highly impactful, almost "irreplaceable" players based on how heavily the team's metrics drop in their absence.

---

## 6. Match-Up Dominance Score (MDS)

**Definition:**
Evaluates specific Batter vs. Bowler match-ups by comparing how well a batter scores against a specific bowler relative to their overall season standard.

**Calculation:**
*   `MDS = Strike Rate vs Bowler - Season Strike Rate`
*   **Positive MDS:** Batter dominates this bowler relative to their normal scoring rate.
*   **Negative MDS:** Batter struggles against this bowler, scoring much slower than usual.
*   **Coaching Application:** Highly actionable for captains. If a batter has a deeply negative MDS against a specific bowler, that bowler should be brought into the attack immediately when the batter arrives at the crease.
