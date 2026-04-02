import pandas as pd
import numpy as np

df = pd.read_parquet('t20_data_with_drs.parquet')
df['year'] = pd.to_datetime(df['date']).dt.year

p2025_all = df[
    (df['year'] == 2025) &
    (df['innings'].isin([1, 2]))
].copy()

# Replicate the new balls_faced logic
work_df = p2025_all.copy()
balls_faced = work_df[work_df['extras_type'].fillna('') != 'wides'].copy()
balls_faced = balls_faced.sort_values(['match_id', 'innings', 'team', 'batter', 'over', 'ball_float'])
balls_faced['batter_ball_no'] = balls_faced.groupby(
    ['match_id', 'innings', 'team', 'batter'], observed=True
).cumcount() + 1

priyansh = balls_faced[balls_faced['batter'].astype(str).str.contains('Priyansh|Arya', na=False)]
total_runs  = priyansh['runs.batter'].sum()
total_balls = len(priyansh)
print(f"Priyansh Arya 2025 — Balls faced: {total_balls}, Runs: {total_runs}, SR: {total_runs/total_balls*100:.2f}")
print(f"Balls in 41-50 range: {priyansh['batter_ball_no'].between(41,50).sum()}")
print(f"Runs in 41-50 range : {priyansh[priyansh['batter_ball_no'].between(41,50)]['runs.batter'].sum()}")
print(f"41-50 SR            : {priyansh[priyansh['batter_ball_no'].between(41,50)]['runs.batter'].sum() / priyansh['batter_ball_no'].between(41,50).sum() * 100:.2f}")
print()
print("Per-match max ball_no:")
print(priyansh.groupby('match_id')['batter_ball_no'].max().to_string())
