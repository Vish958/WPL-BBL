import pandas as pd
import numpy as np

df = pd.read_parquet('t20_data_with_drs.parquet')
df['year'] = pd.to_datetime(df['date']).dt.year

ipl25 = df[(df['league']=='IPL') & (df['year']==2025) & (df['innings'].isin([1,2]))].copy()

# Verify tie match 1473469 now has a winner
tie_rows = ipl25[ipl25['match_id'].astype(str)=='1473469']
print(f"1473469 (tie+SO) winner values: {tie_rows['winner'].unique()}")

# Verify no-result logic
no_res = ipl25[ipl25['winner'].isna()]
print(f"\nNo-result rows remaining: {len(no_res)}, match_ids: {no_res['match_id'].unique()}")
print()

# Apply the innings completeness filter as in the fixed code
no_result_mask = ipl25['winner'].isna()
max_over_per_inn = ipl25.groupby(['match_id','innings'], observed=True)['over'].transform('max')
truncated = no_result_mask & (max_over_per_inn < 19)
ipl25_filtered = ipl25[~truncated]
print(f"After innings-completeness filter: {len(ipl25_filtered)} rows (removed {len(ipl25)-len(ipl25_filtered)})")
print()

for name, espn_runs, espn_bf, espn_inns, espn_outs, espn_avg, espn_sr in [
    ('Priyansh Arya',   475, 265, 17, 17, 27.94, 179.24),
    ('P Simran Singh',  549, 342, 17, 17, 32.29, 160.52),
    ('Shubman Gill',    650, 417, 15, 13, 50.00, 155.87),
]:
    p = ipl25_filtered[ipl25_filtered['batter'].astype(str) == name]
    bf = p[p['extras_type'].astype(str) != 'wides']
    runs = bf['runs.batter'].sum()
    balls = len(bf)
    inns = bf.groupby(['match_id','innings']).ngroups
    dis = ipl25_filtered[ipl25_filtered['player_dismissed'].astype(str) == name]
    outs = len(dis)
    avg = round(runs/outs, 2) if outs else runs
    sr = round(runs/balls*100, 2) if balls else 0
    runs_ok = '✓' if runs == espn_runs else f'✗ diff={runs-espn_runs}'
    bf_ok   = '✓' if balls == espn_bf   else f'✗ diff={balls-espn_bf}'
    avg_ok  = '✓' if abs(avg - espn_avg) < 0.1 else f'✗ diff={round(avg-espn_avg,2)}'
    sr_ok   = '✓' if abs(sr - espn_sr)   < 0.5 else f'✗ diff={round(sr-espn_sr,2)}'
    print(f"{name}:")
    print(f"  App  → Runs:{runs}, BF:{balls}, Inns:{inns}, Outs:{outs}, Avg:{avg}, SR:{sr}")
    print(f"  ESPN → Runs:{espn_runs}, BF:{espn_bf}, Inns:{espn_inns}, Outs:{espn_outs}, Avg:{espn_avg}, SR:{espn_sr}")
    print(f"  Runs:{runs_ok}  BF:{bf_ok}  Avg:{avg_ok}  SR:{sr_ok}")
    print()
