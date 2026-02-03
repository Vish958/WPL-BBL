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

@st.cache_data
def load_data(path=DATA_SOURCE):
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

df = load_data()
if df.empty:
    st.stop()

# Load and merge venue data
venue_map = load_venue_data()
if venue_map:
    df['venue'] = df['match_id'].astype(str).map(lambda x: venue_map.get(x, {}).get('venue', 'Unknown'))
    df['city'] = df['match_id'].astype(str).map(lambda x: venue_map.get(x, {}).get('city', 'Unknown'))

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
    
    mode_val = 'batting' if pp_mode == "Batting" else 'bowling'
    # For bowling mode, pass full df (without team filter) and let function filter by bowling_team
    if mode_val == 'bowling':
        # Get data before team filtering for bowling mode
        bowling_df = df.copy()
        if selected_leagues:
            bowling_df = bowling_df[bowling_df['league'].isin(selected_leagues)]
        if selected_years:
            bowling_df = bowling_df[bowling_df['year'].isin(selected_years)]
        match_stats, season_summary = powerplay_score_tracker(bowling_df, mode=mode_val, filter_teams=selected_teams if selected_teams else None)
    else:
        match_stats, season_summary = powerplay_score_tracker(fdf, mode=mode_val)
    
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
        tab1, tab2, tab3 = st.tabs(["📋 Match-by-Match", "📊 Season Summary", "🏟️ Venue-wise"])
        
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