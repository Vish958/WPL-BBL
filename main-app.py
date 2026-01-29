# app.py (full file) - Final: Impact Player Batting & Bowling Support
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
        logging.info("psutil not available; memory monitor disabled.")
        return
    def _mon():
        pproc = psutil.Process()
        while True:
            try:
                mem = pproc.memory_info().rss / (1024*1024)
                logging.info(f"[mem-monitor] RSS_MB={mem:.1f}")
            except Exception:
                logging.exception("Memory monitor error")
            time.sleep(30)
    t = threading.Thread(target=_mon, daemon=True)
    t.start()

_start_memory_monitor()
# --- END AUTO-ADDED OPTIMIZATIONS ---

# Cached CSV loader fallback
try:
    import streamlit as st
    @st.cache_data
    def load_csv(path, **kwargs):
        import pandas as pd
        return load_csv(path, **kwargs)
except Exception:
    _csv_cache = {}
    def load_csv(path, **kwargs):
        import pandas as pd
        key = (path, tuple(sorted(kwargs.items())))
        if key not in _csv_cache:
            _csv_cache[key] = load_csv(path, **kwargs)
        return _csv_cache[key]

import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

st.set_page_config(page_title="T20 Stats", layout="wide")

st.markdown("""
**By Vishwesh Gaur** [Twitter: @iumvishwesh](https://twitter.com/iumvishwesh) | [LinkedIn: vishwesh-gaur-56760b112](https://www.linkedin.com/in/vishwesh-gaur-56760b112)  
""")

st.markdown("📅 Last updated: 29 Jan 2026")
st.markdown("⏰ Fresh Matches Will Appear as per Data Availability from Cricsheet")
st.markdown("🚀 New: 'Impact Player' (Batting & Bowling for IPL) & 'Score Prediction'!")
st.markdown("🚀 New: 'Season Comparison'(Tabs) for Batting & Bowling!")

st.markdown("""
<style>
/* common badge style */
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
.badge-caption { display:inline-block; margin-left:8px; color:#94a3b8; font-size:12px; vertical-align: middle; }
</style>

<div class="header-badges">
  <div class="ai-badge">Powered by AI</div>
  <div class="otw-badge">Open to work</div>
  <span class="badge-caption"></span>
</div>
""", unsafe_allow_html=True)

st.markdown("# Global T20 Dashboard: IPL, MBBL, WBBL, SA20 & WPL Insights")

DATA_SOURCE = "t20_data.parquet"

# show league start dates (informational)
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

# default compact height; slider in sidebar allows user to change
DEFAULT_COMPACT_HEIGHT = 250

@st.cache_data
def load_data(path=DATA_SOURCE):
    try:
        # Load data
        df = pd.read_parquet(path)

        # --- FIX: Season Adjustment immediately after load (before optimization) ---
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        if 'league' in df.columns and 'date' in df.columns and 'year' in df.columns:
            # SA20: If Month >= 10, shift to next year (e.g. Dec 2025 -> 2026)
            mask_sa20 = (df['league'] == 'SA20') & (df['date'].dt.month >= 10)
            df.loc[mask_sa20, 'year'] = df.loc[mask_sa20, 'year'] + 1
            
            # BBL (MBBL/WBBL): If Month <= 4, shift to prev year (e.g. Jan 2021 -> 2020)
            mask_bbl = (df['league'].isin(['MBBL', 'WBBL'])) & (df['date'].dt.month <= 4)
            df.loc[mask_bbl, 'year'] = df.loc[mask_bbl, 'year'] - 1
            
            # --- FIX: Format Season Display (YYYY/YY) ---
            # Convert year to string to support "2025/26" format
            df['year'] = df['year'].astype(str)
            
            # SA20: Year is End Year (2026). Display as "2025/26"
            mask_sa20_all = df['league'] == 'SA20'
            if mask_sa20_all.any():
                y_sa20 = pd.to_numeric(df.loc[mask_sa20_all, 'year'])
                df.loc[mask_sa20_all, 'year'] = (y_sa20 - 1).astype(str) + "/" + y_sa20.astype(str).str[-2:]
                
            # BBL: Year is Start Year (2020). Display as "2020/21"
            mask_bbl_all = df['league'].isin(['MBBL', 'WBBL'])
            if mask_bbl_all.any():
                y_bbl = pd.to_numeric(df.loc[mask_bbl_all, 'year'])
                df.loc[mask_bbl_all, 'year'] = y_bbl.astype(str) + "/" + (y_bbl + 1).astype(str).str[-2:]
        
        # --- Memory Optimization ---
        if 'phase' in df.columns:
            df['phase'] = df['phase'].astype(str).str.strip().apply(lambda x: x.title().replace('Power Play','Powerplay'))
            df['phase'] = df['phase'].replace({'Powersurge':'Power Surge','Power Surge':'Power Surge','Powerplay':'Powerplay'})
        
        cat_cols = ['league', 'year', 'phase', 'team', 'batter', 'bowler', 'non_striker', 'teams', 'venue', 'outcome', 'match_result', 'winner', 'match_id']
        for col in df.columns:
            if col in cat_cols or df[col].dtype == 'object':
                if df[col].nunique() < (len(df) * 0.5):
                    df[col] = df[col].astype('category')

        f_cols = df.select_dtypes(include=['float']).columns
        for c in f_cols:
            df[c] = pd.to_numeric(df[c], downcast='float')
        
        i_cols = df.select_dtypes(include=['integer']).columns
        for c in i_cols:
            df[c] = pd.to_numeric(df[c], downcast='integer')

        # Ensure is_impact columns exist
        if 'is_impact_batter' not in df.columns: df['is_impact_batter'] = 0
        if 'is_impact_bowler' not in df.columns: df['is_impact_bowler'] = 0

        return df
    except Exception as e:
        st.error(f"Data not found or failed to load: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

if 'submitted' not in st.session_state: st.session_state.submitted = False
if 'compact_height' not in st.session_state: st.session_state.compact_height = DEFAULT_COMPACT_HEIGHT
if 'metrics' not in st.session_state: st.session_state.metrics = []

# initialize keys
if 'matches' not in st.session_state: st.session_state.matches = []
if 'batters' not in st.session_state: st.session_state.batters = []
if 'bowlers' not in st.session_state: st.session_state.bowlers = []

def clear_submitted():
    st.session_state.submitted = False

# Sidebar
st.sidebar.header("UI")
st.session_state.compact_height = st.sidebar.slider("Table height (px)", min_value=150, max_value=800, value=st.session_state.compact_height)

st.sidebar.markdown("---")
st.sidebar.header("Filters")

# --- 1. Global Filters ---
leagues = sorted(df['league'].dropna().unique())
st.sidebar.multiselect("League", leagues, key="leagues", on_change=clear_submitted)

years = sorted(df['year'].dropna().unique())
st.sidebar.multiselect("Year", years, key="years", on_change=clear_submitted)

# --- Season Aggregation Options ---
st.sidebar.markdown("##### Season View Options")
season_view_mode = st.sidebar.selectbox(
    "Season Display Mode",
    ["Normal (Per Season)", "Season Comparison (Tabs)"],
    key="season_view_mode",
    help="Normal: Show data per season. Tabs: Compare seasons side-by-side with aggregated totals."
)

min_date, max_date = df['date'].dt.date.min(), df['date'].dt.date.max()
col1, col2 = st.sidebar.columns(2)
with col1:
    st.sidebar.date_input("From", key="date_from", value=df['date'].dt.date.min(), min_value=min_date, max_value=max_date, on_change=clear_submitted)
with col2:
    st.sidebar.date_input("To", key="date_to", value=df['date'].dt.date.max(), min_value=min_date, max_value=max_date, on_change=clear_submitted)

# --- 2. Phase Filter ---
# Pre-filter for Phase/Dropdowns
p_df = df.copy()
if st.session_state.get('leagues'): p_df = p_df[p_df['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): p_df = p_df[p_df['year'].isin(st.session_state['years'])]
# Fix: Apply date filter to dropdowns
if st.session_state.get('date_from'): p_df = p_df[p_df['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): p_df = p_df[p_df['date'].dt.date <= st.session_state['date_to']]

available_phases = sorted(p_df['phase'].dropna().unique())
if any(l in st.session_state.get('leagues', []) for l in ['WBBL', 'MBBL']):
    if 'Power Surge' not in available_phases:
        available_phases = list(available_phases) + ['Power Surge']
if not available_phases:
    available_phases = ['Powerplay','Power Surge','Middle','Death']

st.sidebar.multiselect("Phase", available_phases, key="phases", on_change=clear_submitted)

with st.sidebar.expander("ℹ️ Phase Definitions", expanded=False):
    st.markdown("""
    **General (IPL, WPL, SA20)**
    - **Powerplay**: Overs 1-6
    - **Middle**: Overs 7-16
    - **Death**: Overs 17-20
    
    **BBL (MBBL, WBBL)**
    - **Powerplay**: Overs 1-4
    - **Middle**: Overs 5-16 (excl. Surge)
    - **Death**: Overs 17-20
    """)

# --- 3. View Mode ---
st.sidebar.markdown("---")
view_mode = st.sidebar.radio(
    "Analysis Scope", 
    ["Specific Matches", "Overall (Season Leaderboard)"],
    key="view_mode_selection",
    help="Specific: Analyze selected matches only.\nOverall: Analyze all matches in the selected League/Year/Phase."
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
    "Impact Player Performance", # NEW METRIC
    "Score Prediction (Next Match)",
    "Key Batting", "Key Bowling", "BPSix", "BP4", "Batter Contribution %",
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

# --- 6. Submit ---
if st.sidebar.button("SUBMIT", type="primary"):
    st.session_state.submitted = True
    st.success("Applied!")

if not st.session_state.submitted:
    st.info("Choose filters. Click SUBMIT to compute metrics.")
    st.stop()

# --- FILTERING ---
fdf = df.copy()

# A. Base Filters
if st.session_state.get('leagues'): fdf = fdf[fdf['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): fdf = fdf[fdf['year'].isin(st.session_state['years'])]
if st.session_state.get('date_from'): fdf = fdf[fdf['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): fdf = fdf[fdf['date'].dt.date <= st.session_state['date_to']]
if st.session_state.get('phases'):
    phases_norm = [p.title().replace('Power Play','Powerplay') for p in st.session_state['phases']]
    fdf = fdf[fdf['phase'].isin(phases_norm)]

# B. Specific Filters
if view_mode == "Specific Matches":
    if st.session_state.get('matches'):
        fdf = fdf[fdf['teams'].isin(st.session_state['matches'])]
    if st.session_state.get('batters'):
        fdf = fdf[fdf['batter'].isin(st.session_state['batters'])]
    if st.session_state.get('bowlers'):
        fdf = fdf[fdf['bowler'].isin(st.session_state['bowlers'])]
else:
    st.info(f"Viewing Overall Stats (Leaderboard Mode). Ignoring specific match selections.")
    if st.session_state.get('batters'):
        fdf = fdf[fdf['batter'].isin(st.session_state['batters'])]
    if st.session_state.get('bowlers'):
        fdf = fdf[fdf['bowler'].isin(st.session_state['bowlers'])]

if fdf.empty:
    st.warning("No data for selected filters.")
    st.stop()

gc.collect()

# --- HELPERS ---
def overs_from_balls(balls):
    o = balls // 6
    b = balls % 6
    return f"{int(o)}.{int(b)}"

def compute_batting_positions(df_all):
    orders = []
    needed_cols = ['match_id','innings','batter','ball_float']
    available = [c for c in needed_cols if c in df_all.columns]
    
    for (mid, inn), g in df_all[available].groupby(['match_id','innings'], observed=True):
        first = g.groupby('batter', observed=True)['ball_float'].min().reset_index().sort_values('ball_float')
        first['position'] = range(1, len(first)+1)
        first['match_id'] = mid
        first['innings'] = inn
        orders.append(first[['match_id','innings','batter','position']])
    if orders:
        return pd.concat(orders, ignore_index=True)
    return pd.DataFrame(columns=['match_id','innings','batter','position'])

batting_positions = compute_batting_positions(df)

def has_meaningful_numbers(df_):
    if df_ is None or df_.empty:
        return False
    numeric_cols = df_.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return len(df_) > 0
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

def render_with_season_tabs(fdf, metric_func, metric_name, x_col, y_col, chart_title, color, 
                            top_n=50, show_chart=True, metric_func_kwargs=None):
    """
    Helper function to render a metric with season comparison tabs.
    """
    season_view_mode = st.session_state.get('season_view_mode', 'Normal (Per Season)')
    
    # Get available seasons for comparison tabs
    available_seasons = sorted(fdf['year'].dropna().unique()) if 'year' in fdf.columns else []
    
    if metric_func_kwargs is None:
        metric_func_kwargs = {}
    
    if season_view_mode == "Season Comparison (Tabs)" and len(available_seasons) >= 1:
        # Create tabs for each season (no All Seasons Combined tab)
        tab_names = [str(s) for s in available_seasons]
        tabs = st.tabs(tab_names)
        
        for idx, tab in enumerate(tabs):
            with tab:
                # Filter data for this season
                season_data = fdf[fdf['year'] == available_seasons[idx]]
                dfm = metric_func(season_data, **metric_func_kwargs)
                st.markdown(f"**Season: {available_seasons[idx]}**")
                show_table(dfm, metric_name)
                if show_chart and dfm is not None and not dfm.empty:
                    show_bar(dfm.head(top_n), x_col, y_col, chart_title, color=color)
    else:
        # Normal view - show data as-is (per selected filters)
        dfm = metric_func(fdf, **metric_func_kwargs)
        show_table(dfm, metric_name)
        if show_chart and dfm is not None and not dfm.empty:
            show_bar(dfm.head(top_n), x_col, y_col, chart_title, color=color)


# -------------------------
# NEW METRIC FUNCTION: Impact Player Performance (Batting & Bowling)
# -------------------------
def calculate_impact_player_stats(df):
    if 'is_impact_batter' not in df.columns:
        st.warning("Data missing impact flags. Please update via preprocessing.")
        return pd.DataFrame(), pd.DataFrame()

    # 1. Batting Impact
    impact_bat = df[df['is_impact_batter'] == 1].copy()
    if not impact_bat.empty:
        bat_stats = impact_bat.groupby(['batter'], observed=True).agg(
            Runs=('runs.batter', 'sum'),
            Balls=('is_valid_delivery', 'sum'),
            Fours=('runs.batter', lambda x: (x==4).sum()),
            Sixes=('runs.batter', lambda x: (x==6).sum())
        ).reset_index()
        bat_stats['Strike Rate'] = (bat_stats['Runs'] / bat_stats['Balls'] * 100).round(2)
        bat_stats = bat_stats[bat_stats['Balls'] > 0].sort_values('Runs', ascending=False)
    else:
        bat_stats = pd.DataFrame()

    # 2. Bowling Impact
    impact_bowl = df[df['is_impact_bowler'] == 1].copy()
    if not impact_bowl.empty:
        # Calculate runs conceded by bowler
        if 'leg_byes' not in impact_bowl.columns: impact_bowl['leg_byes'] = 0
        if 'byes' not in impact_bowl.columns: impact_bowl['byes'] = 0
        impact_bowl['bowler_runs'] = impact_bowl['runs.total'] - impact_bowl['leg_byes'] - impact_bowl['byes']
        
        bowl_stats = impact_bowl.groupby(['bowler'], observed=True).agg(
            Wickets=('wicket_count', 'sum'),
            Runs_Conceded=('bowler_runs', 'sum'),
            Balls_Bowled=('is_valid_delivery', 'sum')
        ).reset_index()
        
        bowl_stats['Overs'] = bowl_stats['Balls_Bowled'].apply(overs_from_balls)
        bowl_stats['Economy'] = (bowl_stats['Runs_Conceded'] / (bowl_stats['Balls_Bowled']/6)).round(2)
        bowl_stats = bowl_stats[bowl_stats['Balls_Bowled'] > 0].sort_values('Wickets', ascending=False)
    else:
        bowl_stats = pd.DataFrame()

    return bat_stats, bowl_stats

# -------------------------
# Existing Metric Functions
# -------------------------

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
        if len(scores) >= 5:
            weights = [0.10, 0.15, 0.20, 0.25, 0.30] 
            predicted_run = sum([s * w for s, w in zip(scores, weights)])
        else:
            predicted_run = sum(scores) / len(scores)
        recent_avg = sum(scores[-2:]) / 2 if len(scores) >= 2 else scores[0]
        old_avg = sum(scores[:2]) / 2
        trend = "📈 Rising" if recent_avg > old_avg else "📉 Dipping"
        predictions.append({'Batter': batter, 'Last 5 Scores': str(scores), 'Projected Score': int(round(predicted_run)), 'Form Trend': trend})
    return pd.DataFrame(predictions)

def run_col_name():
    return 'runs.total' if rr_run_source == 'Total runs (incl extras)' else 'runs.batter'

def run_rate_per_match(df_, match_id):
    g = df_[df_['match_id'] == match_id]
    if g.empty: return pd.DataFrame()
    out = []
    run_col = run_col_name()
    for inn, gg in g.groupby('innings', observed=True):
        gg = gg.sort_values(['over','ball_float']).reset_index(drop=True)
        gg['valid_flag'] = gg['is_valid_delivery'].astype(int)
        gg['cum_valid_balls'] = gg['valid_flag'].cumsum()
        gg['cum_runs'] = gg[run_col].cumsum()
        over_end = gg.groupby('over', observed=True).apply(lambda d: d.iloc[-1]).reset_index(drop=True)
        over_end['RR'] = (over_end['cum_runs'] / over_end['cum_valid_balls'] * 6).replace([np.inf, np.nan], 0).round(2)
        over_summary = over_end[['over','RR']].rename(columns={'over':'Over'})
        over_summary['Innings'] = f"Innings {int(inn)}"
        out.append(over_summary)
    if out: return pd.concat(out, ignore_index=True).sort_values(['Innings','Over'])
    return pd.DataFrame()

def run_rate_multi_match_side_by_side(df_, match_id):
    d = run_rate_per_match(df_, match_id)
    if d.empty: return d
    pivot = d.pivot(index='Over', columns='Innings', values='RR').reset_index().fillna(0)
    pivot = pivot.sort_values('Over')
    return pivot

def run_rate_combined_per_over(df_):
    out = []
    run_col = run_col_name()
    for inn, gg in df_.groupby('innings', observed=True):
        gg = gg.sort_values(['over','ball_float']).reset_index(drop=True)
        gg['valid_flag'] = gg['is_valid_delivery'].astype(int)
        gg['cum_valid_balls'] = gg['valid_flag'].cumsum()
        gg['cum_runs'] = gg[run_col].cumsum()
        over_end = gg.groupby('over', observed=True).apply(lambda d: d.iloc[-1]).reset_index(drop=True)
        over_end['RR'] = (over_end['cum_runs'] / over_end['cum_valid_balls'] * 6).replace([np.inf, np.nan], 0).round(2)
        over_end = over_end.rename(columns={'over':'Over'})
        over_end['Innings'] = f"Innings {int(inn)}"
        out.append(over_end[['Over','Innings','RR']])
    if out: return pd.concat(out, ignore_index=True).sort_values(['Innings','Over'])
    return pd.DataFrame()

def extras_breakdown(df_):
    res = {}
    res['wides'] = int(df_['wides'].sum()) if 'wides' in df_.columns else 0
    res['no_balls'] = int(df_['no_balls'].sum()) if 'no_balls' in df_.columns else 0
    res['byes'] = int(df_['byes'].sum()) if 'byes' in df_.columns else 0
    res['leg_byes'] = int(df_['leg_byes'].sum()) if 'leg_byes' in df_.columns else 0
    total_extras = sum(res.values())
    rows = []
    for k,v in res.items():
        if v == 0: continue
        pct = (v/total_extras*100) if total_extras>0 else 0
        rows.append({'Type':k,'Runs':v,'%':round(pct,2)})
    if not rows: return pd.DataFrame()
    return pd.DataFrame(rows)

def key_batting(df_, aggregate_seasons=False, season_filter=None):
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame(columns=['Innings','batter','Team','Runs','BF','SR','Avg','4s','6s','Dots','Dot%'])
    
    if 'innings' in valid.columns: valid['innings'] = valid['innings'].astype('int64')
    if 'batter' in valid.columns: valid['batter'] = valid['batter'].astype(str)
    for c in ['runs.batter', 'is_valid_delivery']:
        if c in valid.columns: valid[c] = valid[c].astype('int64')
    
    # Apply season filter if provided (for season comparison tabs)
    if season_filter is not None and 'year' in valid.columns:
        valid = valid[valid['year'] == season_filter]
        if valid.empty:
            return pd.DataFrame(columns=['Innings','batter','Team','Runs','BF','SR','Avg','4s','6s','Dots','Dot%'])
    
    # Season mode takes priority: when aggregate_seasons or season_filter is specified,
    # ignore the Analysis Scope setting for grouping
    is_overall = (st.session_state.get('view_mode_selection') == "Overall (Season Leaderboard)")
    
    # Determine grouping columns based on aggregation mode
    if aggregate_seasons:
        # Aggregate across all seasons by batter ONLY (not batter+team)
        # This ensures players who changed teams get their full stats combined
        grp_cols = ['batter']
    elif season_filter is not None:
        # When viewing a specific season in tabs mode, show aggregate by batter+team (not per-innings)
        grp_cols = ['batter', 'team']
    elif is_overall:
        # Default Overall mode (no season mode active)
        grp_cols = ['batter', 'team']
    else:
        grp_cols = ['innings', 'batter', 'team']

    # BF = All deliveries faced by batter (excluding wides as they don't reach batter, but including no-balls)
    balls = valid[valid['wides'] == 0].groupby(grp_cols, observed=True).size().rename('BF')
    runs = valid.groupby(grp_cols, observed=True)['runs.batter'].sum().rename('Runs')
    fours = valid[valid['runs.batter'] == 4].groupby(grp_cols, observed=True).size().rename('4s')
    sixes = valid[valid['runs.batter'] == 6].groupby(grp_cols, observed=True).size().rename('6s')
    dots = valid[(valid['runs.batter'] == 0) & (valid['wides'] == 0)].groupby(grp_cols, observed=True).size().rename('Dots')
    
    innings_played = valid.groupby(grp_cols, observed=True)['match_id'].nunique().rename('InningsPlayed')
    
    # Build stats - only include seasons if available and aggregating
    series_to_concat = [runs, balls, fours, sixes, dots, innings_played]
    
    # Count seasons played by each batter (only when aggregating)
    # Count by batter ONLY (not batter+team) so players who changed teams get correct total
    include_seasons = aggregate_seasons and 'year' in valid.columns
    if include_seasons:
        # Get unique seasons per batter (independent of team)
        batter_seasons = valid.groupby('batter', observed=True)['year'].nunique().rename('Seasons')
        # We'll merge this back after creating stats

    stats = pd.concat(series_to_concat, axis=1).fillna(0).reset_index()
    stats['4s'] = stats['4s'].astype(int)
    stats['6s'] = stats['6s'].astype(int)
    stats['Dots'] = stats['Dots'].astype(int)
    stats['SR'] = (stats['Runs'] / stats['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    stats['Avg'] = (stats['Runs'] / stats['InningsPlayed']).replace([np.inf, np.nan], 0).round(2)
    stats['Dot%'] = (stats['Dots'] / stats['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    
    # Merge batter_seasons if include_seasons (count per batter, not per batter+team)
    if include_seasons:
        stats = stats.merge(batter_seasons.reset_index(), on='batter', how='left')
        stats['Seasons'] = stats['Seasons'].fillna(0).astype(int)
    
    if aggregate_seasons:
        stats['Innings'] = "All Seasons"
        # Get the most common team for each batter (since we're grouping by batter only)
        batter_teams = valid.groupby('batter', observed=True)['team'].agg(
            lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown'
        ).reset_index()
        batter_teams.columns = ['batter', 'Team']
        batter_teams['Team'] = batter_teams['Team'].astype(str)
        stats = stats.merge(batter_teams, on='batter', how='left')
        stats['Team'] = stats['Team'].astype(str).fillna('Unknown')
        if include_seasons:
            cols = ['Innings','batter','Team','Seasons','InningsPlayed','Runs','BF','SR','Avg','4s','6s','Dots','Dot%']
        else:
            cols = ['Innings','batter','Team','InningsPlayed','Runs','BF','SR','Avg','4s','6s','Dots','Dot%']
        return stats[cols].rename(columns={'InningsPlayed':'Inns'}).sort_values('Runs', ascending=False)
    elif season_filter is not None:
        # Season comparison mode - show aggregate
        stats['Innings'] = f"Season {season_filter}"
        cols = ['Innings','batter','team','InningsPlayed','Runs','BF','SR','Avg','4s','6s','Dots','Dot%']
    elif is_overall:
        stats['Innings'] = "Overall"
        cols = ['Innings','batter','team','InningsPlayed','Runs','BF','SR','Avg','4s','6s','Dots','Dot%']
    else:
        stats['Innings'] = stats['innings'].map({1:'Innings 1',2:'Innings 2'})
        cols = ['Innings','batter','team','InningsPlayed','Runs','BF','SR','Avg','4s','6s','Dots','Dot%']
    
    return stats[cols].rename(columns={'team':'Team', 'InningsPlayed':'Inns'}).sort_values('Runs', ascending=False)

def key_bowling(df_, no_team_filter=False, aggregate_seasons=False, season_filter=None):
    g = df_.copy()
    if g.empty:
        return pd.DataFrame(columns=['Innings','Bowler','Team','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots'])
    
    if 'byes' not in g.columns: g['byes'] = 0
    if 'leg_byes' not in g.columns: g['leg_byes'] = 0
    g['runs_to_bowler'] = g['runs.total'] - g['byes'] - g['leg_byes']
    
    # Apply season filter if provided (for season comparison tabs)
    if season_filter is not None and 'year' in g.columns:
        g = g[g['year'] == season_filter]
        if g.empty:
            return pd.DataFrame(columns=['Innings','Bowler','Team','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots'])
    
    # Use bowling_team for proper team association (the team the bowler plays for)
    # Fallback to 'team' if 'bowling_team' doesn't exist (for backward compatibility)
    team_col = 'bowling_team' if 'bowling_team' in g.columns else 'team'
    
    # Convert team column to string to avoid Categorical issues
    g[team_col] = g[team_col].astype(str)
    
    # Season mode takes priority: when aggregate_seasons or season_filter is specified,
    # ignore the Analysis Scope setting for grouping
    is_overall = (st.session_state.get('view_mode_selection') == "Overall (Season Leaderboard)")
    
    # Determine grouping columns based on aggregation mode
    if aggregate_seasons or no_team_filter:
        grp_cols = ['bowler']
    elif season_filter is not None:
        # When viewing a specific season in tabs mode, show aggregate by bowler+team (not per-innings)
        grp_cols = ['bowler', team_col]
    elif is_overall:
        grp_cols = ['bowler', team_col]
    else:
        # For Specific Matches mode, include match_id to show per-match breakdown
        grp_cols = ['match_id', 'innings', 'bowler', team_col]

    grp = g.groupby(grp_cols, observed=True)
    balls = grp['is_valid_delivery'].sum().rename('Balls') 
    runs = grp['runs_to_bowler'].sum().rename('Runs')
    wkts = grp['wicket_count'].sum().rename('Wkts')
    
    # Dots: valid deliveries where no runs scored off the bowler
    dots = g[(g['runs_to_bowler'] == 0) & (g['is_valid_delivery'] == 1)].groupby(grp_cols, observed=True).size().rename('Dots')
    
    # Build stats - only include seasons when aggregating
    series_to_concat = [balls, runs, wkts, dots]
    # Count seasons by bowler ONLY (not bowler+team) so players who changed teams get correct total
    include_seasons = aggregate_seasons and 'year' in g.columns
    if include_seasons:
        bowler_seasons = g.groupby('bowler', observed=True)['year'].nunique().rename('Seasons')
        # We'll merge this later
    
    # For maidens, we still need to group by match/innings/over/bowler, but then aggregate to our grp_cols
    over_grp = ['match_id', 'innings', 'over', 'bowler']
    if not no_team_filter and not aggregate_seasons:
        over_grp.append(team_col)
    over_runs = g.groupby(over_grp, observed=True).agg({'runs_to_bowler':'sum','is_valid_delivery':'sum'}).reset_index()
    maidens_df = over_runs[(over_runs['is_valid_delivery'] == 6) & (over_runs['runs_to_bowler']==0)]
    maiden_counts = maidens_df.groupby(grp_cols, observed=True).size().rename('Maidens')
    
    
    # Calculate Innings Played (unique match+innings combinations per bowler)
    inns_played = grp['match_id'].nunique().rename('InningsPlayed')
    series_to_concat.append(inns_played)

    dfb = pd.concat(series_to_concat, axis=1).fillna(0).reset_index()
    dfb = dfb.merge(maiden_counts.reset_index(), on=grp_cols, how='left')
    dfb['Maidens'] = dfb['Maidens'].fillna(0).astype(int)
    dfb['Dots'] = dfb['Dots'].astype(int)
    
    dfb['Overs'] = dfb['Balls'].apply(overs_from_balls)
    dfb['Econ'] = (dfb['Runs'] / (dfb['Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
    dfb['Avg'] = (dfb['Runs'] / dfb['Wkts']).replace([np.inf, np.nan], 0).round(2)
    dfb['SR'] = (dfb['Balls'] / dfb['Wkts']).replace([np.inf, np.nan], 0).round(2)
    
    if aggregate_seasons:
        dfb['Innings'] = "All Seasons"
        # Get the most common team for each bowler
        bowler_teams = g.groupby('bowler', observed=True)[team_col].agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown').reset_index()
        bowler_teams.columns = ['bowler', 'Team']
        bowler_teams['Team'] = bowler_teams['Team'].astype(str)
        dfb = dfb.merge(bowler_teams, on='bowler', how='left')
        dfb['Team'] = dfb['Team'].astype(str).fillna('Unknown')
        # Merge bowler_seasons (count per bowler only, not per bowler+team)
        if include_seasons:
            dfb = dfb.merge(bowler_seasons.reset_index(), on='bowler', how='left')
            dfb['Seasons'] = dfb['Seasons'].fillna(0).astype(int)
            return dfb[['Innings','bowler','Team','Seasons','InningsPlayed','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots']].rename(columns={'bowler':'Bowler', 'InningsPlayed':'Inns'}).sort_values('Wkts', ascending=False)
        return dfb[['Innings','bowler','Team','InningsPlayed','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots']].rename(columns={'bowler':'Bowler', 'InningsPlayed':'Inns'}).sort_values('Wkts', ascending=False)
    elif no_team_filter:
        dfb['Innings'] = "Overall"
        # Get the most common team for each bowler (their actual team)
        bowler_teams = g.groupby('bowler', observed=True)[team_col].agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown').reset_index()
        bowler_teams.columns = ['bowler', 'Team']
        bowler_teams['Team'] = bowler_teams['Team'].astype(str)
        dfb = dfb.merge(bowler_teams, on='bowler', how='left')
        dfb['Team'] = dfb['Team'].astype(str).fillna('Unknown')
        return dfb[['Innings','bowler','Team','InningsPlayed','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots']].rename(columns={'bowler':'Bowler', 'InningsPlayed':'Inns'}).sort_values('Wkts', ascending=False)
    elif season_filter is not None:
        # Season comparison mode - show season aggregate (by bowler+team)
        dfb['Innings'] = f"Season {season_filter}"
        return dfb[['Innings','bowler',team_col,'InningsPlayed','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots']].rename(columns={'bowler':'Bowler', team_col:'Team', 'InningsPlayed':'Inns'}).sort_values('Wkts', ascending=False)
    elif is_overall:
        dfb['Innings'] = "Overall"
        # Ensure InningsPlayed/Inns is included here for the main leaderboard
        return dfb[['Innings','bowler',team_col,'InningsPlayed','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots']].rename(columns={'bowler':'Bowler', team_col:'Team', 'InningsPlayed':'Inns'}).sort_values('Wkts', ascending=False)
    else:
        dfb['Innings'] = dfb['innings'].map({1:'Innings 1',2:'Innings 2'})
        
    return dfb[['Innings','bowler',team_col,'InningsPlayed','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots']].rename(columns={'bowler':'Bowler', team_col:'Team', 'InningsPlayed':'Inns'}).sort_values('Wkts', ascending=False)

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
        
        # Check for winner column with margin info (from preprocessing)
        if 'winner' in g.columns and pd.notna(g['winner'].iloc[0]):
            winner = str(g['winner'].iloc[0]).strip()
            if winner:
                wbw = g['win_by_wickets'].iloc[0] if 'win_by_wickets' in g.columns else 0
                wbr = g['win_by_runs'].iloc[0] if 'win_by_runs' in g.columns else 0
                
                if pd.notna(wbw) and wbw > 0:
                    out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': f"{winner} won by {int(wbw)} wickets"})
                    continue
                elif pd.notna(wbr) and wbr > 0:
                    out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': f"{winner} won by {int(wbr)} runs"})
                    continue
                else:
                    out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': f"{winner} won"})
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

# Colors
color_pool = px.colors.qualitative.Plotly + px.colors.qualitative.D3 + px.colors.qualitative.Set3

# Iterate metrics and display
for i, metric in enumerate(st.session_state['metrics']):
    color = color_pool[i % len(color_pool)]
    try:
        
        if metric == "Impact Player Performance":
            st.subheader("⚡ Impact Player Performance")
            if 'IPL' not in st.session_state.get('leagues', []) and 'IPL' not in fdf['league'].unique():
                st.info("Impact Players are primarily an IPL feature. Select IPL league to view.")
            else:
                res_bat, res_bowl = calculate_impact_player_stats(fdf)
                
                # Tabbed view for Batting vs Bowling
                tab1, tab2 = st.tabs(["Batting Impact", "Bowling Impact"])
                
                with tab1:
                    if not res_bat.empty:
                        show_table(res_bat)
                        fig = px.bar(res_bat.head(10), x='batter', y='Runs', title="Top Impact Batsmen", color='Strike Rate')
                        st.plotly_chart(fig, width='stretch')
                    else:
                        st.info("No Impact Batters found in selected data.")
                        
                with tab2:
                    if not res_bowl.empty:
                        show_table(res_bowl)
                        fig = px.bar(res_bowl.head(10), x='bowler', y='Wickets', title="Top Impact Bowlers", color='Economy')
                        st.plotly_chart(fig, width='stretch')
                    else:
                        st.info("No Impact Bowlers found in selected data.")

        elif metric == "Score Prediction (Next Match)":
            st.subheader("Score Prediction (Next Match)")
            st.write("Projected score based on recent form (Last 5 innings weighted).") 
            st.write("Hypothetical predictions only")
            if not st.session_state.get('batters'):
                st.info("Select specific batters from the sidebar to see predictions.")
            else:
                dfm = predict_next_score(fdf, st.session_state['batters'])
                show_table(dfm)
                # Trend Graph
                if not dfm.empty:
                    trend_data = fdf[fdf['batter'].isin(st.session_state['batters'])].groupby(['date', 'batter'], observed=True)['runs.batter'].sum().reset_index()
                    fig = px.line(trend_data, x='date', y='runs.batter', color='batter', markers=True, title="Recent Form Trend")
                    st.plotly_chart(fig, width='stretch')

        elif metric == "Run Rate Progression":
            st.subheader("Run Rate Progression")
            st.write("Per-over cumulative run-rate (RR) computed using legal deliveries.")
            if rr_mode == 'Per-over (combined)':
                dfm = run_rate_combined_per_over(fdf)
                show_table(dfm[['Innings','Over','RR']].rename(columns={'Over':'Over','RR':'Avg_RR'}), "Run Rate Progression — Per-over (combined filtered deliveries)")
                show_bar(dfm, 'Over', 'RR', "Per-over Run Rate (combined)", color=color)
            elif rr_mode == 'Per match':
                if not selected_match_for_rr:
                    st.info("Choose a match for Per-match RR view.")
                else:
                    mids = fdf[fdf['teams'] == selected_match_for_rr]['match_id'].unique()
                    if len(mids) == 0:
                        st.info("No data for selected match.")
                    else:
                        mid = mids[0]
                        dfm = run_rate_per_match(fdf, mid)
                        show_table(dfm.rename(columns={'Over':'Over','RR':'RR'}), f"Run Rate Progression — {selected_match_for_rr}")
                        show_bar(dfm, 'Over', 'RR', f"Run Rate Progression ({selected_match_for_rr})", color=color)
            else:
                st.write("Per-match multi-run view shows both innings side-by-side.")
                if not selected_match_for_rr:
                    st.info("Choose a match for Per-match multi-run.")
                else:
                    mids = fdf[fdf['teams'] == selected_match_for_rr]['match_id'].unique()
                    if len(mids) == 0:
                        st.info("No data for selected match.")
                    else:
                        mid = mids[0]
                        dfm = run_rate_multi_match_side_by_side(fdf, mid)
                        show_table(dfm, f"Run Rate (both innings) — {selected_match_for_rr}")           
        elif metric == "Extras Breakdown":
            st.subheader("Extras Breakdown")
            st.write("Breakdown of extras by type (wides, no-balls, byes, leg-byes)")
            dfm = extras_breakdown(fdf)
            show_table(dfm, metric)
            if has_meaningful_numbers(dfm):
                show_bar(dfm, 'Type', '%', "Extras % breakdown", color=color)
        elif metric =="Key Batting":
            st.subheader("Key Batting")
            st.write("Key batting summary (runs, balls faced, strike-rate, 4s/6s, dot%)")
            
            # Get season view mode
            season_view_mode = st.session_state.get('season_view_mode', 'Normal (Per Season)')
            
            # Get available seasons for comparison tabs
            available_seasons = sorted(fdf['year'].dropna().unique()) if 'year' in fdf.columns else []
            
            if season_view_mode == "Season Comparison (Tabs)" and len(available_seasons) >= 1:
                # Create tabs for each season (no All Seasons Combined tab)
                tab_names = [str(s) for s in available_seasons]
                tabs = st.tabs(tab_names)
                
                for idx, tab in enumerate(tabs):
                    with tab:
                        # Individual season tab with aggregated stats
                        dfm = key_batting(fdf, aggregate_seasons=False, season_filter=available_seasons[idx])
                        st.markdown(f"**Season: {available_seasons[idx]}**")
                        show_table(dfm, metric)
                        show_bar(dfm.head(50), 'batter', 'Runs', f"Top Batting Runs", color=color)
            else:
                # Normal view
                dfm = key_batting(fdf, aggregate_seasons=False)
                show_table(dfm, metric)
                show_bar(dfm.head(50), 'batter', 'Runs', "Top Batting Runs", color=color)
        elif metric == "Key Bowling":
            st.subheader("Key Bowling")
            st.write("Key bowling summary overs, balls, runs conceded to bowler, wickets, economy, maidens")
            
            # Toggle for Overall (No Team Filter) view
            col1, col2 = st.columns([3, 1])
            with col2:
                overall_bowling = st.checkbox("📊 Overall (No Team Filter)", key="overall_bowling_toggle", 
                                             help="Aggregate bowler stats across all teams")
            
            # Get season view mode
            season_view_mode = st.session_state.get('season_view_mode', 'Normal (Per Season)')
            
            # Get available seasons for comparison tabs
            available_seasons = sorted(fdf['year'].dropna().unique()) if 'year' in fdf.columns else []
            
            if season_view_mode == "Season Comparison (Tabs)" and len(available_seasons) >= 1:
                # Create tabs for each season (no All Seasons Combined tab)
                tab_names = [str(s) for s in available_seasons]
                tabs = st.tabs(tab_names)
                
                for idx, tab in enumerate(tabs):
                    with tab:
                        # Individual season tab with aggregated stats
                        dfm = key_bowling(fdf, no_team_filter=overall_bowling, aggregate_seasons=False, season_filter=available_seasons[idx])
                        st.markdown(f"**Season: {available_seasons[idx]}**")
                        show_table(dfm, metric)
                        show_bar(dfm.head(50), 'Bowler', 'Wkts', f"Top Wicket Takers", color=color)
            else:
                # Normal view
                dfm = key_bowling(fdf, no_team_filter=overall_bowling, aggregate_seasons=False)
                show_table(dfm, metric)
                show_bar(dfm.head(50), 'Bowler', 'Wkts', "Top Wicket Takers", color=color)
        elif metric == "BPSix":
            st.subheader("Balls-per-Six (BPSix)")
            st.write("how many legal balls a batter takes on average to hit a six")
            render_with_season_tabs(fdf, bpsix, metric, 'batter', 'BPSix', "Balls per Six", color)
        elif metric == "BP4":
            st.subheader("Balls-per-Four (BP4)")
            st.write("how many legal balls a batter takes on average to hit a four")
            render_with_season_tabs(fdf, bp4, metric, 'batter', 'BP4', "Balls per Four", color)
        elif metric == "Boundary Balls %":
            st.subheader("Boundary Balls %")
            st.write("Percentage of balls faced by batter that yielded a boundary (4/6)")
            render_with_season_tabs(fdf, boundary_balls_pct, metric, 'batter', 'Boundary %', "Boundary % by Batter", color)
        elif metric == "Powerplay Boundary Rate":
            st.subheader("Powerplay Boundary Rate")
            st.write("Team boundary rate (boundaries per legal ball) inside mandatory powerplay")
            render_with_season_tabs(fdf, powerplay_boundary_rate, metric, 'Team', 'PPBR (%)', "Powerplay Boundary Rate (%) — aggregated per team", color)
        elif metric == "Death Wag %":
            st.subheader("Death Wag %")
            st.write("Share of death-innings runs coming from lower-order batters (pos7-11)")
            render_with_season_tabs(fdf, death_wag_pct, metric, 'Teams', 'Death Wag %', "Death Wag % aggregated by team", color)
        elif metric == "Match-Up Dominance":
            st.subheader("Match-Up Dominance")
            st.write("How much better/worse a batter performs vs specific bowlers compared to season SR")
            render_with_season_tabs(fdf, match_up_dominance, metric, 'batter', 'MDS', "Match-Up Dominance Score (sample)", color, top_n=50)
        elif metric == "Pressure Index":
            st.subheader("Pressure Index")
            st.write("Average pressure faced per legal ball (runs * wicket-pressure metric)")
            render_with_season_tabs(fdf, pressure_index, metric, 'batter', 'Pressure Index', "Pressure Index (avg pressure per ball faced)", color)
        elif metric == "Dot Ball % Trend":
            st.subheader("Dot Ball % Trend")
            st.write("Dot-ball percentage per batter (legal deliveries only)")
            render_with_season_tabs(fdf, dot_ball_pct_trend, metric, 'batter', 'Dot %', "Dot % Trend by Batter", color)
        elif metric == "Bowler Boundary Leakage by Phase":
            st.subheader("Bowler Boundary Leakage by Phase")
            st.write("Boundaries conceded by bowlers grouped by phase (Powerplay/Death/etc)")
            render_with_season_tabs(fdf, bowler_boundary_leakage_by_phase, metric, 'Bowler', 'Leakage %', "Bowler Boundary Leakage by Phase", color)
        elif metric == "Batter Contribution %":
            st.subheader("Batter Contribution %")
            st.write("Batter's contribution to their innings total (percentage)")
            render_with_season_tabs(fdf, batter_contribution, metric, 'batter', 'Contribution %', "Batter Contribution %", color)
        elif metric == "Match Results":
            st.subheader("Match Results")
            st.write("Match outcomes (inferred if not present) - who won and margin")
            dfm = match_results(fdf)
            show_table(dfm, metric)
        else:
            st.write(f"**{metric}** - Coming soon")
    except Exception as e:
        st.error(f"Error computing {metric}: {e}")