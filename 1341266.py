import pandas as pd
df = pd.read_parquet("t20_data.parquet")
pp = df[(df["match_id"]=="1341266") & (df["innings"]==2)]
print("Powerplay (phase flagged):", pp[pp["phase"]=="Powerplay"]["runs.total"].sum())
print("Rows tagged Powerplay:", len(pp[pp["phase"]=="Powerplay"]))
print("Manual overs 0..3 runs:", pp[pp["over"].between(0,3)]["runs.total"].sum())
print(pp.loc[pp["over"].between(0,3), ["over","ball_float","runs.total","phase","is_valid_delivery"]].to_string(index=False))
