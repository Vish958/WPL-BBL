# 🏏 Batting Order Performance (Team-wise) Metric

## Overview
A new comprehensive metric to analyze team batting performance by player position (1-11) with year-wise comparison capabilities, similar to the SR Comparison (Year-wise) metric.

## Features

### 1. **Two View Modes**
   - **Year-wise Comparison**: Compare performance across multiple seasons with detailed breakdowns
   - **Overall (All Seasons)**: Aggregate statistics across all seasons for cumulative performance analysis

### 2. **Filtering Options**
   - **Team Selection**: Choose one or multiple teams
   - **League Selection**: Filter by specific league(s)

### 3. **Metrics Calculated by Position**
For each batting position (1-11), the metric provides:
- **Innings**: Number of innings where the position was batted
- **Runs**: Total runs scored at this position
- **Balls**: Balls faced at this position
- **SR (Strike Rate)**: Runs per 100 balls
- **Avg**: Average runs per innings
- **Fours**: Total boundaries of 4 runs
- **Sixes**: Total boundaries of 6 runs
- **25+**: Number of innings with 25+ runs
- **50+**: Number of 50-run milestones
- **100+**: Number of centuries (100+ runs)

### 4. **Visualizations**

#### Year-wise View (Single Year)
- **Data Table**: Detailed stats for all teams and positions
- **Heatmap**: Runs scored by each team at each batting position (visual pattern recognition)
- **Bar Chart**: Average Strike Rate by position with color intensity for total runs

#### Year-wise View (Multiple Years)
- **Individual Year Tabs**: Separate tables for each selected season
- **Comparison Tab**: Shows metrics for each position across years with trend lines

#### Overall View
- **Aggregate Table**: Combined statistics across all seasons
- **Overall Heatmap**: Total runs at each position for each team
- **Position Analysis**: Average SR and performance metrics by position

### 5. **Key Insights**
The metric helps answer questions like:
- Which batting positions contribute most to team scores?
- How has a team's batting order performance evolved year-over-year?
- Which positions have the highest strike rates?
- How consistent are teams at specific batting positions?
- Are there trends in position-wise performance across seasons?

## Usage

1. Navigate to "Batting Order Performance (Team-wise)" from the metric selection
2. Choose your **View Mode** (Year-wise or Overall)
3. Select **Team(s)** you want to analyze
4. Select **League(s)** for filtering
5. For Year-wise view, select one or more seasons:
   - **Single Year**: Shows table + heatmap + SR chart
   - **Multiple Years**: Shows individual year tabs + comparison trends
6. Explore tables, charts, and heatmaps to identify patterns

## Example Questions Answered

- "How did Mumbai Indians' number 3 position evolve from 2024 to 2026?"
- "Which team has the best strike rate at position 5?"
- "How many 50+ scores did Chennai Super Kings' opening pair contribute?"
- "What's the average runs per innings for position 7 across all WPL seasons?"

## Data Notes

- Only valid innings (1st and 2nd innings, no walkovers/no-results) are included
- Wides are excluded from balls faced calculation (follows cricket statistics convention)
- Dismissals are counted for average calculations
- Strike rates are calculated from all deliveries except wides
- Milestones count per-innings performances at each position

## Technical Details

- **Functions**: `compute_batting_positions_bo()`, `batting_order_stats()`
- **Caching**: Batting positions computed with streamlit caching for performance
- **Data Processing**: Handles multiple leagues and team filters efficiently
- **Visualizations**: Uses Plotly for interactive charts and heatmaps

## Related Metrics

This metric complements:
- SR Comparison (Year-wise) - Individual batter performance
- Powerplay Score Tracker - Phase-specific analysis
- Over-by-Over Analysis - Inning progression

---

**Created**: April 17, 2026
**Version**: 1.0
