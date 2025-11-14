# app.py (full file) - Updated: per-over RR fix + Run Source option + removed deliveries debug
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

st.set_page_config(page_title="T20 Stats", layout="wide")

st.markdown("""
**By Vishwesh Gaur**  
[Twitter: @iumvishwesh](https://twitter.com/iumvishwesh) | [LinkedIn: vishwesh-gaur-56760b112](https://www.linkedin.com/in/vishwesh-gaur-56760b112)  
""")

st.markdown("📅 Last updated: 2025-10-24")
st.markdown("⏰ Fresh Matches Will Appear as per Data Availability from Cricsheet")

st.markdown("# Global T20 Dashboard: MBBL, WBBL, SA20 & WPL Insights")

DATA_SOURCE = "t20_data.parquet"

# show league start dates (informational)
LEAGUE_START_DATES = {
    'WBBL': '2020-10-25',
    'MBBL': '2020-12-10',
    'WPL':  '2023-03-04',
    'SA20': '2023-01-10'
}
st.markdown("**Data included from:**")
for lg, dt in LEAGUE_START_DATES.items():
    st.markdown(f"- **{lg}** from **{dt}**")

# default compact height; slider in sidebar allows user to change
DEFAULT_COMPACT_HEIGHT = 250

@st.cache_data
def load_data(path=DATA_SOURCE):
    try:
        df = pd.read_parquet(path)
        # defensive normalization
        if 'phase' in df.columns:
            df['phase'] = df['phase'].astype(str).str.strip().apply(lambda x: x.title().replace('Power Play','Powerplay'))
            df['phase'] = df['phase'].replace({'Powersurge':'Power Surge','Power Surge':'Power Surge','Powerplay':'Powerplay'})
        # ensure date column exists as datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception as e:
        st.error(f"Data not found or failed to load: {e}")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

# session defaults initialization safety
if 'submitted' not in st.session_state: st.session_state.submitted = False
if 'compact_height' not in st.session_state: st.session_state.compact_height = DEFAULT_COMPACT_HEIGHT
if 'metrics' not in st.session_state: st.session_state.metrics = []

# initialize keys for match/batter/bowler (so sidebar widgets won't KeyError)
if 'matches' not in st.session_state: st.session_state.matches = []
if 'batters' not in st.session_state: st.session_state.batters = []
if 'bowlers' not in st.session_state: st.session_state.bowlers = []

def clear_submitted():
    st.session_state.submitted = False

# Sidebar: compact height slider (user asked)
st.sidebar.header("UI")
st.session_state.compact_height = st.sidebar.slider("Table height (px)", min_value=150, max_value=800, value=st.session_state.compact_height)

st.sidebar.markdown("---")
st.sidebar.header("Filters")

# LEAGUE / YEAR / DATE
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

# pre-filter to populate downstream selectors before submit
p_df = df.copy()
if st.session_state.get('leagues'): p_df = p_df[p_df['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): p_df = p_df[p_df['year'].isin(st.session_state['years'])]
if st.session_state.get('date_from'): p_df = p_df[p_df['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): p_df = p_df[p_df['date'].dt.date <= st.session_state['date_to']]

# Phases: include 'Power Surge' option only if present in data OR Big Bash leagues may still need explicit JSON
available_phases = sorted(p_df['phase'].dropna().unique())
if any(l in st.session_state.get('leagues', []) for l in ['WBBL', 'MBBL']):
    if 'Power Surge' not in available_phases:
        available_phases = list(available_phases) + ['Power Surge']
if not available_phases:
    available_phases = ['Powerplay','Power Surge','Middle','Death']

st.sidebar.multiselect("Phase", available_phases, key="phases", on_change=clear_submitted)

metrics = [
    "Key Batting", "Key Bowling", "BPSix", "BP4", "Batter Contribution %",
    "Extras Breakdown", "Run Rate Progression", "Boundary Balls %",
    "Powerplay Boundary Rate", "Death Wag %", "Match-Up Dominance",
    "Pressure Index", "Dot Ball % Trend", "Bowler Boundary Leakage by Phase", "Match Results"
]
st.sidebar.multiselect("Metrics", metrics, key="metrics", on_change=clear_submitted)

# --- NEW: populate Match / Batter / Bowler selectors based on current pre-filtered p_df (and phases if given)
# Use a phase-filtered df to ensure selections reflect chosen phases before SUBMIT
pp_df = p_df.copy()
if st.session_state.get('phases'):
    phases_norm = [p.title().replace('Power Play','Powerplay') for p in st.session_state['phases']]
    pp_df = pp_df[pp_df['phase'].isin(phases_norm)]

# Build match options from 'teams' column (Team A vs Team B). Fallback to match_id+date if missing.
if 'teams' in pp_df.columns and not pp_df['teams'].dropna().empty:
    match_options = sorted(pp_df['teams'].dropna().unique())
else:
    # fallback labels
    match_options = sorted(pp_df['match_id'].dropna().unique())

# Keep previous matches only if still available
valid_matches = [m for m in st.session_state.matches if m in match_options]
if valid_matches != st.session_state.matches:
    st.session_state.matches = valid_matches

st.sidebar.multiselect("Match", match_options, key="matches", default=st.session_state.matches, on_change=clear_submitted)

# Batters
if 'batter' in pp_df.columns:
    batter_options = sorted(pp_df['batter'].dropna().unique())
else:
    batter_options = []

valid_batters = [b for b in st.session_state.batters if b in batter_options]
if valid_batters != st.session_state.batters:
    st.session_state.batters = valid_batters

st.sidebar.multiselect("Batter", batter_options, key="batters", default=st.session_state.batters, on_change=clear_submitted)

# Bowlers
if 'bowler' in pp_df.columns:
    bowler_options = sorted(pp_df['bowler'].dropna().unique())
else:
    bowler_options = []

valid_bowlers = [b for b in st.session_state.bowlers if b in bowler_options]
if valid_bowlers != st.session_state.bowlers:
    st.session_state.bowlers = valid_bowlers

st.sidebar.multiselect("Bowler", bowler_options, key="bowlers", default=st.session_state.bowlers, on_change=clear_submitted)
# --- end new selectors

# Run Rate options (user wanted per-over default behaviour)
st.sidebar.markdown("---")
st.sidebar.markdown("### Run Rate options")
rr_mode = st.sidebar.radio("Run Rate View", ['Per-over (combined)', 'Per match', 'Per-match multi-run'], index=0)

# NEW: Run Source option (Batter runs only vs Total runs incl extras)
rr_run_source = st.sidebar.radio("Run Source for RR", ['Total runs (incl extras)','Batter runs only'], index=0)

selected_match_for_rr = None
if rr_mode in ('Per match','Per-match multi-run'):
    match_options_for_rr = sorted(p_df['teams'].unique())
    selected_match_for_rr = st.sidebar.selectbox("Select match for per-match RR", match_options_for_rr)

# SUBMIT
if st.sidebar.button("SUBMIT", type="primary"):
    st.session_state.submitted = True
    st.success("Applied!")

if not st.session_state.submitted:
    st.info("Choose filters. Match/Batter/Bowler populate before SUBMIT. Click SUBMIT to compute metrics.")
    st.stop()

# apply final filters
fdf = df.copy()
if st.session_state.get('leagues'): fdf = fdf[fdf['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): fdf = fdf[fdf['year'].isin(st.session_state['years'])]
if st.session_state.get('date_from'): fdf = fdf[fdf['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): fdf = fdf[fdf['date'].dt.date <= st.session_state['date_to']]
if st.session_state.get('phases'):
    phases_norm = [p.title().replace('Power Play','Powerplay') for p in st.session_state['phases']]
    fdf = fdf[fdf['phase'].isin(phases_norm)]
# Note: matches column named 'teams' (team A vs team B)
if st.session_state.get('matches'):
    fdf = fdf[fdf['teams'].isin(st.session_state['matches'])]
if st.session_state.get('batters'):
    fdf = fdf[fdf['batter'].isin(st.session_state['batters'])]
if st.session_state.get('bowlers'):
    fdf = fdf[fdf['bowler'].isin(st.session_state['bowlers'])]

if fdf.empty:
    st.warning("No data for selected filters.")
    st.stop()

# helpers
def overs_from_balls(balls):
    o = balls // 6
    b = balls % 6
    return f"{int(o)}.{int(b)}"

def compute_batting_positions(df_all):
    orders = []
    for (mid, inn), g in df_all.groupby(['match_id','innings']):
        first = g.groupby('batter')['ball_float'].min().reset_index().sort_values('ball_float')
        first['position'] = range(1, len(first)+1)
        first['match_id'] = mid
        first['innings'] = inn
        orders.append(first[['match_id','innings','batter','position']])
    if orders:
        return pd.concat(orders, ignore_index=True)
    return pd.DataFrame(columns=['match_id','innings','batter','position'])

batting_positions = compute_batting_positions(df)

# Determine if df contains meaningful numbers (avoid showing tables of all zeros)
def has_meaningful_numbers(df_):
    if df_ is None or df_.empty:
        return False
    numeric_cols = df_.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        return len(df_) > 0
    return (df_[numeric_cols].abs().sum(axis=1) > 0).any()

# compact show helpers
def show_table(df_, title=None):
    """
    Show only the dataframe (no heading). Title param kept for compatibility.
    """
    if df_ is None or df_.empty:
        st.info("No data to show for this metric with current filters.")
        return
    if not has_meaningful_numbers(df_):
        st.info("No meaningful numeric data for this metric with current filters.")
        return
    st.dataframe(df_, use_container_width=True, height=st.session_state.compact_height)

def show_bar(df_, x, y, title, color=None, top_n=None):
    if df_ is None or df_.empty:
        st.info("No data to show for this chart.")
        return
    if not has_meaningful_numbers(df_):
        st.info("No meaningful numeric data for this chart with current filters.")
        return
    if top_n:
        df_ = df_.head(top_n)
    if color:
        fig = px.bar(df_, x=x, y=y, title=title, color_discrete_sequence=[color])
    else:
        fig = px.bar(df_, x=x, y=y, title=title)
    st.plotly_chart(fig, use_container_width=True)

# -------------------------
# Metrics implementations
# -------------------------

# RUN RATE - helper to choose run column based on rr_run_source
def run_col_name():
    return 'runs.total' if rr_run_source == 'Total runs (incl extras)' else 'runs.batter'

def run_rate_per_match(df_, match_id):
    # compute per-innings cumulative RR using legal deliveries only (is_valid_delivery==1)
    g = df_[df_['match_id'] == match_id]
    if g.empty:
        return pd.DataFrame()
    out = []
    run_col = run_col_name()
    for inn, gg in g.groupby('innings'):
        gg = gg.sort_values(['over','ball_float']).reset_index(drop=True)
        # consider only legal deliveries for counting balls (is_valid_delivery == 1)
        gg['valid_flag'] = gg['is_valid_delivery'].astype(int)
        # cumulative valid balls by row
        gg['cum_valid_balls'] = gg['valid_flag'].cumsum()
        # cumulative runs according to selected run column
        gg['cum_runs'] = gg[run_col].cumsum()
        # compute RR at end of each over: we want RR after finishing that over (i.e., at last legal delivery of that over)
        # Group by over and take the last row in that over to get cumulative until that over.
        over_end = gg.groupby('over').apply(lambda d: d.iloc[-1]).reset_index(drop=True)
        over_end['RR'] = (over_end['cum_runs'] / over_end['cum_valid_balls'] * 6).replace([np.inf, np.nan], 0).round(2)
        over_summary = over_end[['over','RR']].rename(columns={'over':'Over'})
        over_summary['Innings'] = f"Innings {int(inn)}"
        out.append(over_summary)
    if out:
        return pd.concat(out, ignore_index=True).sort_values(['Innings','Over'])
    return pd.DataFrame()

def run_rate_multi_match_side_by_side(df_, match_id):
    d = run_rate_per_match(df_, match_id)
    if d.empty: return d
    pivot = d.pivot(index='Over', columns='Innings', values='RR').reset_index().fillna(0)
    pivot = pivot.sort_values('Over')
    return pivot

def run_rate_combined_per_over(df_):
    # Combined per-over RR computed across filtered deliveries, per innings.
    out = []
    run_col = run_col_name()
    for inn, gg in df_.groupby('innings'):
        gg = gg.sort_values(['over','ball_float']).reset_index(drop=True)
        gg['valid_flag'] = gg['is_valid_delivery'].astype(int)
        gg['cum_valid_balls'] = gg['valid_flag'].cumsum()
        gg['cum_runs'] = gg[run_col].cumsum()
        over_end = gg.groupby('over').apply(lambda d: d.iloc[-1]).reset_index(drop=True)
        over_end['RR'] = (over_end['cum_runs'] / over_end['cum_valid_balls'] * 6).replace([np.inf, np.nan], 0).round(2)
        over_end = over_end.rename(columns={'over':'Over'})
        over_end['Innings'] = f"Innings {int(inn)}"
        out.append(over_end[['Over','Innings','RR']])
    if out:
        return pd.concat(out, ignore_index=True).sort_values(['Innings','Over'])
    return pd.DataFrame()

# Extras breakdown
def extras_breakdown(df_):
    res = {}
    res['wides'] = int(df_['wides'].sum()) if 'wides' in df_.columns else 0
    res['no_balls'] = int(df_['no_balls'].sum()) if 'no_balls' in df_.columns else 0
    res['byes'] = int(df_['byes'].sum()) if 'byes' in df_.columns else 0
    res['leg_byes'] = int(df_['leg_byes'].sum()) if 'leg_byes' in df_.columns else 0
    total_extras = sum(res.values())
    rows = []
    for k,v in res.items():
        if v == 0:
            continue  # hide zero rows to avoid empty space
        pct = (v/total_extras*100) if total_extras>0 else 0
        rows.append({'Type':k,'Runs':v,'%':round(pct,2)})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)

# Key Batting
def key_batting(df_):
    valid = df_.copy()
    balls = valid[valid['is_valid_delivery']==1].groupby(['innings','batter']).size().rename('BF')
    runs = valid.groupby(['innings','batter'])['runs.batter'].sum().rename('Runs')
    fours = valid[valid['runs.batter'] == 4].groupby(['innings','batter']).size().rename('4s')
    sixes = valid[valid['runs.batter'] == 6].groupby(['innings','batter']).size().rename('6s')
    dots = valid[valid['runs.batter'] == 0].groupby(['innings','batter']).size().rename('Dots')
    innings_played = valid.groupby(['innings','batter']).apply(lambda g: 1 if (g['is_valid_delivery'].sum()>0) else 0).rename('InningsPlayed')
    stats = pd.concat([runs, balls, fours, sixes, dots, innings_played], axis=1).fillna(0).reset_index()
    stats['4s'] = stats['4s'].astype(int)
    stats['6s'] = stats['6s'].astype(int)
    stats['SR'] = (stats['Runs'] / stats['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    stats['Avg'] = (stats['Runs'] / stats['InningsPlayed']).replace([np.inf, np.nan], 0).round(2)
    stats['Dot%'] = (stats['Dots'] / stats['BF'] * 100).replace([np.inf, np.nan], 0).round(2)
    stats['Innings'] = stats['innings'].map({1:'Innings 1',2:'Innings 2'})
    return stats[['Innings','batter','Runs','BF','SR','Avg','4s','6s','Dot%']].sort_values('Runs', ascending=False)

# Key Bowling (including maidens merged here)
def key_bowling(df_):
    # We must ensure bowler runs exclude byes & legbyes (these go to team, not bowler)
    # We'll compute per-over runs conceded by bowler excluding byes/legbyes.
    g = df_.copy()
    # compute runs attributed to bowler on delivery = runs.total - byes - leg_byes - (wides/no-balls contribution handled separately)
    g['runs_to_bowler'] = g['runs.total'] - g.get('byes',0) - g.get('leg_byes', g.get('leg_byes',0))
    # For wides/no-balls runs_to_bowler still includes penalty that sometimes attributed to bowler (wides counted as extras but usually bowler conceded)
    # We will treat wides/no_balls as bowler conceded runs (common convention). If you want different, toggle here.
    # group by innings & bowler
    grp = g.groupby(['innings','bowler'])
    balls = grp['is_valid_delivery'].sum().rename('Balls')  # legal balls only
    runs = grp['runs_to_bowler'].sum().rename('Runs')
    wkts = grp['wicket_count'].sum().rename('Wkts')
    # maidens: count overs where (legal balls in over ==6) AND bowler conceded 0 runs_to_bowler in that over
    # build per-over per-bowler sums
    over_runs = g.groupby(['innings','bowler','over']).agg({'runs_to_bowler':'sum','is_valid_delivery':'sum'}).reset_index()
    over_runs['is_full_over'] = over_runs['is_valid_delivery'] == 6
    maiden_flags = over_runs[(over_runs['is_full_over']) & (over_runs['runs_to_bowler']==0)].groupby(['innings','bowler']).size().rename('Maidens')
    dfb = pd.concat([balls, runs, wkts], axis=1).fillna(0).reset_index()
    dfb = dfb.merge(maiden_flags.reset_index(), on=['innings','bowler'], how='left')
    dfb['Maidens'] = dfb['Maidens'].fillna(0).astype(int)
    dfb['Overs'] = dfb['Balls'].apply(overs_from_balls)
    dfb['Econ'] = (dfb['Runs'] / (dfb['Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
    dfb['Avg'] = (dfb['Runs'] / dfb['Wkts']).replace([np.inf, np.nan], 0).round(2)
    dfb['SR'] = (dfb['Balls'] / dfb['Wkts']).replace([np.inf, np.nan], 0).round(2)
    dfb['Innings'] = dfb['innings'].map({1:'Innings 1',2:'Innings 2'})
    return dfb[['Innings','bowler','Overs','Balls','Runs','Wkts','Econ','Avg','SR','Maidens']].rename(columns={'bowler':'Bowler'})

# BPSix / BP4
def bpsix(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter').size().rename('Balls')
    sixes = valid[valid['runs.batter'] == 6].groupby('batter').size().rename('Sixes')
    s = pd.concat([balls, sixes], axis=1).fillna(0)
    s['BPSix'] = s.apply(lambda r: round(r['Balls'] / r['Sixes'], 2) if r['Sixes'] > 0 else 0, axis=1)
    s = s.reset_index().rename(columns={'index':'batter'})
    if len(st.session_state.get('matches', [])) == 1:
        s = s[s['Sixes'] > 0]
    return s[['batter','Balls','Sixes','BPSix']].sort_values('BPSix')

def bp4(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter').size().rename('Balls')
    fours = valid[valid['runs.batter'] == 4].groupby('batter').size().rename('Fours')
    s = pd.concat([balls, fours], axis=1).fillna(0)
    s['BP4'] = s.apply(lambda r: round(r['Balls'] / r['Fours'], 2) if r['Fours'] > 0 else 0, axis=1)
    s = s.reset_index().rename(columns={'index':'batter'})
    if len(st.session_state.get('matches', [])) == 1:
        s = s[s['Fours'] > 0]
    return s[['batter','Balls','Fours','BP4']].sort_values('BP4')

# Boundary Balls %
def boundary_balls_pct(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter').size().rename('Balls')
    boundaries = valid[valid['runs.batter'].isin([4,6])].groupby('batter').size().rename('Boundaries')
    s = pd.concat([balls, boundaries], axis=1).fillna(0)
    s['Boundary %'] = (s['Boundaries'] / s['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'index':'batter'})
    return s[['batter','Balls','Boundaries','Boundary %']].sort_values('Boundary %', ascending=False)

# Pressure Index simplified: avg pressure per ball faced
def pressure_index(df_):
    temp = df_.sort_values(['match_id','innings','over','ball_float']).copy()
    temp['cum_wickets'] = temp.groupby(['match_id','innings'])['wicket_count'].cumsum()
    temp['pressure'] = temp['runs.total'] * (10 - temp['cum_wickets'])
    pressure_sum = temp.groupby('batter')['pressure'].sum().rename('pressure_sum')
    balls = temp[temp['is_valid_delivery']==1].groupby('batter').size().rename('BallsFaced')
    out = pd.concat([pressure_sum, balls], axis=1).fillna(0).reset_index()
    out['Pressure Index'] = out.apply(lambda r: round(r['pressure_sum'] / r['BallsFaced'], 2) if r['BallsFaced']>0 else 0, axis=1)
    return out[['batter','BallsFaced','Pressure Index']].sort_values('Pressure Index', ascending=False)

# Powerplay Boundary Rate aggregated (team)
def powerplay_boundary_rate(df_):
    pp = df_[df_['phase'] == 'Powerplay']
    if pp.empty:
        return pd.DataFrame()
    balls = pp[pp['is_valid_delivery']==1].groupby('team').size().rename('PP_Balls')
    boundaries = pp[pp['runs.batter'].isin([4,6])].groupby('team').size().rename('PP_Boundaries')
    s = pd.concat([balls, boundaries], axis=1).fillna(0)
    s['PPBR (%)'] = (s['PP_Boundaries'] / s['PP_Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'team':'Team'})
    return s[['Team','PP_Boundaries','PP_Balls','PPBR (%)']].sort_values('PPBR (%)', ascending=False)

# Death Wag % aggregated
def death_wag_pct(df_):
    death = df_[df_['phase'] == 'Death']
    if death.empty:
        return pd.DataFrame()
    pos = batting_positions
    merged = death.merge(pos, on=['match_id','innings','batter'], how='left')
    merged['position'] = merged['position'].fillna(99).astype(int)
    tot = merged.groupby('teams')['runs.total'].sum().rename('DeathRuns')
    pos7 = merged[merged['position'].between(7,11)].groupby('teams')['runs.total'].sum().rename('Pos7-11Runs')
    out = pd.concat([tot,pos7], axis=1).fillna(0).reset_index().rename(columns={'teams':'Teams'})
    out['Death Wag %'] = (out['Pos7-11Runs'] / out['DeathRuns'] * 100).replace([np.inf, np.nan], 0).round(2)
    return out[['Teams','DeathRuns','Pos7-11Runs','Death Wag %']].sort_values('Death Wag %', ascending=False)

# Match-up dominance
def match_up_dominance(df_):
    valid = df_[df_['is_valid_delivery']==1]
    season = valid.groupby('batter').agg({'runs.batter':'sum','is_valid_delivery':'sum'}).reset_index()
    season['SeasonSR'] = (season['runs.batter'] / season['is_valid_delivery'] * 100).replace([np.inf, np.nan], 0)
    vs = valid.groupby(['batter','bowler']).agg({'runs.batter':'sum','is_valid_delivery':'sum'}).reset_index()
    vs['SR_vs_bowler'] = (vs['runs.batter'] / vs['is_valid_delivery'] * 100).replace([np.inf, np.nan], 0)
    out = vs.merge(season[['batter','SeasonSR']], on='batter', how='left')
    out['MDS'] = (out['SR_vs_bowler'] - out['SeasonSR']).round(2)
    return out.sort_values('MDS', ascending=False)

# Dot ball %
def dot_ball_pct_trend(df_):
    valid = df_[df_['is_valid_delivery']==1]
    balls = valid.groupby('batter').size().rename('Balls')
    dots = valid[valid['runs.batter'] == 0].groupby('batter').size().rename('Dots')
    s = pd.concat([balls, dots], axis=1).fillna(0)
    s['Dot %'] = (s['Dots'] / s['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'index':'batter'})
    return s[['batter','Balls','Dots','Dot %']].sort_values('Dot %', ascending=False)

# Bowler boundary leakage by phase
def bowler_boundary_leakage_by_phase(df_):
    out_rows = []
    for (phase, inn, bowler), g in df_.groupby(['phase','innings','bowler']):
        total_runs = g['runs.total'].sum()
        boundaries = g[g['runs.batter'].isin([4,6])]['runs.batter'].count()
        pct = (boundaries / total_runs * 100) if total_runs > 0 else 0
        out_rows.append({'phase': phase, 'Innings': f"Innings {inn}", 'Bowler': bowler, 'Boundaries Conceded': boundaries, 'Phase Runs': total_runs, 'Leakage %': round(pct,2)})
    if not out_rows:
        return pd.DataFrame()
    return pd.DataFrame(out_rows).sort_values(['phase','Leakage %'], ascending=[True,False])

# Batter contribution
def batter_contribution(df_):
    innings_total = df_.groupby(['match_id','innings'])['runs.batter'].sum().rename('InningsRuns').reset_index()
    batter_runs = df_.groupby(['match_id','innings','batter'])['runs.batter'].sum().rename('Runs').reset_index()
    merged = batter_runs.merge(innings_total, on=['match_id','innings'], how='left')
    merged['Contribution %'] = (merged['Runs'] / merged['InningsRuns'] * 100).replace([np.inf, np.nan], 0).round(2)
    merged['Innings'] = merged['innings'].map({1:'Innings 1',2:'Innings 2'})
    agg = merged.groupby(['Innings','batter']).agg({'Runs':'sum','InningsRuns':'sum','Contribution %':'mean'}).reset_index()
    agg['Contribution %'] = agg['Contribution %'].round(2)
    return agg[['Innings','batter','Runs','InningsRuns','Contribution %']].sort_values('Contribution %', ascending=False)

# Match results
def match_results(df_):
    """
    Robust match results:
    - Prefer explicit result columns if present (match_result, outcome, outcome.* or any column containing 'winner').
    - Only infer when both innings (1 and 2) are present for the match to avoid inferring 'no result' matches.
    - Returns DataFrame with columns: Match, Date, Result (sorted by Date desc when available).
    """
    out_rows = []

    # helper: try find a winner-like column in dataframe
    def find_winner_from_columns(g):
        # direct 'match_result'
        if 'match_result' in g.columns and pd.notna(g['match_result'].iloc[0]) and str(g['match_result'].iloc[0]).strip():
            return str(g['match_result'].iloc[0]).strip()
        # direct 'outcome' or 'outcome.winner' style columns
        if 'outcome' in g.columns:
            v = g['outcome'].iloc[0]
            if pd.notna(v) and str(v).strip():
                return str(v).strip()
        # any column name containing 'winner' or 'outcome'
        for c in g.columns:
            if 'winner' in c.lower() or 'outcome' in c.lower():
                v = g[c].iloc[0]
                if pd.notna(v) and str(v).strip():
                    return str(v).strip()
        return None

    for mid, g in df_.groupby('match_id'):
        # basic metadata
        teams = g['teams'].iloc[0] if 'teams' in g.columns else mid
        date_val = None
        if 'date' in g.columns and pd.notna(g['date'].iloc[0]):
            try:
                date_val = pd.to_datetime(g['date'].iloc[0]).date()
            except Exception:
                date_val = g['date'].iloc[0]

        # 1) Try to find an explicit result/outcome in available columns (preferred)
        explicit = find_winner_from_columns(g)
        if explicit:
            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': explicit})
            continue

        # 2) If no explicit result, only infer if both innings exist (1 and 2)
        innings_present = sorted(g['innings'].dropna().unique())
        if not (1 in innings_present and 2 in innings_present):
            # don't guess — likely abandoned/no result/only one innings recorded
            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': "No result / unavailable"})
            continue

        # 3) Safe inference using innings totals + wickets
        try:
            innings_totals = g.groupby('innings')['runs.total'].sum().to_dict()
            innings_wickets = g.groupby('innings')['wicket_count'].sum().to_dict()

            t1 = float(innings_totals.get(1, 0))
            t2 = float(innings_totals.get(2, 0))
            w1 = int(innings_wickets.get(1, 0))
            w2 = int(innings_wickets.get(2, 0))

            # Determine team names for innings
            team1_arr = g[g['innings'] == 1]['team'].dropna().unique()
            team2_arr = g[g['innings'] == 2]['team'].dropna().unique()
            name1 = team1_arr[0] if len(team1_arr) > 0 else 'Innings 1'
            name2 = team2_arr[0] if len(team2_arr) > 0 else 'Innings 2'

            if abs(t1 - t2) < 1e-9:  # equal totals
                res = "Tie"
            elif t1 > t2:
                margin = int(round(t1 - t2))
                res = f"{name1} won by {margin} runs"
            else:
                # chasing team (innings 2) won
                wickets_lost = w2
                # ensure wickets_lost sensible
                wickets_lost = max(0, wickets_lost)
                wickets_remaining = max(0, 10 - wickets_lost)
                # if wickets_lost >= 10, then wickets_remaining = 0 (all out) but still chasing couldn't have won - fallback
                if wickets_remaining == 0:
                    # If this odd case happens, fall back to run margin
                    margin = int(round(t2 - t1))
                    res = f"{name2} won by {margin} runs"
                else:
                    res = f"{name2} won by {wickets_remaining} wickets"

            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': res})
        except Exception as e:
            out_rows.append({'match_id': mid, 'Match': teams, 'Date': date_val, 'Result': f"Result unavailable (err: {e})"})

    if not out_rows:
        return pd.DataFrame(columns=['Match','Date','Result'])

    out = pd.DataFrame(out_rows)
    # Sort by Date if possible
    if 'Date' in out.columns and pd.api.types.is_datetime64_any_dtype(out['Date']):
        out = out.sort_values('Date', ascending=False)
        out['Date'] = out['Date'].dt.date
    else:
        # try convert then sort safely
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
        
        if metric == "Run Rate Progression":
            # add heading before description
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
            else:  # Per-match multi-run
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
            dfm = key_batting(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Runs', "Top Batting Runs", color=color)
        elif metric == "Key Bowling":
            st.subheader("Key Bowling")
            st.write("Key bowling summary overs, balls, runs conceded to bowler, wickets, economy, maidens")
            dfm = key_bowling(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'Bowler', 'Wkts', "Top Wicket Takers", color=color)
        elif metric == "BPSix":
            st.subheader("Balls-per-Six (BPSix)")
            st.write("how many legal balls a batter takes on average to hit a six")
            dfm = bpsix(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'BPSix', "Balls per Six", color=color)
        elif metric == "BP4":
            st.subheader("Balls-per-Four (BP4)")
            st.write("how many legal balls a batter takes on average to hit a four")
            dfm = bp4(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'BP4', "Balls per Four", color=color)
        elif metric == "Boundary Balls %":
            st.subheader("Boundary Balls %")
            st.write("Percentage of balls faced by batter that yielded a boundary (4/6)")
            dfm = boundary_balls_pct(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Boundary %', "Boundary % by Batter", color=color)
        elif metric == "Powerplay Boundary Rate":
            st.subheader("Powerplay Boundary Rate")
            st.write("Team boundary rate (boundaries per legal ball) inside mandatory powerplay")
            dfm = powerplay_boundary_rate(fdf)
            show_table(dfm, metric)
            if has_meaningful_numbers(dfm):
                show_bar(dfm, 'Team', 'PPBR (%)', "Powerplay Boundary Rate (%) — aggregated per team", color=color)
        elif metric == "Death Wag %":
            st.subheader("Death Wag %")
            st.write("Share of death-innings runs coming from lower-order batters (pos7-11)")
            dfm = death_wag_pct(fdf)
            show_table(dfm, metric)
            if has_meaningful_numbers(dfm):
                show_bar(dfm, 'Teams', 'Death Wag %', "Death Wag % aggregated by team", color=color)
        elif metric == "Match-Up Dominance":
            st.subheader("Match-Up Dominance")
            st.write("How much better/worse a batter performs vs specific bowlers compared to season SR")
            dfm = match_up_dominance(fdf)
            show_table(dfm.head(200), metric)
            show_bar(dfm.head(50), 'batter', 'MDS', "Match-Up Dominance Score (sample)", color=color)
        elif metric == "Pressure Index":
            st.subheader("Pressure Index")
            st.write("Average pressure faced per legal ball (runs * wicket-pressure metric)")
            dfm = pressure_index(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Pressure Index', "Pressure Index (avg pressure per ball faced)", color=color)
        elif metric == "Dot Ball % Trend":
            st.subheader("Dot Ball % Trend")
            st.write("Dot-ball percentage per batter (legal deliveries only)")
            dfm = dot_ball_pct_trend(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Dot %', "Dot % Trend by Batter", color=color)
        elif metric == "Bowler Boundary Leakage by Phase":
            st.subheader("Bowler Boundary Leakage by Phase")
            st.write("Boundaries conceded by bowlers grouped by phase (Powerplay/Death/etc)")
            dfm = bowler_boundary_leakage_by_phase(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'Bowler', 'Leakage %', "Bowler Boundary Leakage by Phase", color=color)
        elif metric == "Batter Contribution %":
            st.subheader("Batter Contribution %")
            st.write("Batter's contribution to their innings total (percentage)")
            dfm = batter_contribution(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Contribution %', "Batter Contribution %", color=color)
        elif metric == "Match Results":
            st.subheader("Match Results")
            st.write("Match outcomes (inferred if not present) - who won and margin")
            dfm = match_results(fdf)
            show_table(dfm, metric)
        else:
            st.write(f"**{metric}** - Coming soon")
    except Exception as e:
        st.error(f"Error computing {metric}: {e}")