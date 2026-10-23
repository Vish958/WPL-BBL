# utils/live_sync_helper.py
import json
import logging
import os
import time
from pathlib import Path
import requests

from utils.bcci_parser import fetch_bcci_scorecard, convert_bcci_to_cricsheet

logger = logging.getLogger('live_sync')

BCCI_API_BASE = 'https://stats.bcci.tv'
DEFAULT_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)',
    'Referer': 'https://www.bcci.tv/',
}

_LAST_SYNC_TIMESTAMP = {}

def is_match_live(json_data: dict) -> bool:
    if not json_data or not isinstance(json_data, dict):
        return False
    info = json_data.get('info', {})
    outcome = info.get('outcome', {})
    # If outcome already has winner or draw or tie, match is finished
    if outcome.get('winner') or outcome.get('result') in ('draw', 'tie', 'no result'):
        return False
    status = str(outcome.get('summary', '')).lower()
    if 'won by' in status or 'match drawn' in status:
        return False
    return True

def sync_single_match(match_id: int, save_dir: str = None) -> dict:
    """Fetch the latest scorecard and commentary for match_id and write to save_dir if provided."""
    try:
        now = time.time()
        # Cooldown of 10s per match to prevent rate limiting
        if match_id in _LAST_SYNC_TIMESTAMP and (now - _LAST_SYNC_TIMESTAMP[match_id]) < 10:
            return None
        _LAST_SYNC_TIMESTAMP[match_id] = now
        
        raw_scorecard = fetch_bcci_scorecard(match_id)
        cricsheet_data = convert_bcci_to_cricsheet(raw_scorecard)
        
        if save_dir and os.path.exists(save_dir):
            target_path = Path(save_dir) / f'{match_id}.json'
            try:
                with open(target_path, 'w', encoding='utf-8') as f:
                    json.dump(cricsheet_data, f, indent=2)
            except Exception as e:
                logger.warning(f'Could not write file to {target_path}: {e}')
                
        return cricsheet_data
    except Exception as e:
        logger.warning(f'Error syncing match {match_id}: {e}')
        return None

def fetch_active_ranji_fixtures() -> list:
    """Check stats.bcci.tv for any live or recently scheduled Ranji fixtures."""
    try:
        r = requests.get(f'{BCCI_API_BASE}/match/fixtures/', headers=DEFAULT_HEADERS, timeout=6)
        if r.ok:
            fixtures = r.json().get('match', [])
            return [m for m in fixtures if 'ranji trophy elite' in (m.get('comp_name') or '').lower()]
    except Exception as e:
        logger.warning(f'Error querying fixtures: {e}')
    return []
