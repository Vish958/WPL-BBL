# preprocessing_local_t20.py
# Preprocessing script that includes DRS (review) data extraction for UPT20 and DPL
# By Vishwesh Gaur / Antigravity coding assistant

import pandas as pd
import json
import os
from glob import glob
import logging
from typing import Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

SCRAPER_BASE_DIR = "/Users/vishwesh/Downloads/CricketInsights-main/CricketInsights-1"
DATA_DEST = "local_t20_data_with_drs.parquet"

LEAGUE_START_DATES = {
    'UPT20': '2023-01-01',
    'DPL': '2024-01-01',
}

LEAGUE_PP_DEFAULT = {
    'UPT20': (0.0, 5 + 5/6),
    'DPL': (0.0, 5 + 5/6),
}

# No ODI format or BBL power surge in local leagues
BBL_LEAGUES = set()
ODI_LEAGUES = set()

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

def detect_league(event_name, filepath):
    e = (event_name or '').lower()
    fp = filepath.lower()
    if 'delhi premier' in e or 'dpl' in e or 'dpl_scraper' in fp:
        return 'DPL'
    if 'uttar pradesh' in e or 'upt20' in e or 'upt20_scraper' in fp or 'upt20_cricbuzz_scraper' in fp:
        return 'UPT20'
    return 'OTHER'

def get_powerplay_phases(powerplays: List[dict], league: str, inference=False, innings_deliveries=None):
    pp_mand = pp_surge = None
    for pp in powerplays or []:
        t = pp.get('type')
        from_n = pp.get('from')
        to_n = pp.get('to')
        if from_n is None or to_n is None: continue
        f = notation_to_ball_float(from_n)
        tt = notation_to_ball_float(to_n)
        if t == 'mandatory':
            if pp_mand is None or f < pp_mand[0]:
                pp_mand = (f, tt)
        elif t == 'batting' and league in BBL_LEAGUES:
            pp_surge = (f, tt)

    if not pp_mand: pp_mand = LEAGUE_PP_DEFAULT.get(league)
    return pp_mand, pp_surge

def assign_phase(ball_float, pp_mand, pp_surge, league):
    if pp_mand and pp_mand[0] is not None and pp_mand[1] is not None and pp_mand[0] <= ball_float <= pp_mand[1]: 
        return 'Powerplay'
    
    if league in BBL_LEAGUES and pp_surge and pp_surge[0] is not None and pp_surge[1] is not None and pp_surge[0] <= ball_float <= pp_surge[1]: 
        return 'Power Surge'
    
    death_threshold = 16.0
    if ball_float >= death_threshold: 
        return 'Death'
    
    return 'Middle'

def clean_innings_overs(overs):
    """
    Deduplicate deliveries in an innings' overs.
    If a batter is dismissed, and we see duplicate wickets for the same player,
    we merge the details (e.g. fielders) and remove the duplicate delivery.
    """
    seen_dismissals = {}
    deliveries_to_remove = set()
    for over_idx, over in enumerate(overs):
        for del_idx, d in enumerate(over.get('deliveries', [])):
            wickets = d.get('wickets', []) or []
            for w in wickets:
                p_out = w.get('player_out')
                if p_out:
                    if p_out in seen_dismissals:
                        prev_over_idx, prev_del_idx, prev_w, prev_d = seen_dismissals[p_out]
                        bowler_kinds = {'caught', 'bowled', 'lbw', 'stumped', 'hit wicket', 'caught and bowled'}
                        if w.get('kind') in bowler_kinds and prev_w.get('kind') not in bowler_kinds:
                            prev_w['kind'] = w['kind']
                        if 'fielders' in w and not 'fielders' in prev_w:
                            prev_w['fielders'] = w['fielders']
                        deliveries_to_remove.add((over_idx, del_idx))
                    else:
                        seen_dismissals[p_out] = (over_idx, del_idx, w, d)
    new_overs = []
    for over_idx, over in enumerate(overs):
        new_deliveries = []
        for del_idx, d in enumerate(over.get('deliveries', [])):
            if (over_idx, del_idx) not in deliveries_to_remove:
                new_deliveries.append(d)
        if new_deliveries:
            over_copy = dict(over)
            over_copy['deliveries'] = new_deliveries
            new_overs.append(over_copy)
    return new_overs

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

def extract_review_data(delivery):
    """
    Extract DRS/review data from a delivery.
    Returns a dict with review fields or None if no review.
    """
    review = delivery.get('review')
    if not review:
        return {
            'has_review': 0,
            'review_by_team': None,
            'review_umpire': None,
            'review_batter': None,
            'review_decision': None,
            'review_type': None,
            'umpires_call': False
        }
    
    return {
        'has_review': 1,
        'review_by_team': review.get('by'),
        'review_umpire': review.get('umpire'),
        'review_batter': review.get('batter'),
        'review_decision': review.get('decision'),  # 'struck down' or 'upheld'
        'review_type': review.get('type'),  # 'wicket', etc.
        'umpires_call': review.get('umpires_call', False)
    }

def _process_single_file_drs(args):
    """Process one JSON file. Returns (rows, drs_count). Thread-safe."""
    file, inference_power_surge = args
    rows = []
    drs_count = 0
    # Strip _espn suffix if present (for DRS-enriched copies)
    match_id = os.path.basename(file).split('.')[0].replace('_espn', '')
    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        match_type = data.get('info', {}).get('match_type', '')
        if match_type not in ('T20', 'ODI'):
            return rows, drs_count

        info = data.get('info', {})
        date = pd.to_datetime(info.get('dates', [None])[0]).date()
        year = pd.to_datetime(date).year
        event = info.get('event', {}).get('name', '') if isinstance(info.get('event'), dict) else info.get('event', '')
        event_stage = ''
        if isinstance(info.get('event'), dict):
            event_stage = info.get('event', {}).get('stage', '')
            if not event_stage:
                mn = info.get('event', {}).get('match_number', '')
                if isinstance(mn, str) and not mn.isdigit():
                    event_stage = mn
        gender = info.get('gender', 'male')
        teams = info.get('teams', [])
        league = detect_league(event, file)

        if league in LEAGUE_START_DATES and date < pd.to_datetime(LEAGUE_START_DATES[league]).date():
            return rows, drs_count
        if league not in LEAGUE_START_DATES and year < 2020:
            return rows, drs_count

        match_impact_players = get_impact_players_from_match(data)
        outcome = info.get('outcome', {})
        winner = outcome.get('winner') or outcome.get('eliminator')
        win_by = outcome.get('by', {})
        win_by_wickets = win_by.get('wickets', 0) if win_by else 0
        win_by_runs = win_by.get('runs', 0) if win_by else 0

        for inning_idx, inning in enumerate(data.get('innings', []), start=1):
            team = inning.get('team')
            bowling_team = [t for t in teams if t != team][0] if len(teams) == 2 else team
            innings_num = inning_idx
            inning_deliveries = []
            inning_rows = []
            declared_pp = inning.get('powerplays') or info.get('powerplays') or []
            pp_mand, pp_surge = get_powerplay_phases(declared_pp, league)

            for over in clean_innings_overs(inning.get('overs', [])):
                over_num = over.get('over', 0)
                legal_balls_in_over = 0
                for d in over.get('deliveries', []):
                    extras = d.get('extras', {}) or {}
                    wides_flag = has_wide(extras)
                    noball_flag = has_any_noball_marker(extras)
                    is_valid = not (wides_flag or noball_flag)
                    ball_float = over_num + (legal_balls_in_over / 6.0)

                    inning_deliveries.append({
                        'over': over_num, 'ball_float': ball_float,
                        'runs.total': d.get('runs', {}).get('total', 0),
                        'is_valid_delivery': 1 if is_valid else 0,
                        'batter': d.get('batter'), 'bowler': d.get('bowler'),
                        'wides': extras.get('wides', 0),
                        'no_balls': extras.get('noballs', extras.get('no_ball', extras.get('noball', 0))),
                        'byes': extras.get('byes', 0), 'legbyes': extras.get('legbyes', 0),
                        'wicket_count': sum(1 for w in (d.get('wickets') or []) if w.get('kind') in [
                            'caught', 'bowled', 'lbw', 'stumped', 'hit wicket', 'caught and bowled', 'handled the ball'
                        ])
                    })

                    batter_name = d.get('batter')
                    bowler_name = d.get('bowler')
                    is_impact_batter = 1 if batter_name in match_impact_players else 0
                    is_impact_bowler = 1 if bowler_name in match_impact_players else 0
                    review_data = extract_review_data(d)
                    if review_data['has_review']:
                        drs_count += 1

                    inning_rows.append({
                        'match_id': match_id,
                        'created': pd.to_datetime(date),
                        'date': pd.to_datetime(date),
                        'year': year,
                        'teams': ' vs '.join(sorted(teams)),
                        'innings': innings_num,
                        'team': team,
                        'bowling_team': bowling_team,
                        'over': over_num,
                        'batter': batter_name,
                        'bowler': bowler_name,
                        'runs.batter': d.get('runs', {}).get('batter', 0),
                        'runs.extras': d.get('runs', {}).get('extras', 0),
                        'runs.total': d.get('runs', {}).get('total', 0),
                        'wicket_count': sum(1 for w in (d.get('wickets') or []) if w.get('kind') in [
                            'caught', 'bowled', 'lbw', 'stumped', 'hit wicket',
                            'caught and bowled', 'handled the ball'
                        ]),
                        'team_wicket_count': sum(1 for w in (d.get('wickets') or []) if w.get('kind') not in [
                            'retired hurt', 'retired not out'
                        ]),
                        'wicket_kind': next((w.get('kind') for w in (d.get('wickets') or [])
                                             if w.get('kind') not in ('retired hurt', 'retired not out')), None),
                        'player_dismissed': next(
                            (w.get('player_out') for w in (d.get('wickets') or []) if w.get('player_out')), None
                        ),
                        'extras_type': ','.join([k for k in ['wides','noballs','byes','legbyes'] if k in extras]) or None,
                        'is_valid_delivery': 1 if is_valid else 0,
                        'no_balls': 1 if noball_flag else 0,
                        'wides': extras.get('wides', 0),
                        'byes': extras.get('byes', 0),
                        'leg_byes': extras.get('legbyes', 0),
                        'phase': None,
                        'league': league,
                        'event_stage': event_stage,
                        'ball_float': ball_float,
                        'is_impact_batter': is_impact_batter,
                        'is_impact_bowler': is_impact_bowler,
                        'winner': winner,
                        'win_by_wickets': win_by_wickets,
                        'win_by_runs': win_by_runs,
                        **review_data
                    })

                    if is_valid:
                        legal_balls_in_over += 1

            # Assign phase (done inside thread — fully local)
            for r in inning_rows:
                r['phase'] = assign_phase(r['ball_float'], pp_mand, pp_surge, league)

            rows.extend(inning_rows)

    except Exception as e:
        logger.error(f"Error {file}: {e}")

    return rows, drs_count

def process_local_t20():
    """Process all JSON files for UPT20 and DPL."""
    upt20_2023_files = glob(os.path.join(SCRAPER_BASE_DIR, "upt20_scraper/data/cricsheet/2023/*.json"))
    upt20_2024_files = glob(os.path.join(SCRAPER_BASE_DIR, "upt20_scraper/data/cricsheet/2024/*.json"))
    upt20_2025_files = glob(os.path.join(SCRAPER_BASE_DIR, "upt20_cricbuzz_scraper/data/cricsheet/2025/*.json"))
    
    dpl_2024_files = glob(os.path.join(SCRAPER_BASE_DIR, "dpl_scraper/data/cricsheet/2024/*.json"))
    dpl_2025_files = glob(os.path.join(SCRAPER_BASE_DIR, "dpl_scraper/data/cricsheet/2025/*.json"))
    
    files = upt20_2023_files + upt20_2024_files + upt20_2025_files + dpl_2024_files + dpl_2025_files
    
    logger.info(f"Total files found in scraper directories: {len(files)}")
    
    valid_files = []
    for f in files:
        if os.path.exists(f) and os.path.getsize(f) > 1000:
            try:
                with open(f, 'r', encoding='utf-8') as file:
                    d = json.load(file)
                balls_count = sum(len(o.get('deliveries', [])) for inn in d.get('innings', []) for o in inn.get('overs', []))
                if balls_count > 0:
                    valid_files.append(f)
                else:
                    logger.info(f"Skipping match with 0 deliveries: {f}")
            except Exception as e:
                logger.error(f"Error checking file {f}: {e}")
        else:
            logger.info(f"Skipping tiny/corrupt file: {f}")
            
    # Deduplicate by match ID (keep first occurrence)
    seen_ids = set()
    unique_files = []
    for f in valid_files:
        mid = os.path.basename(f).split('.')[0].replace('_espn', '')
        if mid not in seen_ids:
            seen_ids.add(mid)
            unique_files.append(f)

    logger.info(f"Processing {len(unique_files)} valid unique JSON files.")

    all_rows = []
    total_drs = 0
    n_workers = min(8, (os.cpu_count() or 4))
    args = [(f, False) for f in unique_files]

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        for rows, drs_count in executor.map(_process_single_file_drs, args):
            all_rows.extend(rows)
            total_drs += drs_count

    if all_rows:
        df = pd.DataFrame(all_rows)
        df['created'] = pd.to_datetime(df['created'])
        for c in ['runs.total','runs.batter','wides','byes','leg_byes','no_balls',
                  'is_valid_delivery','wicket_count','is_impact_batter','is_impact_bowler','has_review']:
            if c not in df.columns:
                df[c] = 0
        # Optimize types to save memory
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype('category')
        for col in df.select_dtypes(include=['int64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='integer')
            
        df.to_parquet(DATA_DEST, index=False)
        logger.info(f"Saved: {DATA_DEST} ({len(df):,} rows)")
        logger.info(f"Total DRS reviews extracted: {total_drs}")
    else:
        logger.info("No rows processed.")

if __name__ == '__main__':
    process_local_t20()
