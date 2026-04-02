import pandas as pd
import json
import os
from glob import glob
import logging
from typing import Optional, Tuple, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

JSON_DIR = "/Users/vishwesh/Documents/WPL&BBL/data"  # Change if needed
DATA_DEST = "t20_data.parquet"

LEAGUE_START_DATES = {
    'WBBL': '2020-10-25', 'MBBL': '2020-12-10',
    'WPL': '2023-03-04', 'SA20': '2023-01-10', 'IPL': '2008-04-18'
}

LEAGUE_PP_DEFAULT = {
    'WBBL': (0.0, 3 + 5/6), 'MBBL': (0.0, 3 + 5/6),
    'WPL': (0.0, 5 + 5/6), 'SA20': (0.0, 5 + 5/6),
}

def notation_to_ball_float(notation) -> float:
    try:
        s = str(notation)
        if '.' not in s:
            over = int(float(s))
            ball = 1
        else:
            parts = s.split('.')
            over = int(float(parts[0])) if parts[0] != '' else 0
            ball = int(float(parts[1]))
            if ball < 1: ball = 1
            if ball > 6: ball = 6
        return over + (ball - 1) / 6.0
    except Exception:
        return 0.0

def detect_league(event_name, gender):
    e = (event_name or '').lower()
    if 'wpl' in e or "women's premier league" in e: return 'WPL'
    if 'big bash' in e: return 'WBBL' if gender == 'female' else 'MBBL'
    if 'sa20' in e: return 'SA20'
    if 'ipl' in e or 'indian premier league' in e: return 'IPL'
    return 'OTHER'

# Leagues that have Power Surge (BBL only)
BBL_LEAGUES = {'WBBL', 'MBBL'}

def get_powerplay_phases(powerplays: List[dict], league: str, inference=False, innings_deliveries=None):
    pp_mand = pp_surge = None
    for pp in powerplays or []:
        t = pp.get('type')
        from_n = pp.get('from')
        to_n = pp.get('to')
        if from_n is None or to_n is None: continue
        f = notation_to_ball_float(from_n)
        tt = notation_to_ball_float(to_n)
        if t == 'mandatory': pp_mand = (f, tt)
        # Power Surge (batting powerplay) only applies to BBL leagues
        elif t == 'batting' and league in BBL_LEAGUES: 
            pp_surge = (f, tt)

    if not pp_mand: pp_mand = LEAGUE_PP_DEFAULT.get(league)

    # Inference for Power Surge only applies to BBL leagues
    if league in BBL_LEAGUES and not pp_surge and inference and innings_deliveries and len(innings_deliveries) > 0:
        df = pd.DataFrame(innings_deliveries)
        df_valid = df[df['over'] >= 10]
        if not df_valid.empty:
            runs_by_over = df_valid.groupby('over')['runs.total'].sum()
            best_sum = -1
            best_start = None
            for o in runs_by_over.index:
                if (o + 1) in runs_by_over.index:
                    s = runs_by_over.loc[o] + runs_by_over.loc[o + 1]
                    if s > best_sum:
                        best_sum = s
                        best_start = o
            if best_start is not None:
                pp_surge = (best_start + 0/6.0, best_start + 1 + 5/6.0)
    return pp_mand, pp_surge

def assign_phase(ball_float, pp_mand, pp_surge, league):
    """
    Assign phase for a delivery:
    - WBBL/MBBL: Powerplay (mandatory), Power Surge (batting), Middle, Death (16+)
    - WPL/SA20/IPL: Powerplay (0-5.5), Middle (6-15.5), Death (16+)
    """
    # Powerplay check (mandatory powerplay)
    if pp_mand and pp_mand[0] is not None and pp_mand[1] is not None and pp_mand[0] <= ball_float <= pp_mand[1]: 
        return 'Powerplay'
    
    # Power Surge only applies to BBL leagues
    if league in BBL_LEAGUES and pp_surge and pp_surge[0] is not None and pp_surge[1] is not None and pp_surge[0] <= ball_float <= pp_surge[1]: 
        return 'Power Surge'
    
    # Death overs: 17-20 (ball_float >= 16.0)
    if ball_float >= 16.0: 
        return 'Death'
    
    return 'Middle'

def has_any_noball_marker(extras: dict) -> bool:
    if not extras: return False
    if extras.get('noballs', 0) or extras.get('no_ball', 0) or extras.get('noball', 0): return True
    for k in extras.keys():
        if 'noball' in k.lower() or 'no_ball' in k.lower(): return True
    return False

def has_wide(extras: dict) -> bool:
    if not extras: return False
    return extras.get('wides', 0) > 0 or extras.get('wide', 0) > 0

def get_impact_players_from_match(json_data):
    impact_names = set()
    for inning in json_data.get('innings', []):
        for over in inning.get('overs', []):
            for delivery in over.get('deliveries', []):
                if 'replacements' in delivery and 'match' in delivery['replacements']:
                    for rep in delivery['replacements']['match']:
                        if rep.get('reason', '').lower() == 'impact_player':
                            impact_names.add(rep['in'])
    return impact_names

def process_data(inference_power_surge=True):
    files = glob(os.path.join(JSON_DIR, "*.json"))
    rows = []
    xi_rows = []  # Playing XI rows

    for file in files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if data.get('info', {}).get('match_type') != 'T20': continue

            info = data.get('info', {})
            date = pd.to_datetime(info.get('dates', [None])[0]).date()
            year = pd.to_datetime(date).year
            event = info.get('event', {}).get('name', '') if info.get('event') else info.get('event', '')
            gender = info.get('gender', 'female')
            league = detect_league(event, gender)

            if league in LEAGUE_START_DATES and date < pd.to_datetime(LEAGUE_START_DATES[league]).date(): continue
            if league not in LEAGUE_START_DATES and year < 2020: continue

            teams = info.get('teams', [])
            match_id = os.path.basename(file).split('.')[0]
            match_impact_players = get_impact_players_from_match(data)
            
            # Extract outcome/winner data
            outcome = info.get('outcome', {})
            # Use 'winner' for normal wins; fall back to 'eliminator' for tied matches
            # resolved by super over. Leave as None only for true no-result matches.
            winner = outcome.get('winner') or outcome.get('eliminator')
            win_by = outcome.get('by', {})
            win_by_wickets = win_by.get('wickets', 0) if win_by else 0
            win_by_runs = win_by.get('runs', 0) if win_by else 0

            # ── Extract Playing XI ──
            players_dict = info.get('players', {})
            event_stage = info.get('event', {}).get('stage', 'group') if isinstance(info.get('event'), dict) else 'group'
            for team_name, player_list in players_dict.items():
                for player_name in player_list:
                    xi_rows.append({
                        'match_id': match_id,
                        'player': player_name,
                        'team': team_name,
                        'league': league,
                        'year': year,
                        'date': pd.to_datetime(date),
                        'winner': winner,
                        'event_stage': event_stage,
                        'teams': ' vs '.join(sorted(teams)),
                    })

            for inning_idx, inning in enumerate(data.get('innings', []), start=1):
                team = inning.get('team')  # batting team
                bowling_team = [t for t in teams if t != team][0] if len(teams) == 2 else team
                
                # Check if this is a super over innings
                is_super_over = 1 if inning.get('super_over', False) else 0
                
                # Assign innings label
                if is_super_over:
                    # Super over: BAT1-SO for first super over batting team, BAT2-SO for second
                    # inning_idx 3 or 4 for super overs after tie
                    if inning_idx == 3:
                        innings_label = 'BAT1-SO'
                    else:
                        innings_label = 'BAT2-SO'
                else:
                    # Regular innings: "Innings 1" or "Innings 2"
                    innings_label = f'Innings {inning_idx}'
                
                innings_num = inning_idx
                inning_deliveries = []
                declared_pp = inning.get('powerplays') or info.get('powerplays') or []
                pp_mand, pp_surge = get_powerplay_phases(declared_pp, league)

                for over in inning.get('overs', []):
                    over_num = over.get('over', 0)
                    legal_balls_in_over = 0
                    for d in over.get('deliveries', []):
                        extras = d.get('extras', {}) or {}
                        wides_flag = has_wide(extras)
                        noball_flag = has_any_noball_marker(extras)
                        is_valid = not (wides_flag or noball_flag)
                        ball_float = over_num + (legal_balls_in_over / 6.0)

                        inning_deliveries.append({
                            'over': over_num,
                            'ball_float': ball_float,
                            'runs.total': d.get('runs', {}).get('total', 0),
                            'is_valid_delivery': 1 if is_valid else 0,
                            'batter': d.get('batter'),
                            'bowler': d.get('bowler'),
                            'wides': extras.get('wides', 0),
                            'no_balls': extras.get('noballs', extras.get('no_ball', extras.get('noball', 0))),
                            'byes': extras.get('byes', 0),
                            'legbyes': extras.get('legbyes', 0),
                            'wicket_count': sum(1 for w in (d.get('wickets') or []) if w.get('kind') in [
                                'caught', 'bowled', 'lbw', 'stumped', 'hit wicket',
                                'caught and bowled', 'handled the ball', 'run out', 'obstructing the field'
                            ])
                        })
                        
                        # Check Impact Player Status for Batter AND Bowler
                        batter_name = d.get('batter')
                        bowler_name = d.get('bowler')
                        is_impact_batter = 1 if batter_name in match_impact_players else 0
                        is_impact_bowler = 1 if bowler_name in match_impact_players else 0

                        rows.append({
                            'match_id': match_id,
                            'created': pd.to_datetime(date),
                            'date': pd.to_datetime(date),
                            'year': year,
                            'teams': ' vs '.join(sorted(teams)),
                            'innings': innings_label,
                            'innings_num': innings_num,
                            'is_super_over': is_super_over,
                            'team': team,
                            'bowling_team': bowling_team,
                            'over': over_num,
                            'batter': batter_name,
                            'non_striker': d.get('non_striker'),
                            'bowler': bowler_name,
                            'runs.batter': d.get('runs', {}).get('batter', 0),
                            'runs.extras': d.get('runs', {}).get('extras', 0),
                            'runs.total': d.get('runs', {}).get('total', 0),
                            'wicket_count': sum(1 for w in (d.get('wickets') or []) if w.get('kind') in [
                                'caught', 'bowled', 'lbw', 'stumped', 'hit wicket',
                                'caught and bowled', 'handled the ball'
                            ]),
                            'extras_type': ','.join([k for k in ['wides','noballs','byes','legbyes'] if k in extras]) or None,
                            'is_valid_delivery': 1 if is_valid else 0,
                            'no_balls': 1 if noball_flag else 0,
                            'wides': extras.get('wides', 0),
                            'byes': extras.get('byes', 0),
                            'leg_byes': extras.get('legbyes', 0),
                            'phase': None,
                            'league': league,
                            'ball_float': ball_float,
                            'is_impact_batter': is_impact_batter,
                            'is_impact_bowler': is_impact_bowler,
                            'is_batter_out': 1 if any(w.get('player_out') == batter_name for w in (d.get('wickets') or [])) else 0,
                            'is_non_striker_out': 1 if any(w.get('player_out') == d.get('non_striker') for w in (d.get('wickets') or [])) else 0,
                            'player_out': next((w.get('player_out') for w in (d.get('wickets') or []) if w.get('player_out')), None),
                            'wicket_kind': next((w.get('kind') for w in (d.get('wickets') or []) if w.get('kind')), None),
                            'winner': winner,
                            'win_by_wickets': win_by_wickets,
                            'win_by_runs': win_by_runs
                        })

                        if is_valid:
                            legal_balls_in_over += 1

                if not pp_surge and inference_power_surge:
                    pp_mand_inf, pp_surge_inf = get_powerplay_phases([], league, inference=True, innings_deliveries=inning_deliveries)
                    if not pp_mand: pp_mand = pp_mand_inf
                    if pp_surge_inf: pp_surge = pp_surge_inf

                n = len(inning_deliveries)
                if n > 0:
                    for r in rows[-n:]:
                        r['phase'] = assign_phase(r['ball_float'], pp_mand, pp_surge, league)

        except Exception as e:
            logger.error(f"Error {file}: {e}")

    if rows:
        df = pd.DataFrame(rows)
        df['created'] = pd.to_datetime(df['created'])
        # ensure numeric columns
        for c in ['runs.total','runs.batter','wides','byes','leg_byes','no_balls','is_valid_delivery','wicket_count', 'is_impact_batter', 'is_impact_bowler', 'is_batter_out', 'is_non_striker_out', 'is_super_over']:
            if c not in df.columns:
                df[c] = 0
        df.to_parquet(DATA_DEST, index=False)
        logger.info(f"Saved: {DATA_DEST} ({len(df):,} rows)")
    else:
        logger.info("No rows processed.")

    # ── Save Playing XI parquet ──
    if xi_rows:
        xi_df = pd.DataFrame(xi_rows)
        xi_df['date'] = pd.to_datetime(xi_df['date'])
        xi_dest = os.path.join(os.path.dirname(DATA_DEST), 'playing_xi.parquet')
        xi_df.to_parquet(xi_dest, index=False)
        logger.info(f"Saved: {xi_dest} ({len(xi_df):,} rows, {xi_df['match_id'].nunique():,} matches)")

if __name__ == '__main__':
    process_data(inference_power_surge=True)