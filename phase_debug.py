import pandas as pd

# apni t20_data.parquet file ka path
df = pd.read_parquet("t20_data.parquet")

# sirf Brisbane Heat Women, 1st innings check kar rahe hain
pp = df[(df["team"] == "Brisbane Heat Women") & (df["innings"] == 1)]

print("Powerplay deliveries (marked):")
cols = ["over", "runs.total", "phase", "is_valid_delivery"]
if "ball_in_over" in df.columns:
    cols.insert(1, "ball_in_over")
elif "ball" in df.columns:
    cols.insert(1, "ball")
elif "local_ball_num" in df.columns:
    cols.insert(1, "local_ball_num")

# show first few balls that are tagged Powerplay
print(pp.loc[pp["phase"] == "Powerplay", cols].head(30).to_string(index=False))

print("\nTotal Powerplay runs (from df):", pp.loc[pp["phase"] == "Powerplay", "runs.total"].sum())

# manual check - first 4 overs manually (0,1,2,3)
manual = pp[pp["over"] <= 3]
print("Manual 0–3 overs run sum (ground truth):", manual["runs.total"].sum())