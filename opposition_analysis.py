"""
opposition_analysis.py
Pre-match analysis: Purani Dilli 6 vs Outer Delhi Warriors — DPL 2026
Standalone script — does NOT modify the dashboard.
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ─── Load data ───────────────────────────────────────────────────────────────
df = pd.read_parquet('local_t20_data_with_drs.parquet')
df = df[df['league'] == 'DPL'].copy()
df = df[df['innings'].isin([1, 2])].copy()   # exclude super overs
df['year'] = df['year'].astype(int)
df['batter'] = df['batter'].astype(str).str.strip()
df['bowler'] = df['bowler'].astype(str).str.strip()

# ─── Constants ────────────────────────────────────────────────────────────────
OUTER_DELHI_SQUAD_AVAILABLE = [
    'Navdeep Saini', 'Priyansh Arya', 'Aryan Rana', 'Harsh Tyagi',
    'Shivam Sharma', 'Siddhant Sharma', 'Mohit Panwar', 'Saksham Gahlot',
    'Shaurya Malik', 'Aman Chaudhary', 'Rushal Saini', 'Yajas Sharma',
    'Dhruv Singh', 'Rishabh Drall', 'Aditya Sharma', 'Akshay Sain'
]

# Outer Delhi Warriors team name as stored in parquet
# Let's check
outer_delhi_teams = [t for t in df['team'].dropna().unique()
                     if 'outer' in str(t).lower() or 'warrior' in str(t).lower()]
print("Outer Delhi team names in DB:", outer_delhi_teams)

# Also check all teams
print("\nAll DPL teams:", sorted(df['team'].dropna().unique()))
print("Years:", sorted(df['year'].unique()))

# ─── Helpers ─────────────────────────────────────────────────────────────────

def is_dot(row_df):
    """True for legal deliveries where batter scored 0 and no byes/legbyes."""
    legal = row_df['is_valid_delivery'] == 1
    batter_zero = row_df['runs.batter'] == 0
    no_byes = (row_df['byes'].fillna(0) == 0) if 'byes' in row_df.columns else True
    no_lb = (row_df['leg_byes'].fillna(0) == 0) if 'leg_byes' in row_df.columns else True
    return legal & batter_zero & no_byes & no_lb

def bowler_runs_col(row_df):
    r = row_df['runs.total'].astype(float)
    if 'byes' in row_df.columns: r = r - row_df['byes'].fillna(0).astype(float)
    if 'leg_byes' in row_df.columns: r = r - row_df['leg_byes'].fillna(0).astype(float)
    return r.clip(lower=0)

def safe_div(a, b, fill=0.0):
    return np.where(b > 0, a / b, fill)

NOT_OUT_KINDS = {'retired out', 'retired not out', 'retired hurt', 'retired - not out'}
BOWLER_WKTS = {'caught', 'bowled', 'lbw', 'stumped', 'hit wicket', 'caught and bowled', 'handled the ball'}

def get_dismissal_mask(df_, col='player_dismissed'):
    if col not in df_.columns:
        return pd.Series(False, index=df_.index)
    mask = (df_[col].notna() &
            (df_[col].astype(str).str.strip() != '') &
            (df_[col].astype(str) == df_['batter'].astype(str)))
    if 'wicket_kind' in df_.columns:
        mask = mask & ~df_['wicket_kind'].astype(str).str.lower().str.strip().isin(NOT_OUT_KINDS)
    return mask

OVER_PERIODS = [
    ('Overs 1-6',   (0, 5)),
    ('Overs 7-10',  (6, 9)),
    ('Overs 11-15', (10, 14)),
    ('Overs 16-20', (15, 19)),
]
PHASES = ['Powerplay', 'Middle', 'Death']

# ─── SECTION 1: Outer Delhi Warriors TEAM analysis (2025 only) ───────────────
print("\n" + "="*60)
print("SECTION 1: OUTER DELHI WARRIORS — TEAM ANALYSIS (2025 ONLY)")
print("="*60)

odw_team_name = None
for t in df['team'].dropna().unique():
    if 'outer' in str(t).lower() or 'warrior' in str(t).lower():
        odw_team_name = t
        break

if odw_team_name is None:
    print("ERROR: Could not find Outer Delhi Warriors team name. Available teams:")
    print(sorted(df['team'].dropna().unique()))
else:
    print(f"Using team name: '{odw_team_name}'")
    odw_2025 = df[(df['team'] == odw_team_name) & (df['year'] == 2025)].copy()
    print(f"ODW 2025 rows: {len(odw_2025)}, matches: {odw_2025['match_id'].nunique()}")

    if not odw_2025.empty:
        odw_2025['is_dot'] = is_dot(odw_2025)
        odw_2025['is_boundary'] = odw_2025['runs.batter'].isin([4, 6])
        odw_2025['is_dismissed'] = get_dismissal_mask(odw_2025)
        wkt_col = 'team_wicket_count' if 'team_wicket_count' in odw_2025.columns else 'wicket_count'

        # ── 1a. Over period analysis ──────────────────────────────────────
        print("\n--- 1a. Over Period Analysis ---")
        for label, (ov_s, ov_e) in OVER_PERIODS:
            p = odw_2025[(odw_2025['over'] >= ov_s) & (odw_2025['over'] <= ov_e)]
            if p.empty: continue
            runs = p['runs.total'].sum()
            legal_balls = p['is_valid_delivery'].sum()
            wkts = p[wkt_col].sum()
            dots = p['is_dot'].sum()
            bds = p['is_boundary'].sum()
            rr = (runs / (legal_balls / 6)) if legal_balls > 0 else 0
            dot_pct = (dots / legal_balls * 100) if legal_balls > 0 else 0
            bd_pct = (bds / legal_balls * 100) if legal_balls > 0 else 0
            innings = p.groupby(['match_id', 'innings']).ngroups
            print(f"{label}: Runs={int(runs)}, Balls={int(legal_balls)}, RR={rr:.2f}, "
                  f"Wickets={int(wkts)}, Dot%={dot_pct:.1f}%, Boundary%={bd_pct:.1f}%, "
                  f"Innings={innings}")

        # ── 1b. Phase analysis ────────────────────────────────────────────
        print("\n--- 1b. Phase Analysis ---")
        if 'phase' in odw_2025.columns:
            for ph in PHASES:
                p = odw_2025[odw_2025['phase'] == ph]
                if p.empty: continue
                runs = p['runs.total'].sum()
                legal_balls = p['is_valid_delivery'].sum()
                wkts = p[wkt_col].sum()
                dots = p['is_dot'].sum()
                rr = (runs / (legal_balls / 6)) if legal_balls > 0 else 0
                dot_pct = (dots / legal_balls * 100) if legal_balls > 0 else 0
                print(f"{ph}: Runs={int(runs)}, LegalBalls={int(legal_balls)}, RR={rr:.2f}, "
                      f"Wickets={int(wkts)}, Dot%={dot_pct:.1f}%")

        # ── 1c. Powerplay bowling (against ODW) ───────────────────────────
        print("\n--- 1c. ODW Powerplay Bowling (runs conceded by phase) ---")
        # When ODW is bowling (bowling_team == odw_team_name)
        if 'bowling_team' in df.columns:
            odw_bowl_2025 = df[(df['bowling_team'] == odw_team_name) & (df['year'] == 2025)].copy()
            odw_bowl_2025['bowler_runs'] = bowler_runs_col(odw_bowl_2025)
            odw_bowl_2025['is_dot'] = is_dot(odw_bowl_2025)
            odw_bowl_2025['is_boundary'] = odw_bowl_2025['runs.batter'].isin([4, 6])
            for ph in PHASES:
                p = odw_bowl_2025[odw_bowl_2025['phase'] == ph] if 'phase' in odw_bowl_2025.columns else odw_bowl_2025
                if p.empty: continue
                bowl_runs = p['bowler_runs'].sum()
                legal_balls = p['is_valid_delivery'].sum()
                wkts = p['wicket_count'].sum()  # bowler-credited
                dots = p['is_dot'].sum()
                econ = (bowl_runs / (legal_balls / 6)) if legal_balls > 0 else 0
                dot_pct = (dots / legal_balls * 100) if legal_balls > 0 else 0
                bds = p['is_boundary'].sum()
                bd_pct = (bds / legal_balls * 100) if legal_balls > 0 else 0
                print(f"BOWLING {ph}: Conceded={int(bowl_runs)}, LegalBalls={int(legal_balls)}, "
                      f"Economy={econ:.2f}, Wickets={int(wkts)}, Dot%={dot_pct:.1f}%, "
                      f"Boundary%={bd_pct:.1f}%")

        # ── 1d. Dot-ball pressure conversion (ODW bowling) ────────────────
        print("\n--- 1d. Dot-Ball Pressure Sequences (ODW Bowling, 2025) ---")
        if 'bowling_team' in df.columns and not odw_bowl_2025.empty:
            odw_bowl_sorted = odw_bowl_2025.sort_values(['match_id', 'innings', 'ball_float'])
            pressure_seqs = 0
            wickets_after = 0
            bds_after = 0
            min_streak = 3

            for (mid, inn), inn_df in odw_bowl_sorted.groupby(['match_id', 'innings'], observed=True):
                legal = inn_df[inn_df['is_valid_delivery'] == 1].reset_index(drop=True)
                m = len(legal)
                i = 0
                while i < m:
                    if legal.loc[i, 'runs.batter'] == 0 and legal.loc[i].get('byes', 0) == 0 and legal.loc[i].get('leg_byes', 0) == 0:
                        streak = 0
                        j = i
                        while j < m and legal.loc[j, 'runs.batter'] == 0:
                            streak += 1
                            j += 1
                        if streak >= min_streak:
                            pressure_seqs += 1
                            next3 = legal.iloc[j:j+3]
                            wickets_after += next3['wicket_count'].sum()
                            bds_after += next3['runs.batter'].isin([4, 6]).sum()
                            i = j
                        else:
                            i += 1
                    else:
                        i += 1

            conv_pct = (wickets_after / pressure_seqs * 100) if pressure_seqs > 0 else 0
            print(f"Pressure sequences (3+ dot balls): {pressure_seqs}")
            print(f"Wickets in next 3 legal balls: {wickets_after}")
            print(f"Conversion%: {conv_pct:.1f}%")
            print(f"Boundaries in next 3 legal balls: {bds_after}")

# ─── SECTION 2: Individual Squad Player Analysis (DPL 2024 + 2025) ───────────
print("\n" + "="*60)
print("SECTION 2: SQUAD PLAYER ANALYSIS (DPL 2024+2025, ALL FRANCHISES)")
print("="*60)

squad_df = df[df['year'].isin([2024, 2025])].copy()
squad_df['is_dot'] = is_dot(squad_df)
squad_df['is_boundary'] = squad_df['runs.batter'].isin([4, 6])
squad_df['is_dismissed'] = get_dismissal_mask(squad_df)
squad_df['bowler_runs'] = bowler_runs_col(squad_df)
wkt_col_sq = 'team_wicket_count' if 'team_wicket_count' in squad_df.columns else 'wicket_count'

# ── 2a. Batter Phase Analysis ─────────────────────────────────────────────
print("\n--- 2a. BATTER PHASE VULNERABILITY ---")
# Balls faced = is_valid_delivery == 1 | no_balls > 0 (not wides)
squad_df['is_bf'] = (squad_df['is_valid_delivery'] == 1) | (squad_df['no_balls'].fillna(0) > 0)

batter_phase_rows = []
for batter in OUTER_DELHI_SQUAD_AVAILABLE:
    bat_df = squad_df[squad_df['batter'] == batter]
    if bat_df.empty: continue
    for phase in PHASES:
        ph_df = bat_df[bat_df['phase'] == phase] if 'phase' in bat_df.columns else bat_df
        if ph_df.empty: continue
        runs = ph_df['runs.batter'].sum()
        balls = ph_df['is_bf'].sum()
        legal_balls = ph_df['is_valid_delivery'].sum()
        outs = ph_df['is_dismissed'].sum()
        dots = ph_df['is_dot'].sum()
        bds = ph_df['is_boundary'].sum()
        if balls < 10: continue
        sr = (runs / balls * 100) if balls > 0 else 0
        avg = (runs / outs) if outs > 0 else runs
        dot_pct = (dots / legal_balls * 100) if legal_balls > 0 else 0
        bd_pct = (bds / legal_balls * 100) if legal_balls > 0 else 0
        batter_phase_rows.append({
            'Batter': batter, 'Phase': phase, 'Runs': int(runs), 'Balls': int(balls),
            'Legal': int(legal_balls), 'Outs': int(outs), 'SR': round(sr, 1),
            'Avg': round(avg, 1), 'Dot%': round(dot_pct, 1), 'Bd%': round(bd_pct, 1)
        })

bpv_df = pd.DataFrame(batter_phase_rows)
if not bpv_df.empty:
    print(bpv_df.sort_values(['Batter', 'Phase']).to_string(index=False))

# ── 2b. Batter SR Bucket (first 10 balls vs later) ───────────────────────
print("\n--- 2b. KEY BATTERS: Early vs Late SR (first 10 balls vs 11+) ---")
for batter in OUTER_DELHI_SQUAD_AVAILABLE:
    bat_df = squad_df[squad_df['batter'] == batter].copy()
    if bat_df.empty: continue
    # Sort deliveries per innings and number batter's balls
    bat_df = bat_df.sort_values(['match_id', 'innings', 'ball_float'])
    bat_df['batter_ball_no'] = bat_df.groupby(['match_id', 'innings'], observed=True).cumcount() + 1
    early = bat_df[bat_df['batter_ball_no'] <= 10]
    late = bat_df[bat_df['batter_ball_no'] > 10]
    early_runs = early['runs.batter'].sum()
    early_balls = early['is_bf'].sum()
    late_runs = late['runs.batter'].sum()
    late_balls = late['is_bf'].sum()
    if early_balls < 15: continue
    sr_early = (early_runs / early_balls * 100) if early_balls > 0 else 0
    sr_late = (late_runs / late_balls * 100) if late_balls > 0 else 0
    print(f"{batter}: Balls1-10: {int(early_balls)}, SR={sr_early:.1f} | "
          f"Balls11+: {int(late_balls)}, SR={sr_late:.1f}")

# ── 2c. Boundary dependency ───────────────────────────────────────────────
print("\n--- 2c. BATTER BOUNDARY DEPENDENCY ---")
for batter in OUTER_DELHI_SQUAD_AVAILABLE:
    bat_df = squad_df[squad_df['batter'] == batter]
    if bat_df.empty: continue
    runs = bat_df['runs.batter'].sum()
    balls = bat_df['is_bf'].sum()
    legal_balls = bat_df['is_valid_delivery'].sum()
    bds = bat_df['is_boundary'].sum()
    bd_runs = bat_df[bat_df['is_boundary']]['runs.batter'].sum()
    if balls < 20: continue
    bd_run_pct = (bd_runs / runs * 100) if runs > 0 else 0
    bd_rate = (bds / legal_balls) if legal_balls > 0 else 0
    print(f"{batter}: Runs={int(runs)}, Balls={int(balls)}, Boundaries={int(bds)}, "
          f"BdRun%={bd_run_pct:.1f}%, BdEvery={1/bd_rate:.1f}balls" if bd_rate > 0
          else f"{batter}: no boundaries")

# ── 2d. Bowler Phase Analysis ─────────────────────────────────────────────
print("\n--- 2d. BOWLER PHASE ANALYSIS ---")
bowler_phase_rows = []
for bowler in OUTER_DELHI_SQUAD_AVAILABLE:
    bowl_df = squad_df[squad_df['bowler'] == bowler]
    if bowl_df.empty: continue
    for phase in PHASES:
        ph_df = bowl_df[bowl_df['phase'] == phase] if 'phase' in bowl_df.columns else bowl_df
        if ph_df.empty: continue
        legal_balls = ph_df['is_valid_delivery'].sum()
        if legal_balls < 6: continue
        br = ph_df['bowler_runs'].sum()
        wkts = ph_df['wicket_count'].sum()  # bowler-credited
        dots = ph_df['is_dot'].sum()
        bds = ph_df['is_boundary'].sum()
        overs = legal_balls / 6
        econ = (br / overs) if overs > 0 else 0
        sr_bowl = (legal_balls / wkts) if wkts > 0 else np.nan
        dot_pct = (dots / legal_balls * 100) if legal_balls > 0 else 0
        bd_pct = (bds / legal_balls * 100) if legal_balls > 0 else 0
        bowler_phase_rows.append({
            'Bowler': bowler, 'Phase': phase, 'LegalBalls': int(legal_balls),
            'Overs': round(overs, 1), 'Runs': int(br), 'Wickets': int(wkts),
            'Economy': round(econ, 2),
            'BowlSR': round(sr_bowl, 1) if not np.isnan(sr_bowl) else 'NA',
            'Dot%': round(dot_pct, 1), 'Bd%': round(bd_pct, 1)
        })

bpt_df = pd.DataFrame(bowler_phase_rows)
if not bpt_df.empty:
    print(bpt_df.sort_values(['Bowler', 'Phase']).to_string(index=False))

# ── 2e. Bowler first spell (overs 1-4 powerplay) ─────────────────────────
print("\n--- 2e. BOWLER POWERPLAY / FIRST SPELL ---")
for bowler in OUTER_DELHI_SQUAD_AVAILABLE:
    bowl_df = squad_df[(squad_df['bowler'] == bowler) & (squad_df['over'] < 6)]
    if bowl_df.empty: continue
    legal_balls = bowl_df['is_valid_delivery'].sum()
    if legal_balls < 6: continue
    br = bowl_df['bowler_runs'].sum()
    wkts = bowl_df['wicket_count'].sum()
    dots = bowl_df['is_dot'].sum()
    econ = (br / (legal_balls/6)) if legal_balls > 0 else 0
    dot_pct = (dots / legal_balls * 100) if legal_balls > 0 else 0
    print(f"{bowler}: PP LegalBalls={int(legal_balls)}, Econ={econ:.2f}, "
          f"Wkts={int(wkts)}, Dot%={dot_pct:.1f}%")

# ── 2f. Priyansh Arya detailed (likely key batter) ───────────────────────
print("\n--- 2f. PRIYANSH ARYA — DETAILED ---")
pa = squad_df[squad_df['batter'] == 'Priyansh Arya'].copy()
print(f"Total rows: {len(pa)}, Matches: {pa['match_id'].nunique()}, Years: {sorted(pa['year'].unique())}")
if not pa.empty:
    pa_runs = pa['runs.batter'].sum()
    pa_balls = pa['is_bf'].sum()
    pa_legal = pa['is_valid_delivery'].sum()
    pa_outs = pa['is_dismissed'].sum()
    pa_dots = pa['is_dot'].sum()
    pa_bds = pa['is_boundary'].sum()
    pa_bd_runs = pa[pa['is_boundary']]['runs.batter'].sum()
    print(f"Runs={int(pa_runs)}, Balls={int(pa_balls)}, SR={pa_runs/pa_balls*100:.1f}, "
          f"Outs={int(pa_outs)}, Avg={pa_runs/pa_outs:.1f if pa_outs > 0 else 'NO'}, "
          f"Dot%={(pa_dots/pa_legal*100):.1f}%, BdRun%={(pa_bd_runs/pa_runs*100):.1f}%")

# ── 2g. Navdeep Saini detailed (likely key bowler) ────────────────────────
print("\n--- 2g. NAVDEEP SAINI — DETAILED ---")
ns = squad_df[squad_df['bowler'] == 'Navdeep Saini'].copy()
print(f"Total rows: {len(ns)}, Matches: {ns['match_id'].nunique()}, Years: {sorted(ns['year'].unique())}")
if not ns.empty:
    for phase in PHASES:
        p = ns[ns['phase'] == phase] if 'phase' in ns.columns else ns
        if p.empty: continue
        legal_balls = p['is_valid_delivery'].sum()
        if legal_balls < 6: continue
        br = p['bowler_runs'].sum()
        wkts = p['wicket_count'].sum()
        dots = p['is_dot'].sum()
        econ = (br / (legal_balls/6))
        print(f"  {phase}: Balls={int(legal_balls)}, Econ={econ:.2f}, Wkts={int(wkts)}, "
              f"Dot%={(dots/legal_balls*100):.1f}%")

# ── 2h. Phase competition averages (DPL 2025 for comparison) ──────────────
print("\n--- 2h. DPL 2025 COMPETITION AVERAGES BY PHASE ---")
dpl_2025 = df[df['year'] == 2025].copy()
dpl_2025['is_dot'] = is_dot(dpl_2025)
dpl_2025['bowler_runs'] = bowler_runs_col(dpl_2025)
if 'phase' in dpl_2025.columns:
    for phase in PHASES:
        p = dpl_2025[dpl_2025['phase'] == phase]
        if p.empty: continue
        legal_balls = p['is_valid_delivery'].sum()
        runs = p['runs.total'].sum()
        bowl_runs = p['bowler_runs'].sum()
        wkts = p['wicket_count'].sum()
        dots = p['is_dot'].sum()
        rr = (runs / (legal_balls/6)) if legal_balls > 0 else 0
        bowl_sr = (legal_balls / wkts) if wkts > 0 else np.nan
        dot_pct = (dots / legal_balls * 100) if legal_balls > 0 else 0
        econ = (bowl_runs / (legal_balls/6)) if legal_balls > 0 else 0
        print(f"DPL2025 {phase}: RR={rr:.2f}, Dot%={dot_pct:.1f}%, "
              f"Econ={econ:.2f}, BowlSR={bowl_sr:.1f if not np.isnan(bowl_sr) else 'NA'}")

# ── 2i. Check Navdeep Saini as batter (for batter_ball_no) ───────────────
print("\n--- 2i. Check all available squad members with meaningful batting data ---")
for batter in OUTER_DELHI_SQUAD_AVAILABLE:
    bat_df = squad_df[squad_df['batter'] == batter]
    balls = bat_df['is_bf'].sum()
    runs = bat_df['runs.batter'].sum()
    if balls >= 10:
        print(f"{batter}: Balls={int(balls)}, Runs={int(runs)}, SR={(runs/balls*100):.1f}")

print("\n--- DONE. Review output above to construct validation table. ---")
