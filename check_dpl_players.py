import pandas as pd
import os
import difflib

players_list = [
    "Navdeep Saini", "Priyansh Arya", "Aryan Rana", "Harsh Tyagi", "Shivam Sharma",
    "Siddhant Sharma", "Anant S. Sareen", "Dhanya Nakra", "Mohit Panwar", "Saksham Gahlot",
    "Shaurya Malik", "Aman Chaudhary", "Rushal Saini", "Yajas Sharma", "Dhruv Singh",
    "Rishab Drall", "Aditya Sharma", "Akshay Saini", "Monu Shukla", "Pratham Saluja",
    "Sammar Kohar", "Garvit Grover", "Shivam Bhan", "Deepanshu Phore", "Aditya Yadav"
]

parquet_path = "local_t20_data_with_drs.parquet"
if not os.path.exists(parquet_path):
    print(f"Error: {parquet_path} not found!")
    exit(1)

df = pd.read_parquet(parquet_path)

dataset_players = set()
for col in ['batter', 'bowler', 'player_dismissed']:
    if col in df.columns:
        dataset_players.update(df[col].dropna().astype(str).str.strip().unique())

dataset_players = list(dataset_players)
available = []
not_available = []

for p in players_list:
    p_clean = p.strip().lower()
    match_found = False
    
    # 1. Exact match
    for dp in dataset_players:
        if dp.lower() == p_clean:
            available.append(dp)
            match_found = True
            break
            
    if match_found:
        continue
        
    # 2. String similarity match
    close = difflib.get_close_matches(p, dataset_players, n=1, cutoff=0.80)
    if close:
        c_name = close[0]
        c_parts = c_name.lower().split()
        p_parts = p_clean.split()
        if len(c_parts) > 1 and len(p_parts) > 1:
            first_name_sim = difflib.SequenceMatcher(None, c_parts[0], p_parts[0]).ratio()
            last_name_sim = difflib.SequenceMatcher(None, c_parts[-1], p_parts[-1]).ratio()
            if first_name_sim >= 0.8 and last_name_sim >= 0.7:
                available.append(c_name)
                match_found = True
                
    if not match_found:
        not_available.append(p)

# Create Excel columns
max_len = max(len(available), len(not_available))
avail_col = available + [""] * (max_len - len(available))
not_avail_col = not_available + [""] * (max_len - len(not_available))

out_df = pd.DataFrame({
    "Available": avail_col,
    "Not Available": not_avail_col
})

output_file = "dpl_outer_delhi_availability.xlsx"
out_df.to_excel(output_file, index=False)
print(f"Excel file updated: {output_file}")
print("Available count:", len(available))
print("Not Available count:", len(not_available))
