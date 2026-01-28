
import json
import os

data_dir = "/Users/vishwesh/Documents/WPL&BBL/data"
match_ids = ['1513684', '1513685', '1513688', '1513692', '1513694', '1513696']

for mid in match_ids:
    path = os.path.join(data_dir, f"{mid}.json")
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        event = data.get('info', {}).get('event', {})
        match_type = data.get('info', {}).get('match_type')
        print(f"Match {mid}: {event} | Type: {match_type}")
    except:
        pass
