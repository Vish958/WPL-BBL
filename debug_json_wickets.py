
import json
import os

data_dir = "/Users/vishwesh/Documents/WPL&BBL/data"
match_ids = ['1513684', '1513685', '1513688', '1513692', '1513694', '1513696']
target_bowler = "NSS Sharma"

print(f"Checking JSON files for bowler: {target_bowler}\n")

total_wickets = 0

for mid in match_ids:
    path = os.path.join(data_dir, f"{mid}.json")
    if not os.path.exists(path):
        print(f"Match {mid}: File not found")
        continue
        
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            
        print(f"Match {mid}: {data['info']['dates'][0]} ({data['info']['teams']})")
        
        match_wickets = 0
        for inning in data.get('innings', []):
            for over in inning.get('overs', []):
                for delivery in over.get('deliveries', []):
                    if delivery.get('bowler') == target_bowler:
                        if 'wickets' in delivery:
                            for w in delivery['wickets']:
                                kind = w.get('kind')
                                if kind in ['caught', 'bowled', 'lbw', 'stumped', 'hit wicket', 'caught and bowled']:
                                    match_wickets += 1
                                    print(f"  - Wicket ({kind}): {w.get('player_out')}")
                                else:
                                    print(f"  - Non-bowler wicket ({kind}): {w.get('player_out')}")
        
        print(f"  Total for match: {match_wickets}\n")
        total_wickets += match_wickets
        
    except Exception as e:
        print(f"Error reading {mid}: {e}")

print(f"Grand Total Wickets from JSONs: {total_wickets}")
