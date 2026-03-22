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

# SMHI stations closest to Örkelljunga
# Ängelholm 63600: temp(1), wind(4), cloudcover(16)
# Lund 53430: global radiation(11)
SMHI = {
    "temperature": ("1",  "63600"),
    "wind_speed":  ("4",  "63600"),
    "irradiance":  ("11", "53430"),
    "cloud_cover": ("16", "63600"),
}

st.markdown(f"""<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  header[data-testid="stHeader"]{{background:transparent!important;height:0!important;}}
  #MainMenu,footer{{visibility:hidden;}}
  html,body,[class*="css"]{{font-family:'Inter',-apple-system,sans-serif!important;background:{BG};color:{TEXT};}}
  .block-container{{padding-top:1.2rem!important;padding-bottom:1.5rem;background:{BG};max-width:1400px;}}
  .stApp{{background:{BG};}}
  section[data-testid="stSidebar"]{{background:{BG2};border-right:1px solid {BORDER};}}
  .section-title{{font-size:.62rem;font-weight:600;color:{MUTED};text-transform:uppercase;
    letter-spacing:.12em;margin:20px 0 8px;border-left:2px solid {BLUE};padding-left:8px;}}
  .status-dot{{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle;}}
  .ts-text{{font-size:.78rem;color:{MUTED};vertical-align:middle;}}
</style>""", unsafe_allow_html=True)

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

# ── SMHI fetcher + Supabase storage ──────────────────────────
@st.cache_data(ttl=600)
def fetch_smhi_and_store() -> tuple[dict, dict]:
    """Fetch SMHI latest-day data. Returns (data_dict, error_dict)."""
    # Correct SMHI station IDs for southern Sweden
    # Parameter docs: https://opendata.smhi.se/apidocs/metobs/parameter.html
    SMHI_PARAMS = {
        "temperature": ("1",  "62040"),   # Helsingborg lufttemperatur
        "wind_speed":  ("4",  "62040"),   # Helsingborg vindhastighet
        "irradiance":  ("11", "98210"),   # Hoburg globalstrålning (closest active)
        "cloud_cover": ("16", "62040"),   # Helsingborg molnighet
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

def integrate_power(df) -> float | None:
    now_swe   = datetime.now(SWE)
    today_utc = now_swe.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
    sub = df[df["sensor"]=="power"].copy()
    sub = sub[sub["created_at"]>=today_utc].sort_values("created_at")
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
            total += (power[i]+power[i-1])/2*(times[i]-times[i-1])
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
tab_live, tab_hist, tab_smhi, tab_om = st.tabs(["🔴  Live", "📈  Historik", "🌤  SMHI & Analys", "ℹ️  Om systemet"])

# ════════════════════════════════════════════════════════════════
# LIVE TAB
# ════════════════════════════════════════════════════════════════
with tab_live:

    view_mode = st.radio("Visningsläge", ["🎯 Gauges", "📋 Kompakt"],
                         horizontal=True, label_visibility="collapsed")

    @st.fragment(run_every=30)
    def live_dashboard():
        df = fetch_live()
        if df.empty:
            st.warning("Ingen data."); return

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

        energy_today = integrate_power(df)

        if view_mode == "🎯 Gauges":
            # ── Temperatures (semi gauges) ──
            st.markdown('<div class="section-title">Temperaturer</div>',
                        unsafe_allow_html=True)
            tc = st.columns(5)
            for col, (lbl, sensor, color, mn, mx, sub_text) in zip(tc, [
                ("Collector R", "temp_right_coll", RUST,  20, 160, "Mottagarrör höger"),
                ("Collector L", "temp_left_coll",  AMBER, 20, 160, "Mottagarrör vänster"),
                ("Forward",     "temp_forward",    RUST,  20, 120, "Framledning"),
                ("Return",      "temp_return",     SLATE, 10, 100, "Retur"),
                ("Tank",        "temp_tank",       TEAL,  10, 100, "Lagertank"),
            ]):
                col.plotly_chart(
                    gauge_semi(lbl, v.get(sensor), mn, mx, "°C", color, sub_text),
                    use_container_width=True, config={"displayModeBar": False})

            # ── Flow, Power, Irradiance, Pressure (semi gauges) ──
            st.markdown('<div class="section-title">Flöde, Effekt & Miljö</div>',
                        unsafe_allow_html=True)
            g1,g2,g3,g4 = st.columns(4)
            with g1:
                st.plotly_chart(gauge_semi("Flöde",v.get("flow"),0,1,"m³/h",SLATE,
                    "Värmevätskeflöde"),use_container_width=True,config={"displayModeBar":False})
            with g2:
                st.plotly_chart(gauge_semi("Termisk effekt",v.get("power"),0,9.2,"kW",RUST,
                    "Max 9.2 kW @ 1000 W/m²"),use_container_width=True,config={"displayModeBar":False})
            with g3:
                irr_sub = ("Utmärkt" if (irr and irr>700) else
                           "Måttlig" if (irr and irr>200) else "Låg / natt")
                st.plotly_chart(gauge_semi("Solinstrålning",irr,0,1350,"W/m²",irr_color,
                    f"{irr_sub} · max ~1350 W/m²"),use_container_width=True,config={"displayModeBar":False})
            with g4:
                psub = "⚠ Nära max 6 bar" if (pres and pres>=5) else "Driftområde 0–6 bar"
                st.plotly_chart(gauge_semi("Systemtryck",pres,0,6,"bar",pcolor,
                    psub,warn=5),use_container_width=True,config={"displayModeBar":False})

            # ── Energy ──
            st.markdown('<div class="section-title">Energi</div>', unsafe_allow_html=True)
            e1,e2,e3 = st.columns(3)
            e1.metric("Energi idag", fmt(energy_today,3,"kWh"),
                      help=("Beräknad med **trapetsintegration** av effektmätaren.\n\n"
                            "**Metod:** Varje mätpunkt ger ett litet trapetsobjekt:\n"
                            "`ΔE = (P₁ + P₂) / 2 × Δt`\n\n"
                            "där `P` = effekt i kW och `Δt` = tid i timmar. "
                            "Summan av alla trapetser ger kWh från midnatt. "
                            "Mer exakt än att använda energisensorn direkt "
                            "eftersom den kan ha nollpunktsfel eller kalibreringsproblem."))
            e2.metric("Värmeenergi (total)", fmt(v.get("heat_energy"),3,"kWh"),
                      help="Ackumulerat värde direkt från energisensorn sedan senaste nollställning.")
            e3.metric("ΔT Fwd−Ret", fmt(v.get("temp_difference"),2,"°C"),
                      help="Temperaturdifferens mellan framledning och retur.")

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

            st.markdown('<div class="section-title">Temperaturer</div>', unsafe_allow_html=True)
            cols = st.columns(5)
            for col,(lbl,s,col_,mn,mx) in zip(cols,[
                ("Collector R","temp_right_coll",RUST,20,160),
                ("Collector L","temp_left_coll",AMBER,20,160),
                ("Forward","temp_forward",RUST,20,120),
                ("Return","temp_return",SLATE,10,100),
                ("Tank","temp_tank",TEAL,10,100)]):
                col.markdown(tile(lbl,v.get(s),"°C",mn,mx,col_,1),unsafe_allow_html=True)

            st.markdown('<div class="section-title">Flöde, Effekt & Miljö</div>',
                        unsafe_allow_html=True)
            cols2 = st.columns(6)
            for col,(lbl,s,u,mn,mx,col_,dec,warn) in zip(cols2,[
                ("Flöde","flow","m³/h",0,1,SLATE,3,None),
                ("Effekt","power","kW",0,9.2,RUST,2,None),
                ("Instrålning","irradiance","W/m²",0,1350,irr_color,0,None),
                ("Tryck","pressure","bar",0,6,pcolor,2,5.0),
                ("Vind","wind","m/s",0,20,SLATE,2,None),
                ("ΔT","temp_difference","°C",0,50,BLUE,2,None)]):
                col.markdown(tile(lbl,v.get(s),u,mn,mx,col_,dec,warn),unsafe_allow_html=True)

            st.markdown('<div class="section-title">Energi</div>', unsafe_allow_html=True)
            e1,e2 = st.columns(2)
            e1.metric("Energi idag (trapets)", fmt(energy_today,3,"kWh"))
            e2.metric("Värmeenergi (total)", fmt(v.get("heat_energy"),3,"kWh"))

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

    with st.spinner("Hämtar historik…"):
        df_hist = fetch_history(hours)

    if df_hist.empty:
        st.warning("Ingen data för valt intervall.")
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
            ("irradiance", AMBER, "Instrålning (W/m²)",  "y",  "solid"),
            ("power",      RUST,  "Termisk effekt (kW)", "y2", "solid"),
            ("wind",       SLATE, "Vind (m/s)",          "y2", "dot"),
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
                name="Tryck (bar)", mode="lines",
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
            ("flow",            SLATE, "Flöde (m³/h)", "y2"),
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

        ep = integrate_power(df_hist)
        if ep is not None:
            st.markdown('<div class="section-title">Energi</div>', unsafe_allow_html=True)
            ec1, ec2 = st.columns(2)
            ec1.metric("Energi idag (trapets-integration)", f"{ep:.3f} kWh",
                help=("**Trapetsintegration av effektmätaren:**\n\n"
                      "ΔE = (P₁ + P₂) / 2 × Δt (timmar)\n\n"
                      "Summerar alla mätpunkter från midnatt. "
                      "Mer exakt än energisensorn direkt — opåverkad av "
                      "nollpunktsfel eller kalibreringsproblem."))
            ec2.metric("Värmeenergisensor (total)",
                       fmt(latest_val(df_hist,"heat_energy"), 3, "kWh"))

        with st.expander("📥 Rådata & export"):
            piv2 = df_hist.pivot_table(
                index="created_at", columns="sensor",
                values="value", aggfunc="last"
            ).reset_index().sort_values("created_at", ascending=False)
            st.dataframe(piv2.head(500), use_container_width=True)
            st.download_button("⬇️ CSV", df_hist.to_csv(index=False),
                f"helixis_{hours}h.csv", "text/csv")

# ════════════════════════════════════════════════════════════════
# SMHI & ANALYS TAB
# ════════════════════════════════════════════════════════════════
with tab_smhi:
    st.markdown(f"""<div style='font-size:.8rem;color:{MUTED};margin-bottom:12px'>
SMHI öppen data (CC BY) · <b>Ängelholm</b> (station 63600) — temp, vind, molnighet ·
<b>Lund</b> (station 53430) — globalstrålning · Plats: Eket, Örkelljunga 56.248°N 13.192°E
</div>""",unsafe_allow_html=True)

    with st.spinner("Hämtar SMHI-data och lagrar…"):
        smhi_data, smhi_errors = fetch_smhi_and_store()

    if smhi_errors:
        with st.expander(f"⚠️ {len(smhi_errors)} SMHI-källa(or) kunde inte hämtas"):
            for key, msg in smhi_errors.items():
                st.warning(f"**{key}**: {msg}")
            st.caption("Stationer: Helsingborg (62040) för temp/vind/moln, "
                       "Hoburg (98210) för globalstrålning.")

    # Current SMHI values
    smhi_defs = {
        "temperature": ("Lufttemperatur","°C",-20,40,SLATE,1),
        "wind_speed":  ("Vindhastighet","m/s",0,25,SLATE,1),
        "irradiance":  ("Globalstrålning (Lund)","W/m²",0,1350,AMBER,0),
        "cloud_cover": ("Molnighet","okta",0,8,MUTED,0),
    }
    smhi_latest = {}
    tile_specs = []
    for key,(label,unit,mn,mx,color,dec) in smhi_defs.items():
        df_s = smhi_data.get(key)
        val = float(df_s["value"].iloc[-1]) if isinstance(df_s, pd.DataFrame) and not df_s.empty else None
        smhi_latest[key] = val
        tile_specs.append((label,val,unit,mn,mx,color,dec,None))

    st.markdown('<div class="section-title">SMHI just nu</div>',unsafe_allow_html=True)
    scols = st.columns(4)
    def stile(label,val,unit,mn,mx,color,dec=1):
        display = fmt(val,dec,unit)
        pct = max(0,min(100,round((val-mn)/(mx-mn)*100))) if val is not None and mx>mn else 0
        return f"""<div style='background:{BG2};border-radius:8px;padding:12px 14px'>
<div style='font-size:.65rem;font-weight:500;color:{MUTED};text-transform:uppercase;
  letter-spacing:.08em;margin-bottom:4px'>{label}</div>
<div style='font-size:1.2rem;font-weight:600;color:{color}'>{display}</div>
<div style='height:3px;border-radius:2px;background:{BORDER};margin-top:7px'>
  <div style='height:100%;width:{pct}%;background:{color};border-radius:2px'></div>
</div></div>"""
    for col,(l,val,u,mn,mx,c,d,_) in zip(scols,tile_specs):
        col.markdown(stile(l,val,u,mn,mx,c,d),unsafe_allow_html=True)

    smhi_ts = None
    for df_s in smhi_data.values():
        if isinstance(df_s, pd.DataFrame) and not df_s.empty:
            smhi_ts = df_s["created_at"].iloc[-1].astimezone(SWE)
            break
    if smhi_ts:
        st.caption(f"Senast uppdaterat från SMHI: {smhi_ts.strftime('%H:%M')} · "
                   f"Data fördröjd ~1h · Lagras i Supabase för historisk analys")

    # Comparison chart
    st.markdown('<div class="section-title">Solinstrålning — sensor vs SMHI Lund</div>',
                unsafe_allow_html=True)
    h_cmp = st.selectbox("Jämförelseperiod",[6,12,24,48],index=1,
                          format_func=lambda h:f"{h}h",key="smhi_h")

    df_cmp  = fetch_history(h_cmp)
    df_smhi_hist = fetch_smhi_history(h_cmp)
    since_dt = datetime.now(timezone.utc) - timedelta(hours=h_cmp)

    fig_irr = go.Figure()
    if not df_cmp.empty:
        sub = df_cmp[df_cmp["sensor"]=="irradiance"]
        if not sub.empty:
            fig_irr.add_trace(go.Scatter(x=sub["created_at"],y=sub["value"],
                name="Sensor (på plats)",mode="lines",line=dict(color=AMBER,width=2)))

    # From Supabase (historical SMHI)
    if not df_smhi_hist.empty:
        sub_si = df_smhi_hist[df_smhi_hist["sensor"]=="smhi_irradiance"]
        if not sub_si.empty:
            fig_irr.add_trace(go.Scatter(x=sub_si["created_at"],y=sub_si["value"],
                name="SMHI Lund (lagrat)",mode="lines",line=dict(color=SLATE,width=1.5,dash="dot")))
    # Also from live SMHI fetch
    smhi_irr = smhi_data.get("irradiance")
    if smhi_irr is not None:
        w = smhi_irr[smhi_irr["created_at"]>=since_dt]
        if not w.empty:
            fig_irr.add_trace(go.Scatter(x=w["created_at"],y=w["value"],
                name="SMHI Lund (live)",mode="lines",line=dict(color="#6080C0",width=1.5,dash="dash")))

    fig_irr.update_layout(height=280,margin=dict(l=0,r=0,t=10,b=0),yaxis_title="W/m²",
        hovermode="x unified",legend=dict(orientation="h",yanchor="bottom",y=1.02,
            font=dict(size=10,color=MUTED,family="Inter")),
        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=MUTED,family="Inter"))
    fig_irr.update_xaxes(showgrid=False,color=MUTED)
    fig_irr.update_yaxes(gridcolor=BORDER,color=MUTED)
    st.plotly_chart(fig_irr,use_container_width=True)

    # Power vs cloud cover
    st.markdown('<div class="section-title">Termisk effekt vs molnighet</div>',
                unsafe_allow_html=True)
    fig_cl = go.Figure()
    if not df_cmp.empty:
        sub_p = df_cmp[df_cmp["sensor"]=="power"]
        if not sub_p.empty:
            fig_cl.add_trace(go.Scatter(x=sub_p["created_at"],y=sub_p["value"],
                name="Effekt (kW)",mode="lines",line=dict(color=RUST,width=2),yaxis="y"))
    if not df_smhi_hist.empty:
        sub_cl = df_smhi_hist[df_smhi_hist["sensor"]=="smhi_cloud_cover"]
        if not sub_cl.empty:
            fig_cl.add_trace(go.Scatter(x=sub_cl["created_at"],y=sub_cl["value"],
                name="Molnighet okta (SMHI)",mode="lines+markers",
                line=dict(color="#A0A8C8",width=1.5,dash="dot"),marker=dict(size=4),yaxis="y2"))
    smhi_cl = smhi_data.get("cloud_cover")
    if smhi_cl is not None:
        w = smhi_cl[smhi_cl["created_at"]>=since_dt]
        if not w.empty:
            fig_cl.add_trace(go.Scatter(x=w["created_at"],y=w["value"],
                name="Molnighet (live SMHI)",mode="lines+markers",
                line=dict(color="#8090B8",width=1.5),marker=dict(size=4),yaxis="y2"))
    fig_cl.update_layout(height=260,margin=dict(l=0,r=0,t=10,b=0),
        yaxis=dict(title="kW",color=RUST,gridcolor=BORDER),
        yaxis2=dict(title="okta (0–8)",color=SLATE,overlaying="y",side="right",range=[0,8]),
        hovermode="x unified",
        legend=dict(orientation="h",yanchor="bottom",y=1.02,font=dict(size=10,color=MUTED,family="Inter")),
        paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",font=dict(color=MUTED,family="Inter"))
    fig_cl.update_xaxes(showgrid=False,color=MUTED)
    st.plotly_chart(fig_cl,use_container_width=True)

    with st.expander("ℹ️ Om SMHI-data och lagring"):
        st.markdown(f"""
Varje gång SMHI-fliken laddas hämtas senaste dygnet från SMHI och sparas i tabellen
`smhi_readings` i Supabase. På så sätt byggs ett historiskt arkiv av väderdata
som kan jämföras med sensordata över tid.

**Tabellstruktur (kör i Supabase SQL Editor om tabellen saknas):**
```sql
CREATE TABLE IF NOT EXISTS smhi_readings (
  id         bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  created_at timestamptz NOT NULL,
  sensor     text NOT NULL,
  value      float8 NOT NULL,
  UNIQUE(created_at, sensor)
);
CREATE INDEX IF NOT EXISTS idx_smhi_sensor ON smhi_readings(sensor);
CREATE INDEX IF NOT EXISTS idx_smhi_ts     ON smhi_readings(created_at DESC);
```

**Sensorer som lagras:**
- `smhi_temperature` — lufttemperatur (Ängelholm)
- `smhi_wind_speed` — vindhastighet (Ängelholm)
- `smhi_irradiance` — globalstrålning W/m² (Lund)
- `smhi_cloud_cover` — molnighet okta 0–8 (Ängelholm)
""")

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
