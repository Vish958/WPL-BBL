import pandas as pd
import numpy as np

# Load and preprocess
df = pd.read_parquet('local_t20_data_with_drs.parquet')
df = df[df['league'] == 'DPL'].copy()
df = df[df['innings'].isin([1, 2])].copy()   # exclude super overs
df['year'] = df['year'].astype(int)

# Filter for Outer Delhi Warriors 2025 only
odw_2025 = df[(df['team'] == 'Outer Delhi Warriors') & (df['year'] == 2025)].copy()

# Batting Position Derivation per (match_id, innings, batter)
_pos_df = (
    odw_2025.groupby(['match_id', 'innings', 'batter'], observed=True)['ball_float']
    .min()
    .reset_index()
) if 'ball_float' in odw_2025.columns else (
    odw_2025.groupby(['match_id', 'innings', 'batter'], observed=True)['over']
    .min()
    .reset_index()
    .rename(columns={'over': 'ball_float'})
)
_pos_df = _pos_df.sort_values(['match_id', 'innings', 'ball_float'])
_pos_df['bat_position'] = _pos_df.groupby(['match_id', 'innings'], observed=True).cumcount() + 1

# Merge back
odw_2025 = odw_2025.merge(
    _pos_df[['match_id', 'innings', 'batter', 'bat_position']],
    on=['match_id', 'innings', 'batter'],
    how='left'
)

# Dismissal logic
_dismissed_col = 'player_dismissed' if 'player_dismissed' in odw_2025.columns else (
    'player_out' if 'player_out' in odw_2025.columns else None)

if _dismissed_col:
    _NOT_OUT = {'retired out', 'retired not out', 'retired hurt', 'retired - not out'}
    _is_dis = (
        odw_2025[_dismissed_col].notna() &
        (odw_2025[_dismissed_col].astype(str).str.strip() != '') &
        (odw_2025[_dismissed_col].astype(str) == odw_2025['batter'].astype(str))
    )
    if 'wicket_kind' in odw_2025.columns:
        _is_dis &= ~odw_2025['wicket_kind'].astype(str).str.lower().str.strip().isin(_NOT_OUT)
    odw_2025['is_dismissed'] = _is_dis
else:
    odw_2025['is_dismissed'] = False

# First, get match-level batting scores to find 30+ scores and highest score
match_bat = odw_2025.groupby(['match_id', 'innings', 'batter', 'bat_position'], observed=True).agg(
    Runs=('runs.batter', 'sum'),
    Balls=('is_valid_delivery', 'sum'),
    Outs=('is_dismissed', 'sum')
).reset_index()

match_bat['is_30_plus'] = match_bat['Runs'] >= 30

# Aggregate per player and batting position (positions 1 to 7)
player_pos_agg = match_bat.groupby(['batter', 'bat_position'], observed=True).agg(
    Innings=('match_id', 'nunique'),
    Runs=('Runs', 'sum'),
    Balls=('Balls', 'sum'),
    Outs=('Outs', 'sum'),
    ThirtyPlus=('is_30_plus', 'sum'),
    HighestScore=('Runs', 'max')
).reset_index()

player_pos_agg = player_pos_agg[(player_pos_agg['bat_position'] >= 1) & (player_pos_agg['bat_position'] <= 7)]
player_pos_agg['Batting_Average'] = np.where(
    player_pos_agg['Outs'] > 0,
    (player_pos_agg['Runs'] / player_pos_agg['Outs']).round(2),
    player_pos_agg['Runs'].astype(float)
)
player_pos_agg['Strike_Rate'] = (player_pos_agg['Runs'] / player_pos_agg['Balls'] * 100).round(2)

squad_2026 = [
    'Navdeep Saini', 'Priyansh Arya', 'Aryan Rana', 'Harsh Tyagi', 'Shivam Sharma',
    'Siddhant Sharma', 'Mohit Panwar', 'Saksham Gahlot', 'Shaurya Malik', 'Aman Chaudhary',
    'Rushal Saini', 'Yajas Sharma', 'Dhruv Singh', 'Rishabh Drall', 'Aditya Sharma', 'Akshay Sain'
]

player_pos_agg['In_2026_Squad'] = player_pos_agg['batter'].isin(squad_2026)

print("=== BATTING POSITION IMPACT (Outer Delhi Warriors 2025) ===")
# Print by position
for pos in range(1, 8):
    pos_data = player_pos_agg[player_pos_agg['bat_position'] == pos].sort_values('Runs', ascending=False)
    print(f"\n--- Batting Position {pos} ---")
    print(pos_data[['batter', 'Innings', 'Runs', 'Balls', 'Batting_Average', 'Strike_Rate', 'ThirtyPlus', 'HighestScore', 'In_2026_Squad']].to_string(index=False))

# Calculate runs produced by each position in total
total_pos_runs = player_pos_agg.groupby('bat_position').agg(
    Total_Runs=('Runs', 'sum'),
    Innings_Count=('Innings', 'sum')
).reset_index()
print("\n--- Total runs per batting position (1-7) ---")
print(total_pos_runs.to_string(index=False))


# Analysis 2: Phase Scoring + Wickets Lost — Outer Delhi Warriors 2025
print("\n" + "="*60)
print("=== PHASE SCORING + WICKETS LOST ===")
print("="*60)

# We want to check: Powerplay (1-6), 7-10, 11-15, Death (16-20)
# Let's write the periods:
periods = [
    ('Powerplay (1-6)', (0, 5)),
    ('Overs 7-10', (6, 9)),
    ('Overs 11-15', (10, 14)),
    ('Death (16-20)', (15, 19))
]

# Dot ball logic
no_byes = odw_2025['byes'].fillna(0) == 0 if 'byes' in odw_2025.columns else True
no_lb   = odw_2025['leg_byes'].fillna(0) == 0 if 'leg_byes' in odw_2025.columns else True
odw_2025['is_dot'] = (odw_2025['is_valid_delivery'] == 1) & (odw_2025['runs.batter'] == 0) & no_byes & no_lb
odw_2025['is_boundary'] = odw_2025['runs.batter'].isin([4, 6])
wkt_col = 'team_wicket_count' if 'team_wicket_count' in odw_2025.columns else 'wicket_count'

phase_records = []
total_innings = odw_2025['match_id'].nunique() # should be 8

for label, (ov_s, ov_e) in periods:
    p = odw_2025[(odw_2025['over'] >= ov_s) & (odw_2025['over'] <= ov_e)]
    runs = p['runs.total'].sum()
    legal_balls = p['is_valid_delivery'].sum()
    wkts = p[wkt_col].sum()
    dots = p['is_dot'].sum()
    boundaries = p['is_boundary'].sum()
    
    rr = runs / (legal_balls / 6) if legal_balls > 0 else 0
    avg_wkts = wkts / total_innings if total_innings > 0 else 0
    dot_pct = dots / legal_balls * 100 if legal_balls > 0 else 0
    bpb = legal_balls / boundaries if boundaries > 0 else np.nan
    
    phase_records.append({
        'Period': label,
        'Runs': int(runs),
        'Legal_Balls': int(legal_balls),
        'Run_Rate': round(rr, 2),
        'Wickets_Lost': int(wkts),
        'Avg_Wickets_Per_Innings': round(avg_wkts, 2),
        'Dot_Ball_Pct': round(dot_pct, 1),
        'Balls_per_Boundary': round(bpb, 1) if not np.isnan(bpb) else 'NA'
    })

phase_df = pd.DataFrame(phase_records)
print(phase_df.to_string(index=False))
