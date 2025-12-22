import streamlit as st

# --- BEGIN AUTO-ADDED OPTIMIZATIONS ---
import logging, threading, time
from typing import TYPE_CHECKING
import gc 

# Optional psutil import
if TYPE_CHECKING:
    import psutil  # type: ignore
else:
    try:
        import importlib.util
        spec = importlib.util.find_spec("psutil")
        if spec is not None:
            import importlib
            psutil = importlib.import_module("psutil")
        else:
            psutil = None
    except Exception:
        psutil = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def _start_memory_monitor():
    if psutil is None:
        return
    def _mon():
        pproc = psutil.Process()
        while True:
            try:
                mem = pproc.memory_info().rss / (1024*1024)
                # logging.info(f"[mem-monitor] RSS_MB={mem:.1f}")
            except Exception:
                pass
            time.sleep(30)
    t = threading.Thread(target=_mon, daemon=True)
    t.start()

_start_memory_monitor()
# --- END AUTO-ADDED OPTIMIZATIONS ---

import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

# Cached CSV loader fallback
try:
    import streamlit as st
    @st.cache_data
    def load_csv(path, **kwargs):
        import pandas as pd
        return load_csv(path, **kwargs)
except Exception:
    pass

st.set_page_config(page_title="T20 Stats Dashboard", layout="wide")

st.markdown("""
**By Vishwesh Gaur** [Twitter: @iumvishwesh](https://twitter.com/iumvishwesh) | [LinkedIn: vishwesh-gaur-56760b112](https://www.linkedin.com/in/vishwesh-gaur-56760b112)  
""")

st.markdown("📅 Last updated: 2025-11-28")
st.markdown("⏰ Fresh Matches Will Appear as per Data Availability from Cricsheet")
st.markdown("🚀 **New:** Detailed Breakdown (0s, 1s, 4s, 6s), Impact Players & Score Prediction!")

st.markdown("""
<style>
/* Badge Styles */
.ai-badge, .otw-badge {
  display: inline-block;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-right: 10px;
  vertical-align: middle;
}
.ai-badge {
  background: linear-gradient(90deg,#0f172a,#042e1f);
  color: #9ef08a;
  border: 1px solid rgba(158,240,138,0.15);
  box-shadow: 0 0 0 rgba(158,240,138,0.35);
  animation: pulse-green 1s infinite;
}
.otw-badge {
  background: linear-gradient(90deg,#2b0a0a,#4c0b0b);
  color: #ffd6d6;
  border: 1px solid rgba(255,100,100,0.12);
  box-shadow: 0 0 0 rgba(255,100,100,0.22);
  animation: pulse-red 1s infinite;
}
@keyframes pulse-green {
  0% { box-shadow: 0 0 0 0 rgba(158,240,138,0.35); }
  70% { box-shadow: 0 0 0 12px rgba(158,240,138,0); }
  100% { box-shadow: 0 0 0 0 rgba(158,240,138,0); }
}
@keyframes pulse-red {
  0% { box-shadow: 0 0 0 0 rgba(255,100,100,0.28); transform: translateY(0px); }
  50% { box-shadow: 0 0 8px 4px rgba(255,100,100,0.06); transform: translateY(-1px); }
  100% { box-shadow: 0 0 0 0 rgba(255,100,100,0); transform: translateY(0px); }
}
.header-badges { margin-top: 6px; margin-bottom: 10px; }
</style>
<div class="header-badges">
  <div class="ai-badge">Powered by AI</div>
  <div class="otw-badge">Open to work</div>
</div>
""", unsafe_allow_html=True)

st.markdown("# Global T20 Dashboard: IPL, MBBL, WBBL, SA20 & WPL Insights")

DATA_SOURCE = "t20_data.parquet"

# League Start Dates (for reference)
LEAGUE_START_DATES = {
    'WBBL': '2020-10-25',
    'MBBL': '2020-12-10',
    'WPL':  '2023-03-04',
    'SA20': '2023-01-10',
    'IPL':  '2008-04-18'
}

st.markdown("**Data included from:**")
for lg, dt in LEAGUE_START_DATES.items():
    st.markdown(f"- **{lg}** from **{dt}**")

DEFAULT_COMPACT_HEIGHT = 250

@st.cache_data
def load_data(path=DATA_SOURCE):
    try:
        df = pd.read_parquet(path)
        
        # --- Memory Optimization ---
        # Normalize phases
        if 'phase' in df.columns:
            df['phase'] = df['phase'].astype(str).str.strip().apply(lambda x: x.title().replace('Power Play','Powerplay'))
            df['phase'] = df['phase'].replace({'Powersurge':'Power Surge','Power Surge':'Power Surge','Powerplay':'Powerplay'})
        
        # Convert object columns to categories
        cat_cols = ['league', 'season', 'phase', 'team', 'batter', 'bowler', 'non_striker', 'teams', 'venue', 'outcome', 'match_result', 'winner', 'match_id']
        for col in df.columns:
            if col in cat_cols or df[col].dtype == 'object':
                if df[col].nunique() < (len(df) * 0.5):
                    df[col] = df[col].astype('category')

        # Downcast numerics
        f_cols = df.select_dtypes(include=['float']).columns
        for c in f_cols:
            df[c] = pd.to_numeric(df[c], downcast='float')
        
        i_cols = df.select_dtypes(include=['integer']).columns
        for c in i_cols:
            df[c] = pd.to_numeric(df[c], downcast='integer')

        # Date conversion
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])

        # Ensure necessary columns exist (default to 0 if missing)
        for col in ['is_impact_batter', 'is_impact_bowler', 'no_balls', 'wides', 'leg_byes', 'byes']:
            if col not in df.columns:
                df[col] = 0

        return df
    except Exception as e:
        st.error(f"Data not found or failed to load: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

# Session State Initialization
if 'submitted' not in st.session_state: st.session_state.submitted = False
if 'compact_height' not in st.session_state: st.session_state.compact_height = DEFAULT_COMPACT_HEIGHT
if 'metrics' not in st.session_state: st.session_state.metrics = []
if 'matches' not in st.session_state: st.session_state.matches = []
if 'batters' not in st.session_state: st.session_state.batters = []
if 'bowlers' not in st.session_state: st.session_state.bowlers = []

def clear_submitted():
    st.session_state.submitted = False

# Sidebar UI
st.sidebar.header("UI")
st.session_state.compact_height = st.sidebar.slider("Table height (px)", min_value=150, max_value=800, value=st.session_state.compact_height)

st.sidebar.markdown("---")
st.sidebar.header("Filters")

# --- 1. Global Filters ---
leagues = sorted(df['league'].dropna().unique())
st.sidebar.multiselect("League", leagues, key="leagues", on_change=clear_submitted)

years = sorted(df['year'].dropna().unique())
st.sidebar.multiselect("Year", years, key="years", on_change=clear_submitted)

min_date, max_date = df['date'].dt.date.min(), df['date'].dt.date.max()
col1, col2 = st.sidebar.columns(2)
with col1:
    st.sidebar.date_input("From", key="date_from", value=df['date'].dt.date.min(), min_value=min_date, max_value=max_date, on_change=clear_submitted)
with col2:
    st.sidebar.date_input("To", key="date_to", value=df['date'].dt.date.max(), min_value=min_date, max_value=max_date, on_change=clear_submitted)

# --- 2. Phase Filter ---
# Pre-filter for Dropdown population
p_df = df.copy()
if st.session_state.get('leagues'): p_df = p_df[p_df['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): p_df = p_df[p_df['year'].isin(st.session_state['years'])]
if st.session_state.get('date_from'): p_df = p_df[p_df['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): p_df = p_df[p_df['date'].dt.date <= st.session_state['date_to']]

available_phases = sorted(p_df['phase'].dropna().unique())
if any(l in st.session_state.get('leagues', []) for l in ['WBBL', 'MBBL']):
    if 'Power Surge' not in available_phases:
        available_phases = list(available_phases) + ['Power Surge']
if not available_phases:
    available_phases = ['Powerplay','Power Surge','Middle','Death']

st.sidebar.multiselect("Phase", available_phases, key="phases", on_change=clear_submitted)

# --- 3. View Mode ---
st.sidebar.markdown("---")
view_mode = st.sidebar.radio(
    "Analysis Scope", 
    ["Specific Matches", "Overall (Season Leaderboard)"],
    key="view_mode_selection",
    help="Specific: Analyze specific matches.\nOverall: Aggregate stats across selected League/Year/Phase."
)

# --- 4. Selectors ---
if st.session_state.get('phases'):
    phases_norm = [p.title().replace('Power Play','Powerplay') for p in st.session_state['phases']]
    p_df = p_df[p_df['phase'].isin(phases_norm)]

# Match Selector
if 'teams' in p_df.columns and not p_df['teams'].dropna().empty:
    match_options = sorted(p_df['teams'].dropna().unique())
else:
    match_options = sorted(p_df['match_id'].dropna().unique())

st.session_state.matches = [m for m in st.session_state.matches if m in match_options]
st.sidebar.multiselect("Match", match_options, key="matches", on_change=clear_submitted)

# Batter Selector
batter_source = p_df.copy()
if st.session_state.get('matches'):
    batter_source = batter_source[batter_source['teams'].isin(st.session_state['matches'])]
if 'batter' in batter_source.columns:
    batter_options = sorted(batter_source['batter'].dropna().unique())
else:
    batter_options = []
st.session_state.batters = [b for b in st.session_state.batters if b in batter_options]
st.sidebar.multiselect("Batter", batter_options, key="batters", on_change=clear_submitted)

# Bowler Selector
bowler_source = p_df.copy()
if st.session_state.get('matches'):
    bowler_source = bowler_source[bowler_source['teams'].isin(st.session_state['matches'])]
if 'bowler' in bowler_source.columns:
    bowler_options = sorted(bowler_source['bowler'].dropna().unique())
else:
    bowler_options = []
st.session_state.bowlers = [b for b in st.session_state.bowlers if b in bowler_options]
st.sidebar.multiselect("Bowler", bowler_options, key="bowlers", on_change=clear_submitted)

# --- 5. Metrics ---
metrics = [
    "Key Batting", "Key Bowling", 
    "Score Prediction (Next Match)", "Impact Player Performance",
    "BPSix", "BP4", "Batter Contribution %",
    "Extras Breakdown", "Run Rate Progression", "Boundary Balls %",
    "Powerplay Boundary Rate", "Death Wag %", "Match-Up Dominance",
    "Pressure Index", "Dot Ball % Trend", "Bowler Boundary Leakage by Phase", "Match Results"
]
st.sidebar.markdown("---")
st.sidebar.multiselect("Metrics", metrics, key="metrics", on_change=clear_submitted)

st.sidebar.markdown("### Run Rate options")
rr_mode = st.sidebar.radio("Run Rate View", ['Per-over (combined)', 'Per match', 'Per-match multi-run'], index=0)
rr_run_source = st.sidebar.radio("Run Source for RR", ['Total runs (incl extras)','Batter runs only'], index=0)

selected_match_for_rr = None
if rr_mode in ('Per match','Per-match multi-run'):
    match_options_for_rr = sorted(p_df['teams'].dropna().unique())
    selected_match_for_rr = st.sidebar.selectbox("Select match for per-match RR", match_options_for_rr)

# --- 6. SUBMIT ---
if st.sidebar.button("SUBMIT", type="primary"):
    st.session_state.submitted = True
    st.success("Applied!")

if not st.session_state.submitted:
    st.info("Choose filters. Click SUBMIT to compute metrics.")
    st.stop()

# --- FILTERING ---
fdf = df.copy()

if st.session_state.get('leagues'): fdf = fdf[fdf['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): fdf = fdf[fdf['year'].isin(st.session_state['years'])]
if st.session_state.get('date_from'): fdf = fdf[fdf['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): fdf = fdf[fdf['date'].dt.date <= st.session_state['date_to']]
if st.session_state.get('phases'):
    phases_norm = [p.title().replace('Power Play','Powerplay') for p in st.session_state['phases']]
    fdf = fdf[fdf['phase'].isin(phases_norm)]

# View Mode Filtering
if view_mode == "Specific Matches":
    if st.session_state.get('matches'):
        fdf = fdf[fdf['teams'].isin(st.session_state['matches'])]
    if st.session_state.get('batters'):
        fdf = fdf[fdf['batter'].isin(st.session_state['batters'])]
    if st.session_state.get('bowlers'):
        fdf = fdf[fdf['bowler'].isin(st.session_state['bowlers'])]
else:
    st.info(f"Viewing Overall Stats (Leaderboard Mode). Ignoring specific match selections.")
    # Apply player filters if selected, to show specific player stats in overall view
    if st.session_state.get('batters'):
        fdf = fdf[fdf['batter'].isin(st.session_state['batters'])]
    if st.session_state.get('bowlers'):
        fdf = fdf[fdf['bowler'].isin(st.session_state['bowlers'])]

if fdf.empty:
    st.warning("No data for selected filters.")
    st.stop()

gc.collect()

# --- HELPER FUNCTIONS ---
def overs_from_balls(balls):
    o = balls // 6
    b = balls % 6
    return f"{int(o)}.{int(b)}"

def has_meaningful_numbers(df_):
    if df_ is None or df_.empty: return False
    numeric_cols = df_.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols: return len(df_) > 0
    return (df_[numeric_cols].abs().sum(axis=1) > 0).any()

def show_table(df_, title=None):
    if df_ is None or df_.empty:
        st.info("No data to show.")
        return
    if not has_meaningful_numbers(df_):
        st.info("No meaningful data.")
        return
    st.dataframe(df_, width='stretch', height=st.session_state.compact_height)

def show_bar(df_, x, y, title, color=None, top_n=None):
    if df_ is None or df_.empty:
        st.info("No data.")
        return
    if top_n:
        df_ = df_.head(top_n)
    if color:
        fig = px.bar(df_, x=x, y=y, title=title, color_discrete_sequence=[color])
    else:
        fig = px.bar(df_, x=x, y=y, title=title)
    st.plotly_chart(fig, width='stretch')

# -------------------------
# CORE METRICS (Detailed Breakdown)
# -------------------------

def key_batting(df_):
    valid = df_.copy()
    
    # Cast types for calculation safety
    for c in ['innings', 'runs.batter', 'is_valid_delivery', 'no_balls']:
        if c in valid.columns: valid[c] = valid[c].astype('int64')
    valid['batter'] = valid['batter'].astype(str)

    is_overall = (st.session_state.get('view_mode_selection') == "Overall (Season Leaderboard)")
    grp_cols = ['batter'] if is_overall else ['innings', 'batter']

    # --- Calculations ---
    # Balls Faced (BF) = Valid Deliveries + No Balls
    valid['balls_faced_count'] = valid['is_valid_delivery'] + valid['no_balls']
    
    grp = valid.groupby(grp_cols, observed=True)
    
    runs = grp['runs.batter'].sum().rename('Runs')
    balls = grp['balls_faced_count'].sum().rename('BF')
    
    # Detailed Scoring Shots
    zeros = valid[valid['runs.batter'] == 0].groupby(grp_cols, observed=True).size().rename('0s')
    ones = valid[valid['runs.batter'] == 1].groupby(grp_cols, observed=True).size().rename('1s')
    twos = valid[valid['runs.batter'] == 2].groupby(grp_cols, observed=True).size().rename('2s')
    threes = valid[valid['runs.batter'] == 3].groupby(grp_cols, observed=True).size().rename('3s')
    fours = valid[valid['runs.batter'] == 4].groupby(grp_cols, observed=True).size().rename('4s')
    fives = valid[valid['runs.batter'] == 5].groupby(grp_cols, observed=True).size().rename('5s')
    sixes = valid[valid['runs.batter'] == 6].groupby(grp_cols, observed=True).size().rename('6s')
    
    # Innings Played
    if is_overall:
        innings_played = valid.groupby(grp_cols, observed=True)['match_id'].nunique().rename('Inns')
    else:
        # For specific matches, create a column of 1s
        innings_played = valid.groupby(grp_cols, observed=True).apply(lambda x: 1).rename('Inns')

    stats = pd.concat([runs, balls, innings_played, zeros, ones, twos, threes, fours, fives, sixes], axis=1).fillna(0)
    
    # Derived Metrics
    stats['SR'] = (stats['Runs'] / stats['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    stats['Ave'] = (stats['Runs'] / stats['Inns']).replace([np.inf, np.nan], 0).round(2)
    
    stats = stats.reset_index()
    if is_overall:
        stats['Innings'] = "Overall"
    else:
        stats['Innings'] = stats['innings'].map({1:'Innings 1',2:'Innings 2'})
    
    # Reorder columns for display
    display_cols = ['Innings', 'batter', 'Inns', 'Runs', 'BF', 'Ave', 'SR', '0s', '1s', '2s', '3s', '4s', '6s']
    return stats[display_cols].sort_values('Runs', ascending=False)

def key_bowling(df_):
    g = df_.copy()
    
    # Cast types
    for c in ['runs.total', 'byes', 'leg_byes', 'wides', 'no_balls', 'is_valid_delivery', 'wicket_count']:
        if c in g.columns: g[c] = g[c].astype('int64')
    
    # Runs Conceded = Total - Byes - LegByes
    g['runs_to_bowler'] = g['runs.total'] - g['byes'] - g['leg_byes']
    g['extras_bowler'] = g['wides'] + g['no_balls']
    
    is_overall = (st.session_state.get('view_mode_selection') == "Overall (Season Leaderboard)")
    grp_cols = ['bowler'] if is_overall else ['innings', 'bowler']

    grp = g.groupby(grp_cols, observed=True)
    
    balls = grp['is_valid_delivery'].sum().rename('Balls')
    runs = grp['runs_to_bowler'].sum().rename('Conc') # Runs Conceded
    wkts = grp['wicket_count'].sum().rename('Wkt')
    extras = grp['extras_bowler'].sum().rename('Ex')
    
    # Innings
    if is_overall:
        inns = grp['match_id'].nunique().rename('Inns')
    else:
        inns = grp.apply(lambda x: 1).rename('Inns')

    # Detailed Breakdown (Score allowed per ball)
    zeros = g[g['runs_to_bowler'] == 0].groupby(grp_cols, observed=True).size().rename('0s')
    ones = g[g['runs_to_bowler'] == 1].groupby(grp_cols, observed=True).size().rename('1s')
    twos = g[g['runs_to_bowler'] == 2].groupby(grp_cols, observed=True).size().rename('2s')
    threes = g[g['runs_to_bowler'] == 3].groupby(grp_cols, observed=True).size().rename('3s')
    fours = g[g['runs_to_bowler'] == 4].groupby(grp_cols, observed=True).size().rename('4s')
    fives = g[g['runs_to_bowler'] == 5].groupby(grp_cols, observed=True).size().rename('5s')
    sixes = g[g['runs_to_bowler'] == 6].groupby(grp_cols, observed=True).size().rename('6s')

    stats = pd.concat([inns, balls, runs, wkts, extras, zeros, ones, twos, threes, fours, fives, sixes], axis=1).fillna(0)
    
    stats['Overs'] = stats['Balls'].apply(overs_from_balls)
    stats['Econ'] = (stats['Conc'] / (stats['Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
    stats['Ave'] = (stats['Conc'] / stats['Wkt']).replace([np.inf, np.nan], 0).round(2)
    stats['SR'] = (stats['Balls'] / stats['Wkt']).replace([np.inf, np.nan], 0).round(2)
    
    stats = stats.reset_index()
    if is_overall:
        stats['Innings'] = "Overall"
    else:
        stats['Innings'] = stats['innings'].map({1:'Innings 1',2:'Innings 2'})
        
    display_cols = ['Innings', 'bowler', 'Inns', 'Wkt', 'Conc', 'Balls', 'Overs', 'Econ', 'Ave', 'SR', 'Ex', '0s', '1s', '2s', '4s', '6s']
    return stats[display_cols].sort_values('Wkt', ascending=False)

# -------------------------
# NEW FEATURES
# -------------------------

# Impact Player Stats
def calculate_impact_player_stats(df):
    if 'is_impact_batter' not in df.columns:
        return pd.DataFrame(), pd.DataFrame()
    
    # Batting Impact
    impact_bat = df[df['is_impact_batter'] == 1].copy()
    if not impact_bat.empty:
        bat_stats = key_batting(impact_bat)
    else:
        bat_stats = pd.DataFrame()

    # Bowling Impact
    impact_bowl = df[df['is_impact_bowler'] == 1].copy()
    if not impact_bowl.empty:
        bowl_stats = key_bowling(impact_bowl)
    else:
        bowl_stats = pd.DataFrame()

    return bat_stats, bowl_stats

# Score Prediction
def predict_next_score(df, selected_batters):
    if not selected_batters: return pd.DataFrame()
    
    df['runs.batter'] = df['runs.batter'].astype('int64')
    df_bat = df[df['batter'].isin(selected_batters)].copy()
    
    innings_data = df_bat.groupby(['match_id', 'date', 'batter'], observed=True)['runs.batter'].sum().reset_index().sort_values('date')
    
    predictions = []
    for batter in selected_batters:
        b_data = innings_data[innings_data['batter'] == batter]
        if len(b_data) < 2:
            predictions.append({'Batter': batter, 'Last 5 Scores': str(b_data['runs.batter'].tolist()), 'Projected Score': "Insufficient Data", 'Form Trend': "N/A"})
            continue
            
        scores = b_data.tail(5)['runs.batter'].tolist()
        
        # Weighted Average Logic
        if len(scores) >= 5:
            weights = [0.10, 0.15, 0.20, 0.25, 0.30] 
            predicted_run = sum([s * w for s, w in zip(scores, weights)])
        else:
            predicted_run = sum(scores) / len(scores)
            
        recent_avg = sum(scores[-2:]) / 2 if len(scores) >= 2 else scores[0]
        old_avg = sum(scores[:2]) / 2
        trend = "📈 Rising" if recent_avg > old_avg else "📉 Dipping"
        
        predictions.append({
            'Batter': batter, 
            'Last 5 Scores': str(scores), 
            'Projected Score': int(round(predicted_run)), 
            'Form Trend': trend
        })
    return pd.DataFrame(predictions)

# -------------------------
# OTHER METRICS (Standard)
# -------------------------
def bpsix(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter', observed=True).size().rename('Balls')
    sixes = valid[valid['runs.batter'] == 6].groupby('batter', observed=True).size().rename('Sixes')
    s = pd.concat([balls, sixes], axis=1).fillna(0)
    s['BPSix'] = s.apply(lambda r: round(r['Balls'] / r['Sixes'], 2) if r['Sixes'] > 0 else 0, axis=1)
    s = s.reset_index().rename(columns={'index':'batter'})
    if len(st.session_state.get('matches', [])) == 1:
        s = s[s['Sixes'] > 0]
    return s[['batter','Balls','Sixes','BPSix']].sort_values('BPSix')

def bp4(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter', observed=True).size().rename('Balls')
    fours = valid[valid['runs.batter'] == 4].groupby('batter', observed=True).size().rename('Fours')
    s = pd.concat([balls, fours], axis=1).fillna(0)
    s['BP4'] = s.apply(lambda r: round(r['Balls'] / r['Fours'], 2) if r['Fours'] > 0 else 0, axis=1)
    s = s.reset_index().rename(columns={'index':'batter'})
    if len(st.session_state.get('matches', [])) == 1:
        s = s[s['Fours'] > 0]
    return s[['batter','Balls','Fours','BP4']].sort_values('BP4')

def boundary_balls_pct(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter', observed=True).size().rename('Balls')
    boundaries = valid[valid['runs.batter'].isin([4,6])].groupby('batter', observed=True).size().rename('Boundaries')
    s = pd.concat([balls, boundaries], axis=1).fillna(0)
    s['Boundary %'] = (s['Boundaries'] / s['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'index':'batter'})
    return s[['batter','Balls','Boundaries','Boundary %']].sort_values('Boundary %', ascending=False)

def pressure_index(df_):
    temp = df_.sort_values(['match_id','innings','over','ball_float']).copy()
    temp['cum_wickets'] = temp.groupby(['match_id','innings'], observed=True)['wicket_count'].cumsum()
    temp['pressure'] = temp['runs.total'] * (10 - temp['cum_wickets'])
    pressure_sum = temp.groupby('batter', observed=True)['pressure'].sum().rename('pressure_sum')
    balls = temp[temp['is_valid_delivery']==1].groupby('batter', observed=True).size().rename('BallsFaced')
    out = pd.concat([pressure_sum, balls], axis=1).fillna(0).reset_index()
    out['Pressure Index'] = out.apply(lambda r: round(r['pressure_sum'] / r['BallsFaced'], 2) if r['BallsFaced']>0 else 0, axis=1)
    return out[['batter','BallsFaced','Pressure Index']].sort_values('Pressure Index', ascending=False)

def powerplay_boundary_rate(df_):
    pp = df_[df_['phase'] == 'Powerplay']
    if pp.empty: return pd.DataFrame()
    balls = pp[pp['is_valid_delivery']==1].groupby('team', observed=True).size().rename('PP_Balls')
    boundaries = pp[pp['runs.batter'].isin([4,6])].groupby('team', observed=True).size().rename('PP_Boundaries')
    s = pd.concat([balls, boundaries], axis=1).fillna(0)
    s['PPBR (%)'] = (s['PP_Boundaries'] / s['PP_Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'team':'Team'})
    return s[['Team','PP_Boundaries','PP_Balls','PPBR (%)']].sort_values('PPBR (%)', ascending=False)

def death_wag_pct(df_):
    death = df_[df_['phase'] == 'Death'].copy()
    if death.empty: return pd.DataFrame()
    # Create batting_positions from the dataframe itself
    batting_positions = df_.groupby(['match_id', 'innings', 'batter'], observed=True).apply(lambda x: x.name).reset_index(drop=True)
    batting_positions = df_.groupby(['match_id', 'innings'], observed=True).apply(lambda x: pd.Series({'batter': x['batter'].values, 'position': range(1, len(x) + 1)})).reset_index(drop=True)
    # Simpler approach: rank batters by order of appearance
    batting_positions = df_.sort_values(['match_id', 'innings', 'ball_float']).groupby(['match_id', 'innings']).cumcount().add(1)
    batting_positions = df_.assign(position=batting_positions)[['match_id', 'innings', 'batter', 'position']].drop_duplicates(subset=['match_id', 'innings', 'batter'], keep='first')
    pos = batting_positions.copy()
    
    death['match_id'] = death['match_id'].astype(str)
    pos['match_id'] = pos['match_id'].astype(str)
    death['innings'] = death['innings'].astype('int64')
    pos['innings'] = pos['innings'].astype('int64')
    death['batter'] = death['batter'].astype(str)
    pos['batter'] = pos['batter'].astype(str)

    merged = death.merge(pos, on=['match_id','innings','batter'], how='left')
    merged['position'] = merged['position'].fillna(99).astype(int)
    
    group_col = 'teams' if 'teams' in merged.columns else 'team'
    tot = merged.groupby(group_col, observed=True)['runs.total'].sum().rename('DeathRuns')
    pos7 = merged[merged['position'].between(7,11)].groupby(group_col, observed=True)['runs.total'].sum().rename('Pos7-11Runs')
    out = pd.concat([tot,pos7], axis=1).fillna(0).reset_index().rename(columns={group_col:'Teams'})
    out['Death Wag %'] = (out['Pos7-11Runs'] / out['DeathRuns'] * 100).replace([np.inf, np.nan], 0).round(2)
    return out[['Teams','DeathRuns','Pos7-11Runs','Death Wag %']].sort_values('Death Wag %', ascending=False)

def match_up_dominance(df_):
    valid = df_[df_['is_valid_delivery']==1]
    season = valid.groupby('batter', observed=True).agg({'runs.batter':'sum','is_valid_delivery':'sum'}).reset_index()
    season['SeasonSR'] = (season['runs.batter'] / season['is_valid_delivery'] * 100).replace([np.inf, np.nan], 0)
    vs = valid.groupby(['batter','bowler'], observed=True).agg({'runs.batter':'sum','is_valid_delivery':'sum'}).reset_index()
    vs['SR_vs_bowler'] = (vs['runs.batter'] / vs['is_valid_delivery'] * 100).replace([np.inf, np.nan], 0)
    out = vs.merge(season[['batter','SeasonSR']], on='batter', how='left')
    out['MDS'] = (out['SR_vs_bowler'] - out['SeasonSR']).round(2)
    return out.sort_values('MDS', ascending=False)

def dot_ball_pct_trend(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter', observed=True).size().rename('Balls')
    dots = valid[valid['runs.batter'] == 0].groupby('batter', observed=True).size().rename('Dots')
    s = pd.concat([balls, dots], axis=1).fillna(0)
    s['Dot %'] = (s['Dots'] / s['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'index':'batter'})
    return s[['batter','Balls','Dots','Dot %']].sort_values('Dot %', ascending=False)

def bowler_boundary_leakage_by_phase(df_):
    out_rows = []
    df_['phase'] = df_['phase'].astype(str)
    for (phase, inn, bowler), g in df_.groupby(['phase','innings','bowler'], observed=True):
        total_runs = g['runs.total'].sum()
        boundaries = g[g['runs.batter'].isin([4,6])]['runs.batter'].count()
        pct = (boundaries / total_runs * 100) if total_runs > 0 else 0
        out_rows.append({'phase': phase, 'Innings': f"Innings {inn}", 'Bowler': bowler, 'Boundaries Conceded': boundaries, 'Phase Runs': total_runs, 'Leakage %': round(pct,2)})
    if not out_rows: return pd.DataFrame()
    return pd.DataFrame(out_rows).sort_values(['phase','Leakage %'], ascending=[True,False])

def extras_breakdown(df_):
    if df_.empty: return pd.DataFrame()
    extras_cols = ['wides', 'no_balls', 'byes', 'leg_byes']
    extras_data = {}
    for col in extras_cols:
        if col in df_.columns:
            extras_data[col.replace('_', ' ').title()] = df_[col].sum()
        else:
            extras_data[col.replace('_', ' ').title()] = 0
    
    total_extras = sum(extras_data.values())
    if total_extras == 0:
        return pd.DataFrame()
    
    result = []
    for extra_type, count in extras_data.items():
        pct = (count / total_extras * 100) if total_extras > 0 else 0
        result.append({'Type': extra_type, 'Count': int(count), '%': round(pct, 2)})
    
    return pd.DataFrame(result).sort_values('%', ascending=False)

def batter_contribution(df_):
    innings_total = df_.groupby(['match_id','innings'], observed=True)['runs.batter'].sum().rename('InningsRuns').reset_index()
    batter_runs = df_.groupby(['match_id','innings','batter'], observed=True)['runs.batter'].sum().rename('Runs').reset_index()
    merged = batter_runs.merge(innings_total, on=['match_id','innings'], how='left')
    merged['Contribution %'] = (merged['Runs'] / merged['InningsRuns'] * 100).replace([np.inf, np.nan], 0).round(2)
    merged['Innings'] = merged['innings'].map({1:'Innings 1',2:'Innings 2'})
    agg = merged.groupby(['Innings','batter'], observed=True).agg({'Runs':'sum','InningsRuns':'sum','Contribution %':'mean'}).reset_index()
    agg['Contribution %'] = agg['Contribution %'].round(2)
    return agg[['Innings','batter','Runs','InningsRuns','Contribution %']].sort_values('Contribution %', ascending=False)

def match_results(df_):
    out_rows = []
    def find_winner_from_columns(g):
        if 'match_result' in g.columns and pd.notna(g['match_result'].iloc[0]) and str(g['match_result'].iloc[0]).strip():
            return str(g['match_result'].iloc[0]).strip()
        if 'outcome' in g.columns:
            v = g['outcome'].iloc[0]
            if pd.notna(v) and str(v).strip(): return str(v).strip()
        for c in g.columns:
            if 'winner' in c.lower() or 'outcome' in c.lower():
                v = g[c].iloc[0]
                if pd.notna(v) and str(v).strip(): return str(v).strip()
        return None

    for mid, g in df_.groupby('match_id', observed=True):
        if g.empty: continue
        teams = g['teams'].iloc[0] if 'teams' in g.columns else mid
        date_val = None
        if 'date' in g.columns and pd.notna(g['date'].iloc[0]):
            try:
                date_val = pd.to_datetime(g['date'].iloc[0]).date()
            except Exception:
                date_val = g['date'].iloc[0]

        explicit = find_winner_from_columns(g)
        if explicit:
            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': explicit})
            continue

        innings_present = sorted(g['innings'].dropna().unique())
        if not (1 in innings_present and 2 in innings_present):
            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': "No result / unavailable"})
            continue

        try:
            innings_totals = g.groupby('innings', observed=True)['runs.total'].sum().to_dict()
            innings_wickets = g.groupby('innings', observed=True)['wicket_count'].sum().to_dict()
            t1 = float(innings_totals.get(1, 0))
            t2 = float(innings_totals.get(2, 0))
            w2 = int(innings_wickets.get(2, 0))
            team2_arr = g[g['innings'] == 2]['team'].dropna().unique()
            name1 = g[g['innings'] == 1]['team'].dropna().unique()[0] if len(g[g['innings'] == 1]['team'].dropna().unique()) > 0 else 'Innings 1'
            name2 = team2_arr[0] if len(team2_arr) > 0 else 'Innings 2'

            if abs(t1 - t2) < 1e-9: res = "Tie"
            elif t1 > t2:
                margin = int(round(t1 - t2))
                res = f"{name1} won by {margin} runs"
            else:
                wickets_remaining = max(0, 10 - max(0, w2))
                if wickets_remaining == 0:
                    margin = int(round(t2 - t1))
                    res = f"{name2} won by {margin} runs"
                else:
                    res = f"{name2} won by {wickets_remaining} wickets"
            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': res})
        except Exception as e:
            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': f"Result unavailable (err: {e})"})

    if not out_rows: return pd.DataFrame(columns=['Match','Date','Result'])
    out = pd.DataFrame(out_rows)
    if 'Date' in out.columns and pd.api.types.is_datetime64_any_dtype(out['Date']):
        out = out.sort_values('Date', ascending=False)
        out['Date'] = out['Date'].dt.date
    else:
        try:
            out['Date'] = pd.to_datetime(out['Date'], errors='coerce')
            out = out.sort_values('Date', ascending=False)
            out['Date'] = out['Date'].dt.date
        except Exception:
            pass
    return out[['Match','Date','Result']]

def run_rate_combined_per_over(df_):
    if df_.empty: return pd.DataFrame()
    run_source = df_['runs.batter'] if rr_run_source == 'Batter runs only' else df_['runs.total']
    df_rr = df_.groupby(['innings', 'over'], observed=True)[run_source].sum().reset_index()
    df_rr.columns = ['Innings', 'Over', 'Runs']
    df_rr['RR'] = df_rr['Runs']
    df_rr['Innings'] = df_rr['Innings'].map({1:'Innings 1', 2:'Innings 2'})
    return df_rr[['Innings', 'Over', 'RR']].sort_values('Over')

def run_rate_per_match(df_, match_id):
    if df_.empty: return pd.DataFrame()
    df_match = df_[df_['match_id'] == match_id]
    run_source = df_match['runs.batter'] if rr_run_source == 'Batter runs only' else df_match['runs.total']
    df_rr = df_match.groupby(['innings', 'over'], observed=True)[run_source].sum().reset_index()
    df_rr.columns = ['Innings', 'Over', 'Runs']
    df_rr['RR'] = df_rr['Runs']
    df_rr['Innings'] = df_rr['Innings'].map({1:'Innings 1', 2:'Innings 2'})
    return df_rr[['Innings', 'Over', 'RR']].sort_values('Over')

def run_rate_multi_match_side_by_side(df_, match_id):
    if df_.empty: return pd.DataFrame()
    df_match = df_[df_['match_id'] == match_id]
    run_source = df_match['runs.batter'] if rr_run_source == 'Batter runs only' else df_match['runs.total']
    df_rr = df_match.groupby(['innings', 'over'], observed=True)[run_source].sum().reset_index()
    df_rr.columns = ['Innings', 'Over', 'Runs']
    df_rr['RR'] = df_rr['Runs']
    df_rr['Innings'] = df_rr['Innings'].map({1:'Innings 1', 2:'Innings 2'})
    return df_rr[['Innings', 'Over', 'RR']].sort_values('Over')

# Colors
color_pool = px.colors.qualitative.Plotly + px.colors.qualitative.D3 + px.colors.qualitative.Set3

# Iterate metrics and display
for i, metric in enumerate(st.session_state['metrics']):
    color = color_pool[i % len(color_pool)]
    try:
        
        if metric == "Key Batting":
            st.subheader("Key Batting (Detailed)")
            dfm = key_batting(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'batter', 'Runs', "Top Run Scorers", color=color)
            
        elif metric == "Key Bowling":
            st.subheader("Key Bowling (Detailed)")
            dfm = key_bowling(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'bowler', 'Wkt', "Top Wicket Takers", color=color)
            
        elif metric == "Impact Player Performance":
            st.subheader("⚡ Impact Player Performance")
            if 'IPL' not in st.session_state.get('leagues', []) and 'IPL' not in fdf['league'].unique():
                st.info("Impact Players are primarily an IPL feature. Select IPL to view data.")
            else:
                res_bat, res_bowl = calculate_impact_player_stats(fdf)
                t1, t2 = st.tabs(["Batting", "Bowling"])
                with t1:
                    if not res_bat.empty:
                        show_table(res_bat)
                        fig = px.bar(res_bat.head(10), x='batter', y='Runs', title="Top Impact Batsmen", color='Strike Rate')
                        st.plotly_chart(fig, width='stretch')
                    else:
                        st.info("No Impact Batters found.")
                with t2:
                    if not res_bowl.empty:
                        show_table(res_bowl)
                        fig = px.bar(res_bowl.head(10), x='bowler', y='Wkt', title="Top Impact Bowlers", color='Econ')
                        st.plotly_chart(fig, width='stretch')
                    else:
                        st.info("No Impact Bowlers found.")

        elif metric == "Score Prediction (Next Match)":
            st.subheader("Score Prediction")
            dfm = predict_next_score(fdf, st.session_state.batters)
            show_table(dfm)
            if not dfm.empty:
                trend_data = fdf[fdf['batter'].isin(st.session_state.batters)].groupby(['date', 'batter'], observed=True)['runs.batter'].sum().reset_index()
                fig = px.line(trend_data, x='date', y='runs.batter', color='batter', markers=True, title="Recent Form Trend")
                st.plotly_chart(fig, width='stretch')

        elif metric == "Extras Breakdown":
            st.subheader("Extras Breakdown")
            dfm = extras_breakdown(fdf)
            show_table(dfm)
            show_bar(dfm, 'Type', '%', "Extras %", color=color)

        elif metric == "BPSix":
            st.subheader("Balls Per Six")
            dfm = bpsix(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'batter', 'BPSix', "Balls Per Six (Lower is Better)", color=color)

        elif metric == "BP4":
            st.subheader("Balls Per Four")
            dfm = bp4(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'batter', 'BP4', "Balls Per Four (Lower is Better)", color=color)

        elif metric == "Boundary Balls %":
            st.subheader("Boundary Balls %")
            dfm = boundary_balls_pct(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'batter', 'Boundary %', "Boundary %", color=color)

        elif metric == "Powerplay Boundary Rate":
            st.subheader("Powerplay Boundary Rate")
            dfm = powerplay_boundary_rate(fdf)
            show_table(dfm)
            show_bar(dfm, 'Team', 'PPBR (%)', "Powerplay Boundary Rate", color=color)

        elif metric == "Death Wag %":
            st.subheader("Death Wag %")
            dfm = death_wag_pct(fdf)
            show_table(dfm)
            # Simple bar if cols exist
            if 'DeathRuns' in dfm.columns:
                show_bar(dfm, 'Team', 'DeathRuns', "Death Overs Runs", color=color)

        elif metric == "Match-Up Dominance":
            st.subheader("Match-Up Dominance")
            dfm = match_up_dominance(fdf)
            show_table(dfm.head(100))
            show_bar(dfm.head(20), 'batter', 'MDS', "Match-Up Dominance Score", color=color)

        elif metric == "Pressure Index":
            st.subheader("Pressure Index")
            dfm = pressure_index(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'batter', 'Pressure Index', "Pressure Index", color=color)

        elif metric == "Dot Ball % Trend":
            st.subheader("Dot Ball % Trend")
            dfm = dot_ball_pct_trend(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'batter', 'Dot %', "Dot %", color=color)

        elif metric == "Bowler Boundary Leakage by Phase":
            st.subheader("Bowler Boundary Leakage by Phase")
            dfm = bowler_boundary_leakage_by_phase(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'Bowler', 'Leakage %', "Boundary Leakage %", color=color)

        elif metric == "Batter Contribution %":
            st.subheader("Batter Contribution %")
            dfm = batter_contribution(fdf)
            show_table(dfm)
            show_bar(dfm.head(20), 'batter', 'Contribution %', "Batter Contribution %", color=color)

        elif metric == "Match Results":
            st.subheader("Match Results")
            dfm = match_results(fdf)
            show_table(dfm)

        elif metric == "Run Rate Progression":
            st.subheader("Run Rate Progression")
            if rr_mode == 'Per-over (combined)':
                dfm = run_rate_combined_per_over(fdf)
                show_table(dfm)
                if not dfm.empty:
                    fig = px.line(dfm, x='Over', y='RR', color='Innings', title="Run Rate Progression")
                    st.plotly_chart(fig, width='stretch')
            elif rr_mode == 'Per match':
                if selected_match_for_rr:
                    mids = fdf[fdf['teams'] == selected_match_for_rr]['match_id'].unique()
                    if len(mids) > 0:
                        dfm = run_rate_per_match(fdf, mids[0])
                        show_table(dfm)
                        if not dfm.empty:
                            fig = px.line(dfm, x='Over', y='RR', color='Innings', title=f"Run Rate: {selected_match_for_rr}")
                            st.plotly_chart(fig, width='stretch')
                else:
                    st.info("Select a match for Run Rate view.")
            else:
                if selected_match_for_rr:
                    mids = fdf[fdf['teams'] == selected_match_for_rr]['match_id'].unique()
                    if len(mids) > 0:
                        dfm = run_rate_multi_match_side_by_side(fdf, mids[0])
                        show_table(dfm)
                else:
                    st.info("Select a match.")

    except Exception as e:
        st.error(f"Error computing {metric}: {e}")