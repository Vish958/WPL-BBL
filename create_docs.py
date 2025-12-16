import os

# The documentation content
docs_content = """# Technical Documentation: Score Prediction Algorithm
**Project:** Global T20 Dashboard
**Module:** Player Performance Analytics (Score Prediction)

---

## 1. Overview
The "Score Prediction" feature provides a projected run score for a batsman in their upcoming match. Instead of using a simple average (which treats all matches equally) or heavy Machine Learning models, this system uses a **Weighted Moving Average (WMA)** approach.

This method prioritizes **current form**, operating on the principle that a player's performance in recent matches is a stronger indicator of their next score than their performance months ago.

---

## 2. The Core Concept: Weighted Moving Average (WMA)
In a standard average, every match has equal importance (Weight = 1). In WMA, we assign specific "weights" (importance percentages) to innings based on recency.

- **Latest Match:** Highest Weight (Most Important)
- **Oldest Match:** Lowest Weight (Least Important)

### Why WMA?
1.  **Form Factor:** Captures "hot streaks" or "slumps" effectively.
2.  **Efficiency:** Extremely lightweight calculation that runs instantly without crashing limited RAM environments (e.g., Streamlit Free Tier).
3.  **Interpretability:** The logic is transparent and easy to explain to stakeholders.

---

## 3. Algorithm Breakdown

### Step 1: Data Selection
The system fetches the **last 5 innings** played by the selected batter, sorted chronologically from oldest to newest.

### Step 2: Weight Assignment
We assign a progressive weight distribution summing up to **1.0 (100%)**.

| Chronology      | Match Position | Weight Assigned | Importance   |
| :---            | :---           | :---            | :---         |
| **Oldest** | Match 1 (n-4)  | **0.10** (10%)  | Low          |
|                 | Match 2 (n-3)  | **0.15** (15%)  | Moderate-Low |
|                 | Match 3 (n-2)  | **0.20** (20%)  | Moderate     |
|                 | Match 4 (n-1)  | **0.25** (25%)  | High         |
| **Latest** | Match 5 (n)    | **0.30** (30%)  | **Highest** |

### Step 3: Calculation Formula
The Projected Score (P) is calculated as:

P = Sum( Score_i * Weight_i ) for i = 1 to 5

Where:
- Score_i  = Runs scored in the i-th match.
- Weight_i = Importance assigned to that match.

---

## 4. Practical Example
**Scenario:** A batter has scored the following runs in their last 5 innings:
**20, 40, 10, 80, 50** (Oldest -> Latest).

**Calculation:**

1.  **Match 1 (20 runs):** 20 * 0.10 = **2.0**
2.  **Match 2 (40 runs):** 40 * 0.15 = **6.0**
3.  **Match 3 (10 runs):** 10 * 0.20 = **2.0**
4.  **Match 4 (80 runs):** 80 * 0.25 = **20.0**
5.  **Match 5 (50 runs):** 50 * 0.30 = **15.0**

**Projected Score:** 2.0 + 6.0 + 2.0 + 20.0 + 15.0 = **45 Runs**

*Comparison:* A simple average would have been (20+40+10+80+50)/5 = **40**. The WMA projection is higher (**45**) because the batter performed significantly better in the most recent games.

---

## 5. Form Trend Analysis (Rising vs. Dipping)
The dashboard also displays a visual trend indicator. This is calculated by comparing the "Recent Average" against the "Old Average".

- **Recent Form:** Average of the last 2 matches.
- **Old Form:** Average of the first 2 matches (in the set of 5).

**Logic:**
- IF (Recent_Avg > Old_Avg) -> **Rising Trend (Graph Up)**
- ELSE -> **Dipping Trend (Graph Down)**

---

## 6. Limitations
- **Context Agnostic:** This mathematical model relies purely on run trends. It does not account for external factors such as pitch conditions, weather, or specific opposition bowlers.
- **Sample Size:** Requires a minimum of 5 recent matches for maximum accuracy. If fewer matches are available, the system reverts to a simple average.
"""

# Write to file
filename = "Score_Prediction_Logic.md"
with open(filename, "w", encoding="utf-8") as f:
    f.write(docs_content)

print(f"✅ File '{filename}' created successfully! You can now share this file.")