"""
streamlit_app.py — Helixis LC Monitor
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import time
import os
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Helixis LC Monitor", page_icon="🌀",
                   layout="wide", initial_sidebar_state="collapsed")

SWE    = ZoneInfo("Europe/Stockholm")
BG     = "#FFFFFF"
BG2    = "#F5F6FA"
BORDER = "#DDE0EB"
TEXT   = "#1C2033"
MUTED  = "#8A90A8"
BLUE   = "#1F4FE0"
TEAL   = "#167A5E"
AMBER  = "#B87200"
RUST   = "#A83030"
SLATE  = "#2E5EA0"
LGRAY  = "#E4E7F0"

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  header[data-testid="stHeader"] {{ background:transparent!important; height:0!important; }}
  #MainMenu, footer {{ visibility:hidden; }}
  html,body,[class*="css"] {{ font-family:'Inter',-apple-system,sans-serif!important; background:{BG}; color:{TEXT}; }}
  .block-container {{ padding-top:1.2rem!important; padding-bottom:1.5rem; background:{BG}; max-width:1400px; }}
  .stApp {{ background:{BG}; }}
  section[data-testid="stSidebar"] {{ background:{BG2}; border-right:1px solid {BORDER}; }}
  div[data-testid="metric-container"] {{ background:{BG2}; border:1px solid {BORDER}; border-radius:8px; padding:14px 18px; }}
  div[data-testid="metric-container"] label {{ font-size:.68rem; color:{MUTED}; text-transform:uppercase; letter-spacing:.08em; font-weight:500; }}
  div[data-testid="metric-container"] [data-testid="stMetricValue"] {{ color:{TEXT}; font-size:1.25rem; font-weight:600; }}
  .section-title {{ font-size:.62rem; font-weight:600; color:{MUTED}; text-transform:uppercase; letter-spacing:.12em; margin:20px 0 8px; border-left:2px solid {BLUE}; padding-left:8px; }}
  .status-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; vertical-align:middle; }}
  .ts-text {{ font-size:.78rem; color:{MUTED}; vertical-align:middle; }}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

db = get_db()

def fetch_latest(hours_back=168):
    """Fetch all rows for the last `hours_back` hours using pagination."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    all_rows = []
    page_size = 1000
    offset = 0
    try:
        while True:
            res = db.table("sensor_readings") \
                .select("created_at,sensor,value") \
                .gte("created_at", since) \
                .order("created_at", desc=False) \
                .range(offset, offset + page_size - 1) \
                .execute()
            batch = res.data
            if not batch:
                break
            all_rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
    except Exception as exc:
        st.error(f"Database error: {exc}")
        return pd.DataFrame()
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df = df.sort_values("created_at")
    return df

def filter_hours(df, hours):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return df[df["created_at"] >= since]

def filter_today(df):
    now_swe = datetime.now(SWE)
    today_swe = now_swe.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_swe.astimezone(timezone.utc)
    return df[df["created_at"] >= today_utc]

def latest(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def today_energy(df_today):
    sub = df_today[df_today["sensor"] == "heat_energy"].sort_values("created_at")
    if len(sub) < 2:
        return None
    delta = float(sub["value"].iloc[-1]) - float(sub["value"].iloc[0])
    return delta if delta >= 0 else None

def fmt(val, decimals=1, unit=""):
    if val is None:
        return "—"
    return f"{val:.{decimals}f} {unit}".strip()

def metric_tile(label, val, unit, mn, mx, color, decimals=1, warn=None):
    """Compact metric tile with value, unit, and progress bar (style C)."""
    display = fmt(val, decimals, unit)
    pct = 0
    if val is not None and mx > mn:
        pct = max(0, min(100, round((val - mn) / (mx - mn) * 100)))
    warn_html = ""
    if warn and val is not None and val >= warn:
        warn_html = f"<span style='color:{RUST};font-size:.7rem;margin-left:6px'>⚠</span>"
    return f"""
<div style='background:{BG2};border-radius:8px;padding:12px 14px;height:100%'>
  <div style='font-size:.68rem;font-weight:500;color:{MUTED};text-transform:uppercase;
              letter-spacing:.08em;margin-bottom:4px'>{label}</div>
  <div style='font-size:1.25rem;font-weight:600;color:{color};line-height:1.1'>
    {display}{warn_html}
  </div>
  <div style='height:3px;border-radius:2px;background:{BORDER};margin-top:8px'>
    <div style='height:100%;width:{pct}%;border-radius:2px;background:{color};
                transition:width .4s'></div>
  </div>
</div>"""

def render_tiles(specs):
    """Render a list of tile specs in equal columns via st.markdown."""
    cols = st.columns(len(specs))
    for col, (label, val, unit, mn, mx, color, decimals, warn) in zip(cols, specs):
        col.markdown(
            metric_tile(label, val, unit, mn, mx, color, decimals, warn),
            unsafe_allow_html=True,
        )

def linechart(df, sensors, colors, ylabel, height=270):
    names = {
        "temp_right_coll": "Collector R", "temp_left_coll": "Collector L",
        "temp_tank": "Tank", "temp_forward": "Forward", "temp_return": "Return",
        "temp_difference": "ΔT", "power": "Power", "flow": "Flow",
        "irradiance": "Irradiance", "wind": "Wind", "heat_energy": "Heat energy",
    }
    fig = go.Figure()
    for s, c in zip(sensors, colors):
        sub = df[df["sensor"] == s]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
            name=names.get(s, s), mode="lines", line=dict(width=1.8, color=c)))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0), yaxis_title=ylabel,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color=MUTED, family="Inter")),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, family="Inter"),
    )
    fig.update_xaxes(showgrid=False, color=MUTED)
    fig.update_yaxes(gridcolor=BORDER, color=MUTED)
    return fig

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{TEXT};font-weight:600;font-size:.9rem;margin-bottom:12px'>Settings</div>",
                unsafe_allow_html=True)

    def fmt_hours(h):
        if h < 24:
            return f"{h}h"
        days = h // 24
        return f"{days} day" if days == 1 else f"{days} days"

    hours = st.selectbox("History window",
        options=[1, 6, 12, 24, 48, 168], index=3,
        format_func=fmt_hours)
    auto_ref = st.checkbox("Auto-refresh 60s", value=True)
    if st.button("↺  Refresh now"):
        st.rerun()
    st.divider()
    st.markdown(f"""
<div style='font-size:.75rem;color:{MUTED};line-height:1.9'>
<b style='color:{TEXT}'>Helixis LC12 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Max temp: 160°C · Max pressure: 6 bar
</div>""", unsafe_allow_html=True)

if auto_ref:
    st_autorefresh(interval=60_000, key="autorefresh")

# ── Load data ─────────────────────────────────────────────────
df_all   = fetch_latest(hours_back=max(hours, 24))
df       = filter_hours(df_all, hours)
df_today = filter_today(df_all)

if df_all.empty:
    st.warning("No data received yet.")
    st.stop()

v        = {s: latest(df_all, s) for s in df_all["sensor"].unique()}
last_ts  = df_all["created_at"].max()
age_min  = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
is_live  = age_min < 15
last_swe = last_ts.astimezone(SWE)
pwr  = v.get("power")
irr  = v.get("irradiance")
pres = v.get("pressure")

# ── Header ────────────────────────────────────────────────────
h1, h2 = st.columns([3, 3])
with h1:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=160)
    else:
        st.markdown(f"<div style='font-size:1.4rem;font-weight:800;color:{TEXT}'>HELIXIS</div>",
                    unsafe_allow_html=True)
with h2:
    dot_color = TEAL if is_live else RUST
    st.markdown(
        f'<div style="padding-top:14px">'
        f'<span class="status-dot" style="background:{dot_color}"></span>'
        f'<span class="ts-text">{last_swe.strftime("%H:%M:%S")}</span></div>',
        unsafe_allow_html=True)

st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:10px 0 4px'>",
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
irr_color    = AMBER if (irr and irr > 700) else (SLATE if (irr and irr > 200) else MUTED)
pcolor       = RUST  if (pres and pres >= 5) else SLATE
energy_today = today_energy(df_today)

st.markdown('<div class="section-title">Receiver Tube & Circuit Temperatures</div>',
            unsafe_allow_html=True)
render_tiles([
    ("Collector R", v.get("temp_right_coll"), "°C", 20, 160, RUST,  1, None),
    ("Collector L", v.get("temp_left_coll"),  "°C", 20, 160, AMBER, 1, None),
    ("Forward",     v.get("temp_forward"),    "°C", 20, 120, RUST,  1, None),
    ("Return",      v.get("temp_return"),     "°C", 10, 100, SLATE, 1, None),
    ("Tank",        v.get("temp_tank"),       "°C", 10, 100, TEAL,  1, None),
])

st.markdown('<div class="section-title">Flow, Power & Solar Irradiance</div>',
            unsafe_allow_html=True)
render_tiles([
    ("Flow rate",        v.get("flow"),  "m³/h", 0, 1,    SLATE,     3, None),
    ("Thermal power",    v.get("power"), "kW",   0, 9.2,  RUST,      2, None),
    ("Solar irradiance", irr,            "W/m²", 0, 1350, irr_color, 0, None),
    ("System pressure",  pres,           "bar",  0, 6,    pcolor,    2, 5.0),
])

st.markdown('<div class="section-title">Solar & Environment</div>',
            unsafe_allow_html=True)
render_tiles([
    ("Solar Cell Temp", v.get("temp_cell"), "°C",  0,  80,   AMBER, 1, None),
    ("Wind Speed",      v.get("wind"),      "m/s", 0,  20,   SLATE, 2, None),
    ("Volume",          v.get("volume"),    "L",   0,  500,  TEAL,  1, None),
    ("ΔT Fwd−Ret",      v.get("temp_difference"), "°C", 0, 50, BLUE, 2, None),
])

st.markdown('<div class="section-title">Energy</div>', unsafe_allow_html=True)
render_tiles([
    ("Energy today",       energy_today,          "kWh", 0, 30, TEAL,  3, None),
    ("Heat energy (total)",v.get("heat_energy"),  "kWh", 0, 9999, BLUE, 3, None),
])

st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:16px 0 4px'>",
            unsafe_allow_html=True)
st.markdown("<div class='section-title'>Today's Trends</div>", unsafe_allow_html=True)
chart_df = df_today if not df_today.empty else df

t1, t2, t3, t4 = st.tabs(["🌡️ Temperatures", "⚡ Power & Flow", "☀️ Solar vs Output", "🔁 ΔT Analysis"])
with t1:
    st.plotly_chart(linechart(chart_df,
        ["temp_right_coll", "temp_left_coll", "temp_forward", "temp_return", "temp_tank"],
        [RUST, AMBER, "#C06020", SLATE, TEAL], "°C"), use_container_width=True)
with t2:
    ca, cb = st.columns(2)
    with ca:
        st.caption("Thermal power (kW)")
        st.plotly_chart(linechart(chart_df, ["power"], [RUST], "kW", 240), use_container_width=True)
    with cb:
        st.caption("Flow rate (m³/h)")
        st.plotly_chart(linechart(chart_df, ["flow"], [SLATE], "m³/h", 240), use_container_width=True)
with t3:
    fig_d = go.Figure()
    for s, color, yax, name in [
        ("irradiance", AMBER, "y",  "Irradiance (W/m²)"),
        ("power",      RUST,  "y2", "Power (kW)"),
    ]:
        sub = chart_df[chart_df["sensor"] == s]
        if not sub.empty:
            fig_d.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
                name=name, mode="lines", line=dict(width=1.8, color=color), yaxis=yax))
    fig_d.update_layout(height=270, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="W/m²", color=AMBER),
        yaxis2=dict(title="kW", color=RUST, overlaying="y", side="right"),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(color=MUTED, family="Inter")),
        font=dict(color=MUTED, family="Inter"))
    fig_d.update_xaxes(showgrid=False, color=MUTED)
    fig_d.update_yaxes(gridcolor=BORDER, color=MUTED)
    st.plotly_chart(fig_d, use_container_width=True)
with t4:
    st.plotly_chart(linechart(chart_df,
        ["temp_difference", "temp_forward", "temp_return"],
        [TEXT, RUST, SLATE], "°C"), use_container_width=True)

with st.expander("📥 Raw data & export"):
    pivot = df.pivot_table(index="created_at", columns="sensor", values="value", aggfunc="last") \
        .reset_index().sort_values("created_at", ascending=False)
    st.dataframe(pivot.head(300), use_container_width=True)
    st.download_button("⬇️ Download CSV", df.to_csv(index=False),
        file_name=f"helixis_{hours}h.csv", mime="text/csv")
