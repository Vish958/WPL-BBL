import pandas as pd
df = pd.read_parquet('t20_data_with_drs.parquet')
print(df.shape)
print(df.dtypes)
print(df.memory_usage(deep=True).sum() / 1024**2, "MB")