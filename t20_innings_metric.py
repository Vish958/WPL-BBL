import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(
    page_title="T20 Innings Metric",
    page_icon="🏏",
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .phase-header { font-size: 0.8rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; margin-bottom: 0.25rem; }
    .metric-flag-low  { color: #c0392b; font-weight: 600; }
    .metric-flag-ok   { color: #27ae60; font-weight: 600; }
    .metric-flag-na   { color: #888; }
    .pill-pp    { background:#d5f5e3; color:#1e8449; padding:2px 10px; border-radius:99px; font-size:12px; font-weight:600; }
    .pill-mid   { background:#fef9e7; color:#9a7d0a; padding:2px 10px; border-radius:99px; font-size:12px; font-weight:600; }
    .pill-death { background:#fdedec; color:#922b21; padding:2px 10px; border-radius:99px; font-size:12px; font-weight:600; }
    .stDataFrame thead tr th { font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ───────────────────────────────────────────────────────────────
PHASES = {
    "Powerplay":    (1, 6),
    "Middle overs": (7, 15),
    "Death overs":  (16, 20),
}
PHASE_COLORS = {
    "Powerplay": "#1D9E75",
    "Middle overs": "#BA7517",
    "Death overs": "#A32D2D",
}

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏏 T20 Innings Metric")
    st.divider()

    innings_choice = st.selectbox("Select innings", ["1st innings", "2nd innings"])
    match_name = st.text_input("Match name", "India vs England")

    st.divider()
    st.markdown("**Settings**")
    sr_threshold = st.slider("SR threshold", min_value=80, max_value=200, value=120, step=5)
    min_balls = st.number_input("Min balls faced", min_value=1, max_value=30, value=10, step=1)
    top_n = st.slider("Top N batters", min_value=3, max_value=11, value=7, step=1)

    st.divider()
    if st.button("Load sample data", use_container_width=True):
        st.session_state["sample_loaded"] = True

# ── Sample data ──────────────────────────────────────────────────────────────
SAMPLE = [
    {"name": "Rohit Sharma",       "pos": 1, "pp_r": 28, "pp_b": 18, "mid_r": 24, "mid_b": 20, "death_r": 0,  "death_b": 0,  "4s": 8,  "6s": 4},
    {"name": "Shubman Gill",       "pos": 2, "pp_r": 14, "pp_b": 18, "mid_r": 0,  "mid_b": 0,  "death_r": 0,  "death_b": 0,  "4s": 1,  "6s": 0},
    {"name": "Virat Kohli",        "pos": 3, "pp_r": 10, "pp_b": 8,  "mid_r": 54, "mid_b": 36, "death_r": 18, "death_b": 12, "4s": 7,  "6s": 2},
    {"name": "KL Rahul",           "pos": 4, "pp_r": 0,  "pp_b": 0,  "mid_r": 8,  "mid_b": 11, "death_r": 0,  "death_b": 0,  "4s": 1,  "6s": 0},
    {"name": "Hardik Pandya",      "pos": 5, "pp_r": 0,  "pp_b": 0,  "mid_r": 22, "mid_b": 16, "death_r": 13, "death_b": 8,  "4s": 3,  "6s": 2},
    {"name": "Suryakumar Yadav",   "pos": 6, "pp_r": 0,  "pp_b": 0,  "mid_r": 0,  "mid_b": 0,  "death_r": 44, "death_b": 21, "4s": 4,  "6s": 4},
    {"name": "Ravindra Jadeja",    "pos": 7, "pp_r": 0,  "pp_b": 0,  "mid_r": 0,  "mid_b": 0,  "death_r": 6,  "death_b": 5,  "4s": 0,  "6s": 1},
]

def blank_row(pos):
    return {"name": f"Batter {pos}", "pos": pos,
            "pp_r": 0, "pp_b": 0, "mid_r": 0, "mid_b": 0,
            "death_r": 0, "death_b": 0, "4s": 0, "6s": 0}

# ── Session state init ───────────────────────────────────────────────────────
if "batters" not in st.session_state:
    st.session_state["batters"] = [blank_row(i+1) for i in range(7)]

if st.session_state.get("sample_loaded"):
    st.session_state["batters"] = [dict(r) for r in SAMPLE]
    st.session_state["sample_loaded"] = False

# ── Metric helpers ───────────────────────────────────────────────────────────
def calc_sr(runs, balls):
    return round(runs / balls * 100, 1) if balls > 0 else None

def sr_flag(sr, balls, threshold, min_b):
    if balls < min_b or sr is None:
        return "na"
    return "low" if sr < threshold else "ok"

def flag_label(flag):
    if flag == "low": return "⚠️ Low SR"
    if flag == "ok":  return "✓ OK"
    return "—"

def flag_color(flag):
    if flag == "low": return "metric-flag-low"
    if flag == "ok":  return "metric-flag-ok"
    return "metric-flag-na"

# ── Build computed dataframe ─────────────────────────────────────────────────
def build_df(batters, threshold, min_b, top_n):
    rows = []
    for b in batters[:top_n]:
        total_r = b["pp_r"] + b["mid_r"] + b["death_r"]
        total_b = b["pp_b"] + b["mid_b"] + b["death_b"]
        total_sr = calc_sr(total_r, total_b)
        flag = sr_flag(total_sr, total_b, threshold, min_b)

        phase_data = {}
        for phase, (_, _) in PHASES.items():
            key_r = {"Powerplay": "pp_r", "Middle overs": "mid_r", "Death overs": "death_r"}[phase]
            key_b = {"Powerplay": "pp_b", "Middle overs": "mid_b", "Death overs": "death_b"}[phase]
            pr, pb = b[key_r], b[key_b]
            psr = calc_sr(pr, pb)
            pflag = sr_flag(psr, pb, threshold, min_b)
            phase_data[phase] = {"runs": pr, "balls": pb, "sr": psr, "flag": pflag}

        rows.append({
            "pos": b["pos"],
            "name": b["name"],
            "total_r": total_r, "total_b": total_b,
            "fours": b["4s"], "sixes": b["6s"],
            "total_sr": total_sr, "flag": flag,
            "phases": phase_data,
        })
    return rows

# ── Input section ────────────────────────────────────────────────────────────
st.markdown(f"### {match_name} — {innings_choice}")
st.caption(f"Top {top_n} batters · SR threshold: {sr_threshold} · Min balls: {min_balls}")

with st.expander("📝 Enter batting scorecard", expanded=True):
    st.markdown("Enter runs and balls **per phase** for each batter.")
    cols_header = st.columns([0.4, 1.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6])
    labels = ["#", "Name", "PP R", "PP B", "Mid R", "Mid B", "Death R", "Death B", "4s", "6s"]
    for c, l in zip(cols_header, labels):
        c.markdown(f"**{l}**")

    for i, b in enumerate(st.session_state["batters"][:top_n]):
        cols = st.columns([0.4, 1.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6])
        cols[0].markdown(f"**{b['pos']}**")
        b["name"]    = cols[1].text_input("", b["name"],    key=f"n{i}",  label_visibility="collapsed")
        b["pp_r"]    = cols[2].number_input("", b["pp_r"],  key=f"ppr{i}", label_visibility="collapsed", min_value=0, step=1)
        b["pp_b"]    = cols[3].number_input("", b["pp_b"],  key=f"ppb{i}", label_visibility="collapsed", min_value=0, step=1)
        b["mid_r"]   = cols[4].number_input("", b["mid_r"], key=f"mr{i}",  label_visibility="collapsed", min_value=0, step=1)
        b["mid_b"]   = cols[5].number_input("", b["mid_b"], key=f"mb{i}",  label_visibility="collapsed", min_value=0, step=1)
        b["death_r"] = cols[6].number_input("", b["death_r"], key=f"dr{i}", label_visibility="collapsed", min_value=0, step=1)
        b["death_b"] = cols[7].number_input("", b["death_b"], key=f"db{i}", label_visibility="collapsed", min_value=0, step=1)
        b["4s"]      = cols[8].number_input("", b["4s"],    key=f"4s{i}",  label_visibility="collapsed", min_value=0, step=1)
        b["6s"]      = cols[9].number_input("", b["6s"],    key=f"6s{i}",  label_visibility="collapsed", min_value=0, step=1)

# ── Compute ──────────────────────────────────────────────────────────────────
data = build_df(st.session_state["batters"], sr_threshold, min_balls, top_n)
total_runs  = sum(d["total_r"] for d in data)
total_balls = sum(d["total_b"] for d in data)
team_sr     = calc_sr(total_runs, total_balls)
total_4s    = sum(d["fours"] for d in data)
total_6s    = sum(d["sixes"] for d in data)
flagged     = [d for d in data if d["flag"] == "low"]
qualified   = [d for d in data if d["total_b"] >= min_balls]

st.divider()

# ── Summary metrics ──────────────────────────────────────────────────────────
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total runs", total_runs)
m2.metric("Balls faced", total_balls)
team_sr_display = f"{team_sr}" if team_sr else "—"
m3.metric("Team SR", team_sr_display, delta=None)
m4.metric("Boundaries (4s)", total_4s)
m5.metric("Sixes", total_6s)
flag_str = f"{len(flagged)} / {len(qualified)}"
m6.metric(f"SR < {sr_threshold}", flag_str)

# ── Alert ────────────────────────────────────────────────────────────────────
if flagged:
    names = ", ".join(d["name"] for d in flagged)
    st.warning(f"⚠️ **{len(flagged)} batter(s)** had SR below {sr_threshold} (≥{min_balls} balls): **{names}**", icon=None)
elif qualified:
    st.success(f"✅ All qualified batters maintained SR ≥ {sr_threshold}.")

st.divider()

# ── Tabs: Overall | Phase Breakdown | Charts ─────────────────────────────────
tab_overall, tab_phase, tab_charts = st.tabs(["📋 Overall", "🔄 Phase breakdown", "📊 Charts"])

# ── TAB 1: Overall ───────────────────────────────────────────────────────────
with tab_overall:
    rows = []
    for d in data:
        sr_disp = f"{d['total_sr']}" if d["total_sr"] is not None else "—"
        rows.append({
            "Pos":    d["pos"],
            "Batter": d["name"],
            "Runs":   d["total_r"],
            "Balls":  d["total_b"],
            "4s":     d["fours"],
            "6s":     d["sixes"],
            "SR":     d["total_sr"] if d["total_sr"] else 0,
            "Flag":   flag_label(d["flag"]),
        })
    df = pd.DataFrame(rows)

    def style_flag(val):
        if "Low" in str(val): return "color: #c0392b; font-weight: 600"
        if "✓" in str(val):   return "color: #27ae60; font-weight: 600"
        return "color: #888"

    def style_sr(val):
        if isinstance(val, (int, float)) and val > 0:
            if val < sr_threshold: return "color: #c0392b; font-weight: 600"
            return "color: #27ae60; font-weight: 600"
        return ""

    styled = df.style.applymap(style_flag, subset=["Flag"]).applymap(style_sr, subset=["SR"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

# ── TAB 2: Phase breakdown ───────────────────────────────────────────────────
with tab_phase:
    for phase in PHASES:
        color = PHASE_COLORS[phase]
        overs = f"Overs {PHASES[phase][0]}–{PHASES[phase][1]}"

        phase_rows = []
        for d in data:
            ph = d["phases"][phase]
            if ph["balls"] == 0:
                continue
            phase_rows.append({
                "Batter": d["name"],
                "Runs":   ph["runs"],
                "Balls":  ph["balls"],
                "SR":     ph["sr"] if ph["sr"] else 0,
                "Flag":   flag_label(ph["flag"]),
            })

        phase_runs  = sum(r["Runs"]  for r in phase_rows)
        phase_balls = sum(r["Balls"] for r in phase_rows)
        phase_rr    = round(phase_runs / (phase_balls / 6), 2) if phase_balls > 0 else 0

        st.markdown(f"#### {phase} &nbsp; `{overs}` &nbsp;—&nbsp; {phase_runs} runs · RR {phase_rr}")

        if phase_rows:
            df_phase = pd.DataFrame(phase_rows)
            styled_p = (
                df_phase.style
                .applymap(style_flag, subset=["Flag"])
                .applymap(style_sr,   subset=["SR"])
            )
            st.dataframe(styled_p, use_container_width=True, hide_index=True)
        else:
            st.caption("No balls recorded for this phase.")
        st.divider()

# ── TAB 3: Charts ────────────────────────────────────────────────────────────
with tab_charts:
    col_l, col_r = st.columns(2)

    # SR bar chart (overall)
    with col_l:
        st.markdown("**Strike rate — top batters (overall)**")
        chart_data = [d for d in data if d["total_b"] >= min_balls]
        if chart_data:
            names = [d["name"].split()[-1] for d in chart_data]
            srs   = [d["total_sr"] for d in chart_data]
            colors = ["#A32D2D" if s < sr_threshold else "#1D9E75" for s in srs]
            fig = go.Figure(go.Bar(
                x=names, y=srs, marker_color=colors,
                text=[str(s) for s in srs], textposition="outside",
            ))
            fig.add_hline(y=sr_threshold, line_dash="dash", line_color="#888",
                          annotation_text=f"Threshold ({sr_threshold})", annotation_position="top right")
            fig.update_layout(
                yaxis_title="Strike rate", plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=20, b=10, l=0, r=0),
                height=300, showlegend=False,
                yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("No qualified batters to chart.")

    # Phase-wise runs stacked bar
    with col_r:
        st.markdown("**Runs by phase — each batter**")
        valid = [d for d in data if d["total_r"] > 0]
        if valid:
            bnames = [d["name"].split()[-1] for d in valid]
            pp_runs    = [d["phases"]["Powerplay"]["runs"]    for d in valid]
            mid_runs   = [d["phases"]["Middle overs"]["runs"] for d in valid]
            death_runs = [d["phases"]["Death overs"]["runs"]  for d in valid]
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(name="Powerplay",    x=bnames, y=pp_runs,    marker_color=PHASE_COLORS["Powerplay"]))
            fig2.add_trace(go.Bar(name="Middle overs", x=bnames, y=mid_runs,   marker_color=PHASE_COLORS["Middle overs"]))
            fig2.add_trace(go.Bar(name="Death overs",  x=bnames, y=death_runs, marker_color=PHASE_COLORS["Death overs"]))
            fig2.update_layout(
                barmode="stack", yaxis_title="Runs", height=300,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=20, b=10, l=0, r=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.caption("No runs to chart.")

    # SR heatmap across phases
    st.markdown("**SR heatmap — batter × phase**")
    heat_rows = []
    for d in data:
        if d["total_b"] == 0:
            continue
        row = {"Batter": d["name"].split()[-1]}
        for phase in PHASES:
            ph = d["phases"][phase]
            row[phase] = ph["sr"] if ph["sr"] else 0
        heat_rows.append(row)

    if heat_rows:
        df_heat = pd.DataFrame(heat_rows).set_index("Batter")
        fig3 = go.Figure(go.Heatmap(
            z=df_heat.values,
            x=df_heat.columns.tolist(),
            y=df_heat.index.tolist(),
            colorscale=[[0, "#FCEBEB"], [0.5, "#FAEEDA"], [1, "#EAF3DE"]],
            zmin=0, zmax=250,
            text=[[str(v) if v > 0 else "—" for v in row] for row in df_heat.values],
            texttemplate="%{text}",
            textfont={"size": 12},
            hoverongaps=False,
        ))
        fig3.add_vline(x=-0.5, line_color="rgba(0,0,0,0)")
        fig3.update_layout(
            height=250, margin=dict(t=10, b=10, l=0, r=60),
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(side="top"),
        )
        st.plotly_chart(fig3, use_container_width=True)

    # Innings run progression (estimated)
    st.markdown("**Estimated run progression by phase**")
    pp_total    = sum(d["phases"]["Powerplay"]["runs"]    for d in data)
    mid_total   = sum(d["phases"]["Middle overs"]["runs"] for d in data)
    death_total = sum(d["phases"]["Death overs"]["runs"]  for d in data)
    fig4 = go.Figure()
    fig4.add_trace(go.Bar(
        x=["Powerplay (1–6)", "Middle overs (7–15)", "Death overs (16–20)"],
        y=[pp_total, mid_total, death_total],
        marker_color=[PHASE_COLORS["Powerplay"], PHASE_COLORS["Middle overs"], PHASE_COLORS["Death overs"]],
        text=[pp_total, mid_total, death_total],
        textposition="outside",
    ))
    fig4.update_layout(
        yaxis_title="Runs", height=250, showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=20, b=10, l=0, r=0),
        yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
    )
    st.plotly_chart(fig4, use_container_width=True)

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption("T20 Innings Metric Tool · Phase-wise SR analysis for top-order batters")
