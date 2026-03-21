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

LOGO_B64 = None  # loaded from logo.png

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  header[data-testid="stHeader"] {{ background:transparent!important; height:0!important; }}
  #MainMenu, footer {{ visibility:hidden; }}
  html,body,[class*="css"] {{ font-family:'Inter',-apple-system,sans-serif!important; background:{BG}; color:{TEXT}; }}
  .block-container {{ padding-top:1.2rem!important; padding-bottom:1.5rem; background:{BG}; max-width:1400px; }}
  .stApp {{ background:{BG}; }}
  section[data-testid="stSidebar"] {{ background:{BG2}; border-right:1px solid {BORDER}; }}
  div[data-testid="metric-container"] {{
    background:{BG2}; border:1px solid {BORDER}; border-radius:8px; padding:14px 18px;
  }}
  div[data-testid="metric-container"] label {{
    font-size:.68rem; color:{MUTED}; text-transform:uppercase; letter-spacing:.08em; font-weight:500;
  }}
  div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
    color:{TEXT}; font-size:1.25rem; font-weight:600;
  }}
  .section-title {{
    font-size:.62rem; font-weight:600; color:{MUTED};
    text-transform:uppercase; letter-spacing:.12em;
    margin:20px 0 8px; border-left:2px solid {BLUE}; padding-left:8px;
  }}
  .status-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:5px; vertical-align:middle; }}
  .ts-text {{ font-size:.78rem; color:{MUTED}; vertical-align:middle; }}
</style>
""", unsafe_allow_html=True)

# ── Supabase ──────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

db = get_db()

def fetch_data(hours):
    try:
        res = db.table("sensor_readings").select("created_at,sensor,value") \
            .order("created_at", desc=True).limit(5000).execute()
    except Exception as exc:
        st.error(f"Database error: {exc}"); return pd.DataFrame()
    if not res.data: return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df

def fetch_today():
    now_swe = datetime.now(SWE)
    today_swe = now_swe.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_swe.astimezone(timezone.utc)
    try:
        res = db.table("sensor_readings").select("created_at,sensor,value") \
            .gte("created_at", today_utc.isoformat()).order("created_at").limit(20_000).execute()
    except Exception:
        return pd.DataFrame()
    if not res.data: return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    df = df.sort_values("created_at")
    return df

def latest(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def today_energy(df_today):
    sub = df_today[df_today["sensor"] == "heat_energy"].sort_values("created_at")
    if len(sub) < 2: return None
    delta = float(sub["value"].iloc[-1]) - float(sub["value"].iloc[0])
    return delta if delta >= 0 else None

def fmt(val, decimals=1, unit=""):
    if val is None: return "—"
    return f"{val:.{decimals}f} {unit}".strip()

def make_thermo(label, val, mn, mx, color):
    display = val if val is not None else mn
    mid = round((mn + mx) / 2)
    fill_h = max(0.5, display - mn)
    val_y = min(display + (mx - mn) * 0.12, mx - (mx - mn) * 0.1)

    fig = go.Figure()
    fig.add_trace(go.Bar(x=[0], y=[mx - mn], base=mn,
        marker_color=LGRAY, marker_line=dict(color=BORDER, width=1),
        width=0.5, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Bar(x=[0], y=[fill_h], base=mn,
        marker_color=color, width=0.5, showlegend=False,
        hovertemplate=f"<b>{display:.1f}°C</b><extra></extra>"))
    fig.add_shape(type="circle",
        x0=-0.32, x1=0.32, y0=mn - 7, y1=mn + 7,
        fillcolor=color, line_color=color)
    fig.add_annotation(x=0, y=val_y,
        text=f"<b>{display:.1f}°</b>",
        font=dict(size=11, color=color, family="Inter"),
        showarrow=False, xanchor="center", yanchor="bottom")
    fig.update_layout(
        height=200, barmode="overlay",
        margin=dict(l=30, r=8, t=8, b=8),
        title=dict(text=f"<b>{label}</b>",
                   font=dict(size=10, color=TEXT, family="Inter"), x=0.5),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(range=[mn - 10, mx], gridcolor=BORDER, color=MUTED,
                   tickfont=dict(size=8, family="Inter"),
                   tickvals=[mn, mid, mx],
                   ticktext=[f"{mn}°", f"{mid}°", f"{mx}°"]),
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        showlegend=False,
    )
    return fig

def semi(label, val, mn, mx, unit, color, sub_text="", warn=None):
    steps = [{"range": [mn, warn if warn else mx], "color": BG2}]
    if warn:
        steps.append({"range": [warn, mx], "color": "#FFF0D0"})
    threshold = ({"line": {"color": AMBER, "width": 2},
                  "thickness": 0.75, "value": warn} if warn else None)
    nfmt = ".0f" if unit == "W/m²" else (".2f" if unit in ["bar", "m³/h"] else ".1f")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val if val is not None else 0,
        number={"suffix": f" {unit}", "font": {"size": 20, "color": color, "family": "Inter"},
                "valueformat": nfmt},
        gauge={
            "axis": {"range": [mn, mx],
                     "tickfont": {"size": 8, "color": MUTED, "family": "Inter"},
                     "tickcolor": BORDER, "nticks": 5},
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": BG2, "borderwidth": 1, "bordercolor": BORDER,
            "steps": steps,
            **({"threshold": threshold} if threshold else {}),
        },
        title={
            "text": (f"<span style=\'font-weight:600;font-size:13px;color:{TEXT};font-family:Inter\'>{label}</span>"
                     f"<br><span style=\'font-size:10px;color:{MUTED};font-family:Inter\'>{sub_text}</span>"),
            "font": {"size": 13, "family": "Inter"},
        },
    ))
    fig.update_layout(height=230, margin=dict(l=24, r=24, t=80, b=12),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig

def linechart(df, sensors, colors, ylabel, height=270):
    labels = {
        "temp_right_coll": "Collector R", "temp_left_coll": "Collector L",
        "temp_tank": "Tank", "temp_forward": "Forward", "temp_return": "Return",
        "temp_difference": "ΔT", "power": "Power", "flow": "Flow",
        "irradiance": "Irradiance", "wind": "Wind", "heat_energy": "Heat energy",
    }
    fig = go.Figure()
    for s, c in zip(sensors, colors):
        sub = df[df["sensor"] == s]
        if sub.empty: continue
        fig.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
            name=labels.get(s, s), mode="lines", line=dict(width=1.8, color=c)))
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
    st.markdown(f"<div style='font-family:Inter;color:{TEXT};font-weight:600;font-size:.9rem;margin-bottom:12px'>Settings</div>",
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
        st.cache_data.clear(); st.rerun()
    st.divider()
    st.markdown(f"""
<div style='font-family:Inter;font-size:.75rem;color:{MUTED};line-height:1.9'>
<b style='color:{TEXT}'>Helixis LC12 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Optical efficiency: 75%<br>
Max temp: 160°C · Max pressure: 6 bar
</div>""", unsafe_allow_html=True)

if auto_ref:
    # Simple reliable refresh — rerun every 60s via meta tag
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────
df       = fetch_data(hours)
df_today = fetch_today()

if df.empty:
    st.warning("No data received yet."); st.stop()

v = {s: latest(df, s) for s in df["sensor"].unique()}

# DEBUG
now_utc = datetime.now(timezone.utc)
now_swe = datetime.now(SWE)
today_swe = now_swe.replace(hour=0, minute=0, second=0, microsecond=0)
today_utc_check = today_swe.astimezone(timezone.utc)
st.info(f"DEBUG: now_utc={now_utc.strftime('%H:%M:%S')}, now_swe={now_swe.strftime('%H:%M:%S')}, today_utc_start={today_utc_check.strftime('%Y-%m-%d %H:%M')}, df last={df['created_at'].max()}, df rows={len(df)}, today rows={len(df_today)}")

latest_ts = df["created_at"].max()
if not df_today.empty:
    latest_ts = max(latest_ts, df_today["created_at"].max())
if latest_ts.tzinfo is None:
    latest_ts = latest_ts.replace(tzinfo=timezone.utc)

age_min  = (datetime.now(timezone.utc) - latest_ts).total_seconds() / 60
is_live  = age_min < 15
last_swe = latest_ts.astimezone(SWE)
pwr  = v.get("power")
irr  = v.get("irradiance")
pres = v.get("pressure")

# ── Header ────────────────────────────────────────────────────
h1, h2, h3 = st.columns([3, 3, 1])
with h1:
    try:
        st.image("logo.png", width=160)
    except Exception:
        st.markdown("**HELIXIS**")
with h2:
    dot_color = TEAL if is_live else RUST
    st.markdown(
        f'<div style="padding-top:14px"><span class="status-dot" style="background:{dot_color}"></span>'
        f'<span class="ts-text">{last_swe.strftime("%H:%M:%S")}</span></div>',
        unsafe_allow_html=True)
with h3:
    if "view" not in st.session_state:
        st.session_state.view = "gauges"
    if st.button("⇄ View"):
        st.session_state.view = "numeric" if st.session_state.view == "gauges" else "gauges"

st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:10px 0 4px'>",
            unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
if st.session_state.view == "gauges":

    st.markdown('<div class="section-title">Receiver Tube & Circuit Temperatures</div>',
                unsafe_allow_html=True)
    tc = st.columns(5)
    for col, (lbl, sensor, color, mn, mx) in zip(tc, [
        ("Collector R", "temp_right_coll", RUST,  20, 160),
        ("Collector L", "temp_left_coll",  AMBER, 20, 160),
        ("Forward",     "temp_forward",    RUST,  20, 120),
        ("Return",      "temp_return",     SLATE, 10, 100),
        ("Tank",        "temp_tank",       TEAL,  10, 100),
    ]):
        col.plotly_chart(make_thermo(lbl, v.get(sensor), mn, mx, color),
                         use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Flow, Power & Solar Irradiance</div>',
                unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.plotly_chart(semi("Flow rate", v.get("flow"), 0, 1, "m³/h", SLATE,
                             "Heat-transfer fluid circulation"),
                        use_container_width=True, config={"displayModeBar": False})
    with f2:
        st.plotly_chart(semi("Thermal power", v.get("power"), 0, 9.2, "kW", RUST,
                             "Rated 9.2 kW at 1000 W/m²"),
                        use_container_width=True, config={"displayModeBar": False})
    with f3:
        irr_color = AMBER if (irr and irr > 700) else (SLATE if (irr and irr > 200) else MUTED)
        irr_sub = "Excellent" if (irr and irr > 700) else ("Moderate" if (irr and irr > 200) else "Low / night")
        st.plotly_chart(semi("Solar irradiance", irr, 0, 1350, "W/m²", irr_color,
                             f"{irr_sub} — TOA max ~1350 W/m²"),
                        use_container_width=True, config={"displayModeBar": False})
    with f4:
        pcolor = RUST if (pres and pres >= 5) else SLATE
        psub = "Warning: approaching max 6 bar" if (pres and pres >= 5) else "Operating range 0–6 bar"
        st.plotly_chart(semi("System pressure", pres, 0, 6, "bar", pcolor, psub, warn=5),
                        use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Energy</div>', unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    energy_today = today_energy(df_today)
    k1.metric("Energy today",        fmt(energy_today, 3, "kWh"),
              help="Heat energy harvested since midnight (Swedish time)")
    k2.metric("Heat energy (total)", fmt(v.get("heat_energy"), 3, "kWh"),
              help="Accumulated since last meter reset")
    k3.metric("ΔT Forward−Return",   fmt(v.get("temp_difference"), 2, "°C"),
              help="Temperature drop across heat exchanger")

    st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:16px 0 4px'>",
                unsafe_allow_html=True)
    st.markdown('<div class="section-title">Today\'s Trends</div>', unsafe_allow_html=True)
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

else:
    st.markdown('<div class="section-title">Solar & Environment</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Solar Irradiance", fmt(v.get("irradiance"), 0, "W/m²"))
    c2.metric("Solar Cell Temp",  fmt(v.get("temp_cell"), 1, "°C"))
    c3.metric("Wind Speed",       fmt(v.get("wind"), 2, "m/s"))
    pv = v.get("pressure")
    c4.metric("System Pressure",  fmt(pv, 2, "bar") + (" ⚠" if pv and pv >= 5 else ""))

    st.markdown('<div class="section-title">Temperatures</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Collector Right", fmt(v.get("temp_right_coll"), 1, "°C"))
    c2.metric("Collector Left",  fmt(v.get("temp_left_coll"),  1, "°C"))
    c3.metric("Forward",         fmt(v.get("temp_forward"),    1, "°C"))
    c4.metric("Return",          fmt(v.get("temp_return"),     1, "°C"))
    c5.metric("Tank",            fmt(v.get("temp_tank"),       1, "°C"))

    st.markdown('<div class="section-title">Power & Flow</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Thermal Power",     fmt(v.get("power"), 2, "kW"))
    c2.metric("Flow Rate",         fmt(v.get("flow"), 3, "m³/h"))
    c3.metric("ΔT Forward−Return", fmt(v.get("temp_difference"), 2, "°C"))
    c4.metric("Volume",            fmt(v.get("volume"), 1, "L"))

    st.markdown('<div class="section-title">Energy</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    energy_today = today_energy(df_today)
    c1.metric("Energy today",        fmt(energy_today, 3, "kWh"), help="Since midnight Swedish time")
    c2.metric("Heat energy (total)", fmt(v.get("heat_energy"), 3, "kWh"))

    with st.expander("📥 Raw data & export"):
        pivot = df.pivot_table(index="created_at", columns="sensor", values="value", aggfunc="last") \
            .reset_index().sort_values("created_at", ascending=False)
        st.dataframe(pivot.head(300), use_container_width=True)
        st.download_button("⬇️ Download CSV", df.to_csv(index=False),
            file_name=f"helixis_{hours}h.csv", mime="text/csv")
