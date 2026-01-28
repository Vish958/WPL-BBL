
import pandas as pd

try:
    df = pd.read_parquet("t20_data.parquet")
    
    df_filtered = df[
        (df['league'] == 'WPL') & 
        (df['year'] == 2026) & 
        (df['bowler'] == 'NSS Sharma')
    ]
    
    # Identify duplicates
    duplicates = df_filtered[df_filtered.duplicated(subset=['match_id', 'innings', 'over', 'ball_float'], keep=False)]
    
    print(f"Total Duplicate Rows: {len(duplicates)}")
    
    if not duplicates.empty:
        wickets_in_dupes = duplicates[duplicates['wicket_count'] > 0]
        print(f"Wickets in duplicates: {len(wickets_in_dupes)}")
        print(wickets_in_dupes[['match_id', 'over', 'ball_float', 'wicket_count']])
        
    # Calculate unique wickets (deduplicated)
    df_unique = df_filtered.drop_duplicates(subset=['match_id', 'innings', 'over', 'ball_float'])
    print(f"Total Unique Wickets: {df_unique['wicket_count'].sum()}")

except Exception as e:
    print(e)
