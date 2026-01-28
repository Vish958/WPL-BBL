
import pandas as pd

try:
    df = pd.read_parquet("t20_data.parquet")
    
    # Filter for NSS Sharma in WPL 2026
    df_filtered = df[
        (df['league'] == 'WPL') & 
        (df['year'] == 2026) & 
        (df['bowler'] == 'NSS Sharma')
    ]
    
    print(f"Total rows: {len(df_filtered)}")
    
    # Check distinct bowling teams
    print("Bowling Teams:", df_filtered['bowling_team'].unique())
    
    # Check for duplicate balls
    duplicates = df_filtered[df_filtered.duplicated(subset=['match_id', 'innings', 'over', 'ball_float'], keep=False)]
    if not duplicates.empty:
        print(f"Found {len(duplicates)} duplicate balls!")
        print(duplicates[['match_id', 'innings', 'over', 'ball_float']].head())
    else:
        print("No duplicate balls found.")
        
    # Check wickets per match
    wickets_per_match = df_filtered.groupby(['match_id', 'date', 'bowling_team'])['wicket_count'].sum().reset_index()
    print("\nWickets per match:")
    print(wickets_per_match)
    
    # Total wickets
    print("\nTotal wickets:", df_filtered['wicket_count'].sum())

except Exception as e:
    print(e)
