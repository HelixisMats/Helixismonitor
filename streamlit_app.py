"""
streamlit_app.py — Helixis LC Monitor
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import time

st.set_page_config(page_title="Helixis LC Monitor", page_icon="🌀",
                   layout="wide", initial_sidebar_state="collapsed")

BLUE  = "#2B5BF5"
BG    = "#F0F2F7"
CARD  = "#FFFFFF"
BORDER= "#D8DCE8"
TEXT  = "#1A1E2E"
MUTED = "#6B7590"
GREEN = "#1D9E75"
AMBER = "#E89B00"
RED   = "#C93333"
LBLUE = "#3A7BF5"

st.markdown(f"""
<style>
  /* Remove Streamlit's default white header bar */
  header[data-testid="stHeader"] {{
    background: transparent !important;
    height: 0 !important;
  }}
  #MainMenu, footer, header {{ visibility: hidden; }}

  html,body,[class*="css"] {{
    font-family: 'Inter',-apple-system,sans-serif;
    background: {BG};
    color: {TEXT};
  }}
  .block-container {{
    padding-top: 1.2rem !important;
    padding-bottom: 1rem;
    background: {BG};
  }}
  .stApp {{ background: {BG}; }}
  section[data-testid="stSidebar"] {{
    background: {CARD};
    border-right: 1px solid {BORDER};
  }}

  div[data-testid="metric-container"] {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 12px 16px;
  }}
  div[data-testid="metric-container"] label {{
    font-size: .7rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: .07em;
  }}
  div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
    color: {TEXT}; font-size: 1.2rem; font-weight: 600;
  }}

  .section-title {{
    font-size: .65rem; font-weight: 600; color: {MUTED};
    text-transform: uppercase; letter-spacing: .1em;
    margin: 16px 0 6px; border-left: 3px solid {BLUE}; padding-left: 8px;
  }}

  /* Subtle status pill */
  .status-pill {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px;
    font-size: .75rem; font-weight: 500; margin-bottom: 12px;
  }}
  .s-good {{ background: #E6F5F0; color: #0D6645; }}
  .s-warn {{ background: #FDF5E0; color: #7A5200; }}
  .s-idle {{ background: #ECEEF4; color: {MUTED}; }}
  .s-alert {{ background: #FDECEA; color: #8B1A1A; }}
  .dot {{ width:7px;height:7px;border-radius:50%;display:inline-block; }}

  .helixis-logo {{
    font-size: 1.5rem; font-weight: 800;
    color: {TEXT}; letter-spacing: -.03em; line-height: 1;
  }}
  .helixis-logo span {{ color: {BLUE}; }}
  .helixis-sub {{
    font-size: .68rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: .1em; margin-top: 2px;
  }}
  .live-dot {{
    display: inline-block; width: 7px; height: 7px;
    border-radius: 50%; background: {GREEN}; margin-right: 5px;
  }}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

db = get_db()

@st.cache_data(ttl=60)
def fetch_data(hours):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        res = db.table("sensor_readings").select("created_at,sensor,value") \
            .gte("created_at", since).order("created_at").limit(50_000).execute()
    except Exception as exc:
        st.error(f"Database error: {exc}"); return pd.DataFrame()
    if not res.data: return pd.DataFrame()
    df = pd.DataFrame(res.data)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df

def latest(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def fmt(val, decimals=1, unit=""):
    if val is None: return "—"
    return f"{val:.{decimals}f} {unit}".strip()

# ── Thermometer (vertical bar) ────────────────────────────────
def thermo(label, val, mn, mx, color):
    display = val if val is not None else mn
    pct = max(0.0, min(1.0, (display - mn) / (mx - mn)))

    fig = go.Figure()
    # Track
    fig.add_trace(go.Bar(
        x=[0], y=[mx - mn], base=mn,
        marker_color="#DCE0EC", width=0.6,
        showlegend=False, hoverinfo="skip"
    ))
    # Fill
    fill_h = max(0.5, display - mn)
    fig.add_trace(go.Bar(
        x=[0], y=[fill_h], base=mn,
        marker_color=color, width=0.6,
        showlegend=False,
        hovertemplate=f"<b>{display:.1f}°C</b><extra>{label}</extra>"
    ))
    fig.add_annotation(
        x=0, y=mn + (mx - mn) * 0.06,
        text=f"<b>{display:.1f}°C</b>",
        font=dict(size=13, color=color, family="Inter"),
        showarrow=False
    )
    fig.update_layout(
        height=185, barmode="overlay",
        margin=dict(l=28, r=8, t=26, b=4),
        title=dict(text=label, font=dict(size=10, color=MUTED), x=0.5),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(
            range=[mn, mx],
            gridcolor=BORDER, color=MUTED,
            tickfont=dict(size=8),
            tickvals=[mn, round((mn + mx) / 2), mx],
        ),
        xaxis=dict(showticklabels=False, showgrid=False),
        showlegend=False,
    )
    return fig

# ── Semicircle gauge ──────────────────────────────────────────
def semi(label, val, mn, mx, unit, color, sub="", warn=None):
    steps = [{"range": [mn, warn if warn else mx], "color": "#E8ECF8"}]
    if warn:
        steps.append({"range": [warn, mx], "color": "#FFF0CC"})
    threshold = ({"line": {"color": AMBER, "width": 3},
                  "thickness": 0.8, "value": warn} if warn else None)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val if val is not None else 0,
        number={"suffix": f" {unit}", "font": {"size": 22, "color": color, "family": "Inter"}},
        gauge={
            "axis": {"range": [mn, mx],
                     "tickfont": {"size": 9, "color": MUTED},
                     "tickcolor": BORDER},
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": "#E8ECF8",
            "borderwidth": 0,
            "steps": steps,
            **({"threshold": threshold} if threshold else {}),
        },
        title={
            "text": f"<b>{label}</b><br><span style='font-size:10px;color:{MUTED}'>{sub}</span>",
            "font": {"size": 12, "color": TEXT, "family": "Inter"},
        },
    ))
    fig.update_layout(
        height=210, margin=dict(l=20, r=20, t=60, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig

# ── Line chart ────────────────────────────────────────────────
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
        fig.add_trace(go.Scatter(
            x=sub["created_at"], y=sub["value"],
            name=labels.get(s, s), mode="lines",
            line=dict(width=2, color=c)
        ))
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
    fig.update_yaxes(gridcolor=BORDER, color=MUTED)
    return fig

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{TEXT};font-weight:700;margin-bottom:12px'>Settings</div>",
                unsafe_allow_html=True)
    hours = st.selectbox("Time window",
        options=[1, 6, 12, 24, 48, 168], index=3,
        format_func=lambda h: f"{h}h" if h < 24 else f"{h//24} day{'s' if h > 24 else ''}")
    auto_ref = st.checkbox("Auto-refresh 60s", value=True)
    if st.button("↺  Refresh now"):
        st.cache_data.clear(); st.rerun()
    st.divider()
    st.markdown(f"""
<div style='font-size:.75rem;color:{MUTED};line-height:1.9'>
<b style='color:{TEXT}'>Helixis LC12 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Optical efficiency: 75%<br>
Max temp: 160°C · Max pressure: 6 bar<br>
Fluid: Water / Propylene Glycol
</div>""", unsafe_allow_html=True)

# ── Smooth auto-refresh ───────────────────────────────────────
if auto_ref:
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()
    if time.time() - st.session_state.last_refresh > 60:
        st.session_state.last_refresh = time.time()
        st.cache_data.clear()
        st.rerun()

# ── Load ──────────────────────────────────────────────────────
df = fetch_data(hours)
if df.empty:
    st.warning("No data received yet."); st.stop()

v = {s: latest(df, s) for s in df["sensor"].unique()}
last_ts = df["created_at"].max().astimezone(timezone.utc)
pwr = v.get("power"); irr = v.get("irradiance"); pres = v.get("pressure")

# ── Header ────────────────────────────────────────────────────
h1, h2, h3 = st.columns([4, 3, 1])
with h1:
    st.markdown(
        f'<div class="helixis-logo">HEL<span>I</span>XIS</div>'
        f'<div class="helixis-sub">LC Linear Concentrator — Live Monitor</div>',
        unsafe_allow_html=True)
with h2:
    st.markdown(f"""
<div style='padding-top:8px;font-size:.8rem;color:{MUTED}'>
<span class="live-dot"></span>
Last update: <b style='color:{TEXT}'>{last_ts.strftime('%H:%M:%S UTC')}</b>
</div>""", unsafe_allow_html=True)
with h3:
    if "view" not in st.session_state:
        st.session_state.view = "gauges"
    if st.button("⇄ View"):
        st.session_state.view = "numeric" if st.session_state.view == "gauges" else "gauges"

# Status pill — subtle
if pres and pres >= 5:
    st.markdown(f'<div class="status-pill s-alert"><span class="dot" style="background:#C93333"></span>High pressure: {pres:.2f} bar — max 6 bar</div>', unsafe_allow_html=True)
elif pwr and irr and irr > 200 and pwr > 1.0:
    st.markdown(f'<div class="status-pill s-good"><span class="dot" style="background:{GREEN}"></span>Actively harvesting — concentrator tracking sun</div>', unsafe_allow_html=True)
elif irr and irr > 50:
    st.markdown(f'<div class="status-pill s-warn"><span class="dot" style="background:{AMBER}"></span>Low irradiance — limited collection</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="status-pill s-idle"><span class="dot" style="background:{MUTED}"></span>Idle — insufficient direct sunlight</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
if st.session_state.view == "gauges":

    st.markdown('<div class="section-title">Receiver Tube & Circuit Temperatures</div>', unsafe_allow_html=True)
    tc = st.columns(5)
    for col, (lbl, sensor, color, mn, mx) in zip(tc, [
        ("Collector R", "temp_right_coll", RED,   20, 160),
        ("Collector L", "temp_left_coll",  AMBER, 20, 160),
        ("Forward",     "temp_forward",    RED,   20, 120),
        ("Return",      "temp_return",     LBLUE, 10, 100),
        ("Tank",        "temp_tank",       GREEN, 10, 100),
    ]):
        col.plotly_chart(thermo(lbl, v.get(sensor), mn, mx, color),
                         use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Flow, Power & Solar Irradiance</div>', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        st.plotly_chart(semi("Flow rate", v.get("flow"), 0, 1, "m³/h", LBLUE,
                             "Fluid circulation"),
                        use_container_width=True, config={"displayModeBar": False})
    with f2:
        st.plotly_chart(semi("Thermal power", v.get("power"), 0, 9.2, "kW", RED,
                             "Peak 9.2 kW @ 1000 W/m²"),
                        use_container_width=True, config={"displayModeBar": False})
    with f3:
        irr_color = AMBER if (irr and irr > 700) else (LBLUE if (irr and irr > 200) else MUTED)
        irr_sub = "Excellent" if (irr and irr > 700) else ("Good" if (irr and irr > 200) else "Low")
        st.plotly_chart(semi("Solar irradiance", irr, 0, 1000, "W/m²", irr_color,
                             f"{irr_sub} — design peak 1000 W/m²"),
                        use_container_width=True, config={"displayModeBar": False})
    with f4:
        pcolor = RED if (pres and pres >= 5) else LBLUE
        psub = "⚠ High — max 6 bar" if (pres and pres >= 5) else "Normal — max 6 bar"
        st.plotly_chart(semi("System pressure", pres, 0, 6, "bar", pcolor, psub, warn=5),
                        use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Energy</div>', unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    ef = v.get("Energifaktor")
    k1.metric("Heat Energy",       fmt(v.get("heat_energy"), 3, "kWh"), help="Accumulated since last reset")
    k2.metric("Energy Counter",    fmt(ef / 1000 if ef else None, 2, "kWh"), help="Cumulative Wh → kWh")
    k3.metric("ΔT Forward−Return", fmt(v.get("temp_difference"), 2, "°C"), help="Energy per litre of flow")

    st.divider()
    st.markdown('<div class="section-title">Historical Trends</div>', unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs(["🌡️ Temperatures", "⚡ Power & Flow", "☀️ Solar vs Output", "🔁 ΔT Analysis"])
    with t1:
        st.plotly_chart(linechart(df,
            ["temp_right_coll", "temp_left_coll", "temp_forward", "temp_return", "temp_tank"],
            [RED, AMBER, "#D06020", LBLUE, GREEN], "°C"), use_container_width=True)
    with t2:
        ca, cb = st.columns(2)
        with ca:
            st.caption("Thermal power (kW)")
            st.plotly_chart(linechart(df, ["power"], [RED], "kW", 240), use_container_width=True)
        with cb:
            st.caption("Flow rate (m³/h)")
            st.plotly_chart(linechart(df, ["flow"], [LBLUE], "m³/h", 240), use_container_width=True)
    with t3:
        st.caption("Strong correlation = efficient dual-axis tracking")
        fig_d = go.Figure()
        for s, color, yax, name in [
            ("irradiance", AMBER, "y", "Irradiance (W/m²)"),
            ("power", RED, "y2", "Power (kW)"),
        ]:
            sub = df[df["sensor"] == s]
            if not sub.empty:
                fig_d.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
                    name=name, mode="lines", line=dict(width=2, color=color), yaxis=yax))
        fig_d.update_layout(height=270, margin=dict(l=0,r=0,t=10,b=0),
            yaxis=dict(title="W/m²", color=AMBER),
            yaxis2=dict(title="kW", color=RED, overlaying="y", side="right"),
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(color=MUTED)),
            font=dict(color=MUTED))
        fig_d.update_xaxes(showgrid=False, color=MUTED)
        fig_d.update_yaxes(gridcolor=BORDER, color=MUTED)
        st.plotly_chart(fig_d, use_container_width=True)
    with t4:
        st.caption("Higher ΔT = more energy extracted per litre of flow")
        st.plotly_chart(linechart(df,
            ["temp_difference", "temp_forward", "temp_return"],
            [TEXT, RED, LBLUE], "°C"), use_container_width=True)

else:
    st.markdown('<div class="section-title">Solar Concentrator & Environment</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Solar Irradiance", fmt(v.get("irradiance"), 0, "W/m²"), help="Peak design: 1000 W/m²")
    c2.metric("Solar Cell Temp",  fmt(v.get("temp_cell"), 1, "°C"))
    c3.metric("Wind Speed",       fmt(v.get("wind"), 2, "m/s"))
    pv = v.get("pressure")
    c4.metric("System Pressure",  fmt(pv, 2, "bar") + (" ⚠" if pv and pv >= 5 else ""),
              help="Max 6 bar. Warning at 5 bar")

    st.markdown('<div class="section-title">Receiver Tube & Circuit Temperatures</div>', unsafe_allow_html=True)
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Collector Right", fmt(v.get("temp_right_coll"), 1, "°C"))
    c2.metric("Collector Left",  fmt(v.get("temp_left_coll"),  1, "°C"))
    c3.metric("Forward",         fmt(v.get("temp_forward"),    1, "°C"))
    c4.metric("Return",          fmt(v.get("temp_return"),     1, "°C"))
    c5.metric("Tank",            fmt(v.get("temp_tank"),       1, "°C"))

    st.markdown('<div class="section-title">Thermal Power & Heat Transfer</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Thermal Power",     fmt(v.get("power"), 2, "kW"), help="Peak: 9.2 kW @ 1000 W/m²")
    c2.metric("Flow Rate",         fmt(v.get("flow"), 3, "m³/h"))
    c3.metric("ΔT Forward−Return", fmt(v.get("temp_difference"), 2, "°C"))
    c4.metric("Volume",            fmt(v.get("volume"), 1, "L"))

    st.markdown('<div class="section-title">Accumulated Energy</div>', unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    c1.metric("Heat Energy",    fmt(v.get("heat_energy"), 3, "kWh"))
    ef = v.get("Energifaktor")
    c2.metric("Energy Counter", fmt(ef / 1000 if ef else None, 2, "kWh"))

    with st.expander("📥 Raw data & export"):
        pivot = df.pivot_table(index="created_at", columns="sensor", values="value", aggfunc="last") \
            .reset_index().sort_values("created_at", ascending=False)
        st.dataframe(pivot.head(300), use_container_width=True)
        st.download_button("⬇️ Download CSV", df.to_csv(index=False),
            file_name=f"helixis_{hours}h.csv", mime="text/csv")
