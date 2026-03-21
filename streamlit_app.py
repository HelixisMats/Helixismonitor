"""
streamlit_app.py — Helix Solar Thermal Monitor
Clean gauge dashboard with optional numeric view.
"""

import streamlit as st
from supabase import create_client
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

st.set_page_config(
    page_title="Helix Monitor",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  .block-container { padding-top: 1rem; padding-bottom: 1rem; }
  div[data-testid="metric-container"] {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 10px;
    padding: 10px 14px;
  }
  .status-bar {
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 0.88rem;
    margin-bottom: 12px;
  }
  .status-good { background:#d4edda; color:#155724; border:1px solid #c3e6cb; }
  .status-warn { background:#fff3cd; color:#856404; border:1px solid #ffeeba; }
  .status-idle { background:#e2e3e5; color:#383d41; border:1px solid #d6d8db; }
  .section-title {
    font-size: 0.7rem;
    font-weight: 500;
    color: #6c757d;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 16px 0 8px 2px;
  }
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

# ── Gauge helpers ─────────────────────────────────────────────
def thermometer(label, val, min_val, max_val, color, height=200):
    pct = max(0, min(1, (val - min_val) / (max_val - min_val))) if val is not None else 0
    fig = go.Figure()
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=val if val is not None else 0,
        number={"suffix": "°C", "font": {"size": 18, "color": color}},
        gauge={
            "axis": {"range": [min_val, max_val], "tickwidth": 1, "tickcolor": "#ccc", "tickfont": {"size": 9}},
            "bar": {"color": color, "thickness": 0.25},
            "bgcolor": "#f0f0f0",
            "borderwidth": 0,
            "shape": "bullet",
            "threshold": {"line": {"color": color, "width": 2}, "thickness": 0.75, "value": val or 0},
        },
        title={"text": label, "font": {"size": 11, "color": "#888"}},
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(
        height=100, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", font_color="#333",
    )
    return fig

def gauge(label, val, min_val, max_val, unit, color, sub_text="", height=200):
    pct = max(0, min(1, (val - min_val) / (max_val - min_val))) if val is not None else 0
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val if val is not None else 0,
        number={"suffix": f" {unit}", "font": {"size": 22, "color": color}},
        gauge={
            "axis": {"range": [min_val, max_val], "tickwidth": 1, "tickfont": {"size": 9}},
            "bar": {"color": color},
            "bgcolor": "#f0f0f0",
            "borderwidth": 0,
            "steps": [{"range": [min_val, max_val], "color": "#f0f0f0"}],
        },
        title={"text": f"{label}<br><span style='font-size:11px;color:#999'>{sub_text}</span>",
               "font": {"size": 12, "color": "#666"}},
    ))
    fig.update_layout(
        height=height, margin=dict(l=20, r=20, t=50, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig

def line_chart(df, sensors, colors, y_label, height=280):
    labels = {
        "temp_right_coll": "Coll. Right", "temp_left_coll": "Coll. Left",
        "temp_tank": "Tank", "temp_forward": "Forward", "temp_return": "Return",
        "temp_cell": "Cell", "temp_difference": "ΔT",
        "power": "Power", "flow": "Flow", "irradiance": "Irradiance",
        "wind": "Wind", "pressure": "Pressure", "heat_energy": "Heat Energy",
    }
    fig = go.Figure()
    for s, c in zip(sensors, colors):
        sub = df[df["sensor"] == s]
        if sub.empty: continue
        fig.add_trace(go.Scatter(
            x=sub["created_at"], y=sub["value"],
            name=labels.get(s, s), mode="lines",
            line=dict(width=2, color=c),
        ))
    fig.update_layout(
        height=height, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title=y_label,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e9ecef")
    return fig

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    hours = st.selectbox("Time window",
        options=[1, 6, 12, 24, 48, 168], index=3,
        format_func=lambda h: f"{h}h" if h < 24 else f"{h//24}d")
    auto_refresh = st.checkbox("Auto-refresh 60s", value=True)
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.caption("Solar thermal concentrator")
    st.caption("`helix/1/1234/data`")

if auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="60">', unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────
df = fetch_data(hours)
if df.empty:
    st.warning("⚠️ No data yet.")
    st.stop()

v = {s: latest(df, s) for s in df["sensor"].unique()}
last_ts = df["created_at"].max().astimezone(timezone.utc)

# ── Header ────────────────────────────────────────────────────
h_col, ts_col, view_col = st.columns([3, 2, 1])
h_col.title("☀️ Helix Monitor")
ts_col.markdown(
    f"<div style='padding-top:18px;color:#6c757d;font-size:0.82rem'>"
    f"Last update: <b>{last_ts.strftime('%H:%M:%S')} UTC</b></div>",
    unsafe_allow_html=True,
)

# View toggle
if "view" not in st.session_state:
    st.session_state.view = "gauges"
if view_col.button("📊 Switch view"):
    st.session_state.view = "numeric" if st.session_state.view == "gauges" else "gauges"

# System status
pwr = v.get("power")
irr = v.get("irradiance")
if pwr and irr and irr > 200 and pwr > 1.0:
    st.markdown('<div class="status-bar status-good">🟢 System actively harvesting solar energy</div>', unsafe_allow_html=True)
elif irr and irr > 50:
    st.markdown('<div class="status-bar status-warn">🟡 Low irradiance — limited collection</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="status-bar status-idle">⚪ System idle — insufficient sunlight</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# GAUGE VIEW
# ══════════════════════════════════════════════════════════════
if st.session_state.view == "gauges":

    # Temperatures
    st.markdown('<div class="section-title">🌡️ Temperatures</div>', unsafe_allow_html=True)
    tc = st.columns(5)
    temp_sensors = [
        ("Coll. Right", "temp_right_coll", "#e74c3c", 0, 100),
        ("Coll. Left",  "temp_left_coll",  "#e67e22", 0, 100),
        ("Forward",     "temp_forward",     "#e74c3c", 0, 100),
        ("Return",      "temp_return",      "#3498db", 0, 100),
        ("Tank",        "temp_tank",        "#1D9E75", 10, 80),
    ]
    for col, (lbl, sensor, color, mn, mx) in zip(tc, temp_sensors):
        val = v.get(sensor)
        col.plotly_chart(thermometer(lbl, val, mn, mx, color), use_container_width=True, config={"displayModeBar": False})

    # Flow & Power
    st.markdown('<div class="section-title">⚡ Flow & Power</div>', unsafe_allow_html=True)
    fc1, fc2 = st.columns(2)
    with fc1:
        st.plotly_chart(
            gauge("Flow rate", v.get("flow"), 0, 1, "m³/h", "#3498db", "Normal flow"),
            use_container_width=True, config={"displayModeBar": False}
        )
    with fc2:
        st.plotly_chart(
            gauge("Thermal power", v.get("power"), 0, 10, "kW", "#e74c3c", "Active collection"),
            use_container_width=True, config={"displayModeBar": False}
        )

    # Energy
    st.markdown('<div class="section-title">🔋 Energy harvest</div>', unsafe_allow_html=True)
    ec1, ec2, ec3 = st.columns(3)
    ef = v.get("Energifaktor")
    ec1.metric("Accumulated heat", fmt(v.get("heat_energy"), 3, "kWh"))
    ec2.metric("Energy counter", fmt(ef/1000 if ef else None, 2, "kWh") if ef else "—")
    ec3.metric("ΔT Forward−Return", fmt(v.get("temp_difference"), 2, "°C"))

    # Environment
    st.markdown('<div class="section-title">🌤️ Environment</div>', unsafe_allow_html=True)
    env1, env2, env3, env4 = st.columns(4)
    env1.metric("Solar irradiance", fmt(v.get("irradiance"), 0, "W/m²"))
    env2.metric("Wind", fmt(v.get("wind"), 2, "m/s"))
    env3.metric("Pressure", fmt(v.get("pressure"), 2, "bar"))
    env4.metric("Volume", fmt(v.get("volume"), 1, "L"))

    # Charts
    st.divider()
    st.markdown('<div class="section-title">📈 Trends</div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["🌡️ Temperatures", "⚡ Power & Flow", "☀️ Solar vs Power"])
    with t1:
        st.plotly_chart(line_chart(df,
            ["temp_right_coll", "temp_left_coll", "temp_forward", "temp_return", "temp_tank"],
            ["#e74c3c", "#e67e22", "#f39c12", "#3498db", "#1D9E75"], "°C"),
            use_container_width=True)
    with t2:
        ca, cb = st.columns(2)
        with ca:
            st.plotly_chart(line_chart(df, ["power"], ["#e74c3c"], "kW", height=250), use_container_width=True)
        with cb:
            st.plotly_chart(line_chart(df, ["flow"], ["#3498db"], "m³/h", height=250), use_container_width=True)
    with t3:
        fig_dual = go.Figure()
        for s, color, yax, name in [
            ("irradiance", "#f1c40f", "y",  "Irradiance (W/m²)"),
            ("power",      "#e74c3c", "y2", "Power (kW)"),
        ]:
            sub = df[df["sensor"] == s]
            if not sub.empty:
                fig_dual.add_trace(go.Scatter(x=sub["created_at"], y=sub["value"],
                    name=name, mode="lines", line=dict(width=2, color=color), yaxis=yax))
        fig_dual.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title="W/m²", color="#f1c40f"),
            yaxis2=dict(title="kW", color="#e74c3c", overlaying="y", side="right"),
            hovermode="x unified", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        fig_dual.update_xaxes(showgrid=False)
        fig_dual.update_yaxes(gridcolor="#e9ecef")
        st.plotly_chart(fig_dual, use_container_width=True)

# ══════════════════════════════════════════════════════════════
# NUMERIC VIEW
# ══════════════════════════════════════════════════════════════
else:
    st.subheader("☀️ Solar & Environment")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Irradiance", fmt(v.get("irradiance"), 0, "W/m²"), help="Solar power per m² hitting collectors.")
    c2.metric("Cell temp", fmt(v.get("temp_cell"), 1, "°C"), help="Solar cell temperature.")
    c3.metric("Wind", fmt(v.get("wind"), 2, "m/s"), help="Higher wind = more heat loss.")
    c4.metric("Pressure", fmt(v.get("pressure"), 2, "bar"), help="System hydraulic pressure.")
    st.divider()

    st.subheader("🌡️ Temperatures")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Coll. Right", fmt(v.get("temp_right_coll"), 1, "°C"))
    c2.metric("Coll. Left", fmt(v.get("temp_left_coll"), 1, "°C"))
    c3.metric("Forward", fmt(v.get("temp_forward"), 1, "°C"))
    c4.metric("Return", fmt(v.get("temp_return"), 1, "°C"))
    c5.metric("Tank", fmt(v.get("temp_tank"), 1, "°C"))
    st.divider()

    st.subheader("🔁 Heat Transfer")
    c1, c2, c3 = st.columns(3)
    c1.metric("ΔT Forward−Return", fmt(v.get("temp_difference"), 2, "°C"), help="Temperature drop = energy transferred.")
    c2.metric("Flow rate", fmt(v.get("flow"), 3, "m³/h"), help="Fluid flow per hour.")
    c3.metric("System pressure", fmt(v.get("pressure"), 2, "bar"))
    st.divider()

    st.subheader("⚡ Power & Energy")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Thermal power", fmt(v.get("power"), 2, "kW"), help="Current rate of heat collection.")
    c2.metric("Heat energy", fmt(v.get("heat_energy"), 3, "kWh"), help="Accumulated heat since reset.")
    ef = v.get("Energifaktor")
    c3.metric("Energy counter", fmt(ef/1000 if ef else None, 2, "kWh"))
    c4.metric("Volume", fmt(v.get("volume"), 1, "L"))

    with st.expander("📥 Raw data & export"):
        pivot = df.pivot_table(
            index="created_at", columns="sensor", values="value", aggfunc="last"
        ).reset_index().sort_values("created_at", ascending=False)
        st.dataframe(pivot.head(300), use_container_width=True)
        st.download_button("⬇️ Download CSV", df.to_csv(index=False),
            file_name=f"helix_{hours}h.csv", mime="text/csv")
