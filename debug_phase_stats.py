
import pandas as pd

try:
    df = pd.read_parquet("t20_data.parquet")
    
    # Filter for NSS Sharma in WPL 2026
    df = df[
        (df['league'] == 'WPL') & 
        (df['year'] == 2026) & 
        (df['bowler'] == 'NSS Sharma')
    ]

    print("Stats by Phase:")
    phases = df['phase'].unique()
    
    for p in phases:
        sub = df[df['phase'] == p]
        balls = sub['is_valid_delivery'].sum()
        wkts = sub['wicket_count'].sum()
        runs = sub['runs.total'].sum() - sub['byes'].sum() - sub['leg_byes'].sum() # Approx
        
        print(f"Phase: {p}")
        print(f"  Balls: {balls} ({balls//6}.{balls%6} overs)")
        print(f"  Wickets: {wkts}")
        print(f"  Runs: {runs}")
        print("-" * 20)

    # Combinations?
    # Maybe "Death" only?
    
except Exception as e:
    print(e)
