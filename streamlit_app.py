"""
streamlit_app.py — Helix Solar Thermal Monitor
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

st.set_page_config(
    page_title="Helix Solar Thermal Monitor",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.2rem; }
  div[data-testid="metric-container"] {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 10px;
    padding: 12px 16px;
  }
  div[data-testid="metric-container"] label { font-size: 0.75rem; color: #6c757d; }
  .explain { font-size: 0.82rem; color: #6c757d; margin-top: -8px; margin-bottom: 12px; }
  .system-status { padding: 10px 16px; border-radius: 8px; margin-bottom: 8px; font-size: 0.9rem; }
  .status-good  { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
  .status-warn  { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
  .status-idle  { background: #e2e3e5; color: #383d41; border: 1px solid #d6d8db; }
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
    if val is None:
        return "—"
    return f"{val:.{decimals}f} {unit}".strip()

def system_status(power, irradiance, dt):
    if power is None:
        return "idle", "⚫ No data"
    if irradiance and irradiance > 200 and power > 1.0:
        return "good", f"🟢 System actively harvesting solar energy"
    if irradiance and irradiance > 50:
        return "warn", f"🟡 Low solar irradiance — limited energy collection"
    return "idle", "⚪ System idle — insufficient sunlight"

def make_chart(df, sensors, colors, y_label, height=360, fill=False):
    fig = go.Figure()
    for s, color in zip(sensors, colors):
        sub = df[df["sensor"] == s]
        if sub.empty:
            continue
        label = {
            "temp_right_coll": "Collector Right",
            "temp_left_coll":  "Collector Left",
            "temp_tank":       "Storage Tank",
            "temp_forward":    "Forward (to tank)",
            "temp_return":     "Return (from tank)",
            "temp_cell":       "Solar Cell",
            "temp_difference": "ΔT Forward−Return",
            "power":           "Thermal Power",
            "flow":            "Flow Rate",
            "heat_energy":     "Accumulated Heat",
            "irradiance":      "Solar Irradiance",
            "wind":            "Wind Speed",
            "pressure":        "System Pressure",
        }.get(s, s)
        fig.add_trace(go.Scatter(
            x=sub["created_at"], y=sub["value"],
            name=label, mode="lines",
            fill="tozeroy" if fill else "none",
            line=dict(width=2, color=color),
        ))
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title=y_label,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e9ecef")
    return fig

def make_dual_chart(df, s_left, s_right, label_left, label_right,
                    color_left, color_right, height=360):
    fig = go.Figure()
    for s, yax, color, lbl in [
        (s_left,  "y",  color_left,  label_left),
        (s_right, "y2", color_right, label_right),
    ]:
        sub = df[df["sensor"] == s]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["created_at"], y=sub["value"],
            name=lbl, mode="lines",
            line=dict(width=2, color=color), yaxis=yax,
        ))
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title=label_left,  color=color_left),
        yaxis2=dict(title=label_right, color=color_right, overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e9ecef")
    return fig

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    hours = st.selectbox(
        "Time window",
        options=[1, 6, 12, 24, 48, 168],
        index=3,
        format_func=lambda h: f"{h}h" if h < 24 else f"{h//24} day{'s' if h>24 else ''}",
    )
    auto_refresh = st.checkbox("Auto-refresh every 60s", value=True)
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("**System:** Solar thermal concentrator")
    st.caption("**Node:** `testnod-mqtt-helix`")
    st.caption("**Broker:** `eaasy.life:1883`")
    st.divider()
    st.markdown("""
**How it works:**
Solar collectors heat a fluid which flows through pipes to a storage tank.
An energy meter measures the heat transferred based on flow rate × temperature difference.
""")

if auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────
df = fetch_data(hours)

if df.empty:
    st.warning("⚠️ No data received yet.")
    st.stop()

# Latest values
v = {s: latest(df, s) for s in df["sensor"].unique()}
last_ts = df["created_at"].max().astimezone(timezone.utc)

# ── Header ────────────────────────────────────────────────────
col_title, col_ts = st.columns([3, 1])
col_title.title("☀️ Helix Solar Thermal Monitor")
col_ts.markdown(
    f"<div style='text-align:right; padding-top:18px; color:#6c757d; font-size:0.85rem'>"
    f"Last reading<br><b>{last_ts.strftime('%H:%M:%S')} UTC</b></div>",
    unsafe_allow_html=True,
)

# ── System status banner ──────────────────────────────────────
status_type, status_msg = system_status(v.get("power"), v.get("irradiance"), v.get("temp_difference"))
st.markdown(f'<div class="system-status status-{status_type}">{status_msg}</div>', unsafe_allow_html=True)

st.divider()

# ══════════════════════════════════════════════════════════════
# SECTION 1 — Solar & Environment
# ══════════════════════════════════════════════════════════════
st.subheader("☀️ Solar & Weather Conditions")
st.markdown('<p class="explain">External conditions driving the system. Irradiance is the amount of solar energy hitting the collectors — above ~200 W/m² the system starts collecting meaningfully.</p>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Solar Irradiance", fmt(v.get("irradiance"), 0, "W/m²"),
          help="Solar power per square metre hitting the collector surface. Peak clear-sky value is ~1000 W/m².")
c2.metric("Solar Cell Temp", fmt(v.get("temp_cell"), 1, "°C"),
          help="Temperature of the photovoltaic/thermal cell on the collector. High values may indicate low efficiency.")
c3.metric("Wind Speed", fmt(v.get("wind"), 2, "m/s"),
          help="Wind causes heat loss from the collectors. Higher wind = lower efficiency.")
c4.metric("System Pressure", fmt(v.get("pressure"), 2, "bar"),
          help="Hydraulic pressure in the fluid circuit. Should remain stable. Large changes may indicate a fault.")

st.divider()

# ══════════════════════════════════════════════════════════════
# SECTION 2 — Collector Temperatures
# ══════════════════════════════════════════════════════════════
st.subheader("🌡️ Collector Temperatures")
st.markdown('<p class="explain">Temperature at the solar collectors — the hot end of the system. The fluid is heated here and pumped toward the storage tank. Left and right sensors monitor each side of the collector array independently.</p>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
c1.metric("Collector Right", fmt(v.get("temp_right_coll"), 1, "°C"),
          help="Outlet temperature on the right side of the collector array.")
c2.metric("Collector Left", fmt(v.get("temp_left_coll"), 1, "°C"),
          help="Outlet temperature on the left side of the collector array. Should be close to Right — large differences may indicate shading or flow issues.")

st.divider()

# ══════════════════════════════════════════════════════════════
# SECTION 3 — Heat Transfer Circuit
# ══════════════════════════════════════════════════════════════
st.subheader("🔁 Heat Transfer Circuit")
st.markdown('<p class="explain">The fluid loop between collectors and storage tank. Forward is the hot fluid going toward the tank; Return is the cooler fluid coming back. The temperature difference (ΔT) is key — a larger ΔT means more energy is being transferred per litre of flow.</p>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Forward Temp", fmt(v.get("temp_forward"), 1, "°C"),
          help="Temperature of fluid leaving the collectors toward the storage tank. This is the hottest point in the circuit.")
c2.metric("Return Temp", fmt(v.get("temp_return"), 1, "°C"),
          help="Temperature of fluid returning from the tank back to the collectors. Lower than forward — it has given up its heat.")
dt = v.get("temp_difference")
c3.metric("ΔT (Forward − Return)", fmt(dt, 2, "°C"),
          delta=None,
          help="The temperature drop across the heat exchanger. Multiplied by flow rate, this gives you the thermal power output.")
c4.metric("Flow Rate", fmt(v.get("flow"), 3, "m³/h"),
          help="Volume of fluid circulating per hour. Together with ΔT, this determines how much heat is being moved.")

st.divider()

# ══════════════════════════════════════════════════════════════
# SECTION 4 — Storage Tank
# ══════════════════════════════════════════════════════════════
st.subheader("🪣 Storage Tank")
st.markdown('<p class="explain">The thermal storage — where collected solar energy is stored as hot water. The tank temperature rises as the system collects energy throughout the day.</p>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
c1.metric("Tank Temperature", fmt(v.get("temp_tank"), 1, "°C"),
          help="Current temperature of the storage tank. A healthy solar day should raise this significantly from morning to afternoon.")
c2.metric("Stored Volume", fmt(v.get("volume"), 1, "L"),
          help="Volume of fluid in the system. Should remain stable — changes may indicate leaks.")

# Energifaktor is a cumulative Wh counter — convert to kWh
ef = v.get("Energifaktor")
ef_kwh = ef / 1000 if ef is not None else None
c3.metric("Energy Counter", fmt(ef_kwh, 2, "kWh"),
          help="Cumulative energy count from the meter (converted from Wh). This counter increments over time and may be reset periodically.")

st.divider()

# ══════════════════════════════════════════════════════════════
# SECTION 5 — Power Output
# ══════════════════════════════════════════════════════════════
st.subheader("⚡ Thermal Power Output")
st.markdown('<p class="explain">Real-time energy harvest. Power is calculated by the energy meter from flow rate × ΔT × fluid heat capacity. Heat energy is the accumulated total since the last meter reset.</p>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
c1.metric("Thermal Power", fmt(v.get("power"), 2, "kW"),
          help="Current rate of heat collection. Calculated by the energy meter as: Flow × ΔT × fluid specific heat capacity.")
c2.metric("Accumulated Heat", fmt(v.get("heat_energy"), 3, "kWh"),
          help="Total heat energy collected since the last meter reset. This is the most meaningful measure of daily solar yield.")

# Efficiency estimate: power / (irradiance * assumed collector area)
# We don't know collector area, so show power/irradiance ratio as a proxy
irr = v.get("irradiance")
pwr = v.get("power")
if irr and pwr and irr > 50:
    efficiency_proxy = (pwr * 1000) / irr  # W per W/m² = effective m²
    c3.metric("Effective Collector Output", fmt(efficiency_proxy, 2, "kW per kW/m²"),
              help="Ratio of thermal power output to solar irradiance. Indicates how effectively the collectors are converting available sunlight.")
else:
    c3.metric("Effective Collector Output", "—",
              help="Not available when irradiance is too low.")

st.divider()

# ══════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════
st.subheader("📈 Historical Trends")

tab1, tab2, tab3, tab4 = st.tabs([
    "🌡️ Temperatures",
    "⚡ Power & Flow",
    "☀️ Solar vs Output",
    "🔁 ΔT & Efficiency",
])

with tab1:
    st.caption("All temperature sensors over time. Collector temps should track irradiance; tank temp should rise steadily during daylight hours.")
    st.plotly_chart(
        make_chart(df,
            ["temp_right_coll", "temp_left_coll", "temp_forward", "temp_return", "temp_tank", "temp_cell"],
            ["#e74c3c", "#c0392b", "#e67e22", "#3498db", "#2ecc71", "#9b59b6"],
            "Temperature (°C)"),
        use_container_width=True,
    )

with tab2:
    st.caption("Thermal power output and fluid flow rate. Power = Flow × ΔT × heat capacity. Both should track solar irradiance closely.")
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("**Thermal Power (kW)**")
        st.plotly_chart(
            make_chart(df, ["power"], ["#f39c12"], "kW", height=300, fill=True),
            use_container_width=True,
        )
    with col_b:
        st.caption("**Flow Rate (m³/h)**")
        st.plotly_chart(
            make_chart(df, ["flow"], ["#3498db"], "m³/h", height=300, fill=True),
            use_container_width=True,
        )

with tab3:
    st.caption("Solar irradiance vs thermal power output. These should correlate strongly — gaps indicate shading, cloud cover, or system inefficiency.")
    st.plotly_chart(
        make_dual_chart(df, "irradiance", "power",
                        "Irradiance (W/m²)", "Power (kW)",
                        "#f1c40f", "#e74c3c"),
        use_container_width=True,
    )

with tab4:
    st.caption("ΔT (temperature difference forward−return) shows how much heat is being extracted per litre of flow. Low ΔT with high flow = efficient bulk transfer. High ΔT with low flow = slower but hotter.")
    st.plotly_chart(
        make_dual_chart(df, "temp_difference", "flow",
                        "ΔT (°C)", "Flow (m³/h)",
                        "#e74c3c", "#3498db"),
        use_container_width=True,
    )

# ── Raw data ──────────────────────────────────────────────────
with st.expander("📥 Raw data & export"):
    pivot = df.pivot_table(
        index="created_at", columns="sensor", values="value", aggfunc="last"
    ).reset_index().sort_values("created_at", ascending=False)
    st.dataframe(pivot.head(300), use_container_width=True)
    st.download_button(
        label="⬇️ Download CSV",
        data=df.to_csv(index=False),
        file_name=f"helix_{hours}h.csv",
        mime="text/csv",
    )
