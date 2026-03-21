"""
streamlit_app.py — Helixis LC Monitor
Branded dashboard matching Helixis identity.
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

st.set_page_config(
    page_title="Helixis LC Monitor",
    page_icon="🌀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

BLUE    = "#2B5BF5"
DARK_BG = "#16192A"
DARK2   = "#1E2236"
DARK3   = "#262C45"
WHITE   = "#FFFFFF"
MUTED   = "#7A85A0"
GREEN   = "#1D9E75"
AMBER   = "#F0A500"
RED     = "#E24B4A"
LBLUE   = "#5B8AF5"

st.markdown(f"""
<style>
  html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, sans-serif;
    background-color: {DARK_BG};
    color: {WHITE};
  }}
  .block-container {{ padding-top: 0.8rem; padding-bottom: 1rem; background-color: {DARK_BG}; }}
  .stApp {{ background-color: {DARK_BG}; }}
  section[data-testid="stSidebar"] {{ background: {DARK2}; }}

  div[data-testid="metric-container"] {{
    background: {DARK2};
    border: 1px solid {DARK3};
    border-radius: 10px;
    padding: 12px 16px;
  }}
  div[data-testid="metric-container"] label {{
    font-size: 0.7rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: 0.07em;
  }}
  div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
    color: {WHITE}; font-size: 1.25rem; font-weight: 600;
  }}

  .section-title {{
    font-size: 0.65rem; font-weight: 600; color: {MUTED};
    text-transform: uppercase; letter-spacing: 0.1em;
    margin: 18px 0 8px; border-left: 3px solid {BLUE}; padding-left: 8px;
  }}
  .status-bar {{
    padding: 8px 16px; border-radius: 8px;
    font-size: 0.83rem; margin-bottom: 10px; font-weight: 500;
  }}
  .s-good {{ background:rgba(29,158,117,.15); color:#4ecf9e; border:1px solid rgba(29,158,117,.3); }}
  .s-warn {{ background:rgba(240,165,0,.15);  color:#f0c050; border:1px solid rgba(240,165,0,.3); }}
  .s-idle {{ background:rgba(122,133,160,.1); color:{MUTED}; border:1px solid rgba(122,133,160,.2); }}

  .helixis-logo {{
    font-size: 1.45rem; font-weight: 800;
    color: {WHITE}; letter-spacing: -0.03em;
  }}
  .helixis-logo span {{ color: {BLUE}; }}
  .helixis-sub {{
    font-size: 0.72rem; color: {MUTED}; margin-top: 1px;
    text-transform: uppercase; letter-spacing: 0.1em;
  }}
  .live-dot {{
    display:inline-block; width:8px; height:8px;
    border-radius:50%; background:{GREEN};
    margin-right:6px; animation: pulse 2s infinite;
  }}
  @keyframes pulse {{
    0%,100% {{ opacity:1; }} 50% {{ opacity:.4; }}
  }}
  button[data-baseweb="tab"] {{ color:{MUTED} !important; font-size:0.8rem; }}
  button[data-baseweb="tab"][aria-selected="true"] {{ color:{WHITE} !important; }}
</style>
""", unsafe_allow_html=True)

# ── Supabase ──────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

db = get_db()

@st.cache_data(ttl=60)
def fetch_data(hours: int) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        res = (
            db.table("sensor_readings")
            .select("created_at, sensor, value")
            .gte("created_at", since)
            .order("created_at")
            .limit(50_000)
            .execute()
        )
    except Exception as exc:
        st.error(f"Database error: {exc}")
        return pd.DataFrame()
    if not res.data:
        return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df

def latest(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def fmt(val, decimals=1, unit=""):
    if val is None: return "—"
    return f"{val:.{decimals}f} {unit}".strip()

# ── Gauge builders ────────────────────────────────────────────
def thermo(label, val, mn, mx, color):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val if val is not None else mn,
        number={"suffix": "°C", "font": {"size": 18, "color": color}},
        gauge={
            "axis": {"range": [mn, mx], "tickwidth": 1,
                     "tickcolor": DARK3, "tickfont": {"size": 8, "color": MUTED}},
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": DARK3, "borderwidth": 0, "shape": "bullet",
        },
        title={"text": label, "font": {"size": 10, "color": MUTED}},
    ))
    fig.update_layout(height=105, margin=dict(l=8, r=8, t=28, b=4),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig

def semi(label, val, mn, mx, unit, color, sub=""):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val if val is not None else 0,
        number={"suffix": f" {unit}", "font": {"size": 24, "color": color}},
        gauge={
            "axis": {"range": [mn, mx], "tickfont": {"size": 9, "color": MUTED}},
            "bar": {"color": color},
            "bgcolor": DARK3, "borderwidth": 0,
            "steps": [{"range": [mn, mx], "color": DARK3}],
        },
        title={"text": f"{label}<br><span style='font-size:10px;color:{MUTED}'>{sub}</span>",
               "font": {"size": 12, "color": MUTED}},
    ))
    fig.update_layout(height=210, margin=dict(l=16, r=16, t=55, b=8),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig

def linechart(df, sensors, colors, ylabel, height=270):
    labels = {
        "temp_right_coll":"Collector Right","temp_left_coll":"Collector Left",
        "temp_tank":"Tank","temp_forward":"Forward","temp_return":"Return",
        "temp_cell":"Solar cell","temp_difference":"ΔT",
        "power":"Power","flow":"Flow","irradiance":"Irradiance",
        "wind":"Wind","heat_energy":"Heat energy","pressure":"Pressure",
    }
    fig = go.Figure()
    for s, c in zip(sensors, colors):
        sub = df[df["sensor"] == s]
        if sub.empty: continue
        fig.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
            name=labels.get(s, s), mode="lines", line=dict(width=2, color=c)))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title=ylabel,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color=MUTED)),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED),
    )
    fig.update_xaxes(showgrid=False, color=MUTED)
    fig.update_yaxes(gridcolor=DARK3, color=MUTED)
    return fig

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{WHITE};font-weight:700;margin-bottom:12px'>Settings</div>",
                unsafe_allow_html=True)
    hours = st.selectbox("Time window",
        options=[1, 6, 12, 24, 48, 168], index=3,
        format_func=lambda h: f"{h}h" if h < 24 else f"{h//24} day{'s' if h>24 else ''}")
    auto_ref = st.checkbox("Auto-refresh 60s", value=True)
    if st.button("↺  Refresh now"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown(f"""
<div style='font-size:0.75rem;color:{MUTED};line-height:1.7'>
<b style='color:{WHITE}'>Helixis LC Linear Concentrator</b><br>
CSP dual-axis tracking system<br>
Design temp: up to 160°C<br><br>
Node: <code>helix/1/1234</code><br>
Broker: <code>eaasy.life:1883</code>
</div>""", unsafe_allow_html=True)

if auto_ref:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

# ── Load ──────────────────────────────────────────────────────
df = fetch_data(hours)
if df.empty:
    st.warning("No data received yet.")
    st.stop()

v = {s: latest(df, s) for s in df["sensor"].unique()}
last_ts = df["created_at"].max().astimezone(timezone.utc)

# ── Header ────────────────────────────────────────────────────
h1, h2, h3 = st.columns([4, 3, 1])
with h1:
    st.markdown(f"""
<div class="helixis-logo">HEL<span>I</span>XIS</div>
<div class="helixis-sub">LC Linear Concentrator — Live Monitor</div>
""", unsafe_allow_html=True)
with h2:
    st.markdown(f"""
<div style='padding-top:6px;font-size:0.8rem;color:{MUTED}'>
<span class="live-dot"></span>
Last update: <b style='color:{WHITE}'>{last_ts.strftime('%H:%M:%S UTC')}</b>
<br>Rows collected: <b style='color:{WHITE}'>{len(df):,}</b>
</div>""", unsafe_allow_html=True)
with h3:
    if "view" not in st.session_state:
        st.session_state.view = "gauges"
    if st.button("⇄ View"):
        st.session_state.view = "numeric" if st.session_state.view == "gauges" else "gauges"

# Status
pwr = v.get("power"); irr = v.get("irradiance")
if pwr and irr and irr > 200 and pwr > 1.0:
    st.markdown('<div class="status-bar s-good">● System actively harvesting solar energy — concentrator tracking sun</div>', unsafe_allow_html=True)
elif irr and irr > 50:
    st.markdown('<div class="status-bar s-warn">● Low solar irradiance — limited collection</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="status-bar s-idle">● System idle — insufficient direct sunlight</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# GAUGE VIEW
# ══════════════════════════════════════════════════════════════
if st.session_state.view == "gauges":

    # Temperatures
    st.markdown('<div class="section-title">Receiver & Circuit Temperatures</div>', unsafe_allow_html=True)
    tc = st.columns(5)
    temps = [
        ("Collector R", "temp_right_coll", RED,   0, 160),
        ("Collector L", "temp_left_coll",  AMBER, 0, 160),
        ("Forward",     "temp_forward",    RED,   0, 160),
        ("Return",      "temp_return",     LBLUE, 0, 160),
        ("Tank",        "temp_tank",       GREEN, 10, 100),
    ]
    for col, (lbl, sensor, color, mn, mx) in zip(tc, temps):
        val = v.get(sensor)
        col.plotly_chart(thermo(lbl, val, mn, mx, color),
                         use_container_width=True,
                         config={"displayModeBar": False})

    # Flow & Power
    st.markdown('<div class="section-title">Flow & Thermal Power</div>', unsafe_allow_html=True)
    f1, f2 = st.columns(2)
    with f1:
        st.plotly_chart(
            semi("Flow rate", v.get("flow"), 0, 1, "m³/h", LBLUE,
                 "Heat-transfer fluid circulation"),
            use_container_width=True, config={"displayModeBar": False})
    with f2:
        st.plotly_chart(
            semi("Thermal power", v.get("power"), 0, 10, "kW", RED,
                 "Instantaneous heat output"),
            use_container_width=True, config={"displayModeBar": False})

    # KPIs
    st.markdown('<div class="section-title">Energy & Environment</div>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    ef = v.get("Energifaktor")
    k1.metric("Heat Energy", fmt(v.get("heat_energy"), 3, "kWh"),
              help="Accumulated thermal energy since last meter reset")
    k2.metric("Energy Counter", fmt(ef/1000 if ef else None, 2, "kWh"),
              help="Cumulative meter count (Wh → kWh)")
    k3.metric("ΔT Fwd−Ret", fmt(v.get("temp_difference"), 2, "°C"),
              help="Temperature drop = energy extracted per litre")
    k4.metric("Solar Irradiance", fmt(v.get("irradiance"), 0, "W/m²"),
              help="Direct Normal Irradiance hitting concentrator mirrors")
    k5.metric("Wind Speed", fmt(v.get("wind"), 2, "m/s"),
              help="Wind causes tracking resistance and heat loss")
    k6.metric("System Pressure", fmt(v.get("pressure"), 2, "bar"),
              help="Hydraulic pressure in the fluid circuit")

    # Charts
    st.divider()
    st.markdown('<div class="section-title">Historical Trends</div>', unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs([
        "🌡️ Temperatures", "⚡ Power & Flow", "☀️ Solar vs Output", "🔁 ΔT Analysis"])

    with t1:
        st.caption("Receiver tube temperatures track solar irradiance. Tank temperature rises as energy accumulates.")
        st.plotly_chart(linechart(df,
            ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"],
            [RED, AMBER, "#f39c12", LBLUE, GREEN], "°C"),
            use_container_width=True)

    with t2:
        ca, cb = st.columns(2)
        with ca:
            st.caption("Thermal power output (kW)")
            st.plotly_chart(linechart(df, ["power"], [RED], "kW", 240),
                            use_container_width=True)
        with cb:
            st.caption("Fluid flow rate (m³/h)")
            st.plotly_chart(linechart(df, ["flow"], [LBLUE], "m³/h", 240),
                            use_container_width=True)

    with t3:
        st.caption("Solar irradiance (left) vs thermal power output (right). Strong correlation = efficient tracking.")
        fig_d = go.Figure()
        for s, color, yax, name in [
            ("irradiance", AMBER, "y",  "Irradiance (W/m²)"),
            ("power",      RED,   "y2", "Power (kW)"),
        ]:
            sub = df[df["sensor"] == s]
            if not sub.empty:
                fig_d.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
                    name=name, mode="lines", line=dict(width=2, color=color), yaxis=yax))
        fig_d.update_layout(
            height=270, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title="W/m²", color=AMBER),
            yaxis2=dict(title="kW", color=RED, overlaying="y", side="right"),
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color=MUTED)),
            font=dict(color=MUTED),
        )
        fig_d.update_xaxes(showgrid=False, color=MUTED)
        fig_d.update_yaxes(gridcolor=DARK3, color=MUTED)
        st.plotly_chart(fig_d, use_container_width=True)

    with t4:
        st.caption("ΔT (forward−return) shows heat extraction efficiency. Higher ΔT = more energy per litre of flow.")
        st.plotly_chart(linechart(df,
            ["temp_difference", "temp_forward", "temp_return"],
            [WHITE, RED, LBLUE], "°C"), use_container_width=True)

# ══════════════════════════════════════════════════════════════
# NUMERIC VIEW
# ══════════════════════════════════════════════════════════════
else:
    st.markdown('<div class="section-title">Solar Concentrator & Environment</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Solar Irradiance", fmt(v.get("irradiance"), 0, "W/m²"),
              help="Direct Normal Irradiance. Above 200 W/m² = meaningful collection.")
    c2.metric("Solar Cell Temp", fmt(v.get("temp_cell"), 1, "°C"),
              help="Temperature of the PV/thermal cell. Affects tracking electronics.")
    c3.metric("Wind Speed", fmt(v.get("wind"), 2, "m/s"),
              help="Wind causes heat loss and tracking resistance.")
    c4.metric("System Pressure", fmt(v.get("pressure"), 2, "bar"),
              help="Hydraulic pressure. Should remain stable.")

    st.markdown('<div class="section-title">Receiver Tube & Circuit Temperatures</div>', unsafe_allow_html=True)
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Collector Right", fmt(v.get("temp_right_coll"), 1, "°C"),
              help="Right side of concentrator receiver tube.")
    c2.metric("Collector Left", fmt(v.get("temp_left_coll"), 1, "°C"),
              help="Left side of concentrator receiver tube.")
    c3.metric("Forward", fmt(v.get("temp_forward"), 1, "°C"),
              help="Hot fluid going from receiver to storage tank.")
    c4.metric("Return", fmt(v.get("temp_return"), 1, "°C"),
              help="Cooler fluid returning from tank to receiver.")
    c5.metric("Storage Tank", fmt(v.get("temp_tank"), 1, "°C"),
              help="Tank temperature rises as energy accumulates.")

    st.markdown('<div class="section-title">Thermal Power & Heat Transfer</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Thermal Power", fmt(v.get("power"), 2, "kW"),
              help="Instantaneous heat output = Flow × ΔT × heat capacity.")
    c2.metric("Flow Rate", fmt(v.get("flow"), 3, "m³/h"),
              help="Fluid circulation rate through receiver tube.")
    c3.metric("ΔT Forward−Return", fmt(v.get("temp_difference"), 2, "°C"),
              help="Energy extracted per litre of flow. Key efficiency indicator.")
    c4.metric("Volume", fmt(v.get("volume"), 1, "L"),
              help="Fluid volume in system. Should remain stable.")

    st.markdown('<div class="section-title">Accumulated Energy</div>', unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    c1.metric("Heat Energy", fmt(v.get("heat_energy"), 3, "kWh"),
              help="Total heat energy collected since last meter reset.")
    ef = v.get("Energifaktor")
    c2.metric("Energy Counter", fmt(ef/1000 if ef else None, 2, "kWh"),
              help="Cumulative meter count converted from Wh to kWh.")

    with st.expander("📥 Raw data & export"):
        pivot = df.pivot_table(
            index="created_at", columns="sensor", values="value", aggfunc="last"
        ).reset_index().sort_values("created_at", ascending=False)
        st.dataframe(pivot.head(300), use_container_width=True)
        st.download_button("⬇️ Download CSV", df.to_csv(index=False),
            file_name=f"helixis_{hours}h.csv", mime="text/csv")
