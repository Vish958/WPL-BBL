
import pandas as pd

try:
    df = pd.read_parquet("t20_data.parquet")
    print("Columns:", df.columns.tolist())
    
    # Filter for NSS Sharma
    # Check if name is 'NSS Sharma' or similar. 
    # Usually names are Initials + Surname.
    
    # Let's first search for the player name
    players = df['bowler'].unique()
    match = [p for p in players if 'Sharma' in str(p) and 'N' in str(p)]
    print("Matching players:", match)
    
    target_player = 'NSS Sharma' # Assuming this is the name based on the screenshot, but I'll use the search result if different.
    if match:
         target_player = match[0] # Pick the first one or refine
         for m in match:
             if 'NSS Sharma' == m:
                 target_player = m
                 break
    
    print(f"Targeting: {target_player}")

    # FLiter for WPL 2026
    df_filtered = df[
        (df['league'] == 'WPL') & 
        (df['year'] == 2026) & 
        (df['bowler'] == target_player)
    ]
    
    total_wickets = df_filtered['wicket_count'].sum()
    print(f"Total wickets for {target_player} in WPL 2026: {total_wickets}")
    
    # List matches and wickets per match
    matches = df_filtered[df_filtered['wicket_count'] > 0].groupby(['match_id', 'date'])['wicket_count'].sum().reset_index()
    print("\nMatches with wickets:")
    print(matches)
    
    # Check for any unique dismissal types if possible
    if 'wicket_type' in df.columns:
        print("\nWicket Types:")
        print(df_filtered[df_filtered['wicket_count'] > 0]['wicket_type'].value_counts())
        
except Exception as e:
    print(f"Error: {e}")
