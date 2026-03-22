"""
streamlit_app.py — Helixis LC Monitor
Tabs: Live (gauges) | Historik | SMHI & Analys
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os, requests

st.set_page_config(page_title="Helixis LC Monitor", page_icon="🌀",
                   layout="wide", initial_sidebar_state="collapsed")

SWE    = ZoneInfo("Europe/Stockholm")
BG     = "#FFFFFF"; BG2 = "#F5F6FA"; BORDER = "#DDE0EB"
TEXT   = "#1C2033"; MUTED = "#8A90A8"; BLUE = "#1F4FE0"
TEAL   = "#167A5E"; AMBER = "#B87200"; RUST = "#A83030"; SLATE = "#2E5EA0"
LGRAY  = "#E4E7F0"
SITE_LAT, SITE_LON = 56.248, 13.192

LANG = {
    "en": {
        "live":"Live","history":"History","smhi":"SMHI","about":"About",
        "energy":"Energy","energy_today":"Energy today","heat_total":"Heat energy (total)",
        "delta_t":"ΔT Fwd−Ret",
        "collector_r":"Collector R","collector_l":"Collector L",
        "forward":"Forward","return":"Return","tank":"Tank",
        "flow":"Flow","power":"Thermal power","irradiance":"Solar irradiance",
        "pressure":"System pressure","wind":"Wind speed",
        "recv_r":"Receiver tube right","recv_l":"Receiver tube left",
        "max_power":"Max 9.2 kW @ 1000 W/m²","op_range":"Operating range 0–6 bar",
        "near_max":"⚠ Near max 6 bar","htf":"Heat-transfer fluid",
        "temperatures":"Temperatures","flow_env":"Flow, Power & Environment",
        "clear":"Clear sunshine","sunny":"Sunny","partly":"Partly cloudy",
        "cloudy":"Cloudy","overcast":"Overcast","night":"Night / no sun",
        "recv_r_sub":"Receiver tube right","recv_l_sub":"Receiver tube left",
        "fwd_sub":"Forward pipe","ret_sub":"Return pipe","tank_sub":"Storage tank",
        "htf_sub":"Heat-transfer fluid","max_power_sub":"Max 9.2 kW @ 1000 W/m²",
        "op_range_sub":"Operating range 0–6 bar","near_max_sub":"⚠ Near max 6 bar",
        "irr_excellent":"Excellent","irr_moderate":"Moderate","irr_low":"Low / night",
        "section_flow":"Flow, Power & Environment","display_mode":"Display mode",
        "no_data":"No data received.",
        "section_solar":"Solar, Power & Weather",
        "section_temps_pressure":"Temperatures & System pressure",
        "section_dt_flow":"ΔT & Flow","section_summary":"Summary for period",
        "section_energy":"Energy","energy_today_trap":"Energy today (trapezoid)",
        "heat_sensor_total":"Heat energy sensor (total)",
        "pressure_lbl":"Pressure (bar)","flow_lbl":"Flow (m³/h)",
        "power_lbl":"Thermal power (kW)","irr_lbl":"Irradiance (W/m²)","wind_lbl":"Wind (m/s)",
        "trap_help":"Calculated via trapezoid integration. ΔE=(P₁+P₂)/2×Δt — more accurate than sensor.",
        "heat_help":"Accumulated from energy sensor since last reset.",
        "loading_hist":"Loading history…","no_data_interval":"No data for selected interval.",
        "raw_export":"Raw data & export","download_csv":"Download CSV",
        "analysis_period":"Analysis period",
        "loading_smhi":"Loading SMHI station data…","loading_strang":"Loading STRÅNG model data…",
    },
    "sv": {
        "live":"Live","history":"Historik","smhi":"SMHI","about":"Om",
        "energy":"Energi","energy_today":"Energi idag","heat_total":"Värmeenergi (total)",
        "delta_t":"ΔT Fwd−Ret",
        "collector_r":"Collector R","collector_l":"Collector L",
        "forward":"Framledning","return":"Retur","tank":"Tank",
        "flow":"Flöde","power":"Termisk effekt","irradiance":"Solinstrålning",
        "pressure":"Systemtryck","wind":"Vindhastighet",
        "recv_r":"Mottagarrör höger","recv_l":"Mottagarrör vänster",
        "max_power":"Max 9.2 kW @ 1000 W/m²","op_range":"Driftområde 0–6 bar",
        "near_max":"⚠ Nära max 6 bar","htf":"Värmevätskeflöde",
        "temperatures":"Temperaturer","flow_env":"Flöde, Effekt & Miljö",
        "clear":"Klarsolsken","sunny":"Soligt","partly":"Halvklart",
        "cloudy":"Molnigt","overcast":"Mulet","night":"Natt / ingen sol",
        "recv_r_sub":"Mottagarrör höger","recv_l_sub":"Mottagarrör vänster",
        "fwd_sub":"Framledning","ret_sub":"Retur","tank_sub":"Lagertank",
        "htf_sub":"Värmevätskeflöde","max_power_sub":"Max 9.2 kW @ 1000 W/m²",
        "op_range_sub":"Driftområde 0–6 bar","near_max_sub":"⚠ Nära max 6 bar",
        "irr_excellent":"Utmärkt","irr_moderate":"Måttlig","irr_low":"Låg / natt",
        "section_flow":"Flöde, Effekt & Miljö","display_mode":"Visningsläge",
        "no_data":"Ingen data mottagen.",
        "section_solar":"Sol, Effekt & Väder",
        "section_temps_pressure":"Temperaturer & Systemtryck",
        "section_dt_flow":"ΔT & Flöde","section_summary":"Sammanfattning för perioden",
        "section_energy":"Energi","energy_today_trap":"Energi idag (trapets)",
        "heat_sensor_total":"Värmeenergisensor (total)",
        "pressure_lbl":"Tryck (bar)","flow_lbl":"Flöde (m³/h)",
        "power_lbl":"Termisk effekt (kW)","irr_lbl":"Instrålning (W/m²)","wind_lbl":"Vind (m/s)",
        "trap_help":"Beräknad med trapetsintegration. ΔE=(P₁+P₂)/2×Δt — mer exakt än sensorn.",
        "heat_help":"Ackumulerat värde från energisensorn sedan senaste nollställning.",
        "loading_hist":"Hämtar historik…","no_data_interval":"Ingen data för valt intervall.",
        "raw_export":"Rådata & export","download_csv":"Ladda ner CSV",
        "analysis_period":"Analysperiod",
        "loading_smhi":"Hämtar SMHI stationsdata…","loading_strang":"Hämtar STRÅNG modelldata…",
    },
}

# SMHI stations closest to Örkelljunga
# Ängelholm 63600: temp(1), wind(4), cloudcover(16)
# Malmö 52350: global radiation(11) — closest active station with param 11
SMHI = {
    "temperature": ("1",  "63600"),
    "wind_speed":  ("4",  "63600"),
    "irradiance":  ("11", "64565"),   # Växjö Sol
    "humidity":    ("6",  "63600"),   # Relative humidity
}

st.markdown(f"""<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  header[data-testid="stHeader"]{{background:transparent!important;height:0!important;}}
  #MainMenu,footer{{visibility:hidden;}}
  html,body,[class*="css"]{{font-family:'Inter',-apple-system,sans-serif!important;background:{BG};color:{TEXT};}}
  .block-container{{padding-top:1.2rem!important;padding-bottom:1.5rem;background:{BG};max-width:1400px;}}
  .stApp{{background:{BG};}}
  section[data-testid="stSidebar"]{{background:{BG2};border-right:1px solid {BORDER};}}

  /* Metric tiles */
  div[data-testid="metric-container"]{{background:{BG2};border:1px solid {BORDER};border-radius:8px;padding:14px 18px;}}
  div[data-testid="metric-container"] label{{font-size:.72rem!important;color:{TEXT}!important;text-transform:uppercase;letter-spacing:.08em;font-weight:700!important;}}
  div[data-testid="metric-container"] [data-testid="stMetricValue"]{{color:{TEXT}!important;font-size:1.5rem!important;font-weight:700!important;}}

  /* Section titles */
  .section-title{{font-size:.68rem;font-weight:700;color:{TEXT};text-transform:uppercase;
    letter-spacing:.1em;margin:20px 0 10px;border-left:3px solid {BLUE};padding-left:10px;}}

  /* Status */
  .status-dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle;}}
  .ts-text{{font-size:.85rem;color:{TEXT};vertical-align:middle;font-weight:500;}}

  /* Tabs — compact for mobile */
  .stTabs [data-baseweb="tab-list"]{{gap:0px!important;}}
  .stTabs [data-baseweb="tab"]{{
    font-size:.78rem!important;font-weight:700!important;
    padding:6px 8px!important;white-space:nowrap;
    color:{TEXT}!important;
  }}
  .stTabs [aria-selected="true"]{{
    color:{BLUE}!important;border-bottom:2px solid {BLUE}!important;
  }}

  /* Plotly toolbar hidden */
  .modebar{{display:none!important;}}
</style>
""", unsafe_allow_html=True)

# ── DB ────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
db = get_db()

# ── Sensor data ───────────────────────────────────────────────
@st.cache_data(ttl=25)
def fetch_live() -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        res = db.table("sensor_readings").select("created_at,sensor,value") \
            .gte("created_at", since).order("created_at", desc=False).execute()
        if not res.data: return pd.DataFrame()
        df = pd.DataFrame(res.data)
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
        return df.sort_values("created_at")
    except Exception as e:
        st.error(f"DB: {e}"); return pd.DataFrame()

@st.cache_data(ttl=120)
def fetch_history(hours_back: int) -> pd.DataFrame:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    rows, psize, offset = [], 1000, 0
    try:
        while True:
            res = db.table("sensor_readings").select("created_at,sensor,value") \
                .gte("created_at", since).order("created_at", desc=False) \
                .range(offset, offset+psize-1).execute()
            batch = res.data
            if not batch: break
            rows.extend(batch)
            if len(batch) < psize: break
            offset += psize
    except Exception as e:
        st.error(f"DB: {e}"); return pd.DataFrame()
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df.sort_values("created_at")

@st.cache_data(ttl=60)
def fetch_today_power() -> pd.DataFrame:
    """Fetch all power readings from midnight today — used for energy integration."""
    now_swe   = datetime.now(SWE)
    today_utc = now_swe.replace(hour=0, minute=0, second=0, microsecond=0)                        .astimezone(timezone.utc)
    rows, psize, offset = [], 1000, 0
    try:
        while True:
            res = db.table("sensor_readings")                 .select("created_at,sensor,value")                 .eq("sensor", "power")                 .gte("created_at", today_utc.isoformat())                 .order("created_at", desc=False)                 .range(offset, offset + psize - 1).execute()
            batch = res.data
            if not batch: break
            rows.extend(batch)
            if len(batch) < psize: break
            offset += psize
    except Exception:
        return pd.DataFrame()
    if not rows: return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df.sort_values("created_at")

@st.cache_data(ttl=1800)
def fetch_strang(days_back: int = 1) -> pd.DataFrame:
    """
    Fetch DNI + GHI from SMHI STRÅNG model for Örkelljunga coordinates.
    STRÅNG is a gridded radiation model — no station needed, uses lat/lon directly.
    Parameters: 116=GHI, 118=DNI, 120=diffuse
    """
    from_dt = (datetime.now(SWE) - timedelta(days=days_back)).strftime("%Y%m%d")
    to_dt   = datetime.now(SWE).strftime("%Y%m%d")
    rows = []
    for par, name in [("116", "ghi_strang"), ("118", "dni_strang")]:
        url = (f"https://strang.smhi.se/extraction/getparticular.php"
               f"?par={par}&from={from_dt}&to={to_dt}"
               f"&lat={SITE_LAT}&lon={SITE_LON}&file=csv")
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                continue
            for line in r.text.strip().splitlines():
                parts = line.split(";")
                if len(parts) < 2:
                    continue
                try:
                    ts  = pd.to_datetime(parts[0].strip(), utc=True)
                    val = float(parts[1].strip())
                    rows.append({"created_at": ts, "sensor": name, "value": val})
                except Exception:
                    continue
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("created_at")

# ── SMHI fetcher + Supabase storage ──────────────────────────
@st.cache_data(ttl=600)
def fetch_smhi_and_store() -> tuple[dict, dict]:
    """Fetch SMHI latest-day data. Returns (data_dict, error_dict)."""
    # Correct SMHI station IDs for southern Sweden
    # Parameter docs: https://opendata.smhi.se/apidocs/metobs/parameter.html
    SMHI_PARAMS = {
        "temperature": ("1",  "62040"),   # Helsingborg lufttemperatur
        "wind_speed":  ("4",  "62040"),   # Helsingborg vindhastighet
        "irradiance":  ("11", "64565"),   # Växjö Sol — globalstrålning (~60km)
        "humidity":    ("6",  "62040"),   # Helsingborg luftfuktighet
    }
    result, errors = {}, {}
    for key, (param, station) in SMHI_PARAMS.items():
        url = (f"https://opendata-download-metobs.smhi.se/api/version/latest"
               f"/parameter/{param}/station/{station}/period/latest-day/data.json")
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                errors[key] = f"HTTP {r.status_code} · station {station} · param {param}"
                result[key] = None
                continue
            data = r.json()
            rows = []
            for entry in data.get("value", []):
                try:
                    ts  = pd.to_datetime(entry["date"], unit="ms", utc=True)
                    val = float(entry["value"])
                    rows.append({"created_at": ts, "value": val})
                except Exception:
                    continue
            if not rows:
                errors[key] = "Inga värden i API-svaret"
                result[key] = None
                continue
            df = pd.DataFrame(rows).sort_values("created_at")
            result[key] = df
            # Store in Supabase
            try:
                to_insert = [
                    {"created_at": row["created_at"].isoformat(),
                     "sensor": f"smhi_{key}", "value": row["value"]}
                    for _, row in df.iterrows()
                ]
                db.table("smhi_readings").upsert(
                    to_insert, on_conflict="created_at,sensor"
                ).execute()
            except Exception:
                pass
        except requests.exceptions.ConnectionError as e:
            errors[key] = f"Nätverksfel: {e}"
            result[key] = None
        except Exception as e:
            errors[key] = str(e)
            result[key] = None
    return result, errors

@st.cache_data(ttl=300)
def fetch_smhi_history(hours_back: int) -> pd.DataFrame:
    """Read stored SMHI data from Supabase for historical charts."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    try:
        res = db.table("smhi_readings").select("created_at,sensor,value") \
            .gte("created_at", since).order("created_at", desc=False).execute()
        if not res.data: return pd.DataFrame()
        df = pd.DataFrame(res.data)
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
        return df
    except Exception:
        return pd.DataFrame()

# ── Helpers ───────────────────────────────────────────────────
def latest_val(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def fmt(val, decimals=1, unit=""):
    return f"{val:.{decimals}f} {unit}".strip() if val is not None else "—"

def mwh_to_kwh(val):
    """Convert heat_energy sensor (MWh) to kWh for display."""
    return val * 1000 if val is not None else None

def metric_tile(label, val, unit, mn, mx, color, decimals=1, warn=None):
    display = fmt(val, decimals, unit)
    pct = 0
    if val is not None and mx > mn:
        pct = max(0, min(100, round((val - mn) / (mx - mn) * 100)))
    warn_html = (f"<span style='color:{RUST};font-size:.7rem;margin-left:6px'>⚠</span>"
                 if warn and val is not None and val >= warn else "")
    return f"""
<div style='background:{BG2};border-radius:8px;padding:12px 14px;height:100%'>
  <div style='font-size:.68rem;font-weight:600;color:{TEXT};text-transform:uppercase;
              letter-spacing:.08em;margin-bottom:4px'>{label}</div>
  <div style='font-size:1.25rem;font-weight:700;color:{color};line-height:1.1'>
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

def sky_condition(irr, T):
    if irr is None:    return "—",           "❓", MUTED
    if irr >= 850:     return T["clear"],    "☀️",  AMBER
    if irr >= 600:     return T["sunny"],    "🌤",  AMBER
    if irr >= 350:     return T["partly"],   "⛅",  SLATE
    if irr >= 100:     return T["cloudy"],   "🌥",  MUTED
    if irr >= 20:      return T["overcast"], "☁️",  MUTED
    return                    T["night"],    "🌙",  MUTED

def integrate_power(df) -> float | None:
    """Trapezoid integration of power → kWh. Pass a pre-filtered DataFrame."""
    sub = df[df["sensor"] == "power"].sort_values("created_at") if "sensor" in df.columns else df.sort_values("created_at")
    if len(sub) < 2: return None
    times = sub["created_at"].astype("int64").values / 1e9 / 3600
    power = sub["value"].values.astype(float)
    try:
        import numpy as np
        fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
        return float(max(0.0, fn(power, times)))
    except Exception:
        total = 0.0
        for i in range(1, len(times)):
            total += (power[i] + power[i-1]) / 2 * (times[i] - times[i-1])
        return max(0.0, total)

def linechart(df, sensors, colors, ylabel, height=300, extra_traces=None):
    names = {"temp_right_coll":"Collector R","temp_left_coll":"Collector L",
             "temp_tank":"Tank","temp_forward":"Forward","temp_return":"Return",
             "temp_difference":"ΔT","power":"Power","flow":"Flow",
             "irradiance":"Irradiance","wind":"Wind","heat_energy":"Heat energy"}
    fig = go.Figure()
    for s, c in zip(sensors, colors):
        sub = df[df["sensor"]==s]
        if sub.empty: continue
        fig.add_trace(go.Scatter(x=sub["created_at"],y=sub["value"],
            name=names.get(s,s),mode="lines",line=dict(width=1.8,color=c)))
    for t in (extra_traces or []):
        fig.add_trace(t)
    fig.update_layout(height=height,margin=dict(l=0,r=0,t=10,b=0),yaxis_title=ylabel,
        legend=dict(orientation="h",yanchor="bottom",y=1.02,font=dict(size=10,color=MUTED,family="Inter")),
        hovermode="x unified",paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED,family="Inter"))
    fig.update_xaxes(showgrid=False,color=MUTED)
    fig.update_yaxes(gridcolor=BORDER,color=MUTED)
    return fig

# ── Gauge functions ───────────────────────────────────────────
def gauge_semi(label, val, mn, mx, unit, color, sub_text="", warn=None):
    """Semi-circular Plotly indicator gauge."""
    nfmt = ".0f" if unit in ("W/m²","°C") else (".2f" if unit in ("bar","m³/h") else ".1f")
    steps = [{"range":[mn, warn if warn else mx],"color":BG2}]
    if warn:
        steps.append({"range":[warn,mx],"color":"#FFF0D0"})
    threshold = ({"line":{"color":AMBER,"width":2},"thickness":0.75,"value":warn}
                 if warn else None)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val if val is not None else mn,
        number={"suffix":f" {unit}","font":{"size":18,"color":color,"family":"Inter"},
                "valueformat":nfmt},
        gauge={
            "axis":{"range":[mn,mx],"tickfont":{"size":8,"color":MUTED,"family":"Inter"},
                    "tickcolor":BORDER,"nticks":5},
            "bar":{"color":color,"thickness":0.28},
            "bgcolor":BG2,"borderwidth":1,"bordercolor":BORDER,
            "steps":steps,
            **({"threshold":threshold} if threshold else {}),
        },
        title={"text":(f"<span style='font-weight:600;font-size:12px;color:{TEXT}'>{label}</span>"
                       f"<br><span style='font-size:10px;color:{MUTED}'>{sub_text}</span>"),
               "font":{"size":12,"family":"Inter"}},
    ))
    fig.update_layout(height=200,margin=dict(l=20,r=20,t=70,b=8),
                      paper_bgcolor="rgba(0,0,0,0)")
    return fig

def gauge_thermo(label, val, mn, mx, color):
    """Vertical thermometer bar chart."""
    display = val if val is not None else mn
    mid = round((mn+mx)/2)
    fill_h = max(0.5, display-mn)
    val_y  = min(display+(mx-mn)*0.12, mx-(mx-mn)*0.08)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[0],y=[mx-mn],base=mn,
        marker_color=LGRAY,marker_line=dict(color=BORDER,width=1),
        width=0.5,showlegend=False,hoverinfo="skip"))
    fig.add_trace(go.Bar(x=[0],y=[fill_h],base=mn,
        marker_color=color,width=0.5,showlegend=False,
        hovertemplate=f"<b>{display:.1f}°C</b><extra></extra>"))
    fig.add_shape(type="circle",x0=-0.32,x1=0.32,y0=mn-7,y1=mn+7,
        fillcolor=color,line_color=color)
    fig.add_annotation(x=0,y=val_y,text=f"<b>{display:.1f}°</b>",
        font=dict(size=11,color=color,family="Inter"),
        showarrow=False,xanchor="center",yanchor="bottom")
    fig.update_layout(
        height=200,barmode="overlay",margin=dict(l=30,r=8,t=8,b=8),
        title=dict(text=f"<b>{label}</b>",font=dict(size=10,color=TEXT,family="Inter"),x=0.5),
        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(range=[mn-10,mx],gridcolor=BORDER,color=MUTED,
                   tickfont=dict(size=8,family="Inter"),
                   tickvals=[mn,mid,mx],ticktext=[f"{mn}°",f"{mid}°",f"{mx}°"]),
        xaxis=dict(showticklabels=False,showgrid=False,zeroline=False),
        showlegend=False)
    return fig

# ── Header ────────────────────────────────────────────────────
hcols = st.columns([3, 3])
with hcols[0]:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=160)
    else:
        st.markdown(f"<div style='font-size:1.4rem;font-weight:800;color:{TEXT}'>HELIXIS</div>",
                    unsafe_allow_html=True)

st.markdown(f"<hr style='border:none;border-top:1px solid {BORDER};margin:6px 0 4px'>",
            unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────
lang = st.sidebar.radio("Language / Språk", ["English", "Svenska"],
                        horizontal=True, label_visibility="collapsed")
lang = "en" if lang == "English" else "sv"
T = LANG[lang]

tab_live, tab_hist, tab_smhi, tab_om = st.tabs([
    f"🔴 {T['live']}", f"📈 {T['history']}", f"🌤 {T['smhi']}", f"ℹ️ {T['about']}"
])

# ════════════════════════════════════════════════════════════════
# LIVE TAB
# ════════════════════════════════════════════════════════════════
with tab_live:

    view_mode = st.radio(T["display_mode"], ["🎯 Gauges", "📋 Kompakt"],
                         horizontal=True, label_visibility="collapsed")

    @st.fragment(run_every=30)
    def live_dashboard():
        df = fetch_live()
        if df.empty:
            st.warning(T["no_data"]); return

        v        = {s: latest_val(df,s) for s in df["sensor"].unique()}
        last_ts  = df["created_at"].max()
        age_min  = (datetime.now(timezone.utc)-last_ts).total_seconds()/60
        is_live  = age_min < 15
        last_swe = last_ts.astimezone(SWE)
        irr, pres = v.get("irradiance"), v.get("pressure")
        irr_color = AMBER if (irr and irr>700) else (SLATE if (irr and irr>200) else MUTED)
        pcolor    = RUST if (pres and pres>=5) else SLATE

        dot = TEAL if is_live else RUST
        st.markdown(
            f'<span class="status-dot" style="background:{dot}"></span>'
            f'<span class="ts-text">{last_swe.strftime("%H:%M:%S")} '
            f'{"· LIVE" if is_live else f"· {age_min:.0f} min sedan"}</span>',
            unsafe_allow_html=True)

        df_today_pwr  = fetch_today_power()
        energy_today  = integrate_power(df_today_pwr)

        sky_label, sky_icon, sky_color = sky_condition(irr, T)
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin:6px 0 10px'>"
            f"<span style='font-size:1.8rem;line-height:1'>{sky_icon}</span>"
            f"<span style='font-size:1.05rem;font-weight:600;color:{sky_color}'>{sky_label}</span>"
            f"<span style='font-size:.8rem;color:{MUTED};margin-left:4px'>"
            f"{'· ' + fmt(irr, 0, 'W/m²') if irr is not None else ''}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        if view_mode == "🎯 Gauges":
            # ── Temperatures (semi gauges) ──
            st.markdown(f'<div class="section-title">{T["temperatures"]}</div>',
                        unsafe_allow_html=True)
            tc = st.columns(5)
            for col, (lbl_key, sensor, color, mn, mx, sub_key) in zip(tc, [
                ("collector_r", "temp_right_coll", RUST,  20, 160, "recv_r_sub"),
                ("collector_l", "temp_left_coll",  AMBER, 20, 160, "recv_l_sub"),
                ("forward",     "temp_forward",    RUST,  20, 120, "fwd_sub"),
                ("return",      "temp_return",     SLATE, 10, 100, "ret_sub"),
                ("tank",        "temp_tank",       TEAL,  10, 100, "tank_sub"),
            ]):
                col.plotly_chart(
                    gauge_semi(T[lbl_key], v.get(sensor), mn, mx, "°C", color, T[sub_key]),
                    use_container_width=True, config={"displayModeBar": False})

            # ── Flow, Power, Irradiance, Pressure (semi gauges) ──
            st.markdown(f'<div class="section-title">{T["section_flow"]}</div>',
                        unsafe_allow_html=True)
            g1,g2,g3,g4 = st.columns(4)
            with g1:
                st.plotly_chart(gauge_semi(T["flow"],v.get("flow"),0,1,"m³/h",SLATE,
                    T["htf_sub"]),use_container_width=True,config={"displayModeBar":False})
            with g2:
                st.plotly_chart(gauge_semi(T["power"],v.get("power"),0,9.2,"kW",RUST,
                    T["max_power_sub"]),use_container_width=True,config={"displayModeBar":False})
            with g3:
                irr_sub = (T["irr_excellent"] if (irr and irr>700) else
                           T["irr_moderate"]  if (irr and irr>200) else T["irr_low"])
                st.plotly_chart(gauge_semi(T["irradiance"],irr,0,1350,"W/m²",irr_color,
                    f"{irr_sub} · max ~1350 W/m²"),use_container_width=True,config={"displayModeBar":False})
            with g4:
                psub = T["near_max_sub"] if (pres and pres>=5) else T["op_range_sub"]
                st.plotly_chart(gauge_semi(T["pressure"],pres,0,6,"bar",pcolor,
                    psub,warn=5),use_container_width=True,config={"displayModeBar":False})

            # ── Energy (HTML tiles) ──
            st.markdown(f'<div class="section-title">{T["energy"]}</div>',
                        unsafe_allow_html=True)
            render_tiles([
                (T["energy_today"], energy_today,             "kWh", 0, 30,   TEAL, 3, None),
                (T["heat_total"],   mwh_to_kwh(v.get("heat_energy")), "kWh", 0, 9999, BLUE, 3, None),
                (T["delta_t"],      v.get("temp_difference"), "°C",  0, 50,   BLUE, 2, None),
            ])

        else:
            # ── Compact tile view ──
            def tile(label,val,unit,mn,mx,color,dec=1,warn=None):
                display = fmt(val,dec,unit)
                pct = max(0,min(100,round((val-mn)/(mx-mn)*100))) if val is not None and mx>mn else 0
                wh = f"<span style='color:{RUST};font-size:.7rem;margin-left:4px'>⚠</span>" \
                     if warn and val and val>=warn else ""
                return f"""<div style='background:{BG2};border-radius:8px;padding:12px 14px'>
  <div style='font-size:.65rem;font-weight:500;color:{MUTED};text-transform:uppercase;
    letter-spacing:.08em;margin-bottom:4px'>{label}</div>
  <div style='font-size:1.2rem;font-weight:600;color:{color}'>{display}{wh}</div>
  <div style='height:3px;border-radius:2px;background:{BORDER};margin-top:7px'>
    <div style='height:100%;width:{pct}%;background:{color};border-radius:2px'></div>
  </div></div>"""

            st.markdown(f'<div class="section-title">{T["temperatures"]}</div>', unsafe_allow_html=True)
            cols = st.columns(5)
            for col,(lbl,s,col_,mn,mx) in zip(cols,[
                ("Collector R","temp_right_coll",RUST,20,160),
                ("Collector L","temp_left_coll",AMBER,20,160),
                ("Forward","temp_forward",RUST,20,120),
                ("Return","temp_return",SLATE,10,100),
                ("Tank","temp_tank",TEAL,10,100)]):
                col.markdown(tile(lbl,v.get(s),"°C",mn,mx,col_,1),unsafe_allow_html=True)

            st.markdown(f'<div class="section-title">{T["section_flow"]}</div>',
                        unsafe_allow_html=True)
            cols2 = st.columns(6)
            for col,(lbl,s,u,mn,mx,col_,dec,warn) in zip(cols2,[
                (T["flow"],"flow","m³/h",0,1,SLATE,3,None),
                (T["power"],"power","kW",0,9.2,RUST,2,None),
                (T["irradiance"],"irradiance","W/m²",0,1350,irr_color,0,None),
                (T["pressure"],"pressure","bar",0,6,pcolor,2,5.0),
                (T["wind"],"wind","m/s",0,20,SLATE,2,None),
                ("ΔT","temp_difference","°C",0,50,BLUE,2,None)]):
                col.markdown(tile(lbl,v.get(s),u,mn,mx,col_,dec,warn),unsafe_allow_html=True)

            st.markdown(f'<div class="section-title">{T["section_energy"]}</div>', unsafe_allow_html=True)
            e1,e2 = st.columns(2)
            e1.metric(T["energy_today_trap"], fmt(energy_today,3,"kWh"))
            e2.metric(T["heat_sensor_total"], fmt(mwh_to_kwh(v.get("heat_energy")),3,"kWh"))

    live_dashboard()

# ════════════════════════════════════════════════════════════════
# HISTORIK TAB
# ════════════════════════════════════════════════════════════════
with tab_hist:
    # ── Tidsintervall ─────────────────────────────────────────
    hours = st.selectbox("Tidsintervall",
        [1, 6, 12, 24, 48, 168], index=3,
        format_func=lambda h: f"{h}h" if h < 24 else
            (f"{h//24} dag" if h//24 == 1 else f"{h//24} dagar"))

    with st.spinner(T["loading_hist"]):
        df_hist = fetch_history(hours)

    if df_hist.empty:
        st.warning(T["no_data_interval"])
    else:
        cmap = {
            "temp_right_coll": RUST,  "temp_left_coll": AMBER,
            "temp_forward":    RUST,  "temp_return":    SLATE,
            "temp_tank":       TEAL,  "power":          RUST,
            "flow":            SLATE, "irradiance":     AMBER,
            "wind":            SLATE, "temp_difference": TEXT,
        }

        # ── 1. Sol, Effekt & Väder (kombinerad graf med dubbel y-axel) ──
        st.markdown('<div class="section-title">Sol, Effekt & Väder</div>',
                    unsafe_allow_html=True)
        fig_solar = go.Figure()
        # Vänster axel: instrålning W/m²
        # Höger axel: effekt kW och vind m/s (liknande skala 0-10)
        for sensor, color, name, yaxis, dash in [
            ("irradiance", AMBER, T["irr_lbl"],  "y",  "solid"),
            ("power",      RUST,  T["power_lbl"], "y2", "solid"),
            ("wind",       SLATE, T["wind_lbl"],         "y2", "dot"),
        ]:
            sub = df_hist[df_hist["sensor"] == sensor]
            if not sub.empty:
                fig_solar.add_trace(go.Scatter(
                    x=sub["created_at"], y=sub["value"],
                    name=name, mode="lines",
                    line=dict(width=1.8, color=color, dash=dash),
                    yaxis=yaxis,
                ))
        fig_solar.update_layout(
            height=320, margin=dict(l=0, r=50, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="W/m²", font=dict(color=AMBER)),
                       tickfont=dict(color=AMBER), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="kW / m/s", font=dict(color=RUST)),
                        tickfont=dict(color=RUST), overlaying="y", side="right",
                        showgrid=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_solar.update_xaxes(showgrid=False, color=MUTED)
        st.plotly_chart(fig_solar, use_container_width=True)

        # ── 2. Temperaturer & Tryck ──────────────────────────
        st.markdown('<div class="section-title">Temperaturer & Systemtryck</div>',
                    unsafe_allow_html=True)
        temp_sensors = ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"]
        fig_temp = go.Figure()
        for s in temp_sensors:
            sub = df_hist[df_hist["sensor"] == s]
            if not sub.empty:
                names_map = {"temp_right_coll":"Collector R","temp_left_coll":"Collector L",
                             "temp_forward":"Forward","temp_return":"Return","temp_tank":"Tank"}
                fig_temp.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
                    name=names_map[s], mode="lines",
                    line=dict(width=1.8, color=cmap[s]), yaxis="y"))
        sub_p = df_hist[df_hist["sensor"] == "pressure"]
        if not sub_p.empty:
            fig_temp.add_trace(go.Scatter(x=sub_p["created_at"], y=sub_p["value"],
                name=T["pressure_lbl"], mode="lines",
                line=dict(width=1.5, color=SLATE, dash="dot"), yaxis="y2"))
        fig_temp.update_layout(
            height=320, margin=dict(l=0, r=50, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                       tickfont=dict(color=TEXT), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="bar", font=dict(color=SLATE)),
                        tickfont=dict(color=SLATE), overlaying="y", side="right",
                        showgrid=False, range=[0, 8]),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_temp.update_xaxes(showgrid=False, color=MUTED)
        st.plotly_chart(fig_temp, use_container_width=True)

        # ── 3. ΔT & Flöde ─────────────────────────────────────
        st.markdown('<div class="section-title">ΔT & Flöde</div>',
                    unsafe_allow_html=True)
        fig_dt = go.Figure()
        for sensor, color, name, yaxis in [
            ("temp_difference", TEXT,  "ΔT (°C)",    "y"),
            ("flow",            SLATE, T["flow_lbl"], "y2"),
        ]:
            sub = df_hist[df_hist["sensor"] == sensor]
            if not sub.empty:
                fig_dt.add_trace(go.Scatter(
                    x=sub["created_at"], y=sub["value"],
                    name=name, mode="lines",
                    line=dict(width=1.8, color=color),
                    yaxis=yaxis,
                ))
        fig_dt.update_layout(
            height=260, margin=dict(l=0, r=50, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                       tickfont=dict(color=TEXT), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="m³/h", font=dict(color=SLATE)),
                        tickfont=dict(color=SLATE), overlaying="y", side="right",
                        showgrid=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_dt.update_xaxes(showgrid=False, color=MUTED)
        st.plotly_chart(fig_dt, use_container_width=True)

        # ── 4. Sammanfattning & Energi ────────────────────────
        st.markdown('<div class="section-title">Sammanfattning för perioden</div>',
                    unsafe_allow_html=True)
        all_sensors = temp_sensors + ["power","flow","irradiance","wind","pressure","temp_difference"]
        piv = df_hist[df_hist["sensor"].isin(all_sensors)] \
            .groupby("sensor")["value"].agg(["min","max","mean"]).round(2).reset_index()
        piv.columns = ["Sensor","Min","Max","Medel"]
        sensor_order = all_sensors
        piv["_ord"] = piv["Sensor"].apply(lambda s: sensor_order.index(s)
                                           if s in sensor_order else 99)
        st.dataframe(piv.sort_values("_ord").drop(columns="_ord"),
                     use_container_width=True, hide_index=True)

        # Energy today always uses full-day data — same source as Live tab
        ep_today = integrate_power(fetch_today_power())
        ep_window = integrate_power(df_hist)   # energy in selected window only

        st.markdown(f'<div class="section-title">{T["section_energy"]}</div>', unsafe_allow_html=True)
        ec1, ec2, ec3 = st.columns(3)
        ec1.metric(T["energy_today_trap"], fmt(ep_today, 3, "kWh"),
            help=T["trap_help"])
        ec2.metric(f"{T['energy_today_trap']} ({T['history']} window)",
            fmt(ep_window, 3, "kWh"),
            help="Energy in the selected history window only (not necessarily from midnight).")
        ec2.metric(T["heat_sensor_total"],
                   fmt(mwh_to_kwh(latest_val(df_hist,"heat_energy")), 3, "kWh"),
                   help=T["heat_help"])

        # ── Energikonvergensanalys ────────────────────────────
        st.markdown('<div class="section-title">Energy meter analysis — kWh or MWh?</div>',
                    unsafe_allow_html=True)

        sub_pwr = df_hist[df_hist["sensor"] == "power"].sort_values("created_at")
        sub_egy = df_hist[df_hist["sensor"] == "heat_energy"].sort_values("created_at")

        if len(sub_pwr) >= 2 and len(sub_egy) >= 2:
            # Trapezoid integral from start of window
            t0 = sub_pwr["created_at"].iloc[0]
            times = sub_pwr["created_at"].astype("int64").values / 1e9 / 3600
            power = sub_pwr["value"].values.astype(float)
            try:
                import numpy as np
                fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
                # Cumulative trapezoid
                cum_kwh = []
                for i in range(1, len(times)+1):
                    cum_kwh.append(float(max(0, fn(power[:i], times[:i]) - fn(power[:1], times[:1]))))
                cum_kwh[0] = 0.0
            except Exception:
                cum_kwh = []
                acc = 0.0
                for i in range(1, len(times)):
                    acc += (power[i]+power[i-1])/2*(times[i]-times[i-1])
                    cum_kwh.append(max(0, acc))
                cum_kwh.insert(0, 0.0)

            # Energy sensor delta from start
            e0 = float(sub_egy["value"].iloc[0])
            sub_egy_norm = sub_egy.copy()
            sub_egy_norm["delta"] = sub_egy_norm["value"] - e0

            # Best-fit scale factor: what multiplier makes energy sensor match integral?
            egy_end   = float(sub_egy["value"].iloc[-1]) - e0
            trap_end  = cum_kwh[-1] if cum_kwh else None

            if trap_end and trap_end > 0.01 and egy_end > 0:
                scale = trap_end / egy_end
                if scale > 800:
                    unit_guess = "MWh (factor ~1000)"
                    unit_color = RUST
                elif scale > 80:
                    unit_guess = "Possibly MWh or wrong calibration"
                    unit_color = AMBER
                elif 0.8 < scale < 1.2:
                    unit_guess = "kWh ✓ — matches well"
                    unit_color = TEAL
                else:
                    unit_guess = f"Unknown (scale factor: {scale:.1f}×)"
                    unit_color = MUTED

                # Summary metrics
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Trapezoid integral", f"{trap_end:.3f} kWh",
                           help="Sum of power×time from power sensor since start of window")
                mc2.metric("Energy sensor delta", f"{egy_end:.4f} units",
                           help="Change in heat_energy sensor over same period")
                mc3.metric("Scale factor", f"{scale:.1f}×",
                           help="How many times larger the integral is vs the sensor delta")
                mc4.metric("Likely unit", unit_guess)

                st.markdown(
                    f"<div style='padding:10px 14px;background:{BG2};border-radius:8px;"
                    f"border-left:3px solid {unit_color};margin:8px 0'>"
                    f"<b style='color:{unit_color}'>Conclusion:</b> "
                    f"<span style='color:{TEXT}'>Scale factor {scale:.0f}× suggests the energy sensor "
                    f"is most likely in <b>{'MWh' if scale > 200 else 'kWh' if 0.8 < scale < 1.2 else f'unknown units (×{scale:.1f})' }</b>. "
                    f"{'To display correctly, multiply sensor value by 1000.' if scale > 200 else ''}"
                    f"</span></div>",
                    unsafe_allow_html=True
                )

            # Convergence chart
            fig_conv = go.Figure()
            if cum_kwh:
                fig_conv.add_trace(go.Scatter(
                    x=sub_pwr["created_at"], y=cum_kwh,
                    name="Cumulative energy (trapezoid, kWh)",
                    mode="lines", line=dict(color=TEAL, width=2.5)))

            if not sub_egy_norm.empty and egy_end > 0 and trap_end and trap_end > 0.01:
                # Plot sensor scaled to kWh
                scale_factor = trap_end / egy_end
                fig_conv.add_trace(go.Scatter(
                    x=sub_egy_norm["created_at"],
                    y=sub_egy_norm["delta"] * scale_factor,
                    name=f"Energy sensor ×{scale_factor:.0f} (scaled to kWh)",
                    mode="lines", line=dict(color=RUST, width=1.5, dash="dot")))
                # Also raw sensor on right axis
                fig_conv.add_trace(go.Scatter(
                    x=sub_egy_norm["created_at"], y=sub_egy_norm["delta"],
                    name="Energy sensor (raw delta)",
                    mode="lines", line=dict(color=MUTED, width=1, dash="dash"),
                    yaxis="y2"))

            fig_conv.update_layout(
                height=320, margin=dict(l=0, r=50, t=10, b=0),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            font=dict(size=10, color=MUTED, family="Inter")),
                yaxis=dict(title=dict(text="kWh", font=dict(color=TEAL)),
                           tickfont=dict(color=TEAL), gridcolor=BORDER),
                yaxis2=dict(title=dict(text="sensor raw", font=dict(color=MUTED)),
                            tickfont=dict(color=MUTED), overlaying="y", side="right",
                            showgrid=False),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=MUTED, family="Inter"))
            fig_conv.update_xaxes(showgrid=False, color=MUTED)
            st.plotly_chart(fig_conv, use_container_width=True)
            st.caption("If scaled sensor (dotted red) tracks trapezoid integral (teal) well → "
                       "scale factor is correct and unit can be determined. "
                       "Perfect overlap = calibration confirmed.")
        else:
            st.info("Not enough power or energy data in selected window for convergence analysis.")

        with st.expander(f"📥 {T['raw_export']}"):
            piv2 = df_hist.pivot_table(
                index="created_at", columns="sensor",
                values="value", aggfunc="last"
            ).reset_index().sort_values("created_at", ascending=False)
            st.dataframe(piv2.head(500), use_container_width=True)
            st.download_button(f"⬇️ {T['download_csv']}", df_hist.to_csv(index=False),
                f"helixis_{hours}h.csv", "text/csv")

# ════════════════════════════════════════════════════════════════
# SMHI & ANALYS TAB
# ════════════════════════════════════════════════════════════════
with tab_smhi:

    # ── Förklaringstext ───────────────────────────────────────
    with st.expander("ℹ️ Vad gör vi med denna data?", expanded=False):
        st.markdown(f"""
### Från GHI till DNI — varför det spelar roll för Helixis

Helixis LC12 är en **linjär solfångare (CSP)** som fokuserar direkt solljus via speglar mot
ett mottagarrör. Till skillnad från plana solpaneler (som också nyttjar diffust ljus)
kräver koncentrerade system nästan uteslutande **DNI — Direct Normal Irradiance**,
dvs solstrålning som kommer *direkt* från solen längs en rak linje.

**Problemet:** DNI-mätare (pyrheliometrar) kostar 30 000–100 000 kr och kräver daglig skötsel.
Vi har istället en GHI-sensor (global horisontell instrålning) som mäter allt ljus ovanifrån.

**Lösningen — clearness index (kt):**

SMHI:s modellsystem **STRÅNG** beräknar både GHI och DNI för exakt vår koordinat
(56.248°N, 13.192°E) med en fysikalisk atmosfärmodell. Genom att jämföra:

> `kt = DNI_STRÅNG / GHI_STRÅNG`

får vi ett dimensionslöst tal 0–1 som beskriver hur "klar" himlen är.
Under molnfria dagar är kt högt (0.7–0.9). Under molniga dagar sjunker kt mot 0.

Vi kan sedan **estimera DNI på plats:**

> `DNI_estimerat = kt × GHI_sensor`

**Teoretisk maxeffekt:**

Med känd DNI och systemparametrar kan vi beräkna vad Helixis *borde* producera:

> `P_max = DNI × Apertur × η_optisk`
> `P_max = DNI × 12.35 m² × 0.65 ≈ DNI × 8.0 W per W/m²`

Skillnaden mellan `P_teoretisk` och `P_mätt` berättar om systemet jobbar optimalt —
eller om det finns förluster i form av smuts, feljustering, termiska förluster eller
pumpstörningar.

---
*Data: SMHI STRÅNG-modellen (fri, ingen nyckel) + Helsingborg station 62040 för väder.*
""")

    # ── Hämta data ────────────────────────────────────────────
    h_cmp = st.selectbox(T["analysis_period"], [6, 12, 24, 48, 168], index=2,
                          format_func=lambda h: f"{h}h" if h < 24 else
                              (f"{h//24} dag" if h//24 == 1 else f"{h//24} dagar"),
                          key="smhi_h")

    col_l, col_r = st.columns(2)
    with col_l:
        with st.spinner(T["loading_smhi"]):
            smhi_data, smhi_errors = fetch_smhi_and_store()
    with col_r:
        with st.spinner(T["loading_strang"]):
            days_back = max(1, h_cmp // 24 + 1)
            df_strang = fetch_strang(days_back)

    if smhi_errors:
        with st.expander(f"⚠️ {len(smhi_errors)} SMHI-stationskälla(or) saknas"):
            for key, msg in smhi_errors.items():
                st.warning(f"**{key}**: {msg}")

    # ── Väder just nu ─────────────────────────────────────────
    st.markdown('<div class="section-title">Weather conditions (SMHI stations)</div>',
                unsafe_allow_html=True)
    smhi_defs = {
        "temperature": ("Air temp",    "°C",  -20, 40,   SLATE, 1),
        "wind_speed":  ("Wind speed",  "m/s",   0, 25,   SLATE, 1),
        "irradiance":  ("GHI (Växjö)", "W/m²",  0, 1350, AMBER, 0),
        "humidity":    ("Humidity",    "%",      0, 100,  SLATE, 0),
    }
    tile_specs = []
    for key, (label, unit, mn, mx, color, dec) in smhi_defs.items():
        df_s = smhi_data.get(key)
        val  = float(df_s["value"].iloc[-1]) if isinstance(df_s, pd.DataFrame) and not df_s.empty else None
        tile_specs.append((label, val, unit, mn, mx, color, dec, None))
    render_tiles(tile_specs)

    # ── STRÅNG — DNI & kt-faktor ──────────────────────────────
    st.markdown('<div class="section-title">STRÅNG model — DNI & clearness index kt</div>',
                unsafe_allow_html=True)

    since_dt = datetime.now(timezone.utc) - timedelta(hours=h_cmp)
    df_cmp   = fetch_history(h_cmp)

    # Filter STRÅNG to period
    df_st = df_strang[df_strang["created_at"] >= since_dt] if not df_strang.empty else pd.DataFrame()

    # Compute kt and theoretical power
    kt_current = None
    dni_est_current = None
    p_theoretical = None

    if not df_st.empty and not df_cmp.empty:
        ghi_st  = df_st[df_st["sensor"] == "ghi_strang"][["created_at","value"]].rename(columns={"value":"ghi_m"})
        dni_st  = df_st[df_st["sensor"] == "dni_strang"][["created_at","value"]].rename(columns={"value":"dni_m"})
        merged  = pd.merge_asof(ghi_st.sort_values("created_at"),
                                dni_st.sort_values("created_at"),
                                on="created_at", tolerance=pd.Timedelta("30min"))
        merged  = merged[merged["ghi_m"] > 50].dropna()  # filter night/zeros
        if not merged.empty:
            merged["kt"] = (merged["dni_m"] / merged["ghi_m"]).clip(0, 1.2)

            # Latest kt + DNI estimate from on-site GHI sensor
            irr_live = df_cmp[df_cmp["sensor"] == "irradiance"].sort_values("created_at")
            if not irr_live.empty and not merged.empty:
                kt_current      = float(merged["kt"].iloc[-1])
                ghi_sensor_last = float(irr_live["value"].iloc[-1])
                dni_est_current = kt_current * ghi_sensor_last
                # Theoretical power: DNI × aperture × optical efficiency
                APERTURE   = 12.35   # m²
                ETA_OPT    = 0.65    # optical efficiency (peak ~0.72, realistic 0.65)
                p_theoretical = (dni_est_current * APERTURE * ETA_OPT) / 1000  # kW

            # ── kt tiles ──────────────────────────────────────
            kt_color = TEAL if kt_current and kt_current > 0.6 else (AMBER if kt_current and kt_current > 0.3 else MUTED)
            p_actual = float(df_cmp[df_cmp["sensor"]=="power"]["value"].iloc[-1])                        if not df_cmp[df_cmp["sensor"]=="power"].empty else None
            efficiency_pct = (p_actual / p_theoretical * 100) if p_theoretical and p_theoretical > 0.1 and p_actual else None

            render_tiles([
                ("Clearness index kt",    kt_current,       "",    0, 1,    kt_color, 2, None),
                ("DNI estimated",         dni_est_current,  "W/m²",0, 1000, AMBER,   0, None),
                ("Theoretical max power", p_theoretical,    "kW",  0, 9.2,  RUST,    2, None),
                ("Actual power",          p_actual,         "kW",  0, 9.2,  TEAL,    2, None),
            ])

            if efficiency_pct is not None:
                eff_color = TEAL if efficiency_pct > 75 else (AMBER if efficiency_pct > 40 else RUST)
                st.markdown(
                    f"<div style='margin:12px 0 4px;font-size:.9rem;color:{TEXT}'>"
                    f"System performance: <b style='color:{eff_color}'>{efficiency_pct:.0f}%</b> "
                    f"of theoretical maximum"
                    f"<span style='font-size:.75rem;color:{MUTED};margin-left:8px'>"
                    f"({fmt(p_actual,2,'kW')} measured vs {fmt(p_theoretical,2,'kW')} theoretical)</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )

    # ── Graf: GHI sensor vs STRÅNG GHI + DNI ──────────────────
    st.markdown('<div class="section-title">GHI sensor vs STRÅNG model (GHI & DNI)</div>',
                unsafe_allow_html=True)
    fig_rad = go.Figure()
    if not df_cmp.empty:
        sub_ghi = df_cmp[df_cmp["sensor"] == "irradiance"]
        if not sub_ghi.empty:
            fig_rad.add_trace(go.Scatter(
                x=sub_ghi["created_at"], y=sub_ghi["value"],
                name="GHI sensor (on-site)", mode="lines",
                line=dict(color=AMBER, width=2.5)))
    if not df_st.empty:
        sub_gm = df_st[df_st["sensor"] == "ghi_strang"]
        sub_dm = df_st[df_st["sensor"] == "dni_strang"]
        if not sub_gm.empty:
            fig_rad.add_trace(go.Scatter(
                x=sub_gm["created_at"], y=sub_gm["value"],
                name="GHI STRÅNG model", mode="lines",
                line=dict(color=SLATE, width=1.5, dash="dot")))
        if not sub_dm.empty:
            fig_rad.add_trace(go.Scatter(
                x=sub_dm["created_at"], y=sub_dm["value"],
                name="DNI STRÅNG model", mode="lines",
                line=dict(color=RUST, width=1.5, dash="dash")))
    fig_rad.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="W/m²",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color=MUTED, family="Inter")),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED, family="Inter"))
    fig_rad.update_xaxes(showgrid=False, color=MUTED)
    fig_rad.update_yaxes(gridcolor=BORDER, color=MUTED)
    st.plotly_chart(fig_rad, use_container_width=True)

    # ── Graf: Faktisk vs teoretisk effekt ─────────────────────
    if not df_st.empty and not df_cmp.empty and not merged.empty:
        st.markdown('<div class="section-title">Actual vs theoretical power output</div>',
                    unsafe_allow_html=True)

        # Merge sensor power with STRÅNG kt to get theoretical per timestep
        pwr_df = df_cmp[df_cmp["sensor"] == "power"][["created_at","value"]].rename(columns={"value":"power"})
        irr_df = df_cmp[df_cmp["sensor"] == "irradiance"][["created_at","value"]].rename(columns={"value":"ghi_sensor"})
        kt_df  = merged[["created_at","kt"]]

        tmp = pd.merge_asof(pwr_df.sort_values("created_at"),
                            kt_df.sort_values("created_at"),
                            on="created_at", tolerance=pd.Timedelta("1h"))
        tmp = pd.merge_asof(tmp.sort_values("created_at"),
                            irr_df.sort_values("created_at"),
                            on="created_at", tolerance=pd.Timedelta("10min"))
        tmp = tmp.dropna()
        if not tmp.empty:
            tmp["p_theoretical"] = (tmp["kt"] * tmp["ghi_sensor"] * 12.35 * 0.65 / 1000).clip(0)

            fig_pwr = go.Figure()
            fig_pwr.add_trace(go.Scatter(
                x=tmp["created_at"], y=tmp["p_theoretical"],
                name="Theoretical max (kW)", mode="lines",
                line=dict(color=SLATE, width=1.5, dash="dot"),
                fill="tozeroy", fillcolor=f"rgba(46,94,160,0.08)"))
            fig_pwr.add_trace(go.Scatter(
                x=tmp["created_at"], y=tmp["power"],
                name="Actual power (kW)", mode="lines",
                line=dict(color=RUST, width=2.5),
                fill="tozeroy", fillcolor=f"rgba(168,48,48,0.12)"))
            fig_pwr.update_layout(
                height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="kW",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            font=dict(size=10, color=MUTED, family="Inter")),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=MUTED, family="Inter"))
            fig_pwr.update_xaxes(showgrid=False, color=MUTED)
            fig_pwr.update_yaxes(gridcolor=BORDER, color=MUTED)
            st.plotly_chart(fig_pwr, use_container_width=True)
            st.caption("Gap between theoretical (dotted) and actual (red) = losses from optics, "
                       "tracking, heat exchange, and system startup. Shaded area shows energy potential.")

    # ── kt-tidsserie ──────────────────────────────────────────
    if not df_st.empty and "kt" in locals() and not merged.empty:
        st.markdown('<div class="section-title">Clearness index kt over time</div>',
                    unsafe_allow_html=True)
        fig_kt = go.Figure()
        fig_kt.add_trace(go.Scatter(
            x=merged["created_at"], y=merged["kt"],
            name="kt (DNI/GHI)", mode="lines",
            line=dict(color=TEAL, width=2),
            fill="tozeroy", fillcolor="rgba(22,122,94,0.1)"))
        fig_kt.add_hline(y=0.7, line_dash="dot", line_color=AMBER,
                         annotation_text="Clear sky threshold (kt=0.7)")
        fig_kt.update_layout(
            height=220, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title="kt", range=[0, 1.1], gridcolor=BORDER, color=MUTED),
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"))
        fig_kt.update_xaxes(showgrid=False, color=MUTED)
        st.plotly_chart(fig_kt, use_container_width=True)
        st.caption("kt > 0.7 = clear sky, direct sunlight optimal for concentrating systems. "
                   "kt < 0.3 = heavy cloud cover, DNI too low for meaningful CSP output.")

# ── Om systemet tab ──────────────────────────────────────────
with tab_om:
    c_sys, c_map = st.columns([1, 1])
    with c_sys:
        st.markdown(f"<div class='section-title'>Systemspecifikation</div>",
                    unsafe_allow_html=True)
        st.markdown(f"""<div style='font-size:.85rem;color:{MUTED};line-height:2.1'>
<b style='color:{TEXT}'>Helixis LC12 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Max temp: 160°C · Max pressure: 6 bar
</div>""", unsafe_allow_html=True)

        st.markdown(f"<div class='section-title' style='margin-top:24px'>Geografisk placering</div>",
                    unsafe_allow_html=True)
        st.markdown(f"""<div style='font-size:.85rem;color:{MUTED};line-height:2.1'>
<b style='color:{TEXT}'>Eket, Örkelljunga</b><br>
Koordinater: 56.248°N · 13.192°E<br>
Höjd ö.h.: ~130 m<br>
Region: Skåne
</div>""", unsafe_allow_html=True)

    with c_map:
        st.markdown(f"<div class='section-title'>Flygfoto — Eket</div>",
                    unsafe_allow_html=True)
        if os.path.exists("eket_aerial.png"):
            st.image("eket_aerial.png", caption="Eket, Örkelljunga · © Google Maps",
                     use_container_width=True)
        else:
            st.info("Lägg till eket_aerial.png i repot för att visa flygfoto.")

# ── Sidebar (minimal) ─────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{TEXT};font-weight:600;font-size:.9rem;margin-bottom:8px'>Helixis LC12</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:.72rem;color:{MUTED}'>Eket · Örkelljunga · 56.248°N</div>",
                unsafe_allow_html=True)
