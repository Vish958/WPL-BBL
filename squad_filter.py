import os
import re
import pandas as pd
import streamlit as st

SQUAD_FILE = os.path.join(os.path.dirname(__file__), "DPL 2026 teams.xlsx")

@st.cache_data
def load_2026_squads(file_path=SQUAD_FILE):
    """Load all 2026 team squads from DPL 2026 teams.xlsx."""
    if not os.path.exists(file_path):
        return {}
    try:
        xls = pd.ExcelFile(file_path)
        squads = {}
        for sheet in xls.sheet_names:
            if 'Weak Zone' in sheet:
                continue
            df_sheet = pd.read_excel(xls, sheet_name=sheet)
            if 'Player Name' in df_sheet.columns:
                names = (
                    df_sheet['Player Name']
                    .dropna()
                    .astype(str)
                    .str.replace(r'\s*\(.*?\)', '', regex=True)
                    .str.strip()
                    .tolist()
                )
                names = [n for n in names if n]
                if names:
                    squads[sheet] = sorted(list(set(names)))
        return squads
    except Exception as e:
        print(f"Error loading 2026 squads: {e}")
        return {}

def filter_by_2026_squad(df):
    """
    Renders 2026 Franchise selector in sidebar with a Toggle (Enable/Disable).
    Filters df for 2024 & 2025 data matching players in the selected 2026 squad when enabled.
    Attributes team name to selected franchise and masks non-squad player names.
    """
    squads = load_2026_squads()
    if not squads or df.empty:
        return df

    st.sidebar.markdown("---")
    st.sidebar.subheader("🏆 2026 Squad Base Filter")
    
    enable_filter = st.sidebar.toggle(
        "Enable 2026 Squad Base Filter",
        value=True,
        key="enable_2026_squad_filter"
    )
    
    if not enable_filter:
        st.sidebar.caption("🌐 Showing **Overall / Unfiltered Dataset**")
        st.sidebar.markdown("---")
        return df

    team_list = sorted(list(squads.keys()))
    selected_team = st.sidebar.selectbox(
        "Select 2026 Franchise",
        team_list,
        index=0,
        key="selected_2026_franchise"
    )
    
    squad_players = set(squads.get(selected_team, []))
    
    # Filter for 2024 and 2025 seasons
    if 'year' in df.columns:
        year_series = pd.to_numeric(df['year'], errors='coerce')
        mask_year = year_series.isin([2024, 2025])
    elif 'date' in df.columns:
        dates = pd.to_datetime(df['date'], errors='coerce')
        mask_year = dates.dt.year.isin([2024, 2025])
    else:
        mask_year = pd.Series(True, index=df.index)
        
    mask_player = (
        df['batter'].isin(squad_players) |
        df['bowler'].isin(squad_players) |
        (df['non_striker'].isin(squad_players) if 'non_striker' in df.columns else False) |
        (df['player_dismissed'].isin(squad_players) if 'player_dismissed' in df.columns else False)
    )
    
    filtered_df = df[mask_year & mask_player].copy()

    # Cast string columns to prevent categorical dtype issues
    for c in ['batter', 'bowler', 'non_striker', 'player_dismissed', 'team', 'bowling_team']:
        if c in filtered_df.columns and isinstance(filtered_df[c].dtype, pd.CategoricalDtype):
            filtered_df[c] = filtered_df[c].astype(str)

    # Attribute selected team to squad batters and squad bowlers
    if 'team' in filtered_df.columns:
        filtered_df['team'] = filtered_df['team'].astype(str)
        filtered_df.loc[filtered_df['batter'].isin(squad_players), 'team'] = selected_team

    if 'bowling_team' in filtered_df.columns:
        filtered_df['bowling_team'] = filtered_df['bowling_team'].astype(str)
        filtered_df.loc[filtered_df['bowler'].isin(squad_players), 'bowling_team'] = selected_team

    # Save original unmasked player names in _orig_ columns before masking so player metadata/handedness is preserved
    for col in ['batter', 'bowler', 'non_striker', 'player_dismissed']:
        if col in filtered_df.columns:
            filtered_df[f'_orig_{col}'] = filtered_df[col].copy()
            filtered_df[col] = filtered_df[col].where(filtered_df[col].isin(squad_players), None)
    
    st.sidebar.info(
        f"**Squad Filter ACTIVE**\n\n"
        f"🎯 **Team:** {selected_team}\n\n"
        f"👥 {len(squad_players)} Squad Players | 📊 {len(filtered_df)} Balls (2024-2025)"
    )
    st.sidebar.markdown("---")
    
    return filtered_df
