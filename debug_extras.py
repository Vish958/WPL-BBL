import pandas as pd
import numpy as np

# Load data
df = pd.read_parquet('t20_data_with_drs.parquet')

# Filter for Match 1513703
ei_df = df[df['match_id'] == '1513703'].copy()
print(f"Total rows for match: {len(ei_df)}")

# Sort
ei_df = ei_df.sort_values(['match_id', 'innings', 'over', 'ball_float'])

# Check total wides before logic
total_wides_raw = ei_df['wides'].sum() # Is 'wides' a count or runs?
# In parquet, 'wides' usually stores the runs (e.g. 1). 
# But 'Extras Impact Index' logic calculates "Extra Balls" using count?
# extras_mask = (ei_df['wides'] > 0)
# Extra_Balls = count of rows.
# If 'wides' column has 5 (5 wides), it counts as 1 ball.
# User said "12 wides". If some wides were 5 runs, the count might be differnt from sum.
# Let's check sum vs count.
wides_count_raw = (ei_df['wides'] > 0).sum()
print(f"Total Wide Runs (Raw): {total_wides_raw}")
print(f"Total Wide Balls (Raw Count): {wides_count_raw}")

# Simulate App Logic
ei_df['next_runs'] = ei_df['runs.total'].shift(-1)
ei_df['next_match'] = ei_df['match_id'].shift(-1)
ei_df['next_innings'] = ei_df['innings'].shift(-1)

extras_mask = (ei_df['wides'] > 0) | (ei_df['no_balls'] > 0)
valid_next = (ei_df['next_match'] == ei_df['match_id']) & (ei_df['next_innings'] == ei_df['innings'])

# Filtered DF
processed_df = ei_df[extras_mask & valid_next].copy()

print(f"\n--- After App Logic ---")
print(f"Processed Rows: {len(processed_df)}")
print(f"Processed Wides Count: {(processed_df['wides'] > 0).sum()}")

# Identify dropped rows
dropped_mask = extras_mask & (~valid_next)
dropped_rows = ei_df[dropped_mask]
print(f"\n--- Dropped Rows ({len(dropped_rows)}) ---")
if not dropped_rows.empty:
    print(dropped_rows[['innings', 'over', 'ball_float', 'bowler', 'wides', 'no_balls', 'next_match', 'next_innings']])
else:
    print("No rows dropped due to valid_next logic.")

# Check if 'wides' column is 0 for some expected wides?
# Maybe 'wides' column is not populated correctly in preprocessing?
# Let's look at all rows with 'extras_type' containing 'wide'?
if 'extras_type' in ei_df.columns:
    wides_from_type = ei_df[ei_df['extras_type'].astype(str).str.contains('wide', case=False, na=False)]
    print(f"\n--- Wides from 'extras_type' column: {len(wides_from_type)}")
    # Compare with 'wides' column > 0
    mismatch = wides_from_type[wides_from_type['wides'] == 0]
    if not mismatch.empty:
        print("Found rows with 'wide' in extras_type but 0 in wide column:")
        print(mismatch[['innings', 'over', 'ball', 'extras_type', 'wides']])
