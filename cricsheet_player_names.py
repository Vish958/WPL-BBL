import pandas as pd
import os

def main():
    parquet_path = "t20_data_with_drs.parquet"
    
    if not os.path.exists(parquet_path):
        print(f"Error: {parquet_path} not found. Please run preprocessing first.")
        return
        
    print(f"Loading data from {parquet_path}...")
    # Read only the columns that contain player names to optimize memory and speed
    df = pd.read_parquet(parquet_path, columns=["batter", "bowler", "player_dismissed"])
    
    # Collect all unique player names
    batters = set(df["batter"].dropna().unique())
    bowlers = set(df["bowler"].dropna().unique())
    dismissed = set(df["player_dismissed"].dropna().unique())
    
    # Union of all player sets
    all_players = sorted(list(batters.union(bowlers).union(dismissed)))
    
    # Print summary
    print("\n--- Players Statistics ---")
    print(f"Total Batters: {len(batters)}")
    print(f"Total Bowlers: {len(bowlers)}")
    print(f"Total Unique Players: {len(all_players)}")
    print("--------------------------\n")
    
    # Save to a text file for reference
    output_txt = "all_unique_players.txt"
    with open(output_txt, "w", encoding="utf-8") as f:
        for player in all_players:
            f.write(f"{player}\n")
            
    print(f"List of all unique players written to: {output_txt}")
    
    # Print the first 50 players as a sample
    print("\nFirst 50 players sample:")
    for player in all_players[:50]:
        print(f"- {player}")

if __name__ == "__main__":
    main()
