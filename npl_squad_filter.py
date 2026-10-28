import os
import re
import pandas as pd
import streamlit as st

SQUAD_FILE = os.path.join(os.path.dirname(__file__), "NPL_2026_Players.xlsx")
JSON_ROSTER = os.path.join(os.path.dirname(__file__), "npl_2026_teams_players.json")

@st.cache_data
def load_npl_2026_squads(file_path=SQUAD_FILE):
    """Load all NPL 2026 team squads with player metadata."""
    if os.path.exists(JSON_ROSTER):
        try:
            with open(JSON_ROSTER, 'r', encoding='utf-8') as f:
                import json
                data = json.load(f)
            squads = {}
            for item in data:
                team = item.get('Team', 'Unknown')
                if team not in squads:
                    squads[team] = []
                squads[team].append(item)
            return squads
        except Exception:
            pass

    if not os.path.exists(file_path):
        return {}
    try:
        df = pd.read_excel(file_path, sheet_name=0)
        squads = {}
        for team, group in df.groupby('Team'):
            squads[team] = group.to_dict(orient='records')
        return squads
    except Exception as e:
        print(f"Error loading NPL 2026 squads: {e}")
        return {}

def filter_by_npl_2026_squad(df, key_prefix="npl_sf"):
    """
    Renders NPL 2026 Franchise selector in sidebar with a Toggle (Enable/Disable).
    Filters df for data matching players in the selected NPL 2026 squad when enabled.
    Attributes team name to selected franchise and masks non-squad player names.
    """
    squads = load_npl_2026_squads()
    if not squads or df.empty:
        return df

    st.sidebar.markdown("---")
    st.sidebar.subheader("🏆 NPL 2026 Squad Base Filter")
    
    enable_filter_key = f"{key_prefix}_enable_npl_squad_filter"
    selected_team_key = f"{key_prefix}_selected_npl_franchise"

    enable_filter = st.sidebar.toggle(
        "Enable NPL 2026 Squad Filter",
        value=True,
        key=enable_filter_key
    )
    st.session_state['enable_npl_squad_filter'] = enable_filter
    
    if not enable_filter:
        st.sidebar.caption("🌐 Showing **Overall / All NPL Dataset**")
        st.sidebar.markdown("---")
        return df

    team_list = sorted([t for t in squads.keys() if 'Unsold' not in t])
    selected_team = st.sidebar.selectbox(
        "Select NPL 2026 Franchise",
        team_list,
        index=0,
        key=selected_team_key
    )
    st.session_state['selected_npl_franchise'] = selected_team
    
    team_roster = squads.get(selected_team, [])
    squad_player_names = set()
    for p in team_roster:
        squad_player_names.add(p.get('Full Name', ''))
        squad_player_names.add(p.get('Player Name', ''))
        squad_player_names.add(f"{p.get('First Name', '')} {p.get('Last Name', '')}".strip())
        if p.get('Last Name'):
            squad_player_names.add(p.get('Last Name'))
        if p.get('First Name') and p.get('Last Name'):
            squad_player_names.add(f"{p.get('First Name')[0]} {p.get('Last Name')}")
    squad_player_names.discard('')
    
    # Filter df by squad players or matches involving the team
    mask_player = (
        df['batter'].astype(str).isin(squad_player_names) |
        df['bowler'].astype(str).isin(squad_player_names) |
        (df['player_dismissed'].astype(str).isin(squad_player_names) if 'player_dismissed' in df.columns else False) |
        (df['team'].astype(str) == selected_team) |
        (df['bowling_team'].astype(str) == selected_team)
    )
    
    filtered_df = df[mask_player].copy()

    # Cast string columns to prevent categorical dtype issues
    for c in ['batter', 'bowler', 'player_dismissed', 'team', 'bowling_team']:
        if c in filtered_df.columns and isinstance(filtered_df[c].dtype, pd.CategoricalDtype):
            filtered_df[c] = filtered_df[c].astype(str)

    st.sidebar.info(
        f"**NPL Squad Filter ACTIVE**\n\n"
        f"🎯 **Franchise:** {selected_team}\n\n"
        f"👥 {len(team_roster)} Official Players | 📊 {len(filtered_df)} Balls"
    )
    st.sidebar.markdown("---")
    
    return filtered_df
