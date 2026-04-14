# powerplay_drs_metrics.py
# New metrics file for Powerplay Score Tracker and DRS Analysis
# By Vishwesh Gaur

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

st.set_page_config(page_title="Powerplay & DRS Metrics", layout="wide")

st.markdown("# Powerplay Score Tracker & DRS Analysis")
st.markdown("**By Vishwesh Gaur** [Twitter: @iumvishwesh](https://twitter.com/iumvishwesh)")
st.markdown("📅 Last updated: 14 April 2026")

DATA_SOURCE = "t20_data_with_drs.parquet"  # Updated to include DRS data
JSON_DIR = "data"  # Directory containing JSON files

# Force clear cache on startup to ensure new player matching logic is used
# Remove this after confirming the fix works
st.cache_data.clear()

@st.cache_data
def load_venue_data():
    """Load venue data from JSON files and create a match_id -> venue mapping."""
    import os
    from glob import glob
    import json
    
    venue_map = {}
    files = glob(os.path.join(JSON_DIR, "*.json"))
    
    for file in files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            match_id = os.path.basename(file).split('.')[0]
            venue = data.get('info', {}).get('venue', 'Unknown')
            city = data.get('info', {}).get('city', 'Unknown')
            venue_map[match_id] = {'venue': venue, 'city': city}
        except Exception:
            continue
    
    return venue_map

@st.cache_data(ttl=3600)  # 1 hour TTL
def load_data(path=DATA_SOURCE, _cache_version=6):  # Version 6: Added event_stage column for playoff filtering
    try:
        df = pd.read_parquet(path)
        
        # Memory optimization
        if 'phase' in df.columns:
            df['phase'] = df['phase'].astype(str).str.strip().apply(lambda x: x.title().replace('Power Play','Powerplay'))
        
        cat_cols = ['league', 'season', 'phase', 'team', 'batter', 'bowler', 'teams', 'venue', 'match_id']
        for col in df.columns:
            if col in cat_cols or df[col].dtype == 'object':
                if df[col].nunique() < (len(df) * 0.5):
                    df[col] = df[col].astype('category')
        
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        return df
    except Exception as e:
        st.error(f"Data not found or failed to load: {e}")
        return pd.DataFrame()

# =========================================
# PLAYER DATA LOADING (FOR PACE/SPIN & BATTING HAND)
# =========================================
PACE_KEYWORDS = ['fast', 'medium', 'pace']
SPIN_KEYWORDS = ['offbreak', 'legbreak', 'orthodox', 'wrist-spin', 'slow']

def classify_bowling_type(style):
    """Classify bowling style as Pace, Spin, or Unknown"""
    if pd.isna(style):
        return 'Unknown'
    style_lower = str(style).lower()
    # Check for pace keywords first (medium can be in spin names too)
    if any(kw in style_lower for kw in ['fast', 'medium-fast', 'medium']):
        if 'offbreak' not in style_lower and 'legbreak' not in style_lower and 'orthodox' not in style_lower:
            return 'Pace'
    if any(kw in style_lower for kw in SPIN_KEYWORDS):
        return 'Spin'
    if 'medium' in style_lower:
        return 'Pace'
    return 'Unknown'

@st.cache_data(ttl=3600)  # Cache for 1 hour, will refresh on restart
def load_player_data(_cache_version=9):  # Version 9: Fixed batting_hand KeyError in manual overrides
    """
    Load player data from WPL and IPL Excel files for mapping bowling type and batting hand.
    Creates multiple index keys to handle name format differences:
    - Full name (lowercase): "meg lanning"
    - Last name only: "lanning"
    - First initial + last name: "m lanning" (to match "MM Lanning" -> "M Lanning")
    - Initials pattern: "mm lanning" (to handle abbreviated names)
    """
    import os
    player_data = {}
    errors = []
    
    # Try multiple ways to find the base directory
    possible_dirs = [
        os.getcwd(),  # Current working directory (where streamlit is run from)
        os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else None,
        '/Users/vishwesh/Documents/WPL&BBL',  # Fallback hardcoded path
    ]
    
    base_dir = None
    for d in possible_dirs:
        if d and os.path.exists(os.path.join(d, 'WPL Players.xlsx')):
            base_dir = d
            break
    
    if not base_dir:
        errors.append(f"Could not find Excel files in any of: {possible_dirs}")
        return player_data  # Return empty
    
    def add_player_entry(name, batting_hand, bowling_style, player_data_dict):
        """Add a player with multiple name variations for matching."""
        name = str(name).strip()
        if not name or name.lower() == 'nan':
            return
            
        entry = {
            'batting_hand': batting_hand if pd.notna(batting_hand) else 'Unknown',
            'bowling_type': classify_bowling_type(bowling_style),
            'full_name': name
        }
        
        # Key 1: Full name lowercase (e.g., "meg lanning")
        player_data_dict[name.lower()] = entry
        
        parts = name.split()
        if len(parts) >= 2:
            first_name = parts[0]
            last_name = parts[-1]
            
            # Key 2: Last name only (e.g., "lanning")
            # Only add if not already present (avoid overwriting)
            if last_name.lower() not in player_data_dict:
                player_data_dict[last_name.lower()] = entry
            
            # Key 3: First initial + last name (e.g., "m lanning")
            # Only add if not already present (avoid IPL overwriting WPL)
            first_initial = first_name[0].lower()
            initial_key = f"{first_initial} {last_name.lower()}"
            if initial_key not in player_data_dict:
                player_data_dict[initial_key] = entry
            
            # Key 4: Double initial + last name (handle "MM Lanning" format)
            # Common in cricket data where player has middle name initial
            double_initial_key = f"{first_initial}{first_initial} {last_name.lower()}"
            if double_initial_key not in player_data_dict:
                player_data_dict[double_initial_key] = entry
            
            # Key 5: First initial only (no space, e.g., "mlanning")
            no_space_key = f"{first_initial}{last_name.lower()}"
            if no_space_key not in player_data_dict:
                player_data_dict[no_space_key] = entry
            
        elif len(parts) == 1:
            # Single name player (e.g., "Harmanpreet")
            player_data_dict[parts[0].lower()] = entry
    
    try:
        # Load WPL players
        wpl_path = os.path.join(base_dir, 'WPL Players.xlsx')
        wpl_df = pd.read_excel(wpl_path, engine='openpyxl')
        for _, row in wpl_df.iterrows():
            add_player_entry(
                row['Name'],
                row.get('Batting Styles'),
                row.get('Bowling Styles'),
                player_data
            )
    except Exception as e:
        errors.append(f"WPL load error: {e}")
    
    try:
        # Load IPL players
        ipl_path = os.path.join(base_dir, 'IPL Player.xlsx')
        ipl_df = pd.read_excel(ipl_path, engine='openpyxl')
        for _, row in ipl_df.iterrows():
            add_player_entry(
                row['Name'],
                row.get('Batting Styles'),
                row.get('Bowling Styles'),
                player_data
            )
    except Exception as e:
        errors.append(f"IPL load error: {e}")
    
    
    # Manual overrides for players with name variations between JSON and Excel
    # K Goud (JSON) = Kranti Gaud (Excel) - Pace bowler (right-arm medium-fast)
    # S Asha (JSON) = Asha Sobhana (Excel) - Spin bowler (legbreak googly)
    manual_overrides = {
        # K Goud -> Kranti Gaud (Pace)
        'k goud': {'bowling_type': 'Pace', 'full_name': 'Kranti Gaud', 'batting_hand': 'Unknown'},
        'kgoud': {'bowling_type': 'Pace', 'full_name': 'Kranti Gaud', 'batting_hand': 'Unknown'},
        'goud': {'bowling_type': 'Pace', 'full_name': 'Kranti Gaud', 'batting_hand': 'Unknown'},  
        'k gaud': {'bowling_type': 'Pace', 'full_name': 'Kranti Gaud', 'batting_hand': 'Unknown'},
        'kgaud': {'bowling_type': 'Pace', 'full_name': 'Kranti Gaud', 'batting_hand': 'Unknown'},
        # S Asha -> Asha Sobhana (Spin)
        's asha': {'bowling_type': 'Spin', 'full_name': 'Asha Sobhana', 'batting_hand': 'Unknown'},
        'sasha': {'bowling_type': 'Spin', 'full_name': 'Asha Sobhana', 'batting_hand': 'Unknown'},
        # Add full Asha Sobhana variations too (prioritize over "asha" key from Excel)
        'asha sobhana': {'bowling_type': 'Spin', 'full_name': 'Asha Sobhana', 'batting_hand': 'Unknown'},
        'a sobhana': {'bowling_type': 'Spin', 'full_name': 'Asha Sobhana', 'batting_hand': 'Unknown'},
    }
    for key, value in manual_overrides.items():
        if key not in player_data:
            player_data[key] = value
    
    # Store errors for debugging (can be accessed if needed)
    if errors:
        player_data['_errors'] = errors
    
    return player_data

def normalize_player_name(name):
    """
    Normalize a player name from parquet format to matchable format.
    Handles: "MM Lanning" -> "m lanning", "Shafali Verma" -> "shafali verma"
    """
    if pd.isna(name):
        return None
    name = str(name).strip().lower()
    parts = name.split()
    if len(parts) >= 2:
        first_part = parts[0]
        last_name = parts[-1]
        # Check if first part looks like initials (all caps pattern, 1-3 chars)
        if len(first_part) <= 3 and first_part.replace('-', '').isalpha():
            # It's likely initials like "mm", "nm", "ac"
            first_initial = first_part[0]
            return [
                name,  # Original: "mm lanning"
                f"{first_initial} {last_name}",  # "m lanning"
                f"{first_initial}{last_name}",  # "mlanning"
                last_name  # Just last name
            ]
        else:
            # Full first name like "shafali"
            first_initial = first_part[0]
            return [
                name,  # Original
                f"{first_initial} {last_name}",  # Initial + last
                f"{first_part[0]}{first_part[0]} {last_name}",  # Double initial
                last_name
            ]
    return [name]

def get_player_bowling_type(player_name, player_data_cache):
    """Get bowling type (Pace/Spin) for a player"""
    if pd.isna(player_name):
        return 'Unknown'
    
    # Try all normalized name variations
    name_variations = normalize_player_name(player_name)
    if not name_variations:
        return 'Unknown'
    
    for name_key in name_variations:
        if name_key in player_data_cache:
            return player_data_cache[name_key]['bowling_type']
    
    return 'Unknown'

def get_player_batting_hand(player_name, player_data_cache):
    """Get batting hand (left/right) for a player"""
    if pd.isna(player_name):
        return 'Unknown'
    
    # Try all normalized name variations
    name_variations = normalize_player_name(player_name)
    if not name_variations:
        return 'Unknown'
    
    for name_key in name_variations:
        if name_key in player_data_cache:
            hand = player_data_cache[name_key]['batting_hand']
            if pd.notna(hand):
                hand_str = str(hand).lower()
                if 'left' in hand_str:
                    return 'Left'
                elif 'right' in hand_str:
                    return 'Right'
    
    return 'Unknown'

df = load_data(_cache_version=6)  # Version 6: Added event_stage column for playoff filtering
if df.empty:
    st.stop()

# Load and merge venue data
venue_map = load_venue_data()
if venue_map:
    df['venue'] = df['match_id'].astype(str).map(lambda x: venue_map.get(x, {}).get('venue', 'Unknown'))
    df['city'] = df['match_id'].astype(str).map(lambda x: venue_map.get(x, {}).get('city', 'Unknown'))

# Load player data for pace/spin and batting hand mapping
player_data_cache = load_player_data(_cache_version=9)
if player_data_cache:
    st.sidebar.caption(f"📊 Player mappings: {len(player_data_cache)} entries loaded")

# Sidebar Filters
st.sidebar.header("Filters")

leagues = sorted(df['league'].dropna().unique())
selected_leagues = st.sidebar.multiselect("League", leagues)

years = sorted(df['year'].dropna().unique())
selected_years = st.sidebar.multiselect("Year", years)

# Apply filters
fdf = df.copy()
if selected_leagues:
    fdf = fdf[fdf['league'].isin(selected_leagues)]
if selected_years:
    fdf = fdf[fdf['year'].isin(selected_years)]

# Keep a copy before team filter (for metrics that need cross-team aggregation)
fdf_no_team = fdf.copy()

# Team filter (after league/year filtering)
teams_available = sorted(fdf['team'].dropna().unique())
selected_teams = st.sidebar.multiselect("Team", teams_available)
if selected_teams:
    fdf = fdf[fdf['team'].isin(selected_teams)]

# Metric selection
st.sidebar.markdown("---")
metric_choice = st.sidebar.radio("Select Metric", [
    "Powerplay Score Tracker", 
    "DRS Analysis",
    "Over-by-Over Analysis",
    "Batter vs Bowler Matchup",
    "Extras Impact Index (Bowler)",
    "Overall Extras Summary",
    "Most Wickets in an Over",
    "Left-Right Hand Index",
    "Pace vs Spin Analysis",
    "Super Over Analysis",
    "Innings Progression",
    "Franchise Debut Tracker",
    "SR Comparison (Year-wise)",
    "Fastest 50s & 100s (Player)",
    "Fastest Team 50 & 100",
    "Bowler First Spell Wickets",
    "Back-to-Back 25+ Scores",
    "Boundary-less Overs Spell",
    "Boundary-less Ball Streak",
    "On This Day",
    "Bowler Over Impact",
    "Match Flow Chart",
    "Extra Deliveries Cost",
    "Debutant Bowler Wickets",
    "Longest Wicketless Streaks",
    "Balls Bowled Per Match"
])

if fdf.empty:
    st.warning("No data for selected filters.")
    st.stop()

# =========================================
# POWERPLAY SCORE TRACKER
# =========================================
def powerplay_score_tracker(df_, mode='batting', filter_teams=None):
    """
    Track powerplay scores for each inning/team across matches.
    mode: 'batting' - when team is batting in powerplay
          'bowling' - when team is bowling in powerplay (shows runs conceded)
    filter_teams: list of teams to filter (applies to batting team in batting mode,
                  bowling team in bowling mode)
    """
    pp = df_[df_['phase'] == 'Powerplay'].copy()
    if pp.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # Exclude super over innings (innings 3, 4, etc.)
    pp = pp[pp['innings'].isin([1, 2])]
    if pp.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # Helper to get opponent
    def get_opponent_team(teams_str, my_team):
        parts = str(teams_str).replace(' vs ', ' v ').split(' v ')
        if len(parts) == 2:
            return parts[1].strip() if parts[0].strip() == my_team else parts[0].strip()
        return 'N/A'
    
    # Add bowling_team column (opponent of batting team)
    pp['bowling_team'] = pp.apply(lambda row: get_opponent_team(row['teams'], str(row['team'])), axis=1)

    # Ensure wicket_kind exists as a plain string column for aggregation.
    # If absent (older parquet), synthesise it from wicket_count so lambdas always work.
    _WK_NULL = {'nan', 'None', '<NA>', ''}
    if 'wicket_kind' in pp.columns:
        pp['wicket_kind'] = pp['wicket_kind'].astype(str)
    else:
        # Synthetic fallback: use team_wicket_count (includes run-outs) if available,
        # otherwise fall back to wicket_count (bowler wickets only).
        _wk_col = 'team_wicket_count' if 'team_wicket_count' in pp.columns else 'wicket_count'
        pp['wicket_kind'] = pp[_wk_col].apply(lambda v: 'Wicket' if v > 0 else 'nan')

    if mode == 'batting':
        grp = pp.groupby(['match_id', 'team', 'innings', 'date', 'year', 'teams'], observed=True)
        
        stats = grp.agg(
            PP_Runs=('runs.total', 'sum'),
            PP_Balls=('is_valid_delivery', 'sum'),
            PP_4s=('runs.batter', lambda x: (x == 4).sum()),
            PP_6s=('runs.batter', lambda x: (x == 6).sum()),
            PP_Dots=('runs.batter', lambda x: ((x == 0) & (pp.loc[x.index, 'is_valid_delivery'] == 1)).sum()),
            PP_Wickets=('wicket_kind', lambda x: (~x.isin(_WK_NULL)).sum())  # all dismissals incl. run out
        ).reset_index()
        
        stats['PP_RR'] = (stats['PP_Runs'] / (stats['PP_Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
        stats['PP_Boundaries'] = stats['PP_4s'] + stats['PP_6s']
        stats['PP_Dot%'] = (stats['PP_Dots'] / stats['PP_Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
        
        def get_opponent(row):
            teams_str = str(row['teams'])
            team = str(row['team'])
            parts = teams_str.replace(' vs ', ' v ').split(' v ')
            if len(parts) == 2:
                return parts[1].strip() if parts[0].strip() == team else parts[0].strip()
            return 'N/A'
        
        stats['Opponent'] = stats.apply(get_opponent, axis=1)
        stats['Date'] = pd.to_datetime(stats['date']).dt.date
        stats['Innings'] = stats['innings'].map({1: '1st', 2: '2nd'})
        
        match_stats = stats[['team', 'Opponent', 'Date', 'year', 'Innings', 'PP_Runs', 'PP_Balls', 
                             'PP_RR', 'PP_Boundaries', 'PP_4s', 'PP_6s', 'PP_Dot%', 'PP_Wickets', 'match_id']].copy()
        match_stats = match_stats.rename(columns={'team': 'Team', 'year': 'Season'})
        match_stats = match_stats.sort_values('Date', ascending=False)
        
    else:  # bowling mode - filter by BOWLING team (not batting team)
        # For bowling, filter by bowling_team if filter_teams provided
        if filter_teams:
            pp = pp[pp['bowling_team'].isin(filter_teams)]
            if pp.empty:
                return pd.DataFrame(), pd.DataFrame()
        
        # Group by BOWLING TEAM to show runs they conceded
        grp = pp.groupby(['match_id', 'bowling_team', 'team', 'innings', 'date', 'year', 'teams'], observed=True)
        
        stats = grp.agg(
            PP_Runs_Conceded=('runs.total', 'sum'),
            PP_Balls_Bowled=('is_valid_delivery', 'sum'),
            PP_4s_Conceded=('runs.batter', lambda x: (x == 4).sum()),
            PP_6s_Conceded=('runs.batter', lambda x: (x == 6).sum()),
            PP_Dots_Bowled=('runs.batter', lambda x: ((x == 0) & (pp.loc[x.index, 'is_valid_delivery'] == 1)).sum()),
            PP_Wickets_Taken=('wicket_kind', lambda x: (~x.isin(_WK_NULL)).sum()),  # all dismissals incl. run out
            PP_Wicket_Types=('wicket_kind', lambda x: ', '.join(
                f"{str(k).title()}({v})" for k, v in x[~x.isin(_WK_NULL)].value_counts().items()
            ) if (~x.isin(_WK_NULL)).any() else '')
        ).reset_index()
        
        stats['PP_Econ'] = (stats['PP_Runs_Conceded'] / (stats['PP_Balls_Bowled'] / 6)).replace([np.inf, np.nan], 0).round(2)
        stats['PP_Boundaries_Conceded'] = stats['PP_4s_Conceded'] + stats['PP_6s_Conceded']
        stats['PP_Dot%'] = (stats['PP_Dots_Bowled'] / stats['PP_Balls_Bowled'] * 100).replace([np.inf, np.nan], 0).round(2)
        
        # 'team' is batting team = Against, 'bowling_team' is the team we want
        stats['Against'] = stats['team']
        stats['Date'] = pd.to_datetime(stats['date']).dt.date
        stats['Innings'] = stats['innings'].map({1: '1st Inns', 2: '2nd Inns'})
        
        match_stats = stats[['bowling_team', 'Against', 'Date', 'year', 'Innings', 'PP_Runs_Conceded', 
                             'PP_Balls_Bowled', 'PP_Econ', 'PP_Boundaries_Conceded', 'PP_Dot%', 
                             'PP_Wickets_Taken', 'PP_Wicket_Types', 'match_id']].copy()
        match_stats = match_stats.rename(columns={'bowling_team': 'Team', 'year': 'Season'})
        match_stats = match_stats.sort_values('Date', ascending=False)
    
    # Season summary
    if mode == 'batting':
        season_summary = match_stats.groupby(['Team', 'Season'], observed=True).agg(
            Matches=('match_id', 'nunique'),
            Avg_PP_Runs=('PP_Runs', 'mean'),
            Best_PP=('PP_Runs', 'max'),
            Worst_PP=('PP_Runs', 'min'),
            Total_PP_Runs=('PP_Runs', 'sum'),
            Avg_PP_RR=('PP_RR', 'mean'),
            Total_Boundaries=('PP_Boundaries', 'sum')
        ).reset_index()
        season_summary['Avg_PP_Runs'] = season_summary['Avg_PP_Runs'].round(1)
        season_summary['Avg_PP_RR'] = season_summary['Avg_PP_RR'].round(2)
    else:
        season_summary = match_stats.groupby(['Team', 'Season'], observed=True).agg(
            Matches=('match_id', 'nunique'),
            Avg_Runs_Conceded=('PP_Runs_Conceded', 'mean'),
            Best_PP_Bowling=('PP_Runs_Conceded', 'min'),
            Worst_PP_Bowling=('PP_Runs_Conceded', 'max'),
            Total_Wickets=('PP_Wickets_Taken', 'sum'),
            Avg_Econ=('PP_Econ', 'mean')
        ).reset_index()
        season_summary['Avg_Runs_Conceded'] = season_summary['Avg_Runs_Conceded'].round(1)
        season_summary['Avg_Econ'] = season_summary['Avg_Econ'].round(2)
    
    return match_stats, season_summary


# =========================================
# DRS ANALYSIS (requires DRS data in parquet)
# =========================================
def drs_success_rate(df_):
    """
    Calculate DRS success rate by team.
    Requires 'has_review', 'review_by_team', 'review_decision' columns.
    """
    if 'has_review' not in df_.columns or 'review_by_team' not in df_.columns:
        return pd.DataFrame()
    
    reviews = df_[df_['has_review'] == 1].copy()
    if reviews.empty:
        return pd.DataFrame()
    
    # Calculate success rate by team
    stats = reviews.groupby(['review_by_team', 'year'], observed=True).agg(
        Total_Reviews=('has_review', 'count'),
        Successful=('review_decision', lambda x: (x == 'struck down').sum()),
        Failed=('review_decision', lambda x: (x == 'upheld').sum()),
        Umpires_Call=('umpires_call', lambda x: (x == True).sum() if 'umpires_call' in reviews.columns else 0)
    ).reset_index()
    
    stats['Success_Rate'] = (stats['Successful'] / stats['Total_Reviews'] * 100).round(1)
    stats['Reviews_Lost'] = stats['Failed']
    stats = stats.rename(columns={'review_by_team': 'Team', 'year': 'Season'})
    
    return stats[['Team', 'Season', 'Total_Reviews', 'Successful', 'Reviews_Lost', 'Success_Rate', 'Umpires_Call']]


def drs_reviews_lost(df_):
    """
    Count reviews lost (failed) by team
    """
    if 'has_review' not in df_.columns or 'review_decision' not in df_.columns:
        return pd.DataFrame()
    
    reviews = df_[df_['has_review'] == 1].copy()
    if reviews.empty:
        return pd.DataFrame()
    
    # Only count failed reviews
    failed = reviews[reviews['review_decision'] == 'upheld']
    
    stats = failed.groupby(['review_by_team', 'year', 'match_id', 'teams'], observed=True).size().reset_index(name='Reviews_Lost')
    stats = stats.rename(columns={'review_by_team': 'Team', 'year': 'Season', 'teams': 'Match'})
    
    # Add date if available
    if 'date' in df_.columns:
        date_map = df_.groupby('match_id')['date'].first().to_dict()
        stats['Date'] = stats['match_id'].map(date_map)
        stats['Date'] = pd.to_datetime(stats['Date']).dt.date
        stats = stats.sort_values('Date', ascending=False)
    
    return stats[['Team', 'Match', 'Date', 'Season', 'Reviews_Lost']] if 'Date' in stats.columns else stats[['Team', 'Match', 'Season', 'Reviews_Lost']]


def yearwise_batter_sr_comparison(df_, aggregate_across_teams=True, min_balls=20, include_year=True):
    """
    Year-wise batter SR comparison with ball-range SR buckets.
    Columns:
    Name | Average | Strike Rate | Balls/Inn | 1-10 SR | 11-20 SR | ... | 51-60 SR
    When include_year=False, aggregates across all seasons (no Season column).
    """
    if df_.empty:
        return pd.DataFrame()

    required_cols = {'league', 'year', 'match_id', 'innings', 'team', 'batter', 'runs.batter', 'is_valid_delivery', 'over'}
    if not required_cols.issubset(df_.columns):
        return pd.DataFrame()

    work_df = df_[df_['innings'].isin([1, 2])].copy()
    if work_df.empty:
        return pd.DataFrame()

    # Exclude no-result matches (abandoned/rain) — ESPN/ICC convention: these innings don't
    # count towards averages or innings-played totals.
    # Specifically: for no-result matches (winner=None), only keep innings that were completed
    # (all 20 overs bowled, i.e. max over index >= 19). Truncated innings (rain mid-innings)
    # are excluded. Tie+super-over matches already have winner set via 'eliminator' in preprocessing.
    if 'winner' in work_df.columns:
        no_result_mask = work_df['winner'].isna()
        if no_result_mask.any():
            max_over_per_inn = work_df.groupby(['match_id', 'innings'], observed=True)['over'].transform('max')
            # Only exclude rows from no-result matches WHERE that innings was cut short
            truncated = no_result_mask & (max_over_per_inn < 19)
            work_df = work_df[~truncated]
    if work_df.empty:
        return pd.DataFrame()

    # Validate there is at least one legal delivery
    legal_check = work_df[work_df['is_valid_delivery'] == 1]
    if legal_check.empty:
        return pd.DataFrame()

    # "Balls faced" for BATTER stats = all deliveries EXCEPT wides.
    # No-balls ARE faced by the batter (they can score off them) and are counted
    # by ESPN/ICC in balls-faced. Wides do NOT reach the batter so are excluded.
    balls_faced = work_df[work_df['extras_type'].astype(str).fillna('') != 'wides'].copy()
    if balls_faced.empty:
        return pd.DataFrame()

    balls_faced = balls_faced.sort_values(['match_id', 'innings', 'team', 'batter', 'over', 'ball_float'])
    balls_faced['batter_ball_no'] = balls_faced.groupby(
        ['match_id', 'innings', 'team', 'batter'], observed=True
    ).cumcount() + 1

    grouping = ['league', 'batter'] if not include_year else ['league', 'year', 'batter']
    if not aggregate_across_teams:
        grouping.append('team')

    # Base totals — use balls_faced so SR/Balls aligns with ESPN/ICC convention
    stats = balls_faced.groupby(grouping, observed=True).agg(
        Runs=('runs.batter', 'sum'),
        Balls=('runs.batter', 'count')   # count rows = balls faced (legal + no-balls)
    ).reset_index()

    # Innings batted (innings where batter faced at least one delivery, including no-balls)
    innings_counts = balls_faced.groupby(grouping + ['match_id', 'innings'], observed=True).size().reset_index(name='x')
    innings_counts = innings_counts.groupby(grouping, observed=True).size().reset_index(name='Innings')
    stats = stats.merge(innings_counts, on=grouping, how='left')

    # Dismissals — use player_dismissed or player_out (synonyms across parquet versions).
    dismissed_col = None
    if 'player_dismissed' in work_df.columns:
        dismissed_col = 'player_dismissed'
    elif 'player_out' in work_df.columns:
        dismissed_col = 'player_out'

    if dismissed_col is not None:
        dis_df = work_df[work_df[dismissed_col].notna() & (work_df[dismissed_col].astype(str).str.strip() != '')].copy()
        if not dis_df.empty:
            dis_df = dis_df.drop(columns=['batter'], errors='ignore')
            dis_df = dis_df.rename(columns={dismissed_col: 'batter'})
            dis_df['batter'] = dis_df['batter'].astype(str)
            dismissals = dis_df.groupby(grouping, observed=True).size().reset_index(name='Dismissals')
            stats = stats.merge(dismissals, on=grouping, how='left')
        else:
            stats['Dismissals'] = 0
    elif 'is_batter_out' in work_df.columns:
        # Fallback: use batter-specific out flag (misses non-striker run-outs)
        dismissals = work_df[work_df['is_batter_out'] == True].groupby(grouping, observed=True).size().reset_index(name='Dismissals')
        stats = stats.merge(dismissals, on=grouping, how='left')
    else:
        stats['Dismissals'] = 0

    stats['Dismissals'] = stats['Dismissals'].fillna(0)
    stats['Average'] = np.where(stats['Dismissals'] > 0, stats['Runs'] / stats['Dismissals'], stats['Runs'])
    stats['Strike Rate'] = (stats['Runs'] / stats['Balls'].replace(0, np.nan) * 100).fillna(0)
    stats['Balls/Inn'] = (stats['Balls'] / stats['Innings'].replace(0, np.nan)).fillna(0)

    # Ball-range SR buckets — use batter_ball_no on balls_faced for accurate bucket assignment
    buckets = [
        (1, 10, '1-10 SR'),
        (11, 20, '11-20 SR'),
        (21, 30, '21-30 SR'),
        (31, 40, '31-40 SR'),
        (41, 50, '41-50 SR'),
        (51, 60, '51-60 SR')
    ]

    for start, end, label in buckets:
        balls_faced[f'runs_{label}'] = np.where(
            (balls_faced['batter_ball_no'] >= start) & (balls_faced['batter_ball_no'] <= end),
            balls_faced['runs.batter'],
            0
        )
        balls_faced[f'balls_{label}'] = np.where(
            (balls_faced['batter_ball_no'] >= start) & (balls_faced['batter_ball_no'] <= end),
            1,
            0
        )

    bucket_agg_cols = {}
    for _, _, label in buckets:
        bucket_agg_cols[f'runs_{label}'] = (f'runs_{label}', 'sum')
        bucket_agg_cols[f'balls_{label}'] = (f'balls_{label}', 'sum')

    bucket_stats = balls_faced.groupby(grouping, observed=True).agg(**bucket_agg_cols).reset_index()
    stats = stats.merge(bucket_stats, on=grouping, how='left')

    for _, _, label in buckets:
        stats[label] = (
            stats[f'runs_{label}'] / stats[f'balls_{label}'].replace(0, np.nan) * 100
        ).replace([np.inf, -np.inf], np.nan).fillna(0)

    # Format output
    output = stats[stats['Balls'] >= min_balls].copy()
    rename_map = {'league': 'League', 'batter': 'Name', 'team': 'Team'}
    if include_year:
        rename_map['year'] = 'Season'
    output = output.rename(columns=rename_map)

    out_cols = ['League']
    if include_year:
        out_cols.append('Season')
    out_cols.append('Name')
    if not aggregate_across_teams:
        out_cols.append('Team')
    out_cols += ['Average', 'Strike Rate', 'Balls/Inn', '1-10 SR', '11-20 SR', '21-30 SR', '31-40 SR', '41-50 SR', '51-60 SR', 'Runs', 'Balls']

    for col in ['Average', 'Strike Rate', 'Balls/Inn', '1-10 SR', '11-20 SR', '21-30 SR', '31-40 SR', '41-50 SR', '51-60 SR']:
        output[col] = output[col].round(2)

    sort_cols = ['League', 'Strike Rate'] if not include_year else ['League', 'Season', 'Strike Rate']
    sort_asc = [True, False] if not include_year else [True, False, False]
    return output[out_cols].sort_values(sort_cols, ascending=sort_asc)


# =========================================
# FASTEST INDIVIDUAL 50s & 100s
# =========================================
def fastest_individual_milestones(df_):
    """Per innings per batter: compute balls needed to reach 50 and 100."""
    ipl = df_[df_['innings'].isin([1, 2])].copy()
    if ipl.empty:
        return pd.DataFrame()

    ipl = ipl.sort_values(['match_id', 'innings', 'batter', 'ball_float'])

    results = []
    for (match_id, innings, batter, team), grp in ipl.groupby(
        ['match_id', 'innings', 'batter', 'team'], observed=True
    ):
        grp = grp.sort_values('ball_float')
        cumruns = grp['runs.batter'].cumsum()
        legal_cum = grp['is_valid_delivery'].cumsum()
        # No-balls are physically faced by the batter and count in official "balls faced" stats
        balls_faced_flag = ((grp['is_valid_delivery'] == 1) | (grp['no_balls'] > 0)).astype(int)
        balls_faced_cum = balls_faced_flag.cumsum()
        total_runs = int(cumruns.iloc[-1])
        total_balls = int(balls_faced_cum.iloc[-1])

        # Last delivery: was the batter dismissed?
        is_out = int(grp['is_batter_out'].iloc[-1]) if 'is_batter_out' in grp.columns else 0
        not_out = (is_out == 0)

        balls_to_50 = None
        balls_to_100 = None
        idx_50 = cumruns[cumruns >= 50].index
        idx_100 = cumruns[cumruns >= 100].index
        if len(idx_50):
            balls_to_50 = int(balls_faced_cum.loc[idx_50[0]])
        if len(idx_100):
            balls_to_100 = int(balls_faced_cum.loc[idx_100[0]])

        if balls_to_50 is None and total_runs < 50:
            continue  # never reached 50, skip

        # Get date and match info
        date_val = grp['date'].iloc[0]
        teams_str = str(grp['teams'].iloc[0])
        year_val = grp['year'].iloc[0]

        results.append({
            'Match ID': match_id,
            'Date': pd.to_datetime(date_val).date(),
            'Season': year_val,
            'Match': teams_str,
            'Inning': innings,
            'Batting Team': str(team),
            'Batter': str(batter),
            'Balls to 50': balls_to_50,
            'Balls to 100': balls_to_100,
            'Total Runs': total_runs,
            'Total Balls': total_balls,
            'SR': round(total_runs / total_balls * 100, 1) if total_balls > 0 else 0,
            'Not Out': '*' if not_out else '',
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# =========================================
# FASTEST TEAM 50 & 100
# =========================================
def fastest_team_milestones(df_):
    """Per innings per batting team: balls to team 50 and team 100.
    Uses runs.total (includes byes/leg-byes) for runs, is_valid_delivery for balls.
    """
    ipl = df_[df_['innings'].isin([1, 2])].copy()
    if ipl.empty:
        return pd.DataFrame()

    ipl = ipl.sort_values(['match_id', 'innings', 'team', 'ball_float'])

    results = []
    for (match_id, innings, team, teams_str, date_val, year_val), grp in ipl.groupby(
        ['match_id', 'innings', 'team', 'teams', 'date', 'year'], observed=True
    ):
        grp = grp.sort_values('ball_float')
        cumruns = grp['runs.total'].cumsum()
        legal_cum = grp['is_valid_delivery'].cumsum()
        # No-balls count as deliveries faced for milestone purposes (official T20 rules)
        balls_for_milestone = ((grp['is_valid_delivery'] == 1) | (grp['no_balls'] > 0)).astype(int).cumsum()

        total_runs = int(cumruns.iloc[-1])
        total_balls = int(legal_cum.iloc[-1])  # legal deliveries only (over count)

        balls_to_50 = None
        balls_to_100 = None
        idx_50 = cumruns[cumruns >= 50].index
        idx_100 = cumruns[cumruns >= 100].index
        if len(idx_50):
            balls_to_50 = int(balls_for_milestone.loc[idx_50[0]])
        if len(idx_100):
            balls_to_100 = int(balls_for_milestone.loc[idx_100[0]])

        if balls_to_50 is None:
            continue

        # Team 1 / Team 2 from 'teams' column (alphabetically sorted "A vs B")
        parts = str(teams_str).split(' vs ')
        team1 = parts[0].strip() if len(parts) >= 1 else str(teams_str)
        team2 = parts[1].strip() if len(parts) >= 2 else ''

        results.append({
            'Match ID': match_id,
            'Date': pd.to_datetime(date_val).date(),
            'Season': year_val,
            'Team 1': team1,
            'Team 2': team2,
            'Inning No': innings,
            'Batting Team': str(team),
            'Balls to 50': balls_to_50,
            'Balls to 100': balls_to_100,
            'Total Runs': total_runs,
            'Total Balls': total_balls,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# =========================================
# BOWLER FIRST SPELL WICKETS
# =========================================
def bowler_first_spell_wickets(df_):
    """Wickets taken by each bowler in their first 3 overs (first spell) of an innings."""
    ipl = df_[df_['innings'].isin([1, 2])].copy()
    if ipl.empty:
        return pd.DataFrame()

    results = []
    for (match_id, innings, bowler), grp in ipl.groupby(
        ['match_id', 'innings', 'bowler'], observed=True
    ):
        grp = grp.sort_values('ball_float')
        unique_overs = sorted(grp['over'].unique())
        first_3_overs = unique_overs[:3]
        spell = grp[grp['over'].isin(first_3_overs)]

        wickets = int(spell['wicket_count'].sum())
        runs = int(spell['runs.total'].sum())
        balls = int(spell['is_valid_delivery'].sum())
        overs_bowled = len(first_3_overs)
        # over column is 0-indexed; add 1 for the cricket over number
        spell_over_nos = ', '.join(str(o + 1) for o in first_3_overs)

        date_val = grp['date'].iloc[0]
        teams_str = str(grp['teams'].iloc[0])
        year_val = grp['year'].iloc[0]
        bowling_team = str(grp['bowling_team'].iloc[0]) if 'bowling_team' in grp.columns else ''

        parts = str(teams_str).split(' vs ')
        team1 = parts[0].strip() if len(parts) >= 1 else teams_str
        team2 = parts[1].strip() if len(parts) >= 2 else ''

        results.append({
            'Match ID': match_id,
            'Date': pd.to_datetime(date_val).date(),
            'Season': year_val,
            'Team 1': team1,
            'Team 2': team2,
            'Innings': innings,
            'Bowling Team': bowling_team,
            'Bowler': str(bowler),
            'Wickets in First Spell': wickets,
            'Overs in Spell': overs_bowled,
            'Spell Over Nos': spell_over_nos,
            'Runs Conceded': runs,
            'Balls': balls,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# =========================================
# BACK-TO-BACK 25+ SCORES (SEASON)
# =========================================
def consistent_batter_season(df_):
    """Per season per batter: innings with 25+, no single-digit innings, and consistency metrics."""
    ipl = df_[df_['innings'].isin([1, 2])].copy()
    if ipl.empty:
        return pd.DataFrame()

    # Step 1: per-innings batter score
    inn_scores = (
        ipl.groupby(['match_id', 'innings', 'year', 'batter'], observed=True)
        .agg(
            batter_score=('runs.batter', 'sum'),
            date=('date', 'min'),
        )
        .reset_index()
    )
    inn_scores['date'] = pd.to_datetime(inn_scores['date'])
    inn_scores = inn_scores.sort_values(['year', 'batter', 'date', 'match_id', 'innings'])

    # Step 2: per-season per-batter aggregation
    results = []
    for (year, batter), grp in inn_scores.groupby(['year', 'batter'], observed=True):
        scores = grp['batter_score'].tolist()
        total_innings = len(scores)
        innings_25_plus = sum(1 for s in scores if s >= 25)
        innings_no_single_digit = sum(1 for s in scores if s >= 10)
        total_runs = sum(scores)

        # Max consecutive 25+ streak
        max_streak = 0
        cur_streak = 0
        for s in scores:
            if s >= 25:
                cur_streak += 1
                max_streak = max(max_streak, cur_streak)
            else:
                cur_streak = 0

        consistency_pct = round(innings_no_single_digit / total_innings * 100, 1) if total_innings > 0 else 0

        results.append({
            'Season': year,
            'Batter': str(batter),
            'Innings 25+': innings_25_plus,
            'Max Consec 25+': max_streak,
            'Innings No Single Digit': innings_no_single_digit,
            'Total Runs': total_runs,
            'Total Innings': total_innings,
            'Consistency %': consistency_pct,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# =========================================
# BOUNDARY-LESS OVERS SPELL
# =========================================
def boundary_less_overs_spell(df_):
    """Bowlers who bowled 3+ consecutive overs without conceding a boundary in a single innings."""
    ipl = df_[df_['innings'].isin([1, 2])].copy()
    if ipl.empty:
        return pd.DataFrame()

    # Per over: did the bowler concede a boundary (runs.batter == 4 or 6)?
    over_flags = (
        ipl.groupby(['match_id', 'innings', 'over', 'bowler', 'bowling_team', 'teams', 'date', 'year'], observed=True)
        .agg(
            has_boundary=('runs.batter', lambda x: int((x == 4).any() or (x == 6).any())),
            runs_in_over=('runs.total', 'sum'),
            balls_in_over=('is_valid_delivery', 'sum'),
        )
        .reset_index()
    )

    # Per (match_id, innings, bowler): collect overs in order and find max run of boundary-less overs
    # Also count total boundary-less overs across all spells
    results = []
    for (match_id, innings, bowler, bowling_team, teams_str, date_val, year_val), grp in over_flags.groupby(
        ['match_id', 'innings', 'bowler', 'bowling_team', 'teams', 'date', 'year'], observed=True
    ):
        grp = grp.sort_values('over')
        boundary_less_flags = grp['has_boundary'].tolist()
        total_overs = len(boundary_less_flags)
        total_boundary_less = sum(1 for f in boundary_less_flags if f == 0)
        runs_in_boundary_less = int(grp.loc[grp['has_boundary'] == 0, 'runs_in_over'].sum())
        total_runs = int(grp['runs_in_over'].sum())
        # over column is 0-indexed; add 1 for the cricket over number
        bl_over_nums = [int(row['over']) + 1 for _, row in grp.iterrows() if row['has_boundary'] == 0]
        bl_over_nos_str = ', '.join(str(o) for o in bl_over_nums)

        # Max consecutive boundary-less overs
        max_consec = 0
        cur = 0
        for f in boundary_less_flags:
            if f == 0:
                cur += 1
                max_consec = max(max_consec, cur)
            else:
                cur = 0

        if total_boundary_less < 3:
            continue

        parts = str(teams_str).split(' vs ')
        team1 = parts[0].strip() if len(parts) >= 1 else teams_str
        team2 = parts[1].strip() if len(parts) >= 2 else ''

        results.append({
            'Match ID': match_id,
            'Date': pd.to_datetime(date_val).date(),
            'Season': year_val,
            'Team 1': team1,
            'Team 2': team2,
            'Inning No': innings,
            'Bowler': str(bowler),
            'Bowling Team': str(bowling_team),
            'Boundary-less Overs': total_boundary_less,
            'Boundary-less Over Nos': bl_over_nos_str,
            'Max Consec Boundary-less': max_consec,
            'Total Overs Bowled': total_overs,
            'Runs in Boundary-less Overs': runs_in_boundary_less,
            'Total Runs Conceded': total_runs,
        })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# =========================================
# EXTRA DELIVERIES COST
# =========================================
def extra_deliveries_cost(df_):
    """
    Match-wise & innings-wise breakdown of extra deliveries (wides + no-balls)
    bowled by each BOWLING team, and the total runs conceded purely because of
    those extra deliveries versus the team's overall total.

    Returns a tuple: (match_df, innings_df, season_df)
      match_df   — one row per match per bowling team (both innings combined)
      innings_df — one row per innings per bowling team
      season_df  — season-level aggregation per bowling team
    """
    work = df_[df_['innings'].isin([1, 2])].copy()
    if work.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Identify extra-ball deliveries (wides OR no-balls) — these cost an extra ball
    work['is_wide_ball']    = (work['wides'] > 0).astype(int)
    work['is_nb_ball']      = (work['no_balls'] > 0).astype(int)
    work['is_extra_ball']   = ((work['is_wide_ball'] | work['is_nb_ball'])).astype(int)

    # Runs directly FROM those extra deliveries (penalty + anything scored off them)
    work['wide_runs']       = work['wides']
    work['nb_runs']         = work.apply(
        lambda r: r['runs.total'] if r['is_nb_ball'] else 0, axis=1
    )
    work['extra_ball_runs'] = work.apply(
        lambda r: r['runs.total'] if r['is_extra_ball'] else 0, axis=1
    )

    # Runs scored on the RE-BOWLED delivery immediately after each extra ball.
    # e.g. Kartik Tyagi bowls a wide (5.2), batter hits SIX off the re-bowled 5.2 → next_ball_runs = 6.
    # Rows are in delivery order (parquet preserves JSON order), so shift(-1) within
    # each match+innings gives the very next delivery's runs.
    work['_next_runs'] = (
        work.groupby(['match_id', 'innings'], observed=True)['runs.total']
        .shift(-1)
        .fillna(0)
    )
    work['runs_after_extra'] = (work['is_extra_ball'] * work['_next_runs']).astype(int)

    # ---- Innings-level ----
    grp_inn = work.groupby(
        ['match_id', 'league', 'year', 'date', 'teams', 'bowling_team', 'team', 'innings'], observed=True
    )
    inn_stats = grp_inn.agg(
        Total_Deliveries=('is_valid_delivery', lambda x: len(x)),          # all balls incl. extras
        Legal_Deliveries=('is_valid_delivery', 'sum'),
        # Wide_Balls = SUM of wides column = total wide run penalties (scorecard convention).
        # e.g. a delivery with wides:2 contributes 2 here (1 penalty + 1 run off the wide).
        Wide_Balls=('wides', 'sum'),
        # Wide_Deliveries = count of deliveries called wide (extra balls re-bowled).
        # The same wides:2 delivery contributes 1 here.
        Wide_Deliveries=('is_wide_ball', 'sum'),
        NoBall_Balls=('is_nb_ball', 'sum'),
        Extra_Balls=('is_extra_ball', 'sum'),
        NoBall_Runs=('nb_runs', 'sum'),
        Extra_Ball_Runs=('extra_ball_runs', 'sum'),
        Runs_After_Extra=('runs_after_extra', 'sum'),
        Team_Total_Runs=('runs.total', 'sum'),
    ).reset_index()

    inn_stats['Extra_Ball_%'] = (inn_stats['Extra_Balls'] / inn_stats['Total_Deliveries'] * 100).round(1)
    inn_stats['Extra_Run_%']  = (inn_stats['Extra_Ball_Runs'] / inn_stats['Team_Total_Runs'].replace(0, np.nan) * 100).round(1).fillna(0)
    inn_stats['Date']         = pd.to_datetime(inn_stats['date']).dt.date
    inn_stats['Innings_Label']= inn_stats['innings'].map({1: '1st', 2: '2nd'})
    inn_stats = inn_stats.rename(columns={
        'bowling_team': 'Bowling_Team', 'team': 'Batting_Team', 'year': 'Season', 'league': 'League'
    }).sort_values('Date', ascending=False)

    # ---- Match-level (sum both innings for same bowling team) ----
    match_stats = inn_stats.groupby(
        ['match_id', 'League', 'Season', 'Date', 'teams', 'Bowling_Team'], observed=True
    ).agg(
        Wide_Balls=('Wide_Balls', 'sum'),
        Wide_Deliveries=('Wide_Deliveries', 'sum'),
        NoBall_Balls=('NoBall_Balls', 'sum'),
        Extra_Balls=('Extra_Balls', 'sum'),
        NoBall_Runs=('NoBall_Runs', 'sum'),
        Extra_Ball_Runs=('Extra_Ball_Runs', 'sum'),
        Runs_After_Extra=('Runs_After_Extra', 'sum'),
        Team_Total_Runs=('Team_Total_Runs', 'sum'),
        Total_Deliveries=('Total_Deliveries', 'sum'),
    ).reset_index()
    match_stats['Extra_Ball_%'] = (match_stats['Extra_Balls'] / match_stats['Total_Deliveries'] * 100).round(1)
    match_stats['Extra_Run_%']  = (match_stats['Extra_Ball_Runs'] / match_stats['Team_Total_Runs'].replace(0, np.nan) * 100).round(1).fillna(0)
    match_stats['Opponent']     = match_stats.apply(
        lambda row: ' v '.join(
            [t.strip() for t in str(row['teams']).replace(' vs ', ' v ').split(' v ')
             if t.strip() != str(row['Bowling_Team'])]
        ) or 'N/A', axis=1
    )
    match_stats = match_stats.sort_values('Date', ascending=False)

    # ---- Season-level ----
    season_stats = inn_stats.groupby(['League', 'Season', 'Bowling_Team'], observed=True).agg(
        Matches=('match_id', 'nunique'),
        Total_Wide_Balls=('Wide_Balls', 'sum'),        # sum of wide run penalties
        Total_Wide_Deliveries=('Wide_Deliveries', 'sum'),  # count of wide extra balls
        Total_NoBall_Balls=('NoBall_Balls', 'sum'),
        Total_Extra_Balls=('Extra_Balls', 'sum'),
        Total_NoBall_Runs=('NoBall_Runs', 'sum'),
        Total_Extra_Ball_Runs=('Extra_Ball_Runs', 'sum'),
        Total_Runs_After_Extra=('Runs_After_Extra', 'sum'),
        Total_Runs_Conceded=('Team_Total_Runs', 'sum'),
    ).reset_index()
    season_stats['Avg_Extra_Balls_Per_Match'] = (season_stats['Total_Extra_Balls'] / season_stats['Matches']).round(1)
    season_stats['Avg_Extra_Runs_Per_Match']  = (season_stats['Total_Extra_Ball_Runs'] / season_stats['Matches']).round(1)
    season_stats['Extra_Run_%'] = (
        season_stats['Total_Extra_Ball_Runs'] / season_stats['Total_Runs_Conceded'].replace(0, np.nan) * 100
    ).round(1).fillna(0)
    season_stats = season_stats.sort_values(['Season', 'Total_Extra_Balls'], ascending=[False, False])

    return match_stats, inn_stats, season_stats


# =========================================
# ON THIS DAY
# =========================================
def on_this_day_insights(df_, target_month, target_day):
    """Filter data to the same calendar day across all years and return insights per category."""
    dates = pd.to_datetime(df_['date'])
    mask = (dates.dt.month == target_month) & (dates.dt.day == target_day)
    sub = df_[mask].copy()
    if sub.empty:
        return {}

    return {
        'fastest_50s': fastest_individual_milestones(sub),
        'fastest_team_50s': fastest_team_milestones(sub),
        'first_spell': bowler_first_spell_wickets(sub),
        'boundary_less': boundary_less_overs_spell(sub),
    }


# =========================================
# BOWLER OVER IMPACT
# =========================================
def bowler_over_impact(df_, bowler_name, over_num):
    """For a given bowler and over number, split their match appearances into 3 categories
    based on what happened in that specific over, then return full-match stats for each category.
    over_num is 1-indexed (1–20); Cricsheet 'over' column is 0-indexed.
    """
    bdf = df_[df_['bowler'] == bowler_name].copy()
    if bdf.empty:
        return {}

    over_idx = over_num - 1  # convert to 0-indexed

    # Per appearance (match_id + innings) in the selected over
    target_over = bdf[bdf['over'] == over_idx]
    if target_over.empty:
        return {}

    over_stats = (
        target_over.groupby(['match_id', 'innings'], observed=True)
        .agg(
            wickets_in_over=('wicket_count', 'sum'),
            runs_in_over=('runs.total', 'sum'),
        )
        .reset_index()
    )

    def _categorize(row):
        if row['wickets_in_over'] >= 1 and row['runs_in_over'] <= 10:
            return 'Wicket & \u226410 Runs'
        elif row['wickets_in_over'] == 0 and row['runs_in_over'] <= 10:
            return 'No Wicket & \u226410 Runs'
        else:
            return '>10 Runs in Over'

    over_stats['category'] = over_stats.apply(_categorize, axis=1)

    categories = ['Wicket & \u226410 Runs', 'No Wicket & \u226410 Runs', '>10 Runs in Over']
    output = {}

    for cat in categories:
        cat_rows = over_stats[over_stats['category'] == cat]
        if cat_rows.empty:
            output[cat] = None
            continue

        # Full match deliveries for this bowler in these matches
        match_ids = cat_rows['match_id'].unique()
        full_match = bdf[bdf['match_id'].isin(match_ids)]

        matches = int(len(match_ids))
        wickets = int(full_match['wicket_count'].sum())
        runs = int(full_match['runs.total'].sum())
        balls = int(full_match['is_valid_delivery'].sum())
        dots = int((full_match['runs.total'] == 0).sum())

        economy = round(runs / (balls / 6), 2) if balls > 0 else 0.0
        average = round(runs / wickets, 2) if wickets > 0 else float('inf')
        sr = round(balls / wickets, 2) if wickets > 0 else float('inf')
        # Balls per boundary (4s and 6s off bat)
        boundaries = int(((full_match['runs.batter'] == 4) | (full_match['runs.batter'] == 6)).sum())
        bpb = round(balls / boundaries, 2) if boundaries > 0 else float('inf')
        # Balls per 6
        sixes = int((full_match['runs.batter'] == 6).sum())
        bp6 = round(balls / sixes, 2) if sixes > 0 else float('inf')
        dot_pct = round(dots / balls * 100, 2) if balls > 0 else 0.0
        wkts_per_match = round(wickets / matches, 2) if matches > 0 else 0.0

        output[cat] = {
            'Matches': matches,
            'Wickets': wickets,
            'Economy': economy,
            'Avg': average,
            'SR': sr,
            'BPB': bpb,
            'BP6': bp6,
            'Dot %': dot_pct,
            'Wkts / Match': wkts_per_match,
        }

    return output


# =========================================
# BOUNDARY-LESS BALL STREAK
# =========================================
def boundary_less_ball_streak(df_):
    """
    Per innings per batting team: compute all streaks of consecutive deliveries
    without a boundary (4 or 6 off the bat).
    Returns one row per streak (any length >= 1).
    """
    work = df_[df_['innings'].isin([1, 2])].copy()
    if work.empty:
        return pd.DataFrame()

    work = work.sort_values(['match_id', 'innings', 'ball_float'])
    work['_is_boundary'] = ((work['runs.batter'] == 4) | (work['runs.batter'] == 6)).astype(int)

    results = []
    for (match_id, innings, team), grp in work.groupby(
        ['match_id', 'innings', 'team'], observed=True
    ):
        grp = grp.sort_values('ball_float').reset_index(drop=True)
        date_val = grp['date'].iloc[0]
        year_val = grp['year'].iloc[0]
        teams_str = str(grp['teams'].iloc[0])

        is_bnd = grp['_is_boundary']
        cumsum = is_bnd.cumsum()
        non_bnd = (is_bnd == 0)

        # Group consecutive non-boundary runs by cumsum of boundaries
        # Each unique cumsum value represents one streak segment
        streak_lengths = non_bnd.groupby(cumsum).sum()

        for _, length in streak_lengths.items():
            if length >= 1:
                results.append({
                    'Match ID': match_id,
                    'Date': pd.to_datetime(date_val).date(),
                    'Season': year_val,
                    'Match': teams_str,
                    'Innings': innings,
                    'Batting Team': str(team),
                    'Balls Without Boundary': int(length),
                })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)


# =========================================
# RENDER METRICS
# =========================================

if metric_choice == "Powerplay Score Tracker":
    st.subheader("🎯 Powerplay Score Tracker")
    st.write("Track powerplay performance (overs 1-6) by team across matches")
    
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        pp_mode = st.radio("Mode", ["Batting", "Bowling"], horizontal=True)
    with col2:
        compare_teams = st.checkbox("📊 Compare Teams")
    with col3:
        show_trend = st.checkbox("📈 Show Trend Chart", value=True)
    
    # Playoff filter
    exclude_playoffs = st.checkbox("🏆 Exclude Playoff Matches (Eliminator, Qualifiers, Final)", value=False, 
                                   help="Filter out playoff matches to analyze only league/group stage performance")
    
    mode_val = 'batting' if pp_mode == "Batting" else 'bowling'
    # For bowling mode, pass full df (without team filter) and let function filter by bowling_team
    if mode_val == 'bowling':
        # Get data before team filtering for bowling mode
        bowling_df = df.copy()
        if selected_leagues:
            bowling_df = bowling_df[bowling_df['league'].isin(selected_leagues)]
        if selected_years:
            bowling_df = bowling_df[bowling_df['year'].isin(selected_years)]
        # Exclude playoff matches if checkbox is selected
        if exclude_playoffs:
            bowling_df = bowling_df[bowling_df['event_stage'] == '']
        match_stats, season_summary = powerplay_score_tracker(bowling_df, mode=mode_val, filter_teams=selected_teams if selected_teams else None)
    else:
        # Apply playoff filter to fdf if needed
        filtered_fdf = fdf.copy()
        if exclude_playoffs:
            filtered_fdf = filtered_fdf[filtered_fdf['event_stage'] == '']
        match_stats, season_summary = powerplay_score_tracker(filtered_fdf, mode=mode_val)
    
    if match_stats.empty:
        st.info("No powerplay data available for selected filters.")
    else:
        # Team comparison mode
        if compare_teams:
            available_teams = sorted(match_stats['Team'].unique())
            if len(available_teams) < 2:
                st.warning("Need at least 2 teams in data for comparison.")
                compare_teams = False
            else:
                team_col1, team_col2 = st.columns(2)
                with team_col1:
                    team1 = st.selectbox("Team 1", available_teams, key="pp_team1")
                with team_col2:
                    team2 = st.selectbox("Team 2", [t for t in available_teams if t != team1], key="pp_team2")
                
                match_stats = match_stats[match_stats['Team'].isin([team1, team2])]
                season_summary = season_summary[season_summary['Team'].isin([team1, team2])]
        
        # Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["Match-by-Match", "Season Summary", "Venue-wise", "Playoff Matches"])
        
        with tab1:
            if mode_val == 'batting':
                display_cols = ['Team', 'Opponent', 'Date', 'Season', 'Innings', 'PP_Runs', 'PP_RR', 'PP_Boundaries', 'PP_4s', 'PP_6s', 'PP_Dot%', 'PP_Wickets']
            else:
                display_cols = ['Team', 'Against', 'Date', 'Season', 'Innings', 'PP_Runs_Conceded', 'PP_Econ', 'PP_Boundaries_Conceded', 'PP_Dot%', 'PP_Wickets_Taken', 'PP_Wicket_Types']
            
            st.dataframe(match_stats[[c for c in display_cols if c in match_stats.columns]], use_container_width=True)
            
            # Trend chart
            if show_trend and not match_stats.empty:
                trend_df = match_stats.copy()
                trend_df['Date'] = pd.to_datetime(trend_df['Date'])
                trend_df = trend_df.sort_values('Date')
                
                if mode_val == 'batting':
                    y_col = 'PP_Runs'
                    title = "Powerplay Runs Trend Over Matches"
                else:
                    y_col = 'PP_Runs_Conceded'
                    title = "Powerplay Runs Conceded Trend Over Matches"
                
                fig = px.line(trend_df, x='Date', y=y_col, color='Team', markers=True, title=title)
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            if not season_summary.empty:
                st.dataframe(season_summary, use_container_width=True)
                
                if mode_val == 'batting':
                    fig = px.bar(season_summary, x='Team', y='Avg_PP_Runs', color='Season', 
                                barmode='group', title="Average Powerplay Runs by Team")
                else:
                    fig = px.bar(season_summary, x='Team', y='Avg_Runs_Conceded', color='Season',
                                barmode='group', title="Average PP Runs Conceded by Team")
                st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            st.markdown("#### Venue-wise Powerplay Performance")
            
            # Get venue data for matches in match_stats
            if 'match_id' in match_stats.columns:
                # Merge venue info
                venue_stats_df = match_stats.copy()
                venue_stats_df['Venue'] = venue_stats_df['match_id'].astype(str).map(
                    lambda x: venue_map.get(x, {}).get('venue', 'Unknown')
                )
                
                if mode_val == 'batting':
                    venue_summary = venue_stats_df.groupby('Venue', observed=True).agg(
                        Matches=('match_id', 'nunique'),
                        Avg_PP_Runs=('PP_Runs', 'mean'),
                        Avg_PP_RR=('PP_RR', 'mean'),
                        Best_PP=('PP_Runs', 'max'),
                        Total_Boundaries=('PP_Boundaries', 'sum'),
                        Avg_Wickets_Lost=('PP_Wickets', 'mean')
                    ).reset_index()
                    venue_summary['Avg_PP_Runs'] = venue_summary['Avg_PP_Runs'].round(1)
                    venue_summary['Avg_PP_RR'] = venue_summary['Avg_PP_RR'].round(2)
                    venue_summary['Avg_Wickets_Lost'] = venue_summary['Avg_Wickets_Lost'].round(2)
                    venue_summary = venue_summary.sort_values('Avg_PP_Runs', ascending=False)
                    
                    st.dataframe(venue_summary, use_container_width=True)
                    
                    # Chart
                    fig = px.bar(venue_summary.head(15), x='Venue', y='Avg_PP_Runs',
                                color='Avg_PP_RR', color_continuous_scale='RdYlGn',
                                title="Avg Powerplay Runs by Venue (Top 15)")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    venue_summary = venue_stats_df.groupby('Venue', observed=True).agg(
                        Matches=('match_id', 'nunique'),
                        Avg_Runs_Conceded=('PP_Runs_Conceded', 'mean'),
                        Avg_Econ=('PP_Econ', 'mean'),
                        Best_Bowling=('PP_Runs_Conceded', 'min'),
                        Total_Wickets=('PP_Wickets_Taken', 'sum'),
                        Avg_Wickets=('PP_Wickets_Taken', 'mean')
                    ).reset_index()
                    venue_summary['Avg_Runs_Conceded'] = venue_summary['Avg_Runs_Conceded'].round(1)
                    venue_summary['Avg_Econ'] = venue_summary['Avg_Econ'].round(2)
                    venue_summary['Avg_Wickets'] = venue_summary['Avg_Wickets'].round(2)
                    venue_summary = venue_summary.sort_values('Avg_Runs_Conceded', ascending=True)
                    
                    st.dataframe(venue_summary, use_container_width=True)
                    
                    # Chart
                    fig = px.bar(venue_summary.head(15), x='Venue', y='Avg_Runs_Conceded',
                                color='Avg_Wickets', color_continuous_scale='RdYlGn_r',
                                title="Avg Powerplay Runs Conceded by Venue (Top 15)")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Venue data not available for match-level analysis.")
        
        with tab4:
            st.markdown("##### 🏆 Playoff Matches Analysis")
            st.caption("View powerplay performance in knockout/playoff matches (Final, Eliminator, etc.)")
            
            # Get playoff data
            if mode_val == 'bowling':
                playoff_source = bowling_df.copy() if 'bowling_df' in dir() else df.copy()
            else:
                playoff_source = fdf.copy()
            
            # Filter to only playoff matches
            playoff_data = playoff_source[playoff_source['event_stage'] != ''].copy()
            
            if playoff_data.empty:
                st.info("No playoff matches found for the selected filters. Try selecting different leagues/years.")
            else:
                # Get unique stages for this selection
                available_stages = sorted(playoff_data['event_stage'].unique())
                
                # Stage filter
                st.markdown("**Filter by Stage:**")
                stage_options = ["All Playoffs"] + available_stages
                selected_stage = st.selectbox("Select Stage", stage_options, key="playoff_stage_filter")
                
                if selected_stage != "All Playoffs":
                    playoff_data = playoff_data[playoff_data['event_stage'] == selected_stage]
                
                # Calculate powerplay stats for playoff matches
                playoff_pp = playoff_data[playoff_data['over'] < 6].copy()
                
                if playoff_pp.empty:
                    st.info("No powerplay data available for playoff matches.")
                else:
                    if mode_val == 'batting':
                        # Batting mode - group by batting team (column is 'team')
                        playoff_stats = playoff_pp.groupby(['match_id', 'team', 'bowling_team', 'date', 'event_stage'], observed=True).agg(
                            PP_Runs=('runs.total', 'sum'),
                            PP_Balls=('is_valid_delivery', 'sum'),
                            PP_Wickets=('team_wicket_count', 'sum'),  # includes run-outs
                            PP_4s=('runs.batter', lambda x: (x == 4).sum()),
                            PP_6s=('runs.batter', lambda x: (x == 6).sum())
                        ).reset_index()
                        playoff_stats['PP_RR'] = (playoff_stats['PP_Runs'] / (playoff_stats['PP_Balls'] / 6)).round(2)
                        playoff_stats['PP_Boundaries'] = playoff_stats['PP_4s'] + playoff_stats['PP_6s']
                        playoff_stats = playoff_stats.rename(columns={'team': 'Team', 'bowling_team': 'Opponent', 'event_stage': 'Stage'})
                        
                        display_cols = ['Team', 'Opponent', 'Stage', 'date', 'PP_Runs', 'PP_RR', 'PP_Boundaries', 'PP_4s', 'PP_6s', 'PP_Wickets']
                    else:
                        # Bowling mode - group by bowling team  
                        playoff_stats = playoff_pp.groupby(['match_id', 'bowling_team', 'team', 'date', 'event_stage'], observed=True).agg(
                            PP_Runs_Conceded=('runs.total', 'sum'),
                            PP_Balls=('is_valid_delivery', 'sum'),
                            PP_Wickets_Taken=('wicket_count', 'sum'),
                            PP_Dots=('runs.total', lambda x: (x == 0).sum())
                        ).reset_index()
                        playoff_stats['PP_Econ'] = (playoff_stats['PP_Runs_Conceded'] / (playoff_stats['PP_Balls'] / 6)).round(2)
                        playoff_stats['PP_Dot%'] = ((playoff_stats['PP_Dots'] / playoff_stats['PP_Balls']) * 100).round(1)
                        playoff_stats = playoff_stats.rename(columns={'bowling_team': 'Team', 'team': 'Against', 'event_stage': 'Stage'})
                        
                        display_cols = ['Team', 'Against', 'Stage', 'date', 'PP_Runs_Conceded', 'PP_Econ', 'PP_Dot%', 'PP_Wickets_Taken']
                    
                    playoff_stats = playoff_stats.sort_values('date', ascending=False)
                    playoff_stats = playoff_stats.rename(columns={'date': 'Date'})
                    
                    # Show summary metrics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Playoff Matches", playoff_stats['match_id'].nunique())
                    with col2:
                        finals_count = len(playoff_stats[playoff_stats['Stage'] == 'Final']) if 'Final' in playoff_stats['Stage'].values else 0
                        st.metric("Finals", finals_count)
                    with col3:
                        eliminators_count = len(playoff_stats[playoff_stats['Stage'] == 'Eliminator']) if 'Eliminator' in playoff_stats['Stage'].values else 0
                        st.metric("Eliminators", eliminators_count)
                    
                    # Show table
                    st.dataframe(playoff_stats[[c for c in display_cols if c in playoff_stats.columns]], use_container_width=True)
                    
                    # Stage-wise summary
                    st.markdown("##### Stage-wise Summary")
                    if mode_val == 'batting':
                        stage_summary = playoff_stats.groupby('Stage', observed=True).agg(
                            Matches=('match_id', 'nunique'),
                            Avg_PP_Runs=('PP_Runs', 'mean'),
                            Avg_PP_RR=('PP_RR', 'mean'),
                            Total_Boundaries=('PP_Boundaries', 'sum')
                        ).reset_index()
                        stage_summary['Avg_PP_Runs'] = stage_summary['Avg_PP_Runs'].round(1)
                        stage_summary['Avg_PP_RR'] = stage_summary['Avg_PP_RR'].round(2)
                    else:
                        stage_summary = playoff_stats.groupby('Stage', observed=True).agg(
                            Matches=('match_id', 'nunique'),
                            Avg_Runs_Conceded=('PP_Runs_Conceded', 'mean'),
                            Avg_Econ=('PP_Econ', 'mean'),
                            Total_Wickets=('PP_Wickets_Taken', 'sum')
                        ).reset_index()
                        stage_summary['Avg_Runs_Conceded'] = stage_summary['Avg_Runs_Conceded'].round(1)
                        stage_summary['Avg_Econ'] = stage_summary['Avg_Econ'].round(2)
                    
                    st.dataframe(stage_summary, use_container_width=True)


elif metric_choice == "DRS Analysis":
    st.subheader("⚖️ DRS Analysis")
    
    # Check if DRS data is available
    if 'has_review' not in fdf.columns:
        st.warning("⚠️ DRS data not available in current dataset.")
        st.info("To enable DRS Analysis, run the preprocessing script with DRS extraction enabled.")
    else:
        # DRS metric selection
        drs_metric = st.radio(
            "Select DRS View", 
            ["Team Success Rate", "Bowling vs Batting", "Match-by-Match", "Venue Analysis", "Umpire Analysis", "Player Analysis", "Against Player"], 
            horizontal=True
        )
        
        # Get all reviews
        reviews = fdf[fdf['has_review'] == 1].copy()
        
        # Add helper to determine if review was by bowling or batting team
        if not reviews.empty:
            # The 'team' column is the batting team, so if review_by_team == team, it's a batting review
            reviews['review_type_role'] = reviews.apply(
                lambda row: 'Batting' if str(row.get('review_by_team', '')) == str(row.get('team', '')) else 'Bowling',
                axis=1
            )
        
        if reviews.empty:
            st.info("No DRS reviews found for selected filters.")
        else:
            st.write(f"**Total Reviews Found: {len(reviews)}**")
            
            # Show breakdown
            bowling_count = (reviews['review_type_role'] == 'Bowling').sum()
            batting_count = (reviews['review_type_role'] == 'Batting').sum()
            st.caption(f"📊 Bowling Team Reviews: {bowling_count} | Batting Team Reviews: {batting_count}")
            
            # =====================
            # 1. TEAM SUCCESS RATE
            # =====================
            if drs_metric == "Team Success Rate":
                st.write("Success rate of DRS reviews by team (% of reviews that overturned umpire's decision)")
                
                # Add filter for review type
                review_role_filter = st.radio(
                    "Filter by Review Type",
                    ["All Reviews", "Bowling Team Reviews", "Batting Team Reviews"],
                    horizontal=True,
                    key="drs_role_filter"
                )
                
                filtered_reviews = reviews.copy()
                if review_role_filter == "Bowling Team Reviews":
                    filtered_reviews = filtered_reviews[filtered_reviews['review_type_role'] == 'Bowling']
                elif review_role_filter == "Batting Team Reviews":
                    filtered_reviews = filtered_reviews[filtered_reviews['review_type_role'] == 'Batting']
                
                if filtered_reviews.empty:
                    st.info(f"No {review_role_filter.lower()} found.")
                else:
                    stats = filtered_reviews.groupby(['review_by_team', 'year'], observed=True).agg(
                        Total_Reviews=('has_review', 'count'),
                        Successful=('review_decision', lambda x: (x == 'struck down').sum()),
                        Failed=('review_decision', lambda x: (x == 'upheld').sum()),
                        Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum())
                    ).reset_index()
                    
                    stats['Success_Rate'] = (stats['Successful'] / stats['Total_Reviews'] * 100).round(1)
                    stats['Reviews_Lost'] = stats['Failed']
                    stats = stats.rename(columns={'review_by_team': 'Team', 'year': 'Season'})
                    
                    st.dataframe(stats[['Team', 'Season', 'Total_Reviews', 'Successful', 'Reviews_Lost', 'Success_Rate', 'Umpires_Call']], use_container_width=True)
                    
                    fig = px.bar(stats, x='Team', y='Success_Rate', color='Season',
                                barmode='group', title=f"DRS Success Rate by Team (%) - {review_role_filter}")
                    st.plotly_chart(fig, use_container_width=True)
            
            # =====================
            # NEW: BOWLING VS BATTING REVIEWS
            # =====================
            elif drs_metric == "Bowling vs Batting":
                st.write("Compare DRS reviews taken by bowling teams vs batting teams")
                
                # Overall summary
                role_summary = reviews.groupby(['review_type_role', 'year'], observed=True).agg(
                    Total_Reviews=('has_review', 'count'),
                    Successful=('review_decision', lambda x: (x == 'struck down').sum()),
                    Failed=('review_decision', lambda x: (x == 'upheld').sum()),
                    Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum())
                ).reset_index()
                role_summary['Success_Rate'] = (role_summary['Successful'] / role_summary['Total_Reviews'] * 100).round(1)
                role_summary = role_summary.rename(columns={'review_type_role': 'Review By', 'year': 'Season'})
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("#### Summary by Role")
                    st.dataframe(role_summary[['Review By', 'Season', 'Total_Reviews', 'Successful', 'Failed', 'Success_Rate', 'Umpires_Call']], use_container_width=True)
                
                with col2:
                    fig = px.bar(role_summary, x='Review By', y='Total_Reviews', color='Season',
                                barmode='group', title="Total Reviews: Bowling vs Batting")
                    st.plotly_chart(fig, use_container_width=True)
                
                # Success rate comparison
                st.markdown("---")
                st.markdown("#### Success Rate Comparison")
                
                # Aggregate across seasons for pie chart
                role_agg = reviews.groupby('review_type_role').agg(
                    Total=('has_review', 'count'),
                    Successful=('review_decision', lambda x: (x == 'struck down').sum())
                ).reset_index()
                role_agg['Success_Rate'] = (role_agg['Successful'] / role_agg['Total'] * 100).round(1)
                
                col1, col2 = st.columns(2)
                with col1:
                    fig = px.pie(role_agg, values='Total', names='review_type_role',
                                title="Reviews Distribution: Bowling vs Batting",
                                color='review_type_role',
                                color_discrete_map={'Bowling': '#1f77b4', 'Batting': '#ff7f0e'})
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    fig = px.bar(role_agg, x='review_type_role', y='Success_Rate',
                                color='review_type_role',
                                title="Success Rate by Review Type (%)",
                                color_discrete_map={'Bowling': '#1f77b4', 'Batting': '#ff7f0e'})
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                
                # Team-wise breakdown
                st.markdown("---")
                st.markdown("#### Team-wise Breakdown")
                
                team_role = reviews.groupby(['review_by_team', 'review_type_role'], observed=True).agg(
                    Reviews=('has_review', 'count'),
                    Successful=('review_decision', lambda x: (x == 'struck down').sum()),
                    Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum())
                ).reset_index()
                team_role['Success_Rate'] = (team_role['Successful'] / team_role['Reviews'] * 100).round(1)
                team_role = team_role.rename(columns={'review_by_team': 'Team', 'review_type_role': 'Review Type'})
                
                # Pivot for better display
                pivot_df = team_role.pivot_table(
                    index='Team', 
                    columns='Review Type', 
                    values=['Reviews', 'Success_Rate'],
                    fill_value=0
                ).reset_index()
                pivot_df.columns = ['Team'] + [f'{col[0]}_{col[1]}' for col in pivot_df.columns[1:]]
                
                st.dataframe(team_role.sort_values('Reviews', ascending=False), use_container_width=True)
                
                fig = px.bar(team_role, x='Team', y='Reviews', color='Review Type',
                            barmode='group', title="Reviews by Team: Bowling vs Batting")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
            
            # =====================
            # 2. MATCH-BY-MATCH DRS
            # =====================
            elif drs_metric == "Match-by-Match":
                st.write("DRS reviews per match - showing which team took reviews")
                
                # Add date from main dataframe
                date_map = fdf.groupby('match_id')['date'].first().to_dict()
                reviews['Date'] = reviews['match_id'].map(date_map)
                reviews['Date'] = pd.to_datetime(reviews['Date']).dt.date
                
                # Get short match name (Team A vs Team B -> TA vs TB)
                def get_short_match(teams_str):
                    parts = str(teams_str).replace(' vs ', ' v ').split(' v ')
                    if len(parts) == 2:
                        # Create short names from team names
                        def short_name(name):
                            words = name.strip().split()
                            if len(words) >= 2:
                                return ''.join([w[0].upper() for w in words[:2]])
                            return name[:3].upper()
                        return f"{short_name(parts[0])} vs {short_name(parts[1])}"
                    return str(teams_str)[:15]
                
                # Group by match and reviewing team
                match_team_stats = reviews.groupby(['match_id', 'teams', 'Date', 'review_by_team'], observed=True).agg(
                    Total_Reviews=('has_review', 'count'),
                    Successful=('review_decision', lambda x: (x == 'struck down').sum()),
                    Unsuccessful=('review_decision', lambda x: (x == 'upheld').sum()),
                    Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum())
                ).reset_index()
                
                # Create short match names
                match_team_stats['Match'] = match_team_stats['teams'].astype(str).apply(get_short_match)
                match_team_stats = match_team_stats.rename(columns={'review_by_team': 'Review Taken By'})
                match_team_stats = match_team_stats.sort_values('Date', ascending=False)
                
                # Display simple table
                display_cols = ['Match', 'Date', 'Review Taken By', 'Total_Reviews', 'Successful', 'Unsuccessful', 'Umpires_Call']
                display_df = match_team_stats[display_cols].copy()
                display_df.columns = ['Match', 'Date', 'Review Taken By', 'Total Reviews', 'Successful', 'Unsuccessful', 'Ump Call']
                
                st.dataframe(display_df, use_container_width=True)
                
                # Bar chart
                fig = px.bar(display_df.head(20), x='Review Taken By', y='Total Reviews', 
                            color='Successful', barmode='group',
                            title="DRS Reviews by Team (Top 20)")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
            
            # =====================
            # NEW: VENUE ANALYSIS
            # =====================
            elif drs_metric == "Venue Analysis":
                st.write("DRS reviews analyzed by venue - which grounds see the most reviews and overturns")
                
                # Add venue to reviews
                reviews_with_venue = reviews.copy()
                reviews_with_venue['Venue'] = reviews_with_venue['match_id'].astype(str).map(
                    lambda x: venue_map.get(x, {}).get('venue', 'Unknown')
                )
                
                venue_stats = reviews_with_venue.groupby('Venue', observed=True).agg(
                    Total_Reviews=('has_review', 'count'),
                    Matches_With_Reviews=('match_id', 'nunique'),
                    Overturned=('review_decision', lambda x: (x == 'struck down').sum()),
                    Upheld=('review_decision', lambda x: (x == 'upheld').sum()),
                    Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum())
                ).reset_index()
                
                venue_stats['Overturn_Rate'] = (venue_stats['Overturned'] / venue_stats['Total_Reviews'] * 100).round(1)
                venue_stats['Reviews_Per_Match'] = (venue_stats['Total_Reviews'] / venue_stats['Matches_With_Reviews']).round(2)
                venue_stats = venue_stats.sort_values('Total_Reviews', ascending=False)
                
                st.dataframe(venue_stats, use_container_width=True)
                
                col1, col2 = st.columns(2)
                with col1:
                    fig = px.bar(venue_stats.head(15), x='Venue', y='Total_Reviews',
                                color='Overturn_Rate', color_continuous_scale='RdYlGn',
                                title="Most Reviewed Venues (Top 15)")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
                with col2:
                    fig = px.bar(venue_stats.head(15), x='Venue', y='Overturn_Rate',
                                title="DRS Overturn Rate by Venue (%) - Top 15")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
                
                # Additional breakdown by venue and team
                st.markdown("---")
                st.markdown("#### Venue-Team DRS Breakdown")
                
                venue_team_stats = reviews_with_venue.groupby(['Venue', 'review_by_team'], observed=True).agg(
                    Reviews=('has_review', 'count'),
                    Successful=('review_decision', lambda x: (x == 'struck down').sum()),
                    Failed=('review_decision', lambda x: (x == 'upheld').sum())
                ).reset_index()
                venue_team_stats['Success_Rate'] = (venue_team_stats['Successful'] / venue_team_stats['Reviews'] * 100).round(1)
                venue_team_stats = venue_team_stats.rename(columns={'review_by_team': 'Team'})
                venue_team_stats = venue_team_stats.sort_values(['Venue', 'Reviews'], ascending=[True, False])
                
                # Filter to top venues
                top_venues = venue_stats.head(10)['Venue'].tolist()
                venue_team_filtered = venue_team_stats[venue_team_stats['Venue'].isin(top_venues)]
                
                st.dataframe(venue_team_filtered, use_container_width=True)
            
            # =====================
            # 3. UMPIRE ANALYSIS
            # =====================
            elif drs_metric == "Umpire Analysis":
                st.write("DRS reviews analyzed by umpire - which umpires get reviewed most often")
                
                if 'review_umpire' not in reviews.columns or reviews['review_umpire'].isna().all():
                    st.warning("Umpire data not available in reviews.")
                else:
                    umpire_stats = reviews.groupby('review_umpire', observed=True).agg(
                        Total_Reviews=('has_review', 'count'),
                        Overturned=('review_decision', lambda x: (x == 'struck down').sum()),
                        Upheld=('review_decision', lambda x: (x == 'upheld').sum()),
                        Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum())
                    ).reset_index()
                    
                    umpire_stats['Overturn_Rate'] = (umpire_stats['Overturned'] / umpire_stats['Total_Reviews'] * 100).round(1)
                    umpire_stats = umpire_stats.rename(columns={'review_umpire': 'Umpire'})
                    umpire_stats = umpire_stats.sort_values('Total_Reviews', ascending=False)
                    
                    st.dataframe(umpire_stats, use_container_width=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        fig = px.bar(umpire_stats.head(15), x='Umpire', y='Total_Reviews', 
                                    title="Most Reviewed Umpires")
                        fig.update_xaxes(tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)
                    with col2:
                        fig = px.bar(umpire_stats.head(15), x='Umpire', y='Overturn_Rate',
                                    title="Umpire Overturn Rate (%)")
                        fig.update_xaxes(tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)
            
            # =====================
            # 4. PLAYER ANALYSIS (WHO TOOK REVIEWS)
            # =====================
            elif drs_metric == "Player Analysis":
                st.write("DRS reviews analyzed by bowler (who was bowling when review was taken)")
                
                # Reviews are typically taken by bowling team, so we can analyze by bowler
                player_stats = reviews.groupby(['bowler', 'review_by_team'], observed=True).agg(
                    Total_Reviews=('has_review', 'count'),
                    Successful=('review_decision', lambda x: (x == 'struck down').sum()),
                    Failed=('review_decision', lambda x: (x == 'upheld').sum()),
                    Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum())
                ).reset_index()
                
                player_stats['Success_Rate'] = (player_stats['Successful'] / player_stats['Total_Reviews'] * 100).round(1)
                player_stats = player_stats.rename(columns={'bowler': 'Bowler', 'review_by_team': 'Team'})
                player_stats = player_stats.sort_values('Total_Reviews', ascending=False)
                
                st.dataframe(player_stats, use_container_width=True)
                
                fig = px.bar(player_stats.head(20), x='Bowler', y='Total_Reviews', color='Team',
                            title="Top 20 Bowlers by DRS Reviews Involved")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
            
            # =====================
            # 5. AGAINST PLAYER (BATTER REVIEWED)
            # =====================
            elif drs_metric == "Against Player":
                st.write("DRS reviews analyzed by batter (against whom reviews were taken)")
                
                if 'review_batter' not in reviews.columns or reviews['review_batter'].isna().all():
                    st.warning("Batter review data not available.")
                else:
                    batter_stats = reviews.groupby('review_batter', observed=True).agg(
                        Total_Reviews=('has_review', 'count'),
                        Overturned=('review_decision', lambda x: (x == 'struck down').sum()),
                        Upheld=('review_decision', lambda x: (x == 'upheld').sum()),
                        Umpires_Call=('umpires_call', lambda x: x.sum() if pd.api.types.is_bool_dtype(x) else (x == True).sum()),
                        Review_Types=('review_type', lambda x: ', '.join(x.dropna().unique()))
                    ).reset_index()
                    
                    batter_stats['Given_Out_Rate'] = (batter_stats['Overturned'] / batter_stats['Total_Reviews'] * 100).round(1)
                    batter_stats = batter_stats.rename(columns={'review_batter': 'Batter'})
                    batter_stats = batter_stats.sort_values('Total_Reviews', ascending=False)
                    
                    st.dataframe(batter_stats, use_container_width=True)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        fig = px.bar(batter_stats.head(15), x='Batter', y='Total_Reviews',
                                    title="Top 15 Batters with Most Reviews Against")
                        fig.update_xaxes(tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)
                    with col2:
                        fig = px.pie(batter_stats.head(10), values='Total_Reviews', names='Batter',
                                    title="Reviews Distribution (Top 10 Batters)")
                        st.plotly_chart(fig, use_container_width=True)
# =========================================
# OVER-BY-OVER ANALYSIS
# =========================================
elif metric_choice == "Over-by-Over Analysis":
    st.subheader("📊 Over-by-Over Analysis")
    st.write("Identify which batters scored most runs in a single over and which bowlers conceded most")
    
    # Additional filters
    col1, col2 = st.columns(2)
    with col1:
        venues = sorted(fdf['venue'].dropna().unique()) if 'venue' in fdf.columns else []
        selected_venue = st.selectbox("Filter by Venue", ["All Venues"] + list(venues))
    with col2:
        obo_years = sorted(fdf['year'].dropna().unique())
        selected_obo_year = st.selectbox("Filter by Year", ["All Years"] + list(obo_years), key="obo_year")
    
    # Apply filters
    obo_df = fdf.copy()
    if selected_venue != "All Venues" and 'venue' in obo_df.columns:
        obo_df = obo_df[obo_df['venue'] == selected_venue]
    if selected_obo_year != "All Years":
        obo_df = obo_df[obo_df['year'] == selected_obo_year]
    
    # Exclude super overs
    obo_df = obo_df[obo_df['innings'].isin([1, 2])]
    
    if obo_df.empty:
        st.warning("No data for selected filters.")
    else:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Top Run Scorers by Over",
            "Most Runs Conceded by Over",
            "Over-wise Summary",
            "Batter Profile by Over",
            "Bowler Profile by Over"
        ])
        
        with tab1:
            st.markdown("### Batters who scored most runs in a single over")
            # Group by batter, over, match to find max runs in an over
            batter_over = obo_df.groupby(['match_id', 'batter', 'over', 'team', 'year', 'date'], observed=True).agg(
                Runs=('runs.batter', 'sum'),
                Balls=('is_valid_delivery', 'sum')
            ).reset_index()
            
            # Top individual overs
            top_overs = batter_over.sort_values('Runs', ascending=False).head(50)
            top_overs = top_overs.rename(columns={'batter': 'Batter', 'over': 'Over', 'team': 'Team', 'year': 'Season', 'date': 'Date'})
            top_overs['Over'] = top_overs['Over'] + 1  # Display 1-indexed overs
            top_overs['Date'] = pd.to_datetime(top_overs['Date']).dt.date
            
            st.dataframe(top_overs[['Batter', 'Team', 'Date', 'Over', 'Runs', 'Balls', 'Season']].astype({'Batter': str, 'Team': str}), 
                        use_container_width=True)
            
            # Aggregate: Which batter has most "big overs" (e.g., 15+ runs)
            st.markdown("### Batters with most 15+ run overs")
            big_overs = batter_over[batter_over['Runs'] >= 15].groupby(['batter', 'team'], observed=True).size().reset_index(name='Big_Overs')
            big_overs = big_overs.sort_values('Big_Overs', ascending=False).head(20)
            big_overs = big_overs.rename(columns={'batter': 'Batter', 'team': 'Team'})
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.dataframe(big_overs.astype({'Batter': str, 'Team': str}), use_container_width=True)
            with col2:
                if not big_overs.empty:
                    fig = px.bar(big_overs.head(15).astype({'Batter': str, 'Team': str}), x='Batter', y='Big_Overs', color='Team',
                                title="Batters with Most 15+ Run Overs")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            st.markdown("### Bowlers who conceded most runs in a single over")
            # Group by bowler, over, match
            bowler_over = obo_df.groupby(['match_id', 'bowler', 'over', 'bowling_team', 'year', 'date'], observed=True).agg(
                Runs_Conceded=('runs.total', 'sum'),
                Balls=('is_valid_delivery', 'sum'),
                Wickets=('wicket_count', 'sum')
            ).reset_index()
            
            # Top expensive overs
            expensive_overs = bowler_over.sort_values('Runs_Conceded', ascending=False).head(50)
            expensive_overs = expensive_overs.rename(columns={'bowler': 'Bowler', 'over': 'Over', 'bowling_team': 'Team', 'year': 'Season', 'date': 'Date'})
            expensive_overs['Over'] = expensive_overs['Over'] + 1  # Display 1-indexed
            expensive_overs['Date'] = pd.to_datetime(expensive_overs['Date']).dt.date
            
            st.dataframe(expensive_overs[['Bowler', 'Team', 'Date', 'Over', 'Runs_Conceded', 'Balls', 'Wickets', 'Season']].astype({'Bowler': str, 'Team': str}), 
                        use_container_width=True)
            
            # Aggregate: Bowlers with most "expensive overs" (20+ runs)
            st.markdown("### Bowlers with most 20+ run overs conceded")
            exp_overs = bowler_over[bowler_over['Runs_Conceded'] >= 20].groupby(['bowler', 'bowling_team'], observed=True).size().reset_index(name='Expensive_Overs')
            exp_overs = exp_overs.sort_values('Expensive_Overs', ascending=False).head(20)
            exp_overs = exp_overs.rename(columns={'bowler': 'Bowler', 'bowling_team': 'Team'})
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.dataframe(exp_overs.astype({'Bowler': str, 'Team': str}), use_container_width=True)
            with col2:
                if not exp_overs.empty:
                    fig = px.bar(exp_overs.head(15).astype({'Bowler': str, 'Team': str}), x='Bowler', y='Expensive_Overs', color='Team',
                                title="Bowlers with Most 20+ Run Overs")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            st.markdown("### Average runs per over across all matches")
            # Overall over-wise stats
            over_summary = obo_df.groupby('over', observed=True).agg(
                Total_Runs=('runs.total', 'sum'),
                Total_Balls=('is_valid_delivery', 'sum'),
                Total_Wickets=('wicket_count', 'sum'),
                Matches=('match_id', 'nunique')
            ).reset_index()
            over_summary['Avg_Runs'] = (over_summary['Total_Runs'] / over_summary['Matches']).round(2)
            over_summary['Wicket_Rate'] = (over_summary['Total_Wickets'] / over_summary['Matches']).round(2)
            over_summary = over_summary.rename(columns={'over': 'Over'})
            over_summary['Over'] = over_summary['Over'] + 1  # Display 1-indexed
            
            col1, col2 = st.columns(2)
            with col1:
                fig = px.bar(over_summary, x='Over', y='Avg_Runs', 
                            title="Average Runs per Over",
                            color='Avg_Runs', color_continuous_scale='RdYlGn')
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig = px.line(over_summary, x='Over', y='Wicket_Rate',
                             title="Average Wickets per Over", markers=True)
                st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(over_summary, use_container_width=True)
        
        with tab4:
            st.markdown("### Batter — Performance by Over")
            st.caption("Select a batter to see their scoring pattern across all individual overs")
            
            obo_batters = sorted(obo_df['batter'].astype(str).unique())
            sel_obo_batter = st.selectbox("Select Batter", [""] + list(obo_batters), key="obo_t4_batter")
            
            if sel_obo_batter:
                bp_df = obo_df[obo_df['batter'].astype(str) == sel_obo_batter].copy()
                # Per over instance
                bp_overs = bp_df.groupby(['match_id', 'over', 'date', 'teams', 'team', 'year'], observed=True).agg(
                    Runs=('runs.batter', 'sum'),
                    Balls=('is_valid_delivery', 'sum')
                ).reset_index()
                bp_overs['Over'] = bp_overs['over'] + 1
                bp_overs['Date'] = pd.to_datetime(bp_overs['date']).dt.date
                bp_overs['SR_Over'] = (bp_overs['Runs'] / bp_overs['Balls'].replace(0, np.nan) * 100).fillna(0).round(1)
                bp_overs = bp_overs.rename(columns={'team': 'Team', 'year': 'Season', 'teams': 'Match'})
                bp_overs = bp_overs.sort_values('Runs', ascending=False)
                
                st.dataframe(
                    bp_overs[['Date', 'Match', 'Team', 'Over', 'Runs', 'Balls', 'SR_Over', 'Season']].head(50),
                    use_container_width=True
                )
                
                # Aggregate by over number
                bp_avg = bp_overs.groupby('Over', observed=True).agg(
                    Avg_Runs=('Runs', 'mean'),
                    Innings=('match_id', 'count')
                ).reset_index()
                bp_avg['Avg_Runs'] = bp_avg['Avg_Runs'].round(2)
                
                fig = px.bar(
                    bp_avg, x='Over', y='Avg_Runs',
                    color='Avg_Runs', color_continuous_scale='RdYlGn',
                    title=f"{sel_obo_batter} — Average Runs by Over",
                    hover_data=['Innings']
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Select a batter to view their over-by-over profile.")
        
        with tab5:
            st.markdown("### Bowler — Performance by Over")
            st.caption("Select a bowler to see their economy and wickets across all individual overs")
            
            obo_bowlers = sorted(obo_df['bowler'].astype(str).unique())
            sel_obo_bowler = st.selectbox("Select Bowler", [""] + list(obo_bowlers), key="obo_t5_bowler")
            
            if sel_obo_bowler:
                bwp_df = obo_df[obo_df['bowler'].astype(str) == sel_obo_bowler].copy()
                bwp_overs = bwp_df.groupby(['match_id', 'over', 'date', 'teams', 'bowling_team', 'year'], observed=True).agg(
                    Runs_Conceded=('runs.total', 'sum'),
                    Balls=('is_valid_delivery', 'sum'),
                    Wickets=('wicket_count', 'sum')
                ).reset_index()
                bwp_overs['Over'] = bwp_overs['over'] + 1
                bwp_overs['Date'] = pd.to_datetime(bwp_overs['date']).dt.date
                bwp_overs = bwp_overs.rename(columns={'bowling_team': 'Team', 'year': 'Season', 'teams': 'Match'})
                bwp_overs = bwp_overs.sort_values('Runs_Conceded', ascending=False)
                
                st.dataframe(
                    bwp_overs[['Date', 'Match', 'Team', 'Over', 'Runs_Conceded', 'Balls', 'Wickets', 'Season']].head(50),
                    use_container_width=True
                )
                
                # Aggregate by over number
                bwp_avg = bwp_overs.groupby('Over', observed=True).agg(
                    Avg_Runs=('Runs_Conceded', 'mean'),
                    Total_Wickets=('Wickets', 'sum'),
                    Innings=('match_id', 'count')
                ).reset_index()
                bwp_avg['Avg_Runs'] = bwp_avg['Avg_Runs'].round(2)
                
                fig = px.bar(
                    bwp_avg, x='Over', y='Avg_Runs',
                    color='Total_Wickets', color_continuous_scale='Reds_r',
                    title=f"{sel_obo_bowler} — Average Runs Conceded by Over (colour = wickets)",
                    hover_data=['Total_Wickets', 'Innings']
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Select a bowler to view their over-by-over profile.")

# =========================================
# BATTER VS BOWLER MATCHUP
# =========================================
elif metric_choice == "Batter vs Bowler Matchup":
    st.subheader("⚔️ Batter vs Bowler Matchup")
    st.write("Head-to-head statistics between batters and bowlers")
    
    # Additional filters
    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        matchup_years = sorted(fdf['year'].dropna().unique())
        selected_matchup_year = st.selectbox("Filter by Year", ["All Years"] + list(matchup_years), key="matchup_year")
    with col2:
        min_balls = 1  # Default to 1
    with col3:
        matchup_aggregate = st.checkbox(
            "Aggregate across teams (ignore team split)",
            value=False,
            key="matchup_aggregate",
            help="Merge stats for players who played for multiple teams."
        )
    
    # Source df – use pre-team-filter df when aggregating
    matchup_source = fdf_no_team.copy() if matchup_aggregate else fdf.copy()
    if selected_matchup_year != "All Years":
        matchup_source = matchup_source[matchup_source['year'] == selected_matchup_year]
    matchup_df = matchup_source[matchup_source['innings'].isin([1, 2])]
    
    if matchup_df.empty:
        st.warning("No data for selected filters.")
    else:
        # Calculate matchup stats
        grp_cols = ['batter', 'bowler'] if matchup_aggregate else ['batter', 'bowler', 'team', 'bowling_team']
        matchup_stats = matchup_df.groupby(grp_cols, observed=True).agg(
            Runs=('runs.batter', 'sum'),
            Balls=('is_valid_delivery', 'sum'),
            Dismissals=('wicket_count', 'sum'),
            Innings=('match_id', 'nunique')
        ).reset_index()
        
        # Filter by minimum balls
        matchup_stats = matchup_stats[matchup_stats['Balls'] >= min_balls]
        
        if matchup_stats.empty:
            st.info(f"No matchups with {min_balls}+ balls faced.")
        else:
            matchup_stats['SR'] = (matchup_stats['Runs'] / matchup_stats['Balls'] * 100).round(2)
            matchup_stats['Avg'] = matchup_stats.apply(
                lambda x: round(x['Runs'] / x['Dismissals'], 2) if x['Dismissals'] > 0 else x['Runs'], axis=1
            )
            matchup_stats['Batter'] = matchup_stats['batter'].astype(str)
            matchup_stats['Bowler'] = matchup_stats['bowler'].astype(str)
            if not matchup_aggregate:
                matchup_stats['Batting_Team'] = matchup_stats['team'].astype(str)
                matchup_stats['Bowling_Team'] = matchup_stats['bowling_team'].astype(str)
            
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "Top Matchups (Batter Dominant)",
                "Top Matchups (Bowler Dominant)",
                "Search Matchup",
                "Batter - Best Overs",
                "Bowler - Most Expensive Overs"
            ])
            
            with tab1:
                st.markdown("### Batters who dominate specific bowlers")
                st.caption("Batters with most runs against a bowler without getting dismissed")
                
                batter_dominant = matchup_stats[matchup_stats['Dismissals'] == 0].sort_values('Runs', ascending=False).head(30)
                if batter_dominant.empty:
                    batter_dominant = matchup_stats.sort_values(['Runs', 'SR'], ascending=[False, False]).head(30)
                    st.caption("(Showing top run scorers as no never-out matchups found)")
                
                dom_cols = ['Batter', 'Bowler', 'Innings', 'Runs', 'Balls', 'SR', 'Dismissals', 'Avg']
                if not matchup_aggregate:
                    dom_cols = ['Batter', 'Batting_Team', 'Bowler', 'Bowling_Team'] + dom_cols[2:]
                st.dataframe(batter_dominant[dom_cols], use_container_width=True)
                
                if not batter_dominant.empty:
                    batter_dominant = batter_dominant.copy()
                    batter_dominant['Matchup'] = batter_dominant['Batter'] + ' vs ' + batter_dominant['Bowler']
                    fig = px.bar(batter_dominant.head(15), x='Matchup', y='Runs', color='SR',
                                color_continuous_scale='RdYlGn',
                                title="Top Batter vs Bowler (Most Runs, Never Out)")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
            
            with tab2:
                st.markdown("### Bowlers who dominate specific batters")
                st.caption("Bowlers who have dismissed the same batter multiple times")
                
                bowler_dominant = matchup_stats[matchup_stats['Dismissals'] >= 2].sort_values(
                    ['Dismissals', 'Avg'], ascending=[False, True]
                ).head(30)
                
                if bowler_dominant.empty:
                    st.info("No bowler has dismissed the same batter 2+ times in filtered data.")
                else:
                    dom2_cols = ['Bowler', 'Batter', 'Innings', 'Dismissals', 'Runs', 'Balls', 'Avg']
                    if not matchup_aggregate:
                        dom2_cols = ['Bowler', 'Bowling_Team', 'Batter', 'Batting_Team'] + dom2_cols[2:]
                    st.dataframe(bowler_dominant[dom2_cols], use_container_width=True)
                    
                    bowler_dominant = bowler_dominant.copy()
                    bowler_dominant['Matchup'] = bowler_dominant['Bowler'] + ' vs ' + bowler_dominant['Batter']
                    fig = px.bar(bowler_dominant.head(15), x='Matchup', y='Dismissals', color='Avg',
                                color_continuous_scale='RdYlGn_r',
                                title="Top Bowler vs Batter (Most Dismissals)")
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)
            
            with tab3:
                st.markdown("### Search for specific matchup")
                col1, col2 = st.columns(2)
                with col1:
                    all_batters = sorted(matchup_stats['Batter'].unique())
                    search_batter = st.selectbox("Select Batter", [""] + list(all_batters))
                with col2:
                    all_bowlers = sorted(matchup_stats['Bowler'].unique())
                    search_bowler = st.selectbox("Select Bowler", [""] + list(all_bowlers))
                
                if search_batter or search_bowler:
                    search_result = matchup_stats.copy()
                    if search_batter:
                        search_result = search_result[search_result['Batter'] == search_batter]
                    if search_bowler:
                        search_result = search_result[search_result['Bowler'] == search_bowler]
                    
                    if search_result.empty:
                        st.info("No matchup found for selected players.")
                    else:
                        sr_cols = ['Batter', 'Bowler', 'Innings', 'Runs', 'Balls', 'SR', 'Dismissals', 'Avg']
                        if not matchup_aggregate:
                            sr_cols = ['Batter', 'Batting_Team', 'Bowler', 'Bowling_Team'] + sr_cols[2:]
                        st.dataframe(search_result[sr_cols], use_container_width=True)
                        
                        if len(search_result) > 1:
                            if search_batter:
                                fig = px.bar(search_result.sort_values('Runs', ascending=False).head(15), 
                                            x='Bowler', y='Runs', color='SR',
                                            color_continuous_scale='RdYlGn',
                                            title=f"{search_batter}'s Record Against Bowlers")
                                fig.update_xaxes(tickangle=45)
                                st.plotly_chart(fig, use_container_width=True)
                            elif search_bowler:
                                fig = px.bar(search_result.sort_values('Dismissals', ascending=False).head(15), 
                                            x='Batter', y='Dismissals', color='Avg',
                                            color_continuous_scale='RdYlGn_r',
                                            title=f"{search_bowler}'s Record Against Batters")
                                fig.update_xaxes(tickangle=45)
                                st.plotly_chart(fig, use_container_width=True)
            
            with tab4:
                st.markdown("### Batter — Most Runs in a Single Over")
                st.caption("Select a batter to see their highest-scoring individual overs")
                
                all_batters_t4 = sorted(matchup_df['batter'].astype(str).unique())
                sel_batter_t4 = st.selectbox("Select Batter", [""] + list(all_batters_t4), key="mu_t4_batter")
                
                if sel_batter_t4:
                    batter_overs = matchup_df[matchup_df['batter'].astype(str) == sel_batter_t4].copy()
                    batter_overs = batter_overs.groupby(['match_id', 'over', 'date', 'teams', 'team', 'year'], observed=True).agg(
                        Runs=('runs.batter', 'sum'),
                        Balls=('is_valid_delivery', 'sum')
                    ).reset_index()
                    batter_overs['Over'] = batter_overs['over'] + 1
                    batter_overs['Date'] = pd.to_datetime(batter_overs['date']).dt.date
                    batter_overs['Opponent'] = batter_overs['teams'].astype(str)
                    batter_overs['SR_Over'] = (batter_overs['Runs'] / batter_overs['Balls'].replace(0, np.nan) * 100).fillna(0).round(1)
                    batter_overs = batter_overs.rename(columns={'team': 'Team', 'year': 'Season'})
                    batter_overs = batter_overs.sort_values('Runs', ascending=False)
                    
                    st.markdown(f"**{sel_batter_t4} — Top Scoring Overs**")
                    st.dataframe(
                        batter_overs[['Date', 'Opponent', 'Team', 'Over', 'Runs', 'Balls', 'SR_Over', 'Season']].head(30),
                        use_container_width=True
                    )
                    
                    if not batter_overs.empty:
                        fig = px.bar(
                            batter_overs.head(20),
                            x=batter_overs.head(20)['Date'].astype(str) + ' Ov' + batter_overs.head(20)['Over'].astype(str),
                            y='Runs',
                            color='SR_Over',
                            color_continuous_scale='RdYlGn',
                            title=f"{sel_batter_t4} — Most Runs in a Single Over"
                        )
                        fig.update_xaxes(title='Match / Over', tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Select a batter to see their best individual overs.")
            
            with tab5:
                st.markdown("### Bowler — Most Runs Conceded in a Single Over")
                st.caption("Select a bowler to see their most expensive individual overs")
                
                all_bowlers_t5 = sorted(matchup_df['bowler'].astype(str).unique())
                sel_bowler_t5 = st.selectbox("Select Bowler", [""] + list(all_bowlers_t5), key="mu_t5_bowler")
                
                if sel_bowler_t5:
                    bowler_overs = matchup_df[matchup_df['bowler'].astype(str) == sel_bowler_t5].copy()
                    bowler_overs = bowler_overs.groupby(['match_id', 'over', 'date', 'teams', 'bowling_team', 'year'], observed=True).agg(
                        Runs_Conceded=('runs.total', 'sum'),
                        Balls=('is_valid_delivery', 'sum'),
                        Wickets=('wicket_count', 'sum')
                    ).reset_index()
                    bowler_overs['Over'] = bowler_overs['over'] + 1
                    bowler_overs['Date'] = pd.to_datetime(bowler_overs['date']).dt.date
                    bowler_overs['Match'] = bowler_overs['teams'].astype(str)
                    bowler_overs = bowler_overs.rename(columns={'bowling_team': 'Team', 'year': 'Season'})
                    bowler_overs = bowler_overs.sort_values('Runs_Conceded', ascending=False)
                    
                    st.markdown(f"**{sel_bowler_t5} — Most Expensive Overs**")
                    st.dataframe(
                        bowler_overs[['Date', 'Match', 'Team', 'Over', 'Runs_Conceded', 'Balls', 'Wickets', 'Season']].head(30),
                        use_container_width=True
                    )
                    
                    if not bowler_overs.empty:
                        fig = px.bar(
                            bowler_overs.head(20),
                            x=bowler_overs.head(20)['Date'].astype(str) + ' Ov' + bowler_overs.head(20)['Over'].astype(str),
                            y='Runs_Conceded',
                            color='Wickets',
                            color_continuous_scale='Reds',
                            title=f"{sel_bowler_t5} — Most Runs Conceded in a Single Over"
                        )
                        fig.update_xaxes(title='Match / Over', tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Select a bowler to see their most expensive overs.")

# =========================================
# MOST WICKETS IN AN OVER
# =========================================
elif metric_choice == "Most Wickets in an Over":
    st.subheader("🎯 Most Wickets in an Over")
    st.write("Identify which bowlers take the most wickets in a single over")
    
    # Exclude super overs
    mwo_df = fdf[fdf['innings'].isin([1, 2])].copy()
    
    if mwo_df.empty:
        st.warning("No data for selected filters.")
    else:
        # Group by match, innings, bowler, over to find wickets per over
        wickets_per_over = mwo_df.groupby(['match_id', 'innings', 'bowler', 'over', 'bowling_team', 'teams', 'date', 'year'], observed=True).agg(
            Wickets=('wicket_count', 'sum'),
            Runs_Conceded=('runs.total', 'sum'),
            Balls=('is_valid_delivery', 'sum')
        ).reset_index()
        
        # Convert to string to avoid categorical issues
        wickets_per_over['Bowler'] = wickets_per_over['bowler'].astype(str)
        wickets_per_over['Team'] = wickets_per_over['bowling_team'].astype(str)
        wickets_per_over['Over'] = wickets_per_over['over'] + 1  # Display 1-indexed
        wickets_per_over['Season'] = wickets_per_over['year']
        wickets_per_over['Date'] = pd.to_datetime(wickets_per_over['date']).dt.date
        wickets_per_over['Innings'] = wickets_per_over['innings'].map({1: '1st Inns', 2: '2nd Inns'})
        
        tab1, tab2, tab3 = st.tabs(["📋 Inning-wise", "🏏 Match-wise", "📊 Overall"])
        
        with tab1:
            st.markdown("### Best Bowling Overs in Each Innings")
            # Filter to overs with at least 2 wickets
            multi_wicket_overs = wickets_per_over[wickets_per_over['Wickets'] >= 2].sort_values(['Wickets', 'Runs_Conceded'], ascending=[False, True])
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 1st Innings")
                first_inn = multi_wicket_overs[multi_wicket_overs['innings'] == 1].head(25)
                if first_inn.empty:
                    st.info("No 2+ wicket overs in 1st innings")
                else:
                    st.dataframe(first_inn[['Bowler', 'Team', 'Over', 'Wickets', 'Runs_Conceded', 'Date', 'Season']], use_container_width=True)
            
            with col2:
                st.markdown("#### 2nd Innings")
                second_inn = multi_wicket_overs[multi_wicket_overs['innings'] == 2].head(25)
                if second_inn.empty:
                    st.info("No 2+ wicket overs in 2nd innings")
                else:
                    st.dataframe(second_inn[['Bowler', 'Team', 'Over', 'Wickets', 'Runs_Conceded', 'Date', 'Season']], use_container_width=True)
        
        with tab2:
            st.markdown("### Top Wicket-Taking Overs by Match")
            # Show all multi-wicket overs with match context
            multi_wicket_match = wickets_per_over[wickets_per_over['Wickets'] >= 2].sort_values(['Wickets', 'Runs_Conceded'], ascending=[False, True]).head(50)
            multi_wicket_match['Match'] = multi_wicket_match['teams'].astype(str)
            
            if multi_wicket_match.empty:
                st.info("No 2+ wicket overs found.")
            else:
                st.dataframe(multi_wicket_match[['Bowler', 'Team', 'Match', 'Innings', 'Over', 'Wickets', 'Runs_Conceded', 'Date']], use_container_width=True)
                
                # Chart
                fig = px.bar(multi_wicket_match.head(20), x='Bowler', y='Wickets', color='Team',
                            title="Top 20 Multi-Wicket Overs", text='Wickets')
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            st.markdown("### Overall - Bowlers with Most Multi-Wicket Overs")
            # Aggregate: bowlers with most 2+ wicket overs
            bowler_multi_wicket = wickets_per_over[wickets_per_over['Wickets'] >= 2].groupby(['Bowler', 'Team'], observed=True).agg(
                Multi_Wicket_Overs=('match_id', 'count'),
                Total_Wickets_in_MW=('Wickets', 'sum'),
                Best_Over=('Wickets', 'max')
            ).reset_index().sort_values('Multi_Wicket_Overs', ascending=False).head(30)
            
            if bowler_multi_wicket.empty:
                st.info("No bowlers with 2+ wicket overs found.")
            else:
                st.dataframe(bowler_multi_wicket, use_container_width=True)
                
                fig = px.bar(bowler_multi_wicket.head(15), x='Bowler', y='Multi_Wicket_Overs', color='Team',
                            title="Bowlers with Most 2+ Wicket Overs", text='Multi_Wicket_Overs')
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)

# =========================================
# EXTRAS IMPACT INDEX (BOWLER)
# =========================================
elif metric_choice == "Extras Impact Index (Bowler)":
    st.subheader("💸 Extras Impact Index (Bowler)")
    st.write("Analyze the true cost of extras: Runs conceded on the extra delivery + Runs conceded on the immediate next delivery")
    
    # 1. Filters (Season | Match | Team | Bowler)
    # We start with 'fdf' which is already filtered by League/Year/Team from sidebar if selected.
    # We will add specific filters here as requested.
    
    ei_df = fdf.copy()
    if ei_df.empty:
        st.warning("No data for selected sidebar filters.")
    else:
        # Filter Layout
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            years = sorted(ei_df['year'].unique())
            sel_years = st.multiselect("Season", years, default=years, key="ei_season")
            if sel_years:
                ei_df = ei_df[ei_df['year'].isin(sel_years)]
        
        with col2:
            matches = sorted(ei_df['match_id'].unique())
            # Show matches as "Team vs Team (Date)"
            match_labels = ei_df[['match_id', 'teams', 'date']].drop_duplicates().set_index('match_id')
            match_labels['label'] = match_labels['teams'].astype(str) + ' (' + match_labels['date'].astype(str) + ')'
            match_dict = match_labels['label'].to_dict()
            
            sel_matches = st.multiselect("Match", matches, format_func=lambda x: match_dict.get(x, x), key="ei_match")
            if sel_matches:
                ei_df = ei_df[ei_df['match_id'].isin(sel_matches)]
                
        with col3:
            teams = sorted(ei_df['bowling_team'].unique())
            sel_teams = st.multiselect("Team", teams, default=teams, key="ei_team")
            if sel_teams:
                ei_df = ei_df[ei_df['bowling_team'].isin(sel_teams)]
                
        with col4:
            bowlers = sorted(ei_df['bowler'].unique())
            sel_bowlers = st.multiselect("Bowler", bowlers, default=bowlers, key="ei_bowler")
            if sel_bowlers:
                ei_df = ei_df[ei_df['bowler'].isin(sel_bowlers)]
        
        if ei_df.empty:
            st.warning("No data after applying filters.")
        else:
            # 2. Calculations
            # Sort to ensure delivery order
            ei_df = ei_df.sort_values(['match_id', 'innings', 'over', 'ball_float'])
            
            # Shift to get next ball details
            ei_df['next_runs'] = ei_df['runs.total'].shift(-1)
            ei_df['next_match'] = ei_df['match_id'].shift(-1)
            ei_df['next_innings'] = ei_df['innings'].shift(-1)
            
            # Filter for Extras (Wides and No Balls)
            # Use 'wides' > 0 or 'no_balls' > 0 logic
            # Note: 'no_balls' in preprocessing is a flag (0/1), runs are in runs.extras or runs.total
            extras_mask = (ei_df['wides'] > 0) | (ei_df['no_balls'] > 0)
            
            # Valid next ball check (same match, same innings)
            valid_next = (ei_df['next_match'] == ei_df['match_id']) & (ei_df['next_innings'] == ei_df['innings'])
            
            # Dataframe for extras events
            extras_events_df = ei_df[extras_mask & valid_next].copy()
            
            # Calculate cost per event
            extras_events_df['Runs_on_Extra'] = extras_events_df['runs.total']
            extras_events_df['Runs_Next_Ball'] = extras_events_df['next_runs'].fillna(0)
            extras_events_df['Total_Extra_Impact_Runs'] = extras_events_df['Runs_on_Extra'] + extras_events_df['Runs_Next_Ball']
            
            # Aggregate stats by Bowler
            # 1. Total Runs Conceded by Bowler (for denominator)
            bowler_total_runs = ei_df.groupby(['bowler', 'bowling_team'], observed=True)['runs.total'].sum().reset_index(name='Total_Runs_Conceded')
            
            # 2. Extras Stats
            if extras_events_df.empty:
                st.info("No extras found in the filtered data.")
            else:
                extras_stats = extras_events_df.groupby(['bowler', 'bowling_team'], observed=True).agg(
                    Extra_Balls=('match_id', 'count'), # Count of extra events (deliveries)
                    Wide_Runs=('wides', 'sum'),       # Sum of wide runs
                    NoBall_Runs=('no_balls', 'sum'),  # Sum of no-ball runs (if column is count, this might need check, but usually 'no_balls' in parquet is 0/1 flag. Checks needed.)
                    # Wait, no_balls column in parquet is usually 0/1 flag. 
                    # If we want NoBall RUNS, we should check preprocessing. 
                    # Preprocessing: 'no_balls' is 1 if event['noballs'] > 0 else 0.
                    # Runs for NoBall are in runs.extras.
                    # But if it's a NoBall + Bye, runs.extras includes byes.
                    # Standard convention: NoBall penalty is 1 run. 
                    # We will assume 1 run per NoBall count for the "Extras" part.
                    # But for "Impact", we want the cost.
                    # Let's use specific columns if possible.
                    # For now: NoBall Runs = Count * 1.
                    Extra_Impact_Runs=('Total_Extra_Impact_Runs', 'sum')
                ).reset_index()
                
                # Correction: "no_balls" column is count. Multiply by 1 for runs? 
                # Actually, strictly speaking, a No Ball is 1 run.
                extras_stats['NoBall_Runs'] = extras_events_df.groupby(['bowler', 'bowling_team'], observed=True)['no_balls'].sum().values
                
                # Merge
                final_stats = pd.merge(bowler_total_runs, extras_stats, on=['bowler', 'bowling_team'], how='left')
                # Fill NaNs only in numeric columns to avoid Categorical type errors
                final_stats[['Extra_Balls', 'Wide_Runs', 'NoBall_Runs', 'Extra_Impact_Runs']] = final_stats[['Extra_Balls', 'Wide_Runs', 'NoBall_Runs', 'Extra_Impact_Runs']].fillna(0)
                
                # Impact %
                final_stats['Impact_Percent'] = (final_stats['Extra_Impact_Runs'] / final_stats['Total_Runs_Conceded'] * 100).fillna(0).round(1)
                final_stats = final_stats.sort_values('Extra_Impact_Runs', ascending=False)
                
                # 3. KPI Cards
                total_extra_balls = int(final_stats['Extra_Balls'].sum())
                total_wide_runs = int(final_stats['Wide_Runs'].sum())
                total_nb_runs = int(final_stats['NoBall_Runs'].sum())
                total_impact_runs = int(final_stats['Extra_Impact_Runs'].sum())
                total_runs_conc = int(final_stats['Total_Runs_Conceded'].sum())
                avg_impact_pct = (total_impact_runs / total_runs_conc * 100) if total_runs_conc > 0 else 0
                
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                # Show Runs clearly
                kpi1.metric("🟦 Extra Deliveries", f"{total_extra_balls}")
                kpi2.metric("🟧 Wides / NBs (Runs)", f"{total_wide_runs} / {total_nb_runs}") 
                kpi3.metric("🟥 Extra-Impact Runs", f"{total_impact_runs}")
                kpi4.metric("🟨 Impact %", f"{avg_impact_pct:.1f}%")
                
                st.markdown("---")
                
                # 4. Charts and Table
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown("#### Bowler vs Extra-Impact Runs")
                    fig = px.bar(final_stats.head(20), x='bowler', y='Extra_Impact_Runs', 
                                color='Impact_Percent', 
                                title="Extra-Impact Runs by Bowler (Color = Impact %)",
                                labels={'bowler': 'Bowler', 'Extra_Impact_Runs': 'Extra-Impact Runs', 'Impact_Percent': 'Impact %'},
                                color_continuous_scale='Reds')
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("#### Top Bowlers (Impact Table)")
                    st.dataframe(
                        final_stats[['bowler', 'Extra_Balls', 'Wide_Runs', 'NoBall_Runs', 'Extra_Impact_Runs', 'Impact_Percent']]
                        .rename(columns={'bowler': 'Bowler', 'Extra_Balls': 'Balls', 'Wide_Runs': 'Wides', 'NoBall_Runs': 'NBs', 'Extra_Impact_Runs': 'Impact Runs', 'Impact_Percent': 'Impact %'})
                        .head(20),
                        use_container_width=True,
                        hide_index=True
                    )

                st.markdown("---")
                st.markdown("#### 🔍 Ball-by-Ball Breakdown (Extras → Next Ball)")
                
                # Drill-down table
                drill_down = extras_events_df[['over', 'ball_float', 'bowler', 'batter', 'bowling_team', 'wides', 'no_balls', 'Runs_on_Extra', 'Runs_Next_Ball']].copy()
                drill_down['Over'] = drill_down['over'] + 1
                drill_down['Ball'] = drill_down['ball_float'].apply(lambda x: f"{int(x)}.{(round((x % 1) * 6) + 1)}")
                
                def get_extra_type(row):
                    types = []
                    if row['wides'] > 0: types.append(f"Wide ({int(row['wides'])})")
                    if row['no_balls'] > 0: types.append("No-ball")
                    return ", ".join(types)
                
                drill_down['Extra Type'] = drill_down.apply(get_extra_type, axis=1)
                
                # Formatted table columns
                display_table = drill_down[['bowler', 'Over', 'Ball', 'Extra Type', 'Runs_on_Extra', 'Runs_Next_Ball']]
                display_table.columns = ['Bowler', 'Over', 'Ball', 'Extra Type', 'Runs on Extra', 'Runs Next Ball']
                
                st.dataframe(display_table, use_container_width=True)

# =========================================
# OVERALL EXTRAS SUMMARY (SEASON VIEW)
# =========================================
elif metric_choice == "Overall Extras Summary":
    st.subheader("📊 Overall Extras Summary (Season View)")
    st.write("Comprehensive analysis of extras (Wides, No-Balls) across teams and bowlers.")
    
    # Use raw 'df' to avoid phase filtering, but apply sidebar League/Year filters manually
    # We want "Season Summary", so assume user wants full season data.
    
    # Filter by League/Year from sidebar (re-apply logic on raw df)
    # We don't want 'fdf' because it might have other filters (though currently only League/Year/Team are in sidebar).
    # But just in case 'fdf' has phase filter in future or default behavior, let's be safe.
    # Actually, the sidebar code applies League/Year/Team to 'fdf'. 
    # If we want to ignore Team filter for "Overall Summary" (to show all teams), we should use `df` and re-filter by Year/League.
    # User said "Filters: Season | Match | Team | Bowler" for Impact Index.
    # For "Season Summary", it usually implies showing ALL teams for the selected season.
    # So we will filter by League/Year only.
    
    oes_df = df.copy()
    if selected_leagues:
        oes_df = oes_df[oes_df['league'].isin(selected_leagues)]
    if selected_years:
        oes_df = oes_df[oes_df['year'].isin(selected_years)]
        
    if oes_df.empty:
        st.warning("No data for selected League/Year.")
    else:
        # 1. KPI Cards (Season Overview)
        # Total Extras = Wides + NoBalls + Byes + Legbyes?
        # User request: "Total Extras in Season: 412".
        # Usually implies ALL extras.
        # Wides + NB + Byes + Legbyes
        total_wides = oes_df['wides'].sum()
        total_nbs = oes_df['no_balls'].sum() # Assuming count = runs (approx) or check runs.extras logic
        # Actually in parquet, 'runs.extras' is the sum of all extras runs.
        # We can sum 'runs.extras'.
        total_extras = oes_df['runs.extras'].sum()
        
        matches_count = oes_df['match_id'].nunique()
        avg_extras = round(total_extras / matches_count, 1) if matches_count > 0 else 0
        
        # Most/Least Disciplined Team (Avg Extras/Match)
        team_discipline = oes_df.groupby('bowling_team', observed=True)['runs.extras'].sum().reset_index()
        team_matches = oes_df.groupby('bowling_team', observed=True)['match_id'].nunique().reset_index()
        team_stats = pd.merge(team_discipline, team_matches, on='bowling_team')
        team_stats['Avg_Extras'] = (team_stats['runs.extras'] / team_stats['match_id']).round(1)
        team_stats = team_stats.sort_values('Avg_Extras')
        
        best_team = team_stats.iloc[0] if not team_stats.empty else None
        worst_team = team_stats.iloc[-1] if not team_stats.empty else None
        
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("🟥 Total Extras", f"{int(total_extras)}")
        kpi2.metric("🟨 Avg Extras/Match", f"{avg_extras}")
        if best_team is not None:
            kpi3.metric("🟩 Most Disciplined", f"{best_team['bowling_team']} ({best_team['Avg_Extras']})")
        if worst_team is not None:
            kpi4.metric("🟥 Least Disciplined", f"{worst_team['bowling_team']} ({worst_team['Avg_Extras']})")
            
        st.markdown("---")
        
        # 2. Stacked Bar Chart (Team vs Extras - Wides/NBs)
        # User asked for "Wides (light) + No-balls (dark)"
        team_breakdown = oes_df.groupby('bowling_team', observed=True).agg(
            Wides=('wides', 'sum'),
            NoBalls=('no_balls', 'sum') # Count as runs approximation
        ).reset_index()
        
        # Setup for stacked bar (long format)
        team_long = team_breakdown.melt(id_vars='bowling_team', value_vars=['Wides', 'NoBalls'], 
                                      var_name='Extra_Type', value_name='Runs')
        
        st.markdown("### Team Comparison")
        fig = px.bar(team_long, x='bowling_team', y='Runs', color='Extra_Type',
                     title="Team Extras Breakdown (Wides vs No-Balls)",
                     labels={'bowling_team': 'Team', 'Runs': 'Runs Conceded'},
                     color_discrete_map={'Wides': '#ADD8E6', 'NoBalls': '#00008B'}, # Light/Dark blue
                     barmode='stack')
        st.plotly_chart(fig, use_container_width=True)
        
        # 3. Leaderboard (Bowlers)
        # Columns: Bowler, Team, Wides, No-balls, Total Extras, Extras per Over
        st.markdown("### Bowler Leaderboard")
        
        # Group by Bowler
        bowler_stats = oes_df.groupby(['bowler', 'bowling_team'], observed=True).agg(
            Wides=('wides', 'sum'),
            NoBalls=('no_balls', 'sum'),
            Balls_Bowled=('is_valid_delivery', 'sum') # For Extras/Over calculation
        ).reset_index()
        
        bowler_stats['Total_Extras'] = bowler_stats['Wides'] + bowler_stats['NoBalls']
        # Extras per over: Total Extras / (Balls/6)
        bowler_stats['Overs'] = bowler_stats['Balls_Bowled'] / 6
        bowler_stats['Extras_Per_Over'] = (bowler_stats['Total_Extras'] / bowler_stats['Overs']).replace([np.inf, np.nan], 0).round(2)
        
        # Filter for bowlers with minimum impact? Maybe just top 20.
        bowler_stats = bowler_stats.sort_values('Total_Extras', ascending=False)
        
        # Top 10 Chart
        col1, col2 = st.columns([1, 2])
        
        with col1:
             st.markdown("**Top 10 Bowlers by Extras**")
             fig = px.bar(bowler_stats.head(10), x='Total_Extras', y='bowler', orientation='h',
                          color='bowling_team', title="Top 10 Bowlers (Most Extras)",
                          labels={'Total_Extras': 'Total Wides + NBs', 'bowler': 'Bowler'})
             fig.update_layout(yaxis={'categoryorder':'total ascending'})
             st.plotly_chart(fig, use_container_width=True)
             
        with col2:
            st.dataframe(
                bowler_stats[['bowler', 'bowling_team', 'Wides', 'NoBalls', 'Total_Extras', 'Extras_Per_Over']]
                .rename(columns={'bowler': 'Bowler', 'bowling_team': 'Team', 'Total_Extras': 'Total (W+NB)', 'Extras_Per_Over': 'Extras/Over'}),
                use_container_width=True,
                hide_index=True
            )
            
        # 4. Insight Panel
        st.markdown("---")
        st.subheader("🧠 Insights")
        
        # Top 3 bowlers contribution
        total_wides_season = bowler_stats['Wides'].sum()
        top_3_wides = bowler_stats.sort_values('Wides', ascending=False).head(3)['Wides'].sum()
        top_3_share = (top_3_wides / total_wides_season * 100) if total_wides_season > 0 else 0
        
        st.markdown(f"- **Top 3 Bowlers** contributed **{top_3_share:.1f}%** of all Wides this season.")
        
        # Death overs extras (Overs 16-20)
        death_df = oes_df[(oes_df['over'] >= 15) & (oes_df['over'] <= 19)]
        death_extras = death_df['runs.extras'].sum()
        death_share = (death_extras / total_extras * 100) if total_extras > 0 else 0
        
        st.markdown(f"- **Death Overs (16-20)** account for **{death_share:.1f}%** of total extras.")
        
        # Low extras teams
        disciplined_teams_count = len(team_stats[team_stats['Avg_Extras'] < 10])
        st.markdown(f"- **{disciplined_teams_count} Teams** concede fewer than 10 extras per match on average.")

# =========================================
# LEFT-RIGHT HAND INDEX
# =========================================
elif metric_choice == "Left-Right Hand Index":
    st.subheader("🔄 Left-Right Hand Index")
    st.write("Analyze scoring when left-right batting pairs are at the crease")
    
    # Exclude super overs
    lr_df = fdf[fdf['innings'].isin([1, 2])].copy()
    
    if lr_df.empty:
        st.warning("No data for selected filters.")
    else:
        # Add batting hand to data
        lr_df['batter_hand'] = lr_df['batter'].apply(lambda x: get_player_batting_hand(x, player_data_cache))
        
        # Count how many players have known hand
        known_count = (lr_df['batter_hand'] != 'Unknown').sum()
        total_count = len(lr_df)
        st.caption(f"📊 Player hand mapping: {known_count:,}/{total_count:,} balls ({known_count/total_count*100:.1f}%) with known batting hand")
        
        # Debug: Show player cache info and sample matches
        with st.expander("🔍 Debug: Player Matching Info", expanded=(known_count == 0)):
            st.write(f"**Player cache size:** {len(player_data_cache)} entries")
            
            # Show any errors from loading
            if '_errors' in player_data_cache:
                st.error("**Errors during player data loading:**")
                for err in player_data_cache['_errors']:
                    st.write(f"  ❌ {err}")
            
            # Sample batters from the data
            sample_batters = lr_df['batter'].unique()[:10]
            st.write("**Sample batter matching:**")
            for batter in sample_batters:
                hand = get_player_batting_hand(batter, player_data_cache)
                st.write(f"  - `{batter}` → {hand}")
            
            # Show sample keys in cache
            st.write("**Sample cache keys (first 20):**")
            sample_keys = [k for k in list(player_data_cache.keys())[:20] if not k.startswith('_')]
            st.write(", ".join([f"`{k}`" for k in sample_keys]))
        
        tab1, tab2, tab3 = st.tabs(["📋 Inning-wise", "🏏 Match-wise", "📊 Overall"])
        
        with tab1:
            st.markdown("### Left vs Right Hand Performance by Innings")
            # Group by innings and batting hand
            hand_by_innings = lr_df.groupby(['innings', 'batter_hand'], observed=True).agg(
                Runs=('runs.batter', 'sum'),
                Balls=('is_valid_delivery', 'sum'),
                Dismissals=('wicket_count', 'sum'),
                Boundaries=('runs.batter', lambda x: ((x == 4) | (x == 6)).sum())
            ).reset_index()
            hand_by_innings['SR'] = (hand_by_innings['Runs'] / hand_by_innings['Balls'] * 100).round(2)
            hand_by_innings['Innings'] = hand_by_innings['innings'].map({1: '1st Innings', 2: '2nd Innings'})
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 1st Innings")
                first_inn = hand_by_innings[hand_by_innings['innings'] == 1]
                st.dataframe(first_inn[['batter_hand', 'Runs', 'Balls', 'SR', 'Dismissals', 'Boundaries']].rename(columns={'batter_hand': 'Batting Hand'}), use_container_width=True)
            with col2:
                st.markdown("#### 2nd Innings")
                second_inn = hand_by_innings[hand_by_innings['innings'] == 2]
                st.dataframe(second_inn[['batter_hand', 'Runs', 'Balls', 'SR', 'Dismissals', 'Boundaries']].rename(columns={'batter_hand': 'Batting Hand'}), use_container_width=True)
            
            # Chart
            if not hand_by_innings.empty:
                fig = px.bar(hand_by_innings[hand_by_innings['batter_hand'] != 'Unknown'], 
                            x='Innings', y='Runs', color='batter_hand', barmode='group',
                            title="Runs by Batting Hand per Innings",
                            color_discrete_map={'Left': '#2ecc71', 'Right': '#3498db'})
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            st.markdown("### Left vs Right Hand Performance by Match")
            # Group by match, team, and batting hand
            hand_by_match = lr_df.groupby(['match_id', 'teams', 'team', 'date', 'batter_hand'], observed=True).agg(
                Runs=('runs.batter', 'sum'),
                Balls=('is_valid_delivery', 'sum')
            ).reset_index()
            hand_by_match['SR'] = (hand_by_match['Runs'] / hand_by_match['Balls'] * 100).round(2)
            hand_by_match['Date'] = pd.to_datetime(hand_by_match['date']).dt.date
            hand_by_match['Team'] = hand_by_match['team'].astype(str)
            hand_by_match['Match'] = hand_by_match['teams'].astype(str)
            
            # Pivot to show L-R comparison per match
            hand_pivot = hand_by_match[hand_by_match['batter_hand'].isin(['Left', 'Right'])].pivot_table(
                index=['Match', 'Team', 'Date'],
                columns='batter_hand',
                values=['Runs', 'Balls', 'SR'],
                fill_value=0
            ).reset_index()
            hand_pivot.columns = ['Match', 'Team', 'Date'] + [f'{v}_{h}' for v, h in hand_pivot.columns[3:]]
            hand_pivot = hand_pivot.sort_values('Date', ascending=False)
            
            st.dataframe(hand_pivot.head(30), use_container_width=True)
        
        with tab3:
            st.markdown("### Overall Left vs Right Hand Comparison")
            # Overall summary
            hand_overall = lr_df.groupby('batter_hand', observed=True).agg(
                Total_Runs=('runs.batter', 'sum'),
                Total_Balls=('is_valid_delivery', 'sum'),
                Dismissals=('wicket_count', 'sum'),
                Fours=('runs.batter', lambda x: (x == 4).sum()),
                Sixes=('runs.batter', lambda x: (x == 6).sum()),
                Dots=('runs.batter', lambda x: (x == 0).sum())
            ).reset_index()
            hand_overall['SR'] = (hand_overall['Total_Runs'] / hand_overall['Total_Balls'] * 100).round(2)
            hand_overall['Avg'] = (hand_overall['Total_Runs'] / hand_overall['Dismissals'].replace(0, 1)).round(2)
            hand_overall['Dot%'] = (hand_overall['Dots'] / hand_overall['Total_Balls'] * 100).round(2)
            hand_overall = hand_overall.rename(columns={'batter_hand': 'Batting Hand'})
            
            st.dataframe(hand_overall, use_container_width=True)
            
            # Charts
            col1, col2 = st.columns(2)
            with col1:
                fig = px.pie(hand_overall[hand_overall['Batting Hand'] != 'Unknown'], 
                            values='Total_Runs', names='Batting Hand',
                            title="Run Distribution by Batting Hand",
                            color='Batting Hand',
                            color_discrete_map={'Left': '#2ecc71', 'Right': '#3498db'})
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig = px.bar(hand_overall[hand_overall['Batting Hand'] != 'Unknown'],
                            x='Batting Hand', y='SR', color='Batting Hand',
                            title="Strike Rate by Batting Hand",
                            color_discrete_map={'Left': '#2ecc71', 'Right': '#3498db'})
                st.plotly_chart(fig, use_container_width=True)

# =========================================
# PACE VS SPIN ANALYSIS
# =========================================
elif metric_choice == "Pace vs Spin Analysis":
    st.subheader("⚡ Pace vs Spin Analysis")
    st.write("Compare pace and spin bowling performance in each innings")
    
    # Exclude super overs
    ps_df = fdf[fdf['innings'].isin([1, 2])].copy()
    
    if ps_df.empty:
        st.warning("No data for selected filters.")
    else:
        # Add bowling type to data
        ps_df['bowling_type'] = ps_df['bowler'].apply(lambda x: get_player_bowling_type(x, player_data_cache))
        
        # Calculate bowler-conceded runs (excludes byes/leg-byes which don't count against bowler)
        ps_df['bowler_runs'] = ps_df['runs.batter'] + ps_df['wides'] + ps_df['no_balls']
        
        # Count mapping success
        known_count = (ps_df['bowling_type'] != 'Unknown').sum()
        total_count = len(ps_df)
        st.caption(f"📊 Bowler type mapping: {known_count:,}/{total_count:,} balls ({known_count/total_count*100:.1f}%) with known bowling type")
        
        tab1, tab2, tab3 = st.tabs(["📋 Inning-wise", "🏏 Match-wise", "📊 Overall"])
        
        with tab1:
            st.markdown("### Pace vs Spin Performance by Innings Type")
            # Group by innings and bowling type
            type_by_innings = ps_df.groupby(['innings', 'bowling_type'], observed=True).agg(
                Wickets=('wicket_count', 'sum'),
                Runs=('bowler_runs', 'sum'),  # Use bowler_runs instead of runs.total
                Balls=('is_valid_delivery', 'sum'),
                Dots=('bowler_runs', lambda x: (x == 0).sum())  # Dots based on bowler_runs
            ).reset_index()
            type_by_innings['Overs'] = (type_by_innings['Balls'] / 6).round(1)
            type_by_innings['ER'] = (type_by_innings['Runs'] / type_by_innings['Overs']).round(2)
            type_by_innings['Dot%'] = (type_by_innings['Dots'] / type_by_innings['Balls'] * 100).round(1)
            type_by_innings['Innings'] = type_by_innings['innings'].map({1: '1st Innings', 2: '2nd Innings'})
            
            # Display format: "Pace: 5/111 from 12 overs (ER: 9.25, Dot%: 37.8)"
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 1st Innings")
                for _, row in type_by_innings[type_by_innings['innings'] == 1].iterrows():
                    if row['bowling_type'] != 'Unknown':
                        emoji = "⚡" if row['bowling_type'] == 'Pace' else "🔄"
                        st.markdown(f"**{emoji} {row['bowling_type']}:** {int(row['Wickets'])}/{int(row['Runs'])} from {row['Overs']} overs (ER: {row['ER']}, Dot%: {row['Dot%']})")
            with col2:
                st.markdown("#### 2nd Innings")
                for _, row in type_by_innings[type_by_innings['innings'] == 2].iterrows():
                    if row['bowling_type'] != 'Unknown':
                        emoji = "⚡" if row['bowling_type'] == 'Pace' else "🔄"
                        st.markdown(f"**{emoji} {row['bowling_type']}:** {int(row['Wickets'])}/{int(row['Runs'])} from {row['Overs']} overs (ER: {row['ER']}, Dot%: {row['Dot%']})")
            
            # Chart
            if not type_by_innings.empty:
                fig = px.bar(type_by_innings[type_by_innings['bowling_type'] != 'Unknown'],
                            x='Innings', y='Wickets', color='bowling_type', barmode='group',
                            title="Wickets by Bowling Type per Innings",
                            color_discrete_map={'Pace': '#e74c3c', 'Spin': '#9b59b6'})
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            st.markdown("### Pace vs Spin by Match")
            # Group by match and bowling type
            type_by_match = ps_df.groupby(['match_id', 'teams', 'innings', 'date', 'bowling_type'], observed=True).agg(
                Wickets=('wicket_count', 'sum'),
                Runs=('bowler_runs', 'sum'),  # Use bowler_runs (excludes byes/leg-byes)
                Balls=('is_valid_delivery', 'sum'),
                Dots=('bowler_runs', lambda x: (x == 0).sum())
            ).reset_index()
            type_by_match['Overs'] = (type_by_match['Balls'] / 6).round(1)
            type_by_match['ER'] = (type_by_match['Runs'] / type_by_match['Overs'].replace(0, 1)).round(2)
            type_by_match['Dot%'] = (type_by_match['Dots'] / type_by_match['Balls'].replace(0, 1) * 100).round(1)
            type_by_match['Date'] = pd.to_datetime(type_by_match['date']).dt.date
            type_by_match['Match'] = type_by_match['teams'].astype(str)
            type_by_match['Innings'] = type_by_match['innings'].map({1: '1st', 2: '2nd'})
            type_by_match['Summary'] = type_by_match.apply(
                lambda r: f"{int(r['Wickets'])}/{int(r['Runs'])} ({r['Overs']}ov, {r['ER']}ER)" if r['bowling_type'] != 'Unknown' else '',
                axis=1
            )
            
            # Pivot to show Pace vs Spin side by side
            display_df = type_by_match[type_by_match['bowling_type'].isin(['Pace', 'Spin'])].pivot_table(
                index=['Match', 'Innings', 'Date'],
                columns='bowling_type',
                values='Summary',
                aggfunc='first'
            ).reset_index()
            display_df = display_df.sort_values('Date', ascending=False)
            
            st.dataframe(display_df.head(40), use_container_width=True)
        
        with tab3:
            st.markdown("### Overall Pace vs Spin Comparison")
            # Overall summary
            type_overall = ps_df.groupby('bowling_type', observed=True).agg(
                Wickets=('wicket_count', 'sum'),
                Runs=('bowler_runs', 'sum'),  # Use bowler_runs (excludes byes/leg-byes)
                Balls=('is_valid_delivery', 'sum'),
                Dots=('bowler_runs', lambda x: (x == 0).sum()),
                Matches=('match_id', 'nunique')
            ).reset_index()
            type_overall['Overs'] = (type_overall['Balls'] / 6).round(1)
            type_overall['ER'] = (type_overall['Runs'] / type_overall['Overs']).round(2)
            type_overall['Dot%'] = (type_overall['Dots'] / type_overall['Balls'] * 100).round(1)
            type_overall['Avg'] = (type_overall['Runs'] / type_overall['Wickets'].replace(0, 1)).round(2)
            type_overall['SR'] = (type_overall['Balls'] / type_overall['Wickets'].replace(0, 1)).round(2)
            type_overall = type_overall.rename(columns={'bowling_type': 'Bowling Type'})
            
            st.dataframe(type_overall, use_container_width=True)
            
            # Display in user's format
            st.markdown("---")
            st.markdown("### Summary")
            for _, row in type_overall.iterrows():
                if row['Bowling Type'] != 'Unknown':
                    emoji = "⚡" if row['Bowling Type'] == 'Pace' else "🔄"
                    st.markdown(f"**{emoji} {row['Bowling Type']}:** {int(row['Wickets'])}/{int(row['Runs'])} from {row['Overs']} overs (ER: {row['ER']}, Dot%: {row['Dot%']})")
            
            # Charts
            col1, col2 = st.columns(2)
            with col1:
                fig = px.pie(type_overall[type_overall['Bowling Type'] != 'Unknown'],
                            values='Wickets', names='Bowling Type',
                            title="Wickets Distribution",
                            color='Bowling Type',
                            color_discrete_map={'Pace': '#e74c3c', 'Spin': '#9b59b6'})
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig = px.bar(type_overall[type_overall['Bowling Type'] != 'Unknown'],
                            x='Bowling Type', y='ER', color='Bowling Type',
                            title="Economy Rate Comparison",
                            color_discrete_map={'Pace': '#e74c3c', 'Spin': '#9b59b6'})
                st.plotly_chart(fig, use_container_width=True)

# =========================================
# SUPER OVER ANALYSIS
# =========================================
elif metric_choice == "Super Over Analysis":
    st.subheader("🔥 Super Over Analysis")
    st.write("Analysis of super over performances across matches")
    
    # Filter super over innings (innings >= 3) - use FULL df, not filtered fdf
    super_overs = df[df['innings'] >= 3].copy()
    
    # Apply league/year filters only if selected
    if selected_leagues:
        super_overs = super_overs[super_overs['league'].isin(selected_leagues)]
    if selected_years:
        super_overs = super_overs[super_overs['year'].isin(selected_years)]
    
    if super_overs.empty:
        st.info("No super over matches found for selected filters.")
    else:
        # Load eliminator data from JSON files (for tied matches, eliminator = winner)
        @st.cache_data
        def load_eliminators():
            import os
            from glob import glob
            import json
            elim_map = {}
            files = glob(os.path.join(JSON_DIR, "*.json"))
            for file in files:
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    match_id = os.path.basename(file).split('.')[0]
                    outcome = data.get('info', {}).get('outcome', {})
                    # For super overs, winner is in 'eliminator' field
                    winner = outcome.get('winner') or outcome.get('eliminator')
                    elim_map[match_id] = winner
                except Exception:
                    continue
            return elim_map
        
        eliminator_map = load_eliminators()
        
        # Get unique super over matches
        so_matches = super_overs['match_id'].unique()
        st.write(f"**Total Super Over Matches: {len(so_matches)}**")
        
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Match List", "🏏 Top Batters", "🎯 Top Bowlers", "📊 Team Stats"])
        
        with tab1:
            # Match list with super over details
            match_details = []
            for match_id in so_matches:
                match_so = super_overs[super_overs['match_id'] == match_id]
                match_info = df[df['match_id'] == match_id].iloc[0]
                
                for inn in match_so['innings'].unique():
                    inn_data = match_so[match_so['innings'] == inn]
                    team = inn_data['team'].iloc[0] if not inn_data.empty else 'Unknown'
                    runs = inn_data['runs.total'].sum()
                    wickets = inn_data['wicket_count'].sum()
                    balls = inn_data['is_valid_delivery'].sum()
                    
                    match_details.append({
                        'Match': str(match_info['teams']),
                        'Date': pd.to_datetime(match_info['date']).date(),
                        'League': str(match_info['league']),
                        'Team': str(team),
                        'SO Runs': runs,
                        'SO Wickets': wickets,
                        'SO Balls': balls,
                        'match_id': match_id
                    })
            
            match_df = pd.DataFrame(match_details)
            if not match_df.empty:
                # Add winner info from eliminator map (handles tied matches correctly)
                match_df['Winner'] = match_df['match_id'].astype(str).map(eliminator_map)
                match_df = match_df.sort_values('Date', ascending=False)
                st.dataframe(match_df[['Match', 'Date', 'League', 'Team', 'SO Runs', 'SO Wickets', 'Winner']], 
                           use_container_width=True)
        
        with tab2:
            # Top batters in super overs
            batter_stats = super_overs.groupby('batter', observed=True).agg(
                SO_Matches=('match_id', 'nunique'),
                SO_Runs=('runs.batter', 'sum'),
                SO_Balls=('is_valid_delivery', 'sum'),
                SO_4s=('runs.batter', lambda x: (x == 4).sum()),
                SO_6s=('runs.batter', lambda x: (x == 6).sum())
            ).reset_index()
            batter_stats['SO_SR'] = (batter_stats['SO_Runs'] / batter_stats['SO_Balls'] * 100).replace([np.inf, np.nan], 0).round(1)
            batter_stats = batter_stats.rename(columns={'batter': 'Batter'})
            batter_stats = batter_stats.sort_values('SO_Runs', ascending=False)
            
            st.dataframe(batter_stats.head(20), use_container_width=True)
            
            fig = px.bar(batter_stats.head(15), x='Batter', y='SO_Runs', 
                        color='SO_SR', color_continuous_scale='RdYlGn',
                        title="Top Super Over Run Scorers")
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            # Top bowlers in super overs
            bowler_stats = super_overs.groupby('bowler', observed=True).agg(
                SO_Matches=('match_id', 'nunique'),
                SO_Runs_Conceded=('runs.total', 'sum'),
                SO_Wickets=('wicket_count', 'sum'),
                SO_Balls=('is_valid_delivery', 'sum')
            ).reset_index()
            bowler_stats['SO_Econ'] = (bowler_stats['SO_Runs_Conceded'] / (bowler_stats['SO_Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
            bowler_stats = bowler_stats.rename(columns={'bowler': 'Bowler'})
            bowler_stats = bowler_stats.sort_values('SO_Wickets', ascending=False)
            
            st.dataframe(bowler_stats.head(20), use_container_width=True)
            
            fig = px.bar(bowler_stats.head(15), x='Bowler', y='SO_Wickets',
                        color='SO_Econ', color_continuous_scale='RdYlGn_r',
                        title="Top Super Over Wicket Takers")
            fig.update_xaxes(tickangle=45)
            st.plotly_chart(fig, use_container_width=True)
        
        with tab4:
            # Team super over win %
            # Get SO match results using eliminator_map
            so_team_stats = []
            for match_id in so_matches:
                match_data = df[df['match_id'] == match_id]
                # Use eliminator_map for correct winner (handles tied matches)
                winner = eliminator_map.get(str(match_id))
                teams_str = match_data['teams'].iloc[0] if not match_data.empty else ''
                
                # Parse teams
                parts = str(teams_str).replace(' vs ', ' v ').split(' v ')
                if len(parts) == 2:
                    for team in parts:
                        team = team.strip()
                        so_team_stats.append({
                            'Team': team,
                            'Played': 1,
                            'Won': 1 if team == winner else 0
                        })
            
            if so_team_stats:
                team_df = pd.DataFrame(so_team_stats)
                team_summary = team_df.groupby('Team').agg(
                    SO_Played=('Played', 'sum'),
                    SO_Won=('Won', 'sum')
                ).reset_index()
                team_summary['SO_Win%'] = (team_summary['SO_Won'] / team_summary['SO_Played'] * 100).round(1)
                team_summary = team_summary.sort_values('SO_Played', ascending=False)
                
                st.dataframe(team_summary, use_container_width=True)
                
                fig = px.bar(team_summary, x='Team', y='SO_Win%', 
                            color='SO_Played', color_continuous_scale='Blues',
                            title="Super Over Win % by Team")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)


# =========================================
# INNINGS PROGRESSION
# =========================================
elif metric_choice == "Innings Progression":
    st.subheader("📈 Innings Progression")
    st.write("Phase-by-phase breakdown of innings")
    st.info("**Phases:** Powerplay (Overs 1-6), Middle (Overs 7-15), Death (Overs 16-20)")
    
    # Filter to regular innings only (exclude super overs)
    regular_innings = fdf[fdf['innings'].isin([1, 2])].copy()
    
    if regular_innings.empty:
        st.info("No match data available for selected filters.")
    else:
        # Helper function for phase stats
        def get_phase_stats(data, phase_name, over_start, over_end):
            phase_data = data[(data['over'] >= over_start) & (data['over'] <= over_end)]
            if phase_data.empty:
                return None
            runs = phase_data['runs.total'].sum()
            wickets = phase_data['team_wicket_count'].sum() if 'team_wicket_count' in phase_data.columns else phase_data['wicket_count'].sum()
            balls = phase_data['is_valid_delivery'].sum()
            rr = (runs / (balls / 6)) if balls > 0 else 0
            return {
                'Phase': phase_name,
                'Overs': f"{over_start+1}-{over_end+1}",
                'Runs': int(runs),
                'Wickets': int(wickets),
                'Balls': int(balls),
                'RR': round(rr, 2)
            }
        
        view_mode = st.radio("View Mode", ["📊 All Matches Summary", "🔍 Single Match Detail"], horizontal=True)
        
        if view_mode == "📊 All Matches Summary":
            # Show all matches at once grouped by team
            st.markdown("### All Matches Phase Breakdown")
            
            # Get unique matches and teams
            matches = regular_innings.groupby(['match_id', 'teams', 'date', 'team', 'innings'], observed=True).size().reset_index()
            
            all_match_phases = []
            for _, row in matches.iterrows():
                match_id = row['match_id']
                inn_num = row['innings']
                team = row['team']
                match_date = pd.to_datetime(row['date']).strftime('%d %b %Y')
                opponent = str(row['teams']).replace(' vs ', ' v ').split(' v ')
                opponent = [t.strip() for t in opponent if t.strip() != str(team)]
                opponent = opponent[0] if opponent else 'Unknown'
                
                inn_data = regular_innings[(regular_innings['match_id'] == match_id) & 
                                           (regular_innings['innings'] == inn_num)]
                
                pp = get_phase_stats(inn_data, 'Powerplay', 0, 5)
                mid = get_phase_stats(inn_data, 'Middle', 6, 14)
                death = get_phase_stats(inn_data, 'Death', 15, 19)
                
                total_runs = inn_data['runs.total'].sum()
                total_wkts = inn_data['team_wicket_count'].sum() if 'team_wicket_count' in inn_data.columns else inn_data['wicket_count'].sum()
                
                all_match_phases.append({
                    'Date': match_date,
                    'Team': str(team),
                    'Opponent': opponent,
                    'Innings': '1st' if inn_num == 1 else '2nd',
                    'Total': f"{int(total_runs)}/{int(total_wkts)}",
                    'PP': f"{pp['Runs']}/{pp['Wickets']} ({pp['RR']})" if pp else '-',
                    'Middle': f"{mid['Runs']}/{mid['Wickets']} ({mid['RR']})" if mid else '-',
                    'Death': f"{death['Runs']}/{death['Wickets']} ({death['RR']})" if death else '-',
                    'PP_Runs': pp['Runs'] if pp else 0,
                    'Mid_Runs': mid['Runs'] if mid else 0,
                    'Death_Runs': death['Runs'] if death else 0,
                })
            
            phase_df = pd.DataFrame(all_match_phases)
            phase_df = phase_df.sort_values('Date', ascending=False)
            
            # Display table
            st.dataframe(phase_df[['Date', 'Team', 'Opponent', 'Innings', 'Total', 'PP', 'Middle', 'Death']], 
                        use_container_width=True)
            
            # Summary stats
            st.markdown("---")
            st.markdown("### Average Phase Performance")
            
            # Calculate averages by team
            if selected_teams:
                team_filter = phase_df['Team'].isin([str(t) for t in selected_teams])
                summary_df = phase_df[team_filter].copy()
            else:
                summary_df = phase_df.copy()
            
            if not summary_df.empty:
                team_summary = summary_df.groupby('Team').agg(
                    Matches=('Date', 'count'),
                    Avg_PP_Runs=('PP_Runs', 'mean'),
                    Avg_Mid_Runs=('Mid_Runs', 'mean'),
                    Avg_Death_Runs=('Death_Runs', 'mean')
                ).reset_index()
                team_summary['Avg_PP_Runs'] = team_summary['Avg_PP_Runs'].round(1)
                team_summary['Avg_Mid_Runs'] = team_summary['Avg_Mid_Runs'].round(1)
                team_summary['Avg_Death_Runs'] = team_summary['Avg_Death_Runs'].round(1)
                
                st.dataframe(team_summary, use_container_width=True)
                
                # Chart
                import plotly.graph_objects as go
                fig = go.Figure()
                for team in team_summary['Team'].unique():
                    team_data = team_summary[team_summary['Team'] == team].iloc[0]
                    fig.add_trace(go.Bar(
                        name=str(team),
                        x=['Powerplay', 'Middle', 'Death'],
                        y=[team_data['Avg_PP_Runs'], team_data['Avg_Mid_Runs'], team_data['Avg_Death_Runs']],
                        text=[team_data['Avg_PP_Runs'], team_data['Avg_Mid_Runs'], team_data['Avg_Death_Runs']],
                        textposition='outside'
                    ))
                fig.update_layout(title="Average Runs by Phase", barmode='group')
                st.plotly_chart(fig, use_container_width=True)
        
        else:
            # Single match detail view (original functionality)
            match_options = regular_innings.groupby(['match_id', 'teams', 'date'], observed=True).size().reset_index()
            match_options['Match Label'] = match_options.apply(
                lambda r: f"{r['teams']} ({pd.to_datetime(r['date']).strftime('%d %b %Y')})", axis=1
            )
            match_options = match_options.sort_values('date', ascending=False)
            
            selected_match = st.selectbox("Select Match", match_options['Match Label'].tolist())
            
            if selected_match:
                match_id = match_options[match_options['Match Label'] == selected_match]['match_id'].iloc[0]
                match_data = regular_innings[regular_innings['match_id'] == match_id]
                
                col1, col2 = st.columns(2)
                
                for idx, innings_num in enumerate([1, 2]):
                    inn_data = match_data[match_data['innings'] == innings_num]
                    if inn_data.empty:
                        continue
                    
                    team = inn_data['team'].iloc[0]
                    
                    phases = [
                        get_phase_stats(inn_data, 'Powerplay', 0, 5),
                        get_phase_stats(inn_data, 'Middle', 6, 14),
                        get_phase_stats(inn_data, 'Death', 15, 19)
                    ]
                    phases = [p for p in phases if p]
                    
                    with col1 if idx == 0 else col2:
                        st.markdown(f"### Innings {innings_num}: {team}")
                        
                        total_runs = inn_data['runs.total'].sum()
                        total_wickets = inn_data['team_wicket_count'].sum() if 'team_wicket_count' in inn_data.columns else inn_data['wicket_count'].sum()
                        st.markdown(f"**Total: {int(total_runs)}/{int(total_wickets)}**")
                        
                        for phase in phases:
                            st.markdown(f"""
                            **{phase['Phase']} (Overs {phase['Overs']}):** {phase['Runs']}/{phase['Wickets']} (RR: {phase['RR']})
                            """)
                        
                        # Progress chart
                        if phases:
                            phase_df = pd.DataFrame(phases)
                            fig = px.bar(phase_df, x='Phase', y='Runs', 
                                        text='Runs', color='RR',
                                        color_continuous_scale='RdYlGn',
                                        title=f"{team} Phase Breakdown")
                            fig.update_traces(textposition='outside')
                            st.plotly_chart(fig, use_container_width=True)


# =========================================
# FRANCHISE DEBUT TRACKER
# =========================================
elif metric_choice == "Franchise Debut Tracker":
    st.subheader("🆕 Franchise Debut Tracker")
    st.write("Track player debuts across different franchises")
    
    # Apply league filter first - use filtered data based on sidebar selection
    if selected_leagues:
        filtered_df = df[df['league'].isin(selected_leagues)]
        st.info(f"Showing data for: {', '.join(selected_leagues)}")
    else:
        filtered_df = df.copy()
        st.info("No league selected - showing all leagues. Select a league to filter teams.")
    
    # Get player-team first appearances (filtered by league)
    # For batters: 'team' = batting team = batter's team (correct)
    player_team_first = filtered_df.groupby(['batter', 'team', 'league'], observed=True).agg(
        First_Match_Date=('date', 'min'),
        Matches_Played=('match_id', 'nunique')
    ).reset_index()
    player_team_first = player_team_first.rename(columns={'batter': 'Player', 'team': 'Team', 'league': 'League'})
    
    # For bowlers: use 'bowling_team' = bowler's actual team
    bowler_team_first = filtered_df.groupby(['bowler', 'bowling_team', 'league'], observed=True).agg(
        First_Match_Date=('date', 'min'),
        Matches_Played=('match_id', 'nunique')
    ).reset_index()
    bowler_team_first = bowler_team_first.rename(columns={'bowler': 'Player', 'bowling_team': 'Team', 'league': 'League'})
    
    # Combine batter and bowler data
    all_player_team = pd.concat([player_team_first, bowler_team_first]).groupby(['Player', 'Team', 'League'], observed=True).agg(
        First_Match_Date=('First_Match_Date', 'min'),
        Matches_Played=('Matches_Played', 'max')
    ).reset_index()
    
    # Get teams in selected leagues only
    league_teams = sorted(filtered_df['team'].unique())
    
    tab1, tab2 = st.tabs(["🔍 Player Search", "📋 Debut List"])
    
    with tab1:
        # Search for a player - show only players from filtered leagues
        all_players = sorted(all_player_team['Player'].unique())
        selected_player = st.selectbox("Select Player", all_players, key="debut_player")
        
        if selected_player:
            player_data = all_player_team[all_player_team['Player'] == selected_player]
            teams_played = [str(t) for t in player_data['Team'].tolist()]
            
            st.markdown(f"### {selected_player}")
            st.write(f"**Teams played for in selected league(s):** {len(teams_played)}")
            
            # Show teams played with league
            player_data_sorted = player_data.sort_values('First_Match_Date')
            player_data_sorted['First_Match_Date'] = pd.to_datetime(player_data_sorted['First_Match_Date']).dt.date
            st.dataframe(player_data_sorted[['Team', 'League', 'First_Match_Date', 'Matches_Played']], 
                        use_container_width=True)
            
            # Show teams NOT played for (only from filtered leagues)
            not_played = [str(t) for t in league_teams if str(t) not in teams_played]
            
            if not_played:
                st.markdown(f"**Teams yet to debut for ({len(not_played)}):**")
                cols = st.columns(3)
                for i, team in enumerate(sorted(not_played)):
                    cols[i % 3].write(f"• {team}")
            else:
                st.success("Has played for all teams in selected league(s)!")
    
    with tab2:
        # Recent debuts
        st.markdown("### Recent Franchise Debuts")
        
        if selected_years:
            year_filter = all_player_team['First_Match_Date'].dt.year.isin(selected_years)
            recent_debuts = all_player_team[year_filter].copy()
        else:
            recent_debuts = all_player_team.copy()
        
        recent_debuts = recent_debuts.sort_values('First_Match_Date', ascending=False)
        recent_debuts['First_Match_Date'] = pd.to_datetime(recent_debuts['First_Match_Date']).dt.date
        
        st.dataframe(recent_debuts.head(100)[['Player', 'Team', 'League', 'First_Match_Date', 'Matches_Played']], 
                    use_container_width=True)
        
        # Stats summary
        st.markdown("---")
        st.markdown("### Debut Stats by Team")
        
        team_debuts = recent_debuts.groupby('Team', observed=True).size().reset_index(name='Total_Debuts')
        team_debuts = team_debuts.sort_values('Total_Debuts', ascending=False)
        
        fig = px.bar(team_debuts.head(15), x='Team', y='Total_Debuts',
                    title="Teams with Most Player Debuts")
        fig.update_xaxes(tickangle=45)
        st.plotly_chart(fig, use_container_width=True)

# =========================================
# SR COMPARISON (YEAR-WISE)
# =========================================
elif metric_choice == "SR Comparison (Year-wise)":
    st.subheader("SR Comparison (Year-wise)")
    st.write("Batter strike rate comparison across leagues and seasons with ball-range buckets")

    sr_col1, sr_col2, sr_col3, sr_col4 = st.columns([2, 1, 1, 2])
    with sr_col1:
        aggregate_across_teams = st.checkbox(
            "Aggregate across teams (ignore Team filter)",
            value=True,
            key="sr_aggregate_teams",
            help="Useful when a player has represented multiple teams — stats are merged."
        )
    with sr_col2:
        min_sr_balls = st.number_input("Min Balls", min_value=1, max_value=300, value=20, step=1, key="sr_min_balls")
    with sr_col3:
        top_n_sr = st.number_input("Top N in chart", min_value=5, max_value=50, value=15, step=1, key="sr_top_n")
    with sr_col4:
        sr_view_mode = st.radio("View Mode", ["Year-wise", "Overall (All Seasons)"], key="sr_view_mode", horizontal=True)

    sr_source_df = fdf_no_team.copy() if aggregate_across_teams else fdf.copy()
    sr_table = yearwise_batter_sr_comparison(
        sr_source_df,
        aggregate_across_teams=aggregate_across_teams,
        min_balls=int(min_sr_balls),
        include_year=(sr_view_mode == "Year-wise")
    )

    # Player filter (applies to both view modes)
    if not sr_table.empty:
        all_sr_players = sorted(sr_table['Name'].dropna().astype(str).unique())
        sr_player_filter = st.multiselect("Filter by Player(s) — leave empty to show all", all_sr_players, key="sr_player_filter")
        if sr_player_filter:
            sr_table = sr_table[sr_table['Name'].isin(sr_player_filter)]

    if sr_table.empty:
        st.info("No SR comparison data available for the selected filters.")
    else:
        # Helper columns
        _bucket_cols = ['1-10 SR', '11-20 SR', '21-30 SR', '31-40 SR', '41-50 SR', '51-60 SR']
        _base_cols   = ['Name', 'Average', 'Strike Rate', 'Balls/Inn'] + _bucket_cols

        leagues_in_sr = sorted(sr_table['League'].dropna().unique())
        league_tabs = st.tabs([str(lg) for lg in leagues_in_sr])

        for i, lg in enumerate(leagues_in_sr):
            with league_tabs[i]:
                lg_df = sr_table[sr_table['League'] == lg].copy()

                if sr_view_mode == "Year-wise":
                    year_options = sorted(lg_df['Season'].dropna().unique(), reverse=True)
                    selected_sr_years = st.multiselect(
                        "Season(s) — select one or more",
                        year_options,
                        default=list(year_options[:1]),
                        key=f"sr_season_{i}",
                        help="Pick multiple seasons to see each year separately or compare side-by-side."
                    )
                    active_years = selected_sr_years if selected_sr_years else list(year_options)

                    # Build per-year display cols (add Team when not aggregating)
                    def _make_display_cols(include_season=False):
                        cols = list(_base_cols)
                        if not aggregate_across_teams and 'Team' in lg_df.columns:
                            cols = ['Name', 'Team', 'Average', 'Strike Rate', 'Balls/Inn'] + _bucket_cols
                        if include_season:
                            cols = ['Season'] + cols
                        return cols

                    if len(active_years) == 1:
                        # Single year — plain table + chart, no sub-tabs needed
                        yr_data = lg_df[lg_df['Season'] == active_years[0]].copy()
                        dcols = _make_display_cols(include_season=False)
                        st.dataframe(
                            yr_data[[c for c in dcols if c in yr_data.columns]].sort_values('Strike Rate', ascending=False),
                            use_container_width=True
                        )
                        chart_df = yr_data.sort_values('Strike Rate', ascending=False).head(int(top_n_sr))
                        if not chart_df.empty:
                            fig = px.bar(chart_df, x='Name', y='Strike Rate',
                                         color='Average', color_continuous_scale='Viridis',
                                         title=f"{lg} {active_years[0]} — Strike Rate Comparison",
                                         hover_data=['Balls/Inn'] + _bucket_cols)
                            fig.update_xaxes(tickangle=45)
                            st.plotly_chart(fig, use_container_width=True)
                    else:
                        # Multiple years — one sub-tab per year + a Compare tab
                        year_tab_labels = [str(y) for y in active_years] + ["⚖️ Compare"]
                        year_sub_tabs = st.tabs(year_tab_labels)

                        for j, yr in enumerate(active_years):
                            with year_sub_tabs[j]:
                                yr_data = lg_df[lg_df['Season'] == yr].copy()
                                if yr_data.empty:
                                    st.info(f"No data for {yr}.")
                                    continue

                                dcols = _make_display_cols(include_season=False)
                                st.markdown(f"**{lg} — Season {yr}**")
                                st.dataframe(
                                    yr_data[[c for c in dcols if c in yr_data.columns]].sort_values('Strike Rate', ascending=False),
                                    use_container_width=True
                                )
                                chart_df = yr_data.sort_values('Strike Rate', ascending=False).head(int(top_n_sr))
                                if not chart_df.empty:
                                    fig = px.bar(chart_df, x='Name', y='Strike Rate',
                                                 color='Average', color_continuous_scale='Viridis',
                                                 title=f"{lg} {yr} — Strike Rate",
                                                 hover_data=['Balls/Inn'] + _bucket_cols)
                                    fig.update_xaxes(tickangle=45)
                                    st.plotly_chart(fig, use_container_width=True)

                                # Ball-bucket breakdown per player for this year
                                if not yr_data.empty:
                                    st.markdown("**Ball-range SR Buckets**")
                                    bucket_melt = yr_data[['Name'] + _bucket_cols].melt(
                                        id_vars='Name', var_name='Ball Range', value_name='SR'
                                    )
                                    fig_b = px.bar(
                                        bucket_melt[bucket_melt['SR'] > 0].sort_values('SR', ascending=False),
                                        x='Ball Range', y='SR', color='Name', barmode='group',
                                        title=f"{lg} {yr} — Ball-range SR Buckets"
                                    )
                                    fig_b.update_xaxes(tickangle=0)
                                    st.plotly_chart(fig_b, use_container_width=True)

                        # Compare tab — side-by-side grouped bars, all years together
                        with year_sub_tabs[-1]:
                            compare_df = lg_df[lg_df['Season'].isin(active_years)].copy()
                            if compare_df.empty:
                                st.info("No data for selected seasons.")
                            else:
                                dcols_cmp = _make_display_cols(include_season=True)
                                st.markdown("**All Selected Seasons — Side-by-side**")
                                st.dataframe(
                                    compare_df[[c for c in dcols_cmp if c in compare_df.columns]].sort_values(
                                        ['Name', 'Season'], ascending=[True, True]
                                    ),
                                    use_container_width=True
                                )

                                # Grouped bar: SR by player, coloured by season
                                season_label = ", ".join(str(y) for y in active_years)
                                chart_cmp = compare_df.copy()
                                chart_cmp['Season'] = chart_cmp['Season'].astype(str)
                                fig_cmp = px.bar(
                                    chart_cmp.sort_values('Strike Rate', ascending=False),
                                    x='Name', y='Strike Rate', color='Season',
                                    barmode='group',
                                    title=f"{lg} {season_label} — Year-wise SR Comparison",
                                    hover_data=['Average', 'Balls/Inn'] + _bucket_cols
                                )
                                fig_cmp.update_xaxes(tickangle=45)
                                st.plotly_chart(fig_cmp, use_container_width=True)

                                # Bucket heatmap per player per year
                                if sr_player_filter:
                                    st.markdown("**Ball-bucket progression across seasons (selected players)**")
                                    for player in sr_player_filter:
                                        p_df = compare_df[compare_df['Name'] == player].copy()
                                        if p_df.empty:
                                            continue
                                        p_melt = p_df[['Season'] + _bucket_cols].melt(
                                            id_vars='Season', var_name='Ball Range', value_name='SR'
                                        )
                                        p_melt['Season'] = p_melt['Season'].astype(str)
                                        fig_p = px.line(
                                            p_melt, x='Ball Range', y='SR',
                                            color='Season', markers=True,
                                            title=f"{player} — Ball-range SR by Season"
                                        )
                                        st.plotly_chart(fig_p, use_container_width=True)

                else:
                    # Overall (All Seasons) — aggregate, no year split
                    view_df = lg_df.copy()
                    dcols = list(_base_cols)
                    if not aggregate_across_teams and 'Team' in view_df.columns:
                        dcols = ['Name', 'Team', 'Average', 'Strike Rate', 'Balls/Inn'] + _bucket_cols
                    st.dataframe(
                        view_df[[c for c in dcols if c in view_df.columns]].sort_values('Strike Rate', ascending=False),
                        use_container_width=True
                    )
                    chart_df = view_df.sort_values('Strike Rate', ascending=False).head(int(top_n_sr)).copy()
                    if not chart_df.empty:
                        fig = px.bar(chart_df, x='Name', y='Strike Rate',
                                     color='Average', color_continuous_scale='Viridis',
                                     title=f"{lg} — Overall Strike Rate Comparison (All Seasons)",
                                     hover_data=['Balls/Inn'] + _bucket_cols)
                        fig.update_xaxes(tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)


# =========================================
# FASTEST 50s & 100s (PLAYER)
# =========================================
elif metric_choice == "Fastest 50s & 100s (Player)":
    st.subheader("⚡ Fastest 50s & 100s (Player)")
    st.write("Fastest individual batting milestones by legal balls faced — filter IPL via sidebar, then by player below.")

    m1_df = fdf.copy()
    if m1_df.empty:
        st.warning("No data for selected filters.")
    else:
        # In-section player filter
        all_batters = sorted(m1_df['batter'].dropna().astype(str).unique())
        sel_players = st.multiselect("Filter by Player(s)", all_batters, key="m1_players")

        with st.spinner("Computing fastest milestones..."):
            milestones_df = fastest_individual_milestones(m1_df)

        if milestones_df.empty:
            st.info("No 50+ innings found for the selected filters.")
        else:
            if sel_players:
                milestones_df = milestones_df[milestones_df['Batter'].isin(sel_players)]

            tab_50, tab_100 = st.tabs(["🏏 Fastest 50s", "💯 Fastest 100s"])

            with tab_50:
                st.markdown("### Fastest 50s — sorted by balls faced (ascending)")
                df_50 = milestones_df[milestones_df['Balls to 50'].notna()].sort_values('Balls to 50').copy()
                df_50['Balls to 50'] = df_50['Balls to 50'].astype(int)
                df_50['Batter_Display'] = df_50['Batter'] + df_50['Not Out'].apply(lambda x: '' if x == '' else ' *')
                display_50 = df_50[['Date', 'Season', 'Match', 'Inning', 'Batting Team',
                                    'Batter', 'Balls to 50', 'Total Runs', 'Total Balls', 'SR', 'Not Out']].copy()
                display_50 = display_50.reset_index(drop=True)
                display_50.index += 1
                st.dataframe(display_50.head(200), use_container_width=True)

                if len(df_50) >= 5:
                    fig = px.bar(
                        df_50.head(20),
                        x='Batter', y='Balls to 50', color='Batting Team',
                        title='Top 20 Fastest 50s — Balls Faced',
                        text='Balls to 50'
                    )
                    fig.update_layout(xaxis_tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)

            with tab_100:
                st.markdown("### Fastest 100s — sorted by balls faced (ascending)")
                df_100 = milestones_df[milestones_df['Balls to 100'].notna()].sort_values('Balls to 100').copy()
                if df_100.empty:
                    st.info("No 100+ innings found for the selected filters.")
                else:
                    df_100['Balls to 100'] = df_100['Balls to 100'].astype(int)
                    display_100 = df_100[['Date', 'Season', 'Match', 'Inning', 'Batting Team',
                                         'Batter', 'Balls to 100', 'Total Runs', 'Total Balls', 'SR', 'Not Out']].copy()
                    display_100 = display_100.reset_index(drop=True)
                    display_100.index += 1
                    st.dataframe(display_100.head(200), use_container_width=True)

                    if len(df_100) >= 5:
                        fig = px.bar(
                            df_100.head(20),
                            x='Batter', y='Balls to 100', color='Batting Team',
                            title='Top 20 Fastest 100s — Balls Faced',
                            text='Balls to 100'
                        )
                        fig.update_layout(xaxis_tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)


# =========================================
# FASTEST TEAM 50 & 100
# =========================================
elif metric_choice == "Fastest Team 50 & 100":
    st.subheader("🚀 Fastest Team 50 & 100")
    st.write("Team milestones by legal balls (runs include extras: byes, leg-byes). Filter IPL via sidebar, then by team below.")

    m2_df = fdf.copy()
    if m2_df.empty:
        st.warning("No data for selected filters.")
    else:
        all_teams_m2 = sorted(m2_df['team'].dropna().astype(str).unique())
        sel_teams_m2 = st.multiselect("Filter by Batting Team(s)", all_teams_m2, key="m2_teams")

        with st.spinner("Computing fastest team milestones..."):
            team_miles_df = fastest_team_milestones(m2_df)

        if team_miles_df.empty:
            st.info("No team innings reaching 50 found for the selected filters.")
        else:
            if sel_teams_m2:
                team_miles_df = team_miles_df[team_miles_df['Batting Team'].isin(sel_teams_m2)]

            tab_t50, tab_t100 = st.tabs(["🏏 Fastest Team 50s", "💯 Fastest Team 100s"])

            with tab_t50:
                st.markdown("### Fastest Team 50s — sorted by balls faced (ascending)")
                df_t50 = team_miles_df[team_miles_df['Balls to 50'].notna()].sort_values('Balls to 50').copy()
                df_t50['Balls to 50'] = df_t50['Balls to 50'].astype(int)
                display_t50 = df_t50[['Date', 'Season', 'Team 1', 'Team 2', 'Inning No',
                                      'Batting Team', 'Balls to 50', 'Total Runs', 'Total Balls']].copy()
                display_t50 = display_t50.reset_index(drop=True)
                display_t50.index += 1
                st.dataframe(display_t50.head(300), use_container_width=True)

                st.markdown("#### 🏆 Top 10 Fastest Team 50s")
                st.dataframe(display_t50.head(10), use_container_width=True)

                if len(df_t50) >= 5:
                    fig = px.bar(
                        df_t50.head(20),
                        x='Batting Team', y='Balls to 50', color='Season',
                        title='Top 20 Fastest Team 50s — Balls Faced',
                        text='Balls to 50',
                        hover_data=['Date', 'Team 1', 'Team 2', 'Total Runs']
                    )
                    fig.update_layout(xaxis_tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)

            with tab_t100:
                st.markdown("### Fastest Team 100s — sorted by balls faced (ascending)")
                df_t100 = team_miles_df[team_miles_df['Balls to 100'].notna()].sort_values('Balls to 100').copy()
                if df_t100.empty:
                    st.info("No team innings reaching 100 found for the selected filters.")
                else:
                    df_t100['Balls to 100'] = df_t100['Balls to 100'].astype(int)
                    display_t100 = df_t100[['Date', 'Season', 'Team 1', 'Team 2', 'Inning No',
                                           'Batting Team', 'Balls to 100', 'Total Runs', 'Total Balls']].copy()
                    display_t100 = display_t100.reset_index(drop=True)
                    display_t100.index += 1
                    st.dataframe(display_t100.head(300), use_container_width=True)

                    st.markdown("#### 🏆 Top 10 Fastest Team 100s")
                    st.dataframe(display_t100.head(10), use_container_width=True)

                    if len(df_t100) >= 5:
                        fig = px.bar(
                            df_t100.head(20),
                            x='Batting Team', y='Balls to 100', color='Season',
                            title='Top 20 Fastest Team 100s — Balls Faced',
                            text='Balls to 100',
                            hover_data=['Date', 'Team 1', 'Team 2', 'Total Runs']
                        )
                        fig.update_layout(xaxis_tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)


# =========================================
# BOWLER FIRST SPELL WICKETS
# =========================================
elif metric_choice == "Bowler First Spell Wickets":
    st.subheader("🎯 Bowler First Spell Wickets")
    st.write("Wickets taken by bowlers in their first spell (first 3 overs) of an innings.")

    m3_df = fdf.copy()
    if m3_df.empty:
        st.warning("No data for selected filters.")
    else:
        col_m3a, col_m3b = st.columns([1, 3])
        with col_m3a:
            min_wkts_spell = st.slider("Min Wickets in First Spell", 1, 5, 2, key="m3_min_wkts")

        with st.spinner("Computing first spell wickets..."):
            spell_df = bowler_first_spell_wickets(m3_df)

        if spell_df.empty:
            st.info("No data found.")
        else:
            tab_match, tab_agg = st.tabs(["📋 Match-by-Match", "📊 Career Aggregate"])

            with tab_match:
                st.markdown(f"### Performances with {min_wkts_spell}+ Wickets in First Spell")
                filtered_spell = spell_df[spell_df['Wickets in First Spell'] >= min_wkts_spell].sort_values(
                    ['Wickets in First Spell', 'Runs Conceded'], ascending=[False, True]
                ).copy()
                if filtered_spell.empty:
                    st.info(f"No bowlers with {min_wkts_spell}+ wickets in first spell.")
                else:
                    disp_spell = filtered_spell[['Date', 'Season', 'Team 1', 'Team 2', 'Innings',
                                                  'Bowler', 'Bowling Team', 'Wickets in First Spell',
                                                  'Overs in Spell', 'Spell Over Nos', 'Runs Conceded']].copy()
                    disp_spell = disp_spell.reset_index(drop=True)
                    disp_spell.index += 1
                    st.dataframe(disp_spell, use_container_width=True)

                    if len(disp_spell) >= 3:
                        fig = px.bar(
                            filtered_spell.head(25),
                            x='Bowler', y='Wickets in First Spell', color='Bowling Team',
                            title=f'Top 25 First Spell Performances ({min_wkts_spell}+ wickets)',
                            text='Wickets in First Spell',
                            hover_data=['Date', 'Runs Conceded', 'Overs in Spell']
                        )
                        fig.update_layout(xaxis_tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)

            with tab_agg:
                st.markdown("### All-Time: Bowlers with Most Multi-Wicket First Spells")
                threshold = st.slider("Count spells with at least N wickets", 2, 5, 2, key="m3_agg_thresh")
                agg_spell = (
                    spell_df[spell_df['Wickets in First Spell'] >= threshold]
                    .groupby(['Bowler', 'Bowling Team'], observed=True)
                    .agg(
                        Such_Spells=('Match ID', 'count'),
                        Total_Wickets=('Wickets in First Spell', 'sum'),
                        Best_Spell=('Wickets in First Spell', 'max'),
                        Avg_Runs_Conceded=('Runs Conceded', 'mean'),
                    )
                    .reset_index()
                    .sort_values('Such_Spells', ascending=False)
                )
                agg_spell['Avg_Runs_Conceded'] = agg_spell['Avg_Runs_Conceded'].round(1)
                agg_spell = agg_spell.rename(columns={'Such_Spells': f'{threshold}+ Wkt Spells'})
                if agg_spell.empty:
                    st.info(f"No bowlers with {threshold}+ wicket first spells found.")
                else:
                    st.dataframe(agg_spell.head(50), use_container_width=True)


# =========================================
# BACK-TO-BACK 25+ SCORES
# =========================================
elif metric_choice == "Back-to-Back 25+ Scores":
    st.subheader("🔥 Back-to-Back 25+ Scores")
    st.write("Batters with most 25+ scores and no single-digit innings in a season.")

    m4_df = fdf.copy()
    if m4_df.empty:
        st.warning("No data for selected filters.")
    else:
        col_m4a, col_m4b, col_m4c = st.columns([2, 2, 1])
        with col_m4a:
            all_seasons_m4 = sorted(m4_df['year'].dropna().unique(), reverse=True)
            sel_seasons_m4 = st.multiselect("Season(s)", all_seasons_m4, key="m4_seasons")
        with col_m4b:
            all_batters_m4 = sorted(m4_df['batter'].dropna().astype(str).unique())
            sel_batters_m4 = st.multiselect("Batter(s)", all_batters_m4, key="m4_batters")
        with col_m4c:
            strict_no_sd = st.checkbox("Strict: 0 single-digit innings", value=False, key="m4_strict")

        src_m4 = m4_df.copy()
        if sel_seasons_m4:
            src_m4 = src_m4[src_m4['year'].isin(sel_seasons_m4)]
        if sel_batters_m4:
            src_m4 = src_m4[src_m4['batter'].isin(sel_batters_m4)]

        with st.spinner("Computing consistency metrics..."):
            cons_df = consistent_batter_season(src_m4)

        if cons_df.empty:
            st.info("No data found.")
        else:
            if strict_no_sd:
                cons_df = cons_df[cons_df['Innings No Single Digit'] == cons_df['Total Innings']]

            # Show only batters with at least 1 back-to-back (Max Consec 25+ >= 2)
            min_innings_25 = st.slider("Min Innings with 25+", 1, 20, 2, key="m4_min_25")
            cons_df = cons_df[cons_df['Innings 25+'] >= min_innings_25]

            cons_df = cons_df.sort_values(['Innings 25+', 'Max Consec 25+', 'Consistency %'],
                                          ascending=[False, False, False])
            cons_df = cons_df.reset_index(drop=True)
            cons_df.index += 1

            st.dataframe(
                cons_df[['Season', 'Batter', 'Innings 25+', 'Max Consec 25+',
                         'Innings No Single Digit', 'Total Runs', 'Total Innings', 'Consistency %']],
                use_container_width=True
            )

            if len(cons_df) >= 3:
                top_chart = cons_df.head(20).copy()
                fig = px.bar(
                    top_chart,
                    x='Batter', y='Innings 25+', color='Season',
                    title='Top 20 — Most 25+ Innings in a Season',
                    text='Innings 25+',
                    hover_data=['Max Consec 25+', 'Consistency %', 'Total Runs']
                )
                fig.update_layout(xaxis_tickangle=45)
                st.plotly_chart(fig, use_container_width=True)


# =========================================
# BOUNDARY-LESS OVERS SPELL
# =========================================
elif metric_choice == "Boundary-less Overs Spell":
    st.subheader("🛡️ Boundary-less Overs Spell")
    st.write("Bowlers who bowled 3+ overs without conceding a boundary in an innings (no 4 or 6 off the bat).")

    m5_df = fdf.copy()
    if m5_df.empty:
        st.warning("No data for selected filters.")
    else:
        col_m5a, col_m5b = st.columns([1, 3])
        with col_m5a:
            min_bl_overs = st.slider("Min Boundary-less Overs", 3, 10, 3, key="m5_min_bl")

        with st.spinner("Computing boundary-less overs..."):
            bl_df = boundary_less_overs_spell(m5_df)

        if bl_df.empty:
            st.info("No performances with 3+ boundary-less overs found for the selected filters.")
        else:
            bl_filtered = bl_df[bl_df['Boundary-less Overs'] >= min_bl_overs].sort_values(
                ['Boundary-less Overs', 'Max Consec Boundary-less'], ascending=[False, False]
            ).copy()

            tab_bl_match, tab_bl_agg = st.tabs(["📋 Match Performances", "📊 All-Time Leaders"])

            with tab_bl_match:
                st.markdown(f"### Performances with {min_bl_overs}+ Boundary-less Overs")
                if bl_filtered.empty:
                    st.info(f"No performances with {min_bl_overs}+ boundary-less overs.")
                else:
                    disp_bl = bl_filtered[['Date', 'Season', 'Team 1', 'Team 2', 'Inning No',
                                           'Bowler', 'Bowling Team', 'Boundary-less Overs',
                                           'Boundary-less Over Nos',
                                           'Max Consec Boundary-less', 'Total Overs Bowled',
                                           'Runs in Boundary-less Overs', 'Total Runs Conceded']].copy()
                    disp_bl = disp_bl.reset_index(drop=True)
                    disp_bl.index += 1
                    st.dataframe(disp_bl, use_container_width=True)

                    if len(disp_bl) >= 3:
                        fig = px.bar(
                            bl_filtered.head(25),
                            x='Bowler', y='Boundary-less Overs', color='Bowling Team',
                            title=f'Top 25 — Boundary-less Overs ({min_bl_overs}+)',
                            text='Boundary-less Overs',
                            hover_data=['Date', 'Max Consec Boundary-less', 'Total Runs Conceded']
                        )
                        fig.update_layout(xaxis_tickangle=45)
                        st.plotly_chart(fig, use_container_width=True)

            with tab_bl_agg:
                st.markdown("### All-Time Leaders — Most Boundary-less Overs Performances")
                bl_agg = (
                    bl_df[bl_df['Boundary-less Overs'] >= min_bl_overs]
                    .groupby(['Bowler', 'Bowling Team'], observed=True)
                    .agg(
                        Such_Performances=('Match ID', 'count'),
                        Total_BL_Overs=('Boundary-less Overs', 'sum'),
                        Best_Match=('Boundary-less Overs', 'max'),
                        Best_Max_Consec=('Max Consec Boundary-less', 'max'),
                        Avg_Runs_in_BL=('Runs in Boundary-less Overs', 'mean'),
                    )
                    .reset_index()
                    .sort_values('Such_Performances', ascending=False)
                )
                bl_agg['Avg_Runs_in_BL'] = bl_agg['Avg_Runs_in_BL'].round(1)
                bl_agg = bl_agg.rename(columns={'Such_Performances': f'{min_bl_overs}+ BL Overs Perfs'})

                if bl_agg.empty:
                    st.info("No all-time leaders found.")
                else:
                    st.dataframe(bl_agg.head(50), use_container_width=True)

                    fig = px.bar(
                        bl_agg.head(20),
                        x='Bowler', y=f'{min_bl_overs}+ BL Overs Perfs', color='Bowling Team',
                        title=f'Top 20 — Most {min_bl_overs}+ Boundary-less Overs Performances',
                        text=f'{min_bl_overs}+ BL Overs Perfs',
                        hover_data=['Total_BL_Overs', 'Best_Max_Consec']
                    )
                    fig.update_layout(xaxis_tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)


# =========================================
# BOUNDARY-LESS BALL STREAK
# =========================================
elif metric_choice == "Boundary-less Ball Streak":
    st.subheader("🚫 Boundary-less Ball Streak")
    st.write("Tracks consecutive deliveries where the batting team went without hitting a boundary (no 4 or 6 off the bat).")

    if fdf.empty:
        st.warning("No data for selected filters.")
    else:
        with st.spinner("Computing boundary-less ball streaks..."):
            all_streaks = boundary_less_ball_streak(fdf)

        if all_streaks.empty:
            st.info("No streak data found for the selected filters.")
        else:
            max_possible = int(all_streaks['Balls Without Boundary'].max())
            col_slider, col_info = st.columns([3, 2])
            with col_slider:
                min_balls = st.slider(
                    "Minimum Balls Without Boundary",
                    min_value=1,
                    max_value=min(max_possible, 80),
                    value=10,
                    step=1,
                    key="bls_min_balls",
                    help="Slide to filter: only show streaks of this many consecutive balls or more without a boundary."
                )
            with col_info:
                total_matching = len(all_streaks[all_streaks['Balls Without Boundary'] >= min_balls])
                st.metric("Matching Streaks", total_matching)

            # Per-innings summary: max streak per innings
            innings_summary = (
                all_streaks.groupby(['Match ID', 'Date', 'Season', 'Match', 'Innings', 'Batting Team'], observed=True)
                .agg(
                    Max_Streak=('Balls Without Boundary', 'max'),
                    Num_Droughts=('Balls Without Boundary', 'count'),
                    All_Streaks=('Balls Without Boundary', lambda x: ', '.join(str(v) for v in sorted(x, reverse=True))),
                )
                .reset_index()
                .rename(columns={'Max_Streak': 'Max Balls Without Boundary', 'Num_Droughts': 'No. of Droughts', 'All_Streaks': 'All Streak Lengths'})
            )

            # Per-match summary: max streak across both innings for each team
            match_summary = (
                all_streaks.groupby(['Match ID', 'Date', 'Season', 'Match', 'Batting Team'], observed=True)
                .agg(
                    Max_Streak=('Balls Without Boundary', 'max'),
                    Num_Droughts=('Balls Without Boundary', 'count'),
                )
                .reset_index()
                .rename(columns={'Max_Streak': 'Max Balls Without Boundary', 'Num_Droughts': 'No. of Droughts'})
            )

            tab_inn, tab_match, tab_dist = st.tabs(["📋 Innings-wise", "📊 Match-wise", "📈 Distribution"])

            with tab_inn:
                st.markdown(f"#### Innings with {min_balls}+ Consecutive Balls Without a Boundary")
                inn_filtered = innings_summary[innings_summary['Max Balls Without Boundary'] >= min_balls].sort_values(
                    'Max Balls Without Boundary', ascending=False
                ).copy()
                inn_filtered['Innings'] = inn_filtered['Innings'].map({1: '1st', 2: '2nd'})

                if inn_filtered.empty:
                    st.info(f"No innings found with {min_balls}+ consecutive balls without a boundary.")
                else:
                    inn_filtered = inn_filtered.reset_index(drop=True)
                    inn_filtered.index += 1
                    st.dataframe(
                        inn_filtered[['Batting Team', 'Match', 'Date', 'Season', 'Innings',
                                      'Max Balls Without Boundary', 'No. of Droughts', 'All Streak Lengths']],
                        use_container_width=True
                    )

                    if len(inn_filtered) >= 3:
                        fig_inn = px.bar(
                            inn_filtered.head(30),
                            x='Batting Team', y='Max Balls Without Boundary',
                            color='Season', hover_data=['Match', 'Date', 'Innings', 'All Streak Lengths'],
                            title=f"Top 30 Innings — Max Balls Without Boundary ({min_balls}+)",
                            text='Max Balls Without Boundary'
                        )
                        fig_inn.update_layout(xaxis_tickangle=30, showlegend=True)
                        st.plotly_chart(fig_inn, use_container_width=True)

            with tab_match:
                st.markdown(f"#### Matches with {min_balls}+ Consecutive Balls Without a Boundary")
                match_filtered = match_summary[match_summary['Max Balls Without Boundary'] >= min_balls].sort_values(
                    'Max Balls Without Boundary', ascending=False
                ).copy()

                if match_filtered.empty:
                    st.info(f"No matches found with {min_balls}+ consecutive balls without a boundary.")
                else:
                    match_filtered = match_filtered.reset_index(drop=True)
                    match_filtered.index += 1
                    st.dataframe(
                        match_filtered[['Batting Team', 'Match', 'Date', 'Season',
                                        'Max Balls Without Boundary', 'No. of Droughts']],
                        use_container_width=True
                    )

                    # Team aggregation
                    st.markdown("#### Team Summary")
                    team_agg = (
                        match_summary.groupby('Batting Team', observed=True)
                        .agg(
                            Matches=('Match ID', 'nunique'),
                            Avg_Max_Streak=('Max Balls Without Boundary', 'mean'),
                            Best_Max_Streak=('Max Balls Without Boundary', 'max'),
                            Total_Droughts=('No. of Droughts', 'sum'),
                        )
                        .reset_index()
                        .sort_values('Best_Max_Streak', ascending=False)
                    )
                    team_agg['Avg_Max_Streak'] = team_agg['Avg_Max_Streak'].round(1)
                    team_agg = team_agg.rename(columns={
                        'Avg_Max_Streak': 'Avg Max Streak',
                        'Best_Max_Streak': 'Longest Single Streak',
                    })
                    st.dataframe(team_agg, use_container_width=True)

                    fig_match = px.bar(
                        team_agg,
                        x='Batting Team', y='Longest Single Streak',
                        color='Avg Max Streak', color_continuous_scale='RdYlGn_r',
                        title="Longest Boundary-less Ball Streak by Team",
                        text='Longest Single Streak',
                        hover_data=['Matches', 'Total_Droughts']
                    )
                    fig_match.update_layout(xaxis_tickangle=30)
                    st.plotly_chart(fig_match, use_container_width=True)

            with tab_dist:
                st.markdown("#### Distribution of Streak Lengths")
                st.caption("How often did teams go N consecutive balls without hitting a boundary?")

                dist_data = all_streaks[all_streaks['Balls Without Boundary'] >= min_balls].copy()
                if dist_data.empty:
                    st.info(f"No streaks of {min_balls}+ balls found.")
                else:
                    fig_hist = px.histogram(
                        dist_data,
                        x='Balls Without Boundary',
                        nbins=max(1, (dist_data['Balls Without Boundary'].max() - min_balls + 1)),
                        color='Batting Team' if dist_data['Batting Team'].nunique() <= 12 else None,
                        title=f"Frequency of Boundary-less Streaks ({min_balls}+ balls)",
                        labels={'Balls Without Boundary': 'Consecutive Balls Without Boundary', 'count': 'Frequency'},
                    )
                    fig_hist.update_layout(bargap=0.1)
                    st.plotly_chart(fig_hist, use_container_width=True)

                    # Season breakdown
                    season_dist = (
                        all_streaks[all_streaks['Balls Without Boundary'] >= min_balls]
                        .groupby('Season', observed=True)
                        .agg(
                            Count=('Balls Without Boundary', 'count'),
                            Avg_Streak=('Balls Without Boundary', 'mean'),
                            Max_Streak=('Balls Without Boundary', 'max'),
                        )
                        .reset_index()
                    )
                    season_dist['Avg_Streak'] = season_dist['Avg_Streak'].round(1)
                    season_dist = season_dist.rename(columns={'Count': f'{min_balls}+ Ball Droughts', 'Avg_Streak': 'Avg Streak', 'Max_Streak': 'Longest Streak'})
                    st.markdown("#### Season-wise Summary")
                    st.dataframe(season_dist, use_container_width=True)


# =========================================
# ON THIS DAY
# =========================================
elif metric_choice == "On This Day":
    today = date.today()
    otd_date_col, _ = st.columns([2, 3])
    with otd_date_col:
        selected_otd_date = st.date_input(
            "📅 Select Date",
            value=today,
            min_value=date(2000, 1, 1),
            max_value=today,
            key="otd_date_picker",
            help="Pick any date to explore historical cricket milestones on that calendar day across all years."
        )
    month_name = selected_otd_date.strftime("%B")
    day_num = selected_otd_date.day
    st.subheader(f"📅 On This Day — {month_name} {day_num}")
    st.write(
        f"Historical records from all datasets for every **{month_name} {day_num}** in cricket history."
    )

    with st.spinner(f"Searching historical records for {month_name} {day_num}..."):
        otd = on_this_day_insights(fdf, selected_otd_date.month, selected_otd_date.day)

    if not otd:
        st.info(f"No matches found in the dataset on {month_name} {day_num} across any year.")
    else:
        # ---- Fastest individual 50s & 100s ----
        with st.expander("⚡ Fastest Individual Milestones", expanded=True):
            f50_df = otd.get('fastest_50s', pd.DataFrame())
            if f50_df.empty:
                st.info("No individual milestone innings on this date.")
            else:
                rows_50 = f50_df[f50_df['Balls to 50'].notna()].sort_values('Balls to 50').copy()
                rows_100 = f50_df[f50_df['Balls to 100'].notna()].sort_values('Balls to 100').copy()

                if not rows_50.empty:
                    st.markdown("**Fastest 50s on this date:**")
                    for _, r in rows_50.head(10).iterrows():
                        st.markdown(
                            f"- **On This Day in {r['Season']}**: *{r['Batter']}* ({r['Batting Team']}) reached 50 in "
                            f"**{int(r['Balls to 50'])} balls** — {r['Total Runs']} runs vs {r['Match']} (Inning {r['Inning']})"
                        )

                if not rows_100.empty:
                    st.markdown("**Fastest 100s on this date:**")
                    for _, r in rows_100.head(10).iterrows():
                        st.markdown(
                            f"- **On This Day in {r['Season']}**: *{r['Batter']}* ({r['Batting Team']}) reached 100 in "
                            f"**{int(r['Balls to 100'])} balls** — {r['Total Runs']} runs vs {r['Match']} (Inning {r['Inning']})"
                        )

                with st.expander("View full data table"):
                    st.dataframe(f50_df.sort_values('Date').reset_index(drop=True), use_container_width=True)

        # ---- Fastest team 50s & 100s ----
        with st.expander("🚀 Fastest Team Milestones", expanded=True):
            ft_df = otd.get('fastest_team_50s', pd.DataFrame())
            if ft_df.empty:
                st.info("No team milestone innings on this date.")
            else:
                rows_t50 = ft_df[ft_df['Balls to 50'].notna()].sort_values('Balls to 50').copy()
                rows_t100 = ft_df[ft_df['Balls to 100'].notna()].sort_values('Balls to 100').copy()

                if not rows_t50.empty:
                    st.markdown("**Fastest team 50s on this date:**")
                    for _, r in rows_t50.head(10).iterrows():
                        st.markdown(
                            f"- **On This Day in {r['Season']}**: *{r['Batting Team']}* reached team 50 in "
                            f"**{int(r['Balls to 50'])} balls** — {r['Total Runs']} total vs {r['Team 1']} vs {r['Team 2']} (Inning {r['Inning No']})"
                        )

                if not rows_t100.empty:
                    st.markdown("**Fastest team 100s on this date:**")
                    for _, r in rows_t100.head(10).iterrows():
                        st.markdown(
                            f"- **On This Day in {r['Season']}**: *{r['Batting Team']}* reached team 100 in "
                            f"**{int(r['Balls to 100'])} balls** — {r['Total Runs']} total (Inning {r['Inning No']})"
                        )

                with st.expander("View full data table"):
                    st.dataframe(ft_df.sort_values('Date').reset_index(drop=True), use_container_width=True)

        # ---- Bowler first spell wickets ----
        with st.expander("🎯 Bowler First Spell Wickets", expanded=True):
            fs_df = otd.get('first_spell', pd.DataFrame())
            if fs_df.empty:
                st.info("No notable first spell performances on this date.")
            else:
                notable = fs_df[fs_df['Wickets in First Spell'] >= 2].sort_values(
                    ['Wickets in First Spell', 'Runs Conceded'], ascending=[False, True]
                )
                if notable.empty:
                    st.info("No bowler took 2+ wickets in their first spell on this date.")
                else:
                    for _, r in notable.iterrows():
                        st.markdown(
                            f"- **On This Day in {r['Season']}**: *{r['Bowler']}* ({r['Bowling Team']}) took "
                            f"**{r['Wickets in First Spell']} wickets** in {r['Overs in Spell']} overs "
                            f"(overs {r['Spell Over Nos']}) conceding {r['Runs Conceded']} runs — "
                            f"{r['Team 1']} vs {r['Team 2']} (Inning {r['Innings']})"
                        )

                with st.expander("View full data table"):
                    st.dataframe(fs_df.sort_values('Date').reset_index(drop=True), use_container_width=True)

        # ---- Boundary-less overs ----
        with st.expander("🛡️ Boundary-less Overs Performances", expanded=True):
            bl_df = otd.get('boundary_less', pd.DataFrame())
            if bl_df.empty:
                st.info("No 3+ boundary-less over performances on this date.")
            else:
                notable_bl = bl_df[bl_df['Boundary-less Overs'] >= 3].sort_values(
                    'Boundary-less Overs', ascending=False
                )
                for _, r in notable_bl.iterrows():
                    st.markdown(
                        f"- **On This Day in {r['Season']}**: *{r['Bowler']}* ({r['Bowling Team']}) bowled "
                        f"**{r['Boundary-less Overs']} boundary-less overs** "
                        f"(overs {r['Boundary-less Over Nos']}) — "
                        f"{r['Team 1']} vs {r['Team 2']} (Inning {r['Inning No']})"
                    )

                with st.expander("View full data table"):
                    st.dataframe(bl_df.sort_values('Date').reset_index(drop=True), use_container_width=True)


# =========================================
# BOWLER OVER IMPACT
# =========================================
elif metric_choice == "Bowler Over Impact":
    st.subheader("🎯 Bowler Over Impact")
    st.write(
        "Split a bowler's innings appearances by what happened in a specific over "
        "(Wicket & ≤10 Runs / No Wicket & ≤10 Runs / >10 Runs), then compare their "
        "full-match bowling stats across those categories."
    )

    boi_df = fdf.copy()
    if boi_df.empty:
        st.warning("No data for selected filters.")
    else:
        col_boi1, col_boi2 = st.columns([3, 1])
        with col_boi1:
            all_bowlers_boi = sorted(boi_df['bowler'].dropna().astype(str).unique())
            sel_bowler = st.selectbox("Select Bowler", all_bowlers_boi, key="boi_bowler")
        with col_boi2:
            sel_over = st.slider("Over Number (1–20)", 1, 20, 1, key="boi_over")

        with st.spinner(f"Computing over impact for {sel_bowler}, over {sel_over}..."):
            impact = bowler_over_impact(boi_df, sel_bowler, sel_over)

        if not impact:
            st.info(f"No data found for **{sel_bowler}** bowling over {sel_over}.")
        else:
            # ── header ───────────────────────────────────────────────────────────
            st.markdown(
                f"<h4 style='margin-bottom:2px;'>{sel_bowler} — Over {sel_over} Impact</h4>"
                f"<p style='color:#888;font-size:13px;margin-top:0;margin-bottom:18px;'>"
                f"Stats from the bowler's <b>full match deliveries</b> in each category of appearances.</p>",
                unsafe_allow_html=True,
            )

            CATEGORIES = ['Wicket & \u226410 Runs', 'No Wicket & \u226410 Runs', '>10 Runs in Over']
            # accent colour per category
            CAT_META = {
                'Wicket & \u226410 Runs':     {'accent': '#00c853', 'icon': '🟢', 'border': '#00c853'},
                'No Wicket & \u226410 Runs':  {'accent': '#2979ff', 'icon': '🔵', 'border': '#2979ff'},
                '>10 Runs in Over':           {'accent': '#ff1744', 'icon': '🔴', 'border': '#ff1744'},
            }
            stat_keys = ['Matches', 'Wickets', 'Economy', 'Avg', 'SR', 'BPB', 'BP6', 'Dot %', 'Wkts / Match']

            def _val_color(key, val):
                """Return a hex colour: green = good for bowler, red = bad, white = neutral."""
                if val == float('inf'):
                    return '#888888'
                if key in ('Economy', 'Avg', 'SR'):
                    return '#00c853' if val <= 7.5 else ('#ff1744' if val >= 10 else '#e0e0e0')
                if key == 'Dot %':
                    return '#00c853' if val >= 40 else ('#ff1744' if val < 28 else '#e0e0e0')
                if key == 'Wkts / Match':
                    return '#00c853' if val >= 2 else ('#ff1744' if val < 1 else '#e0e0e0')
                return '#e0e0e0'

            def _fmt(val):
                if val == float('inf'):
                    return '—'
                if isinstance(val, float):
                    return f'{val:.2f}'
                return str(val)

            def _build_card(cat, data):
                meta = CAT_META[cat]
                accent = meta['accent']
                if data is None:
                    body_html = "<p style='color:#888;font-size:13px;margin:12px 0;'>No appearances in this category</p>"
                else:
                    rows = []
                    for key in stat_keys:
                        val = data[key]
                        disp = _fmt(val)
                        vc = _val_color(key, val)
                        rows.append(
                            f"<div style='display:flex;justify-content:space-between;"
                            f"align-items:center;padding:7px 0;"
                            f"border-bottom:1px solid #2a2a3a;'>"
                            f"<span style='color:#9e9e9e;font-size:13px;'>{key}</span>"
                            f"<span style='color:{vc};font-weight:700;font-size:15px;"
                            f"letter-spacing:0.3px;'>{disp}</span>"
                            f"</div>"
                        )
                    body_html = ''.join(rows)

                return (
                    f"<div style='"
                    f"background:#12121f;"
                    f"border-radius:12px;"
                    f"border-top:3px solid {accent};"
                    f"padding:18px 20px 10px 20px;"
                    f"height:100%;'>"
                    f"<p style='color:{accent};font-weight:700;font-size:14px;"
                    f"letter-spacing:0.5px;margin:0 0 4px 0;text-transform:uppercase;'>"
                    f"{meta['icon']} {cat}</p>"
                    f"{body_html}"
                    f"</div>"
                )

            cols = st.columns(3)
            for col_widget, cat in zip(cols, CATEGORIES):
                with col_widget:
                    st.markdown(_build_card(cat, impact.get(cat)), unsafe_allow_html=True)

            # ── comparison chart ─────────────────────────────────────────────────
            st.markdown("<br>", unsafe_allow_html=True)
            COLORS = [CAT_META[c]['accent'] for c in CATEGORIES]

            chart_stat = st.selectbox(
                "Compare stat across categories",
                ['Economy', 'Avg', 'SR', 'Dot %', 'Wkts / Match', 'Wickets', 'Matches'],
                key="boi_chart_stat",
            )

            chart_rows = []
            for cat in CATEGORIES:
                data = impact.get(cat)
                if data is not None:
                    val = data.get(chart_stat, 0)
                    if val == float('inf'):
                        val = 0
                    chart_rows.append({'Category': cat, chart_stat: val})

            if chart_rows:
                chart_df = pd.DataFrame(chart_rows)
                fig = px.bar(
                    chart_df,
                    x='Category',
                    y=chart_stat,
                    color='Category',
                    color_discrete_sequence=COLORS,
                    text=chart_stat,
                    title=f"{sel_bowler} — {chart_stat} by Over-{sel_over} Outcome",
                )
                fig.update_traces(texttemplate='%{text:.2f}', textposition='outside')
                fig.update_layout(
                    showlegend=False,
                    xaxis_title='',
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#e0e0e0',
                    title_font_size=14,
                    margin=dict(t=50, b=20),
                )
                fig.update_xaxes(showgrid=False)
                fig.update_yaxes(gridcolor='#2a2a3a')
                st.plotly_chart(fig, use_container_width=True)


elif metric_choice == "Match Flow Chart":
    st.subheader("🏏 Match Flow Chart")
    st.caption("Ball-by-ball run progression for both innings. Red dots = wickets. Dashed line = Required Run Rate (chasing team).")

    import os as _os, json as _json
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    @st.cache_data
    def _load_match_flow(match_id_str):
        path = _os.path.join(JSON_DIR, f"{match_id_str}.json")
        if not _os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as _f:
            return _json.load(_f)

    def _parse_innings(inn_json):
        rows, ball_no, cumulative = [], 0, 0
        for over in inn_json.get('overs', []):
            for d_idx, delivery in enumerate(over.get('deliveries', [])):
                ball_no += 1
                runs = delivery['runs']['total']
                cumulative += runs
                is_wicket = 'wickets' in delivery
                rows.append({
                    'ball': ball_no,
                    'cumulative': cumulative,
                    'wicket': is_wicket,
                    'player_out': delivery['wickets'][0]['player_out'] if is_wicket else '',
                    'kind': delivery['wickets'][0]['kind'] if is_wicket else '',
                    'batter': delivery.get('batter', ''),
                    'bowler': delivery.get('bowler', ''),
                    'over_ball': f"Over {over['over']+1}.{d_idx+1}",
                })
        return rows

    # Match selector
    _match_opts = (
        fdf[fdf['innings'].isin([1, 2])]
        .groupby(['match_id', 'teams', 'date'], observed=True)
        .size().reset_index()
    )
    _match_opts['Label'] = _match_opts.apply(
        lambda r: f"{r['teams']} — {pd.to_datetime(r['date']).strftime('%d %b %Y')}", axis=1
    )
    _match_opts = _match_opts.sort_values('date', ascending=False)

    if _match_opts.empty:
        st.info("No matches available for selected filters.")
    else:
        _sel_label = st.selectbox("Select Match", _match_opts['Label'].tolist(), key="mfc_sel")
        _match_id = str(_match_opts[_match_opts['Label'] == _sel_label]['match_id'].iloc[0])

        _data = _load_match_flow(_match_id)
        if _data is None:
            st.warning(f"JSON not found for match {_match_id}.")
        else:
            _info = _data.get('info', {})
            _innings_list = _data.get('innings', [])

            # Result string
            _outcome = _info.get('outcome', {})
            _winner = _outcome.get('winner', '')
            _by = _outcome.get('by', {})
            if 'wickets' in _by:
                _result_str = f"🏆 {_winner} won by {_by['wickets']} wicket(s)"
            elif 'runs' in _by:
                _result_str = f"🏆 {_winner} won by {_by['runs']} run(s)"
            elif 'winner' in _outcome:
                _result_str = f"🏆 {_winner} won"
            else:
                _result_str = _outcome.get('result', 'Result unknown')

            if len(_innings_list) < 1:
                st.warning("Insufficient innings data in this match file.")
            else:
                _inn1 = _parse_innings(_innings_list[0])
                _inn2 = _parse_innings(_innings_list[1]) if len(_innings_list) > 1 else []

                _team1 = _innings_list[0].get('team', 'Team 1')
                _team2 = _innings_list[1].get('team', 'Team 2') if len(_innings_list) > 1 else 'Team 2'

                _total1 = _inn1[-1]['cumulative'] if _inn1 else 0
                _total2 = _inn2[-1]['cumulative'] if _inn2 else 0
                _wkts1 = sum(1 for r in _inn1 if r['wicket'])
                _wkts2 = sum(1 for r in _inn2 if r['wicket'])
                _target = _total1 + 1

                # Compute RRR for chasing team (max 120 balls in T20)
                _MAX_BALLS = 120
                for r in _inn2:
                    _balls_rem = max(_MAX_BALLS - r['ball'], 1)
                    _runs_needed = max(_target - r['cumulative'], 0)
                    r['rrr'] = round((_runs_needed / _balls_rem) * 6, 2)

                # ── Single unified chart with secondary y-axis for RRR ──
                # Innings 2 is offset on the x-axis so both fit side-by-side.
                # Innings 1 balls stay as-is (1–N1).
                # Innings 2 balls are offset by a gap so the x-axis reads
                # "1st Inns balls 1-N1 | 2nd Inns balls 1-N2" seamlessly.
                _N1 = len(_inn1)
                _GAP = 5   # small visual gap between innings

                _x2_runs = [r['ball'] + _N1 + _GAP for r in _inn2]
                _x2_rrr  = [r['ball'] + _N1 + _GAP for r in _inn2]

                _fig = make_subplots(specs=[[{"secondary_y": True}]])

                # ── 1st innings run curve (teal) ──
                _fig.add_trace(go.Scatter(
                    x=[r['ball'] for r in _inn1],
                    y=[r['cumulative'] for r in _inn1],
                    mode='lines',
                    name=f"{_team1} ({_total1}/{_wkts1})",
                    line=dict(color='#48cae4', width=2.5),
                    hovertemplate='<b>Inn1</b> %{customdata[0]}<br>Batter: %{customdata[1]}<br>Bowler: %{customdata[2]}<br>Score: <b>%{y}</b><extra></extra>',
                    customdata=[[r['over_ball'], r['batter'], r['bowler']] for r in _inn1],
                ), secondary_y=False)

                # ── 1st innings wickets (red circles) ──
                _w1 = [r for r in _inn1 if r['wicket']]
                if _w1:
                    _fig.add_trace(go.Scatter(
                        x=[r['ball'] for r in _w1],
                        y=[r['cumulative'] for r in _w1],
                        mode='markers',
                        name='Wicket (Inn1)',
                        marker=dict(color='#ff4d6d', size=11, symbol='circle',
                                    line=dict(color='white', width=1.5)),
                        hovertemplate='🔴 <b>%{customdata[0]}</b> — %{customdata[1]}<br>%{customdata[2]}<extra></extra>',
                        customdata=[[r['player_out'], r['kind'], r['over_ball']] for r in _w1],
                    ), secondary_y=False)

                if _inn2:
                    # ── 2nd innings run curve (amber) ──
                    _fig.add_trace(go.Scatter(
                        x=_x2_runs,
                        y=[r['cumulative'] for r in _inn2],
                        mode='lines',
                        name=f"{_team2} ({_total2}/{_wkts2})",
                        line=dict(color='#f4a261', width=2.5),
                        hovertemplate='<b>Inn2</b> %{customdata[0]}<br>Batter: %{customdata[1]}<br>RRR: %{customdata[2]}<br>Score: <b>%{y}</b><extra></extra>',
                        customdata=[[r['over_ball'], r['batter'], r['rrr']] for r in _inn2],
                    ), secondary_y=False)

                    # ── Target line — spans only the 2nd innings x range ──
                    _fig.add_shape(
                        type='line',
                        x0=_N1 + _GAP, x1=_x2_runs[-1] + 2,
                        y0=_target, y1=_target,
                        line=dict(color='#80ffdb', width=1.5, dash='dot'),
                        layer='below',
                    )
                    _fig.add_annotation(
                        x=_x2_runs[-1] + 2, y=_target,
                        text=f"  Target {_target}",
                        showarrow=False,
                        font=dict(color='#80ffdb', size=11),
                        xanchor='left',
                    )

                    # ── RRR on secondary y (lime-yellow dashed) ──
                    _fig.add_trace(go.Scatter(
                        x=_x2_rrr,
                        y=[r['rrr'] for r in _inn2],
                        mode='lines',
                        name='Req. Run Rate',
                        line=dict(color='#ffe66d', width=1.5, dash='dash'),
                        hovertemplate='Ball %{customdata}<br>RRR: <b>%{y:.2f}</b><extra></extra>',
                        customdata=[r['over_ball'] for r in _inn2],
                        opacity=0.85,
                    ), secondary_y=True)

                    # ── 2nd innings wickets (pink) ──
                    _w2 = [r for r in _inn2 if r['wicket']]
                    if _w2:
                        _fig.add_trace(go.Scatter(
                            x=[r['ball'] + _N1 + _GAP for r in _w2],
                            y=[r['cumulative'] for r in _w2],
                            mode='markers',
                            name='Wicket (Inn2)',
                            marker=dict(color='#ff4d6d', size=11, symbol='circle',
                                        line=dict(color='white', width=1.5)),
                            hovertemplate='🔴 <b>%{customdata[0]}</b> — %{customdata[1]}<br>%{customdata[2]}<extra></extra>',
                            customdata=[[r['player_out'], r['kind'], r['over_ball']] for r in _w2],
                        ), secondary_y=False)

                # ── Vertical divider between innings ──
                _fig.add_vline(
                    x=_N1 + _GAP / 2,
                    line=dict(color='#555577', width=1.5, dash='dot'),
                    annotation_text='Innings Break',
                    annotation_font=dict(color='#aaaacc', size=10),
                    annotation_position='top',
                )

                # ── Custom x-axis tick labels (Over numbers) ──
                _tick_vals, _tick_text = [], []
                for ov in range(0, 21, 5):
                    b = ov * 6
                    if b <= _N1:
                        _tick_vals.append(b if b > 0 else 1)
                        _tick_text.append(f"Ov {ov}" if ov > 0 else "Start")
                if _inn2:
                    for ov in range(0, 21, 5):
                        b = ov * 6
                        xpos = b + _N1 + _GAP
                        if xpos <= _x2_runs[-1] + _GAP:
                            _tick_vals.append(xpos)
                            _tick_text.append(f"Ov {ov}" if ov > 0 else "Start")

                # ── Result annotation ──
                _fig.add_annotation(
                    text=_result_str,
                    xref='paper', yref='paper',
                    x=0.5, y=-0.12,
                    showarrow=False,
                    font=dict(size=13, color='#90e0ef', family='Arial Black'),
                    align='center',
                )

                _fig.update_layout(
                    height=520,
                    title=dict(
                        text=f"<b>Match Flow</b>  ·  {_sel_label}",
                        font=dict(size=15, color='#e0e0e0'),
                        x=0.0,
                    ),
                    plot_bgcolor='#0d1117',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font_color='#c9d1d9',
                    legend=dict(
                        orientation='h',
                        yanchor='bottom', y=1.01,
                        xanchor='left', x=0,
                        bgcolor='rgba(0,0,0,0)',
                        font=dict(size=11),
                    ),
                    margin=dict(b=90, t=70, l=60, r=70),
                    hovermode='x unified',
                )
                _fig.update_xaxes(
                    tickvals=_tick_vals,
                    ticktext=_tick_text,
                    showgrid=True,
                    gridcolor='#21262d',
                    zeroline=False,
                    tickfont=dict(size=10),
                    title_text='',
                )
                _fig.update_yaxes(
                    title_text='Cumulative Runs',
                    gridcolor='#21262d',
                    zeroline=False,
                    secondary_y=False,
                )
                _fig.update_yaxes(
                    title_text='Req. Run Rate',
                    gridcolor='rgba(0,0,0,0)',
                    showgrid=False,
                    zeroline=False,
                    secondary_y=True,
                )

                st.plotly_chart(_fig, use_container_width=True)

                # Quick scorecard summary
                _c1, _c2 = st.columns(2)
                with _c1:
                    st.metric(f"🏏 {_team1}", f"{_total1}/{_wkts1}")
                with _c2:
                    st.metric(f"🏏 {_team2}", f"{_total2}/{_wkts2}", delta=f"Target {_target}")


# =========================================
# EXTRA DELIVERIES COST
# =========================================
elif metric_choice == "Extra Deliveries Cost":
    st.subheader("💸 Extra Deliveries Cost")
    st.write("Innings-wise & match-wise view of wides and no-balls bowled by each team, "
             "and the total runs conceded purely because of those extra re-bowled deliveries.")

    # Filters
    edc_col1, edc_col2 = st.columns([2, 2])
    with edc_col1:
        edc_mode = st.radio("View Mode", ["Match-wise", "Innings-wise", "Season Summary"], horizontal=True)
    with edc_col2:
        edc_phase = st.radio("Phase", ["Full Match", "Powerplay", "Middle", "Death"], horizontal=True)

    # Build source dataframe
    edc_df = df.copy()
    if selected_leagues:
        edc_df = edc_df[edc_df['league'].isin(selected_leagues)]
    if selected_years:
        edc_df = edc_df[edc_df['year'].isin(selected_years)]

    if edc_phase != "Full Match":
        phase_map = {"Powerplay": "Powerplay", "Middle": "Middle", "Death": "Death"}
        edc_df = edc_df[edc_df['phase'].astype(str) == phase_map[edc_phase]]

    if selected_teams:
        # Show only selected bowling team(s)
        edc_df = edc_df[edc_df['bowling_team'].astype(str).isin([str(t) for t in selected_teams])]

    if edc_df.empty:
        st.warning("No data for the selected filters.")
    else:
        match_df, inn_df, season_df = extra_deliveries_cost(edc_df)

        if match_df.empty:
            st.info("No data available.")
        else:
            # ---- KPI Cards ----
            total_wide_dels    = match_df['Wide_Deliveries'].sum()
            total_wide_runs    = match_df['Wide_Balls'].sum()
            total_nb_dels      = match_df['NoBall_Balls'].sum()
            total_nb_runs      = match_df['NoBall_Runs'].sum()
            total_extra_runs   = match_df['Extra_Ball_Runs'].sum()
            total_after_extra  = match_df['Runs_After_Extra'].sum()
            total_runs         = match_df['Team_Total_Runs'].sum()
            overall_pct        = round(total_extra_runs / total_runs * 100, 1) if total_runs else 0

            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric("🔴 Wide Deliveries",    f"{int(total_wide_dels)}",
                      help="Number of extra balls re-bowled due to wides")
            k2.metric("💧 Wide Runs",           f"{int(total_wide_runs)}",
                      help="Total runs conceded from wide deliveries (penalty + any batter runs)")
            k3.metric("🟠 No-Ball Deliveries",  f"{int(total_nb_dels)}",
                      help="Number of no-ball deliveries bowled")
            k4.metric("🔥 No-Ball Runs",        f"{int(total_nb_runs)}",
                      help="Total runs conceded from no-ball deliveries (penalty + batter runs)")
            k5.metric("🎯 Runs After Extra",    f"{int(total_after_extra)}",
                      help="Runs scored on the re-bowled delivery immediately after each wide/no-ball")
            k6.metric("📊 Extra Run %",         f"{overall_pct}%",
                      help=f"{int(total_extra_runs)} runs from extra balls as % of {int(total_runs)} total runs conceded")
            st.markdown("---")

            # ---- Match-wise view ----
            if edc_mode == "Match-wise":
                disp_cols = ['Bowling_Team', 'Opponent', 'Date',
                             'Wide_Deliveries', 'Wide_Balls',
                             'NoBall_Balls', 'NoBall_Runs',
                             'Extra_Ball_Runs', 'Runs_After_Extra', 'Extra_Run_%']
                rename = {
                    'Bowling_Team': 'Bowling Team',
                    'Wide_Deliveries': 'Wide Balls',
                    'Wide_Balls': 'Wide Runs',
                    'NoBall_Balls': 'NB Balls',
                    'NoBall_Runs': 'NB Runs',
                    'Extra_Ball_Runs': 'Extra Runs',
                    'Runs_After_Extra': 'Runs After Extra',
                    'Extra_Run_%': 'Extra Run %',
                }
                show_df = match_df[[c for c in disp_cols if c in match_df.columns]].rename(columns=rename)
                st.dataframe(
                    show_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'Extra Run %': st.column_config.NumberColumn(format='%.1f%%'),
                    }
                )

                # Chart: Extra Ball Runs vs Total Runs per match
                fig_bar = px.bar(
                    match_df.sort_values('Date').tail(40),
                    x='Date', y=['Team_Total_Runs', 'Extra_Ball_Runs'],
                    color_discrete_map={'Team_Total_Runs': '#4C9BE8', 'Extra_Ball_Runs': '#FF6B6B'},
                    barmode='overlay', opacity=0.85,
                    labels={'value': 'Runs', 'variable': 'Type', 'Date': 'Match Date'},
                    title="Total Runs vs Runs from Extra Balls (last 40 innings, per bowling team)",
                    color='Bowling_Team' if match_df['Bowling_Team'].nunique() == 1 else None
                )
                if match_df['Bowling_Team'].nunique() > 1:
                    # simple overlay chart by date
                    fig_bar = px.bar(
                        match_df.sort_values('Date').tail(50),
                        x='Date', y='Extra_Ball_Runs', color='Bowling_Team',
                        title="Runs from Extra Balls per Match by Bowling Team",
                        labels={'Extra_Ball_Runs': 'Runs from Extra Balls'}
                    )
                st.plotly_chart(fig_bar, use_container_width=True)

            # ---- Innings-wise view ----
            elif edc_mode == "Innings-wise":
                disp_cols = ['Bowling_Team', 'Batting_Team', 'Innings_Label', 'Date',
                             'Wide_Deliveries', 'Wide_Balls',
                             'NoBall_Balls', 'NoBall_Runs',
                             'Extra_Ball_Runs', 'Runs_After_Extra', 'Extra_Run_%']
                rename = {
                    'Bowling_Team': 'Bowling Team', 'Batting_Team': 'Batting Team',
                    'Innings_Label': 'Inn',
                    'Wide_Deliveries': 'Wide Balls',
                    'Wide_Balls': 'Wide Runs',
                    'NoBall_Balls': 'NB Balls',
                    'NoBall_Runs': 'NB Runs',
                    'Extra_Ball_Runs': 'Extra Runs',
                    'Runs_After_Extra': 'Runs After Extra',
                    'Extra_Run_%': 'Extra Run %',
                }
                show_df = inn_df[[c for c in disp_cols if c in inn_df.columns]].rename(columns=rename)
                st.dataframe(
                    show_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'Extra Run %': st.column_config.NumberColumn(format='%.1f%%'),
                    }
                )

                # 1st vs 2nd innings comparison
                inn_compare = inn_df.groupby('Innings_Label', observed=True).agg(
                    Avg_Extra_Deliveries=('Extra_Balls', 'mean'),
                    Avg_Extra_Runs=('Extra_Ball_Runs', 'mean'),
                    Avg_Wide_Runs=('Wide_Balls', 'mean'),
                    Avg_Wide_Deliveries=('Wide_Deliveries', 'mean'),
                    Avg_NoBalls=('NoBall_Balls', 'mean'),
                ).round(1).reset_index()
                st.markdown("#### 1st vs 2nd Innings Average Comparison")
                st.dataframe(inn_compare.rename(columns={'Innings_Label': 'Innings'}),
                             use_container_width=True, hide_index=True)

                fig_inn = px.bar(inn_compare, x='Innings_Label', y=['Avg_Wide_Runs', 'Avg_NoBalls'],
                                 barmode='group',
                                 title="Avg Wide Run Penalties & No-Ball Deliveries: 1st Inn vs 2nd Inn",
                                 labels={'value': 'Avg', 'variable': 'Type', 'Innings_Label': 'Innings'},
                                 color_discrete_map={'Avg_Wide_Runs': '#4CC3D9', 'Avg_NoBalls': '#FF8C00'})
                st.plotly_chart(fig_inn, use_container_width=True)

            # ---- Season Summary ----
            else:
                season_disp = ['Bowling_Team', 'Matches',
                               'Total_Wide_Deliveries', 'Total_Wide_Balls',
                               'Total_NoBall_Balls', 'Total_NoBall_Runs',
                               'Total_Extra_Ball_Runs', 'Total_Runs_After_Extra',
                               'Extra_Run_%', 'Avg_Extra_Runs_Per_Match']
                rename = {
                    'Bowling_Team': 'Bowling Team',
                    'Total_Wide_Deliveries': 'Wide Balls',
                    'Total_Wide_Balls': 'Wide Runs',
                    'Total_NoBall_Balls': 'NB Balls',
                    'Total_NoBall_Runs': 'NB Runs',
                    'Total_Extra_Ball_Runs': 'Extra Runs',
                    'Total_Runs_After_Extra': 'Runs After Extra',
                    'Extra_Run_%': 'Extra Run %',
                    'Avg_Extra_Runs_Per_Match': 'Avg Extra Runs/Match'
                }
                show_df = season_df[[c for c in season_disp if c in season_df.columns]].rename(columns=rename)
                st.dataframe(
                    show_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        'Extra Run %': st.column_config.NumberColumn(format='%.1f%%'),
                    }
                )

                # Team bar chart
                fig_s = px.bar(
                    season_df.sort_values('Total_Extra_Balls', ascending=False),
                    x='Bowling_Team', y=['Total_Wide_Balls', 'Total_NoBall_Balls'],
                    barmode='stack', color_discrete_map={'Total_Wide_Balls': '#4CC3D9', 'Total_NoBall_Balls': '#FF8C00'},
                    title="Wide Run Penalties & No-Ball Deliveries by Team (Season)",
                    labels={'value': 'Count', 'variable': 'Type', 'Bowling_Team': 'Team'}
                )
                fig_s.update_xaxes(tickangle=30)
                st.plotly_chart(fig_s, use_container_width=True)

                fig_r = px.bar(
                    season_df.sort_values('Extra_Run_%', ascending=False),
                    x='Bowling_Team', y='Extra_Run_%', color='Season',
                    title="Runs from Extra Balls as % of Total Runs Conceded",
                    labels={'Extra_Run_%': 'Extra Run %', 'Bowling_Team': 'Team'},
                    text='Extra_Run_%'
                )
                fig_r.update_traces(texttemplate='%{text}%', textposition='outside')
                fig_r.update_xaxes(tickangle=30)
                st.plotly_chart(fig_r, use_container_width=True)


# =========================================
# DEBUTANT BOWLER WICKETS
# =========================================
elif metric_choice == "Debutant Bowler Wickets":
    st.subheader("🎓 Debutant Bowler Wickets")
    st.write(
        "Wickets taken by bowlers on their debut appearance in a league or for a franchise. "
        "Debut = the first match that bowler ever appeared in for that league / team."
    )

    @st.cache_data(show_spinner=False)
    def debutant_bowler_wickets(df_, use_playing_xi=True):
        """
        For every (player, league) pair, find their TRUE debut match from playing_xi
        (first match they APPEARED in, regardless of whether they bowled).
        Then look up bowling stats for that debut match — players who didn't bowl
        appear with 0 wickets / 0 overs.
        Falls back to bowling-data-based debut when use_playing_xi=False (Franchise mode).
        """
        if df_.empty:
            return pd.DataFrame()

        d = df_.copy()
        for c in ['wicket_count', 'is_valid_delivery']:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)
        if 'byes' not in d.columns: d['byes'] = 0
        if 'leg_byes' not in d.columns: d['leg_byes'] = 0
        d['bowler_runs'] = d['runs.total'] - d['byes'] - d['leg_byes']

        team_col = 'bowling_team' if 'bowling_team' in d.columns else None

        # ── XI-based debut path (League Debut) ──────────────────────────────
        if use_playing_xi:
            try:
                xi = pd.read_parquet('playing_xi.parquet')
                xi['date'] = pd.to_datetime(xi['date'])
            except Exception:
                xi = pd.DataFrame()

            if not xi.empty:
                leagues_in = d['league'].astype(str).unique().tolist()
                xi = xi[xi['league'].astype(str).isin(leagues_in)].copy()

                # True debut = first match in playing XI per (player, league)
                debut_idx = (
                    xi.groupby(['player', 'league'], observed=True)['date']
                    .min().reset_index()
                    .rename(columns={'date': 'debut_date'})
                )

                # Only keep debutants whose debut year is in the user's year selection
                if 'year' in d.columns:
                    years_in = set(d['year'].dropna().unique().tolist())
                    debut_idx = debut_idx[
                        pd.to_datetime(debut_idx['debut_date']).dt.year.isin(years_in)
                    ]

                if debut_idx.empty:
                    return pd.DataFrame()

                # Resolve debut match_id, team, teams from xi
                xi_debuts = xi.merge(debut_idx, on=['player', 'league'], how='inner')
                xi_debuts = xi_debuts[xi_debuts['date'] == xi_debuts['debut_date']]
                xi_debuts = (
                    xi_debuts[['player', 'league', 'match_id', 'debut_date', 'team', 'teams']]
                    .drop_duplicates()
                    .rename(columns={'player': 'bowler'})
                )

                # Load full ball-by-ball (all years) for bowling stats on debut
                full_d = load_data()
                full_d = full_d[full_d['league'].astype(str).isin(leagues_in)].copy()
                for c in ['wicket_count', 'is_valid_delivery']:
                    if c in full_d.columns:
                        full_d[c] = pd.to_numeric(full_d[c], errors='coerce').fillna(0)
                if 'byes' not in full_d.columns: full_d['byes'] = 0
                if 'leg_byes' not in full_d.columns: full_d['leg_byes'] = 0
                full_d['bowler_runs'] = full_d['runs.total'] - full_d['byes'] - full_d['leg_byes']

                # Bowling stats for debut matches only
                debut_bowl = full_d.merge(
                    xi_debuts[['bowler', 'league', 'match_id']],
                    on=['bowler', 'league', 'match_id'], how='inner'
                )

                if not debut_bowl.empty:
                    bowl_stats = debut_bowl.groupby(
                        ['bowler', 'league', 'match_id'], observed=True
                    ).agg(
                        Wickets=('wicket_count', 'sum'),
                        Runs_Conceded=('bowler_runs', 'sum'),
                        Balls_Bowled=('is_valid_delivery', 'sum'),
                    ).reset_index()
                else:
                    bowl_stats = pd.DataFrame(
                        columns=['bowler', 'league', 'match_id',
                                 'Wickets', 'Runs_Conceded', 'Balls_Bowled']
                    )

                # Left-join: players in XI but who didn't bowl get 0 stats
                result = xi_debuts.merge(
                    bowl_stats, on=['bowler', 'league', 'match_id'], how='left'
                )
                for c in ['Wickets', 'Runs_Conceded', 'Balls_Bowled']:
                    if c in result.columns:
                        result[c] = result[c].fillna(0).astype(int)

                result['Overs'] = result['Balls_Bowled'].apply(
                    lambda b: f"{int(b)//6}.{int(b)%6}"
                )
                result['Economy'] = (
                    result['Runs_Conceded'] / (result['Balls_Bowled'] / 6)
                ).replace([np.inf, -np.inf], 0).round(2)

                # Against from teams column (already in xi_debuts via 'teams')
                result['teams'] = result['teams'].astype(str)
                result['team'] = result['team'].astype(str)
                result['Against'] = result.apply(
                    lambda r: next(
                        (p.strip() for p in r['teams'].split(' vs ')
                         if p.strip() != r['team']),
                        ''
                    ), axis=1
                )

                # Season from full_d
                if 'year' in full_d.columns:
                    yr_meta = full_d.drop_duplicates('match_id')[['match_id', 'year']].copy()
                    result = result.merge(yr_meta, on='match_id', how='left')
                    result = result.rename(columns={'year': 'Season'})

                result['Date'] = pd.to_datetime(result['debut_date']).dt.strftime('%d %b %Y')
                result = result.rename(columns={
                    'bowler': 'Bowler', 'league': 'League',
                    'match_id': 'Match ID', 'team': 'Team',
                })
                result = result.drop(columns=['debut_date', 'teams'], errors='ignore')

                col_order = ['Bowler', 'Team', 'Against', 'League', 'Season', 'Date',
                             'Wickets', 'Runs_Conceded', 'Overs', 'Economy',
                             'Balls_Bowled', 'Match ID']
                return result[[c for c in col_order if c in result.columns]].sort_values(
                    'Wickets', ascending=False
                ).reset_index(drop=True)

        # ── Fallback / Franchise-mode: bowling-data-based debut ─────────────
        debut_index = (
            d.groupby(['bowler', 'league'], observed=True)['date']
            .min().reset_index()
            .rename(columns={'date': 'debut_date'})
        )
        d = d.merge(debut_index, on=['bowler', 'league'], how='left')
        debut_rows = d[d['date'] == d['debut_date']].copy()

        if debut_rows.empty:
            return pd.DataFrame()

        grp_cols = ['bowler', 'league', 'match_id', 'debut_date']
        if team_col:
            grp_cols.append(team_col)

        stats = debut_rows.groupby(grp_cols, observed=True).agg(
            Wickets=('wicket_count', 'sum'),
            Runs_Conceded=('bowler_runs', 'sum'),
            Balls_Bowled=('is_valid_delivery', 'sum'),
        ).reset_index()

        stats['Overs'] = stats['Balls_Bowled'].apply(
            lambda b: f"{int(b)//6}.{int(b)%6}"
        )
        stats['Economy'] = (
            stats['Runs_Conceded'] / (stats['Balls_Bowled'] / 6)
        ).replace([np.inf, -np.inf], 0).round(2)

        if 'teams' in debut_rows.columns and team_col:
            meta = debut_rows.drop_duplicates('match_id')[['match_id', 'teams']].copy()
            meta['teams'] = meta['teams'].astype(str)
            stats = stats.merge(meta, on='match_id', how='left')
            stats[team_col] = stats[team_col].astype(str)
            stats['Against'] = stats.apply(
                lambda r: next(
                    (p.strip() for p in str(r.get('teams', '')).split(' vs ')
                     if p.strip() != r.get(team_col, '')),
                    ''
                ), axis=1
            )
            stats = stats.drop(columns=['teams'], errors='ignore')
        elif 'teams' in debut_rows.columns:
            meta = debut_rows.drop_duplicates('match_id')[['match_id', 'teams']].copy()
            stats = stats.merge(meta, on='match_id', how='left')
            stats['Against'] = stats['teams'].astype(str)
            stats = stats.drop(columns=['teams'], errors='ignore')

        if 'year' in debut_rows.columns:
            yr_meta = debut_rows.drop_duplicates('match_id')[['match_id', 'year']].copy()
            stats = stats.merge(yr_meta, on='match_id', how='left')
            stats = stats.rename(columns={'year': 'Season'})

        stats['Date'] = pd.to_datetime(stats['debut_date']).dt.strftime('%d %b %Y')
        rename = {'bowler': 'Bowler', 'league': 'League',
                  'match_id': 'Match ID', 'debut_date': '_drop'}
        if team_col:
            rename[team_col] = 'Team'
        stats = stats.rename(columns=rename).drop(columns=['_drop'], errors='ignore')

        col_order = ['Bowler', 'Team', 'Against', 'League', 'Season', 'Date',
                     'Wickets', 'Runs_Conceded', 'Overs', 'Economy', 'Balls_Bowled', 'Match ID']
        return stats[[c for c in col_order if c in stats.columns]].sort_values(
            'Wickets', ascending=False
        ).reset_index(drop=True)

    deb_df_src = fdf.copy()
    if deb_df_src.empty:
        st.warning("No data for selected filters.")
    else:
        deb_col1, deb_col2, deb_col3 = st.columns([2, 1, 1])
        with deb_col1:
            deb_scope = st.radio(
                "Debut Scope",
                ["League Debut (first ever match in that league)",
                 "Franchise Debut (first match for each team)"],
                key="deb_scope", horizontal=True
            )
        with deb_col2:
            min_debut_wkts = st.number_input("Min Wickets on Debut", min_value=0, max_value=10,
                                              value=1, step=1, key="deb_min_wkts")
        with deb_col3:
            top_n_deb = st.number_input("Top N in chart", min_value=5, max_value=50,
                                        value=15, step=1, key="deb_top_n")

        # Player filter
        all_bowlers_deb = sorted(deb_df_src['bowler'].dropna().astype(str).unique())
        deb_player_filter = st.multiselect(
            "Filter by Bowler(s) — leave empty to show all",
            all_bowlers_deb, key="deb_player_filter"
        )

        if deb_scope.startswith("Franchise"):
            # Franchise debut: group by (bowler, team), find first date per team
            tc = 'bowling_team' if 'bowling_team' in deb_df_src.columns else 'team'
            fran_debut_idx = (
                deb_df_src.groupby(['bowler', tc], observed=True)['date']
                .min().reset_index().rename(columns={'date': 'debut_date'})
            )
            deb_df_src2 = deb_df_src.merge(fran_debut_idx, on=['bowler', tc], how='left')
            deb_df_src2 = deb_df_src2[deb_df_src2['date'] == deb_df_src2['debut_date']]
            # Temporarily patch 'league' with team so the shared function groups by team
            deb_df_src2 = deb_df_src2.copy()
            deb_df_src2['_orig_league'] = deb_df_src2['league']
            deb_df_src2['league'] = deb_df_src2[tc].astype(str)
            debut_result = debutant_bowler_wickets(deb_df_src2, use_playing_xi=False)
            if 'League' in debut_result.columns:
                debut_result = debut_result.rename(columns={'League': 'Franchise'})
        else:
            debut_result = debutant_bowler_wickets(deb_df_src, use_playing_xi=True)

        if deb_player_filter:
            debut_result = debut_result[debut_result['Bowler'].isin(deb_player_filter)]

        debut_result = debut_result[debut_result['Wickets'] >= int(min_debut_wkts)]

        if debut_result.empty:
            st.info("No debutant bowlers found matching the selected filters.")
        else:
            tab_all, tab_league, tab_top = st.tabs(["All Debuts", "By League", "Top Performers"])

            with tab_all:
                st.markdown(f"**{len(debut_result)} debut appearances** matching filters")
                st.dataframe(debut_result, use_container_width=True)

            with tab_league:
                league_col = 'Franchise' if deb_scope.startswith("Franchise") else 'League'
                if league_col in debut_result.columns:
                    leagues_deb = sorted(debut_result[league_col].dropna().unique())
                    lg_tabs_deb = st.tabs([str(l) for l in leagues_deb])
                    for li, lg in enumerate(leagues_deb):
                        with lg_tabs_deb[li]:
                            lg_deb = debut_result[debut_result[league_col] == lg].copy()
                            st.dataframe(lg_deb, use_container_width=True)
                            chart_deb = lg_deb.head(int(top_n_deb))
                            if not chart_deb.empty:
                                color_col = 'Team' if 'Team' in chart_deb.columns else 'Bowler'
                                fig_deb = px.bar(
                                    chart_deb, x='Bowler', y='Wickets',
                                    color=color_col,
                                    hover_data=[c for c in ['Team', 'Against', 'Date', 'Overs', 'Economy']
                                                if c in chart_deb.columns],
                                    title=f"Top {int(top_n_deb)} Debut Wicket Performances — {lg}",
                                    text='Wickets'
                                )
                                fig_deb.update_traces(textposition='outside')
                                fig_deb.update_xaxes(tickangle=45)
                                st.plotly_chart(fig_deb, use_container_width=True)
                else:
                    st.dataframe(debut_result, use_container_width=True)

            with tab_top:
                st.markdown("### Bowlers with Most Wickets on Debut (Career Best Debut)")
                # Keep the best debut (most wickets) per bowler
                top_deb = (
                    debut_result
                    .sort_values('Wickets', ascending=False)
                    .drop_duplicates(subset='Bowler', keep='first')
                    .head(int(top_n_deb))
                    .reset_index(drop=True)
                )
                st.dataframe(top_deb, use_container_width=True)
                if not top_deb.empty:
                    color_col_top = 'Team' if 'Team' in top_deb.columns else 'Bowler'
                    fig_top = px.bar(
                        top_deb, x='Bowler', y='Wickets',
                        color=color_col_top,
                        hover_data=[c for c in ['Team', 'Against', 'Date', 'Overs', 'Economy']
                                    if c in top_deb.columns],
                        title=f"Best Debut Performances — Top {int(top_n_deb)} Bowlers",
                        text='Wickets'
                    )
                    fig_top.update_traces(textposition='outside')
                    fig_top.update_xaxes(tickangle=45)
                    st.plotly_chart(fig_top, use_container_width=True)

                # Distribution histogram
                wkt_dist = debut_result['Wickets'].value_counts().sort_index().reset_index()
                wkt_dist.columns = ['Wickets on Debut', 'Count']
                fig_hist = px.bar(
                    wkt_dist, x='Wickets on Debut', y='Count',
                    title="Distribution of Wickets Taken on Debut",
                    text='Count'
                )
                fig_hist.update_traces(textposition='outside')
                st.plotly_chart(fig_hist, use_container_width=True)


# =========================================
# LONGEST WICKETLESS STREAKS
# =========================================
elif metric_choice == "Longest Wicketless Streaks":
    st.subheader("🔵 Longest Wicketless Streaks")
    st.write(
        "Longest consecutive deliveries bowled without taking a wicket — "
        "measured in legal (valid) balls across the filtered data."
    )

    @st.cache_data(show_spinner=False)
    def longest_wicketless_streaks(df_):
        """
        For each bowler, find ALL runs of consecutive legal deliveries
        (is_valid_delivery == 1) without a wicket (wicket_count == 0).
        Returns one row per streak — a bowler may appear multiple times.
        """
        if df_.empty:
            return pd.DataFrame()

        d = df_.copy()
        for c in ['wicket_count', 'is_valid_delivery']:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)

        required = {'bowler', 'wicket_count', 'is_valid_delivery', 'match_id', 'date'}
        if not required.issubset(d.columns):
            return pd.DataFrame()

        sort_cols = ['bowler', 'date', 'match_id']
        extra = [c for c in ['innings', 'over', 'ball_float'] if c in d.columns]
        d = d.sort_values(sort_cols + extra).reset_index(drop=True)

        legal = d[d['is_valid_delivery'] == 1].copy().reset_index(drop=True)
        if legal.empty:
            return pd.DataFrame()

        team_col = 'bowling_team' if 'bowling_team' in legal.columns else (
            'team' if 'team' in legal.columns else None
        )

        def _safe_mode(series):
            m = series.dropna()
            return str(m.mode().iloc[0]) if len(m.mode()) > 0 else ''

        def _flush(bowler, grp, streak_start, streak_len, records, last_wicket_match_id):
            if streak_len == 0:
                return
            window = grp.iloc[streak_start: streak_start + streak_len]
            if window.empty:
                return
            # Streak start/span = from the first NEW match after the wicket match
            if last_wicket_match_id is not None and 'match_id' in window.columns:
                new_match_rows = window[window['match_id'] != last_wicket_match_id]
                start_date = pd.to_datetime(new_match_rows['date'].iloc[0]).strftime('%d %b %Y') if not new_match_rows.empty else pd.to_datetime(window['date'].iloc[0]).strftime('%d %b %Y')
                matches_spanned = new_match_rows['match_id'].nunique()
            else:
                start_date = pd.to_datetime(window['date'].iloc[0]).strftime('%d %b %Y')
                matches_spanned = window['match_id'].nunique()
            records.append({
                'Bowler':          str(bowler),
                'Team':            _safe_mode(window[team_col]) if (team_col and team_col in window.columns) else '',
                'League':          _safe_mode(window['league']) if 'league' in window.columns else '',
                'Season':          _safe_mode(window['year']) if 'year' in window.columns else '',
                'Streak (Balls)':  streak_len,
                'Streak (Overs)':  round(streak_len / 6, 1),
                'Matches Spanned': matches_spanned,
                'Streak Start':    start_date,
                'Streak End':      pd.to_datetime(window['date'].iloc[-1]).strftime('%d %b %Y'),
            })

        records = []
        for bowler, grp in legal.groupby('bowler', observed=True, sort=False):
            grp = grp.reset_index(drop=True)
            streak = 0
            streak_start = 0
            last_wicket_match_id = None

            for idx, row in grp.iterrows():
                if row['wicket_count'] == 0:
                    streak += 1
                else:
                    _flush(bowler, grp, streak_start, streak, records, last_wicket_match_id)
                    streak = 0
                    streak_start = idx + 1
                    last_wicket_match_id = row['match_id']

            # flush any active streak at end of data
            _flush(bowler, grp, streak_start, streak, records, last_wicket_match_id)

        if not records:
            return pd.DataFrame()
        return (
            pd.DataFrame(records)
            .sort_values('Streak (Balls)', ascending=False)
            .reset_index(drop=True)
        )

    @st.cache_data(show_spinner=False)
    def wicketless_over_streaks(df_):
        """
        Longest consecutive OVERS (complete) without conceding a wicket, per bowler.
        An over 'has a wicket' if wicket_count > 0 for any ball in that over.
        """
        if df_.empty:
            return pd.DataFrame()

        d = df_.copy()
        for c in ['wicket_count', 'is_valid_delivery']:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)

        needed = {'bowler', 'wicket_count', 'over', 'match_id', 'date', 'innings'}
        if not needed.issubset(d.columns):
            return pd.DataFrame()

        d = d[d['innings'].isin([1, 2])].copy()
        if d.empty:
            return pd.DataFrame()

        # Summarise to one row per (bowler, match, innings, over)
        over_grp = d.groupby(
            ['bowler', 'match_id', 'innings', 'over', 'date'], observed=True
        ).agg(
            wickets_in_over=('wicket_count', 'sum'),
            league=('league', 'first') if 'league' in d.columns else ('wicket_count', 'count'),
            year=('year', 'first') if 'year' in d.columns else ('wicket_count', 'count'),
            team=('bowling_team' if 'bowling_team' in d.columns else 'team', 'first'),
        ).reset_index()

        team_col_og = 'bowling_team' if 'bowling_team' in d.columns else 'team'
        over_grp = over_grp.sort_values(['bowler', 'date', 'match_id', 'innings', 'over'])

        def _safe_mode2(series):
            m = series.dropna()
            return str(m.mode().iloc[0]) if len(m.mode()) > 0 else ''

        def _flush_over(bowler, grp, streak_start, streak_len, records, last_wicket_match_id):
            if streak_len == 0:
                return
            window = grp.iloc[streak_start: streak_start + streak_len]
            if window.empty:
                return
            # Streak start/span = from the first NEW match after the wicket match
            if last_wicket_match_id is not None and 'match_id' in window.columns:
                new_match_rows = window[window['match_id'] != last_wicket_match_id]
                start_date = pd.to_datetime(new_match_rows['date'].iloc[0]).strftime('%d %b %Y') if not new_match_rows.empty else pd.to_datetime(window['date'].iloc[0]).strftime('%d %b %Y')
                matches_spanned = new_match_rows['match_id'].nunique()
            else:
                start_date = pd.to_datetime(window['date'].iloc[0]).strftime('%d %b %Y')
                matches_spanned = window['match_id'].nunique()
            records.append({
                'Bowler':          str(bowler),
                'Team':            _safe_mode2(window['team']) if not window.empty else '',
                'League':          _safe_mode2(window['league']) if ('league' in window.columns and not window.empty) else '',
                'Season':          _safe_mode2(window['year']) if ('year' in window.columns and not window.empty) else '',
                'Streak (Overs)':  streak_len,
                'Matches Spanned': matches_spanned,
                'Streak Start':    start_date,
                'Streak End':      pd.to_datetime(window['date'].iloc[-1]).strftime('%d %b %Y'),
            })

        records = []
        for bowler, grp in over_grp.groupby('bowler', observed=True, sort=False):
            grp = grp.reset_index(drop=True)
            streak = 0
            streak_start = 0
            last_wicket_match_id = None

            for idx, row in grp.iterrows():
                if row['wickets_in_over'] == 0:
                    streak += 1
                else:
                    _flush_over(bowler, grp, streak_start, streak, records, last_wicket_match_id)
                    streak = 0
                    streak_start = idx + 1
                    last_wicket_match_id = row['match_id']

            _flush_over(bowler, grp, streak_start, streak, records, last_wicket_match_id)

        if not records:
            return pd.DataFrame()
        return (
            pd.DataFrame(records)
            .sort_values('Streak (Overs)', ascending=False)
            .reset_index(drop=True)
        )

    @st.cache_data(show_spinner=False)
    def wicketless_match_streaks(df_):
        """
        Longest consecutive MATCHES without taking a wicket, per bowler.
        A match 'has a wicket' if wicket_count > 0 for any delivery in that match.
        This is the most player-inclusive definition of a wicketless streak.
        """
        if df_.empty:
            return pd.DataFrame()

        d = df_.copy()
        if 'wicket_count' in d.columns:
            d['wicket_count'] = pd.to_numeric(d['wicket_count'], errors='coerce').fillna(0)

        needed = {'bowler', 'wicket_count', 'match_id', 'date'}
        if not needed.issubset(d.columns):
            return pd.DataFrame()

        team_col = 'bowling_team' if 'bowling_team' in d.columns else (
            'team' if 'team' in d.columns else None
        )

        # Build aggregation dict for match-level summary
        agg_dict = {
            'wickets_in_match': ('wicket_count', 'sum'),
            'date': ('date', 'first'),
        }
        if team_col:
            agg_dict['team'] = (team_col, 'first')
        if 'year' in d.columns:
            agg_dict['year'] = ('year', 'first')
        if 'league' in d.columns:
            agg_dict['league'] = ('league', 'first')

        match_grp = (
            d.groupby(['bowler', 'match_id'], observed=True)
            .agg(**agg_dict)
            .reset_index()
        )
        match_grp = match_grp.sort_values(['bowler', 'date', 'match_id'])

        def _safe_mode(series):
            m = series.dropna()
            return str(m.mode().iloc[0]) if len(m.mode()) > 0 else ''

        def _flush_match(bowler, grp, streak_start, streak_len, records):
            if streak_len == 0:
                return
            window = grp.iloc[streak_start: streak_start + streak_len]
            if window.empty:
                return
            records.append({
                'Bowler':           str(bowler),
                'Team':             _safe_mode(window['team']) if ('team' in window.columns and not window.empty) else '',
                'League':           _safe_mode(window['league']) if ('league' in window.columns and not window.empty) else '',
                'Season':           _safe_mode(window['year']) if ('year' in window.columns and not window.empty) else '',
                'Streak (Matches)': streak_len,
                'Streak Start':     pd.to_datetime(window['date'].iloc[0]).strftime('%d %b %Y'),
                'Streak End':       pd.to_datetime(window['date'].iloc[-1]).strftime('%d %b %Y'),
            })

        records = []
        for bowler, grp in match_grp.groupby('bowler', observed=True, sort=False):
            grp = grp.reset_index(drop=True)
            streak = 0
            streak_start = 0

            for idx, row in grp.iterrows():
                if row['wickets_in_match'] == 0:
                    streak += 1
                else:
                    _flush_match(bowler, grp, streak_start, streak, records)
                    streak = 0
                    streak_start = idx + 1

            _flush_match(bowler, grp, streak_start, streak, records)

        if not records:
            return pd.DataFrame()
        return (
            pd.DataFrame(records)
            .sort_values('Streak (Matches)', ascending=False)
            .reset_index(drop=True)
        )

    # Use fdf_no_team so ALL bowling deliveries are included regardless of
    # which batting team is selected in the sidebar (bowler streaks span both innings).
    wls_source = fdf_no_team.copy()
    if selected_teams:
        # Re-apply team filter using bowling_team (the bowler's own team)
        bowling_team_col = 'bowling_team' if 'bowling_team' in wls_source.columns else None
        if bowling_team_col:
            wls_source = wls_source[wls_source[bowling_team_col].astype(str).isin([str(t) for t in selected_teams])]
    if wls_source.empty:
        st.warning("No data for selected filters.")
    else:
        wls_col1, wls_col2, wls_col3 = st.columns([2, 1, 1])
        with wls_col1:
            wls_scope = st.radio(
                "Streak measured in",
                ["Matches (consecutive matches without wicket)", "Balls (legal deliveries)", "Overs (complete overs)"],
                key="wls_scope", horizontal=True
            )
        with wls_col2:
            top_n_wls = st.number_input(
                "Top N", min_value=5, max_value=100, value=20, step=5, key="wls_top_n"
            )
        with wls_col3:
            if wls_scope.startswith("Matches"):
                wls_min = st.number_input(
                    "Min Matches", min_value=1, max_value=100, value=2, step=1, key="wls_min_match"
                )
            elif wls_scope.startswith("Overs"):
                wls_min = st.number_input(
                    "Min Overs", min_value=1, max_value=100, value=3, step=1, key="wls_min_over"
                )
            else:
                wls_min = st.number_input(
                    "Min Balls", min_value=1, max_value=500, value=12, step=6, key="wls_min_ball"
                )

        # Optional player filter — built from full bowling data for the league/year
        all_bowlers_wls = sorted(wls_source['bowler'].dropna().astype(str).unique())
        wls_player_filter = st.multiselect(
            "Filter by Bowler(s) — leave empty to show all",
            all_bowlers_wls, key="wls_player_filter"
        )

        with st.spinner("Computing wicketless streaks..."):
            if wls_scope.startswith("Balls"):
                wls_df = longest_wicketless_streaks(wls_source)
                streak_col = 'Streak (Balls)'
                unit = 'balls'
            elif wls_scope.startswith("Overs"):
                wls_df = wicketless_over_streaks(wls_source)
                streak_col = 'Streak (Overs)'
                unit = 'overs'
            else:
                wls_df = wicketless_match_streaks(wls_source)
                streak_col = 'Streak (Matches)'
                unit = 'matches'

        if wls_player_filter and not wls_df.empty:
            wls_df = wls_df[wls_df['Bowler'].isin(wls_player_filter)]

        if not wls_df.empty and streak_col in wls_df.columns:
            wls_df = wls_df[wls_df[streak_col] >= int(wls_min)]

        if wls_df is None or wls_df.empty:
            st.info("No wicketless streak data found for the selected filters. Try reducing the minimum threshold.")
        else:
            tab_all, tab_league, tab_chart = st.tabs(["All Streaks", "By League", "Charts"])

            display_df = wls_df.head(int(top_n_wls)).reset_index(drop=True)
            display_df.index += 1

            with tab_all:
                st.markdown(f"**Top {int(top_n_wls)} longest wicketless streaks — measured in {unit}**")
                st.dataframe(display_df, use_container_width=True)

            with tab_league:
                if 'League' in wls_df.columns:
                    leagues_wls = sorted(wls_df['League'].dropna().unique())
                    lg_tabs_wls = st.tabs([str(l) for l in leagues_wls])
                    for li, lg in enumerate(leagues_wls):
                        with lg_tabs_wls[li]:
                            lg_wls = wls_df[wls_df['League'] == lg].head(int(top_n_wls)).reset_index(drop=True)
                            lg_wls.index += 1
                            st.dataframe(lg_wls, use_container_width=True)

            with tab_chart:
                chart_wls = wls_df.head(int(top_n_wls)).copy()
                if not chart_wls.empty:
                    color_wls = 'Team' if 'Team' in chart_wls.columns else 'Bowler'
                    fig_wls = px.bar(
                        chart_wls,
                        x='Bowler', y=streak_col,
                        color=color_wls,
                        hover_data=[c for c in ['Team', 'League', 'Season',
                                                'Matches Spanned', 'Streak Start', 'Streak End']
                                    if c in chart_wls.columns],
                        title=f"Top {int(top_n_wls)} Longest Wicketless Streaks ({unit})",
                        text=streak_col
                    )
                    fig_wls.update_traces(textposition='outside')
                    fig_wls.update_xaxes(tickangle=45)
                    st.plotly_chart(fig_wls, use_container_width=True)

                    # Distribution
                    if len(wls_df) >= 5:
                        st.markdown("**Distribution of wicketless streak lengths**")
                        fig_dist = px.histogram(
                            wls_df, x=streak_col, nbins=30,
                            title=f"Distribution of Wicketless Streak Lengths ({unit})",
                            labels={streak_col: f'Streak ({unit})', 'count': 'Number of Bowlers'}
                        )
                        st.plotly_chart(fig_dist, use_container_width=True)


# =========================================
# BALLS BOWLED PER MATCH
# =========================================
elif metric_choice == "Balls Bowled Per Match":
    st.subheader("⚾ Balls Bowled Per Match")
    st.write(
        "Total legal deliveries (valid balls) bowled in each match, "
        "broken down by innings and phase. Useful for identifying "
        "matches cut short by rain, DLS, or super overs."
    )

    @st.cache_data(show_spinner=False)
    def balls_bowled_per_match(df_):
        if df_.empty:
            return pd.DataFrame()

        d = df_.copy()
        for c in ['is_valid_delivery', 'wides', 'no_balls']:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)
            else:
                d[c] = 0

        needed = {'match_id', 'date', 'innings', 'is_valid_delivery'}
        if not needed.issubset(d.columns):
            return pd.DataFrame()

        d = d[d['innings'].isin([1, 2])].copy()
        if d.empty:
            return pd.DataFrame()

        team_col = 'batting_team' if 'batting_team' in d.columns else 'team'

        agg_cols = {
            'Legal Balls': ('is_valid_delivery', 'sum'),
            'Wides':       ('wides', 'sum'),
            'No Balls':    ('no_balls', 'sum'),
            'date':        ('date', 'first'),
        }
        if team_col in d.columns:
            agg_cols['Batting Team'] = (team_col, 'first')
        if 'teams' in d.columns:
            agg_cols['Match'] = ('teams', 'first')
        if 'league' in d.columns:
            agg_cols['League'] = ('league', 'first')
        if 'year' in d.columns:
            agg_cols['Season'] = ('year', 'first')
        if 'venue' in d.columns:
            agg_cols['Venue'] = ('venue', 'first')

        inn_grp = (
            d.groupby(['match_id', 'innings'], observed=True)
            .agg(**agg_cols)
            .reset_index()
        )
        inn_grp['Total Deliveries'] = inn_grp['Legal Balls'] + inn_grp['Wides'] + inn_grp['No Balls']
        inn_grp['Overs Bowled'] = inn_grp['Legal Balls'].apply(
            lambda b: f"{int(b)//6}.{int(b)%6}"
        )
        inn_grp['Date'] = pd.to_datetime(inn_grp['date']).dt.strftime('%d %b %Y')
        inn_grp = inn_grp.drop(columns=['date'], errors='ignore')
        inn_grp['innings'] = inn_grp['innings'].astype(int)
        inn_grp = inn_grp.rename(columns={'match_id': 'Match ID', 'innings': 'Innings'})

        # Match-level totals (both innings combined)
        match_agg = {'Total_Balls': ('Legal Balls', 'sum'),
                     'Total_Wides': ('Wides', 'sum'),
                     'Total_NoBalls': ('No Balls', 'sum'),
                     'Total_Deliveries': ('Total Deliveries', 'sum'),
                     'Date': ('Date', 'first')}
        for col in ['Match', 'League', 'Season', 'Venue']:
            if col in inn_grp.columns:
                match_agg[col] = (col, 'first')
        match_total = (
            inn_grp.groupby('Match ID', observed=True)
            .agg(**match_agg)
            .reset_index()
        )
        match_total['Total Overs'] = match_total['Total_Balls'].apply(
            lambda b: f"{int(b)//6}.{int(b)%6}"
        )
        match_total = match_total.rename(columns={
            'Total_Balls':      'Total Legal Balls',
            'Total_Wides':      'Total Wides',
            'Total_NoBalls':    'Total No Balls',
            'Total_Deliveries': 'Total Deliveries',
        })

        return inn_grp, match_total

    src_bbpm = fdf.copy()
    if src_bbpm.empty:
        st.warning("No data for selected filters.")
    else:
        result_bbpm = balls_bowled_per_match(src_bbpm)
        if not result_bbpm or (isinstance(result_bbpm, tuple) and result_bbpm[0].empty):
            st.info("No data found for selected filters.")
        else:
            inn_df, match_df = result_bbpm

            bbpm_col1, bbpm_col2 = st.columns([2, 1])
            with bbpm_col1:
                bbpm_view = st.radio(
                    "View by",
                    ["Match Total", "Innings Breakdown"],
                    key="bbpm_view", horizontal=True
                )
            with bbpm_col2:
                bbpm_top_n = st.number_input(
                    "Top N matches", min_value=5, max_value=500, value=20, step=5, key="bbpm_top_n"
                )

            tab_table, tab_chart, tab_phase = st.tabs(["Table", "Chart", "Phase Breakdown"])

            with tab_table:
                if bbpm_view == "Match Total":
                    # Build a pivoted view: one row per match, team1 vs team2 side-by-side
                    inn_sorted = inn_df.sort_values(['Match ID', 'Innings'])
                    rows = []
                    for match_id, grp in inn_sorted.groupby('Match ID', observed=True, sort=False):
                        grp = grp.sort_values('Innings').reset_index(drop=True)
                        row = {
                            'Date':            grp['Date'].iloc[0] if 'Date' in grp.columns else '',
                            'Venue':           grp['Venue'].iloc[0] if 'Venue' in grp.columns else '',
                            'League':          grp['League'].iloc[0] if 'League' in grp.columns else '',
                            'Season':          grp['Season'].iloc[0] if 'Season' in grp.columns else '',
                            'Total Balls':     int(grp['Total Deliveries'].sum()),
                        }
                        for i in range(min(2, len(grp))):
                            r = grp.iloc[i]
                            label = f"Inn {int(r['Innings'])}"
                            team = str(r.get('Batting Team', ''))
                            stats = (
                                f"Balls: {int(r['Legal Balls'])} | "
                                f"Wd: {int(r['Wides'])} | "
                                f"Nb: {int(r['No Balls'])}"
                            )
                            row[f'{label} Team']  = team
                            row[f'{label} Stats'] = stats
                        rows.append(row)

                    pivot_df = pd.DataFrame(rows)
                    pivot_df = pivot_df.sort_values('Total Balls', ascending=False).head(int(bbpm_top_n)).reset_index(drop=True)
                    pivot_df.index += 1

                    col_order = [c for c in [
                        'Date', 'Venue', 'League', 'Season', 'Total Balls',
                        'Inn 1 Team', 'Inn 1 Stats', 'Inn 2 Team', 'Inn 2 Stats'
                    ] if c in pivot_df.columns]
                    st.dataframe(pivot_df[col_order], use_container_width=True)
                else:
                    disp = inn_df.sort_values(['Date', 'Match ID', 'Innings']).head(int(bbpm_top_n) * 2).reset_index(drop=True)
                    disp.index += 1
                    col_order = [c for c in ['Match', 'Innings', 'Batting Team', 'League',
                                              'Season', 'Date', 'Legal Balls', 'Overs Bowled',
                                              'Wides', 'No Balls', 'Total Deliveries']
                                 if c in disp.columns]
                    st.dataframe(disp[col_order], use_container_width=True)

            with tab_chart:
                if bbpm_view == "Match Total":
                    chart_data = match_df.sort_values('Total Legal Balls', ascending=False).head(int(bbpm_top_n)).copy()
                    color_col = 'League' if 'League' in chart_data.columns else 'Match ID'
                    label_col = 'Match' if 'Match' in chart_data.columns else 'Match ID'
                    fig_bbpm = px.bar(
                        chart_data,
                        x=label_col, y='Total Deliveries',
                        color=color_col,
                        text='Total Overs',
                        hover_data=[c for c in ['Total Legal Balls', 'Total Wides', 'Total No Balls',
                                                 'League', 'Season', 'Date', 'Venue']
                                    if c in chart_data.columns],
                        title=f"Top {int(bbpm_top_n)} Matches by Total Deliveries (incl. Wides & No Balls)"
                    )
                    fig_bbpm.update_traces(textposition='outside')
                    fig_bbpm.update_xaxes(tickangle=45)
                    st.plotly_chart(fig_bbpm, use_container_width=True)
                else:
                    chart_data = inn_df.copy()
                    if 'Match' in chart_data.columns:
                        chart_data['Match Label'] = chart_data['Match'].astype(str) + ' Inn' + chart_data['Innings'].astype(str)
                    else:
                        chart_data['Match Label'] = chart_data['Match ID'].astype(str) + ' Inn' + chart_data['Innings'].astype(str)
                    chart_data = chart_data.sort_values('Total Deliveries', ascending=False).head(int(bbpm_top_n))
                    fig_inn = px.bar(
                        chart_data,
                        x='Match Label', y='Total Deliveries',
                        color='Innings',
                        text='Overs Bowled',
                        hover_data=[c for c in ['Legal Balls', 'Wides', 'No Balls'] if c in chart_data.columns],
                        title=f"Top {int(bbpm_top_n)} Innings by Total Deliveries"
                    )
                    fig_inn.update_traces(textposition='outside')
                    fig_inn.update_xaxes(tickangle=45)
                    st.plotly_chart(fig_inn, use_container_width=True)

            with tab_phase:
                if 'phase' in src_bbpm.columns:
                    phase_cols = {
                        'Legal Balls': ('is_valid_delivery', 'sum'),
                    }
                    if 'league' in src_bbpm.columns:
                        phase_cols['League'] = ('league', 'first')
                    if 'year' in src_bbpm.columns:
                        phase_cols['Season'] = ('year', 'first')

                    phase_src = src_bbpm[src_bbpm['innings'].isin([1, 2])].copy()
                    phase_src['is_valid_delivery'] = pd.to_numeric(phase_src['is_valid_delivery'], errors='coerce').fillna(0)
                    for ec in ['wides', 'no_balls']:
                        if ec in phase_src.columns:
                            phase_src[ec] = pd.to_numeric(phase_src[ec], errors='coerce').fillna(0)
                        else:
                            phase_src[ec] = 0
                    phase_df = (
                        phase_src.groupby(['phase'], observed=True)
                        .agg(
                            Legal_Balls=('is_valid_delivery', 'sum'),
                            Wides=('wides', 'sum'),
                            No_Balls=('no_balls', 'sum'),
                        )
                        .reset_index()
                    )
                    phase_df['Total Deliveries'] = phase_df['Legal_Balls'] + phase_df['Wides'] + phase_df['No_Balls']
                    phase_df['Overs'] = phase_df['Legal_Balls'].apply(
                        lambda b: f"{int(b)//6}.{int(b)%6}"
                    )
                    phase_df = phase_df.rename(columns={
                        'phase': 'Phase', 'Legal_Balls': 'Legal Balls',
                        'No_Balls': 'No Balls'
                    })
                    st.markdown("**Balls bowled by phase (across all selected matches)**")
                    st.dataframe(phase_df, use_container_width=True)

                    fig_phase = px.pie(
                        phase_df, names='Phase', values='Legal Balls',
                        title="Share of Balls Bowled by Phase"
                    )
                    st.plotly_chart(fig_phase, use_container_width=True)
                else:
                    st.info("Phase data not available.")


st.markdown("---")
st.markdown("*Data extracted from Cricsheet JSON files.*")