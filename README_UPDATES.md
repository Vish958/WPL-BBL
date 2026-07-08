# Data Ingestion & Player Name Normalization Updates
**Date: July 8, 2026**

This document summarizes the recent updates made to resolve player name mapping issues and automate ingestion tracking reports across the project.

---

## 1. Unified Player Name Normalization
To prevent statistics for the same player from being split across multiple spelling variations (e.g., `PW Hasaranga` vs. `PWH de Silva` in Men's T20I), we implemented a unified name mapping system.

### Key Components:
1. **Central Mapping File ([player_name_map.json](file:///Users/vishwesh/Documents/WPL&BBL/player_name_map.json)):**
   - Serves as the single source of truth for player spelling corrections.
   - Example mappings include Wanindu Hasaranga's variations, Sciver-Brunt, and others:
     ```json
     {
       "PWH de Silva": "PW Hasaranga",
       "Pinnaduwage Wanindu Hasaranga de Silva": "PW Hasaranga",
       "NR Sciver": "NR Sciver-Brunt"
     }
     ```

2. **In-Pipeline Hardening (Preprocessing):**
   - Player names are mapped at ingestion inside:
     * [preprocessing.py](file:///Users/vishwesh/Documents/WPL&BBL/preprocessing.py) (for deliveries and playing XI statistics)
     * [preprocessing_with_drs.py](file:///Users/vishwesh/Documents/WPL&BBL/preprocessing_with_drs.py) (for deliveries, reviews, and impact players)
     * [preprocessing_local_t20.py](file:///Users/vishwesh/Documents/WPL&BBL/preprocessing_local_t20.py) (for local leagues: UPT20, DPL, MPL, JPL, Maharaja T20, TG20)
   - Normalizing names inside the Parquet files guarantees consistent statistics at database level.

3. **Dynamic Cache Hot-Fixing (Streamlit Apps):**
   - The `load_data()` functions inside the main Streamlit apps load `player_name_map.json` at runtime.
   - If a new variant is found, adding it to the JSON file immediately corrects the UI statistics without requiring a database rebuild.

---

## 2. Automated Excel Match Ingestion Summary
To make it easy to see which matches have been successfully ingested and which matches were skipped (e.g., matches before the league's designated start dates), the preprocessors now automatically generate tracking reports.

### Generated Reports:
- **`match_ingestion_summary.xlsx`:** Created automatically by `preprocessing.py` and `preprocessing_with_drs.py`.
- **`local_match_ingestion_summary.xlsx`:** Created automatically by `preprocessing_local_t20.py`.

### Report Structure:
1. **Sheet 1: `League Summary`**
   - Lists each league with total JSON files scanned, total matches successfully imported, and the earliest/latest match dates in the dataset.
2. **Sheet 2: `Excluded Matches`**
   - Lists every file that was scanned but skipped, detailing the Match ID, File Name, League, Date, and specific Reason for Exclusion (e.g., `"Skip: Before League Start Date (2020-01-01)"`).

---

## 3. How to Update Data in the Future
When you add new match JSON files:

1. **Add new files** to their respective raw folders.
2. **(Optional) Add new player name fixes** in [player_name_map.json](file:///Users/vishwesh/Documents/WPL&BBL/player_name_map.json) if duplicate player entries appear in the app.
3. **Re-run the preprocessing pipelines** from your terminal:
   ```bash
   python preprocessing.py
   python preprocessing_with_drs.py
   python preprocessing_local_t20.py
   ```
4. **Open the generated Excel reports** (`match_ingestion_summary.xlsx` and `local_match_ingestion_summary.xlsx`) to visually verify that all new matches were imported successfully!
