# npl_2026_matches.py
# Nepal Premier League (NPL 2026) Ball-by-Ball Analytics Hub
# Season: NPL 2026 Only (Series 1558581)

import os
import glob
import json
import time
import hashlib
import re
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Streamlit Page Setup (Clean Default Theme, No Custom High-Dark Overrides)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NPL 2026 Analytics Hub",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# Path Configuration & Data Directory
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR_2026 = os.path.join(BASE_DIR, "data", "npl_2026_json")
os.makedirs(DATA_DIR_2026, exist_ok=True)

SERIES_ID_2026 = 1558581

# ---------------------------------------------------------------------------
# Helper Functions: Normalization & Checksum
# ---------------------------------------------------------------------------
def get_folder_hash(directory: str) -> str:
    mtimes = []
    if os.path.exists(directory):
        for entry in os.scandir(directory):
            if entry.name.endswith(".json"):
                mtimes.append(f"{entry.name}:{entry.stat().st_mtime}:{entry.stat().st_size}")
    mtimes.sort()
    return hashlib.md5(";".join(mtimes).encode("utf-8")).hexdigest()

def normalize_team_name(name: str) -> str:
    if not name:
        return "Unknown"
    s = re.sub(r"\(NPL\)", "", str(name)).strip()
    if "Sudur" in s or "Paschim" in s:
        return "Sudurpaschim Royals"
    if "Kathmandu" in s:
        return "Kathmandu Gurkhas"
    return s

# ---------------------------------------------------------------------------
# Telemetry Syncer: Checks ESPN Cricinfo Series 1558581 for Live/New Matches
# ---------------------------------------------------------------------------
from urllib.parse import urlsplit
import requests
try:
    from akamai.edgeauth import EdgeAuth
except ImportError:
    EdgeAuth = None

EDGE_AUTH_KEY = "9ced54a89687e1173e91c1f225fc02abf275a119fda8a41d731d2b04dac95ff5"

def espn_request(method: str, url: str) -> requests.Response:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if EdgeAuth:
        query = urlsplit(url)._replace(scheme="", netloc="").geturl()
        et = EdgeAuth(key=EDGE_AUTH_KEY, window_seconds=1800, escape_early=True)
        headers["X-Hsci-Auth-Token"] = et.generate_url_token(query)
    return requests.request(method, url, headers=headers)

def fetch_espn_innings_comments(series_id: int, match_id: int, inning_num: int) -> list:
    base_url = (
        f"https://hs-consumer-api.espncricinfo.com/v1/pages/match/comments"
        f"?lang=en&seriesId={series_id}&matchId={match_id}"
        f"&inningNumber={inning_num}&commentType=ALL&sortDirection=ASC"
    )
    all_comments = []
    next_over = None
    while True:
        url = base_url + (f"&fromInningOver={next_over}" if next_over else "")
        resp = espn_request("get", url)
        if not resp or resp.status_code != 200:
            break
        try:
            data = resp.json()
        except Exception:
            break
        comments = data.get("comments", [])
        if not comments:
            break
        all_comments.extend(comments)
        next_over = data.get("nextInningOver")
        if not next_over:
            break
    return all_comments

def sync_espn_npl_2026():
    try:
        sched_url = f"https://hs-consumer-api.espncricinfo.com/v1/pages/series/schedule?lang=en&seriesId={SERIES_ID_2026}"
        sched_resp = espn_request("get", sched_url)
        if sched_resp.status_code != 200:
            return 0

        matches = sched_resp.json().get("content", {}).get("matches", [])
        # Only process matches that are in progress or finished
        active_matches = [m for m in matches if m.get("state") in ("POST", "LIVE") or m.get("status") == "RESULT"]
        
        saved_count = 0
        for m in active_matches:
            mid = m.get("objectId")
            if not mid:
                continue

            target_file = os.path.join(DATA_DIR_2026, f"{mid}.json")
            # If match is finished and already saved, skip re-fetching
            if os.path.exists(target_file) and m.get("state") == "POST":
                continue

            sc_url = f"https://hs-consumer-api.espncricinfo.com/v1/pages/match/scorecard?lang=en&seriesId={SERIES_ID_2026}&matchId={mid}"
            sc_resp = espn_request("get", sc_url)
            if sc_resp.status_code != 200:
                continue
            sc_data = sc_resp.json()
            match_info = sc_data.get("match", {})

            player_id_to_name = {}
            players_by_team = {}
            for tp in sc_data.get("content", {}).get("matchPlayers", {}).get("teamPlayers", []):
                raw_team = tp.get("team", {}).get("longName", tp.get("team", {}).get("name", ""))
                tname = normalize_team_name(raw_team)
                players_by_team[tname] = []
                for p in tp.get("players", []):
                    pl = p.get("player", {})
                    pname = pl.get("name") or pl.get("longName") or "Unknown"
                    player_id_to_name[pl.get("id")] = pname
                    players_by_team[tname].append(pname)

            teams = [normalize_team_name(t.get("team", {}).get("longName", t.get("team", {}).get("name", ""))) for t in match_info.get("teams", [])]

            innings_list = []
            for inn_num in [1, 2]:
                comments = fetch_espn_innings_comments(SERIES_ID_2026, mid, inn_num)
                if not comments:
                    continue
                deliv_comments = [c for c in comments if c.get("oversActual") is not None]
                deliv_comments.sort(key=lambda x: (x.get("overNumber", 0), x.get("ballNumber", 0)))

                batting_team = None
                for sci in sc_data.get("content", {}).get("innings", []):
                    if sci.get("inningNumber") == inn_num:
                        batting_team = normalize_team_name(sci.get("team", {}).get("longName", sci.get("team", {}).get("name", "")))
                        break
                if not batting_team:
                    batting_team = teams[inn_num - 1] if len(teams) >= inn_num else f"Team {inn_num}"

                overs_dict = {}
                for c in deliv_comments:
                    raw_over = c.get("overNumber", 1)
                    over_no = (raw_over - 1) if raw_over >= 1 else raw_over
                    if over_no not in overs_dict:
                        overs_dict[over_no] = []

                    runs_bat = c.get("batsmanRuns", 0)
                    runs_tot = c.get("totalRuns", 0)
                    runs_extra = runs_tot - runs_bat

                    d_obj = {
                        "batter": player_id_to_name.get(c.get("batsmanPlayerId"), "Unknown"),
                        "bowler": player_id_to_name.get(c.get("bowlerPlayerId"), "Unknown"),
                        "non_striker": player_id_to_name.get(c.get("nonStrikerPlayerId"), "Unknown"),
                        "runs": {
                            "batter": runs_bat,
                            "extras": runs_extra,
                            "total": runs_tot
                        }
                    }

                    extras_dict = {}
                    if c.get("wides", 0) > 0: extras_dict["wides"] = c.get("wides")
                    if c.get("noballs", 0) > 0: extras_dict["noballs"] = c.get("noballs")
                    if c.get("legbyes", 0) > 0: extras_dict["legbyes"] = c.get("legbyes")
                    if c.get("byes", 0) > 0: extras_dict["byes"] = c.get("byes")
                    if extras_dict:
                        d_obj["extras"] = extras_dict

                    if c.get("isWicket"):
                        out_name = player_id_to_name.get(c.get("outPlayerId"), d_obj["batter"])
                        d_obj["wickets"] = [{
                            "kind": str(c.get("dismissalType") or "caught").lower(),
                            "player_out": out_name
                        }]

                    overs_dict[over_no].append(d_obj)

                overs_list = [{"over": o_num, "deliveries": overs_dict[o_num]} for o_num in sorted(overs_dict.keys())]
                innings_list.append({"team": batting_team, "overs": overs_list})

            cricsheet_json = {
                "meta": {
                    "data_version": "1.2.0",
                    "created": match_info.get("startDate", "")[:10],
                    "revision": 1
                },
                "info": {
                    "balls_per_over": 6,
                    "city": match_info.get("city") or "Kirtipur",
                    "dates": [match_info.get("startDate", "")[:10]],
                    "event": {
                        "name": "Nepal Premier League",
                        "match_number": int(re.search(r"(\d+)", match_info.get("title", "1")).group(1)) if re.search(r"(\d+)", match_info.get("title", "")) else 1
                    },
                    "gender": "male",
                    "match_type": "T20",
                    "outcome": {
                        "winner": normalize_team_name(match_info.get("statusText", "").split(" won")[0].strip()) if "won" in match_info.get("statusText", "") else "Unknown",
                        "result": match_info.get("statusText", "")
                    },
                    "overs": 20,
                    "players": players_by_team,
                    "season": "2026/27",
                    "teams": teams,
                    "toss": {
                        "winner": normalize_team_name(match_info.get("tossWinnerTeam", {}).get("longName", teams[0])),
                        "decision": "bat" if "bat" in match_info.get("tossText", "").lower() else "field"
                    },
                    "venue": match_info.get("ground", {}).get("name", "Tribhuvan University International Cricket Ground, Kirtipur")
                },
                "innings": innings_list
            }

            with open(target_file, "w", encoding="utf-8") as fp:
                json.dump(cricsheet_json, fp, indent=2)
            saved_count += 1

        return saved_count
    except Exception:
        return 0

# ---------------------------------------------------------------------------
# Data Loading (NPL 2026 Only)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_npl_2026_matches(folder_hash: str) -> List[Dict[str, Any]]:
    matches = []
    file_list = sorted(glob.glob(os.path.join(DATA_DIR_2026, "*.json")), reverse=True)

    for filepath in file_list:
        fname = os.path.basename(filepath)
        match_id = os.path.splitext(fname)[0]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            info = data.get("info", {})
            dates = info.get("dates", ["Unknown Date"])
            match_date = dates[0] if dates else "Unknown Date"
            raw_teams = info.get("teams", ["Team 1", "Team 2"])
            teams = [normalize_team_name(t) for t in raw_teams]

            match_num = info.get("event", {}).get("match_number", "")
            label = f"{teams[0]} vs {teams[1]} ({match_date})"
            if match_num:
                label = f"Match {match_num}: {label}"

            matches.append({
                "filepath": filepath,
                "filename": fname,
                "match_id": match_id,
                "season": "NPL 2026",
                "date": match_date,
                "teams": teams,
                "venue": info.get("venue", "Tribhuvan University International Cricket Ground, Kirtipur"),
                "city": info.get("city", "Kirtipur"),
                "outcome": info.get("outcome", {}),
                "toss": info.get("toss", {}),
                "label": label,
                "data": data
            })
        except Exception:
            continue

    matches.sort(key=lambda m: m["date"], reverse=True)
    return matches

# ---------------------------------------------------------------------------
# Ball-by-Ball Metric Parser
# ---------------------------------------------------------------------------
def parse_deliveries_and_metrics(matches_list: List[Dict[str, Any]]):
    deliv_records = []
    over_records = []
    partnership_records = []
    big_overs = []
    balls_faced_records = []

    for m in matches_list:
        m_id = m["match_id"]
        m_label = m["label"]
        m_season = m["season"]
        m_date = m["date"]
        raw_match = m["data"]
        innings_list = raw_match.get("innings", [])

        for inn_idx, inn in enumerate(innings_list, 1):
            batting_team = normalize_team_name(inn.get("team", f"Team {inn_idx}"))
            fielding_team = None
            for t in m["teams"]:
                if t != batting_team:
                    fielding_team = t
                    break
            if not fielding_team:
                fielding_team = "Opponent"

            overs_data = inn.get("overs", [])
            min_over = min((o.get("over", 0) for o in overs_data), default=0)
            is_1_indexed = (min_over >= 1)

            curr_b1 = None
            curr_b2 = None
            p_runs = 0
            p_balls = 0
            p_fours = 0
            p_sixes = 0
            p_dots = 0
            b1_runs, b1_balls = 0, 0
            b2_runs, b2_balls = 0, 0
            wkt_num = 1
            over_start_str = "0.1"

            prev_over_started_boundary = False
            prev_over_idx = None

            for over_obj in overs_data:
                raw_over = over_obj.get("over", 0)
                over_idx = (raw_over - 1) if is_1_indexed else raw_over
                display_over = over_idx + 1
                delivs = over_obj.get("deliveries", [])
                if not delivs:
                    continue

                if over_idx <= 5:
                    phase = "Powerplay"
                elif over_idx <= 14:
                    phase = "Middle"
                else:
                    phase = "Death"

                over_runs = 0
                over_extras = 0
                over_wickets = 0
                over_fours = 0
                over_sixes = 0
                over_dots = 0
                over_singles = 0
                over_doubles = 0
                over_bowler = delivs[0].get("bowler", "Unknown") if delivs else "Unknown"
                seq_symbols = []

                first_ball_boundary = False
                last_ball_boundary = False
                earlier_ball_boundaries = False

                legal_balls_in_over = 0
                total_balls_in_over = len(delivs)

                for b_idx, d in enumerate(delivs):
                    batter = d.get("batter", "Unknown")
                    bowler = d.get("bowler", "Unknown")
                    non_striker = d.get("non_striker", "Unknown")

                    runs_obj = d.get("runs", {})
                    runs_bat = runs_obj.get("batter", 0)
                    runs_extra = runs_obj.get("extras", 0)
                    runs_tot = runs_obj.get("total", 0)

                    extras = d.get("extras", {})
                    is_wide = "wides" in extras
                    is_noball = "noballs" in extras
                    is_legal = not is_wide and not is_noball

                    wickets = d.get("wickets", [])
                    is_wkt = len(wickets) > 0
                    wkt_kind = wickets[0].get("kind", "") if is_wkt else ""
                    player_out = wickets[0].get("player_out", "") if is_wkt else ""

                    if is_legal:
                        legal_balls_in_over += 1

                    if is_wkt:
                        sym = f"W({runs_tot})" if runs_tot > 0 else "W"
                    elif is_wide:
                        sym = f"{runs_tot}wd"
                    elif is_noball:
                        sym = f"{runs_tot}nb"
                    else:
                        sym = str(runs_tot)
                    seq_symbols.append(sym)

                    is_four = (runs_bat == 4)
                    is_six = (runs_bat == 6)
                    is_boundary = is_four or is_six
                    is_single = (runs_bat == 1)
                    is_double = (runs_bat in (2, 3))
                    is_dot = (runs_tot == 0 and not is_wide and not is_noball)

                    over_runs += runs_tot
                    over_extras += runs_extra
                    if is_wkt: over_wickets += 1
                    if is_four: over_fours += 1
                    if is_six: over_sixes += 1
                    if is_single: over_singles += 1
                    if is_double: over_doubles += 1
                    if is_dot: over_dots += 1

                    if b_idx == 0:
                        first_ball_boundary = is_boundary
                    else:
                        if b_idx < total_balls_in_over - 1:
                            if is_boundary:
                                earlier_ball_boundaries = True

                    if b_idx == total_balls_in_over - 1:
                        last_ball_boundary = is_boundary

                    # Collect balls faced for local_t20_metrics style SR progression (everything except wides)
                    if not is_wide:
                        balls_faced_records.append({
                            "match_id": m_id,
                            "innings": inn_idx,
                            "team": batting_team,
                            "batter": batter,
                            "runs_batter": runs_bat,
                            "is_wicket": is_wkt and (player_out == batter)
                        })

                    if curr_b1 is None:
                        curr_b1 = batter
                        curr_b2 = non_striker

                    p_runs += runs_tot
                    if not is_wide:
                        p_balls += 1
                        if batter == curr_b1:
                            b1_runs += runs_bat
                            b1_balls += 1
                        elif batter == curr_b2:
                            b2_runs += runs_bat
                            b2_balls += 1
                        else:
                            curr_b2 = batter
                            b2_runs += runs_bat
                            b2_balls += 1

                    if is_four: p_fours += 1
                    if is_six: p_sixes += 1
                    if is_dot: p_dots += 1

                    deliv_records.append({
                        "match_id": m_id,
                        "season": m_season,
                        "date": m_date,
                        "match_label": m_label,
                        "innings": inn_idx,
                        "batting_team": batting_team,
                        "fielding_team": fielding_team,
                        "over": over_idx,
                        "over_display": display_over,
                        "ball_in_over": b_idx + 1,
                        "ball_str": f"{over_idx}.{legal_balls_in_over if legal_balls_in_over > 0 else 1}",
                        "phase": phase,
                        "is_legal": is_legal,
                        "is_valid_delivery": 1 if is_legal else 0,
                        "batter": batter,
                        "bowler": bowler,
                        "non_striker": non_striker,
                        "runs_batter": runs_bat,
                        "runs_extras": runs_extra,
                        "runs_total": runs_tot,
                        "is_four": is_four,
                        "is_six": is_six,
                        "is_boundary": is_boundary,
                        "is_single": is_single,
                        "is_double": is_double,
                        "is_dot": is_dot,
                        "is_wicket": is_wkt,
                        "wicket_kind": wkt_kind,
                        "player_out": player_out
                    })

                    if is_wkt:
                        partnership_records.append({
                            "match_id": m_id,
                            "match_label": m_label,
                            "season": m_season,
                            "date": m_date,
                            "innings": inn_idx,
                            "team": batting_team,
                            "wicket_label": f"{wkt_num}th Wicket" if wkt_num > 3 else (
                                "1st Wicket" if wkt_num == 1 else ("2nd Wicket" if wkt_num == 2 else "3rd Wicket")
                            ),
                            "wicket_order": wkt_num,
                            "batters": f"{curr_b1} & {curr_b2}",
                            "runs": p_runs,
                            "balls": p_balls,
                            "fours": p_fours,
                            "sixes": p_sixes,
                            "dots": p_dots,
                            "strike_rate": round((p_runs / p_balls) * 100, 1) if p_balls > 0 else 0.0,
                            "batter_1": curr_b1,
                            "batter_1_score": f"{b1_runs} ({b1_balls})",
                            "batter_2": curr_b2,
                            "batter_2_score": f"{b2_runs} ({b2_balls})",
                            "over_span": f"{over_start_str} to {over_idx}.{legal_balls_in_over}",
                            "dismissed": player_out or "Wicket"
                        })
                        wkt_num += 1
                        survivor = curr_b2 if player_out == curr_b1 else curr_b1
                        curr_b1 = survivor
                        curr_b2 = None
                        p_runs, p_balls, p_fours, p_sixes, p_dots = 0, 0, 0, 0, 0
                        b1_runs, b1_balls = 0, 0
                        b2_runs, b2_balls = 0, 0
                        over_start_str = f"{over_idx}.{legal_balls_in_over + 1}"

                ends_with_boundary_only = (last_ball_boundary and not earlier_ball_boundaries and not first_ball_boundary)
                if total_balls_in_over == 1 and first_ball_boundary:
                    ends_with_boundary_only = True

                consecutive_start_boundary = False
                if first_ball_boundary and prev_over_started_boundary and prev_over_idx == over_idx - 1:
                    consecutive_start_boundary = True

                if first_ball_boundary:
                    prev_over_started_boundary = True
                    prev_over_idx = over_idx
                else:
                    prev_over_started_boundary = False
                    prev_over_idx = None

                seq_str = ", ".join(seq_symbols)

                if over_runs >= 20:
                    big_overs.append({
                        "match_id": m_id,
                        "season": m_season,
                        "date": m_date,
                        "match": m_label,
                        "innings": inn_idx,
                        "over_number": display_over,
                        "phase": phase,
                        "batting_team": batting_team,
                        "bowling_team": fielding_team,
                        "bowler": over_bowler,
                        "runs": over_runs,
                        "sequence": seq_str,
                        "fours": over_fours,
                        "sixes": over_sixes,
                        "wickets": over_wickets
                    })

                over_records.append({
                    "match_id": m_id,
                    "season": m_season,
                    "date": m_date,
                    "match": m_label,
                    "innings": inn_idx,
                    "over_number": display_over,
                    "over_idx": over_idx,
                    "phase": phase,
                    "batting_team": batting_team,
                    "fielding_team": fielding_team,
                    "bowler": over_bowler,
                    "runs": over_runs,
                    "extras": over_extras,
                    "wickets": over_wickets,
                    "fours": over_fours,
                    "sixes": over_sixes,
                    "dots": over_dots,
                    "singles": over_singles,
                    "doubles": over_doubles,
                    "sequence": seq_str,
                    "starts_with_boundary": first_ball_boundary,
                    "ends_with_boundary_only": ends_with_boundary_only,
                    "ends_with_boundary_any": last_ball_boundary,
                    "consecutive_start_boundary": consecutive_start_boundary
                })

            if curr_b1 and (p_runs > 0 or p_balls > 0):
                partnership_records.append({
                    "match_id": m_id,
                    "match_label": m_label,
                    "season": m_season,
                    "date": m_date,
                    "innings": inn_idx,
                    "team": batting_team,
                    "wicket_label": f"{wkt_num}th Wicket*" if wkt_num > 3 else (
                        "1st Wicket*" if wkt_num == 1 else ("2nd Wicket*" if wkt_num == 2 else "3rd Wicket*")
                    ),
                    "wicket_order": wkt_num,
                    "batters": f"{curr_b1} & {curr_b2 or 'Partner'}",
                    "runs": p_runs,
                    "balls": p_balls,
                    "fours": p_fours,
                    "sixes": p_sixes,
                    "dots": p_dots,
                    "strike_rate": round((p_runs / p_balls) * 100, 1) if p_balls > 0 else 0.0,
                    "batter_1": curr_b1,
                    "batter_1_score": f"{b1_runs} ({b1_balls})",
                    "batter_2": curr_b2 or "Partner",
                    "batter_2_score": f"{b2_runs} ({b2_balls})",
                    "over_span": f"{over_start_str} to End",
                    "dismissed": "Not Out (Unbroken)"
                })

    deliv_cols = [
        "match_id", "match_label", "season", "date", "innings", "batting_team", "fielding_team",
        "over", "over_display", "ball_in_over", "ball_str", "phase", "is_legal", "is_valid_delivery",
        "batter", "bowler", "non_striker", "runs_batter", "runs_extras", "runs_total",
        "is_four", "is_six", "is_boundary", "is_single", "is_double", "is_dot", "is_wicket",
        "wicket_kind", "player_out"
    ]
    ov_cols = [
        "match_id", "season", "date", "match", "innings", "over_number", "over_idx", "phase",
        "batting_team", "fielding_team", "bowler", "runs", "extras", "wickets", "fours", "sixes",
        "dots", "singles", "doubles", "sequence", "starts_with_boundary", "ends_with_boundary_only",
        "ends_with_boundary_any", "consecutive_start_boundary"
    ]
    part_cols = [
        "match_id", "match_label", "season", "date", "innings", "team", "wicket_label", "wicket_order",
        "batters", "runs", "balls", "fours", "sixes", "dots", "strike_rate", "batter_1", "batter_1_score",
        "batter_2", "batter_2_score", "over_span", "dismissed"
    ]
    big_cols = [
        "match_id", "season", "date", "match", "innings", "over_number", "phase", "batting_team",
        "bowling_team", "bowler", "runs", "sequence", "fours", "sixes", "wickets"
    ]
    bf_cols = [
        "match_id", "match", "season", "innings", "team", "batter",
        "runs_1_10", "balls_1_10", "runs_11_20", "balls_11_20", "runs_21_30", "balls_21_30",
        "runs_31_40", "balls_31_40", "runs_41_50", "balls_41_50", "runs_51_60", "balls_51_60"
    ]

    df_deliv = pd.DataFrame(deliv_records, columns=deliv_cols) if deliv_records else pd.DataFrame(columns=deliv_cols)
    df_ov = pd.DataFrame(over_records, columns=ov_cols) if over_records else pd.DataFrame(columns=ov_cols)
    df_part = pd.DataFrame(partnership_records, columns=part_cols) if partnership_records else pd.DataFrame(columns=part_cols)
    df_big = pd.DataFrame(big_overs, columns=big_cols) if big_overs else pd.DataFrame(columns=big_cols)
    df_bf = pd.DataFrame(balls_faced_records, columns=bf_cols) if balls_faced_records else pd.DataFrame(columns=bf_cols)

    return df_deliv, df_ov, df_part, df_big, df_bf

# ---------------------------------------------------------------------------
# Batter SR Progression Table (Designed exactly like local_t20_metrics.py)
# ---------------------------------------------------------------------------
def compute_batter_sr_progression_table(df_bf: pd.DataFrame, min_balls: int = 1) -> pd.DataFrame:
    if df_bf.empty:
        return pd.DataFrame()

    df_work = df_bf.copy()
    df_work["ball_no"] = df_work.groupby(["match_id", "innings", "team", "batter"]).cumcount() + 1

    buckets = [
        (1, 10, "1-10 SR"),
        (11, 20, "11-20 SR"),
        (21, 30, "21-30 SR"),
        (31, 40, "31-40 SR"),
        (41, 50, "41-50 SR"),
        (51, 60, "51-60 SR")
    ]

    for start, end, label in buckets:
        df_work[f"runs_{label}"] = np.where((df_work["ball_no"] >= start) & (df_work["ball_no"] <= end), df_work["runs_batter"], 0)
        df_work[f"balls_{label}"] = np.where((df_work["ball_no"] >= start) & (df_work["ball_no"] <= end), 1, 0)

    grouping = ["batter", "team"]
    stats = df_work.groupby(grouping).agg(
        Runs=("runs_batter", "sum"),
        Balls=("runs_batter", "count"),
        Dismissals=("is_wicket", "sum")
    ).reset_index()

    inn_counts = df_work.groupby(grouping + ["match_id", "innings"]).size().reset_index()
    inn_counts = inn_counts.groupby(grouping).size().reset_index(name="Innings")
    stats = stats.merge(inn_counts, on=grouping, how="left")

    stats["Average"] = np.where(stats["Dismissals"] > 0, (stats["Runs"] / stats["Dismissals"]).round(1), stats["Runs"].astype(float))
    stats["Strike Rate"] = ((stats["Runs"] / stats["Balls"]) * 100).round(1)
    stats["Balls/Inn"] = (stats["Balls"] / stats["Innings"]).round(1)

    bucket_agg = {}
    for _, _, label in buckets:
        bucket_agg[f"runs_{label}"] = (f"runs_{label}", "sum")
        bucket_agg[f"balls_{label}"] = (f"balls_{label}", "sum")

    bkt_stats = df_work.groupby(grouping).agg(**bucket_agg).reset_index()
    stats = stats.merge(bkt_stats, on=grouping, how="left")

    for _, _, label in buckets:
        stats[label] = np.where(
            stats[f"balls_{label}"] > 0,
            ((stats[f"runs_{label}"] / stats[f"balls_{label}"]) * 100).round(1).astype(str),
            "-"
        )

    cols = ["batter", "team", "Innings", "Runs", "Balls", "Average", "Strike Rate", "Balls/Inn", "1-10 SR", "11-20 SR", "21-30 SR", "31-40 SR", "41-50 SR", "51-60 SR"]
    out = stats[stats["Balls"] >= min_balls][cols].rename(columns={"batter": "Name", "team": "Team"}).sort_values("Runs", ascending=False)
    return out

# ---------------------------------------------------------------------------
# Sidebar UI: Controls & Filters (Season 2026 Only, No Emojis, No Uploader)
# ---------------------------------------------------------------------------
if "last_sync_time" not in st.session_state:
    st.session_state.last_sync_time = 0
if "sync_feedback" not in st.session_state:
    st.session_state.sync_feedback = ""

st.sidebar.title("NPL 2026 Controls")

# Compute folder hash for real-time change detection
current_folder_hash = get_folder_hash(DATA_DIR_2026)
matches_2026 = load_npl_2026_matches(current_folder_hash)

# Team Selector
all_teams_set = set()
for m in matches_2026:
    for t in m.get("teams", []):
        all_teams_set.add(t)
available_teams = ["All Teams"] + sorted(list(all_teams_set))
selected_team = st.sidebar.selectbox("Filter by Team:", available_teams, index=0)

if selected_team != "All Teams":
    team_filtered_matches = [m for m in matches_2026 if selected_team in m.get("teams", [])]
else:
    team_filtered_matches = matches_2026

# Match Fixture Selector (keyed by selected_team to prevent stale index errors)
available_match_labels = ["All Matches Aggregated"] + [m["label"] for m in team_filtered_matches]
selected_match_label = st.sidebar.selectbox(
    "Select Match Fixture:",
    available_match_labels,
    index=0,
    key=f"fixture_select_{selected_team}"
)

if selected_match_label != "All Matches Aggregated":
    final_matches = [m for m in team_filtered_matches if m["label"] == selected_match_label]
    if not final_matches:
        final_matches = team_filtered_matches
else:
    final_matches = team_filtered_matches

# Live Telemetry Sync Button with Cooldown
st.sidebar.markdown("---")
st.sidebar.subheader("Live Telemetry Status")
auto_refresh = st.sidebar.checkbox("Auto-refresh live matches (every 30s)", value=True)

col_sync1, col_sync2 = st.sidebar.columns(2)
if col_sync1.button("Sync Now", use_container_width=True):
    now = time.time()
    if now - st.session_state.last_sync_time < 10:
        st.session_state.sync_feedback = "Cooldown active (wait 10s to prevent rate-limiting)."
    else:
        st.session_state.last_sync_time = now
        new_synced = sync_espn_npl_2026()
        load_npl_2026_matches.clear()
        st.session_state.sync_feedback = f"Synced at {datetime.now().strftime('%H:%M:%S')} (updated {new_synced} matches)"
        st.rerun()

if col_sync2.button("Reload Data", use_container_width=True):
    load_npl_2026_matches.clear()
    st.session_state.sync_feedback = "Cache cleared and data reloaded."
    st.rerun()

if st.session_state.sync_feedback:
    st.sidebar.caption(st.session_state.sync_feedback)

st.sidebar.info(
    f"Tournament: Nepal Premier League 2026\n"
    f"Active 2026 Matches Played: {len(matches_2026)}\n"
    f"Selected in View: {len(final_matches)}"
)

# ---------------------------------------------------------------------------
# Main Dashboard Body (Wrapped in @st.fragment for zero page reload)
# ---------------------------------------------------------------------------
refresh_interval = 30 if auto_refresh else None

@st.fragment(run_every=refresh_interval)
def render_npl_dashboard(current_team: str, current_match_label: str):
    # Dynamically query latest matches on fragment refresh
    folder_hash = get_folder_hash(DATA_DIR_2026)
    all_current_matches = load_npl_2026_matches(folder_hash)

    if current_team != "All Teams":
        filtered_matches = [m for m in all_current_matches if current_team in m.get("teams", [])]
    else:
        filtered_matches = all_current_matches

    if current_match_label != "All Matches Aggregated":
        matches_to_render = [m for m in filtered_matches if m.get("label") == current_match_label]
        if not matches_to_render:
            matches_to_render = filtered_matches
    else:
        matches_to_render = filtered_matches

    st.title("Nepal Premier League (NPL 2026) Ball-by-Ball Analytics")
    st.caption(f"Analyzing {len(matches_to_render)} Matches | Season: 2026 | Team: {current_team} | Auto-Syncing In-Place")

    if not matches_to_render:
        st.warning("No match data found matching the selected filters. Please wait for matches to sync or verify data/npl_2026_json directory.")
        if st.button("Force Sync & Fetch ESPN Matches Now"):
            load_npl_2026_matches.clear()
            sync_espn_npl_2026()
            st.rerun()
        return

    df_deliv, df_ov, df_part, df_big, df_bf = parse_deliveries_and_metrics(matches_to_render)

    if df_deliv.empty:
        st.info("Match is currently in progress or pre-match (waiting for first deliveries to be logged).")
        for m in matches_to_render:
            info = m.get("data", {}).get("info", {})
            toss = info.get("toss", {})
            st.subheader(m.get("label", "Live Match"))
            if toss:
                st.write(f"**Toss:** {toss.get('winner', 'TBD')} elected to {toss.get('decision', 'bat/field')} first.")
            st.write(f"**Venue:** {info.get('venue', 'TU Ground, Kirtipur')}")
            players = info.get("players", {})
            if players:
                pcols = st.columns(len(players))
                for idx, (tname, plist) in enumerate(players.items()):
                    with pcols[idx]:
                        st.markdown(f"**{tname} Squad / Playing XI:**")
                        for p in plist:
                            st.write(f"- {p}")
        return

    if current_team != "All Teams":
        df_deliv_view = df_deliv[df_deliv["batting_team"] == current_team]
        df_ov_view = df_ov[df_ov["batting_team"] == current_team]
        df_part_view = df_part[df_part["team"] == current_team]
        df_big_view = df_big[(df_big["batting_team"] == current_team) | (df_big["bowling_team"] == current_team)]
        df_bf_view = df_bf[df_bf["team"] == current_team]
        if df_deliv_view.empty:
            st.info(f"{current_team} has not batted yet in this match. Switch filter to 'All Teams' or the active batting team to view live ball-by-ball telemetry.")
    else:
        df_deliv_view = df_deliv
        df_ov_view = df_ov
        df_part_view = df_part
        df_big_view = df_big
        df_bf_view = df_bf

    total_runs = int(df_deliv_view["runs_total"].sum()) if not df_deliv_view.empty else 0
    total_wickets = int(df_deliv_view["is_wicket"].sum()) if not df_deliv_view.empty else 0
    total_fours = int(df_deliv_view["is_four"].sum()) if not df_deliv_view.empty else 0
    total_sixes = int(df_deliv_view["is_six"].sum()) if not df_deliv_view.empty else 0
    total_dots = int(df_deliv_view["is_dot"].sum()) if not df_deliv_view.empty else 0
    total_balls = len(df_deliv_view) if not df_deliv_view.empty else 0
    dot_pct = round((total_dots / total_balls) * 100, 1) if total_balls > 0 else 0.0

    # Clean native metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Runs", f"{total_runs:,}", f"{total_wickets} Wickets")
    boundary_runs = (total_fours * 4) + (total_sixes * 6)
    b_pct = round((boundary_runs / total_runs) * 100, 1) if total_runs > 0 else 0.0
    m2.metric("Boundaries", f"{total_fours + total_sixes:,}", f"{total_fours} 4s, {total_sixes} 6s ({b_pct}%)")
    m3.metric("Dot Balls", f"{total_dots:,}", f"{dot_pct}% Dot Balls")
    m4.metric("20+ Run Overs", f"{len(df_big_view)}")
    r1_cnt = int(df_ov_view["starts_with_boundary"].sum()) if not df_ov_view.empty else 0
    m5.metric("Overs Starting w/ Boundary", f"{r1_cnt}")

    st.divider()

    # Tab navigation (Clean, zero emoji)
    tab_phases, tab_sr, tab_big_overs, tab_partnerships, tab_over_breakdown = st.tabs([
        "Phase Metrics (Powerplay / Middle / Death)",
        "Strike Rate Progression by Balls Faced",
        "20+ Runs in an Over Tracker",
        "Match-wise Partnerships",
        "Over-by-Over Detailed Breakdown"
    ])

    # -----------------------------------------------------------------------
    # TAB 1: PHASE BREAKDOWN
    # -----------------------------------------------------------------------
    with tab_phases:
        st.subheader("Phase Breakdown: Powerplay, Middle & Death Overs")
        st.caption("Powerplay: Overs 1-6 | Middle: Overs 7-15 | Death: Overs 16-20")

        phases = ["Powerplay", "Middle", "Death"]
        p_cols = st.columns(3)

        for i, ph in enumerate(phases):
            df_p = df_deliv_view[df_deliv_view["phase"] == ph]
            p_runs = int(df_p["runs_total"].sum()) if not df_p.empty else 0
            p_balls = int(df_p["is_legal"].sum()) if not df_p.empty else 0
            p_wkts = int(df_p["is_wicket"].sum()) if not df_p.empty else 0
            p_fours = int(df_p["is_four"].sum()) if not df_p.empty else 0
            p_sixes = int(df_p["is_six"].sum()) if not df_p.empty else 0
            p_dots = int(df_p["is_dot"].sum()) if not df_p.empty else 0
            p_singles = int(df_p["is_single"].sum()) if not df_p.empty else 0
            p_doubles = int(df_p["is_double"].sum()) if not df_p.empty else 0
            p_overs_display = f"{p_balls // 6}.{p_balls % 6}"
            p_overs_num = p_balls / 6.0
            p_rr = round(p_runs / p_overs_num, 2) if p_overs_num > 0 else 0.0
            p_dot_pct = round((p_dots / p_balls) * 100, 1) if p_balls > 0 else 0.0

            with p_cols[i]:
                st.markdown(f"**{ph.upper()} OVERS**")
                st.metric(label=f"{ph} Runs", value=f"{p_runs}/{p_wkts}", delta=f"Run Rate: {p_rr} RPO")
                st.write(f"- Wickets Lost: **{p_wkts}**")
                st.write(f"- Boundaries: **{p_fours + p_sixes}** ({p_fours} 4s, {p_sixes} 6s)")
                st.write(f"- Dot Balls: **{p_dots}** ({p_dot_pct}%)")
                st.write(f"- Singles: **{p_singles}**")
                st.write(f"- Doubles/Triples: **{p_doubles}**")
                st.write(f"- Legal Balls: **{p_balls}** ({p_overs_display} overs)")

        st.divider()

        # Match-by-Match Powerplay Score Tracker (local_t20_metrics style)
        st.subheader("Match-by-Match Powerplay Score Tracker")
        st.caption("Mathematical metrics modeled on local_t20_metrics: PP_Runs, PP_Balls, PP_RR, PP_Boundaries, PP_Dot%, PP_Wickets")
        pp_deliv = df_deliv_view[df_deliv_view["phase"] == "Powerplay"]
        if not pp_deliv.empty:
            pp_grp = pp_deliv.groupby(["match_id", "date", "innings", "batting_team", "fielding_team"], observed=True).agg(
                PP_Runs=("runs_total", "sum"),
                PP_Balls=("is_legal", "sum"),
                PP_Wickets=("is_wicket", "sum"),
                PP_4s=("is_four", "sum"),
                PP_6s=("is_six", "sum"),
                PP_Dots=("is_dot", "sum")
            ).reset_index()

            pp_grp["Score"] = pp_grp["PP_Runs"].astype(str) + "/" + pp_grp["PP_Wickets"].astype(str)
            pp_grp["PP_RR"] = (pp_grp["PP_Runs"] / (pp_grp["PP_Balls"] / 6.0)).replace([np.inf, np.nan], 0).round(2)
            pp_grp["PP_Boundaries"] = pp_grp["PP_4s"] + pp_grp["PP_6s"]
            pp_grp["PP_Dot%"] = ((pp_grp["PP_Dots"] / np.where(pp_grp["PP_Balls"] == 0, 1, pp_grp["PP_Balls"])) * 100).round(1)
            pp_grp["Innings"] = pp_grp["innings"].map({1: "1st Inns", 2: "2nd Inns"})
            pp_grp["Date"] = pd.to_datetime(pp_grp["date"]).dt.date

            st.dataframe(
                pp_grp.rename(columns={
                    "batting_team": "Team",
                    "fielding_team": "Opponent",
                    "Score": "PP Score",
                    "PP_Runs": "PP Runs",
                    "PP_Balls": "PP Balls",
                    "PP_RR": "PP RR",
                    "PP_Boundaries": "Boundaries",
                    "PP_4s": "4s",
                    "PP_6s": "6s",
                    "PP_Dots": "Dots",
                    "PP_Dot%": "Dot %",
                    "PP_Wickets": "Wickets"
                })[[
                    "Team", "Opponent", "Date", "Innings", "PP Score", "PP Runs", "PP Balls",
                    "PP RR", "Boundaries", "4s", "6s", "Dots", "Dot %", "Wickets"
                ]].sort_values("Date", ascending=False),
                use_container_width=True,
                hide_index=True
            )

        st.divider()

        st.subheader("Team-by-Team Phase Comparison Table")
        if not df_deliv_view.empty:
            team_phase_agg = df_deliv_view.groupby(["batting_team", "phase"]).agg(
                Runs=("runs_total", "sum"),
                Balls=("is_legal", "sum"),
                Wickets=("is_wicket", "sum"),
                Fours=("is_four", "sum"),
                Sixes=("is_six", "sum"),
                Singles=("is_single", "sum"),
                Doubles=("is_double", "sum"),
                Dots=("is_dot", "sum")
            ).reset_index()

            team_phase_agg["Overs"] = team_phase_agg["Balls"].apply(lambda b: f"{int(b // 6)}.{int(b % 6)}")
            team_phase_agg["Run_Rate"] = (team_phase_agg["Runs"] / (team_phase_agg["Balls"] / 6.0)).replace([np.inf, np.nan], 0).round(2)
            team_phase_agg["Boundary_Runs"] = (team_phase_agg["Fours"] * 4) + (team_phase_agg["Sixes"] * 6)
            team_phase_agg["Boundary_%"] = ((team_phase_agg["Boundary_Runs"] / np.where(team_phase_agg["Runs"] == 0, 1, team_phase_agg["Runs"])) * 100).round(1)
            team_phase_agg["Dot_%"] = ((team_phase_agg["Dots"] / np.where(team_phase_agg["Balls"] == 0, 1, team_phase_agg["Balls"])) * 100).round(1)

            phase_order = {"Powerplay": 1, "Middle": 2, "Death": 3}
            team_phase_agg["sort_idx"] = team_phase_agg["phase"].map(phase_order)
            team_phase_agg = team_phase_agg.sort_values(["batting_team", "sort_idx"]).drop(columns=["sort_idx"])

            st.dataframe(
                team_phase_agg.rename(columns={
                    "batting_team": "Team",
                    "phase": "Phase",
                    "Boundary_%": "Boundary %",
                    "Dot_%": "Dot %",
                    "Run_Rate": "Run Rate (RPO)"
                }),
                use_container_width=True,
                hide_index=True
            )

        st.subheader("Scoring Composition by Phase")
        if not df_deliv_view.empty:
            phase_dist = df_deliv_view.groupby("phase").agg(
                Dots=("is_dot", "sum"),
                Singles=("is_single", "sum"),
                Doubles=("is_double", "sum"),
                Fours=("is_four", "sum"),
                Sixes=("is_six", "sum"),
            ).reset_index()

            phase_dist["sort"] = phase_dist["phase"].map({"Powerplay": 1, "Middle": 2, "Death": 3})
            phase_dist = phase_dist.sort_values("sort")

            fig_phase = go.Figure()
            fig_phase.add_trace(go.Bar(x=phase_dist["phase"], y=phase_dist["Dots"], name="Dot Balls (0s)", marker_color="#64748B"))
            fig_phase.add_trace(go.Bar(x=phase_dist["phase"], y=phase_dist["Singles"], name="Singles (1s)", marker_color="#0284C7"))
            fig_phase.add_trace(go.Bar(x=phase_dist["phase"], y=phase_dist["Doubles"], name="Doubles/Triples (2s/3s)", marker_color="#0EA5E9"))
            fig_phase.add_trace(go.Bar(x=phase_dist["phase"], y=phase_dist["Fours"], name="Fours (4s)", marker_color="#F59E0B"))
            fig_phase.add_trace(go.Bar(x=phase_dist["phase"], y=phase_dist["Sixes"], name="Sixes (6s)", marker_color="#EF4444"))

            fig_phase.update_layout(
                barmode="stack",
                xaxis=dict(title="Match Phase"),
                yaxis=dict(title="Deliveries"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=380,
                margin=dict(l=20, r=20, t=30, b=20)
            )
            st.plotly_chart(fig_phase, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 2: STRIKE RATE COMPARISON BY BALL BUCKETS (local_t20_metrics style)
    # -----------------------------------------------------------------------
    with tab_sr:
        st.subheader("Year-wise Batter SR Comparison with Ball-Range SR Buckets")
        st.caption("Name | Team | Innings | Runs | Balls | Average | Strike Rate | Balls/Inn | 1-10 SR | 11-20 SR | 21-30 SR | 31-40 SR | 41-50 SR | 51-60 SR")

        c1, c2 = st.columns([2, 1])
        min_balls = c2.slider("Minimum Balls Faced:", min_value=1, max_value=30, value=5)
        batter_search = c1.text_input("Search Batter Name:", "", placeholder="e.g. Malan, Short, Russell...")

        sr_table = compute_batter_sr_progression_table(df_bf_view, min_balls=min_balls)

        if not sr_table.empty:
            if batter_search:
                sr_table = sr_table[sr_table["Name"].str.contains(batter_search, case=False, na=False)]

            st.dataframe(
                sr_table,
                use_container_width=True,
                hide_index=True
            )

            # Acceleration Curve Plot for Top 8 Run-Scorers
            st.subheader("Strike Rate Trajectory Across Inning Depth")
            top_batters_list = sr_table.head(8)["Name"].tolist()

            valid_bkt_cols = ["1-10 SR", "11-20 SR", "21-30 SR", "31-40 SR", "41-50 SR", "51-60 SR"]
            curve_rows = []
            for _, row in sr_table[sr_table["Name"].isin(top_batters_list)].iterrows():
                b_name = row["Name"]
                for b_col in valid_bkt_cols:
                    val_str = str(row[b_col])
                    if val_str != "-":
                        try:
                            curve_rows.append({
                                "Name": b_name,
                                "Window": b_col.replace(" SR", " Balls"),
                                "Strike Rate": float(val_str)
                            })
                        except ValueError:
                            pass

            if curve_rows:
                df_curves = pd.DataFrame(curve_rows)
                fig_curve = px.line(
                    df_curves,
                    x="Window",
                    y="Strike Rate",
                    color="Name",
                    markers=True,
                    labels={"Window": "Balls Faced Window", "Strike Rate": "Strike Rate (SR)"}
                )
                fig_curve.update_layout(height=400, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig_curve, use_container_width=True)
        else:
            st.info("No batter data available matching the ball threshold.")

    # -----------------------------------------------------------------------
    # TAB 3: 20+ RUNS IN AN OVER TRACKER
    # -----------------------------------------------------------------------
    with tab_big_overs:
        st.subheader("20+ Runs in an Over Tracker (NPL 2026)")
        st.caption("Overs in NPL 2026 where 20 or more runs were scored")

        if df_big_view.empty:
            st.info("No overs with 20+ runs found matching current filter.")
        else:
            st.write(f"Total 20+ Run Overs Identified: **{len(df_big_view)}**")

            st.dataframe(
                df_big_view.rename(columns={
                    "match": "Match Fixture",
                    "season": "Season",
                    "innings": "Innings",
                    "over_number": "Over",
                    "phase": "Phase",
                    "batting_team": "Batting Team",
                    "bowling_team": "Bowling Team",
                    "bowler": "Bowler",
                    "runs": "Runs Scored",
                    "sequence": "Delivery Sequence",
                    "fours": "4s",
                    "sixes": "6s",
                    "wickets": "Wickets"
                })[[
                    "Match Fixture", "Season", "Innings", "Over", "Phase",
                    "Batting Team", "Bowling Team", "Bowler", "Runs Scored",
                    "Delivery Sequence", "4s", "6s", "Wickets"
                ]],
                use_container_width=True,
                hide_index=True
            )

            c_b1, c_b2 = st.columns(2)
            with c_b1:
                bo_cnt = df_big_view["phase"].value_counts().reset_index()
                bo_cnt.columns = ["Phase", "Count"]
                fig_bo = px.bar(bo_cnt, x="Phase", y="Count", title="20+ Run Overs by Phase")
                st.plotly_chart(fig_bo, use_container_width=True)

            with c_b2:
                top_hit = df_big_view["batting_team"].value_counts().reset_index()
                top_hit.columns = ["Team", "Count"]
                fig_hit = px.bar(top_hit, x="Count", y="Team", orientation="h", title="20+ Run Overs by Batting Team")
                st.plotly_chart(fig_hit, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 4: MATCH-WISE PARTNERSHIPS
    # -----------------------------------------------------------------------
    with tab_partnerships:
        st.subheader("Match-wise Partnerships")
        st.caption("Detailed partnership progression for every wicket in each match")

        if df_part_view.empty:
            st.info("No partnership data available for current selection.")
        else:
            part_matches = df_part_view["match_label"].unique().tolist()
            chosen_match = st.selectbox("Select Match to View Partnerships:", part_matches, index=0)
            df_m_part = df_part_view[df_part_view["match_label"] == chosen_match]

            for inn_num in sorted(df_m_part["innings"].unique()):
                df_inn = df_m_part[df_m_part["innings"] == inn_num]
                team_name = df_inn["team"].iloc[0] if not df_inn.empty else f"Innings {inn_num}"
                tot_p = df_inn["runs"].sum()
                st.markdown(f"**Innings {inn_num}: {team_name}** ({tot_p} Runs)")

                st.dataframe(
                    df_inn.rename(columns={
                        "wicket_label": "Wicket",
                        "batters": "Batting Pair",
                        "runs": "Runs",
                        "balls": "Balls",
                        "strike_rate": "Strike Rate",
                        "fours": "4s",
                        "sixes": "6s",
                        "dots": "Dots",
                        "batter_1": "Batter 1",
                        "batter_1_score": "Batter 1 Score",
                        "batter_2": "Batter 2",
                        "batter_2_score": "Batter 2 Score",
                        "over_span": "Over Range",
                        "dismissed": "Dismissal"
                    })[[
                        "Wicket", "Batting Pair", "Runs", "Balls", "Strike Rate",
                        "4s", "6s", "Dots", "Batter 1", "Batter 1 Score",
                        "Batter 2", "Batter 2 Score", "Over Range", "Dismissal"
                    ]],
                    use_container_width=True,
                    hide_index=True
                )

                fig_p = px.bar(
                    df_inn,
                    x="wicket_label",
                    y="runs",
                    text="runs",
                    title=f"Partnership Progression - {team_name} (Innings {inn_num})",
                    labels={"wicket_label": "Wicket", "runs": "Partnership Runs"}
                )
                fig_p.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=20))
                st.plotly_chart(fig_p, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 5: OVER-BY-OVER BREAKDOWN & 3 BOUNDARY RULES
    # -----------------------------------------------------------------------
    with tab_over_breakdown:
        st.subheader("Over-by-Over Detailed Breakdown (Boundary Criteria)")
        st.caption(
            "1. Over starts with boundary (Ball 1 is 4 or 6) | "
            "2. Over ends with boundary only (Last ball is 4 or 6, zero earlier boundaries) | "
            "3. Consecutive overs starting with boundary (Over N ball 1 is 4/6 and Over N+1 ball 1 is 4/6)"
        )

        b1, b2, b3, b4 = st.columns(4)
        tot_ov = len(df_ov_view) if not df_ov_view.empty else 0
        r1_c = int(df_ov_view["starts_with_boundary"].sum()) if not df_ov_view.empty else 0
        r2_c = int(df_ov_view["ends_with_boundary_only"].sum()) if not df_ov_view.empty else 0
        r3_c = int(df_ov_view["consecutive_start_boundary"].sum()) if not df_ov_view.empty else 0

        b1.metric("Total Overs Scanned", f"{tot_ov}")
        b2.metric("Rule 1: Starts with Boundary", f"{r1_c}")
        b3.metric("Rule 2: Ends with Boundary Only", f"{r2_c}")
        b4.metric("Rule 3: Consecutive Starts w/ Boundary", f"{r3_c}")

        st.divider()

        rule_filter = st.radio(
            "Filter Overs by Boundary Criteria:",
            [
                "All Overs",
                "Rule 1: Over Starts with Boundary",
                "Rule 2: Over Ends with Boundary ONLY",
                "Rule 3: Consecutive Overs Starting with Boundary",
                "Overs Ending with Any Boundary"
            ],
            horizontal=True
        )

        df_filtered = df_ov_view.copy()
        if rule_filter == "Rule 1: Over Starts with Boundary":
            df_filtered = df_filtered[df_filtered["starts_with_boundary"] == True]
        elif rule_filter == "Rule 2: Over Ends with Boundary ONLY":
            df_filtered = df_filtered[df_filtered["ends_with_boundary_only"] == True]
        elif rule_filter == "Rule 3: Consecutive Overs Starting with Boundary":
            df_filtered = df_filtered[df_filtered["consecutive_start_boundary"] == True]
        elif rule_filter == "Overs Ending with Any Boundary":
            df_filtered = df_filtered[df_filtered["ends_with_boundary_any"] == True]

        st.write(f"Showing **{len(df_filtered)}** matching overs:")

        st.dataframe(
            df_filtered.rename(columns={
                "match": "Match Fixture",
                "season": "Season",
                "innings": "Innings",
                "over_number": "Over",
                "phase": "Phase",
                "batting_team": "Batting Team",
                "bowler": "Bowler",
                "runs": "Runs",
                "sequence": "Delivery Sequence",
                "fours": "4s",
                "sixes": "6s",
                "dots": "Dots",
                "wickets": "Wickets",
                "starts_with_boundary": "Start Boundary",
                "ends_with_boundary_only": "End Boundary Only",
                "consecutive_start_boundary": "Consecutive Start"
            })[[
                "Match Fixture", "Season", "Innings", "Over", "Phase",
                "Batting Team", "Bowler", "Runs", "Delivery Sequence",
                "4s", "6s", "Dots", "Wickets",
                "Start Boundary", "End Boundary Only", "Consecutive Start"
            ]],
            use_container_width=True,
            hide_index=True
        )

render_npl_dashboard(selected_team, selected_match_label)
