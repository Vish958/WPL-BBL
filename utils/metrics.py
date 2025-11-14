# utils/metrics.py
import pandas as pd
import numpy as np

def format_overs(balls):
    if balls == 0: return "0.0"
    return f"{balls // 6}.{balls % 6}"

def calculate_metrics(df):
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    legal = df[df['wide'] == False].copy()

    # BATTING
    bat = legal.groupby('batter').agg(
        runs=('runs_bat', 'sum'),
        balls=('legal_ball', 'count'),
        fours=('runs_bat', lambda x: (x == 4).sum()),
        sixes=('runs_bat', lambda x: (x == 6).sum())
    ).reset_index()

    outs = legal[legal['wicket'] & (legal['out_player'] == legal['batter'])]
    outs_count = outs.groupby('batter').size().reset_index(name='outs')
    bat = bat.merge(outs_count, on='batter', how='left').fillna({'outs': 0})

    bat['SR'] = (bat['runs'] / bat['balls'].replace(0, 1) * 100).round(2)
    bat['Avg'] = np.where(bat['outs'] > 0, (bat['runs'] / bat['outs']).round(1), '-')
    bat['BP4'] = np.where(bat['fours'] > 0, (bat['balls'] / bat['fours']).round(1), '-')
    bat['BP6'] = np.where(bat['sixes'] > 0, (bat['balls'] / bat['sixes']).round(1), '-')

    # BOWLING — LEGAL ONLY
    bowl = legal.groupby('bowler').agg(
        runs=('total_runs', 'sum'),
        balls=('legal_ball', 'count')
    ).reset_index()

    real_wkts = legal[
        legal['wicket'] &
        legal['kind'].isin(['bowled', 'caught', 'lbw', 'stumped', 'hit wicket'])
    ]
    real_wkts = real_wkts.groupby('bowler').size().reset_index(name='real_wkts')
    bowl = bowl.merge(real_wkts, on='bowler', how='left').fillna({'real_wkts': 0})
    bowl['real_wkts'] = bowl['real_wkts'].astype(int)

    bowl['overs_str'] = bowl['balls'].apply(format_overs)
    bowl['Econ'] = (bowl['runs'] / (bowl['balls'] / 6).replace(0, 1)).round(2)
    bowl['Avg'] = np.where(bowl['real_wkts'] > 0, (bowl['runs'] / bowl['real_wkts']).round(1), '-')
    bowl['SR'] = np.where(bowl['real_wkts'] > 0, (bowl['balls'] / bowl['real_wkts']).round(1), '-')

    return bat, bowl