# app.py (full file) - Final: Impact Player Batting & Bowling Support
import streamlit as st
import gc
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

st.set_page_config(page_title="T20 Stats", layout="wide")

# --- WOMEN'S T20 WORLD CUP CONSTANTS ---
_WT20WC_TEAMS = {
    'Australia', 'Bangladesh', 'England', 'India', 'Ireland', 'Netherlands', 'New Zealand',
    'Pakistan', 'Scotland', 'South Africa', 'Sri Lanka', 'Thailand', 'West Indies',
}
_WT20WC_DATE_RANGES = [
    (pd.Timestamp('2016-03-15'), pd.Timestamp('2016-04-03')),
    (pd.Timestamp('2018-11-09'), pd.Timestamp('2018-11-25')),
    (pd.Timestamp('2020-02-21'), pd.Timestamp('2020-03-08')),
    (pd.Timestamp('2023-02-10'), pd.Timestamp('2023-02-26')),
    (pd.Timestamp('2024-10-03'), pd.Timestamp('2024-10-20')),
    (pd.Timestamp('2026-06-12'), pd.Timestamp('2026-07-05')),
]
def _is_wt20wc_match(date_series):
    try:
        dates = pd.to_datetime(date_series).dt.tz_localize(None)
    except TypeError:
        dates = pd.to_datetime(date_series).dt.tz_convert(None)
    mask = pd.Series(False, index=date_series.index)
    for s, e in _WT20WC_DATE_RANGES:
        mask |= (dates >= s) & (dates <= e)
    return mask

# --- PREMIUM GRAPH TEMPLATE ---
import plotly.io as pio
PREMIUM_TEMPLATE = dict(
    layout=dict(
        font=dict(family='Inter, sans-serif', size=13),
        title=dict(font=dict(size=20, family='Inter, sans-serif', color='#1a1a2e')),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, linecolor='#e0e0e0'),
        yaxis=dict(gridcolor='#f0f0f0', linecolor='#e0e0e0'),
        colorway=['#6C63FF','#FF6584','#43B988','#FFB347','#4FC3F7','#AB47BC','#FF7043','#26C6DA','#EC407A','#66BB6A'],
        margin=dict(l=40, r=20, t=60, b=40),
    )
)
pio.templates['premium'] = pio.templates['plotly_white']
pio.templates['premium'].layout.update(PREMIUM_TEMPLATE['layout'])
pio.templates.default = 'premium'

st.markdown("""
**By Vishwesh Gaur** [Twitter: @iumvishwesh](https://twitter.com/iumvishwesh) | [LinkedIn: vishwesh-gaur-56760b112](https://www.linkedin.com/in/vishwesh-gaur-56760b112)  
""")

st.markdown("Last updated: 18 June 2026")
st.markdown("Fresh Matches Will Appear as per Data Availability from Cricsheet")
st.markdown("New: 'Impact Player' (Batting & Bowling for IPL) & 'Score Prediction'!")
st.markdown("**Coach/Analyst Metrics Added:** Batting Acceleration Rate, Bowling Spell Efficiency, Collapse Detector, Player Absence Impact")

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

st.markdown("""
<h1 style='background: linear-gradient(90deg, #6C63FF, #FF6584); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 800; font-size: 2.2rem;'>🏏 Global T20 Dashboard: IPL, MBBL, WBBL, SA20, WPL & MLC Insights</h1>
""", unsafe_allow_html=True)

DATA_SOURCE = "t20_data.parquet"
PLAYING_XI_SOURCE = "playing_xi.parquet"

# Franchise aliases — normalize renamed teams to a single name
TEAM_ALIASES = {
    'Royal Challengers Bengaluru': 'Royal Challengers Bangalore',
    'Delhi Capitals': 'Delhi Daredevils',
    'Punjab Kings': 'Kings XI Punjab',
    'Rising Pune Supergiant': 'Rising Pune Supergiants',
    'Pune Warriors': 'Pune Warriors India',
}

# show league start dates (informational)
LEAGUE_START_DATES = {
    'WBBL': '2020-10-25',
    'MBBL': '2020-12-10',
    'WPL':  '2023-03-04',
    'SA20': '2023-01-10',
    'IPL':  '2008-04-18',
    'MLC':  '2023-07-13',
    'WT20I': '2000-01-01',  # Women's T20 Internationals
}

st.markdown("**Data included from:** " + " | ".join([f"{lg}: {dt}" for lg, dt in LEAGUE_START_DATES.items()]))

# default compact height; slider in sidebar allows user to change
DEFAULT_COMPACT_HEIGHT = 250

@st.cache_data
def load_data(path=DATA_SOURCE, _v=3):  # v3: fix teams col normalization + add Netherlands
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
        
        # --- Team Name Normalization: 'England Women' -> 'England' etc ---
        # Use plain replace (no $ anchor) so both sides of 'X Women vs Y Women' are fixed.
        for _col in ['team', 'teams']:
            if _col in df.columns:
                df[_col] = df[_col].astype(str).str.replace(' Women', '', regex=False)

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

        # ── Player name normalization ──────────────────────────────────────────
        # Normalize known spelling variants so all metrics aggregate correctly.
        # Key = alternate/wrong spelling found in Cricsheet JSON
        # Value = canonical display name you want everywhere in the app
        # To add a new fix: just add another line below in the same format.
        _NAME_FIX = {
            'V Sooryavanshi': 'V Suryavanshi',
            'Prabhsimran Singh': 'P Simran Singh',
            'CPL Connolly': 'C Connolly',
            'Rahul Tewatia': 'R Tewatia',
        }
        for col in ['batter', 'bowler', 'player_dismissed', 'non_striker']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace(_NAME_FIX)
                if df[col].nunique() < len(df) * 0.5:
                    df[col] = df[col].astype('category')
        # ───────────────────────────────────────────────────────────────────────

        return df
    except Exception as e:
        print(f"!!! Error in load_data: {e}")
        st.error(f"Data not found or failed to load: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

@st.cache_data
def load_playing_xi(path=PLAYING_XI_SOURCE):
    """Load playing XI lookup table and normalize team names."""
    try:
        xi = pd.read_parquet(path)
        xi['team'] = xi['team'].replace(TEAM_ALIASES)
        if 'winner' in xi.columns:
            xi['winner'] = xi['winner'].replace(TEAM_ALIASES)
        return xi
    except Exception as e:
        print(f"!!! Error loading playing_xi: {e}")
        return pd.DataFrame()

playing_xi_df = load_playing_xi()

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

# World Cup filter — only when WT20I explicitly selected
_wt20i_leagues = st.session_state.get('leagues', [])
_wt20wc_active = bool(_wt20i_leagues and 'WT20I' in _wt20i_leagues)
if _wt20wc_active:
    st.sidebar.markdown("---")
    st.sidebar.checkbox(
        "World Cup Only (WT20WC)",
        value=False,
        key="wt20wc_only",
        help="Show only Women's T20 World Cup matches (2016, 2018, 2020, 2023, 2024). Data complete from 2016 onwards."
    )
    st.sidebar.markdown("---")
else:
    st.session_state['wt20wc_only'] = False

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
p_df = df
if st.session_state.get('leagues'): p_df = p_df[p_df['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): p_df = p_df[p_df['year'].isin(st.session_state['years'])]
# Fix: Apply date filter to dropdowns
if st.session_state.get('date_from'): p_df = p_df[p_df['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): p_df = p_df[p_df['date'].dt.date <= st.session_state['date_to']]
# Apply WC filter to dropdowns so only WC teams/matches appear
if st.session_state.get('wt20wc_only') and 'date' in p_df.columns:
    p_df = p_df[_is_wt20wc_match(p_df['date'])]
    if 'team' in p_df.columns:
        p_df = p_df[p_df['team'].astype(str).isin(_WT20WC_TEAMS)]

available_phases = sorted(p_df['phase'].dropna().unique())
if any(l in st.session_state.get('leagues', []) for l in ['WBBL', 'MBBL']):
    if 'Power Surge' not in available_phases:
        available_phases = list(available_phases) + ['Power Surge']
if not available_phases:
    available_phases = ['Powerplay','Power Surge','Middle','Death']

st.sidebar.multiselect("Phase", available_phases, key="phases", on_change=clear_submitted)

with st.sidebar.expander("ℹ️ Phase Definitions", expanded=False):
    st.markdown("""
    **General (IPL, WPL, SA20, MLC)**
    - **Powerplay**: Overs 1-6
    - **Middle**: Overs 7-16
    - **Death**: Overs 17-20
    
    **BBL (MBBL, WBBL)**
    - **Powerplay**: Overs 1-4
    - **Middle**: Overs 5-16 (excl. Surge)
    - **Death**: Overs 17-20
    """)
# --- 2c. Team Filter ---
st.sidebar.markdown("---")
_team_col = 'team' if 'team' in p_df.columns else None
_bowling_col = 'bowling_team' if 'bowling_team' in p_df.columns else None
if _team_col:
    # Build unique team list: union of batting + bowling teams in filtered data
    _teams_bat = p_df[_team_col].dropna().astype(str).unique().tolist()
    _teams_bowl = p_df[_bowling_col].dropna().astype(str).unique().tolist() if _bowling_col else []
    _all_teams = sorted(set(_teams_bat + _teams_bowl) - {'nan', 'None', ''})
    sel_teams = st.sidebar.multiselect(
        "Team",
        _all_teams,
        key="teams_filter",
        on_change=clear_submitted,
        help="Filter matches where the selected team(s) appeared (batting OR bowling)."
    )
    if sel_teams:
        _team_match_ids = p_df[
            p_df[_team_col].astype(str).isin(sel_teams) |
            (p_df[_bowling_col].astype(str).isin(sel_teams) if _bowling_col else False)
        ]['match_id'].unique()
        p_df = p_df[p_df['match_id'].isin(_team_match_ids)]
else:
    sel_teams = []

st.sidebar.markdown("---")
st.sidebar.markdown("##### Match Type")

# Check if event_stage column is available in the loaded data
_has_event_stage = 'event_stage' in df.columns

if _has_event_stage:
    _match_type = st.sidebar.radio(
        "Match Type",
        ["All Matches", "League Matches Only", "Playoff / Knockouts Only"],
        key="match_type_filter",
        on_change=clear_submitted,
        help="League Matches Only: regular round-robin games.\nPlayoff/Knockouts Only: Qualifier, Eliminator, Semi Final, Final etc."
    )

    # Build available playoff stages from current pre-filtered data (p_df)
    _playoff_stages_all = sorted(
        p_df[p_df['event_stage'].astype(str).str.lower() != 'group']['event_stage']
        .dropna().astype(str).unique()
    ) if _has_event_stage and 'event_stage' in p_df.columns else []

    sel_playoff_stages = []
    if _match_type == "Playoff / Knockouts Only" and _playoff_stages_all:
        st.sidebar.caption("Filter by specific playoff round (optional):")
        sel_playoff_stages = st.sidebar.multiselect(
            "Playoff Stage",
            _playoff_stages_all,
            key="playoff_stages",
            on_change=clear_submitted,
            help="Leave blank to include ALL playoff rounds. Select specific rounds to narrow down."
        )
else:
    _match_type = "All Matches"
    sel_playoff_stages = []
    st.sidebar.info("⚠️ Playoff filter unavailable — please re-run preprocessing.py to regenerate data.")

# Apply match type to p_df (for downstream match/batter/bowler dropdowns)
if _has_event_stage and 'event_stage' in p_df.columns:
    if _match_type == "League Matches Only":
        p_df = p_df[p_df['event_stage'].astype(str) == 'group']
    elif _match_type == "Playoff / Knockouts Only":
        p_df = p_df[p_df['event_stage'].astype(str) != 'group']
        if sel_playoff_stages:
            p_df = p_df[p_df['event_stage'].astype(str).isin(sel_playoff_stages)]

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

# Match Selector — show "Teams (Date)" labels
if 'teams' in p_df.columns and not p_df['teams'].dropna().empty:
    match_info = p_df.groupby(['match_id', 'teams'], observed=True)['date'].first().reset_index()
    match_info['date_str'] = pd.to_datetime(match_info['date']).dt.strftime('%d %b %Y')
    match_info['label'] = match_info['teams'].astype(str) + ' (' + match_info['date_str'] + ')'
    match_info = match_info.sort_values('date')
    match_label_to_id = dict(zip(match_info['label'], match_info['match_id']))
    match_options = list(match_info['label'])
else:
    match_options = sorted(p_df['match_id'].dropna().unique().astype(str))
    match_label_to_id = {m: m for m in match_options}

st.session_state.matches = [m for m in st.session_state.matches if m in match_options]
st.sidebar.multiselect("Match", match_options, key="matches", on_change=clear_submitted)

# Batter Selector
batter_source = p_df
if st.session_state.get('matches'):
    selected_match_ids = [match_label_to_id[m] for m in st.session_state['matches'] if m in match_label_to_id]
    batter_source = batter_source[batter_source['match_id'].isin(selected_match_ids)]
if 'batter' in batter_source.columns:
    batter_options = sorted(batter_source['batter'].dropna().unique())
else:
    batter_options = []
st.session_state.batters = [b for b in st.session_state.batters if b in batter_options]
st.sidebar.multiselect("Batter", batter_options, key="batters", on_change=clear_submitted)

# Bowler Selector
bowler_source = p_df
if st.session_state.get('matches'):
    selected_match_ids_b = [match_label_to_id[m] for m in st.session_state['matches'] if m in match_label_to_id]
    bowler_source = bowler_source[bowler_source['match_id'].isin(selected_match_ids_b)]
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
    "Dot Ball % Trend", "Bowler Boundary Leakage by Phase", "Match Results",
    # NEW METRICS
    "Over-wise Batting Analysis", "Death Over Bowling Analysis", 
    "Match by Match Analysis", "Batter vs Bowler Matchups",
    # COACH / ANALYST METRICS
    "Batting Acceleration Rate",
    "Bowling Spell Efficiency", "Collapse Detector",
    "Player Absence Impact"
]
st.sidebar.markdown("---")
st.sidebar.markdown("**Coach / Analyst Metrics:** Acceleration Rate, Spell Efficiency, Collapse Detector, Player Absence Impact")
st.sidebar.multiselect("Metrics", metrics, key="metrics", on_change=clear_submitted)

# --- Charts toggle ---
st.sidebar.markdown("---")
show_charts_global = st.sidebar.checkbox(
    "📊 Show Charts",
    value=True,
    key="show_charts_global",
    help="Uncheck to hide bar charts for all metrics — useful when viewing multiple metrics at once."
)

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
fdf = df

# A. Base Filters
if st.session_state.get('leagues'): fdf = fdf[fdf['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): fdf = fdf[fdf['year'].isin(st.session_state['years'])]
if st.session_state.get('date_from'): fdf = fdf[fdf['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): fdf = fdf[fdf['date'].dt.date <= st.session_state['date_to']]

# World Cup filter
if st.session_state.get('wt20wc_only') and 'date' in fdf.columns:
    fdf = fdf[_is_wt20wc_match(fdf['date'])]
    if 'team' in fdf.columns:
        fdf = fdf[fdf['team'].astype(str).isin(_WT20WC_TEAMS)]
if st.session_state.get('phases'):
    phases_norm = [p.title().replace('Power Play','Powerplay') for p in st.session_state['phases']]
    fdf = fdf[fdf['phase'].isin(phases_norm)]

# C. Playoff / Match Type Filter
if _has_event_stage and 'event_stage' in fdf.columns:
    if _match_type == "League Matches Only":
        fdf = fdf[fdf['event_stage'].astype(str) == 'group']
    elif _match_type == "Playoff / Knockouts Only":
        fdf = fdf[fdf['event_stage'].astype(str) != 'group']
        if sel_playoff_stages:
            fdf = fdf[fdf['event_stage'].astype(str).isin(sel_playoff_stages)]

# D. Team Filter
# Filter delivery rows directly: batting rows where team is in selection.
# This ensures Key Batting shows only that team's batters, and all bowling/run-rate
# metrics are scoped to deliveries faced by the selected team.
if sel_teams and 'team' in fdf.columns:
    fdf = fdf[fdf['team'].astype(str).isin(sel_teams)]

# B. Specific Filters
if view_mode == "Specific Matches":
    if st.session_state.get('matches'):
        selected_match_ids_f = [match_label_to_id[m] for m in st.session_state['matches'] if m in match_label_to_id]
        fdf = fdf[fdf['match_id'].isin(selected_match_ids_f)]
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

if st.session_state.get('wt20wc_only'):
    st.info("**World Cup Filter Active** — Showing Women's T20 World Cup matches (2016, 2018, 2020, 2023, 2024, 2026). Data complete from 2016 onwards. Uncheck 'World Cup Only' in sidebar to see all WT20I matches.")

gc.collect()

# --- HELPERS ---
def overs_from_balls(balls):
    o = balls // 6
    b = balls % 6
    return f"{int(o)}.{int(b)}"

@st.cache_data(show_spinner=False)
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
    # Use the user-configured height for inline view.
    # Passing height=None lets Streamlit auto-size (needed for fullscreen to work).
    _h = st.session_state.compact_height
    st.dataframe(df_, width='stretch', height=_h if _h and _h > 0 else None)

def show_bar(df_, x, y, title, color=None, top_n=None):
    # Respect the global Show Charts toggle — if unchecked, skip all bar charts
    if not st.session_state.get('show_charts_global', True):
        return
    if df_ is None or df_.empty:
        st.info("No data.")
        return
    if top_n:
        df_ = df_.head(top_n)
    if color:
        fig = px.bar(df_, x=x, y=y, title=title, color_discrete_sequence=[color])
    else:
        fig = px.bar(df_, x=x, y=y, title=title)
    fig.update_traces(marker_line_width=0, opacity=0.9)
    fig.update_layout(
        title=dict(font=dict(size=18, color='#1a1a2e')),
        xaxis_tickangle=-45,
        bargap=0.15
    )
    show_plotly_chart(fig)

def show_plotly_chart(fig, **kwargs):
    """Wrapper around st.plotly_chart that respects the global Show Charts toggle."""
    if not st.session_state.get('show_charts_global', True):
        return
    kw = {k: v for k, v in kwargs.items() if k not in ('width', 'use_container_width')}
    st.plotly_chart(fig, width="stretch", **kw)

def render_with_season_tabs(fdf, metric_func, metric_name, x_col, y_col, chart_title, color, 
                            top_n=50, show_chart=True, metric_func_kwargs=None):
    """
    Helper function to render a metric with season comparison tabs.
    """
    season_view_mode = st.session_state.get('season_view_mode', 'Normal (Per Season)')
    # Respect the global 'Show Charts' toggle
    show_chart = show_chart and st.session_state.get('show_charts_global', True)
    
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
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    def _bat_agg(grp_df, grp_cols):
        d = grp_df.copy()
        for c in ['runs.batter', 'is_valid_delivery']:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)
        stats = d.groupby(grp_cols, observed=True).agg(
            Runs=('runs.batter', 'sum'),
            Balls=('is_valid_delivery', 'sum'),
            Fours=('runs.batter', lambda x: (x == 4).sum()),
            Sixes=('runs.batter', lambda x: (x == 6).sum())
        ).reset_index()
        stats['Strike Rate'] = (stats['Runs'] / stats['Balls'] * 100).round(2)
        return stats[stats['Balls'] > 0].sort_values('Runs', ascending=False)

    def _bowl_agg(grp_df, grp_cols):
        d = grp_df.copy()
        if 'leg_byes' not in d.columns: d['leg_byes'] = 0
        if 'byes' not in d.columns: d['byes'] = 0
        d['bowler_runs'] = d['runs.total'] - d['leg_byes'] - d['byes']
        stats = d.groupby(grp_cols, observed=True).agg(
            Wickets=('wicket_count', 'sum'),
            Runs_Conceded=('bowler_runs', 'sum'),
            Balls_Bowled=('is_valid_delivery', 'sum')
        ).reset_index()
        stats['Overs'] = stats['Balls_Bowled'].apply(overs_from_balls)
        stats['Economy'] = (stats['Runs_Conceded'] / (stats['Balls_Bowled'] / 6)).round(2)
        return stats[stats['Balls_Bowled'] > 0].sort_values('Wickets', ascending=False)

    def _bat_per_match(grp_df):
        """Per-match view: one row per (innings, batter, match) with Team, Against, Date."""
        d = grp_df.copy()
        for c in ['runs.batter', 'is_valid_delivery']:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)
        d['team'] = d['team'].astype(str)

        grp_cols = [c for c in ['innings', 'batter', 'team', 'match_id', 'date'] if c in d.columns]
        stats = d.groupby(grp_cols, observed=True).agg(
            Runs=('runs.batter', 'sum'),
            Balls=('is_valid_delivery', 'sum'),
            Fours=('runs.batter', lambda x: (x == 4).sum()),
            Sixes=('runs.batter', lambda x: (x == 6).sum())
        ).reset_index()
        stats['SR'] = (stats['Runs'] / stats['Balls'] * 100).round(2)
        stats = stats[stats['Balls'] > 0]

        # Derive 'Against' from the 'teams' column (e.g. "CSK vs MI")
        if 'teams' in d.columns and 'match_id' in stats.columns:
            meta = d.drop_duplicates('match_id')[['match_id', 'teams']].copy()
            meta['teams'] = meta['teams'].astype(str)
            stats = stats.merge(meta, on='match_id', how='left')
            stats['Against'] = stats.apply(
                lambda r: next(
                    (p.strip() for p in str(r.get('teams', '')).split(' vs ') if p.strip() != r.get('team', '')),
                    ''
                ), axis=1
            )
            stats = stats.drop(columns=['teams', 'match_id'])

        if 'date' in stats.columns:
            stats['date'] = pd.to_datetime(stats['date']).dt.strftime('%d %b %Y')

        stats = stats.rename(columns={
            'innings': 'Innings', 'batter': 'Batter', 'team': 'Team', 'date': 'Date'
        })
        col_order = ['Innings', 'Batter', 'Team', 'Against', 'Date', 'Runs', 'Balls', 'SR', 'Fours', 'Sixes']
        return stats[[c for c in col_order if c in stats.columns]].sort_values(
            ['Innings', 'Runs'], ascending=[True, False]
        )

    def _bowl_per_match(grp_df):
        """Per-match view: one row per (innings, bowler, match) with Team, Against, Date."""
        d = grp_df.copy()
        if 'leg_byes' not in d.columns: d['leg_byes'] = 0
        if 'byes' not in d.columns: d['byes'] = 0
        d['bowler_runs'] = d['runs.total'] - d['leg_byes'] - d['byes']

        # bowling_team = the bowler's own team; if absent, derive it below
        team_col = 'bowling_team' if 'bowling_team' in d.columns else None
        if team_col:
            d[team_col] = d[team_col].astype(str)

        grp_cols = [c for c in ['innings', 'bowler', team_col, 'match_id', 'date'] if c]
        grp_cols = [c for c in grp_cols if c in d.columns]
        stats = d.groupby(grp_cols, observed=True).agg(
            Wickets=('wicket_count', 'sum'),
            Runs_Conceded=('bowler_runs', 'sum'),
            Balls_Bowled=('is_valid_delivery', 'sum')
        ).reset_index()
        stats['Overs'] = stats['Balls_Bowled'].apply(overs_from_balls)
        stats['Economy'] = (stats['Runs_Conceded'] / (stats['Balls_Bowled'] / 6)).round(2)
        stats = stats[stats['Balls_Bowled'] > 0]

        if 'teams' in d.columns and 'match_id' in stats.columns:
            d['team'] = d['team'].astype(str)
            meta = d.drop_duplicates('match_id')[['match_id', 'teams', 'team']].copy()
            meta['teams'] = meta['teams'].astype(str)
            stats = stats.merge(meta, on='match_id', how='left')
            # Against = batting team (always the 'team' column per delivery)
            stats = stats.rename(columns={'team': 'Against'})
            if team_col:
                stats = stats.rename(columns={team_col: 'Team'})
            else:
                # Derive bowler's team as the non-batting side from teams string
                stats['Team'] = stats.apply(
                    lambda r: next(
                        (p.strip() for p in str(r.get('teams', '')).split(' vs ') if p.strip() != r.get('Against', '')),
                        ''
                    ), axis=1
                )
            stats = stats.drop(columns=['teams', 'match_id'], errors='ignore')

        if 'date' in stats.columns:
            stats['date'] = pd.to_datetime(stats['date']).dt.strftime('%d %b %Y')

        stats = stats.rename(columns={'innings': 'Innings', 'bowler': 'Bowler', 'date': 'Date'})
        col_order = ['Innings', 'Bowler', 'Team', 'Against', 'Date', 'Wickets', 'Runs_Conceded', 'Overs', 'Economy']
        return stats[[c for c in col_order if c in stats.columns]].sort_values(
            ['Innings', 'Wickets'], ascending=[True, False]
        )

    # ---- Batting ----
    impact_bat = df[df['is_impact_batter'] == 1].copy()
    bat_stats = _bat_agg(impact_bat, ['batter']) if not impact_bat.empty else pd.DataFrame()
    bat_match  = _bat_per_match(impact_bat) if not impact_bat.empty else pd.DataFrame()

    # ---- Bowling ----
    impact_bowl = df[df['is_impact_bowler'] == 1].copy()
    bowl_stats = _bowl_agg(impact_bowl, ['bowler']) if not impact_bowl.empty else pd.DataFrame()
    bowl_match  = _bowl_per_match(impact_bowl) if not impact_bowl.empty else pd.DataFrame()

    return bat_stats, bowl_stats, bat_match, bowl_match

# -------------------------
# Existing Metric Functions
# -------------------------

def predict_next_score(df, selected_batters):
    """Form Guide & Score Projection — comprehensive batter form analysis."""
    if not selected_batters: return pd.DataFrame()
    df = df.copy()
    df['runs.batter'] = df['runs.batter'].astype('int64')
    df_bat = df[df['batter'].isin(selected_batters)]
    innings_data = df_bat.groupby(['match_id', 'date', 'batter'], observed=True).agg(
        Runs=('runs.batter', 'sum'),
        Balls=('is_valid_delivery', 'sum')
    ).reset_index().sort_values('date')

    predictions = []
    for batter in selected_batters:
        b_data = innings_data[innings_data['batter'] == batter]
        if b_data.empty:
            predictions.append({'Batter': batter, 'Inn': 0, 'Season Avg': 0, 'Last 5': '—',
                                'Projected': '—', 'Consistency': '—', 'High': 0,
                                '50+': 0, '30+': 0, 'Form': '—'})
            continue

        all_scores = b_data['Runs'].tolist()
        last5 = b_data.tail(5)['Runs'].tolist()
        season_avg = round(sum(all_scores) / len(all_scores), 1)

        # Weighted projection (recent innings weighted higher)
        if len(last5) >= 3:
            n = len(last5)
            weights = list(range(1, n + 1))  # 1,2,3,4,5
            wt_sum = sum(weights)
            projected = round(sum(s * w for s, w in zip(last5, weights)) / wt_sum, 0)
        else:
            projected = round(sum(all_scores) / len(all_scores), 0)

        # Consistency = coefficient of variation (lower = more consistent)
        if len(all_scores) >= 3:
            mean_s = sum(all_scores) / len(all_scores)
            std_s = (sum((x - mean_s)**2 for x in all_scores) / len(all_scores)) ** 0.5
            consistency = f"{std_s:.0f}" if mean_s > 0 else "—"
        else:
            consistency = "—"

        # Form trend
        if len(last5) >= 4:
            recent_2 = sum(last5[-2:]) / 2
            earlier_2 = sum(last5[:2]) / 2
            if recent_2 > earlier_2 * 1.15:
                trend = "📈 Rising"
            elif recent_2 < earlier_2 * 0.85:
                trend = "📉 Dipping"
            else:
                trend = "➡️ Steady"
        else:
            trend = "➡️ —"

        predictions.append({
            'Batter': batter,
            'Inn': len(all_scores),
            'Season Avg': season_avg,
            'Last 5': ', '.join(str(s) for s in last5),
            'Projected': int(projected),
            'Consistency (σ)': consistency,
            'High': max(all_scores),
            '50+': sum(1 for s in all_scores if s >= 50),
            '30+': sum(1 for s in all_scores if s >= 30),
            'Form': trend
        })
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
        # Handle inn which can be string ("Innings 1") or int (1)
        if isinstance(inn, str) and inn.startswith('Innings'):
            over_summary['Innings'] = inn
        else:
            try:
                over_summary['Innings'] = f"Innings {int(inn)}"
            except (ValueError, TypeError):
                over_summary['Innings'] = str(inn)
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
        # Handle inn which can be string ("Innings 1") or int (1)
        if isinstance(inn, str) and inn.startswith('Innings'):
            over_end['Innings'] = inn
        else:
            try:
                over_end['Innings'] = f"Innings {int(inn)}"
            except (ValueError, TypeError):
                over_end['Innings'] = str(inn)
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

def key_batting(df_, no_team_filter=False, aggregate_seasons=False, season_filter=None):
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame(columns=['Innings','batter','Team','Runs','BF','SR','Avg','4s','6s','Dots','Dot%'])

    # Exclude no-result matches (abandoned/rain) — ESPN/ICC convention: these innings don't
    # count towards averages or innings-played totals.
    # Only exclude innings with < 5 overs completed (truly abandoned/walkover).
    # A match where a batter faced 16+ overs should count regardless of result.
    if 'winner' in valid.columns:
        no_result_mask = valid['winner'].isna()
        if no_result_mask.any():
            max_over_per_inn = valid.groupby(['match_id', 'innings'], observed=True)['over'].transform('max')
            # < 5 means fewer than 5 overs completed — truly abandoned before any meaningful play
            truncated = no_result_mask & (max_over_per_inn < 5)
            valid = valid[~truncated]
    if valid.empty:
        return pd.DataFrame(columns=['Innings','batter','Team','Runs','BF','SR','Avg','4s','6s','Dots','Dot%'])

    # Convert all categorical columns to their base types to avoid "Cannot setitem on a Categorical" errors
    for col in valid.columns:
        if valid[col].dtype.name == 'category':
            valid[col] = valid[col].astype(str) if valid[col].cat.categories.dtype == 'object' else valid[col].astype(valid[col].cat.categories.dtype)
    
    # innings is now a string ("Innings 1", "Innings 2", "BAT1-SO", "BAT2-SO")
    if 'innings' in valid.columns: valid['innings'] = valid['innings'].astype(str)
    if 'batter' in valid.columns: valid['batter'] = valid['batter'].astype(str)
    for c in ['runs.batter', 'is_valid_delivery']:
        if c in valid.columns: valid[c] = pd.to_numeric(valid[c], errors='coerce').fillna(0).astype('int64')
    
    # Apply season filter if provided (for season comparison tabs)
    if season_filter is not None and 'year' in valid.columns:
        valid = valid[valid['year'] == season_filter]
        if valid.empty:
            return pd.DataFrame(columns=['Innings','batter','Team','Runs','BF','SR','Avg','4s','6s','Dots','Dot%'])
    
    # Season mode takes priority: when aggregate_seasons or season_filter is specified,
    # ignore the Analysis Scope setting for grouping
    # Also check if specific matches are selected - if so, we're NOT in overall mode even if radio button says so
    selected_matches = st.session_state.get('matches', [])
    is_overall = (st.session_state.get('view_mode_selection') == "Overall (Season Leaderboard)") and len(selected_matches) == 0
    
    # Determine grouping columns based on aggregation mode
    if aggregate_seasons or no_team_filter:
        # Aggregate by batter ONLY (not batter+team)
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

    # For aggregate views (not per-innings), exclude super over deliveries from stats
    # Super over stats are only shown in per-innings view when user selects "BAT1-SO" or "BAT2-SO"
    is_per_innings_view = (not aggregate_seasons and not no_team_filter and season_filter is None and not is_overall)
    
    if 'is_super_over' in valid.columns and not is_per_innings_view:
        # Exclude super over from aggregate stats
        # Convert to numeric to avoid categorical comparison issues
        valid['is_super_over'] = pd.to_numeric(valid['is_super_over'], errors='coerce').fillna(0).astype(int)
        stats_df = valid[valid['is_super_over'] == 0]
    else:
        stats_df = valid

    # BF = All deliveries faced by batter (excluding wides as they don't reach batter, but including no-balls)
    balls = stats_df[stats_df['wides'] == 0].groupby(grp_cols, observed=True).size().rename('BF')
    runs = stats_df.groupby(grp_cols, observed=True)['runs.batter'].sum().rename('Runs')
    fours = stats_df[stats_df['runs.batter'] == 4].groupby(grp_cols, observed=True).size().rename('4s')
    sixes = stats_df[stats_df['runs.batter'] == 6].groupby(grp_cols, observed=True).size().rename('6s')
    dots = stats_df[(stats_df['runs.batter'] == 0) & (stats_df['wides'] == 0)].groupby(grp_cols, observed=True).size().rename('Dots')
    
    # Calculate Outs (Times Dismissed) - CORRECTLY count all dismissals including run outs as non-striker
    # Outs = is_batter_out (when facing) + is_non_striker_out (when at non-striker end)
    # We need to calculate this by player, not just by batter in data
    
    if 'is_batter_out' in stats_df.columns:
        # 1. Count times dismissed as batter (facing the ball)
        # Exclude 'retired out' — ICC convention: retired (not out) is NOT a dismissal
        _outs_df = stats_df.copy()
        if 'wicket_kind' in _outs_df.columns:
            _retired = {'retired out', 'retired not out', 'retired hurt', 'retired - not out'}
            _outs_df = _outs_df[~_outs_df['wicket_kind'].astype(str).str.lower().str.strip().isin(_retired)]
        batter_outs = _outs_df.groupby(grp_cols, observed=True)['is_batter_out'].sum()
        
        # 2. Count times dismissed as non-striker (run out while not facing)
        if 'is_non_striker_out' in stats_df.columns and 'non_striker' in stats_df.columns:
            # Create a copy to calculate non-striker dismissals
            # We need to map non_striker to batter column name for merging
            ns_df = stats_df[stats_df['is_non_striker_out'] == 1].copy()
            if not ns_df.empty:
                # Replace 'batter' with 'non_striker' in grp_cols for this calculation
                ns_grp_cols = [c if c != 'batter' else 'non_striker' for c in grp_cols]
                ns_outs = ns_df.groupby(ns_grp_cols, observed=True).size()
                # Rename non_striker back to batter for merging
                ns_outs = ns_outs.rename_axis([c if c != 'non_striker' else 'batter' for c in ns_grp_cols])
            else:
                ns_outs = pd.Series(dtype=float, name='Outs')
        else:
            ns_outs = pd.Series(dtype=float, name='Outs')
        
        # Ensure both series have proper index for addition
        # Reset index to align for addition, then set back
        batter_outs_df = batter_outs.reset_index()
        batter_outs_df.columns = list(grp_cols) + ['is_batter_out']
        ns_outs_df = ns_outs.reset_index()
        
        # Merge on grouping columns to combine outs
        # Check that ns_outs_df has the required columns matching grp_cols
        if not ns_outs_df.empty and len(ns_outs_df.columns) > 1:
            # Rename columns to match grp_cols + 'Outs'
            ns_outs_df.columns = list(grp_cols) + ['ns_outs']
            # Check that all grp_cols exist in both DataFrames before merging
            if all(col in ns_outs_df.columns for col in grp_cols) and all(col in batter_outs_df.columns for col in grp_cols):
                combined = batter_outs_df.merge(ns_outs_df, on=grp_cols, how='outer', suffixes=('_batter', '_ns'))
                combined = combined.fillna(0)
                # Sum the two out columns
                combined['Outs'] = combined['is_batter_out'] + combined['ns_outs']
                outs = combined.set_index(grp_cols)['Outs']
            else:
                outs = batter_outs.rename('Outs')
        else:
            outs = batter_outs.rename('Outs')
    else:
        outs = pd.Series(0, index=runs.index, name='Outs')
    
    # InningsPlayed: Only count regular innings (exclude super over)
    # A batter who batted in both regular innings and super over of the same match = 1 innings
    if 'is_super_over' in stats_df.columns:
        regular_innings_df = stats_df[stats_df['is_super_over'] == 0]
        innings_played = regular_innings_df.groupby(grp_cols, observed=True)['match_id'].nunique().rename('InningsPlayed')
    else:
        innings_played = stats_df.groupby(grp_cols, observed=True)['match_id'].nunique().rename('InningsPlayed')
    
    # Build stats - only include seasons if available and aggregating
    series_to_concat = [runs, balls, fours, sixes, dots, outs, innings_played]
    
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
    stats['Outs'] = stats['Outs'].astype(int)
    stats['SR'] = (stats['Runs'] / stats['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    
    # Calculate Average: Runs / Outs. If Outs=0, use Runs/1 (or keep as infinity/0). 
    # Standard: If 0 outs, Avg is undefined. Here we will use Runs/1 to show the runs as average (or handle as inf).
    # Let's use standard replacement: if Outs > 0, Runs/Outs, else Runs (effectively Runs/1 for display or infinity).
    # Actually, let's stick to safe division. User asked for Runs / Times Dismissed.
    # If I just do Runs / Outs, for 0 outs it's inf. replaced by 0 is BAD for high scorers.
    # Better logic: if Outs == 0, Avg = Runs.
    stats['Avg'] = stats.apply(lambda x: x['Runs'] if x['Outs'] == 0 else x['Runs'] / x['Outs'], axis=1).round(2)
    stats['Dot%'] = (stats['Dots'] / stats['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
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
    elif no_team_filter:
        # Overall (No Team Filter) - aggregate by batter only
        stats['Innings'] = "Overall"
        # Get the most common team for each batter
        batter_teams = valid.groupby('batter', observed=True)['team'].agg(
            lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else 'Unknown'
        ).reset_index()
        batter_teams.columns = ['batter', 'Team']
        batter_teams['Team'] = batter_teams['Team'].astype(str)
        stats = stats.merge(batter_teams, on='batter', how='left')
        stats['Team'] = stats['Team'].astype(str).fillna('Unknown')
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
        # Per-innings mode: innings column is already a string ("Innings 1", "Innings 2", "BAT1-SO", etc.)
        stats['Innings'] = stats['innings']
        cols = ['Innings','batter','team','InningsPlayed','Runs','BF','SR','Avg','4s','6s','Dots','Dot%']
    
    return stats[cols].rename(columns={'team':'Team', 'InningsPlayed':'Inns'}).sort_values('Runs', ascending=False)

def key_bowling(df_, no_team_filter=False, aggregate_seasons=False, season_filter=None):
    g = df_.copy()
    if g.empty:
        return pd.DataFrame(columns=['Innings','Bowler','Team','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots'])

    # Exclude no-result matches (abandoned/rain) — official stats don't include these.
    # For no-result matches (winner=None), only exclude truncated innings (max over < 19).
    if 'winner' in g.columns:
        no_result_mask = g['winner'].isna()
        if no_result_mask.any():
            max_over_per_inn = g.groupby(['match_id', 'innings'], observed=True)['over'].transform('max')
            truncated = no_result_mask & (max_over_per_inn < 19)
            g = g[~truncated]
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
    # Also check if specific matches are selected - if so, we're NOT in overall mode
    selected_matches = st.session_state.get('matches', [])
    is_overall = (st.session_state.get('view_mode_selection') == "Overall (Season Leaderboard)") and len(selected_matches) == 0
    
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
        # Per-match mode: innings column is a string but needs BOWL prefix for bowling (BAT1-SO -> BOWL1-SO)
        dfb['Innings'] = dfb['innings'].replace({'BAT1-SO': 'BOWL1-SO', 'BAT2-SO': 'BOWL2-SO'})
        
    return dfb[['Innings','bowler',team_col,'InningsPlayed','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens','Dots']].rename(columns={'bowler':'Bowler', team_col:'Team', 'InningsPlayed':'Inns'}).sort_values('Wkts', ascending=False)

def bpsix(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter', observed=True).size().rename('Balls')
    sixes = valid[valid['runs.batter'] == 6].groupby('batter', observed=True).size().rename('Sixes')
    s = pd.concat([balls, sixes], axis=1).fillna(0)
    s['BPSix'] = s.apply(lambda r: round(r['Balls'] / r['Sixes'], 2) if r['Sixes'] > 0 else 0, axis=1)
    s = s.reset_index().rename(columns={'index':'batter'})
    # Always filter out batters with 0 sixes (0 BPSix)
    s = s[s['Sixes'] > 0]
    return s[['batter','Balls','Sixes','BPSix']].sort_values('BPSix')

def bp4(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter', observed=True).size().rename('Balls')
    fours = valid[valid['runs.batter'] == 4].groupby('batter', observed=True).size().rename('Fours')
    s = pd.concat([balls, fours], axis=1).fillna(0)
    s['BP4'] = s.apply(lambda r: round(r['Balls'] / r['Fours'], 2) if r['Fours'] > 0 else 0, axis=1)
    s = s.reset_index().rename(columns={'index':'batter'})
    # Always filter out batters with 0 fours (0 BP4)
    s = s[s['Fours'] > 0]
    return s[['batter','Balls','Fours','BP4']].sort_values('BP4')

def boundary_balls_pct(df_):
    valid = df_[df_['is_valid_delivery']==1]
    stats = valid.groupby('batter', observed=True).agg(
        Total_Runs=('runs.batter', 'sum'),
        Balls=('runs.batter', 'size')
    ).reset_index()
    # Runs from 4s and 6s
    fours = valid[valid['runs.batter']==4].groupby('batter', observed=True)['runs.batter'].sum().rename('Fours_Runs')
    sixes = valid[valid['runs.batter']==6].groupby('batter', observed=True)['runs.batter'].sum().rename('Sixes_Runs')
    stats = stats.merge(fours, on='batter', how='left').merge(sixes, on='batter', how='left')
    stats['Fours_Runs'] = stats['Fours_Runs'].fillna(0).astype(int)
    stats['Sixes_Runs'] = stats['Sixes_Runs'].fillna(0).astype(int)
    stats['Boundary_Runs'] = stats['Fours_Runs'] + stats['Sixes_Runs']
    stats['Boundary %'] = (stats['Boundary_Runs'] / stats['Total_Runs'] * 100).replace([np.inf, np.nan], 0).round(2)
    stats = stats[stats['Boundary %'] > 0]
    return stats[['batter','Balls','Total_Runs','Boundary_Runs','Boundary %']].sort_values('Boundary %', ascending=False)

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
    
    def extract_innings_num(val):
        if isinstance(val, (int, float)) and not pd.isna(val):
            return int(val)
        if isinstance(val, str):
            import re
            match = re.search(r'(\d+)', val)
            if match:
                return int(match.group(1))
        return 0
    
    death['innings_num'] = death['innings'].apply(extract_innings_num)
    pos['innings_num'] = pos['innings'].apply(extract_innings_num)
    death['batter'] = death['batter'].astype(str)
    pos['batter'] = pos['batter'].astype(str)

    merged = death.merge(pos, on=['match_id','innings_num','batter'], how='left', suffixes=('', '_pos'))
    merged['position'] = merged['position'].fillna(99).astype(int)
    
    # Group by match_id + teams for per-match granularity
    # (teams can play each other multiple times in a season)
    group_cols = ['match_id', 'teams'] if 'teams' in merged.columns else ['match_id', 'team']
    label_col = 'teams' if 'teams' in merged.columns else 'team'
    
    tot = merged.groupby(group_cols, observed=True)['runs.total'].sum().rename('DeathRuns').reset_index()
    pos7 = merged[merged['position'].between(7,11)].groupby(group_cols, observed=True)['runs.total'].sum().rename('Pos7-11Runs').reset_index()
    
    out = tot.merge(pos7, on=group_cols, how='left')
    out['Pos7-11Runs'] = out['Pos7-11Runs'].fillna(0)
    out['Death Wag %'] = (out['Pos7-11Runs'] / out['DeathRuns'] * 100).replace([np.inf, np.nan], 0).round(2)
    out = out.rename(columns={label_col: 'Teams'})
    
    # Add Date column
    if 'date' in merged.columns:
        date_map = merged.groupby('match_id')['date'].first()
        out['Date'] = out['match_id'].map(date_map)
        if pd.api.types.is_datetime64_any_dtype(out['Date']):
             out['Date'] = out['Date'].dt.date
    
    cols = ['Teams', 'Date', 'DeathRuns', 'Pos7-11Runs', 'Death Wag %'] if 'Date' in out.columns else ['Teams', 'DeathRuns', 'Pos7-11Runs', 'Death Wag %']
    return out[cols].sort_values('Death Wag %', ascending=False)

def match_up_dominance(df_, full_season_df=None):
    """Match-Up Dominance Score (MDS)
    
    Compares a batter's Strike Rate against a specific bowler
    vs their overall Season Strike Rate.
    
    MDS = SR vs Bowler - Season SR
    
    Positive MDS = Batter scores faster against this bowler than usual (dominates)
    Negative MDS = Batter scores slower against this bowler (struggles)
    
    Example: S Mandhana has Season SR of 153.25
    - vs Bowler A: SR 200 → MDS = +46.75 (dominates)
    - vs Bowler B: SR 100 → MDS = -53.25 (struggles)
    
    Balls Faced excludes wides only (no-balls count as balls faced).
    SeasonSR is always based on the full season data, not the filtered match.
    """
    # Use full season data for SeasonSR if provided, else fall back to df_
    season_src = full_season_df if full_season_df is not None else df_
    no_wides_season = season_src[season_src['wides'] == 0]
    
    season = no_wides_season.groupby('batter', observed=True).agg(
        Runs=('runs.batter','sum'),
        BF=('runs.batter','size')
    ).reset_index()
    season['SeasonSR'] = (season['Runs'] / season['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    
    # Match-up stats from filtered data
    no_wides = df_[df_['wides'] == 0]
    vs = no_wides.groupby(['batter','bowler'], observed=True).agg(
        Runs=('runs.batter','sum'),
        BF=('runs.batter','size')
    ).reset_index()
    vs['SR_vs_Bowler'] = (vs['Runs'] / vs['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    
    out = vs.merge(season[['batter','SeasonSR']], on='batter', how='left')
    out['MDS'] = (out['SR_vs_Bowler'] - out['SeasonSR']).round(2)
    out = out.rename(columns={'batter': 'Batter', 'bowler': 'Bowler'})
    return out[['Batter', 'Bowler', 'Runs', 'BF', 'SR_vs_Bowler', 'SeasonSR', 'MDS']].sort_values('MDS', ascending=False)

def dot_ball_pct_trend(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter', observed=True).size().rename('Balls')
    dots = valid[valid['runs.batter'] == 0].groupby('batter', observed=True).size().rename('Dots')
    s = pd.concat([balls, dots], axis=1).fillna(0)
    s['Dot %'] = (s['Dots'] / s['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'index':'batter'})
    # Filter out 0 dot %
    s = s[s['Dot %'] > 0]
    return s[['batter','Balls','Dots','Dot %']].sort_values('Dot %', ascending=False)

def bowler_boundary_leakage_by_phase(df_):
    out_rows = []
    df_['phase'] = df_['phase'].astype(str)
    for (phase, inn, bowler), g in df_.groupby(['phase','innings','bowler'], observed=True):
        # Fix: Exclude byes and leg byes from runs conceded by bowler
        if 'byes' not in g.columns: g['byes'] = 0
        if 'leg_byes' not in g.columns: g['leg_byes'] = 0
        
        runs_conceded = g['runs.total'].sum() - g['byes'].sum() - g['leg_byes'].sum()
        balls_bowled = g['is_valid_delivery'].sum()
        boundaries = g[g['runs.batter'].isin([4,6])]['runs.batter'].count()
        
        pct = (boundaries / runs_conceded * 100) if runs_conceded > 0 else 0
        overs = overs_from_balls(balls_bowled)
        
        # Handle inn which can be string ("Innings 1") or int (1)
        if isinstance(inn, str) and inn.startswith('Innings'):
            innings_label = inn
        else:
            try:
                innings_label = f"Innings {int(inn)}"
            except (ValueError, TypeError):
                innings_label = str(inn)
        out_rows.append({'phase': phase, 'Innings': innings_label, 'Bowler': bowler, 'Boundaries Conceded': boundaries, 'Phase Runs': runs_conceded, 'Overs': overs, 'Leakage %': round(pct,2)})
    if not out_rows: return pd.DataFrame()
    return pd.DataFrame(out_rows).sort_values(['phase','Leakage %'], ascending=[True,False])

def batter_contribution(df_):
    innings_total = df_.groupby(['match_id','innings'], observed=True)['runs.batter'].sum().rename('InningsRuns').reset_index()
    batter_runs = df_.groupby(['match_id','innings','batter'], observed=True)['runs.batter'].sum().rename('Runs').reset_index()
    merged = batter_runs.merge(innings_total, on=['match_id','innings'], how='left')
    merged['Contribution %'] = (merged['Runs'] / merged['InningsRuns'] * 100).replace([np.inf, np.nan], 0).round(2)
    # Handle innings which can be string ("Innings 1") or int (1)
    def format_innings(val):
        if isinstance(val, str) and val.startswith('Innings'):
            return val
        try:
            return f"Innings {int(val)}"
        except (ValueError, TypeError):
            return str(val)
    merged['Innings'] = merged['innings'].apply(format_innings)
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

# -------------------------
# NEW METRIC FUNCTIONS
# -------------------------

def over_wise_batting_analysis(df_):
    """Analyze batting performance in 2-over phases: 1-2, 3-4, ..., 19-20"""
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame()
    
    # Create over phase labels (1-2, 3-4, ..., 19-20)
    def get_over_phase(over):
        # over is 0-indexed in parquet, so over 0 = ball 1st over
        over_num = int(over) + 1  # Convert to 1-indexed
        if over_num <= 2: return "1-2"
        elif over_num <= 4: return "3-4"
        elif over_num <= 6: return "5-6"
        elif over_num <= 8: return "7-8"
        elif over_num <= 10: return "9-10"
        elif over_num <= 12: return "11-12"
        elif over_num <= 14: return "13-14"
        elif over_num <= 16: return "15-16"
        elif over_num <= 18: return "17-18"
        else: return "19-20"
    
    valid['over_phase'] = valid['over'].apply(get_over_phase)
    
    # Group by match, innings, and over phase
    stats = valid.groupby(['match_id', 'innings', 'over_phase', 'team', 'teams', 'date'], observed=True).agg(
        Runs=('runs.total', 'sum'),
        Batter_Runs=('runs.batter', 'sum'),
        Balls=('is_valid_delivery', 'sum'),
        Fours=('runs.batter', lambda x: (x == 4).sum()),
        Sixes=('runs.batter', lambda x: (x == 6).sum()),
        Dots=('runs.batter', lambda x: (x == 0).sum())
    ).reset_index()
    
    stats['Extras'] = stats['Runs'] - stats['Batter_Runs']
    stats['SR'] = (stats['Batter_Runs'] / stats['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    stats['Boundaries'] = stats['Fours'] + stats['Sixes']
    
    # Sort by over phase order
    phase_order = ["1-2", "3-4", "5-6", "7-8", "9-10", "11-12", "13-14", "15-16", "17-18", "19-20"]
    stats['phase_order'] = stats['over_phase'].apply(lambda x: phase_order.index(x) if x in phase_order else 99)
    stats = stats.sort_values(['match_id', 'innings', 'phase_order'])
    
    stats['Team'] = stats['team'].astype(str)
    stats['Match'] = stats['teams'].astype(str)
    stats['Date'] = pd.to_datetime(stats['date']).dt.date
    stats['Innings'] = stats['innings'].apply(lambda x: f"Innings {x}" if isinstance(x, (int, float)) else str(x))
    
    return stats[['Match', 'Date', 'Team', 'Innings', 'over_phase', 'Runs', 'Batter_Runs', 'Extras', 'Balls', 'SR', 'Fours', 'Sixes', 'Boundaries', 'Dots']].rename(columns={'over_phase': 'Over Phase'})


def death_over_bowling_analysis(df_):
    """Analyze bowler performance in death overs (17-20)"""
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame()
    
    # Filter to overs 17-20 (0-indexed: 16-19)
    death_overs = valid[valid['over'].isin([16, 17, 18, 19])].copy()
    if death_overs.empty:
        return pd.DataFrame()
    
    # Calculate bowler runs (exclude byes/leg-byes)
    if 'byes' not in death_overs.columns: death_overs['byes'] = 0
    if 'leg_byes' not in death_overs.columns: death_overs['leg_byes'] = 0
    death_overs['runs_to_bowler'] = death_overs['runs.total'] - death_overs['byes'] - death_overs['leg_byes']
    death_overs['over_display'] = death_overs['over'] + 1  # 1-indexed for display
    
    # Use bowling_team for proper team association
    team_col = 'bowling_team' if 'bowling_team' in death_overs.columns else 'team'
    
    # Group by bowler and specific over
    stats = death_overs.groupby(['bowler', team_col, 'over_display'], observed=True).agg(
        Overs_Bowled=('match_id', 'nunique'),
        Runs=('runs_to_bowler', 'sum'),
        Balls=('is_valid_delivery', 'sum'),
        Wickets=('wicket_count', 'sum'),
        Dots=('runs_to_bowler', lambda x: (x == 0).sum())
    ).reset_index()
    
    stats['Economy'] = (stats['Runs'] / (stats['Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
    stats['Dot%'] = (stats['Dots'] / stats['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    
    stats['Bowler'] = stats['bowler'].astype(str)
    stats['Team'] = stats[team_col].astype(str)
    stats['Over'] = stats['over_display'].astype(int)
    
    return stats[['Bowler', 'Team', 'Over', 'Overs_Bowled', 'Balls', 'Runs', 'Wickets', 'Economy', 'Dot%']].sort_values(
        ['Over', 'Economy'], ascending=[True, True]
    )


def match_by_match_analysis(df_):
    """Match-by-match analysis with both batting and bowling stats"""
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # BATTING STATS
    batting = valid.groupby(['match_id', 'teams', 'date', 'innings', 'batter', 'team'], observed=True).agg(
        Runs=('runs.batter', 'sum'),
        Balls=('is_valid_delivery', 'sum'),
        Fours=('runs.batter', lambda x: (x == 4).sum()),
        Sixes=('runs.batter', lambda x: (x == 6).sum())
    ).reset_index()
    batting['SR'] = (batting['Runs'] / batting['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    batting['Batter'] = batting['batter'].astype(str)
    batting['Team'] = batting['team'].astype(str)
    batting['Match'] = batting['teams'].astype(str)
    batting['Date'] = pd.to_datetime(batting['date']).dt.date
    batting['Innings'] = batting['innings'].apply(lambda x: f"Inns {x}" if isinstance(x, (int, float)) else str(x))
    batting = batting[['Match', 'Date', 'Innings', 'Batter', 'Team', 'Runs', 'Balls', 'Fours', 'Sixes', 'SR']].sort_values(['Date', 'Match', 'Innings', 'Runs'], ascending=[False, True, True, False])
    
    # BOWLING STATS
    if 'byes' not in valid.columns: valid['byes'] = 0
    if 'leg_byes' not in valid.columns: valid['leg_byes'] = 0
    valid['runs_to_bowler'] = valid['runs.total'] - valid['byes'] - valid['leg_byes']
    
    team_col = 'bowling_team' if 'bowling_team' in valid.columns else 'team'
    
    bowling = valid.groupby(['match_id', 'teams', 'date', 'innings', 'bowler', team_col], observed=True).agg(
        Runs=('runs_to_bowler', 'sum'),
        Balls=('is_valid_delivery', 'sum'),
        Wickets=('wicket_count', 'sum')
    ).reset_index()
    bowling['Overs'] = bowling['Balls'].apply(overs_from_balls)
    bowling['Economy'] = (bowling['Runs'] / (bowling['Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
    bowling['Average'] = bowling.apply(lambda x: round(x['Runs'] / x['Wickets'], 2) if x['Wickets'] > 0 else 0, axis=1)
    bowling['Balls_Per_Wicket'] = bowling.apply(lambda x: round(x['Balls'] / x['Wickets'], 2) if x['Wickets'] > 0 else 0, axis=1)
    bowling['Bowler'] = bowling['bowler'].astype(str)
    bowling['Team'] = bowling[team_col].astype(str)
    bowling['Match'] = bowling['teams'].astype(str)
    bowling['Date'] = pd.to_datetime(bowling['date']).dt.date
    bowling['Innings'] = bowling['innings'].apply(lambda x: f"Inns {x}" if isinstance(x, (int, float)) else str(x))
    bowling = bowling[['Match', 'Date', 'Innings', 'Bowler', 'Team', 'Overs', 'Balls', 'Runs', 'Wickets', 'Economy', 'Average', 'Balls_Per_Wicket']].sort_values(['Date', 'Match', 'Innings', 'Wickets'], ascending=[False, True, True, False])
    
    return batting, bowling


def batter_vs_bowler_matchup(df_, min_balls=0):
    """Head-to-head statistics between batters and bowlers"""
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame()
    
    # Exclude super overs
    valid = valid[valid['innings'].isin([1, 2])]
    if valid.empty:
        return pd.DataFrame()
    
    # Calculate matchup stats
    matchup_stats = valid.groupby(['batter', 'bowler', 'team', 'bowling_team'], observed=True).agg(
        Runs=('runs.batter', 'sum'),
        Balls=('is_valid_delivery', 'sum'),
        Dismissals=('wicket_count', 'sum'),
        Innings=('match_id', 'nunique')
    ).reset_index()
    
    # Filter by minimum balls
    matchup_stats = matchup_stats[matchup_stats['Balls'] >= min_balls]
    
    if matchup_stats.empty:
        return pd.DataFrame()
    
    matchup_stats['SR'] = (matchup_stats['Runs'] / matchup_stats['Balls'] * 100).round(2)
    matchup_stats['Avg'] = matchup_stats.apply(
        lambda x: round(x['Runs'] / x['Dismissals'], 2) if x['Dismissals'] > 0 else x['Runs'], axis=1
    )
    
    matchup_stats['Batter'] = matchup_stats['batter'].astype(str)
    matchup_stats['Bowler'] = matchup_stats['bowler'].astype(str)
    matchup_stats['Batting_Team'] = matchup_stats['team'].astype(str)
    matchup_stats['Bowling_Team'] = matchup_stats['bowling_team'].astype(str)
    
    return matchup_stats[['Batter', 'Batting_Team', 'Bowler', 'Bowling_Team', 'Innings', 'Runs', 'Balls', 'SR', 'Dismissals', 'Avg']].sort_values('Runs', ascending=False)

# ─────────── NEW COACH / ANALYST METRICS ───────────



def batting_acceleration_rate(df_):
    """Batting Acceleration Rate (BAR) — SR shift from Powerplay → Death.
    
    BAR = Death_SR - Powerplay_SR
    
    - Positive BAR: batter accelerates (low-risk early, explosive late) → No. 4/5 roles.
    - Negative BAR: batter decelerates (PP specialist, struggles at death) → Opener.
    - Near-Zero BAR: "The Engine" — consistent tempo regardless of phase → No. 3 anchor.
    
    Scouting Labels (Player DNA):
    - BAR > 20       → "The Finisher"
    - 5 < BAR ≤ 20   → "Moderate Finisher"
    - -10 ≤ BAR ≤ 5  → "The Engine"
    - BAR < -10      → "PP Specialist"
    """
    valid = df_[df_['is_valid_delivery'] == 1].copy()
    if valid.empty:
        return pd.DataFrame()

    phase_sr = valid.groupby(['batter', 'phase'], observed=True).agg(
        Runs=('runs.batter', 'sum'),
        Balls=('is_valid_delivery', 'sum')
    ).reset_index()
    phase_sr['SR'] = (phase_sr['Runs'] / phase_sr['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)

    # FIX 1: Use NaN fill (not 0) so missing phases don't corrupt the BAR formula
    pivot = phase_sr.pivot_table(index='batter', columns='phase', values='SR', fill_value=np.nan)

    # Convert index to plain strings to avoid categorical index causing merge issues
    pivot.index = pivot.index.astype(str)
    pivot.columns.name = None

    result = pd.DataFrame({'Batter': pivot.index.tolist()})
    for col in ['Powerplay', 'Middle', 'Death']:
        result[f'{col}_SR'] = pivot[col].values if col in pivot.columns else np.nan

    # Get balls per phase for filtering
    balls_pivot = phase_sr.pivot_table(index='batter', columns='phase', values='Balls', fill_value=0)
    balls_pivot.index = balls_pivot.index.astype(str)
    balls_pivot.columns.name = None
    for col in ['Powerplay', 'Middle', 'Death']:
        result[f'{col}_Balls'] = balls_pivot[col].values if col in balls_pivot.columns else 0

    result['Total_Balls'] = result['Powerplay_Balls'] + result['Middle_Balls'] + result['Death_Balls']

    # FIX 2: Add innings count per batter and enforce minimum of 5 innings
    innings_count = valid.groupby('batter', observed=True)['match_id'].nunique().rename('Innings_Count')
    innings_count_df = innings_count.reset_index()
    innings_count_df['batter'] = innings_count_df['batter'].astype(str)
    innings_count_df = innings_count_df.rename(columns={'batter': 'Batter'})
    result = result.merge(innings_count_df, on='Batter', how='left')
    result['Innings_Count'] = result['Innings_Count'].fillna(0).astype(int)

    # Context-aware thresholds: relax minimums for small datasets (single match / few matches)
    # Triggers either via the Specific Matches mode selector, OR when data covers ≤5 matches
    unique_match_count = valid['match_id'].nunique()
    is_specific_matches = (
        (st.session_state.get('view_mode_selection') == "Specific Matches" and
         len(st.session_state.get('matches', [])) > 0) or
        unique_match_count <= 5
    )
    min_innings = 1 if is_specific_matches else 5
    min_balls   = 1 if is_specific_matches else 6
    min_total   = 2 if is_specific_matches else 20

    # require both Powerplay AND Death balls (BAR is meaningless without both)
    result = result[
        (result['Powerplay_Balls'] >= min_balls) &
        (result['Death_Balls'] >= min_balls) &
        (result['Total_Balls'] >= min_total) &
        (result['Innings_Count'] >= min_innings)
    ]

    # Acceleration = Death SR - Powerplay SR (NaN-safe: both phases are guaranteed present now)
    result['Acceleration'] = (result['Death_SR'] - result['Powerplay_SR']).round(2)

    # Fill display SR with 0 only for Middle (optional phase)
    result['Middle_SR'] = result['Middle_SR'].fillna(0)

    # FIX 3: Fixed label gap — 5 < BAR ≤ 20 is now "Moderate Finisher", not "Balanced"
    def label(bar):
        if bar > 20:   return 'The Finisher'
        elif bar > 5:  return 'Moderate Finisher'
        elif bar >= -10: return 'The Engine'
        else:          return 'PP Specialist'
    result['Scouting_Label'] = result['Acceleration'].apply(label)

    return result[['Batter', 'Innings_Count', 'Powerplay_SR', 'Middle_SR', 'Death_SR', 'Acceleration',
                    'Scouting_Label', 'Powerplay_Balls', 'Middle_Balls', 'Death_Balls',
                    'Total_Balls']].sort_values('Acceleration', ascending=False)


def bowling_spell_efficiency(df_):
    """Bowling Spell Efficiency — a bowler's continuous stint (overs within gap ≤ 2)."""
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame()

    spells = []
    for (mid, inn), g in valid.groupby(['match_id', 'innings'], observed=True):
        teams_str = g['teams'].iloc[0] if 'teams' in g.columns else ''
        date_val = g['date'].iloc[0] if 'date' in g.columns else None

        # Get all overs each bowler bowled in this innings
        bowler_overs = g.groupby('bowler', observed=True)['over'].apply(lambda x: sorted(x.unique())).to_dict()

        for bowler, overs_list in bowler_overs.items():
            if len(overs_list) < 2:
                continue

            # Split into spells: gap > 2 between consecutive overs = new spell
            spell_groups = [[overs_list[0]]]
            for k in range(1, len(overs_list)):
                if overs_list[k] - overs_list[k-1] <= 2:
                    spell_groups[-1].append(overs_list[k])
                else:
                    spell_groups.append([overs_list[k]])

            for spell_overs in spell_groups:
                if len(spell_overs) < 2:
                    continue

                spell_data = g[(g['bowler'] == bowler) & (g['over'].isin(spell_overs))]
                byes_val = spell_data['byes'].sum() if 'byes' in spell_data.columns else 0
                lb_val = spell_data['leg_byes'].sum() if 'leg_byes' in spell_data.columns else 0
                runs = spell_data['runs.total'].sum() - byes_val - lb_val
                balls = spell_data['is_valid_delivery'].sum()
                wkts = spell_data['wicket_count'].sum()
                dots = (spell_data['runs.total'] == 0).sum()
                economy = (runs / (balls / 6)) if balls > 0 else 0

                spells.append({
                    'Match': str(teams_str),
                    'Date': date_val,
                    'Innings': str(inn),
                    'Bowler': str(bowler),
                    'Spell_Overs': f"{spell_overs[0]+1}-{spell_overs[-1]+1}",
                    'Overs': len(spell_overs),
                    'Balls': balls,
                    'Runs': runs,
                    'Wickets': wkts,
                    'Dots': dots,
                    'Economy': round(economy, 2),
                    'Dot_Pct': round(dots / balls * 100, 1) if balls > 0 else 0
                })

    if not spells:
        return pd.DataFrame()

    out = pd.DataFrame(spells)
    if 'Date' in out.columns:
        out['Date'] = pd.to_datetime(out['Date']).dt.date
    return out.sort_values('Economy', ascending=True)


def collapse_detector(df_):
    """Collapse Detector — identify 3+ wickets within 20 balls."""
    valid = df_.copy()
    if valid.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    collapses = []

    for (mid, inn), g in valid.groupby(['match_id', 'innings'], observed=True):
        g = g.sort_values('ball_float')
        teams_str = g['teams'].iloc[0] if 'teams' in g.columns else ''
        date_val = g['date'].iloc[0] if 'date' in g.columns else None
        batting_team = g['team'].iloc[0] if 'team' in g.columns else ''

        # Find wicket deliveries
        wkt_rows = g[g['wicket_count'] > 0].copy()
        if len(wkt_rows) < 3:
            continue

        wkt_indices = wkt_rows.index.tolist()
        wkt_balls = wkt_rows['ball_float'].values

        # Sliding window: check every window of 3+ consecutive wickets
        i = 0
        while i <= len(wkt_balls) - 3:
            # Find how many wickets fall within 20 balls of the first
            j = i + 2  # at least 3 wickets
            while j < len(wkt_balls):
                # Count total deliveries between first and last wicket
                window_start = wkt_balls[i]
                window_end = wkt_balls[j]
                deliveries_in_window = len(g[(g['ball_float'] >= window_start) & (g['ball_float'] <= window_end)])
                if deliveries_in_window <= 24:  # ~4 overs worth
                    j += 1
                else:
                    break
            j -= 1  # last valid position

            num_wkts = j - i + 1
            if num_wkts >= 3:
                window_start = wkt_balls[i]
                window_end = wkt_balls[j]
                window_data = g[(g['ball_float'] >= window_start) & (g['ball_float'] <= window_end)]
                runs_lost = window_data['runs.total'].sum()
                balls_span = len(window_data)
                overs_span = f"{int(window_start)+1}.{int((window_start % 1)*6)+1} - {int(window_end)+1}.{int((window_end % 1)*6)+1}"

                # Bowlers involved
                bowlers = window_data[window_data['wicket_count'] > 0]['bowler'].unique()

                collapses.append({
                    'Match': str(teams_str),
                    'Date': date_val,
                    'Innings': str(inn),
                    'Team': str(batting_team),
                    'Wickets': num_wkts,
                    'Runs_Lost': runs_lost,
                    'Balls': balls_span,
                    'Over_Range': overs_span,
                    'Bowlers': ', '.join(str(b) for b in bowlers),
                    'match_id': mid
                })
                i = j + 1  # skip to next window
            else:
                i += 1

    if not collapses:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    coll_df = pd.DataFrame(collapses)
    if 'Date' in coll_df.columns:
        coll_df['Date'] = pd.to_datetime(coll_df['Date']).dt.date

    # All collapses
    all_collapses = coll_df[['Match', 'Date', 'Innings', 'Team', 'Wickets', 'Runs_Lost', 'Balls', 'Over_Range', 'Bowlers']].sort_values('Wickets', ascending=False)

    # Teams most prone to collapses
    teams_prone = coll_df.groupby('Team', observed=True).agg(
        Collapses=('match_id', 'count'),
        Total_Wkts_Lost=('Wickets', 'sum'),
        Avg_Runs_Lost=('Runs_Lost', 'mean')
    ).reset_index().sort_values('Collapses', ascending=False)
    teams_prone['Avg_Runs_Lost'] = teams_prone['Avg_Runs_Lost'].round(1)

    # Bowler triggers
    bowler_list = []
    for _, row in coll_df.iterrows():
        for b in row['Bowlers'].split(', '):
            bowler_list.append({'Bowler': b.strip(), 'Collapses_Triggered': 1})
    if bowler_list:
        bowler_triggers = pd.DataFrame(bowler_list).groupby('Bowler').sum().reset_index().sort_values('Collapses_Triggered', ascending=False)
    else:
        bowler_triggers = pd.DataFrame()

    return all_collapses, teams_prone, bowler_triggers


def player_absence_impact(df_, xi_df=None):
    """
    Player Absence Impact (PAI) — Rigorous Statsguru-style implementation.
    Compares Team Performance WITH vs WITHOUT a player in the Playing XI.
    
    Data Source: 
    - Playing XI (playing_xi.parquet) for accurate "Played" counts.
    - Ball-by-ball for Team/Opponent scores and results.
    
    Constraints:
    - Excludes No Result / Abandoned matches.
    - Requires Min 5 Matches Played, Min 3 Matches Missed.
    """
    if df_.empty:
        return pd.DataFrame(), pd.DataFrame()

    # ── 1. Data Normalization ──
    df_ = df_.copy()
    # Normalize year to plain int
    df_['_year'] = pd.to_numeric(df_['year'].astype(str).str.split('/').str[0], errors='coerce').fillna(0).astype(int)
    # Normalize team names
    df_['_team'] = df_['team'].astype(str).replace(TEAM_ALIASES)
    df_['_winner'] = df_['winner'].astype(str).replace(TEAM_ALIASES)

    # ── 2. Prepare Playing XI ──
    if xi_df is not None and not xi_df.empty:
        leagues = df_['league'].astype(str).unique()
        xi = xi_df[xi_df['league'].isin(leagues)].copy()
        xi['_year'] = xi['year'].astype(int)
        xi['_team'] = xi['team'].astype(str).replace(TEAM_ALIASES)
    else:
        st.error("Playing XI data missing. Cannot compute PAI rigorously.")
        return pd.DataFrame(), pd.DataFrame()

    # ── 3. Build Match-Level Summary (The "Universe" of matches) ──
    # We need: MatchID, Date, Team, Opponent, Runs, Balls, Wickets, Result, OppRuns, OppBalls
    
    # Aggregations per Team per Match
    match_teams = df_.groupby(['match_id', '_team'], observed=True).agg(
        runs=('runs.total', 'sum'),
        balls=('is_valid_delivery', 'sum'),
        wickets=('wicket_count', 'sum'),
        date=('date', 'first'),
        year=('_year', 'first'),
        winner=('_winner', 'first')
    ).reset_index()

    # Filter out No Results (Winner is None/NaN/'No Result'/string 'None'/'nan')
    valid_matches = match_teams[
        match_teams['winner'].notna() & 
        (match_teams['winner'] != 'No Result') & 
        (match_teams['winner'] != '') &
        (match_teams['winner'] != 'None') &
        (match_teams['winner'] != 'nan')
    ].copy()
    
    valid_matches['won'] = (valid_matches['_team'] == valid_matches['winner']).astype(int)
    
    # Self-join to get Opponent stats
    # (Merge on MatchID where Team != Team)
    # Optimization: For each match, we have 2 rows. 
    # Opponent stats = Total Match Runs - Team Runs? No, that's unsafe if incomplete data.
    # Better: Join.
    
    match_summary = pd.merge(
        valid_matches, 
        valid_matches[['match_id', '_team', 'runs', 'balls', 'wickets']], 
        on='match_id', suffixes=('', '_opp')
    )
    match_summary = match_summary[match_summary['_team'] != match_summary['_team_opp']].copy()
    
    # Rename for clarity
    match_summary = match_summary.rename(columns={
        '_team': 'Team', '_team_opp': 'Opponent', 
        'runs': 'Runs', 'balls': 'Balls', 
        'runs_opp': 'Runs_Conceded', 'balls_opp': 'Balls_Bowled',
        'year': 'Season'
    })
    
    # Compute Run Rate & Econ (Match Level)
    match_summary['RR'] = match_summary['Runs'] / (match_summary['Balls'] / 6).replace(0, 1)
    match_summary['Econ'] = match_summary['Runs_Conceded'] / (match_summary['Balls_Bowled'] / 6).replace(0, 1)

    # ── 4. Pre-compute playing_xi match counts (for Mat/Missed, incl. No Result) ──
    # Get set of MatchIDs where Player was in XI
    xi['in_xi'] = True
    player_matches = xi.groupby(['player', '_team'])['match_id'].apply(set).to_dict()
    
    # Pre-compute total team matches per team per year from playing_xi
    # (This includes No Result matches — matching ESPNcricinfo counting)
    xi_team_matches = xi.groupby(['_team', '_year'])['match_id'].apply(set).to_dict()
    
    # Pre-filter: Only teams/seasons present in the filtered data
    unique_teams = match_summary['Team'].unique()
    # Also include teams only present in playing_xi (defunct teams with NR-only matches)
    xi_unique_teams = xi['_team'].unique()
    all_relevant_teams = set(unique_teams) | set(xi_unique_teams)
    
    impact_rows = []
    missed_Log = []
    # Track ALL player-team counts from playing_xi for All Teams aggregation
    xi_player_counts = {}  # {player: {team: {'mat': N, 'missed': N, 'years': set}}}

    # Get roster of players to analyze (all players in playing_xi for relevant leagues)
    roster = xi[['player', '_team']].drop_duplicates()
    
    for _, row in roster.iterrows():
        player = row['player']
        team = row['_team']
        
        # Getting active years for this player-team combo
        p_active_years = xi[(xi['player'] == player) & (xi['_team'] == team)]['_year'].unique()
        p_match_ids = player_matches.get((player, team), set())
        
        # ── Mat/Missed from playing_xi (includes No Result — matches ESPNcricinfo) ──
        xi_mat = len(p_match_ids)
        xi_team_total_ids = set()
        for yr in p_active_years:
            xi_team_total_ids |= xi_team_matches.get((team, yr), set())
        xi_missed = len(xi_team_total_ids) - xi_mat
        
        # Store for All Teams aggregation (even if team doesn't meet impact threshold)
        if player not in xi_player_counts:
            xi_player_counts[player] = {}
        xi_player_counts[player][team] = {
            'mat': xi_mat, 'missed': xi_missed, 'years': set(p_active_years)
        }
        
        # ── Impact metrics from valid matches only (excl. No Result) ──
        team_matches = match_summary[
            (match_summary['Team'] == team) & 
            (match_summary['Season'].isin(p_active_years))
        ].copy()
        
        if team_matches.empty: continue

        # Split into WITH vs WITHOUT
        with_df = team_matches[team_matches['match_id'].isin(p_match_ids)]
        without_df = team_matches[~team_matches['match_id'].isin(p_match_ids)]
        
        n_with_valid = len(with_df)
        n_without_valid = len(without_df)
        
        # Strict Constraints: Min 5 played, Min 3 missed (on valid matches for impact)
        if n_with_valid < 5 or n_without_valid < 3:
            continue
            
        # ── Compute Impact Metrics (from valid matches only) ──
        
        # 1. Win %
        win_pct_with = (with_df['won'].mean() * 100)
        win_pct_without = (without_df['won'].mean() * 100)
        
        # 2. Batting (Avg Score, RR)
        avg_score_with = with_df['Runs'].mean()
        avg_score_without = without_df['Runs'].mean()
        
        avg_rr_with = with_df['RR'].mean()
        avg_rr_without = without_df['RR'].mean()
        
        # 3. Bowling (Avg Opp Score, Team Economy)
        avg_opp_score_with = with_df['Runs_Conceded'].mean()
        avg_opp_score_without = without_df['Runs_Conceded'].mean()
        
        avg_econ_with = with_df['Econ'].mean()
        avg_econ_without = without_df['Econ'].mean()
        
        # ── Impact Score ──
        # Formula: Win% Δ + (RR Δ * 5)
        win_diff = win_pct_with - win_pct_without
        rr_diff = avg_rr_with - avg_rr_without
        impact_score = win_diff + (rr_diff * 5)
        
        impact_rows.append({
            'Player': player,
            'Team': team,
            'Seasons': f"{min(p_active_years)}-{max(p_active_years)}",
            # Mat/Missed from playing_xi (includes NR — matches ESPNcricinfo)
            'Mat': xi_mat,
            'Missed': xi_missed,
            # Impact metrics from valid matches only
            'Win% With': win_pct_with,
            'Win% WO': win_pct_without,
            'Impact Score': impact_score,
            'Score With': avg_score_with,
            'Score WO': avg_score_without,
            'RR With': avg_rr_with,
            'RR WO': avg_rr_without,
            'Opp Score With': avg_opp_score_with,
            'Opp Score WO': avg_opp_score_without,
            'Econ With': avg_econ_with,
            'Econ WO': avg_econ_without,
            'Win% Δ': win_diff,
            'RR Δ': rr_diff
        })
        
        # Log Missed Matches
        for _, m in without_df.iterrows():
            missed_Log.append({
                'Player': player,
                'Team': team,
                'Season': m['Season'],
                'Date': m['date'],
                'Opponent': m['Opponent'],
                'Result': 'Won' if m['won'] else 'Lost',
                'Team Score': f"{m['Runs']}/{m['wickets']} ({round(m['Balls']/6,1)} ov)",
                'Team RR': round(m['RR'], 2),
                'Opp Score': f"{m['Runs_Conceded']}",
            })

    # ── 5. Aggregate "All Teams" combined rows per player ──
    # Uses xi_player_counts (from playing_xi) for Mat/Missed — includes ALL teams
    # Uses impact_rows for impact metrics — only teams that passed the threshold
    if xi_player_counts:
        # Build index of impact_rows by player for quick lookup
        impact_by_player = {}
        for row in impact_rows:
            p = row['Player']
            if p not in impact_by_player:
                impact_by_player[p] = []
            impact_by_player[p].append(row)
        
        all_teams_rows = []
        for player, teams_data in xi_player_counts.items():
            if len(teams_data) < 2:
                continue  # Only add All Teams row if player played for 2+ teams
            
            # Mat/Missed from playing_xi — ALL teams, includes NR
            total_mat = sum(td['mat'] for td in teams_data.values())
            total_missed = sum(td['missed'] for td in teams_data.values())
            all_years = set()
            for td in teams_data.values():
                all_years |= td['years']
            all_team_names = sorted(teams_data.keys())
            
            # Impact metrics from qualifying teams only (those that passed threshold)
            qualifying_rows = impact_by_player.get(player, [])
            if qualifying_rows:
                q_mat = sum(r['Mat'] for r in qualifying_rows)
                q_missed = sum(r['Missed'] for r in qualifying_rows)
                w_win_with = sum(r['Win% With'] * r['Mat'] for r in qualifying_rows) / max(q_mat, 1)
                w_win_wo = sum(r['Win% WO'] * r['Missed'] for r in qualifying_rows) / max(q_missed, 1)
                w_score_with = sum(r['Score With'] * r['Mat'] for r in qualifying_rows) / max(q_mat, 1)
                w_score_wo = sum(r['Score WO'] * r['Missed'] for r in qualifying_rows) / max(q_missed, 1)
                w_rr_with = sum(r['RR With'] * r['Mat'] for r in qualifying_rows) / max(q_mat, 1)
                w_rr_wo = sum(r['RR WO'] * r['Missed'] for r in qualifying_rows) / max(q_missed, 1)
                w_opp_with = sum(r['Opp Score With'] * r['Mat'] for r in qualifying_rows) / max(q_mat, 1)
                w_opp_wo = sum(r['Opp Score WO'] * r['Missed'] for r in qualifying_rows) / max(q_missed, 1)
                w_econ_with = sum(r['Econ With'] * r['Mat'] for r in qualifying_rows) / max(q_mat, 1)
                w_econ_wo = sum(r['Econ WO'] * r['Missed'] for r in qualifying_rows) / max(q_missed, 1)
                win_diff = w_win_with - w_win_wo
                rr_diff = w_rr_with - w_rr_wo
                impact_score = win_diff + (rr_diff * 5)
            else:
                # No qualifying teams — show counts but no impact metrics
                w_win_with = w_win_wo = 0
                w_score_with = w_score_wo = 0
                w_rr_with = w_rr_wo = 0
                w_opp_with = w_opp_wo = 0
                w_econ_with = w_econ_wo = 0
                win_diff = rr_diff = impact_score = 0
            
            all_teams_rows.append({
                'Player': player,
                'Team': 'All Teams (' + ', '.join(all_team_names) + ')',
                'Seasons': f"{min(all_years)}-{max(all_years)}" if all_years else '',
                'Mat': total_mat,
                'Missed': total_missed,
                'Win% With': w_win_with,
                'Win% WO': w_win_wo,
                'Impact Score': impact_score,
                'Score With': w_score_with,
                'Score WO': w_score_wo,
                'RR With': w_rr_with,
                'RR WO': w_rr_wo,
                'Opp Score With': w_opp_with,
                'Opp Score WO': w_opp_wo,
                'Econ With': w_econ_with,
                'Econ WO': w_econ_wo,
                'Win% Δ': win_diff,
                'RR Δ': rr_diff
            })
        impact_rows.extend(all_teams_rows)

    # ── 6. Create DataFrames & UI ──
    if not impact_rows:
        st.warning("No players meet the minimum criteria (5 matches played, 3 missed) for the selected filters.")
        return pd.DataFrame(), pd.DataFrame()
        
    summary_df = pd.DataFrame(impact_rows).sort_values('Impact Score', ascending=False)
    missed_df = pd.DataFrame(missed_Log)
    
    # ── UI Construction ──
    
    # Explanation
    st.info("""
    **How to read this:**  
    * **Impact Score**: Composite metric combining Win% difference and Run Rate difference. positive = Team performs better WITH player.
    * **Min Sample**: Requires at least 5 matches played and 3 missed to ensure statistical relevance.
    * **No Results**: Washed out games are excluded.
    """)
    
    tab_overview, tab_bat, tab_bowl, tab_log = st.tabs([
        "📊 Impact Overview", "🏏 Batting Impact", "mw Bowling Impact", "📝 Missed Matches"
    ])
    
    with tab_overview:
        st.caption("Players sorted by overall positive impact on Team Results")
        disp_cols = ['Player', 'Team', 'Mat', 'Missed', 'Win% With', 'Win% WO', 'Win% Δ', 'Impact Score']
        
        # Formatting
        s_style = summary_df[disp_cols].style.format({
            'Win% With': '{:.1f}%', 'Win% WO': '{:.1f}%', 
            'Win% Δ': '{:+.1f}%', 'Impact Score': '{:+.1f}'
        }).background_gradient(subset=['Impact Score'], cmap='RdYlGn', vmin=-20, vmax=20)
        
        st.dataframe(s_style, width="stretch", height=500)
        
    with tab_bat:
        st.caption("Impact on Team Totals and Scoring Rate")
        bat_cols = ['Player', 'Team', 'Score With', 'Score WO', 'RR With', 'RR WO', 'RR Δ']
        
        b_style = summary_df[bat_cols].style.format({
            'Score With': '{:.1f}', 'Score WO': '{:.1f}',
            'RR With': '{:.2f}', 'RR WO': '{:.2f}', 'RR Δ': '{:+.2f}'
        }).background_gradient(subset=['RR Δ'], cmap='RdYlGn', vmin=-1.0, vmax=1.0)
        
        st.dataframe(b_style, width="stretch", height=500)
        
    with tab_bowl:
        st.caption("Impact on restricting Opponents (Lower Economy/Opp Score is better)")
        bowl_cols = ['Player', 'Team', 'Opp Score With', 'Opp Score WO', 'Econ With', 'Econ WO']
        
        # For bowling, lower is better, so reverse cmap usually, but let's just show raw first
        # Diff column for Econ would be nice
        summary_df['Econ Δ'] = summary_df['Econ With'] - summary_df['Econ WO'] 
        # Negative Econ Diff is GOOD (Team conceded less with player)
        
        bowl_cols_final = bowl_cols + ['Econ Δ']
        
        bo_style = summary_df[bowl_cols_final].style.format({
            'Opp Score With': '{:.1f}', 'Opp Score WO': '{:.1f}',
            'Econ With': '{:.2f}', 'Econ WO': '{:.2f}', 'Econ Δ': '{:+.2f}'
        }).background_gradient(subset=['Econ Δ'], cmap='RdYlGn_r', vmin=-1.0, vmax=1.0) # Red to Green reversed
        
        st.dataframe(bo_style, width="stretch", height=500)
        
    with tab_log:
        st.caption("Details of matches the team played WITHOUT the selected player")
        
        # Selector for player
        all_players = sorted(summary_df['Player'].unique())
        sel_player = st.selectbox("Select Player to view missed matches:", all_players)
        
        if sel_player:
            p_missed = missed_df[missed_df['Player'] == sel_player].sort_values('Date', ascending=False)
            st.dataframe(p_missed[['Date', 'Season', 'Team', 'Opponent', 'Result', 'Team Score', 'Team RR']], width="stretch")
            
    return summary_df, missed_df


# Colors
color_pool = px.colors.qualitative.Plotly + px.colors.qualitative.D3 + px.colors.qualitative.Set3

# Iterate metrics and display
for i, metric in enumerate(st.session_state['metrics']):
    color = color_pool[i % len(color_pool)]
    try:
        
        if metric == "Impact Player Performance":
            st.subheader("Impact Player Performance")
            if 'IPL' not in st.session_state.get('leagues', []) and 'IPL' not in fdf['league'].unique():
                st.info("Impact Players are primarily an IPL feature. Select IPL league to view.")
            else:
                res_bat, res_bowl, res_bat_match, res_bowl_match = calculate_impact_player_stats(fdf)

                # Tabbed view: Batting vs Bowling
                tab1, tab2 = st.tabs(["Batting Impact", "Bowling Impact"])

                with tab1:
                    if not res_bat.empty:
                        sub1, sub2, sub3 = st.tabs(["Overall", "Innings-wise", "All Matches (No Team Filter)"])

                        with sub1:
                            show_table(res_bat)
                            fig = px.bar(res_bat.head(10), x='batter', y='Runs',
                                        title="Top Impact Batsmen (Overall)", color='Strike Rate')
                            show_plotly_chart(fig)

                        with sub2:
                            if not res_bat_match.empty and 'Innings' in res_bat_match.columns:
                                innings_list = sorted(res_bat_match['Innings'].unique())
                                inn_tabs = st.tabs([str(inn) for inn in innings_list])
                                for inn_tab, inn_label in zip(inn_tabs, innings_list):
                                    with inn_tab:
                                        inn_data = res_bat_match[res_bat_match['Innings'] == inn_label].drop(columns='Innings')
                                        show_table(inn_data)
                                        if not inn_data.empty and 'Batter' in inn_data.columns:
                                            fig = px.bar(inn_data.head(10), x='Batter', y='Runs',
                                                        title=f"Top Impact Batsmen — {inn_label}",
                                                        color='SR')
                                            show_plotly_chart(fig)
                            else:
                                st.info("No innings-wise match data available.")

                        with sub3:
                            # All match appearances combined — no innings split, no team filtering applied
                            if not res_bat_match.empty:
                                show_table(res_bat_match)
                                if 'Batter' in res_bat_match.columns:
                                    agg_no_filter = res_bat_match.groupby('Batter', as_index=False).agg(
                                        Appearances=('Runs', 'count'),
                                        Total_Runs=('Runs', 'sum'),
                                        Total_Balls=('Balls', 'sum'),
                                        Total_Fours=('Fours', 'sum'),
                                        Total_Sixes=('Sixes', 'sum')
                                    )
                                    agg_no_filter['SR'] = (agg_no_filter['Total_Runs'] / agg_no_filter['Total_Balls'] * 100).round(2)
                                    agg_no_filter = agg_no_filter.sort_values('Total_Runs', ascending=False)
                                    st.markdown("**Aggregate (all innings combined)**")
                                    show_table(agg_no_filter)
                                    fig = px.bar(agg_no_filter.head(10), x='Batter', y='Total_Runs',
                                                title="Impact Batsmen — All Appearances (No Team Filter)",
                                                color='SR')
                                    show_plotly_chart(fig)
                            else:
                                st.info("No match data available.")
                    else:
                        st.info("No Impact Batters found in selected data.")

                with tab2:
                    if not res_bowl.empty:
                        sub4, sub5, sub6 = st.tabs(["Overall", "Innings-wise", "All Matches (No Team Filter)"])

                        with sub4:
                            show_table(res_bowl)
                            fig = px.bar(res_bowl.head(10), x='bowler', y='Wickets',
                                        title="Top Impact Bowlers (Overall)", color='Economy')
                            show_plotly_chart(fig)

                        with sub5:
                            if not res_bowl_match.empty and 'Innings' in res_bowl_match.columns:
                                innings_list_b = sorted(res_bowl_match['Innings'].unique())
                                inn_tabs_b = st.tabs([str(inn) for inn in innings_list_b])
                                for inn_tab_b, inn_label_b in zip(inn_tabs_b, innings_list_b):
                                    with inn_tab_b:
                                        inn_data_b = res_bowl_match[res_bowl_match['Innings'] == inn_label_b].drop(columns='Innings')
                                        show_table(inn_data_b)
                                        if not inn_data_b.empty and 'Bowler' in inn_data_b.columns:
                                            fig = px.bar(inn_data_b.head(10), x='Bowler', y='Wickets',
                                                        title=f"Top Impact Bowlers — {inn_label_b}",
                                                        color='Economy')
                                            show_plotly_chart(fig)
                            else:
                                st.info("No innings-wise match data available.")

                        with sub6:
                            # All match appearances combined — no innings split, no team filtering applied
                            if not res_bowl_match.empty:
                                show_table(res_bowl_match)
                                if 'Bowler' in res_bowl_match.columns:
                                    agg_b_no_filter = res_bowl_match.groupby('Bowler', as_index=False).agg(
                                        Appearances=('Wickets', 'count'),
                                        Total_Wickets=('Wickets', 'sum'),
                                        Total_Runs=('Runs_Conceded', 'sum'),
                                        Total_Balls=('Overs', 'count')
                                    )
                                    agg_b_no_filter['Economy'] = (
                                        agg_b_no_filter['Total_Runs'] /
                                        res_bowl_match.groupby('Bowler')['Overs'].apply(
                                            lambda x: sum(
                                                int(str(o).split('.')[0]) + int(str(o).split('.')[1]) / 6
                                                if '.' in str(o) else int(str(o))
                                                for o in x
                                            )
                                        ).reindex(agg_b_no_filter['Bowler']).values
                                    ).round(2)
                                    agg_b_no_filter = agg_b_no_filter.sort_values('Total_Wickets', ascending=False)
                                    st.markdown("**Aggregate (all innings combined)**")
                                    show_table(agg_b_no_filter)
                                    fig = px.bar(agg_b_no_filter.head(10), x='Bowler', y='Total_Wickets',
                                                title="Impact Bowlers — All Appearances (No Team Filter)",
                                                color='Economy')
                                    show_plotly_chart(fig)
                            else:
                                st.info("No match data available.")
                    else:
                        st.info("No Impact Bowlers found in selected data.")

        elif metric == "Score Prediction (Next Match)":
            st.subheader("Form Guide & Score Projection")
            st.markdown("""
            **What it shows:** Comprehensive batter form analysis with projected next score.

            | Column | Meaning |
            |--------|---------|
            | **Inn** | Total innings played |
            | **Season Avg** | Average runs per innings this season |
            | **Last 5** | Scores in last 5 innings |
            | **Projected** | Weighted projection (recent form has higher weight) |
            | **Consistency (σ)** | Standard deviation — lower = more consistent |
            | **High** | Highest score this season |
            | **50+ / 30+** | Number of 50+ and 30+ scores |
            | **Form** | 📈 Rising / 📉 Dipping / ➡️ Steady |
            """)
            if not st.session_state.get('batters'):
                st.info("Select specific batters from the sidebar to see form analysis.")
            else:
                dfm = predict_next_score(fdf, st.session_state['batters'])
                show_table(dfm, metric)
                # Trend Graph
                if not dfm.empty:
                    trend_data = fdf[fdf['batter'].isin(st.session_state['batters'])].groupby(['date', 'batter'], observed=True)['runs.batter'].sum().reset_index()
                    fig = px.line(trend_data, x='date', y='runs.batter', color='batter', markers=True, title="Innings-by-Innings Form Trend")
                    fig.update_layout(yaxis_title='Runs', xaxis_title='Date')
                    show_plotly_chart(fig)

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
            
            # Toggle for Overall (No Team Filter) view
            col1, col2 = st.columns([3, 1])
            with col2:
                overall_batting = st.checkbox("📊 Overall (No Team Filter)", key="overall_batting_toggle", 
                                             help="Aggregate batter stats across all teams")
            
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
                        dfm = key_batting(fdf, no_team_filter=overall_batting, aggregate_seasons=False, season_filter=available_seasons[idx])
                        st.markdown(f"**Season: {available_seasons[idx]}**")
                        show_table(dfm, metric)
                        show_bar(dfm.head(50), 'batter', 'Runs', f"Top Batting Runs", color=color)
            else:
                # Normal view
                dfm = key_batting(fdf, no_team_filter=overall_batting, aggregate_seasons=False)
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
            st.markdown("**What it shows:** Out of every 100 balls a batter faces, how many go for **a 4 or a 6**. Higher % = more aggressive batter.")
            render_with_season_tabs(fdf, boundary_balls_pct, metric, 'batter', 'Boundary %', "Boundary % by Batter", color)
        elif metric == "Powerplay Boundary Rate":
            st.subheader("Powerplay Boundary Rate")
            st.write("Team boundary rate (boundaries per legal ball) inside mandatory powerplay")
            render_with_season_tabs(fdf, powerplay_boundary_rate, metric, 'Team', 'PPBR (%)', "Powerplay Boundary Rate (%) — aggregated per team", color)
        elif metric == "Death Wag %":
            st.subheader("Death Wag %")
            st.markdown("""
            **What it shows:** Of all runs scored in the **Death phase** (overs 17-20), what % came from **lower-order batters** (position 7-11)?  
            - **DeathRuns** = Total runs in death overs (17-20) for that match.  
            - **Pos7-11Runs** = Runs scored by batters at positions 7-11 during death overs.  
            - **Death Wag %** = Pos7-11Runs ÷ DeathRuns × 100  
            
            > **Note:** The Death phase in the data covers **overs 17-20** (not 16-20). Over 16 is classified as Middle phase.  
            """)
            render_with_season_tabs(fdf, death_wag_pct, metric, 'Teams', 'Death Wag %', "Death Wag % aggregated by team", color)
        elif metric == "Match-Up Dominance":
            st.subheader("Match-Up Dominance")
            st.markdown("""
            **What it shows:** How much better or worse a batter performs against a specific bowler, compared to their overall season strike rate.  
            
            **Formula:** MDS = SR vs Bowler − Season SR  
            
            - **Positive MDS** → Batter scores **faster** against this bowler than usual (batter dominates).  
            - **Negative MDS** → Batter scores **slower** against this bowler (bowler dominates).  
            - **SR vs Bowler** = Strike Rate of batter when facing that specific bowler.  
            - **Season SR** = Batter's overall Strike Rate across the season.  
            
            > **Benefit:** Helps coaches identify favourable and unfavourable match-ups. For example, if a batter has MDS = +50 against a bowler, it signals the batting team should target that bowler. Conversely, MDS = −50 means the bowling captain should use that bowler against the batter.  
            """)
            render_with_season_tabs(fdf, match_up_dominance, metric, 'Batter', 'MDS', "Match-Up Dominance Score (sample)", color, top_n=50, metric_func_kwargs={'full_season_df': p_df})
        elif metric == "Dot Ball % Trend":
            st.subheader("Dot Ball % Trend")
            st.write("Dot-ball percentage per batter (legal deliveries only)")
            render_with_season_tabs(fdf, dot_ball_pct_trend, metric, 'batter', 'Dot %', "Dot % Trend by Batter", color)
        elif metric == "Bowler Boundary Leakage by Phase":
            st.subheader("Bowler Boundary Leakage by Phase")
            st.write("Boundaries conceded by bowlers grouped by phase (Powerplay/Death/etc)")
            
            # Add toggle for Overall view (aggregating across innings)
            is_overall_leakage = st.checkbox("Show Overall (Aggregate Innings)", value=False, key="bbl_overall")
            
            if is_overall_leakage:
                # Recalculate from raw data directly (not from pre-computed DataFrame)
                df_to_use = fdf.copy()
                if 'byes' not in df_to_use.columns: df_to_use['byes'] = 0
                if 'leg_byes' not in df_to_use.columns: df_to_use['leg_byes'] = 0
                
                df_to_use['runs_to_bowler'] = df_to_use['runs.total'] - df_to_use['byes'] - df_to_use['leg_byes']
                df_to_use['phase'] = df_to_use['phase'].astype(str)
                
                agg = df_to_use.groupby(['phase', 'bowler'], observed=True).agg(
                    Runs=('runs_to_bowler', 'sum'),
                    Balls=('is_valid_delivery', 'sum'),
                    Boundaries=('runs.batter', lambda x: x.isin([4,6]).sum())
                ).reset_index()
                
                agg['Leakage %'] = (agg['Boundaries'] / agg['Runs'] * 100).replace([np.inf, np.nan], 0).round(2)
                agg['Overs'] = agg['Balls'].apply(overs_from_balls)
                agg = agg.rename(columns={'bowler': 'Bowler', 'Boundaries': 'Boundaries Conceded', 'Runs': 'Phase Runs'})
                agg = agg.sort_values(['phase', 'Leakage %'], ascending=[True, False])
                
                show_table(agg, metric)
                # Filter out 0 stats for graph
                agg_graph = agg[agg['Boundaries Conceded'] > 0]
                show_bar(agg_graph.head(30), 'Bowler', 'Leakage %', "Bowler Boundary Leakage (Overall)", color)
            else:
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
        
        # -------------------------
        # NEW METRICS RENDERING
        # -------------------------
        elif metric == "Over-wise Batting Analysis":
            st.subheader("Over-wise Batting Analysis")
            st.write("Batting performance broken down by 2-over phases (1-2, 3-4, ..., 19-20)")
            
            tab1, tab2 = st.tabs(["Match-by-Match", "Aggregate by Phase"])
            
            with tab1:
                dfm = over_wise_batting_analysis(fdf)
                if dfm is not None and not dfm.empty:
                    show_table(dfm, metric)
                else:
                    st.info("No over-wise data available.")
            
            with tab2:
                # Aggregate across all matches by over phase
                valid = fdf.copy()
                if not valid.empty:
                    def get_over_phase(over):
                        over_num = int(over) + 1
                        if over_num <= 2: return "1-2"
                        elif over_num <= 4: return "3-4"
                        elif over_num <= 6: return "5-6"
                        elif over_num <= 8: return "7-8"
                        elif over_num <= 10: return "9-10"
                        elif over_num <= 12: return "11-12"
                        elif over_num <= 14: return "13-14"
                        elif over_num <= 16: return "15-16"
                        elif over_num <= 18: return "17-18"
                        else: return "19-20"
                    
                    valid['over_phase'] = valid['over'].apply(get_over_phase)
                    agg = valid.groupby('over_phase', observed=True).agg(
                        Total_Runs=('runs.total', 'sum'),    # Use runs.total to include extras
                        Batter_Runs=('runs.batter', 'sum'),
                        Total_Balls=('is_valid_delivery', 'sum'),
                        Fours=('runs.batter', lambda x: (x == 4).sum()),
                        Sixes=('runs.batter', lambda x: (x == 6).sum())
                    ).reset_index()
                    agg['SR'] = (agg['Batter_Runs'] / agg['Total_Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
                    agg['Extras'] = agg['Total_Runs'] - agg['Batter_Runs']
                    phase_order = ["1-2", "3-4", "5-6", "7-8", "9-10", "11-12", "13-14", "15-16", "17-18", "19-20"]
                    agg['order'] = agg['over_phase'].apply(lambda x: phase_order.index(x) if x in phase_order else 99)
                    agg = agg.sort_values('order').drop('order', axis=1)
                    show_table(agg.rename(columns={'over_phase': 'Over Phase'}), metric)
                    
                    fig = px.bar(agg, x='over_phase', y='Total_Runs', color='SR',
                                color_continuous_scale='RdYlGn', title="Total Runs by Over Phase (incl. extras)")
                    show_plotly_chart(fig)
            
        
        elif metric == "Death Over Bowling Analysis":
            st.subheader("Death Over Bowling Analysis (Overs 17-20)")
            st.write("Identify bowlers who keep runs down in the crucial death overs")
            
            tab1, tab2 = st.tabs(["By Specific Over", "Best Death Bowlers"])
            
            with tab1:
                dfm = death_over_bowling_analysis(fdf)
                if dfm is not None and not dfm.empty:
                    over_filter = st.multiselect("Filter by Over", [17, 18, 19, 20], default=[17, 18, 19, 20], key="death_over_filter")
                    filtered = dfm[dfm['Over'].isin(over_filter)]
                    show_table(filtered, metric)
                    
                    if not filtered.empty:
                        fig = px.bar(filtered.head(30), x='Bowler', y='Economy', color='Over',
                                    title="Death Over Economy by Bowler", barmode='group')
                        fig.update_xaxes(tickangle=45)
                        show_plotly_chart(fig)
                else:
                    st.info("No death over data available.")
            
            with tab2:
                # Aggregate across all death overs
                dfm = death_over_bowling_analysis(fdf)
                if dfm is not None and not dfm.empty:
                    agg = dfm.groupby(['Bowler', 'Team'], observed=True).agg(
                        Total_Overs=('Overs_Bowled', 'sum'),
                        Total_Balls=('Balls', 'sum'),
                        Total_Runs=('Runs', 'sum'),
                        Total_Wickets=('Wickets', 'sum')
                    ).reset_index()
                    agg['Economy'] = (agg['Total_Runs'] / (agg['Total_Balls'] / 6)).round(2)
                    agg = agg[agg['Total_Balls'] >= 12]  # Min 2 overs
                    agg = agg.sort_values('Economy')
                    
                    st.markdown("### Best Death Bowlers (Min 2 overs, sorted by Economy)")
                    show_table(agg.head(30), metric)
                    
                    if not agg.empty:
                        fig = px.bar(agg.head(15), x='Bowler', y='Economy', color='Total_Wickets',
                                    title="Top 15 Best Death Bowlers by Economy",
                                    color_continuous_scale='RdYlGn_r')
                        fig.update_xaxes(tickangle=45)
                        show_plotly_chart(fig)
        
        elif metric == "Match by Match Analysis":
            st.subheader("Match by Match Analysis")
            st.write("Complete batting and bowling stats for each match")
            
            tab1, tab2 = st.tabs(["Batting", "Bowling"])
            
            batting_df, bowling_df = match_by_match_analysis(fdf)
            
            with tab1:
                if batting_df is not None and not batting_df.empty:
                    st.markdown("### Batting Performance")
                    show_table(batting_df, metric)
                    
                    # Top scorers chart
                    top_batters = batting_df.groupby('Batter', observed=True)['Runs'].sum().reset_index().sort_values('Runs', ascending=False).head(10)
                    if not top_batters.empty:
                        fig = px.bar(top_batters, x='Batter', y='Runs', title="Top 10 Run Scorers", color='Runs', color_continuous_scale='Blues')
                        show_plotly_chart(fig)
                else:
                    st.info("No batting data available.")
            
            with tab2:
                if bowling_df is not None and not bowling_df.empty:
                    st.markdown("### Bowling Performance")
                    st.markdown("**Columns:** Overs Bowled, Balls, Wickets, Economy, Average, Balls Per Wicket")
                    show_table(bowling_df, metric)
                    
                    # Top wicket takers chart
                    top_bowlers = bowling_df.groupby('Bowler', observed=True)['Wickets'].sum().reset_index().sort_values('Wickets', ascending=False).head(10)
                    if not top_bowlers.empty:
                        fig = px.bar(top_bowlers, x='Bowler', y='Wickets', title="Top 10 Wicket Takers", color='Wickets', color_continuous_scale='Reds')
                        show_plotly_chart(fig)
                else:
                    st.info("No bowling data available.")
        
        elif metric == "Batter vs Bowler Matchups":
            st.subheader("Batter vs Bowler Matchups")
            st.write("Head-to-head statistics between batters and bowlers")
            st.caption("💡 **Tip:** Select a Batter AND Bowler from the left sidebar to see their head-to-head matchup directly.")
            
            # Check if user has selected specific batter(s) and bowler(s) from sidebar
            sidebar_batters = st.session_state.get('batters', [])
            sidebar_bowlers = st.session_state.get('bowlers', [])
            
            if sidebar_batters and sidebar_bowlers:
                # Direct matchup mode — show head-to-head for sidebar selections
                for sb in sidebar_batters:
                    for sw in sidebar_bowlers:
                        matchup_balls = p_df[(p_df['batter'] == sb) & (p_df['bowler'] == sw)]
                        if matchup_balls.empty:
                            st.info(f"No matchup data found between {sb} and {sw}.")
                            continue
                        
                        no_wides = matchup_balls[matchup_balls['wides'] == 0]
                        
                        st.markdown(f"### 🏏 {sb} vs 🎯 {sw}")
                        total_runs = int(no_wides['runs.batter'].sum())
                        total_balls = len(no_wides)
                        total_innings = no_wides['match_id'].nunique()
                        dismissals = int(no_wides[no_wides['is_batter_out'] == 1]['wicket_count'].sum()) if 'is_batter_out' in no_wides.columns else 0
                        sr = round(total_runs / total_balls * 100, 2) if total_balls > 0 else 0
                        avg = round(total_runs / dismissals, 2) if dismissals > 0 else total_runs
                        dots = int((no_wides['runs.batter'] == 0).sum())
                        fours = int((no_wides['runs.batter'] == 4).sum())
                        sixes = int((no_wides['runs.batter'] == 6).sum())
                        
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Innings", total_innings)
                        c2.metric("Runs", total_runs)
                        c3.metric("Balls", total_balls)
                        c4.metric("SR", sr)
                        
                        c5, c6, c7, c8 = st.columns(4)
                        c5.metric("Dismissals", dismissals)
                        c6.metric("Average", avg)
                        c7.metric("4s | 6s", f"{fours} | {sixes}")
                        c8.metric("Dot %", f"{round(dots/total_balls*100, 1)}%" if total_balls > 0 else "0%")
                        
                        # Year-by-year
                        st.markdown("#### Year-by-Year Breakdown")
                        yearly = no_wides.groupby('year', observed=True).agg(
                            Innings=('match_id', 'nunique'),
                            Runs=('runs.batter', 'sum'),
                            Balls=('runs.batter', 'size'),
                        ).reset_index()
                        if 'is_batter_out' in no_wides.columns:
                            yearly_wkts = no_wides[no_wides['is_batter_out'] == 1].groupby('year', observed=True)['wicket_count'].sum().reset_index()
                            yearly_wkts.columns = ['year', 'Dismissals']
                            yearly = yearly.merge(yearly_wkts, on='year', how='left')
                            yearly['Dismissals'] = yearly['Dismissals'].fillna(0).astype(int)
                        else:
                            yearly['Dismissals'] = 0
                        yearly['SR'] = (yearly['Runs'] / yearly['Balls'] * 100).round(2)
                        yearly['Avg'] = yearly.apply(lambda x: round(x['Runs']/x['Dismissals'], 2) if x['Dismissals'] > 0 else x['Runs'], axis=1)
                        yearly = yearly.rename(columns={'year': 'Year'}).sort_values('Year')
                        show_table(yearly, "Year-by-Year Matchup")
                        
                        if len(yearly) > 1:
                            fig = px.bar(yearly, x='Year', y='Runs', color='SR',
                                        color_continuous_scale='RdYlGn',
                                        title=f"{sb} vs {sw} — Runs by Year", text='Runs')
                            fig.update_layout(xaxis_type='category')
                            show_plotly_chart(fig)
                        st.markdown("---")
            else:
                # Leaderboard mode — show tabs
                dfm = batter_vs_bowler_matchup(fdf, min_balls=0)
            
                tab1, tab2, tab3 = st.tabs(["Batter Dominant", "Bowler Dominant", "Search"])
                
                with tab1:
                    if dfm is not None and not dfm.empty:
                        st.markdown("### Batters who dominate specific bowlers")
                        st.caption("High runs scored, no/few dismissals")
                        batter_dom = dfm[dfm['Dismissals'] == 0].sort_values('Runs', ascending=False).head(30)
                        if batter_dom.empty:
                            batter_dom = dfm.sort_values(['Runs', 'SR'], ascending=[False, False]).head(30)
                            st.caption("(Showing top run scorers)")
                        show_table(batter_dom, metric)
                        
                        if not batter_dom.empty:
                            batter_dom = batter_dom.copy()
                            batter_dom['Matchup'] = batter_dom['Batter'] + ' vs ' + batter_dom['Bowler']
                            fig = px.bar(batter_dom.head(15), x='Matchup', y='Runs', color='SR',
                                        color_continuous_scale='RdYlGn', title="Top Batter-Dominant Matchups")
                            fig.update_xaxes(tickangle=45)
                            show_plotly_chart(fig)
                    else:
                        st.info("No matchup data for current filters.")
                
                with tab2:
                    if dfm is not None and not dfm.empty:
                        st.markdown("### Bowlers who dominate specific batters")
                        st.caption("Multiple dismissals of the same batter")
                        bowler_dom = dfm[dfm['Dismissals'] >= 2].sort_values(['Dismissals', 'Avg'], ascending=[False, True]).head(30)
                        if bowler_dom.empty:
                            st.info("No bowler has dismissed the same batter 2+ times")
                        else:
                            show_table(bowler_dom, metric)
                            
                            bowler_dom = bowler_dom.copy()
                            bowler_dom['Matchup'] = bowler_dom['Bowler'] + ' vs ' + bowler_dom['Batter']
                            fig = px.bar(bowler_dom.head(15), x='Matchup', y='Dismissals', color='Avg',
                                        color_continuous_scale='RdYlGn_r', title="Top Bowler-Dominant Matchups")
                            fig.update_xaxes(tickangle=45)
                            show_plotly_chart(fig)
                    else:
                        st.info("No matchup data for current filters.")
                
                with tab3:
                    st.markdown("### Search for specific matchup")
                    st.caption("Shows overall stats + year-by-year breakdown")
                    col1, col2 = st.columns(2)
                    with col1:
                        all_batters_search = sorted(str(b) for b in p_df['batter'].dropna().unique())
                        search_batter = st.selectbox("Select Batter", [""] + all_batters_search, key="matchup_search_batter")
                    with col2:
                        all_bowlers_search = sorted(str(b) for b in p_df['bowler'].dropna().unique())
                        search_bowler = st.selectbox("Select Bowler", [""] + all_bowlers_search, key="matchup_search_bowler")
                    
                    if search_batter and search_bowler:
                        matchup_balls = p_df[(p_df['batter'] == search_batter) & (p_df['bowler'] == search_bowler)]
                        
                        if matchup_balls.empty:
                            st.info(f"No matchup data found between {search_batter} and {search_bowler} in the selected league.")
                        else:
                            no_wides = matchup_balls[matchup_balls['wides'] == 0]
                            
                            st.markdown("---")
                            st.markdown(f"### Overall: {search_batter} vs {search_bowler}")
                            total_runs = int(no_wides['runs.batter'].sum())
                            total_balls = len(no_wides)
                            total_innings = no_wides['match_id'].nunique()
                            dismissals = int(no_wides[(no_wides['is_batter_out'] == 1)]['wicket_count'].sum()) if 'is_batter_out' in no_wides.columns else 0
                            sr = round(total_runs / total_balls * 100, 2) if total_balls > 0 else 0
                            avg = round(total_runs / dismissals, 2) if dismissals > 0 else total_runs
                            dots = int(no_wides[no_wides['runs.batter'] == 0].shape[0])
                            fours = int(no_wides[no_wides['runs.batter'] == 4].shape[0])
                            sixes = int(no_wides[no_wides['runs.batter'] == 6].shape[0])
                            
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("Innings", total_innings)
                            c2.metric("Runs", total_runs)
                            c3.metric("Balls", total_balls)
                            c4.metric("SR", sr)
                            
                            c5, c6, c7, c8 = st.columns(4)
                            c5.metric("Dismissals", dismissals)
                            c6.metric("Average", avg)
                            c7.metric("4s | 6s", f"{fours} | {sixes}")
                            c8.metric("Dot %", f"{round(dots/total_balls*100, 1)}%" if total_balls > 0 else "0%")
                            
                            st.markdown("---")
                            st.markdown("### Year-by-Year Breakdown")
                            yearly = no_wides.groupby('year', observed=True).agg(
                                Innings=('match_id', 'nunique'),
                                Runs=('runs.batter', 'sum'),
                                Balls=('runs.batter', 'size'),
                            ).reset_index()
                            if 'is_batter_out' in no_wides.columns:
                                yearly_wkts = no_wides[no_wides['is_batter_out'] == 1].groupby('year', observed=True)['wicket_count'].sum().reset_index()
                                yearly_wkts.columns = ['year', 'Dismissals']
                                yearly = yearly.merge(yearly_wkts, on='year', how='left')
                                yearly['Dismissals'] = yearly['Dismissals'].fillna(0).astype(int)
                            else:
                                yearly['Dismissals'] = 0
                            yearly['SR'] = (yearly['Runs'] / yearly['Balls'] * 100).round(2)
                            yearly['Avg'] = yearly.apply(lambda x: round(x['Runs']/x['Dismissals'], 2) if x['Dismissals'] > 0 else x['Runs'], axis=1)
                            yearly = yearly.rename(columns={'year': 'Year'}).sort_values('Year')
                            show_table(yearly, "Year-by-Year Matchup")
                            
                            if len(yearly) > 1:
                                fig = px.bar(yearly, x='Year', y='Runs', color='SR',
                                            color_continuous_scale='RdYlGn',
                                            title=f"{search_batter} vs {search_bowler} — Runs by Year",
                                            text='Runs')
                                fig.update_layout(xaxis_type='category')
                                show_plotly_chart(fig)
                    
                    elif search_batter or search_bowler:
                        search_data = batter_vs_bowler_matchup(p_df, min_balls=0)
                        if search_data is not None and not search_data.empty:
                            if search_batter:
                                search_result = search_data[search_data['Batter'] == search_batter].sort_values('Runs', ascending=False)
                            else:
                                search_result = search_data[search_data['Bowler'] == search_bowler].sort_values('Runs', ascending=False)
                            
                            if search_result.empty:
                                st.info(f"No matchup data found for {'batter ' + search_batter if search_batter else 'bowler ' + search_bowler} in the selected league.")
                            else:
                                st.markdown(f"### All matchups for {'🏏 ' + search_batter if search_batter else '🎯 ' + search_bowler}")
                                show_table(search_result.head(50), metric)
                        else:
                            st.info("No matchup data available.")
        
        elif metric == "Batting Acceleration Rate":
            st.subheader("Batting Acceleration Rate (BAR)")
            with st.expander("What is this metric?", expanded=False):
                st.markdown("""
**Simple version:** This shows whether a batter speeds up or slows down as the innings progresses.

**BAR = Death Overs SR minus Powerplay SR.** A positive number means the batter finishes stronger than they start.

- **The Finisher** (BAR > +20): Starts slow, explodes at the death — ideal at No. 4/5.
- **Moderate Finisher** (BAR +5 to +20): Consistently gears up — versatile middle-order option.
- **The Engine** (BAR -10 to +5): Same tempo throughout — reliable No. 3 anchor.
- **PP Specialist** (BAR < -10): Dominates the Powerplay but struggles at death — best as opener.

**Best Phase** shows which phase the batter has the highest Strike Rate in, so even a batter with BAR near 0 but a 180 SR in middle overs won't be overlooked.

**Works in two modes:**
- **Single match / Specific Matches:** Select a match from the sidebar and BAR shows every batter who faced balls in both the Powerplay and Death overs of that match — great for post-match role analysis.
- **Season / Overall:** Requires ≥5 innings, ≥6 Powerplay balls and ≥6 Death balls per batter — filters out cameos and shows only players with an established role over the season.
                """)
            st.caption("Displays how much a batter shifted gears. Positive means they finished stronger than they started.")
            
            dfm = batting_acceleration_rate(fdf)
            if dfm is not None and not dfm.empty:
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["Simplified View", "Player DNA", "Accelerators", "Decelerators", "Phase-wise SR"])
                
                with tab1:
                    st.markdown("### Simplified Mode")
                    simp = dfm.copy()
                    
                    # Strategy tag — aligned with fixed labels
                    def _bar_strategy(row):
                        if row['Acceleration'] > 20:
                            if row['Death_SR'] > 200: return 'Death Powerhouse'
                            else: return 'Finisher'
                        elif row['Acceleration'] > 5:
                            return 'Moderate Finisher'
                        elif row['Acceleration'] < -10:
                            return 'PP Blitzer'
                        else:
                            return 'Anchor'
                    simp['Strategy'] = simp.apply(_bar_strategy, axis=1)
                    
                    # Best Phase
                    def _best_phase(row):
                        phases = {'Powerplay': row['Powerplay_SR'], 'Middle': row['Middle_SR'], 'Death': row['Death_SR']}
                        best = max(phases, key=phases.get)
                        return f"{best} ({int(phases[best])} SR)"
                    simp['Best Phase'] = simp.apply(_best_phase, axis=1)
                    
                    # Max SR for highlighting
                    simp['Max SR'] = simp[['Powerplay_SR', 'Middle_SR', 'Death_SR']].max(axis=1).round(0).astype(int)
                    
                    # Visual pace bar (5 blocks)
                    def _pace_bar(acc):
                        if acc > 100: blocks = 5
                        elif acc > 50: blocks = 4
                        elif acc > 20: blocks = 3
                        elif acc > 0: blocks = 2
                        elif acc > -10: blocks = 1
                        else: blocks = 1
                        
                        sign = '+' if acc > 0 else ''
                        if acc > 20:
                            filled = '\U0001f7e9' * blocks + '\u2b1c' * (5 - blocks)
                        elif acc < -10:
                            filled = '\U0001f7e5' + '\u2b1c' * 4
                        else:
                            filled = '\U0001f7e8' * min(blocks, 2) + '\u2b1c' * (5 - min(blocks, 2))
                        
                        return f"{filled} {sign}{int(acc)}"
                    simp['Innings Pace'] = simp['Acceleration'].apply(_pace_bar)
                    
                    display = simp[['Batter', 'Innings_Count', 'Strategy', 'Innings Pace', 'Best Phase', 'Max SR']].reset_index(drop=True)
                    st.dataframe(display, width="stretch", hide_index=True,
                                height=min(len(display) * 38 + 40, st.session_state.compact_height))
                    
                    # Highlight the highest Max SR player
                    if not simp.empty:
                        top_tempo = simp.loc[simp['Max SR'].idxmax()]
                        st.markdown(f"**Highest Phase SR:** {top_tempo['Batter']} ({top_tempo['Max SR']} SR in {top_tempo['Best Phase'].split(' (')[0]})")
                
                with tab2:
                    st.markdown("### Player DNA")
                    dna_colors = {'The Finisher': '#22c55e', 'Moderate Finisher': '#86efac', 'The Engine': '#3b82f6', 'PP Specialist': '#f59e0b'}
                    for label_name in ['The Finisher', 'Moderate Finisher', 'The Engine', 'PP Specialist']:
                        subset = dfm[dfm['Scouting_Label'] == label_name]
                        if not subset.empty:
                            color_hex = dna_colors.get(label_name, '#94a3b8')
                            st.markdown(f"#### <span style='color:{color_hex}'>{label_name}</span> ({len(subset)} players)", unsafe_allow_html=True)
                            show_table(subset[['Batter', 'Innings_Count', 'Powerplay_SR', 'Death_SR', 'Acceleration', 'Scouting_Label']], metric)
                
                with tab3:
                    acc = dfm[dfm['Acceleration'] > 0].head(30)
                    if not acc.empty:
                        fig = px.bar(acc, x='Batter', y='Acceleration', color='Acceleration',
                                    color_continuous_scale='Greens', title="Top Accelerators (Death SR > Powerplay SR)")
                        fig.update_xaxes(tickangle=45)
                        show_plotly_chart(fig)
                    show_table(dfm[dfm['Acceleration'] > 0], metric)
                
                with tab4:
                    dec = dfm[dfm['Acceleration'] < 0].sort_values('Acceleration').head(30)
                    if not dec.empty:
                        fig = px.bar(dec, x='Batter', y='Acceleration', color='Acceleration',
                                    color_continuous_scale='Reds_r', title="Decelerators (Death SR < Powerplay SR)")
                        fig.update_xaxes(tickangle=45)
                        show_plotly_chart(fig)
                    show_table(dfm[dfm['Acceleration'] < 0].sort_values('Acceleration'), metric)
                
                with tab5:
                    show_table(dfm, metric)
                    # Grouped bar: PP SR, Mid SR, Death SR
                    melted = dfm.head(30).melt(id_vars='Batter', value_vars=['Powerplay_SR', 'Middle_SR', 'Death_SR'],
                                                var_name='Phase', value_name='SR')
                    melted['Phase'] = melted['Phase'].str.replace('_SR', '')
                    fig = px.bar(melted, x='Batter', y='SR', color='Phase', barmode='group',
                                title="Strike Rate by Phase (Top 30 by Acceleration)")
                    fig.update_xaxes(tickangle=45)
                    show_plotly_chart(fig)
            else:
                st.info(
                    "No BAR data for current filters. Possible reasons:\n"
                    "- **Single match / batter filter**: BAR needs a batter who faced balls in "
                    "**both Powerplay and Death** overs in the selected data. "
                    "A batter who came in after over 6 has no Powerplay balls and is excluded.\n"
                    "- **Season mode**: Requires ≥5 innings, ≥6 Powerplay balls and ≥6 Death balls per batter. "
                    "Try selecting fewer seasons or switching to Specific Matches mode."
                )
        
        elif metric == "Bowling Spell Efficiency":
            st.subheader("Bowling Spell Efficiency")
            st.markdown("""
            **What it shows:** Consecutive over blocks (2+ overs in a row) bowled by the same bowler, with economy, wickets, and dot ball % for each spell.
            
            **Why it matters for coaches and captains:**  
            - Shows whether a bowler is **more effective bowling in blocks** (e.g., 3 overs straight in the powerplay) vs split overs.  
            - **Low-economy spells with high dot %** = pressure-building spells that set up wickets for the other end.  
            - **Best/Worst spell comparison** reveals a bowler's consistency under different game situations.  
            
            > **Captaincy tip:** If a bowler's best spells are always in blocks of 3, give them a continuous block in the powerplay rather than splitting 1-over slots.  
            """)
            
            dfm = bowling_spell_efficiency(fdf)
            if dfm is not None and not dfm.empty:
                tab1, tab2, tab3 = st.tabs(["Best Spells", "Worst Spells", "Bowler Summary"])
                
                with tab1:
                    # Split at median economy to prevent same spell appearing in both tabs
                    median_econ = dfm['Economy'].median()
                    best = dfm[dfm['Economy'] <= median_econ].sort_values('Economy').head(30)
                    show_table(best, metric)
                    if not best.empty:
                        fig = px.bar(best, x='Bowler', y='Economy', color='Wickets',
                                    color_continuous_scale='Greens_r', title="Most Economical Spells")
                        fig.update_xaxes(tickangle=45)
                        show_plotly_chart(fig)
                
                with tab2:
                    median_econ = dfm['Economy'].median()
                    worst = dfm[dfm['Economy'] > median_econ].sort_values('Economy', ascending=False).head(30)
                    show_table(worst, metric)
                    if not worst.empty:
                        fig = px.bar(worst, x='Bowler', y='Economy', color='Wickets',
                                    color_continuous_scale='Reds', title="Most Expensive Spells")
                        fig.update_xaxes(tickangle=45)
                        show_plotly_chart(fig)
                
                with tab3:
                    # Summarize per bowler: avg economy, total spells, total wickets
                    summary = dfm.groupby('Bowler').agg(
                        Total_Spells=('Overs', 'count'),
                        Avg_Economy=('Economy', 'mean'),
                        Total_Wickets=('Wickets', 'sum'),
                        Avg_Dot_Pct=('Dot_Pct', 'mean'),
                        Total_Overs=('Overs', 'sum')
                    ).reset_index()
                    summary['Avg_Economy'] = summary['Avg_Economy'].round(2)
                    summary['Avg_Dot_Pct'] = summary['Avg_Dot_Pct'].round(1)
                    summary = summary.sort_values('Avg_Economy')
                    show_table(summary, metric)
            else:
                st.info("No spell data available.")
        
        elif metric == "Collapse Detector":
            st.subheader("Collapse Detector")
            st.markdown("""
            **What it shows:** Identifies batting collapses — **3 or more wickets falling within approximately 4 overs** (24 balls).
            
            **Why it matters for coaches:**  
            - **Teams Prone tab** reveals which batting line-ups crumble under pressure — these teams need stabilizing anchors in the middle order.  
            - **Bowler Triggers tab** shows which bowlers (or combinations) cause the most collapses — these bowlers are your "wicket-cluster" specialists.  
            - Analyzing collapse patterns helps design **batting orders that are collapse-resistant** (e.g., not clustering similar-style batters together).  
            
            > **Match-day insight:** If the opposition is collapse-prone, attack with your best "trigger" bowler in a sustained spell to force a domino effect.  
            """)
            
            all_collapses, teams_prone, bowler_triggers = collapse_detector(fdf)
            tab1, tab2, tab3 = st.tabs(["All Collapses", "Teams Prone", "Bowler Triggers"])
            
            with tab1:
                if not all_collapses.empty:
                    show_table(all_collapses, metric)
                    st.metric("Total Collapses Detected", len(all_collapses))
                else:
                    st.info("No collapses detected with current filters.")
            
            with tab2:
                if not teams_prone.empty:
                    show_table(teams_prone, metric)
                    fig = px.bar(teams_prone, x='Team', y='Collapses', color='Avg_Runs_Lost',
                                color_continuous_scale='Reds', title="Teams Most Prone to Collapses")
                    fig.update_xaxes(tickangle=45)
                    show_plotly_chart(fig)
                else:
                    st.info("No collapse team data.")
            
            with tab3:
                if not bowler_triggers.empty:
                    show_table(bowler_triggers, metric)
                    fig = px.bar(bowler_triggers.head(20), x='Bowler', y='Collapses_Triggered',
                                title="Top Collapse-Triggering Bowlers", color='Collapses_Triggered',
                                color_continuous_scale='YlOrRd')
                    fig.update_xaxes(tickangle=45)
                    show_plotly_chart(fig)
                else:
                    st.info("No bowler trigger data.")

        elif metric == "Player Absence Impact":
            st.subheader("Player Absence Impact")
            st.warning("🚧 **Under Development** — This metric is still being refined. Data may be incomplete.")
            st.markdown("""
            **What it shows:** How much does a team suffer when a key player is missing?  
            
            Compares team performance in matches **WITH** vs **WITHOUT** a specific player:
            - **Win% Δ** — How much does the team's win rate drop without this player?  
            - **Avg Score With/Without** — Does the team score fewer runs overall?  
            - **Avg RR With/Without** — Does the batting run rate change?  
            - **Impact Score** — Combined metric: Win%Δ + (Run Rate Δ × 5). Higher = more impactful player.  
            
            > **Coaching Value:** Helps identify irreplaceable players. If a player has Impact Score of +30,  
            > the team wins significantly more and scores faster with them. Useful for retention decisions,  
            > workload management, and planning backup strategies.  
            
            ⚠️ *Requires data where a player has missed at least 1 match across the selected filters.*
            """)
            
            player_absence_impact(fdf, xi_df=playing_xi_df)
        
        else:
            st.write(f"**{metric}** - Coming soon")
    except Exception as e:
        st.error(f"Error computing {metric}: {e}")