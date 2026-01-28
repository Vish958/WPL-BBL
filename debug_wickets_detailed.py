
import pandas as pd

try:
    df = pd.read_parquet("t20_data.parquet")
    
    target_player = 'NSS Sharma'
    
    # Filter for WPL 2026
    df_filtered = df[
        (df['league'] == 'WPL') & 
        (df['year'] == 2026) & 
        (df['bowler'] == target_player)
    ]
    
    print(f"Total rows for {target_player}: {len(df_filtered)}")

    # Check non-zero wicket counts
    wickets_df = df_filtered[df_filtered['wicket_count'] > 0].copy()
    
    print("\nDetailed Wickets:")
    print(wickets_df[['match_id', 'date', 'bowling_team', 'batter', 'wicket_type', 'wicket_count']])
    
    print("\nBreakdown by Wicket Type:")
    print(wickets_df['wicket_type'].value_counts())
    
    print("\nSum of wicket_count:", wickets_df['wicket_count'].sum())
    
    # Check if run outs are included in wicket_count
    run_outs = wickets_df[wickets_df['wicket_type'] == 'run out']
    if not run_outs.empty:
        print("\nWARNING: Run outs found with wicket_count > 0:")
        print(run_outs[['match_id', 'wicket_count']])

except Exception as e:
    print(f"Error: {e}")
