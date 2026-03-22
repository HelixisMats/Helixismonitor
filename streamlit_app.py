"""
streamlit_app.py — Helixis LC Monitor
Two-tab layout: Live (fragment, no blink) + Historik + SMHI
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import requests

st.set_page_config(
    page_title="Helixis LC Monitor",
    page_icon="🌀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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

# Örkelljunga / Eket coordinates
SITE_LAT = 56.248
SITE_LON = 13.192

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

# ── DB ────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

db = get_db()

# ── Data fetchers ─────────────────────────────────────────────
@st.cache_data(ttl=25)
def fetch_live() -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        res = db.table("sensor_readings") \
            .select("created_at,sensor,value") \
            .gte("created_at", since) \
            .order("created_at", desc=False).execute()
        if not res.data:
            return pd.DataFrame()
        df = pd.DataFrame(res.data)
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
        return df.sort_values("created_at")
    except Exception as exc:
        st.error(f"DB error: {exc}")
        return pd.DataFrame()

@st.cache_data(ttl=120)
def fetch_history(hours_back: int) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    all_rows, page_size, offset = [], 1000, 0
    try:
        while True:
            res = db.table("sensor_readings") \
                .select("created_at,sensor,value") \
                .gte("created_at", since) \
                .order("created_at", desc=False) \
                .range(offset, offset + page_size - 1).execute()
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

# ── SMHI ──────────────────────────────────────────────────────
# Closest SMHI stations to Örkelljunga:
#   Temp/wind:  Ängelholm (station 63600)
#   Irradiance: Lund (station 53430) — closest with global radiation
SMHI_STATIONS = {
    "temperature":  ("1", "63600"),   # parameter 1 = lufttemperatur, Ängelholm
    "wind_speed":   ("4", "63600"),   # parameter 4 = vindhastighet
    "irradiance":   ("11","53430"),   # parameter 11 = globalstrålning, Lund
    "cloud_cover":  ("16","63600"),   # parameter 16 = molnighet
}

@st.cache_data(ttl=600)   # refresh every 10 min
def fetch_smhi(param_key: str) -> pd.DataFrame | None:
    param, station = SMHI_STATIONS[param_key]
    url = (f"https://opendata-download-metobs.smhi.se/api/version/latest"
           f"/parameter/{param}/station/{station}/period/latest-day/data.json")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        rows = []
        for v in data.get("value", []):
            try:
                ts  = pd.to_datetime(v["date"], unit="ms", utc=True)
                val = float(v["value"])
                rows.append({"created_at": ts, "value": val})
            except Exception:
                continue
        if not rows:
            return None
        return pd.DataFrame(rows).sort_values("created_at")
    except Exception:
        return None

@st.cache_data(ttl=600)
def fetch_smhi_all() -> dict:
    return {k: fetch_smhi(k) for k in SMHI_STATIONS}

# ── Helpers ───────────────────────────────────────────────────
def latest_val(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def fmt(val, decimals=1, unit=""):
    return f"{val:.{decimals}f} {unit}".strip() if val is not None else "—"

def integrate_power(df) -> float | None:
    """Trapezoid integration of power sensor → kWh. NumPy-version safe."""
    now_swe   = datetime.now(SWE)
    today_utc = now_swe.replace(hour=0, minute=0, second=0, microsecond=0) \
                       .astimezone(timezone.utc)
    sub = df[df["sensor"] == "power"].copy()
    sub = sub[sub["created_at"] >= today_utc].sort_values("created_at")
    if len(sub) < 2:
        return None
    times = sub["created_at"].astype("int64").values / 1e9 / 3600  # → hours
    power = sub["value"].values.astype(float)
    # Compatible with both NumPy <2 and ≥2
    try:
        import numpy as np
        fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
        return float(max(0.0, fn(power, times)))
    except Exception:
        # Pure-Python fallback
        total = 0.0
        for i in range(1, len(times)):
            total += (power[i] + power[i-1]) / 2 * (times[i] - times[i-1])
        return max(0.0, total)

def metric_tile(label, val, unit, mn, mx, color, decimals=1, warn=None):
    display  = fmt(val, decimals, unit)
    pct      = 0
    if val is not None and mx > mn:
        pct = max(0, min(100, round((val - mn) / (mx - mn) * 100)))
    warn_html = (f"<span style='color:{RUST};font-size:.7rem;margin-left:6px'>⚠</span>"
                 if warn and val is not None and val >= warn else "")
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

def linechart(df, sensors, colors, ylabel, height=300, extra_traces=None):
    names = {
        "temp_right_coll":"Collector R","temp_left_coll":"Collector L",
        "temp_tank":"Tank","temp_forward":"Forward","temp_return":"Return",
        "temp_difference":"ΔT","power":"Power","flow":"Flow",
        "irradiance":"Irradiance (sensor)","wind":"Wind","heat_energy":"Heat energy",
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
    if extra_traces:
        for trace in extra_traces:
            fig.add_trace(trace)
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

# ── Header ────────────────────────────────────────────────────
with st.columns([3, 3])[0]:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=160)
    else:
        st.markdown(f"<div style='font-size:1.4rem;font-weight:800;color:{TEXT}'>HELIXIS</div>",
                    unsafe_allow_html=True)

st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:6px 0 4px'>",
            unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────
tab_live, tab_hist, tab_smhi = st.tabs(["🔴  Live", "📈  Historik", "🌤  SMHI & Analys"])

# ════════════════════════════════════════════════════════════════
# LIVE TAB
# ════════════════════════════════════════════════════════════════
with tab_live:

    @st.fragment(run_every=30)
    def live_dashboard():
        df = fetch_live()
        if df.empty:
            st.warning("Ingen data.")
            return

        v        = {s: latest_val(df, s) for s in df["sensor"].unique()}
        last_ts  = df["created_at"].max()
        age_min  = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
        is_live  = age_min < 15
        last_swe = last_ts.astimezone(SWE)
        irr      = v.get("irradiance")
        pres     = v.get("pressure")

        dot_color = TEAL if is_live else RUST
        st.markdown(
            f'<span class="status-dot" style="background:{dot_color}"></span>'
            f'<span class="ts-text">{last_swe.strftime("%H:%M:%S")} '
            f'{"· LIVE" if is_live else f"· {age_min:.0f} min sedan"}</span>',
            unsafe_allow_html=True,
        )

        irr_color = AMBER if (irr and irr > 700) else (SLATE if (irr and irr > 200) else MUTED)
        pcolor    = RUST  if (pres and pres >= 5) else SLATE

        st.markdown('<div class="section-title">Temperaturer</div>', unsafe_allow_html=True)
        render_tiles([
            ("Collector R", v.get("temp_right_coll"), "°C", 20, 160, RUST,  1, None),
            ("Collector L", v.get("temp_left_coll"),  "°C", 20, 160, AMBER, 1, None),
            ("Forward",     v.get("temp_forward"),    "°C", 20, 120, RUST,  1, None),
            ("Return",      v.get("temp_return"),     "°C", 10, 100, SLATE, 1, None),
            ("Tank",        v.get("temp_tank"),       "°C", 10, 100, TEAL,  1, None),
        ])

        st.markdown('<div class="section-title">Flöde, Effekt & Miljö</div>',
                    unsafe_allow_html=True)
        render_tiles([
            ("Flöde",            v.get("flow"),            "m³/h", 0, 1,    SLATE,     3, None),
            ("Termisk effekt",   v.get("power"),           "kW",   0, 9.2,  RUST,      2, None),
            ("Solinstrålning",   irr,                      "W/m²", 0, 1350, irr_color, 0, None),
            ("Systemtryck",      pres,                     "bar",  0, 6,    pcolor,    2, 5.0),
            ("Vind",             v.get("wind"),            "m/s",  0, 20,   SLATE,     2, None),
            ("ΔT Fwd−Ret",       v.get("temp_difference"), "°C",   0, 50,   BLUE,      2, None),
        ])

        st.markdown('<div class="section-title">Energi</div>', unsafe_allow_html=True)
        energy_today = integrate_power(df)
        render_tiles([
            ("Energi idag (beräknad)", energy_today,         "kWh", 0, 30,   TEAL, 3, None),
            ("Värmeenergi (total)",    v.get("heat_energy"), "kWh", 0, 9999, BLUE, 3, None),
        ])

    live_dashboard()

# ════════════════════════════════════════════════════════════════
# HISTORIK TAB
# ════════════════════════════════════════════════════════════════
with tab_hist:
    c1, c2 = st.columns([2, 5])
    with c1:
        def fmt_hours(h):
            return f"{h}h" if h < 24 else (f"{h//24} dag" if h//24 == 1 else f"{h//24} dagar")
        hours = st.selectbox("Tidsintervall",
            options=[1, 6, 12, 24, 48, 168], index=3, format_func=fmt_hours)
    with c2:
        sensor_groups = {
            "Temperaturer":   ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"],
            "Effekt & flöde": ["power","flow"],
            "Sol & miljö":    ["irradiance","wind"],
            "ΔT-analys":      ["temp_difference","temp_forward","temp_return"],
        }
        view = st.selectbox("Visa", list(sensor_groups.keys()))

    with st.spinner("Hämtar historik…"):
        df_hist = fetch_history(hours)

    if df_hist.empty:
        st.warning("Ingen data för valt intervall.")
    else:
        sensors = sensor_groups[view]
        colors_map = {
            "temp_right_coll":RUST, "temp_left_coll":AMBER,
            "temp_forward":RUST, "temp_return":SLATE,
            "temp_tank":TEAL, "power":RUST, "flow":SLATE,
            "irradiance":AMBER, "wind":SLATE, "temp_difference":TEXT,
        }
        colors = [colors_map.get(s, MUTED) for s in sensors]
        ylabels = {"Temperaturer":"°C","Effekt & flöde":"kW / m³/h",
                   "Sol & miljö":"W/m² / m/s","ΔT-analys":"°C"}

        st.plotly_chart(
            linechart(df_hist, sensors, colors, ylabels[view], height=400),
            use_container_width=True,
        )

        st.markdown('<div class="section-title">Sammanfattning</div>', unsafe_allow_html=True)
        pivot = df_hist[df_hist["sensor"].isin(sensors)] \
            .groupby("sensor")["value"].agg(["min","max","mean"]).round(2).reset_index()
        pivot.columns = ["Sensor","Min","Max","Medel"]
        st.dataframe(pivot, use_container_width=True, hide_index=True)

        energy_period = integrate_power(df_hist)
        if energy_period is not None:
            st.markdown('<div class="section-title">Energi för perioden</div>',
                        unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            col1.metric("Energi idag (trapets-integration)", f"{energy_period:.3f} kWh")
            col2.metric("Värmeenergisensor (total)",
                        fmt(latest_val(df_hist,"heat_energy"), 3, "kWh"))

        with st.expander("📥 Rådata & export"):
            pivot2 = df_hist.pivot_table(
                index="created_at", columns="sensor", values="value", aggfunc="last"
            ).reset_index().sort_values("created_at", ascending=False)
            st.dataframe(pivot2.head(500), use_container_width=True)
            st.download_button("⬇️ Ladda ner CSV", df_hist.to_csv(index=False),
                file_name=f"helixis_{hours}h.csv", mime="text/csv")

# ════════════════════════════════════════════════════════════════
# SMHI & ANALYS TAB
# ════════════════════════════════════════════════════════════════
with tab_smhi:
    st.markdown(f"""
<div style='font-size:.8rem;color:{MUTED};margin-bottom:12px'>
SMHI öppen data · Närmaste stationer: <b>Ängelholm</b> (temp/vind) &
<b>Lund</b> (globalstrålning) · Plats: Eket, Örkelljunga 56.248°N 13.192°E
</div>""", unsafe_allow_html=True)

    with st.spinner("Hämtar SMHI-data…"):
        smhi = fetch_smhi_all()

    # Show SMHI current values
    smhi_tiles = []
    labels_units = {
        "temperature":  ("Lufttemperatur (SMHI)",  "°C",   -20, 40,  SLATE,  1),
        "wind_speed":   ("Vindhastighet (SMHI)",   "m/s",  0,   25,  SLATE,  1),
        "irradiance":   ("Globalstrålning (SMHI)", "W/m²", 0,   1350,AMBER,  0),
        "cloud_cover":  ("Molnighet (SMHI)",       "okta", 0,   8,   MUTED,  0),
    }
    smhi_latest = {}
    for key, (label, unit, mn, mx, color, dec) in labels_units.items():
        df_s = smhi.get(key)
        val  = float(df_s["value"].iloc[-1]) if df_s is not None and not df_s.empty else None
        smhi_latest[key] = val
        smhi_tiles.append((label, val, unit, mn, mx, color, dec, None))

    st.markdown('<div class="section-title">SMHI just nu</div>', unsafe_allow_html=True)
    render_tiles(smhi_tiles)

    # Comparison: sensor irradiance vs SMHI irradiance
    st.markdown('<div class="section-title">Solinstrålning — sensor vs SMHI (Lund)</div>',
                unsafe_allow_html=True)

    hours_smhi = st.selectbox("Jämförelseperiod", [6, 12, 24, 48], index=1,
                               format_func=lambda h: f"{h}h", key="smhi_hours")
    df_cmp = fetch_history(hours_smhi)

    fig_cmp = go.Figure()
    if not df_cmp.empty:
        sub_irr = df_cmp[df_cmp["sensor"] == "irradiance"]
        if not sub_irr.empty:
            fig_cmp.add_trace(go.Scatter(
                x=sub_irr["created_at"], y=sub_irr["value"],
                name="Sensor (på plats)", mode="lines",
                line=dict(color=AMBER, width=2),
            ))
    smhi_irr = smhi.get("irradiance")
    if smhi_irr is not None:
        # Filter to same time window
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_smhi)
        smhi_irr_w = smhi_irr[smhi_irr["created_at"] >= since_dt]
        if not smhi_irr_w.empty:
            fig_cmp.add_trace(go.Scatter(
                x=smhi_irr_w["created_at"], y=smhi_irr_w["value"],
                name="SMHI Lund (referens)", mode="lines",
                line=dict(color=SLATE, width=1.5, dash="dot"),
            ))
    fig_cmp.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="W/m²", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color=MUTED, family="Inter")),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, family="Inter"),
    )
    fig_cmp.update_xaxes(showgrid=False, color=MUTED)
    fig_cmp.update_yaxes(gridcolor=BORDER, color=MUTED)
    st.plotly_chart(fig_cmp, use_container_width=True)

    # Effekt vs molnighet
    st.markdown('<div class="section-title">Termisk effekt vs molnighet (SMHI)</div>',
                unsafe_allow_html=True)
    fig_clouds = go.Figure()
    if not df_cmp.empty:
        sub_pwr = df_cmp[df_cmp["sensor"] == "power"]
        if not sub_pwr.empty:
            fig_clouds.add_trace(go.Scatter(
                x=sub_pwr["created_at"], y=sub_pwr["value"],
                name="Termisk effekt (kW)", mode="lines",
                line=dict(color=RUST, width=2), yaxis="y",
            ))
    smhi_cloud = smhi.get("cloud_cover")
    if smhi_cloud is not None:
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_smhi)
        smhi_cloud_w = smhi_cloud[smhi_cloud["created_at"] >= since_dt]
        if not smhi_cloud_w.empty:
            fig_clouds.add_trace(go.Scatter(
                x=smhi_cloud_w["created_at"], y=smhi_cloud_w["value"],
                name="Molnighet okta (SMHI)", mode="lines+markers",
                line=dict(color="#A0A8C8", width=1.5, dash="dot"),
                marker=dict(size=4), yaxis="y2",
            ))
    fig_clouds.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title="kW", color=RUST, gridcolor=BORDER),
        yaxis2=dict(title="okta (0–8)", color=SLATE, overlaying="y",
                    side="right", range=[0, 8]),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color=MUTED, family="Inter")),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, family="Inter"),
    )
    fig_clouds.update_xaxes(showgrid=False, color=MUTED)
    st.plotly_chart(fig_clouds, use_container_width=True)

    st.markdown(f"""
<div style='font-size:.72rem;color:{MUTED};margin-top:8px'>
Källa: SMHI Öppna data (CC BY) · Ängelholm station 63600 · Lund station 53430 ·
Data fördröjd ~1h
</div>""", unsafe_allow_html=True)

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
Max temp: 160°C · Max pressure: 6 bar<br><br>
<b style='color:{TEXT}'>Plats</b><br>
Eket, Örkelljunga<br>
56.248°N 13.192°E
</div>""", unsafe_allow_html=True)
