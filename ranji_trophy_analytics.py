# ranji_trophy_analytics.py
# Advanced Multi-Day & First-Class Cricket Analytics Dashboard (Ranji Trophy Elite)
# By Vishwesh Gaur

import os
import glob
import json
import time
import re
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ----------------------------------------------------
# OFFICIAL DATA ALIGNMENT REGISTRY
# Permanent reconciliation for known scorer mix-ups or official extras breakdowns
# ----------------------------------------------------
DATA_ALIGNMENT_REGISTRY = {
    "239965": {
        "bowler_corrections": {
            1: {"Ayush Doseja": "Ayush Badoni"}
        },
        "official_extras": {
            0: {"byes": 12, "legbyes": 13, "wides": 7, "noballs": 0, "penalty": 0, "total": 32}
        }
    }
}

# ----------------------------------------------------
# PAGE CONFIGURATION
# ----------------------------------------------------
st.set_page_config(
    page_title="Ranji Trophy Elite - Multi-Day Cricket Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Minimal utility CSS only (no dark theme override)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------
# DEFAULT DATA DIRECTORY & DISCOVERY
# ----------------------------------------------------
_LOCAL_PATH = Path("/Users/vishwesh/Documents/WPL&BBL/data/BCCI Domestic/International")
_RELATIVE_PATH = Path(__file__).resolve().parent / "data" / "BCCI Domestic" / "International"
DEFAULT_DIR = str(_LOCAL_PATH if _LOCAL_PATH.exists() else _RELATIVE_PATH)

_MATCH_METADATA_CACHE = {}

def discover_matches(folder_path):
    """Scan folder for match JSON files with retry resilience and in-memory fallback."""
    if not os.path.exists(folder_path):
        return []

    found_matches = []
    file_list = sorted(glob.glob(os.path.join(folder_path, "*.json")))

    for fpath in file_list:
        fname = os.path.basename(fpath)
        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            mtime = 0

        cached = _MATCH_METADATA_CACHE.get(fpath)
        if cached and cached.get("_mtime") == mtime:
            found_matches.append(cached)
            continue

        d = None
        for _ in range(3):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    d = json.load(f)
                break
            except Exception:
                time.sleep(0.05)

        if d is None:
            if cached:
                found_matches.append(cached)
            continue

        info = d.get("info", {})
        teams = info.get("teams", ["Team 1", "Team 2"])
        event = info.get("event", {})
        event_name = str(event.get("name", "Ranji Trophy")).replace("BCCI", "").replace("  ", " ").strip()
        match_num_raw = event.get("match_number", "")
        try:
            match_num_int = int(match_num_raw)
        except (ValueError, TypeError):
            match_num_int = 999

        match_str = f"Match {match_num_raw}" if match_num_raw else f"ID {os.path.splitext(fname)[0]}"
        dates = info.get("dates", [])
        date_str = dates[0] if dates else ""
        outcome = info.get("outcome", {})
        summary = outcome.get("summary", outcome.get("result", ""))

        label = f"{match_str}: {teams[0]} vs {teams[1]}"
        if date_str:
            label += f" | {date_str}"

        meta = {
            "label": label,
            "path": fpath,
            "filename": fname,
            "match_num": match_num_int,
            "teams": teams,
            "date": date_str,
            "event": event_name,
            "summary": summary,
            "_mtime": mtime
        }
        _MATCH_METADATA_CACHE[fpath] = meta
        found_matches.append(meta)

    found_matches.sort(key=lambda m: m["match_num"])
    return found_matches

# ----------------------------------------------------
# DATA PARSING HELPERS
# ----------------------------------------------------
def compute_overs_str(legal_balls):
    """Convert legal ball count to overs string like 77.3"""
    completed = legal_balls // 6
    remainder = legal_balls % 6
    if remainder > 0:
        return f"{completed}.{remainder}"
    return str(completed)

def compute_overs_float(legal_balls):
    """Convert legal ball count to overs float for RR calculation."""
    return legal_balls // 6 + (legal_balls % 6) / 6.0

def resolve_player_name(raw_name, priority_pool=None, fallback_pool=None):
    """Normalize and resolve commentary snippets or abbreviated names to full official player names."""
    if not raw_name or not isinstance(raw_name, str):
        return raw_name
    token = raw_name.split(",")[0].strip()
    token = re.sub(r"[!*()]+", "", token).strip()
    if not token:
        return raw_name
    pools = []
    if priority_pool:
        pools.append(priority_pool)
    if fallback_pool:
        pools.append(fallback_pool)
    for pool in pools:
        for p in pool:
            if p.lower() == token.lower():
                return p
        for p in pool:
            if p.split()[-1].lower() == token.lower():
                return p
        for p in pool:
            if p.split()[0].lower() == token.lower():
                return p
        for p in pool:
            if token.lower() in [w.lower() for w in p.split()]:
                return p
    return token

def parse_match_data(json_data, filter_day=None):
    """Parse complete JSON for first-class multi-day match, with optional day filter."""
    info = json_data.get("info", {})
    innings_raw = json_data.get("innings", [])
    teams = info.get("teams", [])

    players_by_team = info.get("players", {})
    all_players = []
    for t_name, plist in players_by_team.items():
        all_players.extend(plist)
    for p in info.get("registry", {}).get("people", {}).keys():
        if p not in all_players:
            all_players.append(p)
    
    parsed_innings = []
    for inn_idx, inn in enumerate(innings_raw):
        team = inn.get("team", f"Innings {inn_idx+1}")
        fielding_team = [t for t in teams if t != team][0] if teams and len(teams) > 1 else None
        bat_pool = players_by_team.get(team, [])
        bowl_pool = players_by_team.get(fielding_team, [])
        overs_list = inn.get("overs", [])
        
        # Filter overs/deliveries by day if specified
        if filter_day is not None:
            filtered_overs = []
            for o_obj in overs_list:
                ov_day = o_obj.get("day")
                delivs_today = [d for d in o_obj.get("deliveries", []) if d.get("day", ov_day) == filter_day]
                if delivs_today:
                    new_o = dict(o_obj)
                    new_o["deliveries"] = delivs_today
                    filtered_overs.append(new_o)
            overs_list = filtered_overs
        
        # Innings metrics
        batters = {}
        bowlers = {}
        extras = {"byes": 0, "legbyes": 0, "wides": 0, "noballs": 0, "penalty": 0, "total": 0}
        fow = []
        partnerships = []
        overs_stats = []
        ball_by_ball = []  # for partnership tracking
        
        tot_runs = 0
        tot_wkts = 0
        tot_legal_balls = 0
        
        for o_obj in overs_list:
            ov_num = o_obj.get("over", 0)
            ov_deliveries = o_obj.get("deliveries", [])
            
            ov_runs = 0
            ov_dots = 0
            ov_wkts = 0
            ov_fours = 0
            ov_sixes = 0
            ov_wkts_list = []
            ov_bowler = ov_deliveries[0].get("bowler", "Unknown") if ov_deliveries else "Unknown"
            ov_bowler = resolve_player_name(ov_bowler, bowl_pool, all_players)
            if ov_bowler == "Ayush Doseja" and ("Delhi" in team or "Delhi" in info.get("teams", [])):
                ov_bowler = "Ayush Badoni"
            ov_legal_balls = 0
            
            for b_idx, d in enumerate(ov_deliveries):
                b = resolve_player_name(d.get("batter", "Unknown"), bat_pool, all_players)
                ns = resolve_player_name(d.get("non_striker", "Unknown"), bat_pool, all_players)
                bw = resolve_player_name(d.get("bowler", "Unknown"), bowl_pool, all_players)
                if bw == "Ayush Doseja" and ("Delhi" in team or "Delhi" in info.get("teams", [])):
                    bw = "Ayush Badoni"
                r_dict = d.get("runs", {})
                r_b = r_dict.get("batter", 0)
                r_e = r_dict.get("extras", 0)
                r_t = r_dict.get("total", 0)
                
                tot_runs += r_t
                ov_runs += r_t
                
                # Extras breakdown
                ex_dict = d.get("extras", {})
                is_wide = "wides" in ex_dict
                is_noball = "noballs" in ex_dict
                is_legal = not is_wide and not is_noball
                
                if is_legal:
                    tot_legal_balls += 1
                    ov_legal_balls += 1
                
                if "byes" in ex_dict: extras["byes"] += ex_dict["byes"]
                if "legbyes" in ex_dict: extras["legbyes"] += ex_dict["legbyes"]
                if is_wide: extras["wides"] += ex_dict["wides"]
                if is_noball: extras["noballs"] += ex_dict["noballs"]
                if "penalty" in ex_dict: extras["penalty"] += ex_dict["penalty"]
                extras["total"] += r_e
                
                # Batters tracking
                if b not in batters:
                    batters[b] = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "dots": 0, "dismissal": "not out"}
                if ns not in batters:
                    batters[ns] = {"runs": 0, "balls": 0, "fours": 0, "sixes": 0, "dots": 0, "dismissal": "not out"}
                
                if not is_wide:
                    batters[b]["balls"] += 1
                batters[b]["runs"] += r_b
                if r_b == 4:
                    batters[b]["fours"] += 1
                    ov_fours += 1
                elif r_b == 6:
                    batters[b]["sixes"] += 1
                    ov_sixes += 1
                elif r_b == 0 and not is_wide:
                    batters[b]["dots"] += 1
                
                # Bowlers tracking
                if bw not in bowlers:
                    bowlers[bw] = {"balls": 0, "runs": 0, "wickets": 0, "dots": 0, "maidens": 0, "wides": 0, "noballs": 0, "fours": 0, "sixes": 0}
                
                if is_legal:
                    bowlers[bw]["balls"] += 1
                if is_wide: bowlers[bw]["wides"] += ex_dict.get("wides", 1)
                if is_noball: bowlers[bw]["noballs"] += ex_dict.get("noballs", 1)
                
                bw_conceded = r_b + ex_dict.get("wides", 0) + ex_dict.get("noballs", 0)
                bowlers[bw]["runs"] += bw_conceded
                if r_b == 4: bowlers[bw]["fours"] += 1
                if r_b == 6: bowlers[bw]["sixes"] += 1
                
                if bw_conceded == 0 and is_legal:
                    bowlers[bw]["dots"] += 1
                    ov_dots += 1
                
                clean_wickets = []
                for w in d.get("wickets", []):
                    w_c = dict(w)
                    if "player_out" in w_c:
                        w_c["player_out"] = resolve_player_name(w_c["player_out"], bat_pool, all_players)
                    clean_wickets.append(w_c)

                # Store ball-by-ball for partnership
                ball_entry = {
                    "over": ov_num,
                    "ball_idx": b_idx,
                    "batter": b,
                    "non_striker": ns,
                    "bowler": bw,
                    "batter_runs": r_b,
                    "extras_runs": r_e,
                    "total_runs": r_t,
                    "is_wide": is_wide,
                    "wickets": clean_wickets
                }
                ball_by_ball.append(ball_entry)
                
                # Wickets
                if "wickets" in d:
                    for w in clean_wickets:
                        tot_wkts += 1
                        ov_wkts += 1
                        p_out = resolve_player_name(w.get("player_out", b), bat_pool, all_players)
                        kind = w.get("kind", "dismissed")
                        fldrs = [resolve_player_name(f.get("name"), bowl_pool, all_players) for f in w.get("fielders", []) if f.get("name")]
                        
                        f_str = f"c {fldrs[0]} " if fldrs else "c " if kind == "caught" else ""
                        if kind == "bowled": dis_str = f"b {bw}"
                        elif kind == "caught": dis_str = f"{f_str}b {bw}"
                        elif kind == "lbw": dis_str = f"lbw b {bw}"
                        elif kind == "run out": dis_str = f"run out ({fldrs[0]})" if fldrs else "run out"
                        elif kind == "stumped": dis_str = f"st {fldrs[0]} b {bw}" if fldrs else f"st b {bw}"
                        else: dis_str = f"{kind} b {bw}"
                        
                        if p_out in batters:
                            batters[p_out]["dismissal"] = dis_str
                        
                        if kind not in ["run out", "retired out", "retired hurt"]:
                            bowlers[bw]["wickets"] += 1
                        
                        cur_ball_str = f"{ov_num+1}.{b_idx+1}"
                        ov_wkts_list.append({"player": p_out, "bowler": bw, "kind": kind, "ball": cur_ball_str})
                        
                        fow.append({
                            "wicket": tot_wkts,
                            "score": tot_runs,
                            "player": p_out,
                            "over": cur_ball_str
                        })

            # Over level stats for Manhattan, Hourly, Spells
            is_maiden = (ov_runs == 0 and ov_legal_balls >= 6)
            overs_stats.append({
                "over_num": ov_num, # 0-indexed
                "over_display": ov_num + 1,
                "bowler": ov_bowler,
                "runs": ov_runs,
                "dots": ov_dots,
                "wickets": ov_wkts,
                "wickets_list": ov_wkts_list,
                "fours": ov_fours,
                "sixes": ov_sixes,
                "balls": len(ov_deliveries),
                "is_maiden": is_maiden,
                "deliveries": ov_deliveries
            })
        
        # --- Build partnerships from ball_by_ball ---
        partnerships = _build_partnerships(ball_by_ball)

        # Calculate maidens in bowler stats
        for b_name in bowlers:
            b_ovs = [os for os in overs_stats if os["bowler"] == b_name]
            bowlers[b_name]["maidens"] = sum(1 for os in b_ovs if os["is_maiden"])

        # Prioritize official bowling figures in Full Match view
        if filter_day is None and inn.get("official_bowlers"):
            for bw_name, off_b in inn["official_bowlers"].items():
                ov_str = str(off_b.get("overs", "0"))
                if "." in ov_str:
                    comp_ov, rem = map(int, ov_str.split("."))
                else:
                    comp_ov, rem = int(ov_str) if str(ov_str).isdigit() else 0, 0
                b_balls = comp_ov * 6 + rem
                bowlers[bw_name] = {
                    "balls": b_balls,
                    "runs": int(off_b.get("runs", 0)),
                    "wickets": int(off_b.get("wickets", 0)),
                    "maidens": int(off_b.get("maidens", 0)),
                    "dots": int(off_b.get("dots", 0)),
                    "fours": int(off_b.get("fours", 0)),
                    "sixes": int(off_b.get("sixes", 0)),
                    "wides": int(off_b.get("wides", 0)),
                    "noballs": int(off_b.get("noballs", 0)),
                }
        
        overs_str = compute_overs_str(tot_legal_balls)
        overs_float = compute_overs_float(tot_legal_balls)
        
        parsed_innings.append({
            "innings_index": inn_idx + 1,
            "team": team,
            "total_runs": tot_runs,
            "total_wickets": tot_wkts,
            "did_not_bat": (tot_legal_balls == 0 and tot_runs == 0),
            "total_overs": overs_str,
            "total_overs_count": len(overs_list),
            "total_legal_balls": tot_legal_balls,
            "run_rate": round(tot_runs / overs_float, 2) if overs_float > 0 else 0.0,
            "batters": batters,
            "bowlers": bowlers,
            "extras": extras,
            "fow": fow,
            "partnerships": partnerships,
            "overs_stats": overs_stats,
            "ball_by_ball": ball_by_ball
        })

    return {
        "info": info,
        "innings": parsed_innings
    }


def _build_partnerships(ball_by_ball):
    """
    Build partnership data from ball-by-ball records.
    Tracks which two batters are at the crease and accumulates
    runs/balls for each partnership stand.
    """
    if not ball_by_ball:
        return []

    partnerships = []
    wkt_num = 1

    # Current pair at crease
    on_strike = None
    off_strike = None
    p_runs = 0
    p_balls = 0
    b1_name = None
    b2_name = None
    b1_runs = 0
    b2_runs = 0
    p_start_ov = "0.1"

    for ball in ball_by_ball:
        batter = ball["batter"]
        non_striker = ball["non_striker"]

        # Initialize pair from first ball
        if on_strike is None:
            on_strike = batter
            off_strike = non_striker
            b1_name = batter
            b2_name = non_striker

        # Update who is at crease (handles new batter replacing dismissed one)
        current_pair = {on_strike, off_strike}
        ball_pair = {batter, non_striker}
        if ball_pair != current_pair:
            # A new batter has come in — update the pair
            new_batter = ball_pair - current_pair
            if new_batter:
                departed = current_pair - ball_pair
                for dep in departed:
                    if dep == on_strike:
                        on_strike = new_batter.pop()
                    elif dep == off_strike:
                        off_strike = new_batter.pop()
                    break
                if new_batter:
                    # Both changed (shouldn't normally happen)
                    on_strike = batter
                    off_strike = non_striker
            # Update b1/b2 names if needed
            if on_strike not in (b1_name, b2_name):
                if b1_name is None:
                    b1_name = on_strike
                else:
                    b2_name = on_strike
            if off_strike not in (b1_name, b2_name):
                if b1_name is None:
                    b1_name = off_strike
                else:
                    b2_name = off_strike

        # Accumulate
        p_runs += ball["total_runs"]
        if not ball["is_wide"]:
            p_balls += 1

        # Track individual batter runs
        if batter == b1_name:
            b1_runs += ball["batter_runs"]
        elif batter == b2_name:
            b2_runs += ball["batter_runs"]

        # Handle wickets
        if ball["wickets"]:
            for w in ball["wickets"]:
                p_out = w.get("player_out", batter)
                cur_ball_str = f"{ball['over']+1}.{ball['ball_idx']+1}"

                _ordinal = lambda n: f"{n}{'st' if n==1 else 'nd' if n==2 else 'rd' if n==3 else 'th'}"

                partnerships.append({
                    "wicket_no": wkt_num,
                    "wicket_label": f"{_ordinal(wkt_num)} Wicket",
                    "batter1": b1_name or "Unknown",
                    "b1_runs": b1_runs,
                    "batter2": b2_name or "Unknown",
                    "b2_runs": b2_runs,
                    "runs": p_runs,
                    "balls": p_balls,
                    "over_range": f"{p_start_ov} - {cur_ball_str}",
                    "unbroken": False
                })
                wkt_num += 1

                # Reset for next partnership
                p_runs = 0
                p_balls = 0
                b1_runs = 0
                b2_runs = 0
                next_ball_ov = ball['over'] + 1
                next_ball_idx = ball['ball_idx'] + 2
                p_start_ov = f"{next_ball_ov}.{next_ball_idx if next_ball_idx <= 6 else 1}"

                # The dismissed batter leaves; update pair
                if p_out == on_strike:
                    on_strike = None
                elif p_out == off_strike:
                    off_strike = None

                # Reset b1/b2 for new partnership
                remaining = on_strike or off_strike
                b1_name = remaining
                b2_name = None

    # Unbroken final stand
    if p_balls > 0 or p_runs > 0:
        _ordinal = lambda n: f"{n}{'st' if n==1 else 'nd' if n==2 else 'rd' if n==3 else 'th'}"
        partnerships.append({
            "wicket_no": wkt_num,
            "wicket_label": f"{_ordinal(wkt_num)} Wicket (Unbroken)",
            "batter1": b1_name or "Unknown",
            "b1_runs": b1_runs,
            "batter2": b2_name or "Unknown",
            "b2_runs": b2_runs,
            "runs": p_runs,
            "balls": p_balls,
            "over_range": f"{p_start_ov} - end",
            "unbroken": True
        })

    return partnerships


# ----------------------------------------------------
# 1. SPELL-WISE BOWLER ANALYSIS
# ----------------------------------------------------
def compute_bowler_spells(innings_data):
    """
    Computes spell-by-spell performance for all bowlers in an innings.
    A new spell begins whenever a bowler has a gap of more than 1 over
    (i.e., they skip more than the standard alternate-over rotation).
    Standard rotation: gap of 2 (bowler bowls every other over).
    Spell break: gap > 2.
    """
    overs_stats = innings_data.get("overs_stats", [])
    if not overs_stats:
        return pd.DataFrame()

    # Find unique bowlers in order of appearance
    bowler_order = []
    for os in overs_stats:
        if os["bowler"] not in bowler_order:
            bowler_order.append(os["bowler"])

    all_spells = []
    for bw in bowler_order:
        bw_overs = [os for os in overs_stats if os["bowler"] == bw]
        if not bw_overs:
            continue
            
        spells = []
        cur_spell = []
        for os in bw_overs:
            if not cur_spell:
                cur_spell.append(os)
            else:
                prev_ov = cur_spell[-1]["over_num"]
                # Standard alternate-over gap is 2 (bowler bowls 1, rests 1, bowls again)
                # A gap > 2 means the bowler took a break
                if os["over_num"] - prev_ov <= 2:
                    cur_spell.append(os)
                else:
                    spells.append(cur_spell)
                    cur_spell = [os]
        if cur_spell:
            spells.append(cur_spell)

        for s_idx, sp in enumerate(spells):
            sp_ov = len(sp)
            sp_runs = sum(x["runs"] for x in sp)
            sp_dots = sum(x["dots"] for x in sp)
            sp_wkts = sum(x["wickets"] for x in sp)
            sp_maidens = sum(1 for x in sp if x["is_maiden"])
            sp_fours = sum(x["fours"] for x in sp)
            sp_sixes = sum(x["sixes"] for x in sp)
            sp_econ = round(sp_runs / sp_ov, 2) if sp_ov > 0 else 0.0
            sp_dot_pct = round(sp_dots / (sp_ov * 6) * 100, 1) if sp_ov > 0 else 0.0
            
            wkts_details = []
            for os in sp:
                for w in os.get("wickets_list", []):
                    wkts_details.append(f"{w['player']} ({w['kind']})")

            # Show actual overs bowled (not range)
            actual_overs = [x["over_display"] for x in sp]
            start_ov = actual_overs[0]
            end_ov = actual_overs[-1]
            ov_range_str = f"Over {start_ov}" if start_ov == end_ov else f"Overs {start_ov}-{end_ov}"

            all_spells.append({
                "Bowler": bw,
                "Spell": f"Spell {s_idx+1}",
                "Spell_No": s_idx + 1,
                "Over Range": ov_range_str,
                "Actual Overs": ", ".join(str(x) for x in actual_overs),
                "Start Over": start_ov,
                "End Over": end_ov,
                "Overs": sp_ov,
                "Maidens": sp_maidens,
                "Runs": sp_runs,
                "Wickets": sp_wkts,
                "Economy": sp_econ,
                "Dots": sp_dots,
                "Dot %": sp_dot_pct,
                "4s": sp_fours,
                "6s": sp_sixes,
                "Wickets Taken": ", ".join(wkts_details) if wkts_details else "-"
            })

    return pd.DataFrame(all_spells)

# ----------------------------------------------------
# 2. HOURLY & SESSION SUMMARY
# ----------------------------------------------------
def compute_time_blocks(innings_data, block_overs=15, block_type="Hour"):
    """
    Computes session or hourly summaries:
    Overs, runs, run rate, wickets lost, dot%, top scorers/bowlers.
    """
    overs_stats = innings_data.get("overs_stats", [])
    total_overs = len(overs_stats)
    if total_overs == 0:
        return pd.DataFrame()

    num_blocks = (total_overs + block_overs - 1) // block_overs
    blocks = []
    
    for b_idx in range(num_blocks):
        start_ov = b_idx * block_overs
        end_ov = min(total_overs, (b_idx + 1) * block_overs)
        chunk = overs_stats[start_ov:end_ov]
        
        b_runs = sum(x["runs"] for x in chunk)
        b_ov = len(chunk)
        b_dots = sum(x["dots"] for x in chunk)
        b_wkts_count = sum(x["wickets"] for x in chunk)
        b_fours = sum(x["fours"] for x in chunk)
        b_sixes = sum(x["sixes"] for x in chunk)
        b_rr = round(b_runs / b_ov, 2) if b_ov > 0 else 0.0
        b_dot_pct = round(b_dots / (b_ov * 6) * 100, 1) if b_ov > 0 else 0.0

        wkts_details = []
        for x in chunk:
            for w in x.get("wickets_list", []):
                wkts_details.append(f"{w['player']} ({w['kind']} b {w['bowler']})")

        # Top batter in this block
        bat_runs = {}
        bow_wkts = {}
        for x in chunk:
            for d in x["deliveries"]:
                bt = d.get("batter")
                r = d.get("runs", {}).get("batter", 0)
                bat_runs[bt] = bat_runs.get(bt, 0) + r
                if "wickets" in d:
                    for w in d["wickets"]:
                        if w.get("kind") not in ["run out", "retired out", "retired hurt"]:
                            bw = d.get("bowler")
                            bow_wkts[bw] = bow_wkts.get(bw, 0) + 1

        top_bat = max(bat_runs.items(), key=lambda t: t[1])[0] + f" ({max(bat_runs.values())})" if bat_runs else "-"
        top_bow = max(bow_wkts.items(), key=lambda t: t[1])[0] + f" ({max(bow_wkts.values())}w)" if bow_wkts and max(bow_wkts.values()) > 0 else "-"

        # Session dominance assessment
        if b_wkts_count >= 3:
            dom = "Bowling Team"
        elif b_runs >= (block_overs * 3.5) and b_wkts_count <= 1:
            dom = "Batting Team"
        else:
            dom = "Evenly Poised"

        block_label = f"{block_type} {b_idx+1}"
        if block_type == "Session":
            session_names = ["Morning (Pre-Lunch)", "Afternoon (Lunch-Tea)", "Evening (Post-Tea)", "Day 2 Morning", "Day 2 Afternoon", "Day 2 Evening"]
            if b_idx < len(session_names):
                block_label = f"Session {b_idx+1}: {session_names[b_idx]}"

        blocks.append({
            "Interval": block_label,
            "Overs Span": f"Overs {start_ov+1}-{end_ov}",
            "Overs Bowled": b_ov,
            "Runs": b_runs,
            "Run Rate": b_rr,
            "Wickets Lost": b_wkts_count,
            "Wickets Details": ", ".join(wkts_details) if wkts_details else "None",
            "Dot %": b_dot_pct,
            "Boundaries": f"{b_fours}x4, {b_sixes}x6",
            "Top Batter": top_bat,
            "Top Bowler": top_bow,
            "Phase Dominance": dom
        })

    return pd.DataFrame(blocks)

# ----------------------------------------------------
# 3. SCORECARD FORMATTERS
# ----------------------------------------------------
def format_batting_scorecard(batters_dict):
    """Format batting scorecard dataframe."""
    rows = []
    for b_name, b_stat in batters_dict.items():
        runs = b_stat["runs"]
        balls = b_stat["balls"]
        sr = round(runs / balls * 100, 2) if balls > 0 else 0.0
        dots = b_stat["dots"]
        dot_pct = round(dots / balls * 100, 1) if balls > 0 else 0.0
        
        rows.append({
            "Batter": b_name,
            "Dismissal": b_stat["dismissal"],
            "Runs": runs,
            "Balls": balls,
            "4s": b_stat["fours"],
            "6s": b_stat["sixes"],
            "Strike Rate": sr,
            "Dots": dots,
            "Dot %": dot_pct
        })
    if not rows:
        return pd.DataFrame(columns=["Batter", "Dismissal", "Runs", "Balls", "4s", "6s", "Strike Rate", "Dots", "Dot %"])
    return pd.DataFrame(rows)

def format_bowling_scorecard(bowlers_dict):
    """Format bowling scorecard dataframe."""
    rows = []
    for bw_name, bw_stat in bowlers_dict.items():
        balls = bw_stat["balls"]
        completed_ov = balls // 6
        rem_balls = balls % 6
        ov_str = f"{completed_ov}.{rem_balls}" if rem_balls > 0 else str(completed_ov)
        ov_float = completed_ov + (rem_balls / 6.0)
        
        runs = bw_stat["runs"]
        wkts = bw_stat["wickets"]
        maidens = bw_stat["maidens"]
        econ = round(runs / ov_float, 2) if ov_float > 0 else 0.0
        dots = bw_stat["dots"]
        dot_pct = round(dots / balls * 100, 1) if balls > 0 else 0.0
        
        rows.append({
            "Bowler": bw_name,
            "Overs": ov_str,
            "Maidens": maidens,
            "Runs": runs,
            "Wickets": wkts,
            "Economy": econ,
            "Dots": dots,
            "Dot %": dot_pct,
            "4s": bw_stat["fours"],
            "6s": bw_stat["sixes"],
            "Wides": bw_stat["wides"],
            "No Balls": bw_stat["noballs"]
        })
    df = pd.DataFrame(rows)
    if df.empty or "Wickets" not in df.columns:
        return pd.DataFrame(columns=["Bowler", "Overs", "Maidens", "Runs", "Wickets", "Economy", "Dots", "Dot %", "4s", "6s", "Wides", "No Balls"])
    return df.sort_values("Wickets", ascending=False)

# ----------------------------------------------------
# 4. SPECIAL FEATS (3+ WICKETS IN AN OVER & HAT-TRICKS)
# ----------------------------------------------------
def scan_special_feats(json_data_list):
    """
    Scans matches for:
    - 3 or more wickets in a single over
    - Hat-tricks (3 wickets in 3 consecutive deliveries by a bowler)
    """
    three_wkt_overs = []
    hat_tricks = []
    
    for match_item in json_data_list:
        d = match_item["data"]
        label = match_item["label"]
        info = d.get("info", {})
        teams = info.get("teams", ["Team 1", "Team 2"])
        match_title = f"{teams[0]} vs {teams[1]}"
        
        for inn_idx, inn in enumerate(d.get("innings", [])):
            team = inn.get("team", f"Inn {inn_idx+1}")
            inn_label = f"{team} (Innings {inn_idx+1})"
            
            bowler_deliv_seq = {}
            
            for o in inn.get("overs", []):
                ov_num = o.get("over", 0) + 1
                ov_wkts = []
                
                for b_idx, deliv in enumerate(o.get("deliveries", [])):
                    bw = deliv.get("bowler", "Unknown")
                    if bw not in bowler_deliv_seq:
                        bowler_deliv_seq[bw] = []
                    
                    wkts = deliv.get("wickets", [])
                    is_bowler_wkt = len(wkts) > 0 and wkts[0].get("kind") not in ["run out", "retired out", "retired hurt"]
                    
                    bowler_deliv_seq[bw].append({
                        "over": ov_num,
                        "ball_in_over": b_idx + 1,
                        "is_wkt": is_bowler_wkt,
                        "wkt_details": wkts[0] if wkts else None
                    })
                    
                    if wkts:
                        for w in wkts:
                            ov_wkts.append({
                                "bowler": bw,
                                "player_out": w.get("player_out"),
                                "kind": w.get("kind"),
                                "ball": f"{ov_num}.{b_idx+1}"
                            })

                if len(ov_wkts) >= 3:
                    w_summary = ", ".join(f"{w['player_out']} ({w['kind']} b {w['bowler']})" for w in ov_wkts)
                    three_wkt_overs.append({
                        "Match": match_title,
                        "Innings": inn_label,
                        "Bowler": ov_wkts[0]["bowler"],
                        "Over": f"Over {ov_num}",
                        "Wickets": len(ov_wkts),
                        "Dismissals": w_summary
                    })
            
            # Check for Hat-tricks
            for bw, b_seq in bowler_deliv_seq.items():
                for idx in range(len(b_seq) - 2):
                    if b_seq[idx]["is_wkt"] and b_seq[idx+1]["is_wkt"] and b_seq[idx+2]["is_wkt"]:
                        d1 = b_seq[idx]
                        d2 = b_seq[idx+1]
                        d3 = b_seq[idx+2]
                        hat_tricks.append({
                            "Match": match_title,
                            "Innings": inn_label,
                            "Bowler": bw,
                            "Balls Span": f"Ov {d1['over']}.{d1['ball_in_over']} to {d3['over']}.{d3['ball_in_over']}",
                            "Victims": f"1. {d1['wkt_details']['player_out']} ({d1['wkt_details']['kind']}) | 2. {d2['wkt_details']['player_out']} ({d2['wkt_details']['kind']}) | 3. {d3['wkt_details']['player_out']} ({d3['wkt_details']['kind']})"
                        })
                        
    return pd.DataFrame(three_wkt_overs), pd.DataFrame(hat_tricks)

# ----------------------------------------------------
# 5. MULTI-DAY SPECIFIC METRICS
# ----------------------------------------------------
def compute_multiday_metrics(innings_data):
    """
    Computes key First-Class & Multi-day analytics:
    - Ball-Age Phases (New Ball 1-20, Settled 21-60, Old Ball 61-80, Second New Ball 81+)
    - Attrition & Defensive Solidity (Balls Faced, Dots Defended %)
    - Batting Order Contribution (Top Order 1-3 vs Middle 4-7 vs Tail 8-11)
    """
    overs_stats = innings_data.get("overs_stats", [])
    if not overs_stats:
        return {}, pd.DataFrame(), pd.DataFrame()
        
    # 1. Ball Age Phases
    phases = {
        "Phase 1: New Ball (Overs 1-20)": {"overs": 0, "runs": 0, "balls": 0, "wkts": 0, "dots": 0, "fours": 0, "sixes": 0},
        "Phase 2: Settled Ball (Overs 21-60)": {"overs": 0, "runs": 0, "balls": 0, "wkts": 0, "dots": 0, "fours": 0, "sixes": 0},
        "Phase 3: Worn/Old Ball (Overs 61-80)": {"overs": 0, "runs": 0, "balls": 0, "wkts": 0, "dots": 0, "fours": 0, "sixes": 0},
        "Phase 4: Second New Ball (Overs 81+)": {"overs": 0, "runs": 0, "balls": 0, "wkts": 0, "dots": 0, "fours": 0, "sixes": 0}
    }
    
    for os in overs_stats:
        ov = os["over_display"]
        if ov <= 20: p_key = "Phase 1: New Ball (Overs 1-20)"
        elif ov <= 60: p_key = "Phase 2: Settled Ball (Overs 21-60)"
        elif ov <= 80: p_key = "Phase 3: Worn/Old Ball (Overs 61-80)"
        else: p_key = "Phase 4: Second New Ball (Overs 81+)"
        
        phases[p_key]["overs"] += 1
        phases[p_key]["runs"] += os["runs"]
        phases[p_key]["dots"] += os["dots"]
        phases[p_key]["wkts"] += os["wickets"]
        phases[p_key]["fours"] += os["fours"]
        phases[p_key]["sixes"] += os["sixes"]

    phase_rows = []
    for pk, pv in phases.items():
        if pv["overs"] > 0:
            rr = round(pv["runs"] / pv["overs"], 2)
            dot_pct = round(pv["dots"] / (pv["overs"] * 6) * 100, 1)
            phase_rows.append({
                "Ball Age Phase": pk,
                "Overs": pv["overs"],
                "Runs": pv["runs"],
                "Wickets": pv["wkts"],
                "Run Rate": rr,
                "Dot %": dot_pct,
                "Boundaries": f"{pv['fours']}x4, {pv['sixes']}x6"
            })
    df_phases = pd.DataFrame(phase_rows)

    # 2. Batting Order Breakdown
    batters = list(innings_data.get("batters", {}).items())
    top_order = batters[:3]
    middle_order = batters[3:7]
    tail_order = batters[7:]

    order_breakdown = [
        {"Section": "Top Order (Positions 1-3)", "Runs": sum(b[1]["runs"] for b in top_order), "Balls": sum(b[1]["balls"] for b in top_order)},
        {"Section": "Middle Order (Positions 4-7)", "Runs": sum(b[1]["runs"] for b in middle_order), "Balls": sum(b[1]["balls"] for b in middle_order)},
        {"Section": "Tailenders (Positions 8-11)", "Runs": sum(b[1]["runs"] for b in tail_order), "Balls": sum(b[1]["balls"] for b in tail_order)}
    ]
    df_order = pd.DataFrame(order_breakdown)
    tot_inn_runs = innings_data.get("total_runs", 1) or 1
    df_order["% of Total Runs"] = (df_order["Runs"] / tot_inn_runs * 100).round(1)

    return phases, df_phases, df_order

# ----------------------------------------------------
# 6. ADVANCED FIRST-CLASS ANALYTICS SUITE
# ----------------------------------------------------
def compute_bowler_tandems(inn, min_overs=3):
    """
    Detect bowling pairs operating in tandem from opposite ends in alternating overs.
    Red-ball bowling pressure is built in hunting packs.
    """
    overs_stats = inn.get("overs_stats", [])
    if len(overs_stats) < min_overs:
        return pd.DataFrame()
    
    tandems = []
    i = 0
    while i < len(overs_stats) - 1:
        b1 = overs_stats[i].get("bowler", "Unknown")
        b2 = overs_stats[i+1].get("bowler", "Unknown")
        if b1 != b2 and b1 != "Unknown" and b2 != "Unknown":
            pair_seq = [overs_stats[i], overs_stats[i+1]]
            j = i + 2
            expected = b1
            while j < len(overs_stats):
                nxt_bw = overs_stats[j].get("bowler", "Unknown")
                if nxt_bw == expected:
                    pair_seq.append(overs_stats[j])
                    expected = b2 if expected == b1 else b1
                    j += 1
                else:
                    break
            
            if len(pair_seq) >= min_overs:
                tot_o = len(pair_seq)
                tot_r = sum(o["runs"] for o in pair_seq)
                tot_w = sum(o["wickets"] for o in pair_seq)
                tot_d = sum(o["dots"] for o in pair_seq)
                tot_b = sum(len(o.get("deliveries", [])) for o in pair_seq)
                
                b1_ovs = [o for o in pair_seq if o["bowler"] == b1]
                b1_r = sum(o["runs"] for o in b1_ovs)
                b1_w = sum(o["wickets"] for o in b1_ovs)
                b1_econ = round(b1_r / len(b1_ovs), 2) if b1_ovs else 0.0
                
                b2_ovs = [o for o in pair_seq if o["bowler"] == b2]
                b2_r = sum(o["runs"] for o in b2_ovs)
                b2_w = sum(o["wickets"] for o in b2_ovs)
                b2_econ = round(b2_r / len(b2_ovs), 2) if b2_ovs else 0.0
                
                if b1_w > b2_w:
                    strike_bw, anchor_bw = b1, b2
                elif b2_w > b1_w:
                    strike_bw, anchor_bw = b2, b1
                else:
                    strike_bw = b1 if b1_econ <= b2_econ else b2
                    anchor_bw = b2 if strike_bw == b1 else b1
                
                tandem_pair_name = f"{min(b1, b2)} & {max(b1, b2)}"
                econ = round(tot_r / tot_o, 2)
                dot_pct = round((tot_d / tot_b) * 100, 1) if tot_b else 0.0
                
                start_ov = pair_seq[0].get("over_display", pair_seq[0].get("over_num", 0) + 1)
                end_ov = pair_seq[-1].get("over_display", pair_seq[-1].get("over_num", 0) + 1)
                
                tandems.append({
                    "Tandem Pair": tandem_pair_name,
                    "Overs Span": f"Ovs {start_ov} - {end_ov}",
                    "Tandem Overs": tot_o,
                    "Runs": tot_r,
                    "Wickets": tot_w,
                    "Economy": econ,
                    "Dot %": dot_pct,
                    "Strike Bowler": strike_bw,
                    "Pressure Anchor": anchor_bw,
                    f"{b1} Figures": f"{len(b1_ovs)}-{b1_r}-{b1_w}",
                    f"{b2} Figures": f"{len(b2_ovs)}-{b2_r}-{b2_w}"
                })
                i = j - 1
        i += 1
    return pd.DataFrame(tandems)


def compute_pressure_chains(inn, window_balls=18):
    """
    Analyzes the dot ball chains and pressure buildup in the 18 deliveries immediately prior to each dismissal.
    Multi-day wickets are earned through sustained dot-ball attrition.
    """
    bbb = inn.get("ball_by_ball", [])
    if not bbb:
        return pd.DataFrame()
    
    pressure_rows = []
    wkt_idx = 0
    for i, ball in enumerate(bbb):
        if ball.get("wickets"):
            for w in ball["wickets"]:
                wkt_idx += 1
                p_out = w.get("player_out", ball.get("batter"))
                kind = w.get("kind", "dismissed")
                bw = ball.get("bowler", "Unknown")
                ov_str = f"{ball['over']}.{ball['ball_idx']+1}"
                
                start_i = max(0, i - window_balls)
                leadup = bbb[start_i:i]
                
                batter_leadup = [b for b in bbb[:i] if b.get("batter") == p_out][-15:]
                
                tot_dots = sum(1 for b in leadup if b.get("total_runs", 0) == 0)
                tot_runs = sum(b.get("total_runs", 0) for b in leadup)
                leadup_len = len(leadup)
                dot_pct = round((tot_dots / leadup_len) * 100, 1) if leadup_len > 0 else 0.0
                leadup_econ = round((tot_runs / (leadup_len / 6.0)), 2) if leadup_len > 0 else 0.0
                
                consec_dots = 0
                for b in reversed(batter_leadup):
                    if b.get("batter_runs", 0) == 0:
                        consec_dots += 1
                    else:
                        break
                
                if dot_pct >= 70 or consec_dots >= 4:
                    rating = "Severe Choke (Dot Attrition)"
                elif dot_pct >= 50 or consec_dots >= 2:
                    rating = "Sustained Pressure"
                else:
                    rating = "Against Run of Play"
                
                pressure_rows.append({
                    "Wicket": f"#{wkt_idx}",
                    "Batter Dismissed": p_out,
                    "Dismissal": f"{kind} b {bw}",
                    "Over": ov_str,
                    "Lead-up Balls": leadup_len,
                    "Lead-up Dots": tot_dots,
                    "Lead-up Dot %": dot_pct,
                    "Lead-up Runs": tot_runs,
                    "Lead-up RR": leadup_econ,
                    "Batter Consec. Dots": consec_dots,
                    "Pressure Verdict": rating
                })
    return pd.DataFrame(pressure_rows)


def compute_settlement_index(inn, danger_threshold=30):
    """
    Measures batter vulnerability in the Crease Settlement Window (first 30 balls)
    versus the Settled Phase (balls 31+).
    """
    bbb = inn.get("ball_by_ball", [])
    if not bbb:
        return pd.DataFrame()
    
    batter_deliveries = {}
    for ball in bbb:
        b = ball.get("batter")
        if not b:
            continue
        if ball.get("is_wide"):
            continue
        if b not in batter_deliveries:
            batter_deliveries[b] = []
        batter_deliveries[b].append(ball)
    
    rows = []
    batters_dict = inn.get("batters", {})
    for b, balls in batter_deliveries.items():
        if len(balls) < 10:
            continue
        
        p1 = balls[:danger_threshold]
        p2 = balls[danger_threshold:] if len(balls) > danger_threshold else []
        
        p1_r = sum(x.get("batter_runs", 0) for x in p1)
        p1_dots = sum(1 for x in p1 if x.get("batter_runs", 0) == 0)
        p1_b = len(p1)
        p1_sr = round((p1_r / p1_b) * 100, 1) if p1_b > 0 else 0.0
        p1_dot_pct = round((p1_dots / p1_b) * 100, 1) if p1_b > 0 else 0.0
        
        has_set = len(p2) > 0
        p2_r = sum(x.get("batter_runs", 0) for x in p2) if has_set else 0
        p2_dots = sum(1 for x in p2 if x.get("batter_runs", 0) == 0) if has_set else 0
        p2_b = len(p2)
        p2_sr = round((p2_r / p2_b) * 100, 1) if p2_b > 0 else 0.0
        p2_dot_pct = round((p2_dots / p2_b) * 100, 1) if p2_b > 0 else 0.0
        
        accel = round(p2_sr - p1_sr, 1) if has_set else 0.0
        
        dis = batters_dict.get(b, {}).get("dismissal", "not out")
        is_out = (dis != "not out")
        
        if not has_set:
            status = "Dismissed in Danger Window (<30b)" if is_out else "Active in Danger Window"
        else:
            if accel > 15:
                status = "Accelerated Post-Settlement"
            elif accel > -10:
                status = "Steady Anchor Post-Settlement"
            else:
                status = "Defensive Attrition Post-Settlement"
        
        rows.append({
            "Batter": b,
            "Total Balls": len(balls),
            "Total Runs": p1_r + p2_r,
            "Settlement Runs (<=30b)": p1_r,
            "Settlement SR": p1_sr,
            "Settlement Dot %": p1_dot_pct,
            "Set Runs (31+b)": p2_r if has_set else None,
            "Set SR": p2_sr if has_set else None,
            "Set Dot %": p2_dot_pct if has_set else None,
            "SR Shift": accel if has_set else None,
            "Settlement Status": status
        })
    
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Total Balls", ascending=False).reset_index(drop=True)
    return df


def detect_batting_collapses(inn, min_wickets=3, max_runs=25, max_overs=8.0):
    """
    Detects clustered batting collapses where a team lost 3+ wickets within 25 runs or 8 overs.
    """
    fow = inn.get("fow", [])
    if len(fow) < min_wickets:
        return pd.DataFrame()
    
    collapses = []
    for length in range(min_wickets, len(fow) + 1):
        for i in range(len(fow) - length + 1):
            j = i + length - 1
            wkts_lost = length
            runs_span = fow[j]["score"] - fow[i]["score"]
            try:
                ov_start = float(fow[i]["over"])
                ov_end = float(fow[j]["over"])
                overs_elapsed = round(ov_end - ov_start, 1)
            except Exception:
                overs_elapsed = 0.0
            
            if runs_span <= max_runs or (0 < overs_elapsed <= max_overs):
                batters_out = [fow[k]["player"] for k in range(i, j + 1)]
                severity = "Catastrophic Collapse" if (wkts_lost >= 4 or runs_span <= 15) else "Major Collapse"
                collapses.append({
                    "Collapse Span": f"Wickets {fow[i]['wicket']} to {fow[j]['wicket']}",
                    "Wickets Lost": wkts_lost,
                    "Runs Scored": runs_span,
                    "Overs Elapsed": f"{overs_elapsed} ov",
                    "Score Transition": f"{fow[i]['score']}/{fow[i]['wicket']-1} -> {fow[j]['score']}/{fow[j]['wicket']}",
                    "Dismissed Batters": ", ".join(batters_out),
                    "Severity": severity
                })
    
    if not collapses:
        return pd.DataFrame()
    
    return pd.DataFrame(collapses).drop_duplicates(subset=["Collapse Span"]).reset_index(drop=True)

# ----------------------------------------------------
# SIDEBAR CONTROLS & MATCH LOADING
# ----------------------------------------------------
with st.sidebar:
    st.markdown("### Ranji Trophy Elite")
    st.caption("Indian Domestic Multi-Day Match Analytics")
    st.markdown("---")
    
    # Discover matches from default directory
    available_matches = discover_matches(DEFAULT_DIR)
    
    selected_json_data = None
    selected_match_label = ""
    
    if available_matches:
        # Preserve user selection across re-runs and browser reloads
        saved_match = st.query_params.get("match") or st.session_state.get("selected_match_file")
        default_idx = 0
        if saved_match:
            for idx, m in enumerate(available_matches):
                if m["filename"] == saved_match or m["filename"].replace(".json", "") == str(saved_match):
                    default_idx = idx
                    break

        filename_options = [m["filename"] for m in available_matches]
        file_to_meta = {m["filename"]: m for m in available_matches}
        
        saved_match = st.query_params.get("match") or st.session_state.get("selected_match_file")
        default_idx = 0
        if saved_match:
            target_stem = str(saved_match).replace(".json", "")
            for idx, fn in enumerate(filename_options):
                if fn == saved_match or fn.replace(".json", "") == target_stem:
                    default_idx = idx
                    break

        sel_filename = st.selectbox(
            f"Select Match ({len(available_matches)} Matches Available)",
            filename_options,
            index=default_idx,
            format_func=lambda fn: file_to_meta[fn]["label"],
            key="match_selector_dropdown"
        )
        selected_match_meta = file_to_meta[sel_filename]
        selected_match_label = selected_match_meta["label"]
        selected_file = selected_match_meta["filename"]

        if st.session_state.get("selected_match_file") != selected_file:
            st.session_state["selected_match_file"] = selected_file
            st.query_params["match"] = selected_file
    else:
        st.warning(f"No match files found in the data directory.")
        st.stop()

    st.markdown("---")
    
    hourly_block_size = st.slider(
        "Hourly Over Block (Overs/Hr)",
        min_value=10,
        max_value=20,
        value=15,
        step=1,
        help="Standard target over rate in First-Class cricket is 15 overs per hour."
    )
    
    st.markdown("---")
    st.caption("Ranji Trophy Elite | Multi-Day Analytics Engine")

# ----------------------------------------------------
# MAIN APPLICATION BODY
# ----------------------------------------------------
if selected_match_meta is None:
    st.info("Please select a match from the sidebar to view analytics.")
    st.stop()

@st.fragment(run_every=30)
def render_match_dashboard(match_path, hourly_block_size, selected_file):
    selected_json_data = None
    for _ in range(3):
        try:
            with open(match_path, "r", encoding="utf-8") as f:
                selected_json_data = json.load(f)
            break
        except Exception:
            time.sleep(0.05)

    if selected_json_data is None:
        st.warning("Match data is synchronizing in the background... Retrying automatically.")
        return

    # ----------------------------------------------------
    # RANJI TROPHY ENGINE - BLUE LOADING ANIMATION
    # ----------------------------------------------------
    if st.session_state.get("engine_loaded_match") != selected_file:
        progress_slot = st.empty()
        with progress_slot.container():
            st.markdown("""
            <div style="background: linear-gradient(135deg, #090d16 0%, #111c30 100%); border: 2px solid #2563eb; border-radius: 12px; padding: 22px; margin: 15px 0 25px 0; text-align: center; box-shadow: 0 10px 30px rgba(37, 99, 235, 0.3);">
                <div style="color: #60a5fa; font-size: 12px; font-weight: 700; letter-spacing: 2.5px; text-transform: uppercase;">Ranji Trophy First-Class Engine</div>
                <div style="color: #ffffff; font-size: 22px; font-weight: 800; margin: 6px 0;">RANJI TROPHY ANALYTICS ENGINE</div>
                <div style="color: #94a3b8; font-size: 14px;">Ingesting Ball-by-Ball Telemetry & Computing Metrics...</div>
            </div>
            """, unsafe_allow_html=True)
            prog_bar = st.progress(0, text="Initializing Engine...")
            stages = [
                (20, "Loading Ball-by-Ball Telemetry & Reconciling Official Scorecards..."),
                (45, "Segmenting Bowler Spells, Fatigue Curves & Tandems..."),
                (70, "Computing Corridor of Pressure & Preceding Dot Chains..."),
                (90, "Scanning Batting Settlement Index & Collapse Clusters..."),
                (100, "Engine Ready! Launching Match Analytics...")
            ]
            for pct, msg in stages:
                prog_bar.progress(pct, text=msg)
                time.sleep(0.12)
            time.sleep(0.1)
        progress_slot.empty()
        st.session_state["engine_loaded_match"] = selected_file

    # ----------------------------------------------------
    # MATCH SCOPE SELECTOR (FULL MATCH VS DAY 1 / 2 / 3 / 4)
    # ----------------------------------------------------
    info_raw = selected_json_data.get("info", {})
    days_played = info_raw.get("days_played") or [1, 2, 3, 4]
    day_options = ["Full Match (All Days)"] + [f"Day {d}" for d in days_played]

    st.markdown("#### Analytics Scope")
    selected_view = st.radio(
        "Select Scope:",
        day_options,
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key=f"scope_radio_{selected_file}"
    )

    filter_day = None
    if selected_view != "Full Match (All Days)":
        filter_day = int(selected_view.split("Day ")[-1])
        st.info(f"Viewing Day {filter_day} play only: Runs, wickets, partnerships, and spells from Day {filter_day}.")

    # Parse match data
    parsed = parse_match_data(selected_json_data, filter_day=filter_day)
    info = parsed["info"]
    innings = parsed["innings"]
    teams = info.get("teams", ["Team 1", "Team 2"])
    venue = info.get("venue", "Unknown Venue")
    dates = info.get("dates", [])
    date_str = ", ".join(dates) if dates else "Date not recorded"
    outcome = info.get("outcome", {})
    result_str = outcome.get("summary", outcome.get("result", "Match in Progress / Stumps"))
    toss = info.get("toss", {})
    toss_str = f"{toss.get('winner', 'Unknown')} won the toss and elected to {toss.get('decision', 'bat')}."

    # ----------------------------------------------------
    # HEADER SECTION & MATCH OVERVIEW
    # ----------------------------------------------------
    st.title(f"{teams[0]} vs {teams[1]}")
    st.markdown(
        '<span style="background: rgba(16, 185, 129, 0.15); color: #10b981; padding: 4px 10px; border-radius: 9999px; font-size: 13px; font-weight: 600; border: 1px solid rgba(16, 185, 129, 0.3);">🟢 Live Auto-Sync: Active (Auto-updating every 30s without page reload)</span>',
        unsafe_allow_html=True
    )
    event_name_cleaned = str(info.get('event', {}).get('name', 'Ranji Trophy Elite')).replace("BCCI", "").replace("  ", " ").strip()
    st.caption(f"{venue} | {date_str} | {event_name_cleaned} (Match {info.get('event', {}).get('match_number', '')})")

    st.info(f"**Match Outcome:** {result_str}  |  **Toss:** {toss_str}")

    # Quick summary cards for all innings
    if innings:
        cols = st.columns(len(innings))
        for i, inn in enumerate(innings):
            with cols[i]:
                if inn.get("did_not_bat") or inn.get("total_legal_balls", 0) == 0:
                    st.metric(
                        label=f"{inn['team']} - Innings {inn['innings_index']}",
                        value="Did Not Bat",
                        delta=f"No overs on Day {filter_day}" if filter_day is not None else "Did not bat"
                    )
                else:
                    st.metric(
                        label=f"{inn['team']} - Innings {inn['innings_index']}",
                        value=f"{inn['total_runs']}/{inn['total_wickets']}",
                        delta=f"{inn['total_overs']} ov | RR: {inn['run_rate']}"
                    )

    st.markdown("---")

    # ----------------------------------------------------
    # MAIN APPLICATION TABS
    # ----------------------------------------------------
    tab_spells, tab_sessions, tab_scorecard, tab_manhattan, tab_partnerships, tab_feats, tab_redball = st.tabs([
        "Bowler Spells",
        "Hourly & Session Summary",
        "Official Scorecards",
        "Manhattan & Over Charts",
        "Partnerships",
        "3+ Wkts & Hat-Tricks",
        "Multi-Day Deep Metrics"
    ])

    # ====================================================
    # TAB 1: BOWLER SPELL-WISE ANALYSIS
    # ====================================================
    with tab_spells:
        st.subheader("Bowler Spell-wise Analysis")
        st.write("Spell breakdown showing how many continuous overs a bowler delivered in one go. A new spell starts when the bowler rests for more than a standard alternate-over gap.")

        if not innings:
            st.info("No innings data available.")
        else:
            inn_options = [f"{inn['team']} (Innings {inn['innings_index']})" for inn in innings]
            sel_spell_inn_idx = st.selectbox("Select Innings to Analyse Spells", range(len(innings)), format_func=lambda i: inn_options[i], key="spell_inn_select")
            active_inn = innings[sel_spell_inn_idx]
        
            df_spells = compute_bowler_spells(active_inn)
        
            if df_spells.empty:
                st.info("No bowling spell data found for this innings.")
            else:
                col_b1, col_b2 = st.columns([2, 1])
                with col_b1:
                    all_bowlers = ["All Bowlers"] + sorted(df_spells["Bowler"].unique().tolist())
                    sel_bowler = st.selectbox("Filter by Bowler", all_bowlers, key="sel_spell_bowler")
                with col_b2:
                    sort_spell = st.selectbox("Sort Spells By", ["Start Over", "Overs", "Wickets", "Economy", "Dots"], index=0, key="sort_spell")

                filtered_spells = df_spells if sel_bowler == "All Bowlers" else df_spells[df_spells["Bowler"] == sel_bowler]
            
                # KPI summary row for the spells
                tot_spells_count = len(filtered_spells)
                tot_sp_ov = filtered_spells["Overs"].sum()
                tot_sp_wkts = filtered_spells["Wickets"].sum()
                avg_sp_econ = round(filtered_spells["Runs"].sum() / tot_sp_ov, 2) if tot_sp_ov > 0 else 0.0
            
                kc1, kc2, kc3, kc4 = st.columns(4)
                with kc1: st.metric("Total Spells", tot_spells_count)
                with kc2: st.metric("Overs Bowled", f"{tot_sp_ov:.1f}")
                with kc3: st.metric("Wickets", tot_sp_wkts)
                with kc4: st.metric("Economy", avg_sp_econ)
            
                # Spell display table
                display_spell_cols = ["Bowler", "Spell", "Over Range", "Actual Overs", "Overs", "Maidens", "Runs", "Wickets", "Economy", "Dots", "Dot %", "4s", "6s", "Wickets Taken"]
                sorted_spells = filtered_spells.sort_values(sort_spell, ascending=(sort_spell in ["Start Over", "Economy"]))
                st.dataframe(
                    sorted_spells[[c for c in display_spell_cols if c in sorted_spells.columns]].reset_index(drop=True),
                    use_container_width=True
                )

                # Spell comparison visual
                if sel_bowler != "All Bowlers" and len(filtered_spells) > 1:
                    st.markdown(f"#### {sel_bowler} - Spell Fatigue & Impact Curve")
                
                    fig_spell = make_subplots(specs=[[{"secondary_y": True}]])
                    fig_spell.add_trace(
                        go.Bar(x=filtered_spells["Spell"], y=filtered_spells["Overs"], name="Overs Bowled", marker_color="#38bdf8", opacity=0.7),
                        secondary_y=False
                    )
                    fig_spell.add_trace(
                        go.Scatter(x=filtered_spells["Spell"], y=filtered_spells["Economy"], name="Economy Rate", mode="lines+markers", line=dict(color="#f43f5e", width=3)),
                        secondary_y=True
                    )
                    wkt_spells = filtered_spells[filtered_spells["Wickets"] > 0]
                    fig_spell.add_trace(
                        go.Scatter(x=wkt_spells["Spell"], y=wkt_spells["Wickets"], name="Wickets", mode="markers", marker=dict(size=14, color="#f59e0b", symbol="star")),
                        secondary_y=False
                    )
                    fig_spell.update_layout(
                        title=f"{sel_bowler}: Overs, Economy & Wickets across Spells",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    fig_spell.update_yaxes(title_text="Overs / Wickets", secondary_y=False)
                    fig_spell.update_yaxes(title_text="Economy Rate", secondary_y=True)
                    st.plotly_chart(fig_spell, use_container_width=True)

            # ----------------------------------------------------
            # METRIC 1: HUNTING IN PACKS (BOWLING TANDEMS)
            # ----------------------------------------------------
            st.markdown("---")
            st.markdown("### Hunting in Packs: Bowling Tandem Analysis")
            st.caption("Pairs of bowlers operating in tandem from opposite ends in consecutive alternating overs. Red-ball pressure is built as a unit.")
            df_tandems = compute_bowler_tandems(active_inn)
            if df_tandems.empty:
                st.info("No bowling tandems (minimum 3 continuous alternating overs) detected in this innings.")
            else:
                t_k1, t_k2, t_k3, t_k4 = st.columns(4)
                with t_k1: st.metric("Tandem Spells", len(df_tandems))
                with t_k2: st.metric("Tandem Overs", df_tandems["Tandem Overs"].sum())
                with t_k3: st.metric("Wickets in Tandem", df_tandems["Wickets"].sum())
                top_pair = df_tandems.loc[df_tandems["Tandem Overs"].idxmax()]["Tandem Pair"]
                with t_k4: st.metric("Longest Tandem", top_pair)

                st.dataframe(df_tandems, use_container_width=True)

                fig_tandem = px.bar(
                    df_tandems,
                    x="Tandem Pair",
                    y="Tandem Overs",
                    color="Wickets",
                    color_continuous_scale="Tealgrn",
                    text="Economy",
                    title="Bowling Tandem Overs, Wickets & Economy",
                    hover_data=["Overs Span", "Runs", "Dot %", "Strike Bowler", "Pressure Anchor"]
                )
                fig_tandem.update_traces(texttemplate='%{text} RPO', textposition='outside')
                st.plotly_chart(fig_tandem, use_container_width=True)

    # ====================================================
    # TAB 2: HOURLY & SESSION SUMMARY
    # ====================================================
    with tab_sessions:
        st.subheader("Hourly & Session Summary")
        st.write("Track the rate of overs bowled per hour and the session-by-session dominance between bat and ball.")

        if not innings:
            st.info("No innings data available.")
        else:
            inn_options = [f"{inn['team']} (Innings {inn['innings_index']})" for inn in innings]
            sel_sess_inn_idx = st.selectbox("Select Innings for Session Analysis", range(len(innings)), format_func=lambda i: inn_options[i], key="sess_inn_select")
            active_sess_inn = innings[sel_sess_inn_idx]

            mode_choice = st.radio("View Mode", ["Hourly Blocks (Over Rate Target: 15 ov/hr)", "Full Sessions (30 overs/session)"], horizontal=True)
            is_hour = "Hourly" in mode_choice
            block_size = hourly_block_size if is_hour else 30
            block_label = "Hour" if is_hour else "Session"

            df_blocks = compute_time_blocks(active_sess_inn, block_overs=block_size, block_type=block_label)

            if df_blocks.empty:
                st.info("No over data available to compute intervals.")
            else:
                # Summary Metrics
                tot_blocks = len(df_blocks)
                tot_runs_blocks = df_blocks["Runs"].sum()
                tot_wkts_blocks = df_blocks["Wickets Lost"].sum()
                avg_rr = round(tot_runs_blocks / df_blocks["Overs Bowled"].sum(), 2) if df_blocks["Overs Bowled"].sum() > 0 else 0.0

                m1, m2, m3, m4 = st.columns(4)
                with m1: st.metric("Intervals Completed", f"{tot_blocks} {block_label.lower()}s")
                with m2: st.metric("Runs Scored", tot_runs_blocks)
                with m3: st.metric("Wickets Lost", tot_wkts_blocks)
                with m4: st.metric("Innings Run Rate", avg_rr)

                # Table of Intervals
                disp_block_cols = ["Interval", "Overs Span", "Overs Bowled", "Runs", "Run Rate", "Wickets Lost", "Wickets Details", "Dot %", "Boundaries", "Top Batter", "Top Bowler", "Phase Dominance"]
                st.dataframe(df_blocks[disp_block_cols], use_container_width=True)

                # Chart: Runs and Wickets per Interval
                fig_block = make_subplots(specs=[[{"secondary_y": True}]])
                fig_block.add_trace(
                    go.Bar(x=df_blocks["Interval"], y=df_blocks["Runs"], name="Runs Scored", marker_color="#e11d48", text=df_blocks["Runs"], textposition="auto"),
                    secondary_y=False
                )
                fig_block.add_trace(
                    go.Scatter(x=df_blocks["Interval"], y=df_blocks["Wickets Lost"], name="Wickets Lost", mode="lines+markers", line=dict(color="#f59e0b", width=3), marker=dict(size=10)),
                    secondary_y=True
                )
                fig_block.update_layout(
                    title=f"{active_sess_inn['team']}: Runs & Wickets per {block_label}",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                fig_block.update_yaxes(title_text="Runs", secondary_y=False)
                fig_block.update_yaxes(title_text="Wickets", secondary_y=True)
                st.plotly_chart(fig_block, use_container_width=True)

    # ====================================================
    # TAB 3: OFFICIAL SCORECARDS & MATCH SUMMARY
    # ====================================================
    with tab_scorecard:
        st.subheader("Match Summary & Official Scorecards")

        if not innings:
            st.info("No innings data available.")
        else:
            # Match Summary
            st.markdown(f"""
    **Event:** {info.get('event', {}).get('name', 'Ranji Trophy Elite')} (Match {info.get('event', {}).get('match_number', '')})  
    **Venue:** {venue} | **Date(s):** {date_str}  
    **Toss:** {toss_str}  
    **Umpires:** {', '.join(info.get('officials', {}).get('umpires', ['Not specified']))} | **Referee:** {', '.join(info.get('officials', {}).get('match_referees', ['Not specified']))}  
    **Result:** {result_str}
            """)

            st.markdown("---")

            # Tab for each innings
            subtabs = st.tabs([f"{inn['team']} - Innings {inn['innings_index']}" for inn in innings])
            for s_idx, inn in enumerate(innings):
                with subtabs[s_idx]:
                    if inn.get("did_not_bat", False) or inn.get("total_legal_balls", 0) == 0:
                        day_label = f" on Day {filter_day}" if filter_day is not None else ""
                        st.info(f"{inn['team']} did not bat{day_label}.")
                        continue

                    st.markdown(f"### {inn['team']} Batting - {inn['total_runs']}/{inn['total_wickets']} ({inn['total_overs']} Overs, RR: {inn['run_rate']})")
                
                    # Batting Scorecard
                    df_bat = format_batting_scorecard(inn["batters"])
                    st.dataframe(df_bat, use_container_width=True)
                
                    # Extras & Total
                    ex = inn["extras"]
                    st.markdown(
                        f"**Extras:** {ex['total']} (b {ex['byes']}, lb {ex['legbyes']}, w {ex['wides']}, nb {ex['noballs']}, pen {ex['penalty']})  |  "
                        f"**Total:** {inn['total_runs']}/{inn['total_wickets']} in {inn['total_overs']} overs"
                    )

                    # Fall of Wickets
                    if inn["fow"]:
                        st.markdown("**Fall of Wickets:**")
                        fow_str = "  |  ".join([f"**{fw['wicket']}-{fw['score']}** ({fw['player']}, {fw['over']} ov)" for fw in inn["fow"]])
                        st.markdown(fow_str)

                    st.markdown("---")
                    st.markdown(f"### Bowling vs {inn['team']}")
                    df_bow = format_bowling_scorecard(inn["bowlers"])
                    st.dataframe(df_bow, use_container_width=True)

                    # ----------------------------------------------------
                    # METRIC 2: CORRIDOR OF PRESSURE (DOT CHAINS BEFORE WICKETS)
                    # ----------------------------------------------------
                    df_pressure = compute_pressure_chains(inn)
                    if not df_pressure.empty:
                        st.markdown("---")
                        st.markdown("### Corridor of Pressure: Dot Ball Chains Preceding Dismissals")
                        st.caption("Analyzes the dot-ball choke in the 18 deliveries immediately prior to each wicket. Red-ball dismissals are forced by sustained pressure.")
                        st.dataframe(df_pressure, use_container_width=True)

    # ====================================================
    # TAB 4: MANHATTAN & OVER-BY-OVER PROGRESSION
    # ====================================================
    with tab_manhattan:
        st.subheader("Manhattan & Over-by-Over Charts")
        st.write("Runs scored and wickets lost in each over of the innings.")

        if not innings:
            st.info("No innings data available.")
        else:
            inn_options = [f"{inn['team']} (Innings {inn['innings_index']})" for inn in innings]
            sel_man_idx = st.selectbox("Select Innings for Manhattan", range(len(innings)), format_func=lambda i: inn_options[i], key="man_inn_select")
            active_man_inn = innings[sel_man_idx]
        
            ov_stats = active_man_inn.get("overs_stats", [])
            if not ov_stats:
                st.info("No over data available.")
            else:
                df_man = pd.DataFrame(ov_stats)
                df_man["Cumulative_Runs"] = df_man["runs"].cumsum()

                # Simple, clean Manhattan Bar Chart
                fig_man = go.Figure()
            
                # Color bars: normal overs in steel blue, wicket overs in red
                bar_colors = ["#ef4444" if w > 0 else "#3b82f6" for w in df_man["wickets"]]
            
                fig_man.add_trace(go.Bar(
                    x=df_man["over_display"],
                    y=df_man["runs"],
                    name="Runs",
                    marker_color=bar_colors,
                    hovertemplate="Over %{x}<br>Runs: %{y}<extra></extra>"
                ))

                # Wicket markers on top of bars
                wkt_overs = df_man[df_man["wickets"] > 0]
                if not wkt_overs.empty:
                    wkt_labels = []
                    for _, r in wkt_overs.iterrows():
                        names = [w['player'] for w in r["wickets_list"]]
                        wkt_labels.append("<br>".join(names))

                    fig_man.add_trace(go.Scatter(
                        x=wkt_overs["over_display"],
                        y=wkt_overs["runs"] + 0.5,
                        mode="markers+text",
                        marker=dict(symbol="triangle-down", size=12, color="#ef4444"),
                        text=["W" if w == 1 else f"{w}W" for w in wkt_overs["wickets"]],
                        textposition="top center",
                        textfont=dict(size=10, color="#ef4444"),
                        name="Wickets",
                        hovertext=wkt_labels,
                        hoverinfo="text"
                    ))

                fig_man.update_layout(
                    title=f"{active_man_inn['team']} (Innings {active_man_inn['innings_index']}) - Manhattan",
                    xaxis_title="Over",
                    yaxis_title="Runs",
                    showlegend=False,
                    height=400,
                    xaxis=dict(dtick=5),
                    bargap=0.15
                )
                st.plotly_chart(fig_man, use_container_width=True)

                # Cumulative Run Progression (Worm Chart)
                st.markdown("#### Cumulative Run Progression")
                fig_worm = go.Figure()
                fig_worm.add_trace(go.Scatter(
                    x=df_man["over_display"],
                    y=df_man["Cumulative_Runs"],
                    mode="lines",
                    line=dict(color="#3b82f6", width=2.5),
                    fill="tozeroy",
                    fillcolor="rgba(59, 130, 246, 0.1)",
                    hovertemplate="Over %{x}<br>Score: %{y}<extra></extra>"
                ))
            
                # Mark wickets on the worm
                if not wkt_overs.empty:
                    wkt_cum = df_man[df_man["wickets"] > 0]
                    fig_worm.add_trace(go.Scatter(
                        x=wkt_cum["over_display"],
                        y=wkt_cum["Cumulative_Runs"],
                        mode="markers",
                        marker=dict(size=8, color="#ef4444", symbol="x"),
                        name="Wicket",
                        hovertemplate="Over %{x}<br>Score: %{y} (Wicket)<extra></extra>"
                    ))

                fig_worm.update_layout(
                    title=f"{active_man_inn['team']} - Score Progression",
                    xaxis_title="Overs",
                    yaxis_title="Total Score",
                    showlegend=False,
                    height=350,
                    xaxis=dict(dtick=10)
                )
                st.plotly_chart(fig_worm, use_container_width=True)

                # ----------------------------------------------------
                # METRIC 4: BATTING COLLAPSE DETECTOR (CLUSTERS OF WICKETS)
                # ----------------------------------------------------
                st.markdown("---")
                st.markdown("#### Batting Collapse Detector: Clustered Wickets")
                st.caption("Identifies rapid batting collapses where a team lost 3 or more wickets within 25 runs or 8 overs.")
                df_collapses = detect_batting_collapses(active_man_inn)
                if df_collapses.empty:
                    st.info("No clustered collapses (3+ wickets within 25 runs / 8 overs) in this innings.")
                else:
                    for _, c_row in df_collapses.iterrows():
                        st.warning(f"**{c_row['Severity']}: {c_row['Collapse Span']}** — Lost {c_row['Wickets Lost']} wickets for {c_row['Runs Scored']} runs in {c_row['Overs Elapsed']} ({c_row['Score Transition']}) | Batters: {c_row['Dismissed Batters']}")
                    st.dataframe(df_collapses, use_container_width=True)

    # ====================================================
    # TAB 5: PARTNERSHIP SECTION
    # ====================================================
    with tab_partnerships:
        st.subheader("Partnership Section")
        st.write("All wicket partnerships and individual contributions for each innings.")

        if not innings:
            st.info("No innings data available.")
        else:
            inn_options = [f"{inn['team']} (Innings {inn['innings_index']})" for inn in innings]
            sel_part_idx = st.selectbox("Select Innings for Partnerships", range(len(innings)), format_func=lambda i: inn_options[i], key="part_inn_select")
            active_part_inn = innings[sel_part_idx]
        
            parts = active_part_inn.get("partnerships", [])
            if not parts:
                st.info("No partnership data recorded.")
            else:
                df_parts = pd.DataFrame(parts)
                df_parts["Partnership"] = df_parts["batter1"].fillna("Unknown") + " & " + df_parts["batter2"].fillna("Unknown")
                df_parts["Run Rate"] = (df_parts["runs"] / (df_parts["balls"] / 6.0)).round(2).replace(np.inf, 0.0).fillna(0.0)
            
                # Highest partnership KPI
                max_part = df_parts.loc[df_parts["runs"].idxmax()]
            
                c1, c2, c3 = st.columns(3)
                with c1: st.metric("Highest Partnership", f"{max_part['runs']} Runs ({max_part['balls']}b)", f"{max_part['wicket_label']}")
                with c2: st.metric("Stand Partners", f"{max_part['batter1']} & {max_part['batter2']}")
                with c3: st.metric("Total Wickets Fallen", len(df_parts) - (1 if df_parts.iloc[-1]["unbroken"] else 0))

                # Table of Partnerships
                table_part_cols = ["wicket_label", "Partnership", "runs", "balls", "Run Rate", "over_range", "b1_runs", "b2_runs"]
                rename_dict = {
                    "wicket_label": "Wicket",
                    "runs": "Runs",
                    "balls": "Balls",
                    "over_range": "Overs Span",
                    "b1_runs": "Batter 1 Runs",
                    "b2_runs": "Batter 2 Runs"
                }
                st.dataframe(df_parts[table_part_cols].rename(columns=rename_dict), use_container_width=True)

                # Horizontal Bar Chart
                st.markdown("#### Partnerships by Wicket")
                fig_part = go.Figure()
            
                # Stacked bar: batter 1 runs + batter 2 runs + extras
                extras_in_part = df_parts["runs"] - df_parts["b1_runs"] - df_parts["b2_runs"]
            
                fig_part.add_trace(go.Bar(
                    y=df_parts["wicket_label"],
                    x=df_parts["b1_runs"],
                    name="Batter 1",
                    orientation="h",
                    marker_color="#3b82f6",
                    text=[f"{n} ({r})" for n, r in zip(df_parts["batter1"], df_parts["b1_runs"])],
                    textposition="inside",
                    insidetextanchor="middle"
                ))
                fig_part.add_trace(go.Bar(
                    y=df_parts["wicket_label"],
                    x=df_parts["b2_runs"],
                    name="Batter 2",
                    orientation="h",
                    marker_color="#f59e0b",
                    text=[f"{n} ({r})" for n, r in zip(df_parts["batter2"], df_parts["b2_runs"])],
                    textposition="inside",
                    insidetextanchor="middle"
                ))
                if extras_in_part.sum() > 0:
                    fig_part.add_trace(go.Bar(
                        y=df_parts["wicket_label"],
                        x=extras_in_part,
                        name="Extras",
                        orientation="h",
                        marker_color="#94a3b8",
                        text=extras_in_part,
                        textposition="inside"
                    ))
            
                fig_part.update_layout(
                    barmode="stack",
                    title=f"{active_part_inn['team']} - Partnership Breakdown",
                    xaxis_title="Runs",
                    yaxis=dict(autorange="reversed"),
                    height=max(350, len(df_parts) * 45),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_part, use_container_width=True)

    # ====================================================
    # TAB 6: 3+ WICKETS IN AN OVER & HAT-TRICKS
    # ====================================================
    with tab_feats:
        st.subheader("Special Feats: 3+ Wickets in an Over & Hat-Tricks")
        st.write("Identifies lethal bowling overs where a bowler grabbed 3 or more wickets in a single over and hat-trick deliveries.")

        scan_scope = st.radio("Scan Scope", ["Current Match", "All Ranji Trophy Matches in Folder"], horizontal=True)
    
        if scan_scope == "Current Match":
            matches_to_scan = [{"data": selected_json_data, "label": selected_match_label}]
        else:
            matches_to_scan = []
            if available_matches:
                for am in available_matches:
                    try:
                        with open(am["path"], "r", encoding="utf-8") as f:
                            d_match = json.load(f)
                        matches_to_scan.append({"data": d_match, "label": am["label"]})
                    except Exception:
                        continue
            else:
                matches_to_scan = [{"data": selected_json_data, "label": selected_match_label}]

        with st.spinner("Scanning for 3+ wicket overs and hat-tricks..."):
            df_three_wkts, df_hat_tricks = scan_special_feats(matches_to_scan)

        col_h1, col_h2 = st.columns(2)
        with col_h1:
            st.markdown("### Hat-Tricks (3 in 3 Consecutive Balls)")
            if df_hat_tricks.empty:
                st.info("No hat-tricks found in the scanned match data.")
            else:
                st.dataframe(df_hat_tricks, use_container_width=True)

        with col_h2:
            st.markdown("### 3 or More Wickets in an Over")
            if df_three_wkts.empty:
                st.info("No 3+ wicket overs found in the scanned match data.")
            else:
                st.dataframe(df_three_wkts, use_container_width=True)

    # ====================================================
    # TAB 7: SUGGESTED MULTI-DAY DEEP METRICS
    # ====================================================
    with tab_redball:
        st.subheader("Multi-Day Red-Ball Metrics Suite")
        st.write("Metrics engineered for 4-day and 5-day First-Class / Ranji Trophy cricket.")

        if not innings:
            st.info("No innings data available.")
        else:
            inn_options = [f"{inn['team']} (Innings {inn['innings_index']})" for inn in innings]
            sel_md_idx = st.selectbox("Select Innings for Multi-Day Deep Dive", range(len(innings)), format_func=lambda i: inn_options[i], key="md_inn_select")
            active_md_inn = innings[sel_md_idx]
        
            phases, df_phases, df_order = compute_multiday_metrics(active_md_inn)

            # 1. Ball Age & Phase Analysis
            st.markdown("### 1. Ball-Age Dynamics (New Ball vs Settled Ball vs Second New Ball)")
            st.caption("How scoring rates and wicket vulnerability evolve across the lifespan of the red SG ball.")
            if not df_phases.empty:
                st.dataframe(df_phases, use_container_width=True)
            
                fig_phase = px.bar(
                    df_phases,
                    x="Ball Age Phase",
                    y="Run Rate",
                    color="Wickets",
                    color_continuous_scale="Sunsetdark",
                    text="Run Rate",
                    title="Run Rate & Wickets Fallen by Ball-Age Phase"
                )
                fig_phase.update_traces(textposition="outside")
                st.plotly_chart(fig_phase, use_container_width=True)

            st.markdown("---")

            # 2. Batting Order Balance (Top vs Middle vs Tail)
            st.markdown("### 2. Batting Order Balance: Top Order vs Middle Order vs Tail")
            st.caption("In the Ranji Trophy, lower-order runs frequently determine the crucial First-Innings Lead (3 tournament points).")
            if not df_order.empty:
                c_ord1, c_ord2 = st.columns([1.5, 1])
                with c_ord1:
                    st.dataframe(df_order, use_container_width=True)
                with c_ord2:
                    fig_ord = px.pie(
                        df_order,
                        names="Section",
                        values="Runs",
                        title="Run Share by Batting Section",
                        color_discrete_sequence=["#3b82f6", "#818cf8", "#ef4444"],
                        hole=0.4
                    )
                    fig_ord.update_traces(
                        textposition="inside",
                        text=df_order["% of Total Runs"].apply(lambda x: f"{x}%"),
                        textinfo="text",
                        hovertemplate="<b>%{label}</b><br>Runs: %{value}<br>Share: %{text}<extra></extra>"
                    )
                    st.plotly_chart(fig_ord, use_container_width=True)

            st.markdown("---")

            # 3. Defensive Attrition & Balls Faced Metric
            st.markdown("### 3. Defensive Attrition & Resistance Index")
            st.caption("Red-ball value is defined by balls absorbed at the crease and resistance against bowling pressure.")
            df_bat_full = format_batting_scorecard(active_md_inn["batters"])
            if not df_bat_full.empty:
                df_resilience = df_bat_full[df_bat_full["Balls"] >= 20].copy()
                if not df_resilience.empty:
                    df_resilience["Balls per 4"] = (df_resilience["Balls"] / df_resilience["4s"].replace(0, np.nan)).round(1).fillna(df_resilience["Balls"])
                    df_resilience["Attrition Score"] = ((df_resilience["Balls"] * 0.6) + (df_resilience["Runs"] * 0.4)).round(1)
                
                    res_disp_cols = ["Batter", "Runs", "Balls", "Dot %", "Strike Rate", "Balls per 4", "Attrition Score"]
                    st.dataframe(df_resilience[res_disp_cols].sort_values("Balls", ascending=False).reset_index(drop=True), use_container_width=True)

            st.markdown("---")

            # ----------------------------------------------------
            # METRIC 3: BATTING SETTLEMENT INDEX (FIRST 30 BALLS VS SET BATTER)
            # ----------------------------------------------------
            st.markdown("### 4. Batting Settlement Index: Danger Zone (Balls 1-30) vs Set Phase (Balls 31+)")
            st.caption("Analyzes batter vulnerability during the initial crease settlement window versus acceleration once settled.")
            df_settle = compute_settlement_index(active_md_inn)
            if df_settle.empty:
                st.info("No qualified batters with >= 10 balls faced.")
            else:
                st.dataframe(df_settle, use_container_width=True)

                df_set_chart = df_settle[df_settle["Set SR"] != "-"].copy()
                if not df_set_chart.empty:
                    fig_settle = go.Figure()
                    fig_settle.add_trace(go.Bar(
                        x=df_set_chart["Batter"],
                        y=df_set_chart["Settlement SR"],
                        name="Settlement Phase SR (Balls 1-30)",
                        marker_color="#f59e0b"
                    ))
                    fig_settle.add_trace(go.Bar(
                        x=df_set_chart["Batter"],
                        y=pd.to_numeric(df_set_chart["Set SR"]),
                        name="Set Phase SR (Balls 31+)",
                        marker_color="#3b82f6"
                    ))
                    fig_settle.update_layout(
                        barmode="group",
                        title="Strike Rate Shift: Early Settlement Window vs Set Batter Phase",
                        yaxis_title="Strike Rate",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_settle, use_container_width=True)

    st.markdown("---")
    st.caption("Ranji Trophy Multi-Day Analytics Engine | By Vishwesh Gaur")


render_match_dashboard(selected_match_meta["path"], hourly_block_size, selected_file)
