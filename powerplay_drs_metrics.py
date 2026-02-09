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
st.markdown("📅 Last updated: 2026-02-03")

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
    "Most Wickets in an Over",
    "Left-Right Hand Index",
    "Pace vs Spin Analysis",
    "Super Over Analysis",
    "Innings Progression",
    "Franchise Debut Tracker"
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
    
    if mode == 'batting':
        grp = pp.groupby(['match_id', 'team', 'innings', 'date', 'year', 'teams'], observed=True)
        
        stats = grp.agg(
            PP_Runs=('runs.total', 'sum'),
            PP_Balls=('is_valid_delivery', 'sum'),
            PP_4s=('runs.batter', lambda x: (x == 4).sum()),
            PP_6s=('runs.batter', lambda x: (x == 6).sum()),
            PP_Dots=('runs.batter', lambda x: ((x == 0) & (pp.loc[x.index, 'is_valid_delivery'] == 1)).sum()),
            PP_Wickets=('wicket_count', 'sum')
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
            PP_Wickets_Taken=('wicket_count', 'sum')
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
                             'PP_Wickets_Taken', 'match_id']].copy()
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
        tab1, tab2, tab3, tab4 = st.tabs(["📋 Match-by-Match", "📊 Season Summary", "🏟️ Venue-wise", "🏆 Playoff Matches"])
        
        with tab1:
            if mode_val == 'batting':
                display_cols = ['Team', 'Opponent', 'Date', 'Season', 'Innings', 'PP_Runs', 'PP_RR', 'PP_Boundaries', 'PP_4s', 'PP_6s', 'PP_Dot%', 'PP_Wickets']
            else:
                display_cols = ['Team', 'Against', 'Date', 'Season', 'Innings', 'PP_Runs_Conceded', 'PP_Econ', 'PP_Boundaries_Conceded', 'PP_Dot%', 'PP_Wickets_Taken']
            
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
                            PP_Wickets=('wicket_count', 'sum'),
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
        tab1, tab2, tab3 = st.tabs(["🏏 Top Run Scorers by Over", "🎯 Most Runs Conceded by Over", "📈 Over-wise Summary"])
        
        with tab1:
            st.markdown("### Batters who scored most runs in a single over")
            # Group by batter, over, match to find max runs in an over
            batter_over = obo_df.groupby(['match_id', 'batter', 'over', 'team', 'year'], observed=True).agg(
                Runs=('runs.batter', 'sum'),
                Balls=('is_valid_delivery', 'sum')
            ).reset_index()
            
            # Top individual overs
            top_overs = batter_over.sort_values('Runs', ascending=False).head(50)
            top_overs = top_overs.rename(columns={'batter': 'Batter', 'over': 'Over', 'team': 'Team', 'year': 'Season'})
            top_overs['Over'] = top_overs['Over'] + 1  # Display 1-indexed overs
            
            st.dataframe(top_overs[['Batter', 'Team', 'Over', 'Runs', 'Balls', 'Season']].astype({'Batter': str, 'Team': str}), 
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
            bowler_over = obo_df.groupby(['match_id', 'bowler', 'over', 'bowling_team', 'year'], observed=True).agg(
                Runs_Conceded=('runs.total', 'sum'),
                Balls=('is_valid_delivery', 'sum'),
                Wickets=('wicket_count', 'sum')
            ).reset_index()
            
            # Top expensive overs
            expensive_overs = bowler_over.sort_values('Runs_Conceded', ascending=False).head(50)
            expensive_overs = expensive_overs.rename(columns={'bowler': 'Bowler', 'over': 'Over', 'bowling_team': 'Team', 'year': 'Season'})
            expensive_overs['Over'] = expensive_overs['Over'] + 1  # Display 1-indexed
            
            st.dataframe(expensive_overs[['Bowler', 'Team', 'Over', 'Runs_Conceded', 'Balls', 'Wickets', 'Season']].astype({'Bowler': str, 'Team': str}), 
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

# =========================================
# BATTER VS BOWLER MATCHUP
# =========================================
elif metric_choice == "Batter vs Bowler Matchup":
    st.subheader("⚔️ Batter vs Bowler Matchup")
    st.write("Head-to-head statistics between batters and bowlers")
    
    # Additional filters
    col1, col2 = st.columns(2)
    with col1:
        matchup_years = sorted(fdf['year'].dropna().unique())
        selected_matchup_year = st.selectbox("Filter by Year", ["All Years"] + list(matchup_years), key="matchup_year")
    with col2:
        min_balls = st.slider("Minimum Balls Faced", 1, 50, 6)
    
    # Apply year filter
    matchup_df = fdf.copy()
    if selected_matchup_year != "All Years":
        matchup_df = matchup_df[matchup_df['year'] == selected_matchup_year]
    
    # Exclude super overs
    matchup_df = matchup_df[matchup_df['innings'].isin([1, 2])]
    
    if matchup_df.empty:
        st.warning("No data for selected filters.")
    else:
        # Calculate matchup stats - count unique innings for matches
        matchup_stats = matchup_df.groupby(['batter', 'bowler', 'team', 'bowling_team'], observed=True).agg(
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
            # Convert to string to avoid categorical issues
            matchup_stats['Batter'] = matchup_stats['batter'].astype(str)
            matchup_stats['Bowler'] = matchup_stats['bowler'].astype(str)
            matchup_stats['Batting_Team'] = matchup_stats['team'].astype(str)
            matchup_stats['Bowling_Team'] = matchup_stats['bowling_team'].astype(str)
            
            tab1, tab2, tab3 = st.tabs(["🏏 Top Matchups (Batter Dominant)", "🎯 Top Matchups (Bowler Dominant)", "🔍 Search Matchup"])
            
            with tab1:
                st.markdown("### Batters who dominate specific bowlers")
                st.caption("Batters with most runs against a bowler without getting dismissed")
                
                # High runs, no dismissals
                batter_dominant = matchup_stats[matchup_stats['Dismissals'] == 0].sort_values('Runs', ascending=False).head(30)
                if batter_dominant.empty:
                    batter_dominant = matchup_stats.sort_values(['Runs', 'SR'], ascending=[False, False]).head(30)
                    st.caption("(Showing top run scorers as no never-out matchups found)")
                
                st.dataframe(batter_dominant[['Batter', 'Batting_Team', 'Bowler', 'Bowling_Team', 'Innings', 'Runs', 'Balls', 'SR', 'Dismissals', 'Avg']], 
                           use_container_width=True)
                
                if not batter_dominant.empty:
                    # Create matchup label
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
                
                # High dismissals, low avg
                bowler_dominant = matchup_stats[matchup_stats['Dismissals'] >= 2].sort_values(
                    ['Dismissals', 'Avg'], ascending=[False, True]
                ).head(30)
                
                if bowler_dominant.empty:
                    st.info("No bowler has dismissed the same batter 2+ times in filtered data.")
                else:
                    st.dataframe(bowler_dominant[['Bowler', 'Bowling_Team', 'Batter', 'Batting_Team', 'Innings', 'Dismissals', 'Runs', 'Balls', 'Avg']], 
                               use_container_width=True)
                    
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
                        st.dataframe(search_result[['Batter', 'Batting_Team', 'Bowler', 'Bowling_Team', 'Innings', 'Runs', 'Balls', 'SR', 'Dismissals', 'Avg']], 
                                   use_container_width=True)
                        
                        if len(search_result) > 1:
                            if search_batter:
                                # Show batter's record against all selected bowlers
                                fig = px.bar(search_result.sort_values('Runs', ascending=False).head(15), 
                                            x='Bowler', y='Runs', color='SR',
                                            color_continuous_scale='RdYlGn',
                                            title=f"{search_batter}'s Record Against Bowlers")
                                fig.update_xaxes(tickangle=45)
                                st.plotly_chart(fig, use_container_width=True)
                            elif search_bowler:
                                # Show bowler's record against all batters
                                fig = px.bar(search_result.sort_values('Dismissals', ascending=False).head(15), 
                                            x='Batter', y='Dismissals', color='Avg',
                                            color_continuous_scale='RdYlGn_r',
                                            title=f"{search_bowler}'s Record Against Batters")
                                fig.update_xaxes(tickangle=45)
                                st.plotly_chart(fig, use_container_width=True)

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
            wickets = phase_data['wicket_count'].sum()
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
                total_wkts = inn_data['wicket_count'].sum()
                
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
                        total_wickets = inn_data['wicket_count'].sum()
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


st.markdown("---")
st.markdown("*Data extracted from Cricsheet JSON files.*")