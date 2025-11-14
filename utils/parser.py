# utils/parser.py
import json
import pandas as pd
from pathlib import Path

def parse_cricsheet_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    info = data['info']
    innings = data.get('innings', [])
    
    # SKIP ABANDONED WITH TOSS
    if not innings or len(innings) == 0:
        return pd.DataFrame()

    match_id = Path(file_path).stem
    date = info['dates'][0]
    teams = info['teams']

    # League
    event = info.get('event', {}).get('name', '')
    gender = info.get('gender', 'female')
    if 'WPL' in event or 'Women\'s Premier League' in event:
        league = 'WPL'
    elif 'Big Bash' in event:
        league = 'WBBL' if gender == 'female' else 'MBBL'
    elif 'SA20' in event:
        league = 'SA20'
    else:
        league = 'OTHER'

    # Powerplay
    pp_mand = None
    pp_surge = None
    for pp in info.get('powerplays', []):
        if pp.get('type') == 'mandatory':
            pp_mand = (pp['from'], pp['to'])
        elif pp.get('type') == 'batting':
            pp_surge = (pp['from'], pp['to'])

    rows = []
    for inning_idx, inning in enumerate(innings):
        batting_team = inning['team']
        bowling_team = [t for t in teams if t != batting_team][0]

        legal_ball_in_over = 0
        for over in inning.get('overs', []):
            over_num = over['over']
            legal_ball_in_over = 0  # Reset per over

            for ball in over['deliveries']:
                batter = ball['batter']
                bowler = ball['bowler']
                runs_bat = ball['runs']['batter']
                runs_ext = ball['runs']['extras']
                total_runs = ball['runs']['total']

                wicket = 'wickets' in ball
                kind = ball['wickets'][0]['kind'] if wicket else None
                out_player = ball['wickets'][0]['player_out'] if wicket else None

                extras = ball.get('extras', {})
                wide = 'wides' in extras
                noball = 'noballs' in extras or 'no_balls' in extras

                is_legal = not (wide or noball)
                if is_legal:
                    legal_ball_in_over += 1

                ball_float = over_num + legal_ball_in_over / 6

                phase = 'Middle'
                if pp_mand and pp_mand[0] <= ball_float <= pp_mand[1]:
                    phase = 'Powerplay'
                elif pp_surge and pp_surge[0] <= ball_float <= pp_surge[1]:
                    phase = 'Power Surge'

                rows.append({
                    'match_id': match_id,
                    'date': date,
                    'league': league,
                    'batting_team': batting_team,
                    'bowling_team': bowling_team,
                    'inning': inning_idx + 1,
                    'over': over_num,
                    'legal_ball': legal_ball_in_over,
                    'batter': batter,
                    'bowler': bowler,
                    'runs_bat': runs_bat,
                    'runs_ext': runs_ext,
                    'total_runs': total_runs,
                    'wicket': wicket,
                    'kind': kind,
                    'out_player': out_player,
                    'wide': wide,
                    'noball': noball,
                    'phase': phase
                })

    df = pd.DataFrame(rows)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df