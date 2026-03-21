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

LOGO_B64 = "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"

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
    import base64 as _b64
    logo_bytes = _b64.b64decode(LOGO_B64)
    st.image(logo_bytes, width=160)
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
