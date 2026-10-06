import pandas as pd
import json
import os
from glob import glob
import logging
from typing import Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

JSON_DIR = "/Users/vishwesh/Documents/WPL&BBL/data"  # Change if needed
JSON_DIR_WT20I = "/Users/vishwesh/Documents/WPL&BBL/data/t20i_female_json"  # Women's T20I JSON files
JSON_DIR_AFG_ODI = "/Users/vishwesh/Documents/WPL&BBL/Male_ODI_Data/odis_male_json/Afghanistan Games"  # Afghanistan ODI files
JSON_DIR_MENS_ODI = "/Users/vishwesh/Documents/WPL&BBL/Male_ODI_Data/odis_male_json"  # All Men's ODI files
JSON_DIR_MENS_T20I = "/Users/vishwesh/Documents/WPL&BBL/Male T20I "  # All Men's T20I files
JSON_DIR_NPL = "/Users/vishwesh/Documents/WPL&BBL/data/npl_json" # All Nepal Premier League files
DATA_DEST = "t20_data.parquet"

# Load player name mapping dictionary
NAME_MAP = {}
mapping_path = "/Users/vishwesh/Documents/WPL&BBL/player_name_map.json"
if os.path.exists(mapping_path):
    try:
        with open(mapping_path, 'r', encoding='utf-8') as f:
            NAME_MAP = json.load(f)
        logger.info(f"Loaded {len(NAME_MAP)} player name mappings from {mapping_path}")
    except Exception as e:
        logger.error(f"Error loading player_name_map.json: {e}")

LEAGUE_START_DATES = {
    'WBBL': '2020-10-25', 'MBBL': '2020-12-10',
    'WPL': '2023-03-04', 'SA20': '2023-01-10', 'IPL': '2008-04-18',
    'MLC': '2023-07-13',
    'WT20I': '2000-01-01',  # Women's T20 Internationals — include all dates
    'MENS_ODI': '2002-01-01',  # All Men's ODI matches
    'MENS_T20I': '2020-01-01',  # Men's T20 Internationals from Jan 1 2020
    'NPL': '2024-11-30',
}

LEAGUE_PP_DEFAULT = {
    'WBBL': (0.0, 3 + 5/6), 'MBBL': (0.0, 3 + 5/6),
    'WPL': (0.0, 5 + 5/6), 'SA20': (0.0, 5 + 5/6),
    'WT20I': (0.0, 5 + 5/6),  # Women's T20I: standard 6-over powerplay
    'MENS_ODI': (0.0, 9 + 5/6),  # ODI: mandatory 10-over powerplay
    'MENS_T20I': (0.0, 5 + 5/6),  # Men's T20I: standard 6-over powerplay
    'NPL': (0.0, 5 + 5/6),
}

# Leagues that use ODI (50-over) format — death starts at over 40
ODI_LEAGUES = {'MENS_ODI'}

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

def detect_league(event_name, gender, match_type='T20', teams=None):
    e = (event_name or '').lower()
    if 'nepal premier league' in e or 'npl' in e: return 'NPL'
    if 'wpl' in e or "women's premier league" in e: return 'WPL'
    if 'big bash' in e: return 'WBBL' if gender == 'female' else 'MBBL'
    if 'sa20' in e: return 'SA20'
    if 'ipl' in e or 'indian premier league' in e: return 'IPL'
    if 'major league cricket' in e: return 'MLC'
    # Men's ODI matches (including Afghanistan Games)
    if match_type == 'ODI' and gender == 'male': return 'MENS_ODI'
    # Women's T20 Internationals: any female T20 that isn't a known franchise league
    if gender == 'female': return 'WT20I'
    # Men's T20 Internationals: any male T20 that isn't a known franchise league
    if match_type == 'T20' and gender == 'male': return 'MENS_T20I'
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
        if t == 'mandatory':
            # ODI JSONs have 3 mandatory blocks (PP / Middle / Death).
            # Only take the FIRST (lowest from_n) — that's the actual powerplay.
            if pp_mand is None or f < pp_mand[0]:
                pp_mand = (f, tt)
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
    - MENS_ODI: Powerplay (0-9.5), Middle (10-39.5), Death (40+)
    """
    # Powerplay check (mandatory powerplay)
    if pp_mand and pp_mand[0] is not None and pp_mand[1] is not None and pp_mand[0] <= ball_float <= pp_mand[1]: 
        return 'Powerplay'
    
    # Power Surge only applies to BBL leagues
    if league in BBL_LEAGUES and pp_surge and pp_surge[0] is not None and pp_surge[1] is not None and pp_surge[0] <= ball_float <= pp_surge[1]: 
        return 'Power Surge'
    
    # ODI: Death overs are 41-50 (ball_float >= 40.0); T20: Death overs are 17-20 (ball_float >= 16.0)
    death_threshold = 40.0 if league in ODI_LEAGUES else 16.0
    if ball_float >= death_threshold: 
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

def _resolve_name(raw_name: str, delivery_names: set) -> str:
    """
    Resolve an impact-player name from the 'replacements' block to the exact
    name used in deliveries, handling common abbreviation mismatches.

    Matching priority:
      1. Exact match
      2. Same surname + replacement initials are a prefix of the delivery initials
         (e.g. 'Rahul Tewatia' -> 'R Tewatia', 'Ravindra Jadeja' -> 'RA Jadeja')
      3. Surname-only fallback (last word matches)

    Returns the matched delivery name, or the original raw_name if nothing fits.
    """
    if raw_name in delivery_names:
        return raw_name

    raw_parts  = raw_name.split()
    raw_surname = raw_parts[-1].lower()
    # Build initials string for the raw name (e.g. 'Ravindra Ashwin' -> 'RA')
    raw_initials = ''.join(p[0].upper() for p in raw_parts[:-1])

    surname_matches = []
    for dname in delivery_names:
        d_parts = dname.split()
        if not d_parts:
            continue
        d_surname = d_parts[-1].lower()
        if d_surname != raw_surname:
            continue
        surname_matches.append(dname)
        # Build initials for the delivery name
        d_initials = ''.join(p[0].upper() for p in d_parts[:-1])
        # Accept if one initials string is a prefix of the other
        # (covers 'R' vs 'RA', 'RA' vs 'R', 'Rahul' vs 'R', etc.)
        if raw_initials.startswith(d_initials) or d_initials.startswith(raw_initials):
            logger.info(
                f"Impact-player name resolved: '{raw_name}' -> '{dname}'"
            )
            return dname

    # Surname-only fallback: if exactly one candidate shares the surname, use it
    if len(surname_matches) == 1:
        logger.info(
            f"Impact-player name resolved (surname fallback): '{raw_name}' -> '{surname_matches[0]}'"
        )
        return surname_matches[0]

    logger.warning(
        f"Impact-player name '{raw_name}' could not be resolved to a delivery name. "
        f"Candidates: {surname_matches}. Using raw name (player may not have batted/bowled)."
    )
    return raw_name


def get_impact_players_from_match(json_data):
    """
    Extract the set of impact-player names (as they appear in deliveries)
    from a match JSON. Automatically resolves abbreviation mismatches between
    the 'replacements' block and the actual batter/bowler names in deliveries.
    """
    # Step 1: collect every name that actually appears in deliveries
    delivery_names: set = set()
    for inning in json_data.get('innings', []):
        for over in inning.get('overs', []):
            for delivery in over.get('deliveries', []):
                if delivery.get('batter'):      delivery_names.add(NAME_MAP.get(delivery['batter'], delivery['batter']))
                if delivery.get('bowler'):      delivery_names.add(NAME_MAP.get(delivery['bowler'], delivery['bowler']))
                if delivery.get('non_striker'): delivery_names.add(NAME_MAP.get(delivery['non_striker'], delivery['non_striker']))

    # Step 2: collect replacement names and resolve each one
    impact_names: set = set()
    for inning in json_data.get('innings', []):
        for over in inning.get('overs', []):
            for delivery in over.get('deliveries', []):
                if 'replacements' in delivery and 'match' in delivery['replacements']:
                    for rep in delivery['replacements']['match']:
                        if rep.get('reason', '').lower() == 'impact_player':
                            resolved = _resolve_name(rep['in'], delivery_names)
                            impact_names.add(resolved)
    return impact_names

def _process_single_file(args):
    """Process one JSON file. Returns (rows, xi_rows). Thread-safe — no shared state."""
    file, inference_power_surge = args
    rows = []
    xi_rows = []
    match_id = os.path.basename(file).split('.')[0].replace('_espn', '')
    try:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        match_type = data.get('info', {}).get('match_type', '')
        if match_type not in ('T20', 'ODI'):
            return rows, xi_rows, {
                'match_id': match_id,
                'file': os.path.basename(file),
                'league': 'N/A',
                'date': 'N/A',
                'reason': f"Skip: Unsupported match type ({match_type})"
            }

        info = data.get('info', {})
        date = pd.to_datetime(info.get('dates', [None])[0]).date()
        year = pd.to_datetime(date).year
        event = info.get('event', {}).get('name', '') if info.get('event') else info.get('event', '')
        gender = info.get('gender', 'male')
        teams = info.get('teams', [])
        league = detect_league(event, gender, match_type=match_type, teams=teams)

        if league in LEAGUE_START_DATES and date < pd.to_datetime(LEAGUE_START_DATES[league]).date():
            return rows, xi_rows, {
                'match_id': match_id,
                'file': os.path.basename(file),
                'league': league,
                'date': str(date),
                'reason': f"Skip: Before League Start Date ({LEAGUE_START_DATES[league]})"
            }
        if league not in LEAGUE_START_DATES and year < 2020:
            return rows, xi_rows, {
                'match_id': match_id,
                'file': os.path.basename(file),
                'league': league,
                'date': str(date),
                'reason': "Skip: Before 2020 (other leagues)"
            }

        match_impact_players = get_impact_players_from_match(data)
        outcome = info.get('outcome', {})
        winner = outcome.get('winner') or outcome.get('eliminator')
        win_by = outcome.get('by', {})
        win_by_wickets = win_by.get('wickets', 0) if win_by else 0
        win_by_runs = win_by.get('runs', 0) if win_by else 0

        event_stage = ''
        if isinstance(info.get('event'), dict):
            event_stage = info.get('event', {}).get('stage', '')
            if not event_stage:
                mn = info.get('event', {}).get('match_number', '')
                if isinstance(mn, str) and not mn.isdigit():
                    event_stage = mn
        if not event_stage:
            event_stage = 'group'

        # Playing XI
        players_dict = info.get('players', {})
        for team_name, player_list in players_dict.items():
            for player_name in player_list:
                mapped_player = NAME_MAP.get(player_name, player_name)
                xi_rows.append({
                    'match_id': match_id, 'player': mapped_player, 'team': team_name,
                    'league': league, 'year': year, 'date': pd.to_datetime(date),
                    'winner': winner, 'event_stage': event_stage,
                    'teams': ' vs '.join(sorted(teams)),
                })

        for inning_idx, inning in enumerate(data.get('innings', []), start=1):
            team = inning.get('team')
            bowling_team = [t for t in teams if t != team][0] if len(teams) == 2 else team
            is_super_over = 1 if inning.get('super_over', False) else 0
            if is_super_over:
                innings_label = 'BAT1-SO' if inning_idx == 3 else 'BAT2-SO'
            else:
                innings_label = f'Innings {inning_idx}'
            innings_num = inning_idx
            inning_deliveries = []
            inning_rows = []
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

                    raw_batter = d.get('batter')
                    raw_bowler = d.get('bowler')
                    raw_non_striker = d.get('non_striker')

                    batter_name = NAME_MAP.get(raw_batter, raw_batter)
                    bowler_name = NAME_MAP.get(raw_bowler, raw_bowler)
                    non_striker_name = NAME_MAP.get(raw_non_striker, raw_non_striker)

                    raw_player_out = next((w.get('player_out') for w in (d.get('wickets') or []) if w.get('player_out')), None)
                    player_out_name = NAME_MAP.get(raw_player_out, raw_player_out) if raw_player_out else None

                    inning_deliveries.append({
                        'over': over_num, 'ball_float': ball_float,
                        'runs.total': d.get('runs', {}).get('total', 0),
                        'is_valid_delivery': 1 if is_valid else 0,
                        'batter': batter_name, 'bowler': bowler_name,
                        'wides': extras.get('wides', 0),
                        'no_balls': extras.get('noballs', extras.get('no_ball', extras.get('noball', 0))),
                        'byes': extras.get('byes', 0), 'legbyes': extras.get('legbyes', 0),
                        'wicket_count': sum(1 for w in (d.get('wickets') or []) if w.get('kind') in [
                            'caught', 'bowled', 'lbw', 'stumped', 'hit wicket', 'caught and bowled', 'handled the ball'
                        ])
                    })

                    is_impact_batter = 1 if batter_name in match_impact_players else 0
                    is_impact_bowler = 1 if bowler_name in match_impact_players else 0

                    inning_rows.append({
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
                        'non_striker': non_striker_name,
                        'bowler': bowler_name,
                        'runs.batter': d.get('runs', {}).get('batter', 0),
                        'runs.extras': d.get('runs', {}).get('extras', 0),
                        'runs.total': d.get('runs', {}).get('total', 0),
                        'wicket_count': sum(1 for w in (d.get('wickets') or []) if w.get('kind') in [
                            'caught', 'bowled', 'lbw', 'stumped', 'hit wicket', 'caught and bowled', 'handled the ball'
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
                        'is_batter_out': 1 if player_out_name == batter_name else 0,
                        'is_non_striker_out': 1 if player_out_name == non_striker_name else 0,
                        'player_out': player_out_name,
                        'wicket_kind': next((w.get('kind') for w in (d.get('wickets') or []) if w.get('kind')), None),
                        'winner': winner,
                        'win_by_wickets': win_by_wickets,
                        'win_by_runs': win_by_runs,
                        'event_stage': event_stage
                    })

                    if is_valid:
                        legal_balls_in_over += 1

            if not pp_surge and inference_power_surge:
                pp_mand_inf, pp_surge_inf = get_powerplay_phases(
                    [], league, inference=True, innings_deliveries=inning_deliveries
                )
                if not pp_mand:
                    pp_mand = pp_mand_inf
                if pp_surge_inf:
                    pp_surge = pp_surge_inf

            # Assign phase (local to this inning — thread-safe)
            for r in inning_rows:
                r['phase'] = assign_phase(r['ball_float'], pp_mand, pp_surge, league)

            rows.extend(inning_rows)

    except Exception as e:
        logger.error(f"Error {file}: {e}")
        return [], [], {
            'match_id': match_id,
            'file': os.path.basename(file),
            'league': 'Error',
            'date': 'N/A',
            'reason': f"Error: {str(e)}"
        }

    return rows, xi_rows, None
def generate_excel_summary(df, exclusions, league_file_counts, report_name="match_ingestion_summary.xlsx"):
    summary_rows = []
    if not df.empty:
        # Group by league and find count, min, max
        grp = df.groupby('league', observed=False).agg(
            total_matches=('match_id', 'nunique'),
            first_match=('date', 'min'),
            last_match=('date', 'max')
        )
        for league, row in grp.iterrows():
            summary_rows.append({
                'League': league,
                'JSON Files Scanned': int(league_file_counts.get(league, row['total_matches'])),
                'Successfully Imported': int(row['total_matches']),
                'Earliest Match Date': str(row['first_match'].date()) if hasattr(row['first_match'], 'date') else str(row['first_match']),
                'Latest Match Date': str(row['last_match'].date()) if hasattr(row['last_match'], 'date') else str(row['last_match'])
            })
    
    summary_df = pd.DataFrame(summary_rows)
    excluded_df = pd.DataFrame(exclusions)
    if excluded_df.empty:
        excluded_df = pd.DataFrame(columns=['Match ID', 'File', 'League', 'Date', 'Reason for Exclusion'])
    else:
        excluded_df = excluded_df.rename(columns={
            'match_id': 'Match ID',
            'file': 'File',
            'league': 'League',
            'date': 'Date',
            'reason': 'Reason for Exclusion'
        })
        col_order = ['Match ID', 'File', 'League', 'Date', 'Reason for Exclusion']
        excluded_df = excluded_df[[c for c in col_order if c in excluded_df.columns]]

    try:
        with pd.ExcelWriter(report_name, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='League Summary', index=False)
            excluded_df.to_excel(writer, sheet_name='Excluded Matches', index=False)
        logger.info(f"Excel summary report written to: {report_name}")
    except Exception as e:
        logger.error(f"Failed to generate Excel report {report_name}: {e}")


def process_data(inference_power_surge=True):
    main_files = glob(os.path.join(JSON_DIR, "*.json"))

    wt20i_files = glob(os.path.join(JSON_DIR_WT20I, "*.json"))
    afg_files = glob(os.path.join(JSON_DIR_AFG_ODI, "*.json"))
    mens_odi_files = glob(os.path.join(JSON_DIR_MENS_ODI, "*.json"))
    mens_t20i_files = glob(os.path.join(JSON_DIR_MENS_T20I, "*.json"))
    npl_files = glob(os.path.join(JSON_DIR_NPL, "*.json"))
    files = main_files + wt20i_files + afg_files + mens_odi_files + mens_t20i_files + npl_files

    # Sort to prioritize *_espn.json (DRS data), then deduplicate by match_id
    files = sorted(files, key=lambda x: (not x.endswith('_espn.json'), x))
    seen_ids = set()
    unique_files = []
    for f in files:
        mid = os.path.basename(f).split('.')[0].replace('_espn', '')
        if mid not in seen_ids:
            seen_ids.add(mid)
            unique_files.append(f)

    logger.info(
        f"Processing {len(unique_files)} JSON files: "
        f"{len(main_files)} main T20 + {len(wt20i_files)} WT20I + "
        f"{len(afg_files)} Afghanistan ODI + {len(mens_odi_files)} Men's ODI + "
        f"{len(mens_t20i_files)} Men's T20I"
    )

    all_rows = []
    all_xi_rows = []
    all_exclusions = []
    file_leagues = []
    n_workers = min(8, (os.cpu_count() or 4))
    args = [(f, inference_power_surge) for f in unique_files]

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        for rows, xi_rows, exclusion in executor.map(_process_single_file, args):
            if exclusion:
                all_exclusions.append(exclusion)
                file_leagues.append(exclusion['league'])
            else:
                all_rows.extend(rows)
                all_xi_rows.extend(xi_rows)
                if rows:
                    file_leagues.append(rows[0]['league'])

    from collections import Counter
    league_file_counts = dict(Counter(file_leagues))

    if all_rows:
        df = pd.DataFrame(all_rows)
        df['created'] = pd.to_datetime(df['created'])
        for c in ['runs.total','runs.batter','wides','byes','leg_byes','no_balls',
                  'is_valid_delivery','wicket_count','is_impact_batter','is_impact_bowler',
                  'is_batter_out','is_non_striker_out','is_super_over']:
            if c not in df.columns:
                df[c] = 0
        # Optimize types to save ~90% memory at runtime
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype('category')
        for col in df.select_dtypes(include=['int64']).columns:
            df[col] = pd.to_numeric(df[col], downcast='integer')
        df.to_parquet(DATA_DEST, index=False)
        logger.info(f"Saved: {DATA_DEST} ({len(df):,} rows)")
        
        generate_excel_summary(df, all_exclusions, league_file_counts, "match_ingestion_summary.xlsx")
    else:
        logger.info("No rows processed.")

    if all_xi_rows:
        xi_df = pd.DataFrame(all_xi_rows)
        xi_df['date'] = pd.to_datetime(xi_df['date'])
        xi_dest = os.path.join(os.path.dirname(DATA_DEST), 'playing_xi.parquet')
        # Optimize types to save ~90% memory at runtime
        for col in xi_df.select_dtypes(include=['object']).columns:
            xi_df[col] = xi_df[col].astype('category')
        for col in xi_df.select_dtypes(include=['int64']).columns:
            xi_df[col] = pd.to_numeric(xi_df[col], downcast='integer')
        xi_df.to_parquet(xi_dest, index=False)
        logger.info(f"Saved: {xi_dest} ({len(xi_df):,} rows, {xi_df['match_id'].nunique():,} matches)")

if __name__ == '__main__':
    process_data(inference_power_surge=True)