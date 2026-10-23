# utils/auto_sync_ranji.py
import json
import logging
import os
import sys
import time
from pathlib import Path
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.bcci_parser import fetch_bcci_scorecard, convert_bcci_to_cricsheet

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('auto_sync_ranji')

DATA_DIR = REPO_ROOT / 'data' / 'BCCI Domestic' / 'International'
BCCI_API_BASE = 'https://stats.bcci.tv'
DEFAULT_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)',
    'Referer': 'https://www.bcci.tv/',
}

def is_match_concluded(file_path: Path) -> bool:
    if not file_path.exists():
        return False
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        info = d.get('info', {})
        outcome = info.get('outcome', {})
        if outcome.get('winner') or outcome.get('result') in ('draw', 'tie', 'no result'):
            return True
        summary = str(outcome.get('summary', '')).lower()
        if 'won by' in summary or 'match drawn' in summary:
            return True
    except Exception:
        pass
    return False

def discover_all_bcci_ranji_matches() -> dict:
    """Scan both fixtures and results endpoints to gather all Ranji matches."""
    matches = {}
    
    # 1. Results (completed / recent games)
    try:
        r = requests.get(f'{BCCI_API_BASE}/match/results/', headers=DEFAULT_HEADERS, timeout=10)
        if r.ok:
            for m in r.json().get('match', []):
                cname = (m.get('comp_name') or '').lower()
                if 'ranji trophy elite' in cname and 'plate' not in cname:
                    mid = int(m['match_id'])
                    matches[mid] = m
    except Exception as e:
        logger.warning(f'Error querying results: {e}')

    # 2. Fixtures (live / in-progress games)
    try:
        r = requests.get(f'{BCCI_API_BASE}/match/fixtures/', headers=DEFAULT_HEADERS, timeout=10)
        if r.ok:
            for m in r.json().get('match', []):
                cname = (m.get('comp_name') or '').lower()
                if 'ranji trophy elite' in cname and 'plate' not in cname:
                    mid = int(m['match_id'])
                    # Overwrite or add fixture info
                    matches[mid] = m
    except Exception as e:
        logger.warning(f'Error querying fixtures: {e}')

    return matches

def sync_all():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_bcci = discover_all_bcci_ranji_matches()
    logger.info(f'Discovered {len(all_bcci)} Ranji matches on BCCI portal.')
    
    updated_count = 0
    skipped_count = 0
    forthcoming_count = 0
    error_count = 0

    for mid, meta in sorted(all_bcci.items()):
        fpath = DATA_DIR / f'{mid}.json'
        status = str(meta.get('match_status', '')).lower()

        # Skip unstarted / future matches
        if status in ('forthcoming', 'scheduled', 'upcoming'):
            forthcoming_count += 1
            continue

        # If match is already concluded and on disk, skip
        if is_match_concluded(fpath):
            skipped_count += 1
            continue

        t1 = meta.get('team1_name', 'T1')
        t2 = meta.get('team2_name', 'T2')
        logger.info(f'Processing Match {mid}: {t1} vs {t2} (Status: {status})...')

        try:
            scorecard = fetch_bcci_scorecard(mid)
            if not scorecard.get('innings'):
                logger.info(f'Skipping match {mid} (No innings started yet).')
                continue

            cricsheet_data = convert_bcci_to_cricsheet(scorecard)
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(cricsheet_data, f, indent=2)
            
            updated_count += 1
            logger.info(f'✓ Successfully updated {fpath.name}')
            time.sleep(1.0)
        except Exception as e:
            error_count += 1
            logger.error(f'✗ Failed to sync match {mid}: {e}')

    logger.info('=' * 50)
    logger.info(f'Sync summary: {updated_count} updated, {skipped_count} concluded (skipped), {forthcoming_count} forthcoming (skipped), {error_count} errors.')
    return updated_count

if __name__ == '__main__':
    sync_all()
