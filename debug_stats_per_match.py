
import pandas as pd

try:
    df = pd.read_parquet("t20_data.parquet")
    
    # Filter for NSS Sharma in WPL 2026
    df = df[
        (df['league'] == 'WPL') & 
        (df['year'] == 2026) & 
        (df['bowler'] == 'NSS Sharma')
    ]
    
    # Helper for overs
    def get_overs(balls):
        return f"{balls // 6}.{balls % 6}"

    # Group by Match
    stats = df.groupby(['match_id', 'date']).agg(
        Balls=('is_valid_delivery', 'sum'),
        Runs=('runs.total', 'sum'), # Note: Logic in app might exclude byes/legbyes
        Wickets=('wicket_count', 'sum')
    ).reset_index()
    
    stats['Overs'] = stats['Balls'].apply(get_overs)
    
    print("NSS Sharma WPL 2026 Stats per Match:")
    print(stats)
    
    print("\nTotal:")
    total_balls = stats['Balls'].sum()
    print(f"Balls: {total_balls} ({get_overs(total_balls)} overs)")
    print(f"Wickets: {stats['Wickets'].sum()}")

except Exception as e:
    print(e)
