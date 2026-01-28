
import json
import os

data_dir = "/Users/vishwesh/Documents/WPL&BBL/data"
match_ids = ['1513684', '1513685', '1513688', '1513692', '1513694', '1513696']

for mid in match_ids:
    path = os.path.join(data_dir, f"{mid}.json")
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        outcome = data.get('info', {}).get('outcome', {})
        winner = outcome.get('winner')
        result = outcome.get('result')
        print(f"Match {mid}: Winner={winner}, Result={result}")
    except:
        pass
