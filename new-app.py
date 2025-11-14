# app.py — Updated: per-over Run Rate + extras toggle + no deliveries debug
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

st.set_page_config(page_title="T20 Stats", layout="wide")
st.markdown("# T20 Stats | WBBL | MBBL | WPL | SA20")

DATA_SOURCE = "t20_data.parquet"

# default compact height; slider in sidebar allows user to change
DEFAULT_COMPACT_HEIGHT = 300

# ------------------------
# Session-state safe init
# ------------------------
if 'submitted' not in st.session_state:
    st.session_state.submitted = False
if 'compact_height' not in st.session_state:
    st.session_state.compact_height = DEFAULT_COMPACT_HEIGHT
# default metrics (safe init) to avoid KeyError
DEFAULT_METRICS = [
    "Key Batting", "Key Bowling", "BPSix", "BP4", "Batter Contribution %",
    "Extras Breakdown", "Run Rate Progression", "Boundary Balls %",
    "Powerplay Boundary Rate", "Death Wag %", "Match-Up Dominance",
    "Pressure Index", "Dot Ball % Trend", "Bowler Boundary Leakage by Phase", "Match Results"
]
if 'metrics' not in st.session_state:
    st.session_state.metrics = DEFAULT_METRICS

@st.cache_data
def load_data(path=DATA_SOURCE):
    try:
        df = pd.read_parquet(path)
        # defensive normalization
        if 'phase' in df.columns:
            df['phase'] = df['phase'].astype(str).str.strip().apply(lambda x: x.title().replace('Power Play','Powerplay'))
            df['phase'] = df['phase'].replace({'Powersurge':'Power Surge','Power Surge':'Power Surge','Powerplay':'Powerplay'})
        # ensure types
        for c in ['runs.total','runs.batter','runs.extras','is_valid_delivery','wides','no_balls','byes','leg_byes','wicket_count','over','innings']:
            if c in df.columns:
                try:
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
                except Exception:
                    pass
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception as e:
        st.error(f"Data not found or failed to load. ({e})")
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

def clear_submitted():
    st.session_state.submitted = False

# Sidebar: compact height slider (user asked)
st.sidebar.header("UI")
st.session_state.compact_height = st.sidebar.slider("Table height (px)", min_value=150, max_value=1000, value=st.session_state.compact_height)

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
    st.sidebar.date_input("From", key="date_from", value=min_date, min_value=min_date, max_value=max_date, on_change=clear_submitted)
with col2:
    st.sidebar.date_input("To", key="date_to", value=max_date, min_value=min_date, max_value=max_date, on_change=clear_submitted)

# pre-filter to populate downstream selectors before submit
p_df = df.copy()
if st.session_state.get('leagues'): p_df = p_df[p_df['league'].isin(st.session_state['leagues'])]
if st.session_state.get('years'): p_df = p_df[p_df['year'].isin(st.session_state['years'])]
if st.session_state.get('date_from'): p_df = p_df[p_df['date'].dt.date >= st.session_state['date_from']]
if st.session_state.get('date_to'): p_df = p_df[p_df['date'].dt.date <= st.session_state['date_to']]

# Phases: include 'Power Surge' option for Big Bash leagues
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

# Run Rate options (per-user requested features)
st.sidebar.markdown("---")
st.sidebar.markdown("### Run Rate options")
rr_mode = st.sidebar.radio("Run Rate View", ['Per-over (combined)', 'Per match', 'Per-match multi-run'], index=0)
selected_match_for_rr = None
if rr_mode in ('Per match','Per-match multi-run'):
    match_options = sorted(p_df['teams'].unique())
    selected_match_for_rr = st.sidebar.selectbox("Select match for per-match RR", match_options)

# Extras inclusion toggle under Run Rate (user requested)
include_extras = st.sidebar.radio("Include extras in RR calculation?", ['Yes','No'], index=0)
include_extras_flag = (include_extras == 'Yes')

# SUBMIT
if st.sidebar.button("SUBMIT", type="primary"):
    st.session_state.submitted = True
    st.success("Applied!")

if not st.session_state.submitted:
    st.info("Choose filters. Click SUBMIT to compute metrics.")
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
    o = int(balls // 6)
    b = int(balls % 6)
    return f"{o}.{b}"

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
def show_table(df_, title):
    st.subheader(title)
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

# RUN RATE - per-over RR (user requested)
def run_rate_per_match(df_, match_id, include_extras=True):
    g = df_[df_['match_id'] == match_id]
    if g.empty:
        return pd.DataFrame()
    out = []
    for inn, gg in g.groupby('innings'):
        # group by over and compute runs_in_over (respecting include_extras) and legal balls in that over
        if include_extras:
            runs_col = 'runs.total'
        else:
            runs_col = 'runs.batter'
        over_summary = gg.groupby('over').agg(
            RunsInOver = (runs_col, 'sum'),
            LegalBalls = ('is_valid_delivery', 'sum')
        ).reset_index()
        # compute per-over RR: runs_in_over / legal_balls * 6 (if legal balls == 0 -> RR 0)
        over_summary['RR'] = over_summary.apply(lambda r: round((r['RunsInOver'] / r['LegalBalls'] * 6), 2) if r['LegalBalls']>0 else 0.0, axis=1)
        over_summary['Innings'] = f"Innings {inn}"
        over_summary = over_summary.rename(columns={'over':'Over', 'RunsInOver':'Runs','LegalBalls':'ValidBalls'})
        out.append(over_summary[['Innings','Over','Runs','ValidBalls','RR']])
    if out:
        return pd.concat(out, ignore_index=True).sort_values(['Innings','Over'])
    return pd.DataFrame()

def run_rate_multi_match_side_by_side(df_, match_id, include_extras=True):
    d = run_rate_per_match(df_, match_id, include_extras=include_extras)
    if d.empty: return d
    pivot = d.pivot(index='Over', columns='Innings', values='RR').reset_index().fillna(0)
    pivot = pivot.sort_values('Over')
    return pivot

def run_rate_combined_per_over(df_, include_extras=True):
    out = []
    for inn, gg in df_.groupby('innings'):
        runs_col = 'runs.total' if include_extras else 'runs.batter'
        over_summary = gg.groupby('over').agg(
            RunsInOver = (runs_col, 'sum'),
            LegalBalls = ('is_valid_delivery', 'sum')
        ).reset_index()
        over_summary['RR'] = over_summary.apply(lambda r: round((r['RunsInOver'] / r['LegalBalls'] * 6), 2) if r['LegalBalls']>0 else 0.0, axis=1)
        over_summary['Innings'] = f"Innings {inn}"
        over_summary = over_summary.rename(columns={'over':'Over','RunsInOver':'Runs','LegalBalls':'ValidBalls'})
        out.append(over_summary[['Innings','Over','Runs','ValidBalls','RR']])
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
            # hide zero rows (user asked to remove unnecessary zero rows)
            continue
        pct = (v/total_extras*100) if total_extras>0 else 0
        rows.append({'Type':k,'Runs':v,'%':round(pct,2)})
    return pd.DataFrame(rows)

# Key Batting
def key_batting(df_):
    valid = df_.copy()
    balls = valid[valid['is_valid_delivery'] == 1].groupby(['innings','batter']).size().rename('BF')
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

# Key Bowling (maiden inside)
def key_bowling(df_):
    # We'll compute bowler runs excluding byes/leg_byes for bowler accountability
    g = df_.groupby(['innings','bowler'])
    balls = g['is_valid_delivery'].sum().rename('Balls')
    raw_runs = g['runs.total'].sum().rename('RawRuns')
    # deduct byes + leg_byes conceded in bowler's overs to compute runs charged to bowler
    byes = g['byes'].sum().rename('Byes')
    legbyes = g['leg_byes'].sum().rename('LegByes')
    runs_charged = (raw_runs - byes - legbyes).rename('Runs')
    wkts = g['wicket_count'].sum().rename('Wkts')

    # Maiden: compute per-over runs charged to bowler and check legal balls count
    df_copy = df_.copy()
    # runs charged at delivery-level: runs.total minus byes/leg_byes on that delivery
    df_copy['runs_charged_delivery'] = df_copy['runs.total'] - df_copy.get('byes', 0) - df_copy.get('leg_byes', 0)
    over_runs = df_copy.groupby(['innings','bowler','over']).agg(
        legal_balls = ('is_valid_delivery','sum'),
        runs_charged = ('runs_charged_delivery','sum')
    ).reset_index()
    # a maiden is legal_balls==6 and runs_charged==0
    maiden_flags = over_runs[(over_runs['legal_balls']==6) & (over_runs['runs_charged']==0)].groupby(['innings','bowler']).size().rename('Maidens')

    dfb = pd.concat([balls, runs_charged, wkts], axis=1).fillna(0).reset_index()
    dfb['Overs'] = dfb['Balls'].apply(overs_from_balls)
    dfb['Econ'] = (dfb['Runs'] / (dfb['Balls'] / 6)).replace([np.inf, np.nan], 0).round(2)
    dfb['Avg'] = (dfb['Runs'] / dfb['Wkts']).replace([np.inf, np.nan], 0).round(2)
    dfb['SR'] = (dfb['Balls'] / dfb['Wkts']).replace([np.inf, np.nan], 0).round(2)
    if isinstance(maiden_flags, pd.Series):
        dfb = dfb.merge(maiden_flags.reset_index(), on=['innings','bowler'], how='left')
    if 'Maidens' not in dfb.columns:
        dfb['Maidens'] = 0
    dfb['Innings'] = dfb['innings'].map({1:'Innings 1',2:'Innings 2'})
    dfb = dfb.rename(columns={'bowler':'Bowler','Runs':'RunsCharged'})
    # reorder columns
    return dfb[['Innings','Bowler','Overs','Balls','RunsCharged','Wkts','Econ','Avg','SR','Maidens']].fillna(0)

# BPSix / BP4
def bpsix(df_):
    valid = df_[df_['is_valid_delivery'] == 1]
    balls = valid.groupby('batter').size().rename('Balls')
    sixes = valid[valid['runs.batter'] == 6].groupby('batter').size().rename('Sixes')
    s = pd.concat([balls, sixes], axis=1).fillna(0)
    s['BPSix'] = s.apply(lambda r: round(r['Balls'] / r['Sixes'], 2) if r['Sixes'] > 0 else 0, axis=1)
    s = s.reset_index().rename(columns={'index':'batter'})
    if len(st.session_state.get('matches', [])) == 1:
        s = s[s['Sixes'] > 0]
    return s[['batter','Balls','Sixes','BPSix']].sort_values('BPSix')

def bp4(df_):
    valid = df_[df_['is_valid_delivery'] == 1]
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
    valid = df_[df_['is_valid_delivery'] == 1]
    balls = valid.groupby('batter').size().rename('Balls')
    boundaries = valid[valid['runs.batter'].isin([4,6])].groupby('batter').size().rename('Boundaries')
    s = pd.concat([balls, boundaries], axis=1).fillna(0)
    s['Boundary %'] = (s['Boundaries'] / s['Balls'] * 100).replace([np.inf, np.nan], 0).round(2)
    s = s.reset_index().rename(columns={'index':'batter'})
    return s[['batter','Balls','Boundaries','Boundary %']].sort_values('Boundary %', ascending=False)

# Pressure Index simplified: avg pressure per ball faced
def pressure_index(df_):
    temp = df_.sort_values(['match_id','innings','over']).copy()
    temp['cum_wickets'] = temp.groupby(['match_id','innings'])['wicket_count'].cumsum()
    temp['pressure'] = temp['runs.total'] * (10 - temp['cum_wickets'])
    pressure_sum = temp.groupby('batter')['pressure'].sum().rename('pressure_sum')
    balls = temp[temp['is_valid_delivery'] == 1].groupby('batter').size().rename('BallsFaced')
    out = pd.concat([pressure_sum, balls], axis=1).fillna(0).reset_index()
    out['Pressure Index'] = out.apply(lambda r: round(r['pressure_sum'] / r['BallsFaced'], 2) if r['BallsFaced']>0 else 0, axis=1)
    return out[['batter','BallsFaced','Pressure Index']].sort_values('Pressure Index', ascending=False)

# Powerplay Boundary Rate aggregated (team)
def powerplay_boundary_rate(df_):
    pp = df_[df_['phase'] == 'Powerplay']
    if pp.empty:
        return pd.DataFrame()
    balls = pp[pp['is_valid_delivery'] == 1].groupby('team').size().rename('PP_Balls')
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
    valid = df_[df_['is_valid_delivery'] == 1]
    season = valid.groupby('batter').agg({'runs.batter':'sum','is_valid_delivery':'sum'}).reset_index()
    season['SeasonSR'] = (season['runs.batter'] / season['is_valid_delivery'] * 100).replace([np.inf, np.nan], 0)
    vs = valid.groupby(['batter','bowler']).agg({'runs.batter':'sum','is_valid_delivery':'sum'}).reset_index()
    vs['SR_vs_bowler'] = (vs['runs.batter'] / vs['is_valid_delivery'] * 100).replace([np.inf, np.nan], 0)
    out = vs.merge(season[['batter','SeasonSR']], on='batter', how='left')
    out['MDS'] = (out['SR_vs_bowler'] - out['SeasonSR']).round(2)
    return out.sort_values('MDS', ascending=False)

# Dot ball %
def dot_ball_pct_trend(df_):
    valid = df_[df_['is_valid_delivery'] == 1]
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
    if 'match_result' in df_.columns:
        mr = df_.groupby('match_id').agg({'match_result':'first','teams':'first','date':'first'}).reset_index()
        mr['date'] = pd.to_datetime(mr['date']).dt.date
        out = mr[['teams','date','match_result']].rename(columns={'teams':'Match','date':'Date','match_result':'Result'}).sort_values('Date', ascending=False)
        return out
    return pd.DataFrame()

# Colors
color_pool = px.colors.qualitative.Plotly + px.colors.qualitative.D3 + px.colors.qualitative.Set3

# Iterate metrics and display
for i, metric in enumerate(st.session_state['metrics']):
    color = color_pool[i % len(color_pool)]
    try:
        if metric == "Run Rate Progression":
            if rr_mode == 'Per-over (combined)':
                dfm = run_rate_combined_per_over(fdf, include_extras=include_extras_flag)
                show_table(dfm, "Run Rate Progression — Per-over (combined filtered deliveries)")
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
                        dfm = run_rate_per_match(fdf, mid, include_extras=include_extras_flag)
                        show_table(dfm, f"Run Rate Progression — {selected_match_for_rr}")
                        show_bar(dfm, 'Over', 'RR', f"Run Rate Progression ({selected_match_for_rr})", color=color)
            else:  # Per-match multi-run
                if not selected_match_for_rr:
                    st.info("Choose a match for Per-match multi-run.")
                else:
                    mids = fdf[fdf['teams'] == selected_match_for_rr]['match_id'].unique()
                    if len(mids) == 0:
                        st.info("No data for selected match.")
                    else:
                        mid = mids[0]
                        dfm = run_rate_multi_match_side_by_side(fdf, mid, include_extras=include_extras_flag)
                        show_table(dfm, f"Run Rate (both innings) — {selected_match_for_rr}")
        elif metric == "Extras Breakdown":
            dfm = extras_breakdown(fdf)
            show_table(dfm, metric)
            if has_meaningful_numbers(dfm):
                show_bar(dfm, 'Type', '%', "Extras % breakdown", color=color)
        elif metric == "Key Batting":
            dfm = key_batting(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Runs', "Top Batting Runs", color=color)
        elif metric == "Key Bowling":
            dfm = key_bowling(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'Bowler', 'Wkts', "Top Wicket Takers", color=color)
        elif metric == "BPSix":
            dfm = bpsix(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'BPSix', "Balls per Six", color=color)
        elif metric == "BP4":
            dfm = bp4(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'BP4', "Balls per Four", color=color)
        elif metric == "Boundary Balls %":
            dfm = boundary_balls_pct(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Boundary %', "Boundary % by Batter", color=color)
        elif metric == "Powerplay Boundary Rate":
            dfm = powerplay_boundary_rate(fdf)
            show_table(dfm, metric)
            if has_meaningful_numbers(dfm):
                show_bar(dfm, 'Team', 'PPBR (%)', "Powerplay Boundary Rate (%) — aggregated per team", color=color)
        elif metric == "Death Wag %":
            dfm = death_wag_pct(fdf)
            show_table(dfm, metric)
            if has_meaningful_numbers(dfm):
                show_bar(dfm, 'Teams', 'Death Wag %', "Death Wag % aggregated by team", color=color)
        elif metric == "Match-Up Dominance":
            dfm = match_up_dominance(fdf)
            show_table(dfm.head(200), metric)
            show_bar(dfm.head(50), 'batter', 'MDS', "Match-Up Dominance Score (sample)", color=color)
        elif metric == "Pressure Index":
            dfm = pressure_index(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Pressure Index', "Pressure Index (avg pressure per ball faced)", color=color)
        elif metric == "Dot Ball % Trend":
            dfm = dot_ball_pct_trend(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Dot %', "Dot % Trend by Batter", color=color)
        elif metric == "Bowler Boundary Leakage by Phase":
            dfm = bowler_boundary_leakage_by_phase(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'Bowler', 'Leakage %', "Bowler Boundary Leakage by Phase", color=color)
        elif metric == "Batter Contribution %":
            dfm = batter_contribution(fdf)
            show_table(dfm, metric)
            show_bar(dfm.head(50), 'batter', 'Contribution %', "Batter Contribution %", color=color)
        elif metric == "Match Results":
            dfm = match_results(fdf)
            show_table(dfm, metric)
        else:
            st.write(f"**{metric}** - Coming soon")
    except Exception as e:
        st.error(f"Error computing {metric}: {e}")

