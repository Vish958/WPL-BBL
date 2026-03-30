import pandas as pd

# Load data
try:
    df = pd.read_parquet('t20_data_with_drs.parquet')
except FileNotFoundError:
    print("Error: t20_data_with_drs.parquet not found.")
    exit()

# Filter for WPL 2026
wpl_2026 = df[(df['league'] == 'WPL') & (df['year'] == 2026)].copy()

if wpl_2026.empty:
    print("No data found for WPL 2026.")
    exit()

print(f"Analyzing {len(wpl_2026)} deliveries from WPL 2026...")

# --- TEAM EXTRAS ---
# Team extras typically include Wides, No Balls, Byes, Leg Byes
team_extras = wpl_2026.groupby('bowling_team')['runs.extras'].sum().sort_values(ascending=False).reset_index()
team_extras.columns = ['Team', 'Total Extras Conceded']

print("\n--- Total Extras Conceded by Team (WPL 2026) ---")
print(team_extras.to_string(index=False))

# --- BOWLER EXTRAS ---
# Bowler extras are strictly Wides and No Balls
# We need to sum 'wides' and 'no_balls' columns.
# Note: 'no_balls' column in parquet is usually a flag (0/1) or count?
# In preprocessing: 'no_balls': extras.get('noballs', ...).
# If it's a count of no-balls (usually 1), we should treat it as runs or count?
# "Bowled total extras" usually implies runs conceded via extras OR count of extra deliveries.
# Wides = runs (usually). No balls = 1 run.
# Let's check the columns. 'wides' stores the run value (e.g. 1, or 5 for wide+4).
# 'no_balls' stores the run value? checking preprocessing...
# line 212: 'no_balls': extras.get('noballs', ...) which is runs? No, usually in JSON 'extras': {'wides': 1}.
# Preprocessing line 244: 'runs.extras': d.get('runs', {}).get('extras', 0)
# Let's use 'wides' and 'no_balls' columns if they are numeric runs.
# Actually, let's use the 'wides' and 'no_balls' columns created in preprocessing.
# line 253: 'wides': extras.get('wides', 0) -> this is the RUNS for wide.
# line 252: 'no_balls': 1 if noball_flag else 0 -> this is a FLAG (count of balls).
# But wait, runs for no-ball are in 'runs.extras'.
# A noball is 1 run.
# So Bowler Extra Runs = Sum('wides') + Sum(No Ball occurrences * 1) ?
# Or simply sum `runs.extras` where `wides > 0` or `no_balls > 0`?
# Note: Byes/Legbyes runs are in `runs.extras` too but shouldn't count for bowler.
# Best approach:
# Bowler Wides = sum('wides')
# Bowler NoBalls = sum('no_balls') * 1  (assuming standard 1 run penalty)
# Total Bowler Extras = Bowler Wides + Bowler NoBalls

# Let's verify 'no_balls' column meaning in preprocessing.
# line 252: 'no_balls': 1 if noball_flag else 0. It is a count flag.
# But `runs.extras` has the actual values.
# If it's a noball, `runs.extras` should be 1.
# If it's a noball + bye, `runs.extras` is 1 + byes? No, byes are separate.
# In Cricsheet loops: 'runs': {'extras': 1, ...}.
# So sum of runs.extras where extras_type includes 'wides' or 'noballs'?
# Preprocessing has 'extras_type'.
# Let's calculate: 
# Total Wides Run = wpl_2026['wides'].sum()
# Total NoBall Runs = wpl_2026[wpl_2026['no_balls'] == 1]['runs.extras'].sum() ?
# Actually, `wides` column in dataframe comes from `extras.get('wides', 0)`.
# If `wides` is 1, `runs.extras` is 1. If `wides` is 5, `runs.extras` is 5.
# So `wides` column is reliable for Wide Runs.
# `no_balls` column is a flag (0 or 1).
# We should sum `runs.extras` for rows where `no_balls` == 1 to get No Ball runs.
# (But careful, if legbyes happen on no ball, is it extra? Yes, usually legbyes on noballs are recorded as... separate runs? Cricsheet structure separates them.)
# Let's stick to: Bowler Extras = Wides (Runs) + No Balls (Count * 1).
# Standard T20 rule: No Ball is 1 run penalty.
# Wides: Value in column is runs.

wpl_2026['NB_Runs'] = wpl_2026['no_balls'] # Each no ball is 1 run
# Note: free hits don't count as extras unless they are also extras.

bowler_extras = wpl_2026.groupby(['bowler', 'bowling_team']).agg(
    Wides=('wides', 'sum'),
    NoBalls=('no_balls', 'sum')
).reset_index()

bowler_extras['Total_Bowler_Extras'] = bowler_extras['Wides'] + bowler_extras['NoBalls']
bowler_extras = bowler_extras.sort_values('Total_Bowler_Extras', ascending=False)

print("\n--- Top 20 Bowlers by Extras Conceded (WPL 2026) ---")
print(bowler_extras[['bowler', 'bowling_team', 'Wides', 'NoBalls', 'Total_Bowler_Extras']].head(20).to_string(index=False))
