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
st.markdown("📅 Last updated: 2026-01-19")

DATA_SOURCE = "t20_data_with_drs.parquet"  # Updated to include DRS data

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
metric_choice = st.sidebar.radio("Select Metric", ["Powerplay Score Tracker", "DRS Analysis"])

if fdf.empty:
    st.warning("No data for selected filters.")
    st.stop()

# =========================================
# POWERPLAY SCORE TRACKER
# =========================================
def powerplay_score_tracker(df_, mode='batting'):
    """
    Track powerplay scores for each inning/team across matches.
    mode: 'batting' - when team is batting in powerplay
          'bowling' - when team is bowling in powerplay
    """
    pp = df_[df_['phase'] == 'Powerplay'].copy()
    if pp.empty:
        return pd.DataFrame(), pd.DataFrame()
    
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
        
    else:  # bowling mode
        grp = pp.groupby(['match_id', 'team', 'innings', 'date', 'year', 'teams'], observed=True)
        
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
        
        def get_bowling_team(row):
            teams_str = str(row['teams'])
            batting_team = str(row['team'])
            parts = teams_str.replace(' vs ', ' v ').split(' v ')
            if len(parts) == 2:
                return parts[1].strip() if parts[0].strip() == batting_team else parts[0].strip()
            return 'N/A'
        
        stats['Bowling_Team'] = stats.apply(get_bowling_team, axis=1)
        stats['Against'] = stats['team']
        stats['Date'] = pd.to_datetime(stats['date']).dt.date
        stats['Innings'] = stats['innings'].map({1: '1st', 2: '2nd'})
        
        match_stats = stats[['Bowling_Team', 'Against', 'Date', 'year', 'Innings', 'PP_Runs_Conceded', 
                             'PP_Balls_Bowled', 'PP_Econ', 'PP_Boundaries_Conceded', 'PP_Dot%', 
                             'PP_Wickets_Taken', 'match_id']].copy()
        match_stats = match_stats.rename(columns={'Bowling_Team': 'Team', 'year': 'Season'})
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
    Count reviews lost (failed) by team.
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
        tab1, tab2 = st.tabs(["📋 Match-by-Match", "📊 Season Summary"])
        
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
            ["Team Success Rate", "Match-by-Match", "Umpire Analysis", "Player Analysis", "Against Player"], 
            horizontal=True
        )
        
        # Get all reviews
        reviews = fdf[fdf['has_review'] == 1].copy()
        
        if reviews.empty:
            st.info("No DRS reviews found for selected filters.")
        else:
            st.write(f"**Total Reviews Found: {len(reviews)}**")
            
            # =====================
            # 1. TEAM SUCCESS RATE
            # =====================
            if drs_metric == "Team Success Rate":
                st.write("Success rate of DRS reviews by team (% of reviews that overturned umpire's decision)")
                
                stats = reviews.groupby(['review_by_team', 'year'], observed=True).agg(
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
                            barmode='group', title="DRS Success Rate by Team (%)")
                st.plotly_chart(fig, use_container_width=True)
            
            # =====================
            # 2. MATCH-BY-MATCH DRS
            # =====================
            elif drs_metric == "Match-by-Match":
                st.write("All DRS reviews broken down match-by-match")
                
                # Add date from main dataframe
                date_map = fdf.groupby('match_id')['date'].first().to_dict()
                reviews['Date'] = reviews['match_id'].map(date_map)
                reviews['Date'] = pd.to_datetime(reviews['Date']).dt.date
                
                match_drs = reviews.groupby(['match_id', 'teams', 'Date', 'year'], observed=True).agg(
                    Total_Reviews=('has_review', 'count'),
                    Successful=('review_decision', lambda x: (x == 'struck down').sum()),
                    Failed=('review_decision', lambda x: (x == 'upheld').sum()),
                    Teams_Reviewed=('review_by_team', lambda x: ', '.join(x.dropna().unique()))
                ).reset_index()
                
                match_drs = match_drs.rename(columns={'teams': 'Match', 'year': 'Season'})
                match_drs = match_drs.sort_values('Date', ascending=False)
                
                st.dataframe(match_drs[['Match', 'Date', 'Season', 'Total_Reviews', 'Successful', 'Failed', 'Teams_Reviewed']], use_container_width=True)
                
                # Bar chart of reviews per match
                fig = px.bar(match_drs.head(20), x='Match', y='Total_Reviews', color='Successful',
                            title="DRS Reviews per Match (Top 20 by Date)")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)
            
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
                    Failed=('review_decision', lambda x: (x == 'upheld').sum())
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

st.markdown("---")
st.markdown("*DRS data extracted from Cricsheet JSON files.*")

