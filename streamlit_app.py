"""
streamlit_app.py — Helixis LC Monitor
Light theme dashboard.
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="Helixis LC Monitor", page_icon="🌀",
                   layout="wide", initial_sidebar_state="collapsed")

BLUE  = "#2B5BF5"
WHITE = "#FFFFFF"
BG    = "#F4F6FA"
CARD  = "#FFFFFF"
BORDER= "#E2E6EF"
TEXT  = "#1A1E2E"
MUTED = "#6B7590"
GREEN = "#1D9E75"
AMBER = "#E89B00"
RED   = "#D93B3B"
LBLUE = "#3A7BF5"

st.markdown(f"""
<style>
  html,body,[class*="css"]{{font-family:'Inter',-apple-system,sans-serif;background:{BG};color:{TEXT};}}
  .block-container{{padding-top:.8rem;padding-bottom:1rem;background:{BG};}}
  .stApp{{background:{BG};}}
  section[data-testid="stSidebar"]{{background:{CARD};border-right:1px solid {BORDER};}}

  div[data-testid="metric-container"]{{
    background:{CARD};border:1px solid {BORDER};
    border-radius:10px;padding:12px 16px;
  }}
  div[data-testid="metric-container"] label{{
    font-size:.7rem;color:{MUTED};
    text-transform:uppercase;letter-spacing:.07em;
  }}
  div[data-testid="metric-container"] [data-testid="stMetricValue"]{{
    color:{TEXT};font-size:1.2rem;font-weight:600;
  }}

  .section-title{{
    font-size:.65rem;font-weight:600;color:{MUTED};
    text-transform:uppercase;letter-spacing:.1em;
    margin:18px 0 8px;border-left:3px solid {BLUE};padding-left:8px;
  }}
  .status-bar{{padding:8px 16px;border-radius:8px;font-size:.83rem;margin-bottom:10px;font-weight:500;}}
  .s-good{{background:#E8F8F3;color:#0F6E50;border:1px solid #B8E8D8;}}
  .s-warn{{background:#FFF8E6;color:#8A5E00;border:1px solid #FFE0A0;}}
  .s-idle{{background:#F0F2F7;color:{MUTED};border:1px solid {BORDER};}}
  .s-alert{{background:#FEF0F0;color:#A02020;border:1px solid #F5C0C0;}}

  .helixis-logo{{font-size:1.5rem;font-weight:800;color:{TEXT};letter-spacing:-.03em;}}
  .helixis-logo span{{color:{BLUE};}}
  .helixis-sub{{font-size:.72rem;color:{MUTED};text-transform:uppercase;letter-spacing:.1em;}}
  .live-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;background:{GREEN};margin-right:6px;animation:pulse 2s infinite;}}
  @keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:.4;}}}}
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
        res = db.table("sensor_readings").select("created_at,sensor,value")\
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

# ── Vertical thermometer ──────────────────────────────────────
def thermo(label, val, mn, mx, color):
    display = val if val is not None else mn
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[label], y=[mx - mn], base=mn,
        marker_color=BORDER, width=0.5, showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Bar(x=[label], y=[max(0, display - mn)], base=mn,
        marker_color=color, width=0.5, showlegend=False,
        hovertemplate=f"{label}: {display:.1f}°C<extra></extra>"))
    fig.add_annotation(x=label, y=mn + (mx - mn) * 0.08,
        text=f"<b>{display:.1f}°C</b>",
        font=dict(size=13, color=color), showarrow=False)
    fig.update_layout(
        height=180, barmode="overlay",
        margin=dict(l=4, r=4, t=28, b=4),
        title=dict(text=label, font=dict(size=10, color=MUTED), x=0.5),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(range=[mn, mx], gridcolor=BORDER, color=MUTED,
                   tickfont=dict(size=8), tickvals=[mn, round((mn+mx)/2), mx]),
        xaxis=dict(showticklabels=False),
        showlegend=False,
    )
    return fig

# ── Semicircle gauge ──────────────────────────────────────────
def semi(label, val, mn, mx, unit, color, sub="", warn=None):
    steps = []
    if warn:
        steps = [{"range": [mn, warn], "color": "#EEF2FF"},
                 {"range": [warn, mx], "color": "#FFF3CD"}]
    else:
        steps = [{"range": [mn, mx], "color": "#EEF2FF"}]
    threshold = {"line": {"color": AMBER, "width": 3}, "thickness": 0.8, "value": warn} if warn else None

    indicator = dict(
        mode="gauge+number",
        value=val if val is not None else 0,
        number={"suffix": f" {unit}", "font": {"size": 26, "color": color}},
        gauge={
            "axis": {"range": [mn, mx], "tickfont": {"size": 9, "color": MUTED}},
            "bar": {"color": color},
            "bgcolor": "#EEF2FF", "borderwidth": 0,
            "steps": steps,
            **({"threshold": threshold} if threshold else {}),
        },
        title={"text": f"{label}<br><span style='font-size:10px;color:{MUTED}'>{sub}</span>",
               "font": {"size": 12, "color": MUTED}},
    )
    fig = go.Figure(go.Indicator(**indicator))
    fig.update_layout(height=210, margin=dict(l=16, r=16, t=55, b=8),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig

# ── Line chart ────────────────────────────────────────────────
def linechart(df, sensors, colors, ylabel, height=270):
    labels = {
        "temp_right_coll":"Collector R","temp_left_coll":"Collector L",
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
        height=height, margin=dict(l=0,r=0,t=10,b=0),
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
        format_func=lambda h: f"{h}h" if h < 24 else f"{h//24} day{'s' if h>24 else ''}")
    auto_ref = st.checkbox("Auto-refresh 60s", value=True)
    if st.button("↺  Refresh now"):
        st.cache_data.clear(); st.rerun()
    st.divider()
    st.markdown(f"""
<div style='font-size:.75rem;color:{MUTED};line-height:1.8'>
<b style='color:{TEXT}'>Helixis LC12 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Optical efficiency: 75%<br>
Max temp: 160°C · Max pressure: 6 bar<br>
Fluid: Water / Propylene Glycol
</div>""", unsafe_allow_html=True)

if auto_ref:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

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
    st.markdown(f'<div class="helixis-logo">HEL<span>I</span>XIS</div>'
                f'<div class="helixis-sub">LC Linear Concentrator — Live Monitor</div>',
                unsafe_allow_html=True)
with h2:
    st.markdown(f"""
<div style='padding-top:6px;font-size:.8rem;color:{MUTED}'>
<span class="live-dot"></span>
Last update: <b style='color:{TEXT}'>{last_ts.strftime('%H:%M:%S UTC')}</b>
</div>""", unsafe_allow_html=True)
with h3:
    if "view" not in st.session_state:
        st.session_state.view = "gauges"
    if st.button("⇄ View"):
        st.session_state.view = "numeric" if st.session_state.view == "gauges" else "gauges"

# Status
if pres and pres >= 5:
    st.markdown(f'<div class="status-bar s-alert">⚠ HIGH PRESSURE: {pres:.2f} bar — approaching max 6 bar</div>', unsafe_allow_html=True)
elif pwr and irr and irr > 200 and pwr > 1.0:
    st.markdown('<div class="status-bar s-good">● System actively harvesting solar energy — concentrator tracking sun</div>', unsafe_allow_html=True)
elif irr and irr > 50:
    st.markdown('<div class="status-bar s-warn">● Low irradiance — limited collection</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="status-bar s-idle">● System idle — insufficient direct sunlight</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
if st.session_state.view == "gauges":

    st.markdown('<div class="section-title">Receiver Tube & Circuit Temperatures</div>', unsafe_allow_html=True)
    tc = st.columns(5)
    temps = [
        ("Collector R", "temp_right_coll", RED,   20, 160),
        ("Collector L", "temp_left_coll",  AMBER, 20, 160),
        ("Forward",     "temp_forward",    RED,   20, 120),
        ("Return",      "temp_return",     LBLUE, 10, 100),
        ("Tank",        "temp_tank",       GREEN, 10, 100),
    ]
    for col, (lbl, sensor, color, mn, mx) in zip(tc, temps):
        col.plotly_chart(thermo(lbl, v.get(sensor), mn, mx, color),
                         use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Flow & Thermal Power</div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    with f1:
        st.plotly_chart(semi("Flow rate", v.get("flow"), 0, 1, "m³/h", LBLUE,
                             "Heat-transfer fluid circulation"),
                        use_container_width=True, config={"displayModeBar": False})
    with f2:
        st.plotly_chart(semi("Thermal power", v.get("power"), 0, 9.2, "kW", RED,
                             "Peak 9.2 kW @ 1000 W/m²"),
                        use_container_width=True, config={"displayModeBar": False})
    with f3:
        pcolor = RED if (pres and pres >= 5) else LBLUE
        psub = "⚠ Warning: > 5 bar" if (pres and pres >= 5) else "Normal — max 6 bar"
        st.plotly_chart(semi("System pressure", pres, 0, 6, "bar", pcolor, psub, warn=5),
                        use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Energy & Environment</div>', unsafe_allow_html=True)
    k1,k2,k3,k4,k5 = st.columns(5)
    ef = v.get("Energifaktor")
    k1.metric("Heat Energy", fmt(v.get("heat_energy"), 3, "kWh"), help="Accumulated since last reset")
    k2.metric("Energy Counter", fmt(ef/1000 if ef else None, 2, "kWh"), help="Cumulative Wh→kWh")
    k3.metric("ΔT Forward−Return", fmt(v.get("temp_difference"), 2, "°C"), help="Energy per litre")
    k4.metric("Solar Irradiance", fmt(v.get("irradiance"), 0, "W/m²"), help="Peak design: 1000 W/m²")
    k5.metric("Wind Speed", fmt(v.get("wind"), 2, "m/s"))

    st.divider()
    st.markdown('<div class="section-title">Historical Trends</div>', unsafe_allow_html=True)
    t1,t2,t3,t4 = st.tabs(["🌡️ Temperatures","⚡ Power & Flow","☀️ Solar vs Output","🔁 ΔT Analysis"])
    with t1:
        st.plotly_chart(linechart(df,
            ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"],
            [RED, AMBER, "#E06020", LBLUE, GREEN], "°C"), use_container_width=True)
    with t2:
        ca,cb = st.columns(2)
        with ca:
            st.caption("Thermal power (kW)")
            st.plotly_chart(linechart(df,["power"],[RED],"kW",240), use_container_width=True)
        with cb:
            st.caption("Flow rate (m³/h)")
            st.plotly_chart(linechart(df,["flow"],[LBLUE],"m³/h",240), use_container_width=True)
    with t3:
        st.caption("Strong correlation between irradiance and power = efficient dual-axis tracking")
        fig_d = go.Figure()
        for s,color,yax,name in [("irradiance",AMBER,"y","Irradiance (W/m²)"),("power",RED,"y2","Power (kW)")]:
            sub = df[df["sensor"]==s]
            if not sub.empty:
                fig_d.add_trace(go.Scatter(x=sub["created_at"],y=sub["value"],
                    name=name,mode="lines",line=dict(width=2,color=color),yaxis=yax))
        fig_d.update_layout(height=270,margin=dict(l=0,r=0,t=10,b=0),
            yaxis=dict(title="W/m²",color=AMBER),
            yaxis2=dict(title="kW",color=RED,overlaying="y",side="right"),
            hovermode="x unified",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h",yanchor="bottom",y=1.02,font=dict(color=MUTED)),font=dict(color=MUTED))
        fig_d.update_xaxes(showgrid=False,color=MUTED)
        fig_d.update_yaxes(gridcolor=BORDER,color=MUTED)
        st.plotly_chart(fig_d,use_container_width=True)
    with t4:
        st.caption("ΔT = Forward − Return. Higher ΔT = more energy extracted per litre of flow.")
        st.plotly_chart(linechart(df,["temp_difference","temp_forward","temp_return"],
            [TEXT,RED,LBLUE],"°C"),use_container_width=True)

else:
    st.markdown('<div class="section-title">Solar Concentrator & Environment</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Solar Irradiance", fmt(v.get("irradiance"),0,"W/m²"), help="Peak design: 1000 W/m²")
    c2.metric("Solar Cell Temp", fmt(v.get("temp_cell"),1,"°C"))
    c3.metric("Wind Speed", fmt(v.get("wind"),2,"m/s"))
    pres_val = v.get("pressure")
    c4.metric("System Pressure",
              fmt(pres_val,2,"bar") + (" ⚠" if pres_val and pres_val>=5 else ""),
              help="Max 6 bar. Warning at 5 bar")

    st.markdown('<div class="section-title">Receiver Tube & Circuit Temperatures</div>', unsafe_allow_html=True)
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Collector Right", fmt(v.get("temp_right_coll"),1,"°C"), help="Range: 20–160°C")
    c2.metric("Collector Left",  fmt(v.get("temp_left_coll"),1,"°C"),  help="Range: 20–160°C")
    c3.metric("Forward",         fmt(v.get("temp_forward"),1,"°C"),    help="Hot fluid to tank")
    c4.metric("Return",          fmt(v.get("temp_return"),1,"°C"),     help="Cooled fluid from tank")
    c5.metric("Tank",            fmt(v.get("temp_tank"),1,"°C"),       help="Storage temperature")

    st.markdown('<div class="section-title">Thermal Power & Heat Transfer</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Thermal Power",      fmt(v.get("power"),2,"kW"),    help="Peak: 9.2 kW @ 1000 W/m²")
    c2.metric("Flow Rate",          fmt(v.get("flow"),3,"m³/h"))
    c3.metric("ΔT Forward−Return",  fmt(v.get("temp_difference"),2,"°C"))
    c4.metric("Volume",             fmt(v.get("volume"),1,"L"))

    st.markdown('<div class="section-title">Accumulated Energy</div>', unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    c1.metric("Heat Energy", fmt(v.get("heat_energy"),3,"kWh"))
    ef = v.get("Energifaktor")
    c2.metric("Energy Counter", fmt(ef/1000 if ef else None,2,"kWh"))

    with st.expander("📥 Raw data & export"):
        pivot = df.pivot_table(index="created_at",columns="sensor",values="value",aggfunc="last")\
            .reset_index().sort_values("created_at",ascending=False)
        st.dataframe(pivot.head(300),use_container_width=True)
        st.download_button("⬇️ Download CSV",df.to_csv(index=False),
            file_name=f"helixis_{hours}h.csv",mime="text/csv")
