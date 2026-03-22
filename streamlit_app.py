"""
streamlit_app.py — Helixis LC Monitor
Two-tab layout: Live (fragment, no blink) + Historik
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os

st.set_page_config(
    page_title="Helixis LC Monitor",
    page_icon="🌀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SWE   = ZoneInfo("Europe/Stockholm")
BG    = "#FFFFFF"
BG2   = "#F5F6FA"
BORDER= "#DDE0EB"
TEXT  = "#1C2033"
MUTED = "#8A90A8"
BLUE  = "#1F4FE0"
TEAL  = "#167A5E"
AMBER = "#B87200"
RUST  = "#A83030"
SLATE = "#2E5EA0"

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  header[data-testid="stHeader"]{{background:transparent!important;height:0!important;}}
  #MainMenu,footer{{visibility:hidden;}}
  html,body,[class*="css"]{{font-family:'Inter',-apple-system,sans-serif!important;background:{BG};color:{TEXT};}}
  .block-container{{padding-top:1.2rem!important;padding-bottom:1.5rem;background:{BG};max-width:1400px;}}
  .stApp{{background:{BG};}}
  section[data-testid="stSidebar"]{{background:{BG2};border-right:1px solid {BORDER};}}
  div[data-testid="metric-container"]{{background:{BG2};border:1px solid {BORDER};border-radius:8px;padding:14px 18px;}}
  div[data-testid="metric-container"] label{{font-size:.68rem;color:{MUTED};text-transform:uppercase;letter-spacing:.08em;font-weight:500;}}
  div[data-testid="metric-container"] [data-testid="stMetricValue"]{{color:{TEXT};font-size:1.25rem;font-weight:600;}}
  .section-title{{font-size:.62rem;font-weight:600;color:{MUTED};text-transform:uppercase;letter-spacing:.12em;margin:20px 0 8px;border-left:2px solid {BLUE};padding-left:8px;}}
  .status-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle;}}
  .ts-text{{font-size:.78rem;color:{MUTED};vertical-align:middle;}}
</style>
""", unsafe_allow_html=True)

# ── DB client ─────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

db = get_db()

# ── Data fetchers ─────────────────────────────────────────────
@st.cache_data(ttl=25)          # live: fresh every 25 s
def fetch_live() -> pd.DataFrame:
    """Latest 20 min of data — fast, for live tiles."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        res = db.table("sensor_readings") \
            .select("created_at,sensor,value") \
            .gte("created_at", since) \
            .order("created_at", desc=False) \
            .execute()
        if not res.data:
            return pd.DataFrame()
        df = pd.DataFrame(res.data)
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
        return df.sort_values("created_at")
    except Exception as exc:
        st.error(f"DB error: {exc}")
        return pd.DataFrame()

@st.cache_data(ttl=120)         # history: re-fetch every 2 min
def fetch_history(hours_back: int) -> pd.DataFrame:
    """Paginated fetch for the history tab."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    all_rows, page_size, offset = [], 1000, 0
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
        st.error(f"DB error: {exc}")
        return pd.DataFrame()
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df.sort_values("created_at")

# ── Helpers ───────────────────────────────────────────────────
def latest_val(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def fmt(val, decimals=1, unit=""):
    return f"{val:.{decimals}f} {unit}".strip() if val is not None else "—"

def integrate_power(df) -> float | None:
    """Trapezoid integration of power sensor → kWh today."""
    now_swe   = datetime.now(SWE)
    today_utc = now_swe.replace(hour=0, minute=0, second=0, microsecond=0) \
                       .astimezone(timezone.utc)
    sub = df[df["sensor"] == "power"].copy()
    sub = sub[sub["created_at"] >= today_utc].sort_values("created_at")
    if len(sub) < 2:
        return None
    times  = sub["created_at"].astype("int64") / 1e9 / 3600   # → hours
    power  = sub["value"].values
    import numpy as np
    return float(max(0, np.trapz(power, times)))

def metric_tile(label, val, unit, mn, mx, color, decimals=1, warn=None):
    display = fmt(val, decimals, unit)
    pct = 0
    if val is not None and mx > mn:
        pct = max(0, min(100, round((val - mn) / (mx - mn) * 100)))
    warn_html = f"<span style='color:{RUST};font-size:.7rem;margin-left:6px'>⚠</span>" \
                if warn and val is not None and val >= warn else ""
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
    cols = st.columns(len(specs))
    for col, (label, val, unit, mn, mx, color, dec, warn) in zip(cols, specs):
        col.markdown(metric_tile(label, val, unit, mn, mx, color, dec, warn),
                     unsafe_allow_html=True)

def linechart(df, sensors, colors, ylabel, height=300):
    names = {
        "temp_right_coll":"Collector R","temp_left_coll":"Collector L",
        "temp_tank":"Tank","temp_forward":"Forward","temp_return":"Return",
        "temp_difference":"ΔT","power":"Power","flow":"Flow",
        "irradiance":"Irradiance","wind":"Wind","heat_energy":"Heat energy",
    }
    fig = go.Figure()
    for s, c in zip(sensors, colors):
        sub = df[df["sensor"] == s]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["created_at"], y=sub["value"],
            name=names.get(s, s), mode="lines",
            line=dict(width=1.8, color=c),
        ))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title=ylabel,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color=MUTED, family="Inter")),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, family="Inter"),
    )
    fig.update_xaxes(showgrid=False, color=MUTED)
    fig.update_yaxes(gridcolor=BORDER, color=MUTED)
    return fig

# ── Header (always rendered, never re-runs) ───────────────────
h1, h2 = st.columns([3, 3])
with h1:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=160)
    else:
        st.markdown(f"<div style='font-size:1.4rem;font-weight:800;color:{TEXT}'>HELIXIS</div>",
                    unsafe_allow_html=True)

st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:6px 0 4px'>",
            unsafe_allow_html=True)

# ── Top-level tabs ────────────────────────────────────────────
tab_live, tab_hist = st.tabs(["🔴  Live", "📈  Historik"])

# ════════════════════════════════════════════════════════════════
# LIVE TAB — fragment isolates re-runs to this section only
# ════════════════════════════════════════════════════════════════
with tab_live:

    @st.fragment(run_every=30)
    def live_dashboard():
        df = fetch_live()

        if df.empty:
            st.warning("No data yet.")
            return

        v       = {s: latest_val(df, s) for s in df["sensor"].unique()}
        last_ts = df["created_at"].max()
        age_min = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
        is_live = age_min < 15
        last_swe= last_ts.astimezone(SWE)
        irr     = v.get("irradiance")
        pres    = v.get("pressure")

        # Status bar
        dot_color = TEAL if is_live else RUST
        st.markdown(
            f'<span class="status-dot" style="background:{dot_color}"></span>'
            f'<span class="ts-text">{last_swe.strftime("%H:%M:%S")} '
            f'{"· LIVE" if is_live else "· OFFLINE"}</span>',
            unsafe_allow_html=True,
        )

        irr_color = AMBER if (irr and irr > 700) else (SLATE if (irr and irr > 200) else MUTED)
        pcolor    = RUST  if (pres and pres >= 5) else SLATE

        # Energy today (from live window — approx; history tab has full calc)
        energy_today = integrate_power(df)

        st.markdown('<div class="section-title">Temperatures</div>', unsafe_allow_html=True)
        render_tiles([
            ("Collector R", v.get("temp_right_coll"), "°C", 20, 160, RUST,  1, None),
            ("Collector L", v.get("temp_left_coll"),  "°C", 20, 160, AMBER, 1, None),
            ("Forward",     v.get("temp_forward"),    "°C", 20, 120, RUST,  1, None),
            ("Return",      v.get("temp_return"),     "°C", 10, 100, SLATE, 1, None),
            ("Tank",        v.get("temp_tank"),       "°C", 10, 100, TEAL,  1, None),
        ])

        st.markdown('<div class="section-title">Flow, Power & Environment</div>',
                    unsafe_allow_html=True)
        render_tiles([
            ("Flow rate",        v.get("flow"),       "m³/h", 0, 1,    SLATE,     3, None),
            ("Thermal power",    v.get("power"),      "kW",   0, 9.2,  RUST,      2, None),
            ("Solar irradiance", irr,                 "W/m²", 0, 1350, irr_color, 0, None),
            ("System pressure",  pres,                "bar",  0, 6,    pcolor,    2, 5.0),
            ("Wind speed",       v.get("wind"),       "m/s",  0, 20,   SLATE,     2, None),
            ("ΔT Fwd−Ret",       v.get("temp_difference"), "°C", 0, 50, BLUE,    2, None),
        ])

        st.markdown('<div class="section-title">Energy</div>', unsafe_allow_html=True)
        render_tiles([
            ("Energy today (approx)", energy_today,         "kWh", 0, 30,   TEAL, 3, None),
            ("Heat energy (total)",   v.get("heat_energy"), "kWh", 0, 9999, BLUE, 3, None),
        ])

    live_dashboard()

# ════════════════════════════════════════════════════════════════
# HISTORIK TAB — full paginated data, user-controlled range
# ════════════════════════════════════════════════════════════════
with tab_hist:

    # Controls
    c1, c2 = st.columns([2, 5])
    with c1:
        def fmt_hours(h):
            return f"{h}h" if h < 24 else (f"{h//24} dag" if h//24 == 1 else f"{h//24} dagar")
        hours = st.selectbox("Tidsintervall",
            options=[1, 6, 12, 24, 48, 168], index=3, format_func=fmt_hours)

    with c2:
        sensor_groups = {
            "Temperaturer":  ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"],
            "Effekt & flöde":["power","flow"],
            "Sol & miljö":   ["irradiance","wind"],
            "ΔT-analys":     ["temp_difference","temp_forward","temp_return"],
        }
        view = st.selectbox("Visa", list(sensor_groups.keys()))

    with st.spinner("Hämtar historik…"):
        df_hist = fetch_history(hours)

    if df_hist.empty:
        st.warning("Ingen data för valt intervall.")
    else:
        sensors = sensor_groups[view]
        colors_map = {
            "temp_right_coll": RUST,  "temp_left_coll": AMBER,
            "temp_forward":    RUST,  "temp_return":    SLATE,
            "temp_tank":       TEAL,  "power":          RUST,
            "flow":            SLATE, "irradiance":     AMBER,
            "wind":            SLATE, "temp_difference":TEXT,
        }
        colors  = [colors_map.get(s, MUTED) for s in sensors]
        ylabels = {"Temperaturer":"°C","Effekt & flöde":"kW / m³/h",
                   "Sol & miljö":"W/m² / m/s","ΔT-analys":"°C"}

        st.plotly_chart(
            linechart(df_hist, sensors, colors, ylabels[view], height=400),
            use_container_width=True,
        )

        # Summary stats
        st.markdown('<div class="section-title">Sammanfattning för perioden</div>',
                    unsafe_allow_html=True)
        pivot = df_hist[df_hist["sensor"].isin(sensors)] \
            .groupby("sensor")["value"] \
            .agg(["min","max","mean"]).round(2).reset_index()
        pivot.columns = ["Sensor","Min","Max","Medel"]
        st.dataframe(pivot, use_container_width=True, hide_index=True)

        # Energy for period (trapezoid)
        energy_period = integrate_power(df_hist)
        if energy_period is not None:
            st.markdown('<div class="section-title">Energi</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            col1.metric("Energy today (trapets-integration)", f"{energy_period:.3f} kWh")
            col2.metric("Heat energy sensor (total)",
                        fmt(latest_val(df_hist,"heat_energy"), 3, "kWh"))

        with st.expander("📥 Rådata & export"):
            pivot2 = df_hist.pivot_table(
                index="created_at", columns="sensor", values="value", aggfunc="last"
            ).reset_index().sort_values("created_at", ascending=False)
            st.dataframe(pivot2.head(500), use_container_width=True)
            st.download_button("⬇️ Ladda ner CSV", df_hist.to_csv(index=False),
                file_name=f"helixis_{hours}h.csv", mime="text/csv")

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{TEXT};font-weight:600;font-size:.9rem;margin-bottom:12px'>Om systemet</div>",
                unsafe_allow_html=True)
    st.markdown(f"""
<div style='font-size:.75rem;color:{MUTED};line-height:1.9'>
<b style='color:{TEXT}'>Helixis LC12 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Max temp: 160°C · Max pressure: 6 bar
</div>""", unsafe_allow_html=True)
