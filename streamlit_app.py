"""
streamlit_app.py
────────────────
Helix Energy Monitor dashboard.
Deploy to Streamlit Cloud or run locally with: streamlit run streamlit_app.py

Secrets needed (Streamlit Cloud → App settings → Secrets):
  SUPABASE_URL = "https://xxxx.supabase.co"
  SUPABASE_KEY = "eyJ..."
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="Helix Energy Monitor",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ───────────────────────────────────────────────────
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
</style>
""", unsafe_allow_html=True)

# ── Sensor metadata ───────────────────────────────────────────
UNITS = {
    "temp_right_coll":  "°C",
    "temp_left_coll":   "°C",
    "temp_tank":        "°C",
    "temp_forward":     "°C",
    "temp_return":      "°C",
    "temp_difference":  "°C",
    "temp_cell":        "°C",
    "power":            "kW",
    "heat_energy":      "kWh",
    "Energifaktor":     "",
    "flow":             "m³/h",
    "volume":           "L",
    "irradiance":       "W/m²",
    "wind":             "m/s",
    "pressure":         "bar",
}

LABELS = {
    "temp_right_coll":  "Collector Right",
    "temp_left_coll":   "Collector Left",
    "temp_tank":        "Tank",
    "temp_forward":     "Forward",
    "temp_return":      "Return",
    "temp_difference":  "ΔT",
    "temp_cell":        "Cell",
    "power":            "Power",
    "heat_energy":      "Heat Energy",
    "Energifaktor":     "Energy Factor",
    "flow":             "Flow",
    "volume":           "Volume",
    "irradiance":       "Irradiance",
    "wind":             "Wind",
    "pressure":         "Pressure",
}

GROUPS = {
    "🌡️ Collectors": ["temp_right_coll", "temp_left_coll", "temp_cell"],
    "🪣 Tank & Circuit": ["temp_tank", "temp_forward", "temp_return", "temp_difference"],
    "⚡ Power & Flow": ["power", "flow", "heat_energy", "Energifaktor"],
    "🌤️ Environment": ["irradiance", "wind", "pressure", "volume"],
}

TEMP_SENSORS   = ["temp_right_coll", "temp_left_coll", "temp_tank",
                  "temp_forward", "temp_return", "temp_cell"]
POWER_SENSORS  = ["power", "flow"]
ENV_SENSORS    = ["irradiance", "wind"]

# ── Supabase connection ───────────────────────────────────────
@st.cache_resource
def get_db():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

db = get_db()

# ── Data helpers ──────────────────────────────────────────────
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
        st.error(f"Supabase error: {exc}")
        return pd.DataFrame()

    if not res.data:
        return pd.DataFrame()

    df = pd.DataFrame(res.data)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df


def get_latest(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return df.sort_values("created_at").groupby("sensor")["value"].last().to_dict()


def fmt(val, sensor):
    unit = UNITS.get(sensor, "")
    if val is None:
        return "—"
    if abs(val) >= 100:
        return f"{val:.1f} {unit}".strip()
    return f"{val:.2f} {unit}".strip()


def make_line_chart(df, sensors, y_label, height=380):
    fig = go.Figure()
    colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]
    for i, s in enumerate(sensors):
        sub = df[df["sensor"] == s]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["created_at"], y=sub["value"],
            name=LABELS.get(s, s),
            mode="lines",
            line=dict(width=2, color=colors[i % len(colors)]),
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


def make_dual_axis_chart(df, sensor_left, sensor_right,
                          label_left, label_right,
                          color_left="#f39c12", color_right="#3498db", height=380):
    fig = go.Figure()
    for s, yax, color, label in [
        (sensor_left,  "y",  color_left,  label_left),
        (sensor_right, "y2", color_right, label_right),
    ]:
        sub = df[df["sensor"] == s]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["created_at"], y=sub["value"],
            name=LABELS.get(s, s), mode="lines",
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
        format_func=lambda h: f"{h} hour{'s' if h > 1 else ''}" if h < 24 else f"{h // 24} day{'s' if h > 24 else ''}",
    )
    auto_refresh = st.checkbox("Auto-refresh every 60s", value=True)
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("Node: `testnod-mqtt-helix`")
    st.caption("Broker: `eaasy.life:1883`")

if auto_refresh:
    # Lightweight JS-based refresh
    st.markdown(
        '<meta http-equiv="refresh" content="60">',
        unsafe_allow_html=True,
    )

# ── Load data ─────────────────────────────────────────────────
df = fetch_data(hours)
now = get_latest(df)

# ── Header ────────────────────────────────────────────────────
title_col, ts_col = st.columns([3, 1])
title_col.title("🌡️ Helix Energy Monitor")
if not df.empty:
    last_ts = df["created_at"].max().astimezone(timezone.utc)
    ts_col.markdown(
        f"<div style='text-align:right; padding-top:16px; color:#6c757d; font-size:0.85rem'>"
        f"Last reading<br><b>{last_ts.strftime('%H:%M:%S')} UTC</b></div>",
        unsafe_allow_html=True,
    )

if df.empty:
    st.warning("⚠️ No data received yet. Make sure `mqtt_bridge.py` is running on your PC.")
    st.stop()

# ── KPI banner ────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("⚡ Power",         fmt(now.get("power"),        "power"))
k2.metric("🌤️ Irradiance",    fmt(now.get("irradiance"),   "irradiance"))
k3.metric("🪣 Tank temp",     fmt(now.get("temp_tank"),    "temp_tank"))
k4.metric("🔥 Heat energy",   fmt(now.get("heat_energy"),  "heat_energy"))
k5.metric("📊 Energy factor", fmt(now.get("Energifaktor"), "Energifaktor"))

st.divider()

# ── Sensor cards ──────────────────────────────────────────────
for group_name, sensors in GROUPS.items():
    st.subheader(group_name)
    cols = st.columns(len(sensors))
    for col, sensor in zip(cols, sensors):
        label = LABELS.get(sensor, sensor)
        val   = now.get(sensor)
        col.metric(label, fmt(val, sensor))

st.divider()

# ── Charts ────────────────────────────────────────────────────
st.subheader("📈 Trends")

tab_temp, tab_power, tab_env = st.tabs(["🌡️ Temperatures", "⚡ Power & Flow", "🌤️ Environment"])

with tab_temp:
    st.plotly_chart(
        make_line_chart(df, TEMP_SENSORS, "°C"),
        use_container_width=True,
    )

with tab_power:
    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("Power (kW)")
        sub = df[df["sensor"] == "power"]
        if not sub.empty:
            fig_p = go.Figure(go.Scatter(
                x=sub["created_at"], y=sub["value"],
                fill="tozeroy", mode="lines",
                line=dict(color="#f39c12", width=2),
            ))
            fig_p.update_layout(
                height=300, margin=dict(l=0, r=0, t=4, b=0),
                yaxis_title="kW",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            fig_p.update_xaxes(showgrid=False)
            fig_p.update_yaxes(gridcolor="#e9ecef")
            st.plotly_chart(fig_p, use_container_width=True)

    with col_b:
        st.caption("Flow (m³/h)")
        sub = df[df["sensor"] == "flow"]
        if not sub.empty:
            fig_f = go.Figure(go.Scatter(
                x=sub["created_at"], y=sub["value"],
                fill="tozeroy", mode="lines",
                line=dict(color="#3498db", width=2),
            ))
            fig_f.update_layout(
                height=300, margin=dict(l=0, r=0, t=4, b=0),
                yaxis_title="m³/h",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            fig_f.update_xaxes(showgrid=False)
            fig_f.update_yaxes(gridcolor="#e9ecef")
            st.plotly_chart(fig_f, use_container_width=True)

with tab_env:
    st.plotly_chart(
        make_dual_axis_chart(df, "irradiance", "wind", "W/m²", "m/s",
                             color_left="#f1c40f", color_right="#2980b9"),
        use_container_width=True,
    )

# ── Raw data & export ─────────────────────────────────────────
with st.expander("📥 Raw data & export"):
    pivot = df.pivot_table(
        index="created_at", columns="sensor", values="value", aggfunc="last"
    ).reset_index().sort_values("created_at", ascending=False)
    st.dataframe(pivot.head(200), use_container_width=True)
    st.download_button(
        label="⬇️ Download CSV",
        data=df.to_csv(index=False),
        file_name=f"helix_{hours}h.csv",
        mime="text/csv",
    )
