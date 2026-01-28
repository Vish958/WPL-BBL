
import pandas as pd

try:
    df = pd.read_parquet("t20_data.parquet")
    
    # Filter for NSS Sharma in WPL 2026
    df = df[
        (df['league'] == 'WPL') & 
        (df['year'] == 2026) & 
        (df['bowler'] == 'NSS Sharma')
    ]

    # Check wickets in Over 16 (ball_float 15.0 to 15.99)
    # 15.1 is 15.0
    # 15.6 is 15 + 5/6 = 15.833
    
    over_16_wickets = df[
        (df['ball_float'] >= 15.0) & 
        (df['ball_float'] < 16.0)
    ]
    
    print("Wickets in Over 16 (16th over, 15.1-16.0):")
    wkts = over_16_wickets['wicket_count'].sum()
    print(f"Count: {wkts}")
    if wkts > 0:
        print(over_16_wickets[['match_id', 'date', 'ball_float', 'wicket_count', 'wicket_type', 'batter']])

except Exception as e:
    print(e)
