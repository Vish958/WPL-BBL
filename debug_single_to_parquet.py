# debug_single_to_parquet.py
# Usage:
#   python debug_single_to_parquet.py /Users/vishwesh/Documents/WPL&BBL/data/1341266.json
import sys
import json
import pandas as pd
import os

path = sys.argv[1] if len(sys.argv) > 1 else None
if not path or not os.path.exists(path):
    print("Usage: python debug_single_to_parquet.py /path/to/1341266.json")
    sys.exit(1)

with open(path) as f:
    data = json.load(f)

info = data.get("info", {})
event = info.get("event", {}).get("name", "")
gender = info.get("gender", "female")
print(f"DEBUG parse of: {path}")
print("Event:", event)
print("Info-level powerplays:", info.get("powerplays"))

rows = []
for inn_idx, inn in enumerate(data.get("innings", []), start=1):
    team = inn.get("team", "Unknown")
    powerplays = inn.get("powerplays", info.get("powerplays", []))
    print(f"\nInning {inn_idx} team={team} declared powerplays={powerplays}")
    valid_balls = 0
    for over in inn.get("overs", []):
        over_num = over.get("over", 0)
        for d in over.get("deliveries", []):
            extras = d.get("extras", {}) or {}
            wickets = d.get("wickets", []) or []
            wicket_count = sum(1 for w in wickets if w.get("kind") in [
                "caught","bowled","lbw","stumped","hit wicket","caught and bowled","handled the ball"
            ])
            is_valid = 0 if any(k in extras for k in ["wides","noballs","no_ball"]) else 1
            ball_float = over_num + (valid_balls / 6.0 if is_valid else 5/6.0)
            rows.append({
                "match_id": os.path.basename(path).split(".")[0],
                "date": info.get("dates", [None])[0],
                "innings": inn_idx,
                "team": team,
                "over": over_num,
                "is_valid_delivery": is_valid,
                "runs.total": d.get("runs", {}).get("total", 0),
                "extras": extras,
                "ball_float": ball_float
            })
            if is_valid:
                valid_balls += 1

df = pd.DataFrame(rows)
print("\nParsed rows:", len(df))
if df.empty:
    print("ERROR: no rows parsed from JSON — something wrong with JSON structure.")
else:
    print("\nSample rows (first 40):")
    pd.set_option("display.max_rows", 200)
    print(df.head(40).to_string(index=False))

    # sums:
    for inn in sorted(df['innings'].unique()):
        mask = (df['innings']==inn)
        manual_sum = df.loc[mask & (df['over']<=3),'runs.total'].sum()
        marked_pp_sum = df.loc[mask & (df['ball_float']>=0.0) & (df['ball_float']<=3.833333),'runs.total'].sum()
        print(f"\nInning {inn} manual 0-3 over sum: {manual_sum}")
        print(f"Inning {inn} ball_float 0.0-3.8333 sum (expected Powerplay): {marked_pp_sum}")

    # write temp parquet for streamlit test
    outp = "debug_1341266.parquet"
    df.to_parquet(outp, index=False)
    print("\nWrote temporary parquet:", outp)
    print("Now run: python - <<'PY'\\nimport pandas as pd\\ndf=pd.read_parquet('debug_1341266.parquet'); print(df.head(20).to_string(index=False))\\nPY")
