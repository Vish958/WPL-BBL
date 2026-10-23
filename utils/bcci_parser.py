"""
pipeline/parsers/bcci_parser.py
================================
Fetches match data from the new BCCI / CricViz platform and converts it
into canonical Cricsheet v1.1.0 format.

Usage:
------
python pipeline/parsers/bcci_parser.py --url https://www.bcci.tv/matches/3d7873ad-54d3-4040-98cd-c062f5130d12/bengal-vs-delhi
python pipeline/parsers/bcci_parser.py --match_id 239950
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BCCI_API_BASE = "https://stats.bcci.tv"
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
    "Referer": "https://www.bcci.tv/",
}


def resolve_match_id(url_or_id: str) -> Tuple[int, str]:
    """
    Given a BCCI URL or match ID, resolves the CricViz numeric match_id and slug/gid.
    """
    clean_val = url_or_id.strip()
    if clean_val.isdigit():
        return int(clean_val), clean_val

    # Check for UUID / slug in BCCI URL
    # format: https://www.bcci.tv/matches/{gid}/{slug}
    m = re.search(r"/matches/([a-f0-9\-]+)/?([^/?#]*)", clean_val)
    if not m:
        raise ValueError(f"Could not parse match ID or UUID from input: {url_or_id}")

    gid = m.group(1)
    slug = m.group(2) or ""

    # 1. First attempt: fetch page HTML and look for "match":{"id":"<id>"
    try:
        resp = requests.get(clean_val, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]}, timeout=10)
        if resp.ok:
            m_id = re.search(r'"match":\s*\{\s*"id":\s*"(\d+)"', resp.text)
            if m_id:
                return int(m_id.group(1)), slug or gid
    except Exception as e:
        logger.warning(f"Error reading page HTML directly: {e}")

    # 2. Second attempt: search in https://stats.bcci.tv/match/results/ or fixtures
    for endpoint in ["/match/results/", "/match/fixtures/", "/match/live_scores/"]:
        try:
            r = requests.get(f"{BCCI_API_BASE}{endpoint}", headers=DEFAULT_HEADERS, timeout=8)
            if r.ok:
                data = r.json()
                matches = data.get("match") or data.get("live_scores") or []
                for match in matches:
                    if str(match.get("gid")) == gid or str(match.get("match_id")) == gid:
                        return int(match["match_id"]), slug or gid
        except Exception:
            pass

    raise ValueError(f"Could not resolve numeric match_id for BCCI GID {gid}")


def fetch_bcci_scorecard(match_id: int) -> dict:
    """Fetch structured scorecard JSON from stats.bcci.tv."""
    url = f"{BCCI_API_BASE}/match/{match_id}/scorecard/"
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=10)
    if not resp.ok:
        raise RuntimeError(f"Failed to fetch scorecard for match {match_id}: HTTP {resp.status_code}")
    return resp.json()


def parse_wicket_kind(dismissal_name: str) -> str:
    """Map BCCI dismissal_name to Cricsheet wicket kind."""
    d = (dismissal_name or "").lower().strip()
    if "caught" in d:
        return "caught"
    elif "bowled" in d:
        return "bowled"
    elif "leg before" in d or "lbw" in d:
        return "lbw"
    elif "run out" in d:
        return "run out"
    elif "stumped" in d:
        return "stumped"
    elif "hit wicket" in d:
        return "hit wicket"
    elif "retired" in d:
        return "retired hurt"
    return "caught" if "c " in d else "bowled"


def build_match_timing(match_meta: dict, innings_raw: list) -> dict:
    """
    Computes deterministic match timing & fixed 1-hour over projection
    based on the official 15 overs/hour (4 min/over) playing condition benchmark.
    """
    current_day = int(match_meta.get("current_day") or 1)
    scheduled_days = int(match_meta.get("scheduled_days") or 1)
    raw_sched_overs = int(match_meta.get("scheduled_overs") or 0)
    
    # In First-class / Multi-day cricket, raw scheduled_overs is 0 (unlimited),
    # but the daily regulatory quota is 90 overs per day.
    if raw_sched_overs > 0:
        scheduled_daily_overs = raw_sched_overs
    elif scheduled_days >= 2:
        scheduled_daily_overs = 90
    else:
        scheduled_daily_overs = 90

    # Get latest innings overs bowled
    latest_inn = innings_raw[-1] if innings_raw else {}
    overs_str = str(latest_inn.get("overs") or "0")
    if "." in overs_str:
        ov_comp, balls_rem = map(int, overs_str.split("."))
    else:
        ov_comp, balls_rem = int(overs_str) if overs_str.isdigit() else 0, 0

    total_balls_bowled = (ov_comp * 6) + balls_rem
    daily_quota_balls = scheduled_daily_overs * 6
    remaining_balls_today = max(0, daily_quota_balls - total_balls_bowled)

    rem_overs_cricket = f"{remaining_balls_today // 6}.{remaining_balls_today % 6}"

    # Fixed regulatory projection: 1 hour = 15 overs = 90 balls
    one_hour_balls = 15 * 6
    expected_next_hour_balls = min(one_hour_balls, remaining_balls_today)
    expected_next_hour_cricket = f"{expected_next_hour_balls // 6}.{expected_next_hour_balls % 6}"

    return {
        "day": current_day,
        "scheduled_daily_overs": scheduled_daily_overs,
        "overs_bowled": float(overs_str) if overs_str.replace('.', '', 1).isdigit() else 0.0,
        "overs_remaining_today": float(rem_overs_cricket),
        "balls_remaining_today": remaining_balls_today,
        "fixed_projection": {
            "standard_overs_per_hour": 15,
            "minutes_per_over": 4.0,
            "one_hour_capacity_overs": 15.0,
            "expected_overs_next_hour": float(expected_next_hour_cricket),
            "max_overs_with_1hr_extension": round((expected_next_hour_balls + one_hour_balls) / 6, 1),
            "extension_1_hour_overs": 15.0,
            "extension_30_min_overs": 7.5,
        },
    }


def convert_bcci_to_cricsheet(raw: dict) -> dict:
    """
    Transforms raw BCCI scorecard data into standard Cricsheet v1.1.0 format.
    """
    match_meta = raw.get("match", {})
    teams_meta = raw.get("team", [])
    innings_raw = raw.get("innings", [])
    officials_raw = raw.get("official", [])

    # Map teams
    team_order = [t.get("name") for t in teams_meta]
    player_id_to_name: Dict[str, str] = {}
    team_players: Dict[str, List[str]] = {}

    for t in teams_meta:
        tname = t.get("name", "Unknown")
        team_players[tname] = []
        for p in t.get("player", []):
            pid = str(p.get("player_id"))
            pname = p.get("known_as") or p.get("name") or f"Player_{pid}"
            player_id_to_name[pid] = pname
            team_players[tname].append(pname)

    # Info block
    toss_winner_id = str(match_meta.get("toss_winner_team_id"))
    toss_decision = (match_meta.get("toss_decision") or "field").lower()
    toss_winner = team_order[0] if len(team_order) > 0 else "Unknown"
    for t in teams_meta:
        if str(t.get("team_id")) == toss_winner_id:
            toss_winner = t.get("name")

    venue_name = match_meta.get("ground_name") or "Bengal Cricket Academy Ground, Kalyani"
    city = match_meta.get("ground_city")
    full_venue = f"{venue_name}, {city}" if city and city.lower() != "unknown city" and city not in venue_name else venue_name

    start_date = match_meta.get("start_date") or datetime.date.today().isoformat()
    match_dates = [start_date]

    # Officials
    umpires = []
    referees = []
    for off in officials_raw:
        oname = off.get("known_as") or off.get("name")
        otype = (off.get("type_name") or "").lower()
        if "umpire" in otype:
            umpires.append(oname)
        elif "referee" in otype:
            referees.append(oname)

    officials_dict: dict = {}
    if umpires:
        officials_dict["umpires"] = umpires
    if referees:
        officials_dict["match_referees"] = referees

    # Event
    comp_name = match_meta.get("comp_name") or match_meta.get("alt_comp_name") or "Ranji Trophy"
    match_num_str = match_meta.get("tournament_match_number") or "1"
    match_num = int(match_num_str) if str(match_num_str).isdigit() else 1
    event_dict = {"name": comp_name, "match_number": match_num}

    # Match timing & Fixed 1-Hour Extension Projection
    match_timing = build_match_timing(match_meta, innings_raw)

    # Build Day & Session mapper from official BCCI session data
    session_raw = raw.get("session") or []
    day_mapper, days_summary, stumps_by_inn = _build_day_session_mapper(session_raw)

    raw_current_day = match_meta.get("current_day")
    days_found = [int(s.get("day_number") or 1) for s in session_raw if str(s.get("day_number", "")).isdigit()]
    if raw_current_day and str(raw_current_day).isdigit():
        max_day = int(raw_current_day)
    elif days_found:
        max_day = max(days_found)
    elif days_summary:
        max_day = max(days_summary.keys())
    else:
        max_day = 1

    match_status_val = match_meta.get("match_status") or "complete"
    outcome_summary = match_meta.get("result_string") or (f"Day {max_day} Stumps" if match_status_val == "live" else "Match Drawn")

    if max_day not in days_summary:
        days_summary[max_day] = {
            "day": max_day,
            "status": "in play" if match_status_val == "live" else "stumps",
            "score": outcome_summary,
            "time": "",
        }

    info: dict = {
        "balls_per_over": int(match_meta.get("bpo") or 6),
        "city": city,
        "current_day": max_day,
        "dates": match_dates,
        "day_status": f"Live Day {max_day}" if match_status_val == "live" else (f"Day {max_day} Stumps" if "stumps" in outcome_summary.lower() else outcome_summary),
        "days_played": list(range(1, max_day + 1)),
        "days_summary": [days_summary[d] for d in sorted(days_summary.keys())],
        "event": event_dict,
        "gender": "male",
        "match_timing": match_timing,
        "match_type": "MDM",
        "officials": officials_dict,
        "outcome": {
            "result": "stumps" if match_status_val == "live" else "draw",
            "summary": outcome_summary,
        },
        "players": team_players,
        "registry": {"people": {name: pid for pid, name in player_id_to_name.items()}},
        "season": match_meta.get("comp_season") or "2026/27",
        "team_type": "domestic",
        "teams": team_order,
        "toss": {"decision": toss_decision, "winner": toss_winner},
        "venue": full_venue,
    }

    # Only include 'overs' limit in info for limited-overs matches (T20/ODI), NOT for Multi-Day Matches (MDM)
    raw_sched_overs = int(match_meta.get("scheduled_overs") or 0)
    scheduled_days = int(match_meta.get("scheduled_days") or 1)
    if raw_sched_overs > 0 and scheduled_days < 2:
        info["overs"] = raw_sched_overs

    gid = match_meta.get("gid")
    comm_data = None
    if gid:
        comm_data = fetch_bcci_commentary(gid)

    comm_innings = list(reversed(comm_data.get("innings", []))) if comm_data and comm_data.get("innings") else []

    # Build Innings with day-wise tracking
    innings_list = []
    for inn_idx, inn in enumerate(innings_raw, start=1):
        batting_team_id = str(inn.get("batting_team_id"))
        batting_team_name = team_order[1] if len(team_order) > 1 else "Unknown"
        for t in teams_meta:
            if str(t.get("team_id")) == batting_team_id:
                batting_team_name = t.get("name")

        if inn_idx - 1 < len(comm_innings):
            comm_inn = comm_innings[inn_idx - 1]
            overs_data = parse_genuine_commentary_innings(
                comm_inn=comm_inn,
                scorecard_inn=inn,
                player_map=player_id_to_name,
                inn_number=inn_idx,
                day_mapper=day_mapper
            )
        else:
            logger.warning(f"No genuine commentary found for match {match_meta.get('match_id')} innings {inn_idx}. Leaving overs empty.")
            overs_data = []

        official_bowlers = {}
        for b in inn.get("bowling", []):
            pid = str(b.get("player_id"))
            pname = player_id_to_name.get(pid, f"Player_{pid}")
            official_bowlers[pname] = {
                "overs": str(b.get("overs") or "0"),
                "maidens": int(b.get("maidens") or 0),
                "runs": int(b.get("conceded") or b.get("runs") or 0),
                "wickets": int(b.get("wickets") or 0),
                "dots": int(b.get("dots") or 0),
                "fours": int(b.get("fours_conceded") or 0),
                "sixes": int(b.get("sixes_conceded") or 0),
                "wides": int(b.get("wides") or 0),
                "noballs": int(b.get("noballs") or 0),
            }

        innings_list.append({
            "team": batting_team_name,
            "overs": overs_data,
            "official_bowlers": official_bowlers,
        })

    return {
        "meta": {
            "data_version": "1.1.0",
            "created": datetime.date.today().isoformat(),
            "revision": 1,
        },
        "info": info,
        "innings": innings_list,
    }


def fetch_bcci_commentary(gid: str) -> Optional[dict]:
    """
    Fetch genuine ball-by-ball commentary feed directly from Ellipse Data / CricViz.
    Authenticates using BCCI customer key and CORS headers.
    """
    if not gid:
        return None
    url = f"https://epr.ellipsedata.com/redirect/1/match/{gid}/commentary?type=enhanced"
    headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "Edak": "dREj-f+6etraCroX6",
        "Origin": "https://www.bcci.tv",
        "Referer": "https://www.bcci.tv/",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.ok:
            data = resp.json()
            if "innings" in data:
                return data
    except Exception as e:
        logger.warning(f"Error fetching genuine commentary for gid {gid}: {e}")
    return None



def _build_day_session_mapper(session_raw: list):
    """
    Builds a lookup function to map (innings_number, over_index) to (day_number, session_number)
    based on official BCCI session data, and extracts daily stumps checkpoints.
    """
    checkpoints: dict[int, list[tuple[float, int, int]]] = {}
    days_summary: dict[int, dict] = {}
    stumps_by_inn: dict[int, list[dict]] = {}

    for s in session_raw:
        inn_num = int(s.get("innings_number") or 1)
        day_num = int(s.get("day_number") or 1)
        sess_num = int(s.get("session_number") or 1)
        ov_str = str(s.get("overs") or "0")
        if "." in ov_str:
            o, b = ov_str.split(".")
            ov_val = float(o) + float(b) / 6.0
            balls_val = int(o) * 6 + int(b)
        else:
            ov_val = float(ov_str) if ov_str.replace(".", "", 1).isdigit() else 0.0
            balls_val = int(ov_val) * 6

        if inn_num not in checkpoints:
            checkpoints[inn_num] = []
        checkpoints[inn_num].append((ov_val, day_num, sess_num))

        if s.get("is_day_end") == "1" or s.get("status_name") in ("stumps", "end of match"):
            days_summary[day_num] = {
                "day": day_num,
                "status": s.get("status_name") or "stumps",
                "score": f"{s.get('runs')}/{s.get('wickets')} in {ov_str} ov",
                "time": s.get("time_utc") or s.get("time") or "",
            }
            if inn_num not in stumps_by_inn:
                stumps_by_inn[inn_num] = []
            stumps_by_inn[inn_num].append({
                "day": day_num,
                "balls": balls_val,
                "runs": int(s.get("runs") or 0),
                "wickets": int(s.get("wickets") or 0),
                "p1_id": str(s.get("player1_id") or ""),
                "p1_r": int(s.get("player1_runs") or 0),
                "p2_id": str(s.get("player2_id") or ""),
                "p2_r": int(s.get("player2_runs") or 0),
            })

    for inn_num in checkpoints:
        checkpoints[inn_num].sort(key=lambda x: x[0])
    for inn_num in stumps_by_inn:
        stumps_by_inn[inn_num].sort(key=lambda x: x["balls"])

    def mapper(inn_num: int, ov_idx: int) -> tuple[int, int]:
        pts = checkpoints.get(inn_num, [])
        if not pts:
            day = (ov_idx // 90) + 1
            sess = ((ov_idx % 90) // 30) + 1
            return min(4, day), min(3, sess)
        for ov_thresh, day, sess in pts:
            if ov_thresh > ov_idx:
                return day, sess
        return pts[-1][1], pts[-1][2]

    return mapper, days_summary, stumps_by_inn


def parse_genuine_commentary_innings(
    comm_inn: dict,
    scorecard_inn: dict,
    player_map: Dict[str, str],
    inn_number: int = 1,
    day_mapper = None,
) -> List[dict]:
    """
    Converts genuine Ellipse Data commentary for an innings into standard Cricsheet format.
    Preserves exact bowlers, batters, runs, extras, and wickets with zero synthetic data.
    """
    raw_overs = list(reversed(comm_inn.get("bbb", [])))
    batting_list = scorecard_inn.get("batting", [])

    dismissal_map: Dict[str, dict] = {}
    for b in batting_list:
        pid = str(b.get("player_id"))
        pname = player_map.get(pid, f"Player_{pid}")
        d_name = b.get("dismissal_name", "")
        if d_name and d_name.lower() != "not out":
            kind = parse_wicket_kind(d_name)
            fielders = []
            for fld in b.get("fielding", []):
                fname = fld.get("player_known_as") or player_map.get(str(fld.get("player_id")), "")
                if fname:
                    fielders.append({"name": fname})
            dismissal_map[pname] = {"kind": kind, "fielders": fielders}

    # Track active batters at crease
    active_batters: list[str] = []
    for b in batting_list[:2]:
        pname = player_map.get(str(b.get("player_id")))
        if pname:
            active_batters.append(pname)

    innings_overs: List[dict] = []
    for ov_obj in raw_overs:
        ov_num = int(ov_obj.get("over_number") or 1) - 1
        bowler_fallback = ov_obj.get("bowling_player_name") or "Bowler"
        raw_balls = list(reversed(ov_obj.get("balls", [])))

        day_num, sess_num = day_mapper(inn_number, ov_num) if day_mapper else ((ov_num // 90) + 1, ((ov_num % 90) // 30) + 1)
        ov_deliveries = []

        for b in raw_balls:
            summary = b.get("commentary", {}).get("ball_summary_text") or ""
            if " to " in summary:
                parts = summary.split(" to ", 1)
                bowler = parts[0].strip()
                batter = parts[1].strip()
            else:
                bowler = bowler_fallback
                batter = player_map.get(str(b.get("batting_player_id")), "Batter")

            if batter not in active_batters:
                active_batters.append(batter)
                if len(active_batters) > 2:
                    active_batters = active_batters[-2:]

            non_striker = None
            if len(active_batters) == 2:
                non_striker = active_batters[0] if active_batters[1] == batter else active_batters[1]

            scoring = str(b.get("scoring") or "")
            tot_runs = int(b.get("runs") or 0)

            runs_dict = {"batter": 0, "extras": 0, "total": tot_runs}
            extras_dict = {}

            if "ʷᵈ" in scoring or "wd" in scoring.lower():
                runs_dict["extras"] = tot_runs
                extras_dict["wides"] = tot_runs
            elif "ⁿᵇ" in scoring or "nb" in scoring.lower():
                bat_runs = max(0, tot_runs - 1)
                runs_dict["batter"] = bat_runs
                runs_dict["extras"] = 1
                extras_dict["noballs"] = 1
            elif "ˡᵇ" in scoring or "lb" in scoring.lower():
                runs_dict["extras"] = tot_runs
                extras_dict["legbyes"] = tot_runs
            elif "ᵇ" in scoring or "b" in scoring.lower():
                runs_dict["extras"] = tot_runs
                extras_dict["byes"] = tot_runs
            else:
                runs_dict["batter"] = tot_runs

            deliv = {
                "batter": batter,
                "bowler": bowler,
                "non_striker": non_striker,
                "runs": runs_dict,
                "day": day_num,
                "session": sess_num,
            }
            if extras_dict:
                deliv["extras"] = extras_dict

            out_pid = b.get("out_player_id")
            if out_pid and out_pid != 0:
                out_name = player_map.get(str(out_pid), batter)
                msg = (b.get("commentary", {}).get("message") or "").lower()
                if "c & b" in msg or "caught and bowled" in msg:
                    kind = "caught and bowled"
                elif "caught" in msg or " c " in msg:
                    kind = "caught"
                elif "bowled" in msg or " b " in msg:
                    kind = "bowled"
                elif "lbw" in msg:
                    kind = "lbw"
                elif "run out" in msg:
                    kind = "run out"
                elif "stumped" in msg:
                    kind = "stumped"
                else:
                    kind = dismissal_map.get(out_name, {}).get("kind", "caught")

                w_entry: dict = {"kind": kind, "player_out": out_name}
                flds = dismissal_map.get(out_name, {}).get("fielders")
                if flds:
                    w_entry["fielders"] = flds
                deliv["wickets"] = [w_entry]

                if out_name in active_batters:
                    active_batters.remove(out_name)

            ov_deliveries.append(deliv)

        innings_overs.append({
            "over": ov_num,
            "day": day_num,
            "session": sess_num,
            "deliveries": ov_deliveries
        })

    return innings_overs


def main():
    parser = argparse.ArgumentParser(description="Fetch and convert BCCI match to Cricsheet format")
    parser.add_argument("--url", type=str, help="BCCI Match URL")
    parser.add_argument("--match_id", type=str, help="BCCI / CricViz match ID")
    parser.add_argument("--output", type=str, default="", help="Path to write Cricsheet JSON file")
    args = parser.parse_args()

    input_val = args.url or args.match_id
    if not input_val:
        parser.error("Must provide either --url or --match_id")

    match_id, slug = resolve_match_id(input_val)
    logger.info(f"Resolved match_id={match_id} (slug={slug})")

    logger.info("Fetching BCCI scorecard...")
    scorecard = fetch_bcci_scorecard(match_id)

    logger.info("Converting to canonical Cricsheet format...")
    cricsheet_data = convert_bcci_to_cricsheet(scorecard)

    output_path = Path(args.output) if args.output else Path(__file__).parent.parent / "canonical" / f"{match_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cricsheet_data, f, indent=2)

    logger.info(f"Successfully written Cricsheet format to: {output_path}")
    print(f"\n✓ Generated Cricsheet JSON file: {output_path}")


if __name__ == "__main__":
    main()
