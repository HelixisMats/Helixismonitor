"""
streamlit_app.py — Helixis LC Monitor
Tabs: Live (gauges) | Historik | SMHI & Analys
"""

import streamlit as st
from supabase import create_client
from streamlit_echarts import st_echarts
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os, requests, json
import numpy as np
from irradiance_panel import clear_sky, fit_line

def send_alert_email(age_min: float):
    """Send email alert when data stops arriving. Uses Gmail SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    try:
        gmail_user = st.secrets.get("ALERT_GMAIL_USER", "")
        gmail_pass = st.secrets.get("ALERT_GMAIL_APP_PASSWORD", "")
        if not gmail_user or not gmail_pass:
            return  # Not configured — fail silently
        msg = MIMEText(
            f"⚠️ Helixis LC Monitor — No data received\n\n"
            f"Last data: {age_min:.0f} minutes ago\n"
            f"System may have lost MQTT connection.\n\n"
            f"Check the MQTT broker and sensor gateway at Eket, Örkelljunga.",
            "plain", "utf-8"
        )
        msg["Subject"] = f"⚠️ Helixis: No sensor data for {age_min:.0f} min"
        msg["From"]    = gmail_user
        msg["To"]      = "mats@helixis.se, eugene.nedilko@helixis.se"
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
    except Exception:
        pass  # Never crash the app due to email failure

st.set_page_config(page_title="Helixis LC Monitor", page_icon="🌀",
                   layout="wide", initial_sidebar_state="expanded")

SWE    = ZoneInfo("Europe/Stockholm")
BG     = "#FFFFFF"; BG2 = "#F5F6FA"; BORDER = "#E6E9F2"
TEXT   = "#10131A"; MUTED = "#8A90A8"; BLUE = "#2878F5"
CARD_R = "18px"                      # card corner radius
SHADOW = "0 2px 16px rgba(20,30,60,.07)"
APP_BUILD = "2026-10-29"             # shown in the card, so it is obvious
                                     # which version is actually deployed
HERO   = "hero.jpg"                  # background render from the design
ASSETS = "assets"                    # icons and logo exported from Figma
TEAL   = "#167A5E"; AMBER = "#B87200"; RUST = "#A83030"; SLATE = "#2E5EA0"
LGRAY  = "#E4E7F0"
SITE_LAT, SITE_LON = 56.248, 13.192

# ── Graf-interaktion ──────────────────────────────────────────
# Standardconfig för alla Plotly-grafer. Verktygsfältet (modebar) måste vara
# på, annars går det inte att zooma ut igen efter en zoom-drag — knapparna
# "Zoom out" och "Reset axes" ligger där. doubleClick="reset" gör dessutom att
# dubbelklick/dubbeltryck alltid tar dig tillbaka till hela intervallet.
PLOT_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "displaylogo": False,
    "doubleClick": "reset",
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
}
# Samma sak men utan scroll-zoom (för staplar/översikter där scroll ska
# fortsätta scrolla sidan i mobilen).
PLOT_CONFIG_NOSCROLL = {**PLOT_CONFIG, "scrollZoom": False}


def add_time_controls(fig, extra_height=66):
    """Snabbknappar för tidsintervall ovanför en datum-x-axel.

    Ger en väg tillbaka ur en zoom utan att ladda om: tryck på en förvald
    period, använd Reset axes i verktygsfältet, eller dubbelklicka i grafen.
    """
    fig.update_xaxes(rangeselector=dict(
        buttons=[
            dict(count=6,  label="6h",  step="hour", stepmode="backward"),
            dict(count=12, label="12h", step="hour", stepmode="backward"),
            dict(count=1,  label="24h", step="day",  stepmode="backward"),
            dict(count=3,  label="3d",  step="day",  stepmode="backward"),
            dict(step="all", label=T.get("btn_all", "All")),
        ],
        x=0, xanchor="left", y=1.30, yanchor="top",
        bgcolor=BG2, activecolor=LGRAY, bordercolor=BORDER, borderwidth=1,
        font=dict(size=11, color=TEXT, family="Inter"),
    ))
    fig.update_layout(height=(fig.layout.height or 320) + extra_height,
                      margin=dict(t=76))
    return fig

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
        "pressure_lbl":"Pressure (bar)","flow_lbl":"Flow (l/min)",
        "power_lbl":"Thermal power (kW)","irr_lbl":"Irradiance (W/m²)","wind_lbl":"Wind (m/s)",
        "trap_help":"Calculated via trapezoid integration. ΔE=(P₁+P₂)/2×Δt — more accurate than sensor.",
        "heat_help":"Accumulated from energy sensor since last reset.",
        "loading_hist":"Loading history…","no_data_interval":"No data for selected interval.",
        "raw_export":"Raw data & export","download_csv":"Download CSV",
        "analysis_period":"Analysis period",
        "loading_smhi":"Loading SMHI station data…","loading_strang":"Loading STRÅNG model data…",
        "overview_title":"Overview — click to select a period",
        "overview_caption":"Yellow line = peak irradiance (W/m²). Blue bars = daily energy (kWh). Select a period with the date pickers below.",
        "btn_all":"All",
        "resolution_note":"Showing {res} averages across the selected period.",
        "resolution_raw":"Showing every reading, unaveraged.",
        "export_note_raw":"Export contains every reading, unaveraged.",
        "err_timeout":"The database gave up on this query (statement timeout). "
                      "The table is too large to read raw. Run supabase_perf.sql "
                      "in the Supabase SQL editor — it moves this work into the "
                      "database — or pick a shorter period.",
        "err_rpc_timeout":"The database timed out aggregating this period. Try a "
                          "shorter range, or re-run supabase_perf.sql (it raises "
                          "the timeout for these queries).",
        "res_label":"Detail","res_auto":"Auto","res_fine":"Fine","res_full":"Max (1 s)",
        "res_help":"Readings are averaged into time buckets so a period loads in "
                   "one request. Auto sizes the bucket to the period; Fine and "
                   "Max keep more detail, down to a 1-second floor. The bucket "
                   "actually used is shown under the first chart.",
        "export_note":"Export uses the same {res} averages shown in the charts.",
        "chart_hint":"Drag across a chart to zoom in. Use the preset buttons, double-click the chart, or the toolbar's reset button (top right) to zoom back out.",
        "date_from":"From","date_to":"To","peak_irr_lbl":"Peak irradiance","energy_kwh_lbl":"Energy (kWh)",
        "no_data_db":"No data in the database.","no_data_available":"No data available.",
        "no_data_last_day":"No data in the last 24 hours.",
        "recent_2days":"Sun & Power — last two days with data",
        "last_day_system":"Last 24 hours — temperatures & system",
        "today_lbl":"Today","yesterday_lbl":"Yesterday","window":"window",
        "no_values_for_days":"Data exists but no irradiance/power values for {a} or {b}.",
        "col_sensor":"Sensor","col_min":"Min","col_max":"Max","col_mean":"Mean",
        "energy_window_help":"Energy in the selected history window only (not necessarily from midnight).",
        "about_spec":"System specification","about_location":"Geographic location",
        "about_aerial":"Aerial photo — Eket","about_add_img":"Add eket_aerial.png to the repo to show the aerial photo.",
        "about_coords":"Coordinates","about_alt":"Altitude a.s.l.","about_region":"Region",
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
        "pressure_lbl":"Tryck (bar)","flow_lbl":"Flöde (l/min)",
        "power_lbl":"Termisk effekt (kW)","irr_lbl":"Instrålning (W/m²)","wind_lbl":"Vind (m/s)",
        "trap_help":"Beräknad med trapetsintegration. ΔE=(P₁+P₂)/2×Δt — mer exakt än sensorn.",
        "heat_help":"Ackumulerat värde från energisensorn sedan senaste nollställning.",
        "loading_hist":"Hämtar historik…","no_data_interval":"Ingen data för valt intervall.",
        "raw_export":"Rådata & export","download_csv":"Ladda ner CSV",
        "analysis_period":"Analysperiod",
        "loading_smhi":"Hämtar SMHI stationsdata…","loading_strang":"Hämtar STRÅNG modelldata…",
        "overview_title":"Översikt — klicka för att välja period",
        "overview_caption":"Gula linjen = toppinstrålning (W/m²). Blå staplar = daglig energi (kWh). Välj period med datumväljarna nedan.",
        "btn_all":"Allt",
        "resolution_note":"Visar {res}-medelvärden över vald period.",
        "resolution_raw":"Visar varje mätvärde, utan medelvärdesbildning.",
        "export_note_raw":"Exporten innehåller varje mätvärde, utan medelvärdesbildning.",
        "err_timeout":"Databasen avbröt frågan (statement timeout). Tabellen är "
                      "för stor för att läsas rå. Kör supabase_perf.sql i "
                      "Supabase SQL-editorn — den flyttar jobbet in i databasen "
                      "— eller välj en kortare period.",
        "err_rpc_timeout":"Databasen hann inte aggregera perioden. Välj en kortare "
                          "period, eller kör supabase_perf.sql igen (den höjer "
                          "tidsgränsen för de här frågorna).",
        "res_label":"Detaljnivå","res_auto":"Auto","res_fine":"Fin","res_full":"Max (1 s)",
        "res_help":"Mätvärden slås ihop i tidsintervall så att perioden hämtas i "
                   "en enda förfrågan. Auto anpassar intervallet till perioden; Fin "
                   "och Max behåller mer detalj, ned till 1 sekund. Vilket "
                   "intervall som används visas under första grafen.",
        "export_note":"Exporten använder samma {res}-medelvärden som graferna.",
        "chart_hint":"Dra i grafen för att zooma in. Zooma ut igen med snabbknapparna, dubbelklick i grafen, eller reset-knappen i verktygsfältet uppe till höger.",
        "date_from":"Från","date_to":"Till","peak_irr_lbl":"Toppinstrålning","energy_kwh_lbl":"Energi (kWh)",
        "no_data_db":"Ingen data i databasen.","no_data_available":"Ingen data tillgänglig.",
        "no_data_last_day":"Ingen data senaste dygnet.",
        "recent_2days":"Sol & Effekt — senaste två dagarna",
        "last_day_system":"Senaste dygnet — temperaturer & system",
        "today_lbl":"Idag","yesterday_lbl":"Igår","window":"fönster",
        "no_values_for_days":"Data finns men inga irradiance/power-värden för {a} eller {b}.",
        "col_sensor":"Sensor","col_min":"Min","col_max":"Max","col_mean":"Medel",
        "energy_window_help":"Energi endast i det valda historikfönstret (inte nödvändigtvis från midnatt).",
        "about_spec":"Systemspecifikation","about_location":"Geografisk placering",
        "about_aerial":"Flygfoto — Eket","about_add_img":"Lägg till eket_aerial.png i repot för att visa flygfoto.",
        "about_coords":"Koordinater","about_alt":"Höjd ö.h.","about_region":"Region",
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

# ── Page chrome ───────────────────────────────────────────────
# The layout follows the Figma proposal: a light page with an optional
# background render, a floating card on the left holding status and
# navigation, and white cards on the right. Streamlit's own sidebar is that
# left card — it is already a fixed left panel, so no column juggling.
import base64 as _b64

# The exported artwork is carried in the file itself. It used to be read
# from an assets/ folder, and when that folder did not follow the app to
# the server the logo silently fell back to plain text and the section
# icons vanished — with no error to explain why.
_ASSET_SVG = {
"helixis-logo.svg": "<svg width=\"250\" height=\"64\" viewBox=\"0 0 250 64\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><g clip-path=\"url(#clip0_67_9)\"><path d=\"M52.2592 31.4004V17.4439C50.1198 15.3181 48.9198 14.1258 46.7804 12H32.7344L52.2592 31.4004Z\" fill=\"#2878F5\"/><path d=\"M25.0832 32.4003L32.5311 24.9998L19.4479 12H12V19.4004L25.0832 32.4003Z\" fill=\"#2878F5\"/><path d=\"M12 32.5996V46.5561C14.1394 48.6819 15.3394 49.8742 17.4788 52H31.5248L12 32.5996Z\" fill=\"#2878F5\"/><path d=\"M39.1745 31.5996L31.7266 39.0001L44.8098 51.9999H52.2577V44.5994L39.1745 31.5996Z\" fill=\"#2878F5\"/><path d=\"M87.2174 29.6852H71.2055V17.5938H64.3438V48.0493H71.2055V35.8218H87.2174V48.0493H94.0799V17.5938H87.2174V29.6852Z\" fill=\"#1C262C\"/><path d=\"M99.6639 17.5938H97.7422V48.0493H99.6639H104.605H123.681V41.9127H104.605V35.7761H122.995V29.6852H104.605V23.7304H123.681V17.5938H104.605H99.6639Z\" fill=\"#1C262C\"/><path d=\"M133.651 17.5938H126.789V48.0493H128.711H133.651H151.905V41.9127H133.651V17.5938Z\" fill=\"#1C262C\"/><path d=\"M161.51 17.5938H154.648V48.0493H161.51V17.5938Z\" fill=\"#1C262C\"/><path d=\"M198.38 17.5938H189.413L181.133 28.4578H180.63L172.029 17.5938H163.062L175.003 32.5037V33.0033L163.062 48.0493H172.029L180.355 37.0493H180.859L189.413 48.0493H198.38L186.486 33.14V32.6397L198.38 17.5938Z\" fill=\"#1C262C\"/><path d=\"M206.846 17.5938H199.984V48.0493H206.846V17.5938Z\" fill=\"#1C262C\"/><path d=\"M237.088 35.2536C236.477 34.0876 235.495 33.0946 234.137 32.2759C232.78 31.4578 230.958 30.8667 228.671 30.5031L220.07 29.1396C219.216 28.9885 218.529 28.8067 218.011 28.5942C217.492 28.3823 217.111 28.087 216.868 27.7078C216.623 27.3291 216.502 26.8521 216.502 26.2759C216.502 25.6096 216.7 25.0642 217.097 24.6398C217.493 24.216 218.156 23.8975 219.086 23.685C220.016 23.4731 221.305 23.3672 222.952 23.3672C224.995 23.3672 226.567 23.5114 227.664 23.7991C228.762 24.0875 229.517 24.5344 229.929 25.14C230.341 25.7469 230.546 26.5342 230.546 27.504V28.1403H237.454V27.8676C237.454 25.7469 236.951 23.8756 235.944 22.2538C234.938 20.6327 233.421 19.3751 231.392 18.4806C229.364 17.5872 226.779 17.1396 223.638 17.1396C221.045 17.1396 218.857 17.4123 217.073 17.9577C215.289 18.5031 213.848 19.2234 212.75 20.1168C211.652 21.0107 210.852 22.0187 210.348 23.1396C209.845 24.2611 209.594 25.3977 209.594 26.5486C209.594 28.2155 209.944 29.6329 210.646 30.799C211.348 31.9656 212.346 32.8978 213.643 33.5943C214.939 34.292 216.502 34.7916 218.332 35.0944L226.932 36.3219C228.488 36.5946 229.578 36.9431 230.204 37.3675C230.828 37.7919 231.141 38.474 231.141 39.4131C231.141 40.0801 230.958 40.6255 230.592 41.0499C230.226 41.4743 229.555 41.7846 228.58 41.9814C227.603 42.1789 226.201 42.2767 224.371 42.2767C222.297 42.2767 220.711 42.1407 219.613 41.8673C218.515 41.594 217.76 41.1702 217.349 40.5948C216.937 40.0193 216.731 39.2614 216.731 38.3223V37.5042H209.869V37.7769C209.869 40.1409 210.433 42.1181 211.562 43.7092C212.69 45.3002 214.337 46.4976 216.503 47.3006C218.668 48.103 221.291 48.5055 224.372 48.5055C227.604 48.5055 230.228 48.066 232.24 47.1871C234.253 46.3089 235.717 45.1491 236.632 43.7098C237.547 42.2711 238.004 40.732 238.004 39.0959C238.004 37.7023 237.699 36.4215 237.089 35.2549L237.088 35.2536Z\" fill=\"#1C262C\"/></g><defs><clipPath id=\"clip0_67_9\"><rect width=\"226\" height=\"40\" fill=\"white\" transform=\"translate(12 12)\"/></clipPath></defs></svg>",
"temperatures-icon.svg": "<svg width=\"40\" height=\"40\" viewBox=\"0 0 40 40\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"40\" height=\"40\" rx=\"20\" fill=\"#2878F5\"/><path d=\"M20 10V12\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M20.0001 16C19.085 15.9995 18.1974 16.3129 17.4854 16.8877C16.7733 17.4625 16.28 18.2641 16.0875 19.1588C15.8951 20.0534 16.0152 20.987 16.4278 21.8038C16.8405 22.6205 17.5207 23.2711 18.3551 23.647\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M10 20H12\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M28 22.54C28.7626 22.9803 29.3586 23.6599 29.6955 24.4734C30.0325 25.2869 30.0916 26.1888 29.8637 27.0394C29.6358 27.8899 29.1336 28.6415 28.435 29.1775C27.7365 29.7136 26.8805 30.0041 26 30.0041C25.1195 30.0041 24.2635 29.7136 23.565 29.1775C22.8664 28.6415 22.3642 27.8899 22.1363 27.0394C21.9084 26.1888 21.9675 25.2869 22.3045 24.4734C22.6415 23.6599 23.2374 22.9803 24 22.54V12C24 11.4696 24.2107 10.9609 24.5858 10.5858C24.9609 10.2107 25.4696 10 26 10C26.5304 10 27.0391 10.2107 27.4142 10.5858C27.7893 10.9609 28 11.4696 28 12V22.54Z\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M12.9302 12.9302L14.3402 14.3402\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M14.3402 25.6602L12.9302 27.0702\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/></svg>",
"Flow-icon.svg": "<svg width=\"40\" height=\"40\" viewBox=\"0 0 40 40\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"40\" height=\"40\" rx=\"20\" fill=\"#2878F5\"/><path d=\"M20 22L24 18\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M11.34 27C10.4622 25.4798 10.0001 23.7553 10 21.9999C9.99993 20.2445 10.462 18.52 11.3396 16.9997C12.2173 15.4795 13.4797 14.217 14.9999 13.3393C16.5201 12.4616 18.2446 11.9995 20 11.9995C21.7554 11.9995 23.4799 12.4616 25.0001 13.3393C26.5203 14.217 27.7827 15.4795 28.6604 16.9997C29.538 18.52 30.0001 20.2445 30 21.9999C29.9999 23.7553 29.5378 25.4798 28.66 27\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/></svg>",
"energy-icon.svg": "<svg width=\"40\" height=\"40\" viewBox=\"0 0 40 40\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"40\" height=\"40\" rx=\"20\" fill=\"#2878F5\"/><path d=\"M23.9142 12.0002C24.0273 11.6795 24.0282 11.33 23.9166 11.0088C23.805 10.6876 23.5877 10.4138 23.3001 10.2324C23.0125 10.051 22.6719 9.9726 22.3339 10.0102C21.996 10.0477 21.6809 10.199 21.4402 10.4392L12.4402 19.4392C12.2303 19.6489 12.0874 19.9161 12.0294 20.2071C11.9714 20.4981 12.0011 20.7997 12.1145 21.0738C12.228 21.3479 12.4202 21.5823 12.6668 21.7472C12.9135 21.912 13.2035 22.0001 13.5002 22.0002H17.5022C17.582 22.0003 17.6607 22.0195 17.7316 22.0563C17.8026 22.093 17.8636 22.1462 17.9098 22.2115C17.9559 22.2767 17.9857 22.352 17.9967 22.4311C18.0078 22.5102 17.9997 22.5908 17.9732 22.6662L16.0862 28.0002C15.973 28.3209 15.9722 28.6706 16.0838 28.9919C16.1955 29.3131 16.4131 29.5869 16.7008 29.7683C16.9886 29.9497 17.3294 30.0278 17.6675 29.99C18.0055 29.9522 18.3206 29.8006 18.5612 29.5602L27.5612 20.5602C27.7707 20.3503 27.9134 20.0831 27.9711 19.7922C28.0289 19.5013 27.9991 19.1998 27.8856 18.9258C27.772 18.6519 27.5798 18.4177 27.3332 18.253C27.0866 18.0882 26.7967 18.0002 26.5002 18.0002H22.5032C22.4231 18.0003 22.3442 17.9811 22.273 17.9444C22.2019 17.9076 22.1406 17.8543 22.0943 17.789C22.0481 17.7236 22.0182 17.6481 22.0072 17.5688C21.9962 17.4894 22.0044 17.4086 22.0312 17.3332L23.9142 12.0002Z\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/></svg>",
"sun-power-icon.svg": "<svg width=\"40\" height=\"40\" viewBox=\"0 0 40 40\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"40\" height=\"40\" rx=\"20\" fill=\"#2878F5\"/><path d=\"M24 20C24 22.2091 22.2091 24 20 24C17.7909 24 16 22.2091 16 20C16 17.7909 17.7909 16 20 16C22.2091 16 24 17.7909 24 20Z\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M20 10V12\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M20 28V30\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M12.9302 12.9302L14.3402 14.3402\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M25.6602 25.6602L27.0702 27.0702\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M10 20H12\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M28 20H30\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M14.3402 25.6602L12.9302 27.0702\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M27.0702 12.9302L25.6602 14.3402\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/></svg>",
"last24hr-icon.svg": "<svg width=\"40\" height=\"40\" viewBox=\"0 0 40 40\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"40\" height=\"40\" rx=\"20\" fill=\"#2878F5\"/><path d=\"M20 15V20L24 22\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M24 16H29V11\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/><path d=\"M29 16L26.7 13.7C24.8976 11.971 22.4977 11.0038 20 11C18.22 11 16.4799 11.5278 14.9999 12.5168C13.5198 13.5057 12.3663 14.9113 11.6851 16.5558C11.0039 18.2004 10.8257 20.01 11.1729 21.7558C11.5202 23.5016 12.3774 25.1053 13.636 26.364C14.8947 27.6226 16.4984 28.4798 18.2442 28.8271C19.99 29.1743 21.7996 28.9961 23.4442 28.3149C25.0887 27.6337 26.4943 26.4802 27.4832 25.0001C28.4722 23.5201 29 21.78 29 20\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#F3F3F3\"/></svg>",
"live-icon-active.svg": "<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12.1851 5.8208C13.0273 6.66449 13.5003 7.80791 13.5003 9.00005C13.5003 10.1922 13.0273 11.3356 12.1851 12.1793\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M14.3062 3.69971C15.7108 5.10598 16.4998 7.01233 16.4998 8.99996C16.4998 10.9876 15.7108 12.8939 14.3062 14.3002\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M3.69365 14.3002C2.28899 12.8939 1.5 10.9876 1.5 8.99996C1.5 7.01233 2.28899 5.10598 3.69365 3.69971\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M5.8148 12.1793C4.97256 11.3356 4.49951 10.1922 4.49951 9.00005C4.49951 7.80791 4.97256 6.66449 5.8148 5.8208\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M10.5 9C10.5 9.82843 9.82843 10.5 9 10.5C8.17157 10.5 7.5 9.82843 7.5 9C7.5 8.17157 8.17157 7.5 9 7.5C9.82843 7.5 10.5 8.17157 10.5 9Z\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/></svg>",
"live-icon-normal.svg": "<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12.1851 5.8208C13.0273 6.66449 13.5003 7.80791 13.5003 9.00005C13.5003 10.1922 13.0273 11.3356 12.1851 12.1793\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M14.3062 3.69971C15.7108 5.10598 16.4998 7.01233 16.4998 8.99996C16.4998 10.9876 15.7108 12.8939 14.3062 14.3002\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M3.69365 14.3002C2.28899 12.8939 1.5 10.9876 1.5 8.99996C1.5 7.01233 2.28899 5.10598 3.69365 3.69971\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M5.8148 12.1793C4.97256 11.3356 4.49951 10.1922 4.49951 9.00005C4.49951 7.80791 4.97256 6.66449 5.8148 5.8208\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M10.5 9C10.5 9.82843 9.82843 10.5 9 10.5C8.17157 10.5 7.5 9.82843 7.5 9C7.5 8.17157 8.17157 7.5 9 7.5C9.82843 7.5 10.5 8.17157 10.5 9Z\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/></svg>",
"History-icon-active.svg": "<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12 9.75V11.4L13.2 12.15\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M2.25 9H4.8435\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M2.25 14.25H5.124\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M2.25 3.75H15.75\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M16.5 11.25C16.5 13.7353 14.4853 15.75 12 15.75C9.51472 15.75 7.5 13.7353 7.5 11.25C7.5 8.76472 9.51472 6.75 12 6.75C14.4853 6.75 16.5 8.76472 16.5 11.25Z\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/></svg>",
"History-icon-normal.svg": "<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12 9.75V11.4L13.2 12.15\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M2.25 9H4.8435\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M2.25 14.25H5.124\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M2.25 3.75H15.75\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M16.5 11.25C16.5 13.7353 14.4853 15.75 12 15.75C9.51472 15.75 7.5 13.7353 7.5 11.25C7.5 8.76472 9.51472 6.75 12 6.75C14.4853 6.75 16.5 8.76472 16.5 11.25Z\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/></svg>",
"About-icon-active.svg": "<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><g clip-path=\"url(#clip0_67_509)\"><path d=\"M16.5 9C16.5 13.1421 13.1421 16.5 9 16.5C4.85786 16.5 1.5 13.1421 1.5 9C1.5 4.85786 4.85786 1.5 9 1.5C13.1421 1.5 16.5 4.85786 16.5 9Z\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M9 12V9\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/><path d=\"M9 6H9.0075\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#FDFDFD\"/></g><defs><clipPath id=\"clip0_67_509\"><rect width=\"18\" height=\"18\" fill=\"white\"/></clipPath></defs></svg>",
"About-icon-normal.svg": "<svg width=\"18\" height=\"18\" viewBox=\"0 0 18 18\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M16.5 9C16.5 13.1421 13.1421 16.5 9 16.5C4.85786 16.5 1.5 13.1421 1.5 9C1.5 4.85786 4.85786 1.5 9 1.5C13.1421 1.5 16.5 4.85786 16.5 9Z\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M9 12V9\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M9 6H9.0075\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/></svg>",
"Login-icon.svg": "<svg width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M17 8C17 10.7614 14.7614 13 12 13C9.23858 13 7 10.7614 7 8C7 5.23858 9.23858 3 12 3C14.7614 3 17 5.23858 17 8Z\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/><path d=\"M20 21C20 18.8783 19.1571 16.8434 17.6569 15.3431C16.1566 13.8429 14.1217 13 12 13C9.87827 13 7.84344 13.8429 6.34315 15.3431C4.84285 16.8434 4 18.8783 4 21\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke=\"#1C262C\"/></svg>"
}


def _asset(name):
    """The exported SVG, inline so it stays crisp and needs no extra file."""
    if name in _ASSET_SVG:
        return _ASSET_SVG[name]
    path = os.path.join(ASSETS, name)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def _asset_b64(name):
    svg = _asset(name)
    return _b64.b64encode(svg.encode("utf-8")).decode() if svg else ""


if os.path.exists(HERO):
    _mime = "image/jpeg" if HERO.lower().endswith((".jpg", ".jpeg")) else "image/png"
    _hero_b64 = _b64.b64encode(open(HERO, "rb").read()).decode()
    # Fixed, so the render stays put while the cards scroll over it.
    _hero_css = ("background-image:url('data:" + _mime + ";base64," + _hero_b64 +
                 "');background-size:cover;background-position:center left;"
                 "background-repeat:no-repeat;background-attachment:fixed;")
else:
    _hero_css = ("background-image:linear-gradient(170deg,#E9ECF2 0%,"
                 "#F4F6F9 30%,#FFFFFF 58%);")

_NAV_ICONS = {"live": ("live-icon-normal.svg", "live-icon-active.svg"),
              "hist": ("History-icon-normal.svg", "History-icon-active.svg"),
              "about": ("About-icon-normal.svg", "About-icon-active.svg")}
_nav_icon_css = ""
for _k, (_n, _a) in _NAV_ICONS.items():
    for _kind, _f in (("secondary", _n), ("primary", _a)):
        _b = _asset_b64(_f)
        if _b:
            _nav_icon_css += (
                f'.st-key-nav_{_k} button[kind="{_kind}"]::before{{content:"";'
                f'display:inline-block;width:19px;height:19px;margin-right:11px;'
                f'flex:0 0 19px;background:url("data:image/svg+xml;base64,{_b}")'
                f' center/contain no-repeat;}}')

st.markdown(f"""<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
  header[data-testid="stHeader"]{{background:transparent!important;height:0!important;}}
  #MainMenu,footer{{visibility:hidden;}}
  html,body,[class*="css"]{{font-family:'Inter',-apple-system,sans-serif!important;color:{TEXT};}}
  .stApp{{{_hero_css}}}
  .block-container{{padding-top:1.1rem!important;padding-bottom:2rem;max-width:1560px;}}
  /* A soft veil over the content column. The render stays visible down the
     left side and around the cards, but small captions that sit outside a
     card are still readable against it. */
  div[data-testid="stMainBlockContainer"]{{
    background:linear-gradient(90deg,rgba(255,255,255,0) 0,
      rgba(255,255,255,.72) 90px,rgba(255,255,255,.80) 100%);
    border-radius:24px;}}

  /* ── Left card (Streamlit's sidebar) ───────────────────────── */
  /* The card is the only way to reach History and About, so it must not be
     collapsible: a folded sidebar left the app looking like it had lost half
     its navigation. */
  section[data-testid="stSidebar"]{{background:transparent!important;border:none!important;
    transform:none!important;visibility:visible!important;
    min-width:320px!important;width:320px!important;}}
  div[data-testid="stSidebarCollapseButton"],
  div[data-testid="stSidebarCollapsedControl"],
  div[data-testid="stSidebarResizeHandle"]{{display:none!important;}}
  section[data-testid="stSidebar"] > div{{background:transparent!important;padding-top:2px;}}
  section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"]
    > div > div[data-testid="stVerticalBlock"]{{
    background:#fff;border-radius:{CARD_R};box-shadow:{SHADOW};
    padding:18px 16px 16px;gap:.55rem;}}
  .hx-status{{font-size:.82rem;font-weight:700;color:{TEXT};line-height:1.9;}}
  .hx-status .sub{{font-weight:500;color:{MUTED};}}
  .hx-rule{{border:none;border-top:1px solid {BORDER};margin:12px 0 14px;}}

  /* Nav buttons */
  section[data-testid="stSidebar"] .stButton button{{
    width:100%;justify-content:flex-start;text-align:left;
    background:#fff;color:{TEXT};border:1px solid {BORDER};
    border-radius:13px;padding:9px 14px;font-weight:600;font-size:.92rem;
    box-shadow:none;transition:border-color .12s ease,background .12s ease;}}
  section[data-testid="stSidebar"] .stButton button:hover{{border-color:{BLUE};color:{BLUE};}}
  section[data-testid="stSidebar"] .stButton button[kind="primary"]{{
    background:{BLUE};color:#fff;border-color:{BLUE};}}
  section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover{{
    background:{BLUE};color:#fff;}}

  /* Gauges | Kompakt — a segmented control built from st.radio */
  section[data-testid="stSidebar"] div[role="radiogroup"]{{
    display:flex;gap:0;background:#fff;border:1px solid {BORDER};
    border-radius:13px;padding:3px;}}
  section[data-testid="stSidebar"] div[role="radiogroup"] label{{
    flex:1;justify-content:center;margin:0!important;padding:6px 4px;
    border-radius:10px;font-size:.84rem;font-weight:600;color:{MUTED};
    cursor:pointer;transition:background .12s ease,color .12s ease;}}
  section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked){{background:{BG2};color:{TEXT};}}
  section[data-testid="stSidebar"] div[role="radiogroup"] label > div{{
    display:flex;align-items:center;justify-content:center;gap:0;}}
  section[data-testid="stSidebar"] div[role="radiogroup"] label > div > div:not([data-testid]){{
    display:none!important;}}
  section[data-testid="stSidebar"] div[role="radiogroup"] label p{{
    margin:0;font-size:.84rem;font-weight:600;}}

  /* ── Top bar ───────────────────────────────────────────────── */
  .st-key-lang_en button,.st-key-lang_sv button,.st-key-acct button{{
    border:1px solid {BORDER};background:#fff;color:{MUTED};font-weight:600;
    font-size:.88rem;padding:6px 14px;min-height:0;border-radius:999px;
    box-shadow:{SHADOW};width:100%;}}
  .st-key-lang_en button[kind="primary"],.st-key-lang_sv button[kind="primary"]{{
    color:{TEXT};background:#fff;border-color:{BLUE};}}

  /* ── Section header bar ────────────────────────────────────── */
  .hx-sec{{display:flex;align-items:center;gap:15px;background:#fff;
    border-radius:{CARD_R};box-shadow:{SHADOW};padding:13px 22px;
    margin:22px 0 -4px;position:relative;z-index:2;}}
  .hx-sec svg{{width:34px;height:34px;flex:0 0 34px;}}
  .hx-sec .ttl{{font-size:.95rem;font-weight:800;letter-spacing:.06em;
    text-transform:uppercase;color:{TEXT};}}

  /* ── Panel card wrapping a row of gauges or charts ─────────── */
  /* The panel card. Streamlit's own container border is switched off — the
     card is the white background plus the shadow, drawn here. */
  /* The panel card. Only the innermost wrapper that holds a row of dials —
     st.fragment wraps the whole tab in one too, and without the :not() that
     outer wrapper becomes one giant card around everything. */
  div[data-testid="stLayoutWrapper"]:has(div[data-testid="stBidiComponentRegular"]):not(
    :has(div[data-testid="stLayoutWrapper"] div[data-testid="stBidiComponentRegular"])){{
    background:#fff!important;border:none!important;border-radius:{CARD_R};
    box-shadow:{SHADOW};padding:26px 12px 10px;margin-top:0;}}
  div[data-testid="stLayoutWrapper"]:has(div[data-testid="stBidiComponentRegular"]) > div{{
    border:none!important;}}
  div[data-testid="stPlotlyChart"]{{
    background:#fff;border-radius:{CARD_R};box-shadow:{SHADOW};padding:12px 10px;}}
  div[data-testid="stBidiComponentRegular"],
  div[data-testid="stBidiComponentRegular"] > iframe{{
    background:transparent!important;border:none!important;}}
  /* Streamlit's own toolbar — not part of the design */
  div[data-testid="stToolbar"]{{display:none!important;}}

  /* Gauge heading: label, then the big reading above the dial */
  .hx-g-lbl{{font-size:.80rem;font-weight:700;letter-spacing:.055em;
    text-transform:uppercase;color:{TEXT};text-align:center;}}
  .hx-g-val{{font-size:2.45rem;font-weight:400;color:{TEXT};text-align:center;
    line-height:1.15;margin-top:4px;}}
  .hx-g-val span{{font-size:1.05rem;font-weight:400;color:{MUTED};margin-left:4px;}}
  /* Small captions for the charts. They sit outside a card, straight on the
     render, so they carry their own backing. */
  .hx-cap{{display:inline-block;background:#fff;border-radius:10px;
    padding:5px 12px;margin:14px 0 6px;font-size:.72rem;font-weight:700;
    letter-spacing:.07em;text-transform:uppercase;color:{TEXT};
    box-shadow:{SHADOW};}}

  /* Metric tiles */
  div[data-testid="metric-container"]{{background:{BG2};border:1px solid {BORDER};border-radius:12px;padding:14px 18px;}}
  div[data-testid="metric-container"] label{{font-size:.72rem!important;color:{TEXT}!important;text-transform:uppercase;letter-spacing:.08em;font-weight:700!important;}}
  div[data-testid="metric-container"] [data-testid="stMetricValue"]{{color:{TEXT}!important;font-size:1.5rem!important;font-weight:700!important;}}

  .section-title{{font-size:.68rem;font-weight:700;color:{TEXT};text-transform:uppercase;
    letter-spacing:.1em;margin:20px 0 10px;border-left:3px solid {BLUE};padding-left:10px;}}

  .status-dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle;}}
  .ts-text{{font-size:.85rem;color:{TEXT};vertical-align:middle;font-weight:500;}}

  /* Plotly toolbar — discreet, but never hidden: Zoom out and Reset axes
     live there, and without them a zoom is a one-way street. */
  .modebar{{
    opacity:.4!important;transition:opacity .15s ease!important;
    background:rgba(255,255,255,.9)!important;
    border-radius:6px!important;
  }}
  .js-plotly-plot:hover .modebar,.modebar:hover{{opacity:1!important;}}
  .modebar-btn .icon path{{fill:{MUTED}!important;}}
  .modebar-btn:hover .icon path,
  .modebar-btn.active .icon path{{fill:{BLUE}!important;}}
  .rangeselector text{{font-family:Inter!important;}}
  {_nav_icon_css}
</style>
""", unsafe_allow_html=True)

# ── DB ────────────────────────────────────────────────────────
@st.cache_resource
def get_db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
db = get_db()

# ── Query helpers ─────────────────────────────────────────────
# PostgREST caps every response at 1000 rows, so a raw pull has to be
# paginated — and Supabase caps each statement at a few seconds, so every
# page must also be cheap for Postgres to plan. Three rules:
#
#  1. Page on created_at, never on OFFSET and never on id alone.
#     OFFSET makes Postgres walk and discard every skipped row. Paging on
#     `id > last_id` looks cheaper but is worse here: with a created_at
#     filter the planner walks the primary key from the start of the table
#     and throws away everything older than the window — which on a table
#     this size hits the statement timeout. created_at is the indexed
#     column the window is expressed in, so seeking on it is what the
#     index is for.
#
#  2. created_at is NOT unique — all sensors in one MQTT message share a
#     timestamp — so the cursor is inclusive (gte) and rows already seen
#     are dropped by id. Overlap costs one message per page.
#
#  3. Aggregate in Postgres when the helper functions from
#     supabase_perf.sql are installed — see _rpc(). Without them the app
#     still works, but on a large table the raw path may simply be too
#     slow for Supabase's statement timeout, which is what _db_error()
#     explains rather than dumping a Postgres error code at the user.
PAGE = 1000
ROW_BUDGET = 400_000      # stop runaway raw pulls before the browser dies


def _is_timeout(e) -> bool:
    txt = str(e).lower()
    return "57014" in txt or "statement timeout" in txt or "canceling statement" in txt


def _db_error(e):
    """Show a DB failure in terms the operator can act on."""
    if _is_timeout(e):
        st.error(T["err_timeout"])
    else:
        st.error(f"DB: {e}")


@st.cache_resource
def _rpc_flags():
    """Remembers which helper functions exist, so a missing one is probed
    once per server process instead of on every rerun."""
    return {}


def _rpc(fn: str, params: dict):
    """Call a Postgres function from supabase_perf.sql.

    Returns (status, data) where status is:
      "ok"      — it ran; data is the result
      "missing" — not installed; the caller should fall back to raw rows
      "timeout" — installed but too slow; falling back would only stall
                  again, so the caller should surface it instead
      "error"   — anything else; treated like "missing"
    Never raises: a broken fast path must not take the app down.
    """
    flags = _rpc_flags()
    if flags.get(fn) is False:
        return "missing", None
    try:
        res = db.rpc(fn, params).execute()
        flags[fn] = True
        return "ok", res.data
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in
               ("does not exist", "could not find", "pgrst202", "permission")):
            flags[fn] = False          # not installed — stop probing
            return "missing", None
        if _is_timeout(e):
            return "timeout", None
        return "error", None


def _fetch_rows(t_from_iso, t_to_iso=None, sensors=None, page=PAGE):
    """Raw sensor_readings over a time window, paginated on created_at."""
    rows, seen, cursor = [], set(), t_from_iso
    try:
        while True:
            q = (db.table("sensor_readings")
                   .select("id,created_at,sensor,value")
                   .gte("created_at", cursor))
            if t_to_iso:
                q = q.lte("created_at", t_to_iso)
            if sensors:
                q = q.in_("sensor", list(sensors))
            res = q.order("created_at", desc=False).limit(page).execute()
            batch = res.data
            if not batch:
                break
            fresh = [r for r in batch if r["id"] not in seen]
            if not fresh:
                break                  # only rows we already have — done
            for r in fresh:
                seen.add(r["id"])
            rows.extend(fresh)
            if len(batch) < page or len(rows) >= ROW_BUDGET:
                break
            cursor = batch[-1]["created_at"]
    except Exception as e:
        _db_error(e)
        return []
    return rows


def _rows_to_df(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop(columns=["id"], errors="ignore")
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df.sort_values("created_at")


# Points kept per sensor when bucketing. The charts are ~1000 px wide, so
# more than this is detail nobody can see — and megabytes nobody wants to
# wait for.
HIST_MAX_POINTS = 900

# Finest bucket worth asking for. The bridge stores at most one sample per
# sensor per second, so 1 s is the real floor of the data — asking for less
# would just return the same points with more rows. Bucketing still applies
# at every level, so the raw-row path is never used from the UI.
MIN_BUCKET_SECONDS = 1


def bucket_seconds_for(t_from, t_to, max_points: int = HIST_MAX_POINTS) -> int:
    span = max(1.0, (t_to - t_from).total_seconds())
    return max(MIN_BUCKET_SECONDS, int(span // max_points))


def fmt_resolution(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{round(seconds / 60)} min"
    return f"{seconds / 3600:.1f} h"


# Which series each Live chart actually draws. Everything else the database
# holds is left where it is.
LIVE_POWER_SENSORS = ["power", "heat_power"]
LIVE_SUN_SENSORS   = ["irradiance", "power", "heat_power"]
LIVE_DAY_SENSORS   = ["temp_forward", "temp_supply", "temp_return", "temp_tank",
                      "temp_right_coll", "temp_left_coll",
                      "flow", "pressure", "temp_difference"]


# ── Sensor data ───────────────────────────────────────────────
@st.cache_data(ttl=25)
def fetch_live() -> pd.DataFrame:
    """Every sensor, last 20 minutes.

    Paged through _fetch_rows. A plain .execute() here hit PostgREST's
    1000-row ceiling, and since the rows came back oldest-first the cap threw
    away the NEWEST half of the window — roughly 20 sensors x 90 samples is
    1900 rows, so the Live tab was showing values about ten minutes behind
    reality while still calling itself LIVE."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    try:
        return _rows_to_df(_fetch_rows(since))
    except Exception as e:
        st.error(f"DB: {e}"); return pd.DataFrame()

# ── Data-down alert ───────────────────────────────────────────
ALERT_AFTER_MIN = 30   # minutes without any sensor data before emailing

@st.cache_data(ttl=25)
def fetch_last_reading_ts():
    """Latest sensor timestamp of ANY age (UTC). fetch_live() only looks back
    20 min and is empty during a real outage, so the down-alert needs this."""
    try:
        res = db.table("sensor_readings").select("created_at") \
            .order("created_at", desc=True).limit(1).execute()
        if not res.data:
            return None
        return pd.to_datetime(res.data[0]["created_at"], utc=True)
    except Exception:
        return None

@st.cache_resource
def _alert_state():
    """Shared across all browser sessions in this server process, so the outage
    email is sent once per outage rather than once per viewer/rerun."""
    return {}

def check_data_alert(age_min: float, last_ts):
    """Email once when data has been missing ≥ ALERT_AFTER_MIN; re-arm when it returns.
    NOTE: only runs while the app is open in a browser — Streamlit is not a
    background service, so this is best-effort, not guaranteed monitoring."""
    state = _alert_state()
    if age_min >= ALERT_AFTER_MIN:
        key = last_ts.isoformat()          # stable during an outage (no new data)
        if state.get("outage_alerted") != key:
            send_alert_email(age_min)
            state["outage_alerted"] = key
    elif age_min < 15:                      # data flowing again → re-arm
        state.pop("outage_alerted", None)

@st.cache_data(ttl=120, show_spinner=False)
def fetch_history(hours_back: int) -> pd.DataFrame:
    """Raw readings for the last N hours (Live tab). Still raw — the live
    charts want full resolution — but keyset-paginated, so a 7-day pull no
    longer pays the OFFSET penalty on every page."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()
    return _rows_to_df(_fetch_rows(since))

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_history_range(date_from, date_to,
                       max_points: int = HIST_MAX_POINTS,
                       sensors=None) -> pd.DataFrame:
    """Readings for a date range, aggregated into time buckets by Postgres.

    A month of data is ~250 000 raw rows = 250 sequential requests; bucketed
    it is ~900 points per sensor in ONE request. Same curve on screen.

    max_points=0 asks for untouched raw rows — slow, but the only way to see
    short spikes (pump cycling, stagnation) in a long window.
    Falls back to raw rows if history_bucketed_json() is not installed.
    """
    if max_points <= 0:
        return _rows_to_df(_fetch_rows(date_from.isoformat(), date_to.isoformat(),
                                       sensors=sensors))
    bucket = bucket_seconds_for(date_from, date_to, max_points)
    status, data = _rpc("history_bucketed_json", {
        "t_from":         date_from.isoformat(),
        "t_to":           date_to.isoformat(),
        "bucket_seconds": bucket,
        # Only the series the caller is going to draw. Asking for all 21 when
        # a chart plots two is the single most expensive habit in this app.
        "sensors":        list(sensors) if sensors else None,
    })
    if status == "ok":
        if isinstance(data, str):
            data = json.loads(data)
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data).rename(
            columns={"b": "created_at", "s": "sensor", "v": "value"})
        df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
        df["value"] = df["value"].astype(float)
        return df.sort_values("created_at")
    if status == "timeout":
        st.error(T["err_rpc_timeout"])
        return pd.DataFrame()
    return _rows_to_df(_fetch_rows(date_from.isoformat(), date_to.isoformat(),
                                   sensors=sensors))


@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_bucketed(hours_back: int, max_points: int = 900,
                          sensors=None) -> pd.DataFrame:
    """Last N hours, every sensor, bucketed by Postgres.

    The Live tab used to call fetch_history(168), which pulls RAW rows. Since
    the bridge went to 1-second resolution seven days is close to a million
    rows, and _fetch_rows stops at ROW_BUDGET. It pages oldest-first, so that
    cut-off threw away the NEWEST days without a word: the charts ended on
    whichever day the budget ran out, and the app announced "no data in the
    last 24 hours" while readings were arriving normally."""
    t_to = datetime.now(timezone.utc)
    t_from = t_to - timedelta(hours=hours_back)
    return fetch_history_range(t_from, t_to, max_points, sensors)


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_window_stats(date_from, date_to) -> pd.DataFrame:
    """Exact per-sensor min/max/mean over the window.

    Bucket averages flatten real peaks, so the summary table asks Postgres
    for the true extremes instead of deriving them from the plotted points.
    Empty DataFrame when the helper function is not installed — the caller
    then falls back to aggregating whatever it has.
    """
    status, data = _rpc("sensor_window_stats", {
        "t_from": date_from.isoformat(), "t_to": date_to.isoformat()})
    if status != "ok" or not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_daily_summary(days: int = 90) -> pd.DataFrame:
    """Daily kWh + peak irradiance for the overview strip.

    This is what made the History tab slow to open: 90 days of raw power and
    irradiance readings is roughly three quarters of a million rows, fetched
    1000 at a time, just to draw 90 bars. daily_energy_summary() does the
    same integration in Postgres and returns 90 rows.
    """
    status, data = _rpc("daily_energy_summary", {"days_back": days})
    if status == "timeout":
        st.error(T["err_rpc_timeout"])
        return pd.DataFrame()
    if status == "ok":
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["day"]).dt.date
        df["kwh"] = df["kwh"].astype(float)
        df["peak_irr"] = df["peak_irr"].astype(float)
        return df[["date", "kwh", "peak_irr"]].sort_values("date")
    return _daily_summary_raw(days)


def _daily_summary_raw(days: int) -> pd.DataFrame:
    """Fallback for when supabase_perf.sql has not been applied yet.
    Same result, but it has to download every reading to get there."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    df = _rows_to_df(_fetch_rows(since, sensors=["power", "irradiance"]))
    if df.empty:
        return pd.DataFrame()
    df["date"] = df["created_at"].dt.tz_convert(ZoneInfo("Europe/Stockholm")).dt.date
    out = []
    for date, grp in df.groupby("date"):
        pwr = grp[grp["sensor"] == "power"].sort_values("created_at")
        irr = grp[grp["sensor"] == "irradiance"]
        if len(pwr) >= 2:
            import numpy as np
            times = (pwr["created_at"] - pwr["created_at"].iloc[0]) \
                        .dt.total_seconds().values / 3600.0
            fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
            kwh = float(max(0.0, fn(pwr["value"].values.astype(float), times)))
        else:
            kwh = 0.0
        peak_irr = float(irr["value"].max()) if not irr.empty else 0.0
        out.append({"date": date, "kwh": round(kwh, 2), "peak_irr": round(peak_irr, 0)})
    return pd.DataFrame(out).sort_values("date")


@st.cache_data(ttl=60, show_spinner=False)
def fetch_today_power() -> pd.DataFrame:
    """All power readings since local midnight — used for energy integration."""
    now_swe   = datetime.now(SWE)
    today_utc = now_swe.replace(hour=0, minute=0, second=0, microsecond=0) \
                       .astimezone(timezone.utc)
    return _rows_to_df(_fetch_rows(today_utc.isoformat(), sensors=["power"]))


@st.cache_data(ttl=1800)
def fetch_strang(days_back: int = 1):
    """
    Fetch DNI+GHI from SMHI STRÅNG via the new Open Data API.
    New URL: opendata-download-metanalys.smhi.se/api/category/strang1g/...
    Parameter 116=GHI, 118=DNI
    Time format: YYYYMMDDhh  (hour appended)
    Returns (DataFrame, errors_dict).
    """
    now_swe = datetime.now(SWE)
    # from = yesterday 00:00, to = today current hour
    from_dt = (now_swe - timedelta(days=days_back)).strftime("%Y%m%d") + "00"
    to_dt   = now_swe.strftime("%Y%m%d%H")
    base    = "https://opendata-download-metanalys.smhi.se/api/category/strang1g/version/1"
    rows, errors = [], {}
    for par, name in [("116", "ghi_strang"), ("118", "dni_strang")]:
        url = (f"{base}/geotype/point"
               f"/lon/{SITE_LON}/lat/{SITE_LAT}"
               f"/parameter/{par}/data.json"
               f"?from={from_dt}&to={to_dt}&interval=hourly")
        try:
            r = requests.get(url, timeout=15)
            if r.status_code != 200:
                errors[name] = f"HTTP {r.status_code} · {url}"
                continue
            data = r.json()
            # Response is a list of {date_time, value} or wrapped in timeSeries
            items = data if isinstance(data, list) else data.get("timeSeries", [])
            if not items:
                errors[name] = f"Empty JSON response · keys: {list(data.keys()) if isinstance(data, dict) else 'list'}"
                continue
            parsed = 0
            for item in items:
                try:
                    # date_time is epoch ms or ISO string
                    dt_raw = item.get("date_time") or item.get("dateTime") or item.get("t")
                    val    = item.get("value") or item.get("v")
                    if dt_raw is None or val is None:
                        continue
                    if isinstance(dt_raw, (int, float)):
                        ts = pd.to_datetime(dt_raw, unit="ms", utc=True)
                    else:
                        ts = pd.to_datetime(dt_raw, utc=True)
                    rows.append({"created_at": ts, "sensor": name, "value": float(val)})
                    parsed += 1
                except Exception:
                    continue
            if parsed == 0:
                errors[name] = f"Could not parse response. Sample: {str(items[:2])[:200]}"
        except requests.exceptions.ConnectionError as e:
            errors[name] = f"Connection error: {e}"
        except Exception as e:
            errors[name] = str(e)
    df = pd.DataFrame(rows).sort_values("created_at") if rows else pd.DataFrame()
    return df, errors

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
                # iterrows over a day of samples is slow for no reason
                to_insert = [
                    {"created_at": ts.isoformat(), "sensor": f"smhi_{key}",
                     "value": float(val)}
                    for ts, val in zip(df["created_at"], df["value"])
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

SMHI_TEMP_URL = ("https://opendata-download-metobs.smhi.se/api/version/latest"
                 "/parameter/1/station/62040/period/latest-hour/data.json")


@st.cache_data(ttl=900, show_spinner=False)
def fetch_outside_temp():
    """Outside temperature for the Live tab, without blocking the render.

    The Live tab used to call fetch_smhi_and_store() for this one number. That
    function fetches four SMHI endpoints with a 15-second timeout each and
    upserts a whole day of rows back into Supabase — up to a minute of frozen
    page every ten minutes, to fill a single gauge. Here we read what SMHI data
    we already stored, and only reach out to SMHI, for the temperature alone
    and with a short timeout, when that stored value has gone stale."""
    try:
        res = (db.table("smhi_readings").select("created_at,value")
               .eq("sensor", "smhi_temperature")
               .order("created_at", desc=True).limit(1).execute())
        if res.data:
            ts = pd.to_datetime(res.data[0]["created_at"], utc=True)
            if datetime.now(timezone.utc) - ts < timedelta(hours=3):
                return float(res.data[0]["value"])
    except Exception:
        pass
    try:
        r = requests.get(SMHI_TEMP_URL, timeout=6)
        if r.status_code == 200:
            vals = r.json().get("value") or []
            if vals:
                return float(vals[-1]["value"])
    except Exception:
        pass
    return None


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
# Thermal power from flow and temperature difference.
#
# The flow sensor reports LITRES PER MINUTE. Every formula in this file used
# to divide by 3600, which is the conversion for cubic metres per hour — the
# unit the old pipeline wrongly labelled this sensor with. That made every
# computed power, and therefore every efficiency, 16.7 times too high, which
# is why the efficiency filter threw away all of its own samples.
#
#   mass flow [kg/s] = flow [l/min] x rho [kg/m3] / 60000
#   P [kW]           = mass flow x cp [J/kgK] x dT [K] / 1000
RHO_HTF = 1000.0            # kg/m3
CP_HTF  = 3800.0            # J/kgK, 30% glycol. Pure water is 4186.
FLOW_MIN_LMIN = 1.0         # below this the loop is not circulating


def thermal_power_kw(flow_lmin, dt_k, cp=CP_HTF, rho=RHO_HTF):
    """kW carried by the heat transfer fluid. flow in l/min, dt in K."""
    return flow_lmin * rho * cp * dt_k / 60000.0 / 1000.0


def pick_sensor(df, *names):
    """First of these sensor names that carries data.

    The PLC was replaced and renamed its tags: temp_forward became
    temp_supply, power became heat_power. Both generations sit in the same
    table, so every analysis has to accept either."""
    for n in names:
        sub = df[df["sensor"] == n]
        if not sub.empty:
            return sub, n
    return df.iloc[0:0], names[0]


def naive_swe(s):
    """Return timestamps as tz-naive Swedish local wall-clock for Plotly.

    Data is stored in UTC. Plotly.js renders datetimes in UTC and ignores the
    timezone offset, so a tz-aware timestamp would display 2h behind (the stored
    UTC time). We convert to the site's local time (Örkelljunga / Europe/Stockholm)
    and drop the tz, so Plotly shows the correct local wall-clock for every viewer
    regardless of where they are. Safe on tz-naive input too."""
    try:
        return s.dt.tz_convert(SWE).dt.tz_localize(None)
    except (TypeError, AttributeError):
        return s  # already tz-naive

def latest_val(df, sensor):
    sub = df[df["sensor"] == sensor]
    return float(sub["value"].iloc[-1]) if not sub.empty else None

def fmt(val, decimals=1, unit=""):
    return f"{val:.{decimals}f} {unit}".strip() if val is not None else "—"

def heat_energy_kwh(val):
    """The heat meter's cumulative counter, in kWh.

    It was read as MWh and multiplied by 1000. The three-method panel settled
    it: over one window M1 integrated 53.701 kWh while the counter moved
    53.730 — a ratio of 1.0005, not 1000. The counter is already in kWh."""
    return val

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
    if irr >= 1000:    return T["clear"],    "☀️",  AMBER   # >1000 fully possible in Sweden
    if irr >= 700:     return T["clear"],    "☀️",  AMBER
    if irr >= 500:     return T["sunny"],    "🌤",  AMBER
    if irr >= 300:     return T["partly"],   "⛅",  SLATE
    if irr >= 100:     return T["cloudy"],   "🌥",  MUTED
    if irr >= 20:      return T["overcast"], "☁️",  MUTED
    return                    T["night"],    "🌙",  MUTED

def integrate_power(df) -> float | None:
    """Trapezoid integration of power → kWh. Handles both full and pre-filtered DataFrames."""
    if df is None or df.empty:
        return None
    # Filter to power sensor if multi-sensor df, otherwise use as-is
    if "sensor" in df.columns:
        sub = df[df["sensor"] == "power"]
    else:
        sub = df  # already pre-filtered (e.g. from fetch_today_power)
    # Ensure created_at exists
    if "created_at" not in sub.columns:
        return None
    sub = sub.sort_values("created_at").dropna(subset=["created_at"])
    if len(sub) < 2:
        return None
    # Use "value" column if present, else first numeric column
    val_col = "value" if "value" in sub.columns else sub.select_dtypes("number").columns[0]
    # Hours since the first sample. Do NOT use .astype("int64")/1e9 here:
    # that assumes nanosecond datetimes, and pandas 3 parses timestamps at
    # microsecond resolution — which would silently divide every kWh by 1000.
    times = (sub["created_at"] - sub["created_at"].iloc[0]) \
                .dt.total_seconds().values / 3600.0
    power = sub[val_col].values.astype(float)
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
def echarts_gauge(label, val, mn, mx, unit, green_end=None, warn_start=None, mode="performance"):
    """
    ECharts dial gauge.
    mode="performance"  — single green arc (higher = better, no danger zones)
    mode="limit"        — green / amber / red (pressure, temps near max)
    mode="temp"         — cool blue → green → warm red gradient across full range
    """
    if val is None: val = mn
    # The dial can only point somewhere on its own scale. A reading outside it
    # would park the needle flat against the end and read as a fault, so clamp
    # what the needle shows — the printed figure above it stays untouched.
    val = max(mn, min(mx, val))
    decimals = 0 if unit in ("W/m²", "°C") else (1 if unit == "l/min" else 2)

    if mode == "temp":
        # Smooth 5-stop gradient: cold blue → teal → green → amber → red
        colors = [
            [0.20, "#5B8FD4"],  # cold blue
            [0.40, "#4CAF50"],  # comfortable green
            [0.65, "#8BC34A"],  # warm green
            [0.85, "#FF9800"],  # hot amber
            [1.00, "#F44336"],  # danger red
        ]
    elif mode == "limit":
        if green_end  is None: green_end  = mn + (mx - mn) * 0.75
        if warn_start is None: warn_start = mn + (mx - mn) * 0.90
        safe    = max(0.001, (green_end  - mn) / (mx - mn))
        caution = max(safe + 0.001, (warn_start - mn) / (mx - mn))
        colors = [
            [safe,    "#4CAF50"],
            [caution, "#FF9800"],
            [1.00,    "#F44336"],
        ]
    else:  # "performance" — solid green, no warning
        colors = [[1.0, "#4CAF50"]]

    return {
        # Without this each dial paints its own white rectangle inside the card.
        "backgroundColor": "transparent",
        "series": [{
            "type": "gauge",
            # A clean half dial: no ticks, no split lines, rounded arc ends.
            # The reading sits above it as HTML and the range is printed under
            # the ends, so the dial itself carries no text at all.
            "startAngle": 180, "endAngle": 0,
            "min": mn, "max": mx,
            "radius": "118%", "center": ["50%", "88%"],
            "axisLine": {"roundCap": True,
                         "lineStyle": {"width": 17, "color": colors}},
            "pointer": {"length": "64%", "width": 11,
                        # Wide at the hub, narrow at the tip.
                        "icon": "path://M2,0 L0.6,-1 L-0.6,-1 L-2,0 Z",
                        "offsetCenter": [0, "0%"],
                        "itemStyle": {"color": "#1A1D26"}},
            "anchor": {"show": True, "size": 13, "showAbove": True,
                       "itemStyle": {"color": "#1A1D26"}},
            "axisTick":  {"show": False},
            "splitLine": {"show": False},
            # The scale, printed just inside the arc, ends included. An
            # earlier version hid the two ends with a JavaScript formatter so
            # they would not repeat the labels under the dial — but whether a
            # formatter survives depends on the streamlit-echarts version, and
            # where it did not the whole scale disappeared without a word.
            # Plain options only: what is drawn here is drawn everywhere.
            "splitNumber": 5,
            "axisLabel": {"show": True, "distance": 12, "fontSize": 10,
                          "color": "#8A90A8"},
            "detail": {"show": False},
            "title": {"show": False},
            "data": [{"value": round(float(val), decimals)}],
        }]
    }


def hx_section(title, icon_file):
    """Section header drawn as a card with the exported round icon."""
    ico = _asset(icon_file) or ""
    st.markdown(f'<div class="hx-sec">{ico}<div class="ttl">{title}</div></div>',
                unsafe_allow_html=True)


def render_echarts_gauge(label, val, mn, mx, unit,
                         green_end=None, warn_start=None,
                         mode="performance", key=None, height=150):
    decimals = 0 if unit in ("W/m²", "°C") else (1 if unit == "l/min" else 2)
    shown = f"{val:.{decimals}f}" if val is not None else "—"
    st.markdown(f'<div class="hx-g-lbl">{label}</div>'
                f'<div class="hx-g-val">{shown}<span>{unit}</span></div>',
                unsafe_allow_html=True)
    opt = echarts_gauge(label, val, mn, mx, unit, green_end, warn_start, mode)
    st_echarts(options=opt, height=f"{height}px",
               key=key or f"g_{label}_{mn}_{mx}")

# ── Top bar ───────────────────────────────────────────────────
if "lang" not in st.session_state:
    st.session_state.lang = "en"
if "page" not in st.session_state:
    st.session_state.page = "live"
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

hc_logo, _hc_gap, hc_en, hc_sv, hc_acct = st.columns([6, 3, .8, .8, .8],
                                                     vertical_alignment="center")
with hc_logo:
    _logo_svg = _asset("helixis-logo.svg")
    if _logo_svg:
        st.markdown(f"<div style='margin:6px 0 2px'>{_logo_svg}</div>",
                    unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='font-size:1.6rem;font-weight:800;color:{TEXT}'>HELIXIS</div>",
                    unsafe_allow_html=True)
with hc_en:
    if st.button("Eng", key="lang_en", use_container_width=True,
                 type="primary" if st.session_state.lang == "en" else "secondary"):
        st.session_state.lang = "en"; st.rerun()
with hc_sv:
    if st.button("Sve", key="lang_sv", use_container_width=True,
                 type="primary" if st.session_state.lang == "sv" else "secondary"):
        st.session_state.lang = "sv"; st.rerun()
with hc_acct:
    with st.popover("👤", use_container_width=True):
        if st.session_state.authenticated:
            st.markdown(f"<div style='font-size:.8rem;color:{TEAL}'>✓ Internal access</div>",
                        unsafe_allow_html=True)
            if st.button("Log out", use_container_width=True, key="acct_out"):
                st.session_state.authenticated = False; st.rerun()
        else:
            pwd = st.text_input("Password", type="password", key="acct_pwd",
                                label_visibility="collapsed",
                                placeholder="Internal password…")
            if st.button("Login", use_container_width=True, key="acct_in"):
                if pwd == st.secrets.get("ADMIN_PASSWORD", ""):
                    st.session_state.authenticated = True; st.rerun()
                else:
                    st.error("Incorrect password")

lang = st.session_state.lang
T = LANG[lang]
is_internal = st.session_state.authenticated
page = st.session_state.page

# ── Left card: status + navigation ────────────────────────────
# live_dashboard() fills status_slot from inside its 30-second fragment, so
# the clock in the card keeps ticking without rerunning the whole page.
_PAGES = [("live", T["live"]), ("hist", T["history"])]
if is_internal:
    _PAGES.append(("smhi", T["smhi"]))
_PAGES.append(("about", T["about"]))

with st.sidebar:
    status_slot = st.empty()
    if page != "live":
        status_slot.markdown('<div class="hx-status sub">Helixis LC10<br>'
                             'Eket · Örkelljunga</div>', unsafe_allow_html=True)
    st.markdown('<hr class="hx-rule">', unsafe_allow_html=True)
    for _key, _label in _PAGES:
        if st.button(_label, key=f"nav_{_key}",
                     use_container_width=True,
                     type="primary" if page == _key else "secondary"):
            st.session_state.page = _key; st.rerun()
        if _key == "live" and page == "live":
            view_mode = st.radio(T["display_mode"], ["🎯 Gauges", "📋 Kompakt"],
                                 horizontal=True, label_visibility="collapsed")

if page != "live":
    view_mode = "🎯 Gauges"

# ════════════════════════════════════════════════════════════════
# LIVE TAB
# ════════════════════════════════════════════════════════════════
if page == "live":

    @st.fragment(run_every=30)
    def live_dashboard():
        df = fetch_live()

        # Down-alert FIRST — it must run even when there is no recent data (during a
        # real outage fetch_live() is empty and would return early). Uses the true
        # latest timestamp regardless of the 20-min live window.
        last_any = fetch_last_reading_ts()
        if last_any is not None:
            age_any = (datetime.now(timezone.utc) - last_any).total_seconds() / 60
            check_data_alert(age_any, last_any)

        if df.empty:
            st.warning(T["no_data"]); return

        v        = {s: latest_val(df,s) for s in df["sensor"].unique()}
        last_ts  = df["created_at"].max()
        age_min  = (datetime.now(timezone.utc)-last_ts).total_seconds()/60
        is_live  = age_min < 15
        last_swe = last_ts.astimezone(SWE)
        irr, pres = v.get("irradiance"), v.get("pressure")
        irr_color = AMBER if (irr and irr>600) else (SLATE if (irr and irr>200) else MUTED)
        pcolor    = RUST if (pres and pres>=5) else SLATE

        dot = TEAL if is_live else RUST

        # (Down-alert is handled at the top of live_dashboard via check_data_alert,
        #  which works even when fetch_live() is empty during an outage.)

        df_today_pwr  = fetch_today_power()
        energy_today  = integrate_power(df_today_pwr)

        # Both status lines live in the left card, written from inside this
        # fragment so the clock keeps ticking without a full page rerun.
        sky_label, sky_icon, sky_color = sky_condition(irr, T)
        status_slot.markdown(
            f"<div class='hx-status'>"
            f"<span class='status-dot' style='background:{dot}'></span>"
            f"{last_swe.strftime('%H:%M:%S')}"
            f"<span class='sub'> · {'LIVE' if is_live else f'{age_min:.0f} min'}</span>"
            f"<br><span style='font-size:1rem'>{sky_icon}</span> "
            f"<span style='color:{sky_color}'>{sky_label.upper()}</span>"
            f"<span class='sub'>{' · ' + fmt(irr, 0, 'W/m²') if irr is not None else ''}</span>"
            f"</div>",
            unsafe_allow_html=True)

        if view_mode == "🎯 Gauges":
            # ── Temperatures (semi gauges) ──
            # The collector gauges only appear when those sensors are actually
            # reporting. The new PLC block does not send temp_right_coll /
            # temp_left_coll, and a gauge with no value silently parks its needle
            # at the scale minimum — 20 °C, which reads like a measurement.
            hx_section(T["temperatures"], "temperatures-icon.svg")
            temp_specs = [
                ("collector_r","temp_right_coll", 20,160,"g_cr"),
                ("collector_l","temp_left_coll",  20,160,"g_cl"),
                # Floors at zero: the design was drawn with summer numbers, but
                # a 15 °C forward line in winter must still land on the scale.
                ("forward",    "temp_forward",     0,120,"g_fw"),
                ("return",     "temp_return",      0,100,"g_rt"),
                ("tank",       "temp_tank",        0,100,"g_tk"),
            ]
            temp_specs = [t for t in temp_specs if v.get(t[1]) is not None]
            with st.container(border=True):
                tc = st.columns(len(temp_specs) + 1)
                for col,(lbl_key,sensor,mn,mx,gkey) in zip(tc,temp_specs):
                    with col:
                        render_echarts_gauge(T[lbl_key], v.get(sensor), mn, mx, "°C",
                            mode="temp", key=gkey)
                # Outside temperature from SMHI (last stored value)
                with tc[-1]:
                    render_echarts_gauge("Outside (SMHI)", fetch_outside_temp(), -25, 40,
                        "°C", mode="temp", key="g_outside")

            # ── Flow, Power, Irradiance, Pressure (semi gauges) ──
            hx_section(T["section_flow"], "Flow-icon.svg")
            _flow_card = st.container(border=True)
            with _flow_card:
                g1,g2,g3,g4 = st.columns(4)
            with g1:
                render_echarts_gauge(T["flow"], v.get("flow"), 0, 30, "l/min",
                    mode="performance", key="g_flow")
            with g2:
                render_echarts_gauge(T["power"], v.get("power"), 0, 9.2, "kW",
                    mode="performance", key="g_power")
            with g3:
                render_echarts_gauge(T["irradiance"], irr, 0, 1500, "W/m²",
                    mode="performance", key="g_irr")
            with g4:
                render_echarts_gauge(T["pressure"], pres, 0, 6, "bar",
                    green_end=4.5, warn_start=5.2, mode="limit", key="g_pres")

            # ── Energy (tiles + bar charts) ──
            hx_section(T["energy"], "energy-icon.svg")
            render_tiles([
                (T["energy_today"], energy_today,             "kWh", 0, 30,   TEAL, 3, None),
                (T["heat_total"],   heat_energy_kwh(v.get("heat_energy_total")
                                                     or v.get("heat_energy")),
                 "kWh", 0, 9999, BLUE, 3, None),
                (T["delta_t"],      v.get("temp_difference"), "°C",  0, 50,   BLUE, 2, None),
            ])

            # ── Hourly & Daily energy bar charts ──────────────
            # Daily bars need one series over seven days, not every sensor at
            # full resolution: ~400 points is more than a bar chart can show.
            df_7d = fetch_recent_bucketed(168, max_points=400,
                                          sensors=LIVE_POWER_SENSORS)
            if not df_7d.empty and "power" not in set(df_7d["sensor"]):
                df_7d = df_7d.assign(sensor="power")   # new PLC name
            if not df_7d.empty:
                pwr_all = df_7d[df_7d["sensor"]=="power"][["created_at","value"]].copy()
                pwr_all = pwr_all.sort_values("created_at")
                pwr_all["dt_h"] = pwr_all["created_at"].diff().dt.total_seconds().fillna(0) / 3600
                pwr_all["e_kwh"] = pwr_all["value"] * pwr_all["dt_h"]

                # Hourly — today only
                pwr_all["ts_swe"] = pwr_all["created_at"].dt.tz_convert(SWE)
                today_str = pd.Timestamp.now(tz=SWE).date()
                pwr_today = pwr_all[pwr_all["ts_swe"].dt.date == today_str].copy()

                ch1, ch2 = st.columns(2)

                with ch1:
                    st.markdown(f"<div class='hx-cap'>"
                                f"Hourly energy today (kWh)</div>", unsafe_allow_html=True)
                    if not pwr_today.empty:
                        hourly = pwr_today.groupby(pwr_today["ts_swe"].dt.hour)["e_kwh"].sum().reset_index()
                        hourly.columns = ["hour","kwh"]
                        hourly["label"] = hourly["hour"].apply(lambda h: f"{h:02d}:00")
                        fig_h = go.Figure(go.Bar(
                            x=hourly["label"], y=hourly["kwh"].round(3),
                            marker_color=TEAL, text=hourly["kwh"].round(2),
                            textposition="outside", textfont=dict(size=9, color=MUTED)))
                        fig_h.update_layout(
                            height=220, margin=dict(l=0,r=0,t=10,b=30),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                            yaxis=dict(gridcolor=BORDER, color=MUTED, title="kWh"),
                            xaxis=dict(color=MUTED, showgrid=False),
                            font=dict(family="Inter", color=MUTED))
                        st.plotly_chart(fig_h, use_container_width=True,
                            config=PLOT_CONFIG_NOSCROLL)
                    else:
                        st.caption("No data for today yet")

                with ch2:
                    st.markdown(f"<div class='hx-cap'>"
                                f"Daily energy — last 7 days (kWh)</div>", unsafe_allow_html=True)
                    daily = pwr_all.groupby(pwr_all["ts_swe"].dt.date)["e_kwh"].sum().reset_index()
                    daily.columns = ["date","kwh"]
                    daily["label"] = pd.to_datetime(daily["date"]).dt.strftime("%b %d")
                    fig_d = go.Figure(go.Bar(
                        x=daily["label"], y=daily["kwh"].round(1),
                        marker_color=BLUE, text=daily["kwh"].round(1),
                        textposition="outside", textfont=dict(size=9, color=MUTED)))
                    fig_d.update_layout(
                        height=220, margin=dict(l=0,r=0,t=10,b=30),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        yaxis=dict(gridcolor=BORDER, color=MUTED, title="kWh"),
                        xaxis=dict(color=MUTED, showgrid=False),
                        font=dict(family="Inter", color=MUTED))
                    st.plotly_chart(fig_d, use_container_width=True,
                        config=PLOT_CONFIG_NOSCROLL)

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
            _temp_tiles = [t for t in [
                ("Collector R","temp_right_coll",RUST,20,160),
                ("Collector L","temp_left_coll",AMBER,20,160),
                ("Forward","temp_forward",RUST,20,120),
                ("Return","temp_return",SLATE,10,100),
                ("Tank","temp_tank",TEAL,10,100)] if v.get(t[1]) is not None]
            cols = st.columns(max(1, len(_temp_tiles)))
            for col,(lbl,s,col_,mn,mx) in zip(cols,_temp_tiles):
                col.markdown(tile(lbl,v.get(s),"°C",mn,mx,col_,1),unsafe_allow_html=True)

            st.markdown(f'<div class="section-title">{T["section_flow"]}</div>',
                        unsafe_allow_html=True)
            cols2 = st.columns(6)
            for col,(lbl,s,u,mn,mx,col_,dec,warn) in zip(cols2,[
                (T["flow"],"flow","l/min",0,30,SLATE,1,None),
                (T["power"],"power","kW",0,9.2,RUST,2,None),
                (T["irradiance"],"irradiance","W/m²",0,1500,irr_color,0,None),
                (T["pressure"],"pressure","bar",0,6,pcolor,2,5.0),
                (T["wind"],"wind","m/s",0,20,SLATE,2,None),
                ("ΔT","temp_difference","°C",0,50,BLUE,2,None)]):
                col.markdown(tile(lbl,v.get(s),u,mn,mx,col_,dec,warn),unsafe_allow_html=True)

            st.markdown(f'<div class="section-title">{T["section_energy"]}</div>', unsafe_allow_html=True)
            e1,e2 = st.columns(2)
            e1.metric(T["energy_today_trap"], fmt(energy_today,3,"kWh"))
            e2.metric(T["heat_sensor_total"],
                      fmt(heat_energy_kwh(v.get("heat_energy_total")
                                          or v.get("heat_energy")), 3, "kWh"))

        # ── Sol & Effekt — senaste två dagarna med data ───────
        hx_section(T["recent_2days"], "sun-power-icon.svg")
        # Two series, seven days back so a gap does not hide the last day
        # that actually has data.
        df_48h = fetch_recent_bucketed(168, max_points=500,
                                       sensors=LIVE_SUN_SENSORS)
        if not df_48h.empty and "power" not in set(df_48h["sensor"]):
            df_48h = df_48h.assign(
                sensor=df_48h["sensor"].replace({"heat_power": "power"}))
        if df_48h.empty:
            st.caption(T["no_data_db"])
        else:
            df_48h["swe"] = df_48h["created_at"].dt.tz_convert(SWE)
            df_48h["date_d"] = df_48h["swe"].dt.date
            # Hitta de två senaste dagarna som faktiskt har data
            available_days = sorted(df_48h["date_d"].unique(), reverse=True)
            if len(available_days) == 0:
                st.caption(T["no_data_available"])
            else:
                day_a = available_days[0]                                  # senaste
                day_b = available_days[1] if len(available_days) > 1 else None  # näst senaste
                label_a = T["today_lbl"] if day_a == datetime.now(SWE).date() else str(day_a)
                label_b = (T["yesterday_lbl"] if day_b and day_b == datetime.now(SWE).date() - timedelta(days=1)
                           else str(day_b)) if day_b else None

                fig_cmp = go.Figure()
                has_traces = False
                for sensor, color, name, yaxis in [
                    ("irradiance", AMBER, T["irr_lbl"],   "y"),
                    ("power",      RUST,  T["power_lbl"], "y2"),
                ]:
                    sub = df_48h[df_48h["sensor"] == sensor].copy()
                    if sub.empty:
                        continue
                    for day, dash, opacity, lbl in [
                        (day_a, "solid", 1.0,  label_a),
                        (day_b, "dot",   0.5,  label_b),
                    ]:
                        if day is None:
                            continue
                        day_sub = sub[sub["date_d"] == day].copy()
                        if day_sub.empty:
                            continue
                        day_sub["time_str"] = day_sub["swe"].dt.strftime("%H:%M")
                        fig_cmp.add_trace(go.Scatter(
                            x=day_sub["time_str"], y=day_sub["value"],
                            name=f"{name} — {lbl}", mode="lines",
                            line=dict(width=1.8, color=color, dash=dash),
                            opacity=opacity, yaxis=yaxis,
                            hovertemplate=f"<b>%{{x}}</b><br>%{{y:.1f}}<extra>{name} {lbl}</extra>",
                        ))
                        has_traces = True

                if has_traces:
                    fig_cmp.update_layout(
                        height=300, margin=dict(l=0, r=70, t=10, b=0),
                        hovermode="x unified",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                    font=dict(size=10, color=MUTED, family="Inter")),
                        xaxis=dict(showgrid=False, color=MUTED, tickfont=dict(size=10)),
                        yaxis=dict(title=dict(text="W/m²", font=dict(color=AMBER)),
                                   tickfont=dict(color=AMBER), gridcolor=BORDER),
                        yaxis2=dict(title=dict(text="kW", font=dict(color=RUST)),
                                    tickfont=dict(color=RUST), overlaying="y",
                                    side="right", showgrid=False),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=MUTED, family="Inter"),
                    )
                    st.plotly_chart(fig_cmp, use_container_width=True,
                                    config=PLOT_CONFIG)
                else:
                    st.caption(T["no_values_for_days"].format(a=label_a, b=label_b))

        # ── Senaste dygnet — temperaturer, ΔT, flöde & tryck (24h) ──
        # Kontinuerlig tidslinje för alla övriga värden. Lokal tid (naive_swe).
        hx_section(T["last_day_system"], "last24hr-icon.svg")
        if df_48h.empty:
            st.caption(T["no_data_db"])
        else:
            # Own pull rather than a slice of the 7-day set: bucketed over
            # 24 hours the resolution is ~1.5 min instead of ~11.
            df_24 = fetch_recent_bucketed(24, max_points=600,
                                          sensors=LIVE_DAY_SENSORS)
            if df_24.empty:
                st.caption(T["no_data_last_day"])
            else:
                # Chart 1 — Temperaturer
                temp_names = {"temp_right_coll":T["collector_r"],"temp_left_coll":T["collector_l"],
                              "temp_forward":T["forward"],"temp_return":T["return"],"temp_tank":T["tank"]}
                temp_cmap  = {"temp_right_coll":RUST,"temp_left_coll":AMBER,"temp_forward":"#C1440E",
                              "temp_return":SLATE,"temp_tank":TEAL}
                fig24_t = go.Figure()
                for s in ["temp_right_coll","temp_left_coll","temp_forward","temp_return","temp_tank"]:
                    sub = df_24[df_24["sensor"] == s]
                    if not sub.empty:
                        fig24_t.add_trace(go.Scatter(
                            x=naive_swe(sub["created_at"]), y=sub["value"],
                            name=temp_names[s], mode="lines",
                            line=dict(width=1.6, color=temp_cmap[s])))
                fig24_t.update_layout(
                    height=260, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                               tickfont=dict(color=TEXT), gridcolor=BORDER),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig24_t.update_xaxes(showgrid=False, color=MUTED)
                st.markdown(f"<div class='hx-cap'>"
                            f"{T['temperatures']}</div>", unsafe_allow_html=True)
                st.plotly_chart(fig24_t, use_container_width=True,
                                config=PLOT_CONFIG, key="live24_temp")

                # Chart 2 — ΔT, Flöde & Tryck
                fig24_d = go.Figure()
                sub_dt = df_24[df_24["sensor"] == "temp_difference"]
                if not sub_dt.empty:
                    fig24_d.add_trace(go.Scatter(
                        x=naive_swe(sub_dt["created_at"]), y=sub_dt["value"],
                        name="ΔT (°C)", mode="lines", line=dict(width=1.6, color=TEXT), yaxis="y"))
                sub_fl = df_24[df_24["sensor"] == "flow"]
                if not sub_fl.empty:
                    fig24_d.add_trace(go.Scatter(
                        x=naive_swe(sub_fl["created_at"]), y=sub_fl["value"],
                        name=T["flow_lbl"], mode="lines", line=dict(width=1.6, color=SLATE), yaxis="y2"))
                sub_pr = df_24[df_24["sensor"] == "pressure"]
                if not sub_pr.empty:
                    fig24_d.add_trace(go.Scatter(
                        x=naive_swe(sub_pr["created_at"]), y=sub_pr["value"],
                        name=T["pressure_lbl"], mode="lines",
                        line=dict(width=1.5, color=TEAL, dash="dot"), yaxis="y3"))
                fig24_d.update_layout(
                    height=240, margin=dict(l=0, r=90, t=10, b=0), hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                               tickfont=dict(color=TEXT), gridcolor=BORDER),
                    yaxis2=dict(title=dict(text="l/min", font=dict(color=SLATE)),
                                tickfont=dict(color=SLATE), overlaying="y", side="right",
                                showgrid=False, anchor="x"),
                    yaxis3=dict(title=dict(text="bar", font=dict(color=TEAL)),
                                tickfont=dict(color=TEAL), overlaying="y", side="right",
                                showgrid=False, anchor="free", position=1.0, range=[0, 8]),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig24_d.update_xaxes(showgrid=False, color=MUTED)
                st.markdown(f"<div class='hx-cap'>"
                            f"{T['section_dt_flow']}</div>", unsafe_allow_html=True)
                st.plotly_chart(fig24_d, use_container_width=True,
                                config=PLOT_CONFIG, key="live24_dtflow")

    live_dashboard()

# ════════════════════════════════════════════════════════════════
# HISTORIK TAB
# ════════════════════════════════════════════════════════════════
if page == "hist":
    # ── Översikt — välj period ────────────────────────────────
    today = datetime.now(SWE).date()

    df_daily = fetch_daily_summary(days=90)
    if not df_daily.empty:
        st.markdown(f'<div class="section-title">{T["overview_title"]}</div>',
                    unsafe_allow_html=True)
        fig_ov = go.Figure()
        fig_ov.add_trace(go.Bar(
            x=df_daily["date"].astype(str), y=df_daily["kwh"],
            name=T["energy_kwh_lbl"], marker_color=TEAL,
            hovertemplate="<b>%{x}</b><br>%{y:.2f} kWh<extra></extra>",
        ))
        fig_ov.add_trace(go.Scatter(
            x=df_daily["date"].astype(str), y=df_daily["peak_irr"] / 150,
            name=T["peak_irr_lbl"], mode="lines",
            line=dict(color=AMBER, width=1.5),
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>%{customdata:.0f} W/m²<extra></extra>",
            customdata=df_daily["peak_irr"],
        ))
        fig_ov.update_layout(
            height=160, margin=dict(l=0, r=0, t=6, b=0),
            hovermode="x unified", barmode="overlay",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=9, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="kWh", font=dict(size=9)),
                       gridcolor=BORDER, color=MUTED, tickfont=dict(size=9)),
            yaxis2=dict(overlaying="y", side="right", showgrid=False,
                        showticklabels=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_ov.update_xaxes(showgrid=False, color=MUTED, tickfont=dict(size=9),
                             tickangle=-45)
        st.plotly_chart(fig_ov, use_container_width=True,
                        config=PLOT_CONFIG_NOSCROLL)
        st.caption(T["overview_caption"])

    # ── Datumintervall ────────────────────────────────────────
    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input(T["date_from"], value=today - timedelta(days=7),
                                  max_value=today, key="hist_from")
    with col_to:
        date_to = st.date_input(T["date_to"], value=today,
                                min_value=date_from, max_value=today, key="hist_to")

    # Convert to UTC datetimes covering full days in Swedish time
    dt_from = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
    dt_to   = datetime.combine(date_to,   datetime.max.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
    hours_back = max(1, int((dt_to - dt_from).total_seconds() / 3600) + 1)

    # How much detail to pull. Averaging into buckets is what makes a long
    # window load in one request instead of hundreds — but it also smooths
    # away short spikes, so "Full" stays available for digging into an event.
    # Keys stay language-independent so switching language does not invalidate
    # the stored session_state selection.
    RES_CHOICES = {"auto": HIST_MAX_POINTS, "fine": 2500, "full": 5000}
    res_key = st.radio(T["res_label"], list(RES_CHOICES),
                       format_func=lambda k: T[f"res_{k}"], horizontal=True,
                       key="hist_res", help=T["res_help"])
    hist_points = RES_CHOICES[res_key]
    hist_bucket = bucket_seconds_for(dt_from, dt_to, hist_points) if hist_points else 0

    with st.spinner(T["loading_hist"]):
        df_hist   = fetch_history_range(dt_from, dt_to, hist_points)
        df_smhi_h = fetch_smhi_history(hours_back)

    # Data lagras i UTC. Plotly ritar datum i UTC och struntar i tidszons-offset,
    # så vi konverterar till platsens lokala tid (Örkelljunga) och tar bort tz —
    # då visar alla grafer nedan lokal tid. Varje graf läser från dessa två frames.
    if not df_hist.empty:
        df_hist = df_hist.copy()
        df_hist["created_at"] = naive_swe(df_hist["created_at"])
    if not df_smhi_h.empty:
        df_smhi_h = df_smhi_h.copy()
        df_smhi_h["created_at"] = naive_swe(df_smhi_h["created_at"])

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
        st.markdown(f'<div class="section-title">{T["section_solar"]}</div>',
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
        # Overlay outside temp (SMHI) on solar chart — shows temp effect on performance
        if not df_smhi_h.empty:
            sub_ot = df_smhi_h[df_smhi_h["sensor"] == "smhi_temperature"]
            if not sub_ot.empty:
                fig_solar.add_trace(go.Scatter(
                    x=sub_ot["created_at"], y=sub_ot["value"],
                    name="Outside temp °C (SMHI)", mode="lines",
                    line=dict(width=1.5, color="#7B5EA7", dash="dot"),
                    yaxis="y3"))
        fig_solar.update_layout(
            height=340, margin=dict(l=0, r=90, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="W/m²", font=dict(color=AMBER)),
                       tickfont=dict(color=AMBER), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="kW / m/s", font=dict(color=RUST)),
                        tickfont=dict(color=RUST), overlaying="y", side="right",
                        showgrid=False),
            yaxis3=dict(title=dict(text="°C", font=dict(color="#7B5EA7")),
                        tickfont=dict(color="#7B5EA7"), overlaying="y",
                        side="right", anchor="free", position=1.0,
                        showgrid=False),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_solar.update_xaxes(showgrid=False, color=MUTED)
        add_time_controls(fig_solar)
        st.plotly_chart(fig_solar, use_container_width=True, config=PLOT_CONFIG)
        st.caption(T["chart_hint"] + "  \n"
                   + (T["resolution_note"].format(res=fmt_resolution(hist_bucket))
                      if hist_bucket else T["resolution_raw"]))

        # ── 2. Temperaturer & Tryck ──────────────────────────
        st.markdown(f'<div class="section-title">{T["section_temps_pressure"]}</div>',
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
        # Outside temperature from SMHI (Helsingborg station)
        if not df_smhi_h.empty:
            sub_ot = df_smhi_h[df_smhi_h["sensor"] == "smhi_temperature"]
            if not sub_ot.empty:
                fig_temp.add_trace(go.Scatter(
                    x=sub_ot["created_at"], y=sub_ot["value"],
                    name="Outside temp (SMHI)", mode="lines",
                    line=dict(width=2, color="#7B5EA7", dash="dash"), yaxis="y"))
        fig_temp.update_layout(
            height=320, margin=dict(l=0, r=10, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                       tickfont=dict(color=TEXT), gridcolor=BORDER),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_temp.update_xaxes(showgrid=False, color=MUTED)
        add_time_controls(fig_temp)
        st.plotly_chart(fig_temp, use_container_width=True, config=PLOT_CONFIG)

        # ── 3. ΔT, Flöde & Tryck ──────────────────────────────
        st.markdown(f'<div class="section-title">{T["section_dt_flow"]}</div>',
                    unsafe_allow_html=True)
        fig_dt = go.Figure()
        # Left axis: ΔT
        sub_dt = df_hist[df_hist["sensor"] == "temp_difference"]
        if not sub_dt.empty:
            fig_dt.add_trace(go.Scatter(
                x=sub_dt["created_at"], y=sub_dt["value"],
                name="ΔT (°C)", mode="lines",
                line=dict(width=1.8, color=TEXT), yaxis="y"))
        # Right axis (inner): Flow l/min
        sub_fl = df_hist[df_hist["sensor"] == "flow"]
        if not sub_fl.empty:
            fig_dt.add_trace(go.Scatter(
                x=sub_fl["created_at"], y=sub_fl["value"],
                name=T["flow_lbl"], mode="lines",
                line=dict(width=1.8, color=SLATE), yaxis="y2"))
        # Right axis (outer): Pressure bar
        sub_pr = df_hist[df_hist["sensor"] == "pressure"]
        if not sub_pr.empty:
            fig_dt.add_trace(go.Scatter(
                x=sub_pr["created_at"], y=sub_pr["value"],
                name=T["pressure_lbl"], mode="lines",
                line=dict(width=1.5, color=TEAL, dash="dot"), yaxis="y3"))
        fig_dt.update_layout(
            height=280, margin=dict(l=0, r=90, t=10, b=0),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        font=dict(size=10, color=MUTED, family="Inter")),
            yaxis=dict(title=dict(text="°C", font=dict(color=TEXT)),
                       tickfont=dict(color=TEXT), gridcolor=BORDER),
            yaxis2=dict(title=dict(text="l/min", font=dict(color=SLATE)),
                        tickfont=dict(color=SLATE), overlaying="y", side="right",
                        showgrid=False, anchor="x"),
            yaxis3=dict(title=dict(text="bar", font=dict(color=TEAL)),
                        tickfont=dict(color=TEAL), overlaying="y", side="right",
                        showgrid=False, anchor="free", position=1.0,
                        range=[0, 8]),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MUTED, family="Inter"),
        )
        fig_dt.update_xaxes(showgrid=False, color=MUTED)
        add_time_controls(fig_dt)
        st.plotly_chart(fig_dt, use_container_width=True, config=PLOT_CONFIG)

        # ── 4. Sammanfattning & Energi ────────────────────────
        st.markdown(f'<div class="section-title">{T["section_summary"]}</div>',
                    unsafe_allow_html=True)
        all_sensors = temp_sensors + ["power","flow","irradiance","wind","pressure","temp_difference"]
        # The plotted series are bucket averages, which hide true peaks — so
        # min/max/mean come from the raw rows via sensor_window_stats() when
        # it is installed, and from the plotted points otherwise.
        stats = fetch_window_stats(dt_from, dt_to)
        if not stats.empty:
            piv = stats[stats["sensor"].isin(all_sensors)][
                ["sensor", "v_min", "v_max", "v_mean"]].round(2).reset_index(drop=True)
        else:
            piv = df_hist[df_hist["sensor"].isin(all_sensors)] \
                .groupby("sensor")["value"].agg(["min","max","mean"]).round(2).reset_index()
        piv.columns = [T["col_sensor"],T["col_min"],T["col_max"],T["col_mean"]]
        sensor_order = all_sensors
        piv["_ord"] = piv[T["col_sensor"]].apply(lambda s: sensor_order.index(s)
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
            help=T["energy_window_help"])
        ec2.metric(T["heat_sensor_total"],
                   fmt(heat_energy_kwh(latest_val(df_hist, "heat_energy_total")
                                       or latest_val(df_hist, "heat_energy")), 3, "kWh"),
                   help=T["heat_help"])

        # ── Temporary: Three-method power correlation ────────────
        with st.expander("🔬 Power correlation: 3 methods (temporary analysis)", expanded=True):
            st.markdown(f"""
**M1 — Power sensor:** Direct `power` reading, kW.
**M2 — Flow×ΔT (physics):** `P = flow[l/min] × ρ × cp × (T_fwd − T_ret) / 60000 / 1000`, kW.
**M3 — Heat energy counter:** Cumulative kWh delta since the first sample. Reset date unknown.

**Instantaneous power chart** compares M1 vs M2. **Cumulative energy chart** compares all three from t₀.
If M1 ≈ M2 → controller calculates power internally from flow×ΔT (not independent).
Ratio M1/M2 reveals the actual cp of the fluid.
""")
            RHO = 1000
            CP_DEFAULT = 3800

            # cp slider — always visible so it drives both charts
            cp_val = st.slider("cp (J/kg·K) — adjust to match M1 vs M2",
                               min_value=3400, max_value=4200, value=CP_DEFAULT, step=50,
                               help="Pure water=4186 · 30% glycol≈3800 · 50% glycol≈3500")

            # Accept both PLC generations for every tag.
            sensor_alts = {
                "power":        ("power", "heat_power"),
                "flow":         ("flow",),
                "temp_forward": ("temp_forward", "temp_supply"),
                "temp_return":  ("temp_return",),
                "heat_energy":  ("heat_energy", "heat_energy_total"),
            }
            dfs = {}
            for key, alts in sensor_alts.items():
                sub, _used = pick_sensor(df_hist, *alts)
                sub = sub[["created_at", "value"]].copy()
                sub = sub.rename(columns={"value": key}).set_index("created_at")
                dfs[key] = sub

            if all(s in dfs and not dfs[s].empty for s in ["flow","temp_forward","temp_return"]):
                base = dfs["flow"]
                for s in ["temp_forward","temp_return","power","heat_energy"]:
                    if s in dfs and not dfs[s].empty:
                        base = pd.merge_asof(
                            base.sort_index().reset_index(),
                            dfs[s].sort_index().reset_index(),
                            on="created_at", tolerance=pd.Timedelta("2min")
                        ).set_index("created_at")
                base = base.dropna(subset=["flow","temp_forward","temp_return"])

                # M2 with selected cp
                base["p_physics"] = thermal_power_kw(
                    base["flow"],
                    base["temp_forward"] - base["temp_return"],
                    cp=cp_val, rho=RHO)

                # M3: cumulative delta from t₀ in kWh
                if "heat_energy" in base.columns and not base["heat_energy"].dropna().empty:
                    e0 = float(base["heat_energy"].dropna().iloc[0])
                    base["heat_kwh_delta"] = base["heat_energy"] - e0   # already kWh

                # ── Instantaneous power chart (M1 vs M2) ──────────
                st.markdown(f'<div class="section-title">Instantaneous power — M1 vs M2 (kW)</div>',
                            unsafe_allow_html=True)
                fig_pwr = go.Figure()
                if "power" in base.columns:
                    fig_pwr.add_trace(go.Scatter(
                        x=base.index, y=base["power"],
                        name="M1: power sensor (kW)",
                        mode="lines", line=dict(color=RUST, width=2)))
                fig_pwr.add_trace(go.Scatter(
                    x=base.index, y=base["p_physics"],
                    name=f"M2: flow×ΔT (kW, cp={cp_val})",
                    mode="lines", line=dict(color=TEAL, width=2, dash="dot")))
                fig_pwr.update_layout(
                    height=260, margin=dict(l=0,r=0,t=10,b=0),
                    yaxis_title="kW", hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig_pwr.update_xaxes(showgrid=False, color=MUTED)
                fig_pwr.update_yaxes(gridcolor=BORDER, color=MUTED)
                st.plotly_chart(fig_pwr, use_container_width=True, config=PLOT_CONFIG)

                # ── Correlation metrics ────────────────────────────
                if "power" in base.columns:
                    # Only samples where the loop is actually running. Taking
                    # the median across every night and every standstill put
                    # thousands of zeros in the middle of the distribution, so
                    # the ratio came out 0.000 and the implied cp came out inf.
                    both = base[["power", "p_physics", "flow"]].dropna()
                    both = both[(both["flow"] > FLOW_MIN_LMIN) &
                                (both["p_physics"] > 0.2)]
                    if len(both) > 10:
                        corr  = both["power"].corr(both["p_physics"])
                        ratio = (both["power"] / both["p_physics"]).median()
                        implied_cp = cp_val / ratio if ratio and ratio > 0.05 else float("nan")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Correlation M1 vs M2", f"{corr:.3f}",
                            help=">0.99 = power is calculated from flow×ΔT in controller")
                        c2.metric("Median ratio M1/M2", f"{ratio:.3f}",
                            help="1.0 = perfect. Deviation = cp mismatch or calibration offset")
                        c3.metric("cp used", f"{cp_val} J/kg·K")
                        c4.metric("Implied cp if ratio=1.0",
                            "—" if implied_cp != implied_cp else f"{implied_cp:.0f} J/kg·K",
                            help="The cp value that would make M2 exactly match M1")
                        st.caption(f"Statistics from {len(both)} samples with flow above "
                                   f"{FLOW_MIN_LMIN:g} l/min — idle periods are excluded.")
                        if corr > 0.99:
                            st.info("🔗 Correlation >0.99 — power sensor is calculated from flow×ΔT "
                                    "internally. M1 and M2 are **not independent**.")
                        elif corr > 0.95:
                            st.warning("⚠️ 0.95–0.99 — likely same source, small calibration difference.")
                        else:
                            st.success("✅ <0.95 — power sensor appears to be an independent measurement.")

                # ── Cumulative energy chart (M1 + M2 + M3) ────────
                st.markdown(f'<div class="section-title">Cumulative energy from t₀ — all 3 methods (kWh)</div>',
                            unsafe_allow_html=True)

                # M1 cumulative: trapezoid of power sensor
                pwr_sub = base["power"].dropna()
                # Hours since t0 — resolution-independent (see integrate_power)
                times_h  = (pwr_sub.index - pwr_sub.index[0]) \
                               .total_seconds() / 3600.0
                try:
                    import numpy as np
                    fn = getattr(np, "trapezoid", None) or getattr(np, "trapz")
                    cum_m1 = []
                    t_arr = times_h.values
                    p_arr = pwr_sub.values
                    t0_h  = t_arr[0]
                    for i in range(len(t_arr)):
                        cum_m1.append(float(max(0, fn(p_arr[:i+1], t_arr[:i+1]) - t0_h * 0)))
                    # simpler: running integral
                    cum_m1 = [0.0]
                    for i in range(1, len(t_arr)):
                        cum_m1.append(cum_m1[-1] + (p_arr[i]+p_arr[i-1])/2*(t_arr[i]-t_arr[i-1]))
                except Exception:
                    cum_m1 = [0.0]
                    for i in range(1, len(t_arr)):
                        cum_m1.append(cum_m1[-1] + (p_arr[i]+p_arr[i-1])/2*(t_arr[i]-t_arr[i-1]))

                # M2 cumulative: trapezoid of p_physics aligned to same index
                phy_sub = base["p_physics"].reindex(pwr_sub.index, method="nearest")
                ph_arr  = phy_sub.values
                cum_m2  = [0.0]
                for i in range(1, len(t_arr)):
                    cum_m2.append(cum_m2[-1] + (ph_arr[i]+ph_arr[i-1])/2*(t_arr[i]-t_arr[i-1]))

                fig_cum = go.Figure()
                fig_cum.add_trace(go.Scatter(
                    x=pwr_sub.index, y=cum_m1,
                    name="M1 cumulative (power sensor, kWh)",
                    mode="lines", line=dict(color=RUST, width=2)))
                fig_cum.add_trace(go.Scatter(
                    x=pwr_sub.index, y=cum_m2,
                    name=f"M2 cumulative (flow×ΔT cp={cp_val}, kWh)",
                    mode="lines", line=dict(color=TEAL, width=2, dash="dot")))

                # M3: heat_energy counter delta
                if "heat_kwh_delta" in base.columns:
                    m3_sub = base["heat_kwh_delta"].dropna()
                    if not m3_sub.empty:
                        fig_cum.add_trace(go.Scatter(
                            x=m3_sub.index, y=m3_sub.values,
                            name="M3 cumulative (heat energy counter ÷1000→kWh)",
                            mode="lines", line=dict(color=BLUE, width=2, dash="dash")))

                fig_cum.update_layout(
                    height=280, margin=dict(l=0,r=0,t=10,b=0),
                    yaxis_title="kWh", hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig_cum.update_xaxes(showgrid=False, color=MUTED)
                fig_cum.update_yaxes(gridcolor=BORDER, color=MUTED)
                st.plotly_chart(fig_cum, use_container_width=True, config=PLOT_CONFIG)

                # Three-way end-of-window summary
                m1_end = cum_m1[-1] if cum_m1 else None
                m2_end = cum_m2[-1] if cum_m2 else None
                m3_end = float(base["heat_kwh_delta"].dropna().iloc[-1])                          if "heat_kwh_delta" in base.columns and not base["heat_kwh_delta"].dropna().empty else None
                s1, s2, s3 = st.columns(3)
                s1.metric("M1 total (window)", fmt(m1_end, 3, "kWh"))
                s2.metric("M2 total (window)", fmt(m2_end, 3, "kWh"))
                s3.metric("M3 delta (window)", fmt(m3_end, 3, "kWh"),
                          help="Change in heat energy counter over this window. "
                               "Already ×1000 (MWh→kWh). Should match M1 if calibrated.")
                if m1_end and m3_end and m1_end > 0.1:
                    m3_ratio = m3_end / m1_end
                    st.caption(f"M3/M1 ratio: {m3_ratio:.3f} — "
                               f"{'good agreement ✓' if 0.9 < m3_ratio < 1.1 else 'deviation — check calibration or reset'}")
            else:
                st.info("Need flow, temp_forward and temp_return data in selected window.")


        # ── Irradiance sensor vs DNI ──────────────────────────────────
        with st.expander("🔆 Irradiance sensor vs DNI — what is this sensor seeing?",
                         expanded=False):
            st.markdown("""
The irradiance sensor is a **silicon cell measuring global irradiance in its own
plane**. A concentrator can only use the **direct beam**. The two are different
quantities, so before any efficiency figure means anything we need to know what
this sensor actually sees — and whether it is mounted flat or on the tracker.

Two references are drawn against it:

- **Clear-sky envelope**, computed here from the sun's position over Eket. It
  needs no external data. On the clearest hours the sensor should approach one
  of the two curves and never exceed it.
- **STRÅNG DNI**, SMHI's modelled beam irradiance for these coordinates.
""")
            linke = st.slider("Linke turbidity — sky clarity for the envelope",
                              2.0, 5.0, 3.0, 0.1,
                              help="2.5–3 is a clean Nordic winter sky, 4–5 a hazy "
                                   "summer one. Turn this only if the envelope sits "
                                   "consistently off the clearest measured days.")

            _irr = df_hist[df_hist["sensor"] == "irradiance"].copy()
            # The history window can arrive from the bucketed path, which does
            # not always carry the timezone through. Everything below assumes
            # UTC-aware stamps.
            _irr["created_at"] = pd.to_datetime(_irr["created_at"], utc=True)
            irr_h = (_irr.set_index("created_at")["value"]
                     .resample("1h").mean().dropna())

            if irr_h.empty:
                st.info("No irradiance readings in the selected window.")
            else:
                cs = clear_sky(irr_h.index, SITE_LAT, SITE_LON, linke=linke)
                cmp_df = pd.DataFrame({"sensor": irr_h.values,
                                       "ghi_clear": cs["ghi_clear"].values,
                                       "dni_clear": cs["dni_clear"].values,
                                       "elevation": cs["elevation"].values},
                                      index=irr_h.index)

                # STRÅNG DNI for the same hours, if it answers
                _first = pd.Timestamp(cmp_df.index.min())
                if _first.tzinfo is None:
                    _first = _first.tz_localize("UTC")
                days_span = max(1, int((pd.Timestamp.now(tz="UTC") - _first).days) + 1)
                df_str, str_err = fetch_strang(min(days_span, 30))
                if not df_str.empty:
                    for name in ("dni_strang", "ghi_strang"):
                        sub = df_str[df_str["sensor"] == name]
                        if not sub.empty:
                            ser = (sub.set_index("created_at")["value"]
                                      .resample("1h").mean())
                            cmp_df[name] = ser.reindex(cmp_df.index)

                day = cmp_df[cmp_df["elevation"] > 5].copy()

                # ── 1. The envelope ───────────────────────────────
                st.markdown(f'<div class="hx-cap">Sensor against the clear-sky '
                            f'envelope</div>', unsafe_allow_html=True)
                fig_cs = go.Figure()
                fig_cs.add_trace(go.Scatter(
                    x=naive_swe(pd.Series(day.index)), y=day["sensor"],
                    name="Sensor (W/m²)", mode="lines",
                    line=dict(color=AMBER, width=2)))
                fig_cs.add_trace(go.Scatter(
                    x=naive_swe(pd.Series(day.index)), y=day["ghi_clear"],
                    name="Clear-sky GHI (horizontal)", mode="lines",
                    line=dict(color=SLATE, width=1.4, dash="dot")))
                fig_cs.add_trace(go.Scatter(
                    x=naive_swe(pd.Series(day.index)), y=day["dni_clear"],
                    name="Clear-sky DNI (tracked)", mode="lines",
                    line=dict(color=RUST, width=1.4, dash="dash")))
                if "dni_strang" in day.columns:
                    fig_cs.add_trace(go.Scatter(
                        x=naive_swe(pd.Series(day.index)), y=day["dni_strang"],
                        name="STRÅNG DNI", mode="lines",
                        line=dict(color=TEAL, width=1.4)))
                fig_cs.update_layout(
                    height=300, margin=dict(l=0, r=0, t=10, b=0),
                    yaxis_title="W/m²", hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"))
                fig_cs.update_xaxes(showgrid=False, color=MUTED)
                fig_cs.update_yaxes(gridcolor=BORDER, color=MUTED)
                st.plotly_chart(fig_cs, use_container_width=True, config=PLOT_CONFIG,
                                key="cs_env")

                # Which curve does the sensor follow? That is the mounting.
                hi = day[day["elevation"] > 10]
                hi = hi[hi["sensor"] > 0.1 * hi["dni_clear"].max()] if not hi.empty else hi
                if len(hi) > 5:
                    r_ghi = float((hi["sensor"] / hi["ghi_clear"]
                                   .replace(0, np.nan)).median())
                    r_dni = float((hi["sensor"] / hi["dni_clear"]
                                   .replace(0, np.nan)).median())
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Sensor / clear-sky GHI", f"{r_ghi:.2f}",
                              help="Near 1.0 on clear hours → mounted horizontally")
                    m2.metric("Sensor / clear-sky DNI", f"{r_dni:.2f}",
                              help="Near 1.0 on clear hours → mounted on the tracker")
                    m3.metric("Peak reading", f"{day['sensor'].max():.0f} W/m²")
                    verdict = ("looks **horizontal** — it tracks the GHI envelope"
                               if abs(r_ghi - 1) < abs(r_dni - 1)
                               else "looks **tracked** — it follows the DNI envelope")
                    st.caption(f"On clear hours the sensor {verdict}. "
                               f"A reading above both envelopes means the "
                               f"calibration reads high, or the cell sees "
                               f"reflected or concentrated light.")

                # ── 2. Correlation against DNI ────────────────────
                if "dni_strang" in day.columns and day["dni_strang"].notna().sum() > 5:
                    both = day[["sensor", "dni_strang", "elevation",
                                "ghi_clear"]].dropna()
                    both = both[both["dni_strang"] > 20]
                    a, b, r, n = fit_line(both["sensor"], both["dni_strang"])

                    st.markdown('<div class="hx-cap">Sensor vs STRÅNG DNI</div>',
                                unsafe_allow_html=True)
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Hours compared", f"{n}")
                    c2.metric("Correlation r", "—" if r is None else f"{r:.3f}")
                    c3.metric("Slope DNI/sensor", "—" if a is None else f"{a:.2f}")

                    fig_sc = go.Figure()
                    fig_sc.add_trace(go.Scatter(
                        x=both["sensor"], y=both["dni_strang"], mode="markers",
                        name="Hourly means",
                        marker=dict(size=5, color=both["elevation"],
                                    colorscale="Viridis", showscale=True,
                                    colorbar=dict(title="Sun<br>elev °",
                                                  thickness=10))))
                    lim = float(max(both["sensor"].max(), both["dni_strang"].max()))
                    fig_sc.add_trace(go.Scatter(
                        x=[0, lim], y=[0, lim], mode="lines", name="1:1",
                        line=dict(color=MUTED, width=1, dash="dot")))
                    if a is not None:
                        fig_sc.add_trace(go.Scatter(
                            x=[0, lim], y=[b, a * lim + b], mode="lines",
                            name=f"Fit: DNI = {a:.2f}·sensor + {b:.0f}",
                            line=dict(color=RUST, width=2)))
                    fig_sc.update_layout(
                        height=380, margin=dict(l=0, r=0, t=10, b=0),
                        xaxis_title="Sensor (W/m²)", yaxis_title="STRÅNG DNI (W/m²)",
                        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                    font=dict(size=10, color=MUTED, family="Inter")),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=MUTED, family="Inter"))
                    fig_sc.update_xaxes(gridcolor=BORDER, color=MUTED)
                    fig_sc.update_yaxes(gridcolor=BORDER, color=MUTED)
                    st.plotly_chart(fig_sc, use_container_width=True,
                                    config=PLOT_CONFIG, key="cs_scatter")

                    # Ratio against sun elevation: a fixed plane cannot hold a
                    # constant ratio as the sun climbs, a tracker can.
                    both = both.assign(ratio=both["sensor"] / both["dni_strang"])
                    fig_ra = go.Figure()
                    fig_ra.add_trace(go.Scatter(
                        x=both["elevation"], y=both["ratio"], mode="markers",
                        name="Sensor / DNI",
                        marker=dict(size=5, color=SLATE, opacity=.55)))
                    fig_ra.update_layout(
                        height=300, margin=dict(l=0, r=0, t=10, b=0),
                        xaxis_title="Solar elevation (°)",
                        yaxis_title="Sensor / STRÅNG DNI",
                        showlegend=False,
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color=MUTED, family="Inter"))
                    fig_ra.update_xaxes(gridcolor=BORDER, color=MUTED)
                    fig_ra.update_yaxes(gridcolor=BORDER, color=MUTED, range=[0, 2])
                    st.markdown('<div class="hx-cap">Ratio against sun elevation'
                                '</div>', unsafe_allow_html=True)
                    st.plotly_chart(fig_ra, use_container_width=True,
                                    config=PLOT_CONFIG, key="cs_ratio")
                    st.caption("A flat cloud of points means the sensor sees the "
                               "same share of the beam whatever the sun's height — "
                               "that is tracking. A cloud that climbs with "
                               "elevation is a fixed plane, where the cosine of "
                               "the incidence angle changes through the day.")
                elif str_err:
                    st.warning("STRÅNG did not answer, so only the clear-sky "
                               "envelope is shown: " + "; ".join(str_err.values()))

        with st.expander(f"📥 {T['raw_export']}"):
            piv2 = df_hist.pivot_table(
                index="created_at", columns="sensor",
                values="value", aggfunc="last"
            ).reset_index().sort_values("created_at", ascending=False)
            st.dataframe(piv2.head(500), use_container_width=True)
            st.caption(T["export_note"].format(res=fmt_resolution(hist_bucket))
                       if hist_bucket else T["export_note_raw"])
            _tag = fmt_resolution(hist_bucket).replace(" ", "") if hist_bucket else "raw"
            st.download_button(f"⬇️ {T['download_csv']}", df_hist.to_csv(index=False),
                f"helixis_{date_from}_{date_to}_{_tag}.csv", "text/csv")

# ════════════════════════════════════════════════════════════════
# SMHI & ANALYS TAB  (internal only)
# ════════════════════════════════════════════════════════════════
if is_internal:
     if page == "smhi":

        # ── Förklaringstext ───────────────────────────────────────
        with st.expander("ℹ️ Understanding STRÅNG model data — what each parameter means", expanded=False):
            st.markdown(f"""
    #### What is STRÅNG?

    STRÅNG is SMHI's gridded solar radiation model. Unlike weather stations (which only exist
    at fixed points), STRÅNG calculates radiation values for **any coordinate in the Nordic countries**
    using atmospheric physics and satellite cloud data. Resolution: 2.5 × 2.5 km, hourly.

    No API key needed. Data is freely available from SMHI Open Data.

    ---

    #### The three radiation parameters

    | Parameter | Full name | What it measures | Sensor type |
    |---|---|---|---|
    | **GHI** | Global Horizontal Irradiance | Total solar energy hitting a flat horizontal surface — direct + diffuse | Pyranometer (flat plate) |
    | **DNI** | Direct Normal Irradiance | Solar energy arriving in a straight line from the sun, measured perpendicular to the sun's rays | Pyrheliometer (tracks sun) |
    | **DHI** | Diffuse Horizontal Irradiance | Scattered light only (clouds, atmosphere) — GHI minus the direct component | Calculated |

    **Why DNI matters for Helixis:** The LC10 concentrates sunlight using mirrors. Diffuse light
    (scattered by clouds) arrives from all directions and cannot be focused. Only DNI contributes
    to useful output. On a heavily overcast day, GHI may be 200 W/m² but DNI is near zero — the
    system produces almost nothing despite "some" sunlight.

    ---

    #### Clearness index kt

    `kt = DNI_STRÅNG / GHI_STRÅNG`

    A dimensionless ratio from 0 to ~0.9 describing sky clarity:

    | kt value | Sky condition | Helixis output |
    |---|---|---|
    | 0.75 – 0.90 | Clear sky, direct sun | Full output possible |
    | 0.50 – 0.75 | Mostly clear, thin haze | Reduced ~10–30% |
    | 0.25 – 0.50 | Partly cloudy | Significantly reduced |
    | 0.00 – 0.25 | Overcast | Near-zero output |

    **Note on kt > 1.0:** This is physically valid at low solar elevation angles. Because GHI is
    measured on a horizontal surface while DNI is measured perpendicular to the sun:

    `GHI = DNI × cos(zenith angle) + diffuse`

    When the sun is low in the sky, DNI can exceed GHI, giving kt > 1.0 from STRÅNG.
    The app does not clip kt — the on-site sensor (IMT Si-RS485TC, rated 0–1500 W/m², ±1.6%) is
    trusted directly. Values above 1000 W/m² are fully possible on clear days in Sweden.

    ---

    #### How we estimate DNI without a pyrheliometer

    Since DNI sensors cost 30,000–100,000 SEK and require daily maintenance, we use:

    `DNI_estimated = kt_STRÅNG × GHI_sensor`

    This uses STRÅNG's sky-clarity ratio applied to our own on-site measurement.
    Accuracy is typically ±10–15% on clear days, worse on partially cloudy days
    (when cloud patterns between Örkelljunga and the STRÅNG grid cell differ).

    ---

    #### Theoretical vs actual power

    `P_theoretical = DNI_estimated × 12.35 m² × 0.65 = DNI × 8.03 W per W/m²`

    The 0.65 factor is the optical efficiency (peak ~0.72, realistic with tracking error and
    mirror soiling ~0.65). The gap between theoretical and actual power reveals system losses:
    mirror soiling, tracking error, pump issues, heat exchanger efficiency, and startup losses.

    ---
    *Sources: SMHI STRÅNG Open Data · Helsingborg station 62040 (temp/wind/humidity) · Växjö station 64565 (GHI station)*
    """)

        # ── Datumväljare ──────────────────────────────────────────
        _now_swe = datetime.now(SWE)
        _today   = _now_swe.date()

        # ── Day toggle buttons — last 7 days ──────────────────
        # Session state: set of selected dates
        if "smhi_selected_days" not in st.session_state:
            # Default: all 7 days selected
            st.session_state.smhi_selected_days = {
                _today - pd.Timedelta(days=i) for i in range(7)
            }

        # Show buttons for last 14 days, grouped in rows of 7
        st.markdown(f"<div class='hx-cap'>"
                    f"Select days for analysis</div>", unsafe_allow_html=True)

        # Row 1: last 7 days
        day_cols = st.columns(7)
        for i, col in enumerate(day_cols):
            d = _today - pd.Timedelta(days=6-i)
            label = d.strftime("%a\n%d %b")
            selected = d in st.session_state.smhi_selected_days
            if col.button(label,
                          key=f"day_{d}",
                          type="primary" if selected else "secondary",
                          use_container_width=True):
                if selected:
                    st.session_state.smhi_selected_days.discard(d)
                else:
                    st.session_state.smhi_selected_days.add(d)
                st.rerun()

        # Expand to older dates
        with st.expander("← Older dates"):
            old_cols = st.columns(7)
            for i, col in enumerate(old_cols):
                d = _today - pd.Timedelta(days=13-i)
                label = d.strftime("%a\n%d %b")
                selected = d in st.session_state.smhi_selected_days
                if col.button(label,
                              key=f"day_old_{d}",
                              type="primary" if selected else "secondary",
                              use_container_width=True):
                    if selected:
                        st.session_state.smhi_selected_days.discard(d)
                    else:
                        st.session_state.smhi_selected_days.add(d)
                    st.rerun()

        # Quick actions
        qa1, qa2, qa3 = st.columns([1,1,3])
        if qa1.button("Select all", key="sel_all", use_container_width=True):
            st.session_state.smhi_selected_days = {_today - pd.Timedelta(days=i) for i in range(14)}
            st.rerun()
        if qa2.button("Clear all", key="sel_none", use_container_width=True):
            st.session_state.smhi_selected_days = set()
            st.rerun()

        # Derive date_from / date_to from selected days
        selected_days = sorted(st.session_state.smhi_selected_days)
        if not selected_days:
            st.info("Select at least one day above.")
            st.stop()
        date_from = selected_days[0]
        date_to   = selected_days[-1]

        # Convert to UTC — from = start of first day, to = end of last day
        dt_from = datetime.combine(date_from, datetime.min.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
        dt_to   = datetime.combine(date_to,   datetime.max.time()).replace(tzinfo=SWE).astimezone(timezone.utc)
        h_cmp   = max(24, int((dt_to - dt_from).total_seconds() / 3600) + 24)

        col_l, col_r = st.columns(2)
        with col_l:
            with st.spinner(T["loading_smhi"]):
                smhi_data, smhi_errors = fetch_smhi_and_store()
        with col_r:
            with st.spinner(T["loading_strang"]):
                days_back = max(1, (date_to - date_from).days + 2)
                df_strang, strang_errors = fetch_strang(days_back)

        if smhi_errors:
            with st.expander(f"⚠️ {len(smhi_errors)} SMHI-stationskälla(or) saknas"):
                for key, msg in smhi_errors.items():
                    st.warning(f"**{key}**: {msg}")

        with st.expander("📧 Test alert email", expanded=False):
            import smtplib
            from email.mime.text import MIMEText
            _gu = st.secrets.get("ALERT_GMAIL_USER", "")
            _gp = st.secrets.get("ALERT_GMAIL_APP_PASSWORD", "")
            st.caption(f"From: {_gu or '(not configured)'} → mats@helixis.se, eugene.nedilko@helixis.se")
            if st.button("Send test email now", key="test_email"):
                if not _gu or not _gp:
                    st.error("❌ ALERT_GMAIL_USER or ALERT_GMAIL_APP_PASSWORD missing in Secrets")
                else:
                    try:
                        _msg = MIMEText("Test alert from Helixis LC Monitor.", "plain", "utf-8")
                        _msg["Subject"] = "✅ Helixis alert test"
                        _msg["From"]    = _gu
                        _msg["To"]      = "mats@helixis.se, eugene.nedilko@helixis.se"
                        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as _srv:
                            _srv.login(_gu, _gp)
                            _srv.send_message(_msg)
                        st.success(f"✅ Sent from {_gu}")
                    except Exception as _e:
                        st.error(f"❌ {_e}")

        if strang_errors:
            with st.expander(f"⚠️ STRÅNG model: {len(strang_errors)} parameter(s) failed", expanded=True):
                for k, msg in strang_errors.items():
                    st.warning(f"**{k}**: {msg}")
                st.caption(f"New URL: opendata-download-metanalys.smhi.se/api/category/strang1g/version/1"
                           f"/geotype/point/lon/{SITE_LON}/lat/{SITE_LAT}/parameter/118/data.json?from=YYYYMMDDhh&to=YYYYMMDDhh&interval=hourly")
        elif not df_strang.empty:
            sensors_loaded = df_strang["sensor"].unique().tolist()
            last_ts = df_strang["created_at"].max().astimezone(SWE).strftime("%H:%M")
            st.success(f"✓ STRÅNG: {len(df_strang)} rows · {', '.join(sensors_loaded)} · latest: {last_ts}")

        # ── Väder just nu ─────────────────────────────────────────
        st.markdown('<div class="section-title">Weather conditions (SMHI stations)</div>',
                    unsafe_allow_html=True)
        smhi_defs = {
            "temperature": ("Air temp",    "°C",  -20, 40,   SLATE, 1),
            "wind_speed":  ("Wind speed",  "m/s",   0, 25,   SLATE, 1),
            "irradiance":  ("GHI (Växjö)", "W/m²",  0, 1500, AMBER, 0),
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

        # Fetch only the selected date range — cached 30 min, fast for historical days
        df_cmp = fetch_history_range(dt_from, dt_to)

        # All variables initialized — safe even if STRÅNG/sensor data is missing
        APERTURE = 12.35
        kt_current = None; dni_est_current = None; p_theoretical = None
        ETA_OPT = 0.65; merged = pd.DataFrame()
        eta_clear = pd.DataFrame(); eta_df = pd.DataFrame()
        eta_median = eta_p90 = eta_p95 = eta_max = None; n_pts = 0
        # System η (forward/return) — parallel calculation
        sys_clear = pd.DataFrame()
        sys_median = sys_p90 = sys_p95 = None; sys_pts = 0
        irr_live = df_cmp[df_cmp["sensor"]=="irradiance"].sort_values("created_at")
        pwr_live = df_cmp[df_cmp["sensor"]=="power"].sort_values("created_at")
        p_actual = float(pwr_live["value"].iloc[-1]) if not pwr_live.empty else None

        # Clip STRÅNG to selected date range
        df_st = pd.DataFrame()
        if not df_strang.empty:
            df_st = df_strang[
                (df_strang["created_at"] >= dt_from) &
                (df_strang["created_at"] <= dt_to)
            ].copy()

        # Use STRÅNG DNI directly — skip kt=DNI/GHI which breaks when GHI_STRÅNG≈0
        dni_strang_df = pd.DataFrame()
        if not df_st.empty:
            dni_rows = df_st[df_st["sensor"]=="dni_strang"][["created_at","value"]].copy()
            dni_rows = dni_rows.rename(columns={"value":"dni_strang"})
            dni_strang_df = dni_rows[dni_rows["dni_strang"] > 10].sort_values("created_at")

        if not dni_strang_df.empty and not irr_live.empty:
            last_ts    = irr_live["created_at"].iloc[-1]
            ghi_last   = float(irr_live["value"].iloc[-1])
            time_diffs = (dni_strang_df["created_at"] - last_ts).abs()
            best_mask  = time_diffs <= pd.Timedelta("3h")
            if best_mask.any():
                best_idx        = time_diffs[best_mask].idxmin()
                dni_est_current = float(dni_strang_df.loc[best_idx, "dni_strang"])
                kt_current      = (dni_est_current / ghi_last) if ghi_last > 20 else None

            pwr_df = pwr_live[["created_at","value"]].rename(columns={"value":"p_meas"})
        # Collector η: T_right (outlet) − T_left (inlet) × flow
        # Pure optical efficiency — no pipe/HX losses
        CP = 4186; RHO = 1000
        tr_df = df_cmp[df_cmp["sensor"]=="temp_right_coll"][["created_at","value"]].rename(columns={"value":"t_out"})
        tl_df = df_cmp[df_cmp["sensor"]=="temp_left_coll"][["created_at","value"]].rename(columns={"value":"t_in"})
        fl_df = df_cmp[df_cmp["sensor"]=="flow"][["created_at","value"]].rename(columns={"value":"flow"})

        if not tr_df.empty and not tl_df.empty and not fl_df.empty and not dni_strang_df.empty:
            eta_df = pd.merge_asof(tr_df.sort_values("created_at"),
                                   tl_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            eta_df = pd.merge_asof(eta_df.sort_values("created_at"),
                                   fl_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            eta_df = pd.merge_asof(eta_df.sort_values("created_at"),
                                   dni_strang_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("65min"),
                                   direction="nearest")
            eta_df = eta_df.dropna(subset=["t_out","t_in","flow","dni_strang"])
            if not eta_df.empty:
                eta_df["dT_coll"] = (eta_df["t_out"] - eta_df["t_in"]).abs()
                eta_df["p_coll"]  = thermal_power_kw(eta_df["flow"], eta_df["dT_coll"],
                                                    cp=CP, rho=RHO)
                eta_df = eta_df.sort_values("created_at")
                eta_df["dt_h"]   = eta_df["created_at"].diff().dt.total_seconds().fillna(0) / 3600
                eta_df["e_coll"] = eta_df["p_coll"]     * eta_df["dt_h"]
                eta_df["e_in"]   = eta_df["dni_strang"] * APERTURE / 1000 * eta_df["dt_h"]
                eta_df["strang_hour"] = eta_df["created_at"].dt.floor("1h")
                hourly_eta = eta_df.groupby("strang_hour").agg(
                    e_coll=("e_coll","sum"), e_in=("e_in","sum"),
                    dni_mean=("dni_strang","mean"),
                    p_mean=("p_coll","mean"),
                    flow_mean=("flow","mean"),
                    n=("flow","count")
                ).reset_index()
                hourly_eta = hourly_eta[
                    (hourly_eta["dni_mean"]  > 300) &
                    (hourly_eta["p_mean"]    > 0.5) &
                    (hourly_eta["flow_mean"] > FLOW_MIN_LMIN) &
                    (hourly_eta["n"]         > 10)
                ].copy()
                hourly_eta["eta_h"] = hourly_eta["e_coll"] / \
                    hourly_eta["e_in"].replace(0, float("nan"))
                hourly_eta = hourly_eta[
                    (hourly_eta["eta_h"] >= 0.10) &
                    (hourly_eta["eta_h"] <= 0.90)
                ]
                if not hourly_eta.empty:
                    eta_df = eta_df.merge(
                        hourly_eta[["strang_hour","eta_h"]], on="strang_hour", how="inner")
                    eta_df["eta_raw"] = eta_df["eta_h"]
                    eta_df["ghi_s"]   = eta_df["dni_strang"]
                    eta_clear = eta_df[
                        (eta_df["flow"] > FLOW_MIN_LMIN) & (eta_df["p_coll"] > 0.3)
                    ].copy()
        # Compute η statistics from qualifying samples
        if not eta_clear.empty:
            eta_median = float(eta_clear["eta_raw"].median())
            eta_p90    = float(eta_clear["eta_raw"].quantile(0.90))
            eta_p95    = float(eta_clear["eta_raw"].quantile(0.95))
            eta_max    = float(eta_clear["eta_raw"].max())
            n_pts      = len(eta_clear)
            ETA_OPT    = float(max(0.10, min(0.85, eta_p90)))
            p_theoretical = (dni_est_current * APERTURE * ETA_OPT) / 1000 \
                if dni_est_current is not None else None

        # ── System η: T_forward / T_return ────────────────────
        tf_df  = df_cmp[df_cmp["sensor"]=="temp_forward"][["created_at","value"]].rename(columns={"value":"t_fwd"})
        tr2_df = df_cmp[df_cmp["sensor"]=="temp_return"][["created_at","value"]].rename(columns={"value":"t_ret"})
        fl_df2 = df_cmp[df_cmp["sensor"]=="flow"][["created_at","value"]].rename(columns={"value":"flow"})

        if not tf_df.empty and not tr2_df.empty and not fl_df2.empty and not dni_strang_df.empty:
            sys_df = pd.merge_asof(tf_df.sort_values("created_at"),
                                   tr2_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            sys_df = pd.merge_asof(sys_df.sort_values("created_at"),
                                   fl_df2.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("2min"))
            sys_df = pd.merge_asof(sys_df.sort_values("created_at"),
                                   dni_strang_df.sort_values("created_at"),
                                   on="created_at", tolerance=pd.Timedelta("65min"),
                                   direction="nearest")
            sys_df = sys_df.dropna(subset=["t_fwd","t_ret","flow","dni_strang"])
            if not sys_df.empty:
                sys_df["dT_sys"] = (sys_df["t_fwd"] - sys_df["t_ret"]).abs()
                sys_df["p_sys"]  = thermal_power_kw(sys_df["flow"], sys_df["dT_sys"],
                                                   cp=CP, rho=RHO)
                sys_df = sys_df.sort_values("created_at")
                sys_df["dt_h"]  = sys_df["created_at"].diff().dt.total_seconds().fillna(0) / 3600
                sys_df["e_sys"] = sys_df["p_sys"]      * sys_df["dt_h"]
                sys_df["e_in"]  = sys_df["dni_strang"] * APERTURE / 1000 * sys_df["dt_h"]
                sys_df["strang_hour"] = sys_df["created_at"].dt.floor("1h")
                h_sys = sys_df.groupby("strang_hour").agg(
                    e_sys=("e_sys","sum"), e_in=("e_in","sum"),
                    dni_mean=("dni_strang","mean"),
                    p_mean=("p_sys","mean"), flow_mean=("flow","mean"),
                    n=("flow","count")
                ).reset_index()
                h_sys = h_sys[
                    (h_sys["dni_mean"]  > 300) & (h_sys["p_mean"]    > 0.5) &
                    (h_sys["flow_mean"] > FLOW_MIN_LMIN) & (h_sys["n"]        > 10)
                ].copy()
                h_sys["eta_h"] = h_sys["e_sys"] / h_sys["e_in"].replace(0, float("nan"))
                h_sys = h_sys[(h_sys["eta_h"] >= 0.05) & (h_sys["eta_h"] <= 0.90)]
                if not h_sys.empty:
                    sys_df = sys_df.merge(h_sys[["strang_hour","eta_h"]], on="strang_hour", how="inner")
                    sys_df["eta_raw"] = sys_df["eta_h"]
                    sys_clear = sys_df[(sys_df["flow"] > FLOW_MIN_LMIN) & (sys_df["p_sys"] > 0.3)].copy()

        if not sys_clear.empty:
            sys_median = float(sys_clear["eta_raw"].median())
            sys_p90    = float(sys_clear["eta_raw"].quantile(0.90))
            sys_p95    = float(sys_clear["eta_raw"].quantile(0.95))
            sys_pts    = len(sys_clear)
        # ── kt tiles ──────────────────────────────────────
        kt_color = TEAL if kt_current and kt_current > 0.6 else (AMBER if kt_current and kt_current > 0.3 else MUTED)
        efficiency_pct = (p_actual / p_theoretical * 100)                 if p_theoretical and p_theoretical > 0.1 and p_actual else None

        render_tiles([
            ("Clearness index kt",    kt_current,      "",     0, 1.2,  kt_color, 2, None),
            ("DNI estimated",         dni_est_current, "W/m²", 0, 1500, AMBER,    0, None),
            ("Theoretical max power", p_theoretical,   "kW",   0, 9.2,  RUST,     2, None),
            ("Actual power",          p_actual,        "kW",   0, 9.2,  TEAL,     2, None),
        ])
        # Show what data range was actually used
        if not df_st.empty and not df_cmp.empty:
            st_t0 = df_st["created_at"].min().astimezone(SWE).strftime("%b %d %H:%M")
            st_t1 = df_st["created_at"].max().astimezone(SWE).strftime("%b %d %H:%M")
            s_t0  = df_cmp["created_at"].min().astimezone(SWE).strftime("%b %d %H:%M")
            s_t1  = df_cmp["created_at"].max().astimezone(SWE).strftime("%b %d %H:%M")
            n_sensor = len(df_cmp[df_cmp["sensor"]=="irradiance"])
            n_strang = len(df_st)
            st.caption(f"Data used — sensor: {s_t0} → {s_t1} ({n_sensor} pts) · "
                       f"STRÅNG: {st_t0} → {st_t1} ({n_strang} pts)")
        if kt_current is None:
            st.caption("⚠ kt: no STRÅNG value within ±3h of latest sensor reading. "
                       "STRÅNG is hourly — analysis uses historical η from the window.")

        # ── Optical efficiency — headline + time series ────
        st.markdown('<div class="section-title">Optical efficiency η* over time</div>',
                    unsafe_allow_html=True)

        if eta_p90 is not None and n_pts > 5 or sys_p90 is not None and sys_pts > 5:
            ec1, ec2 = st.columns(2)

            # Collector η card
            with ec1:
                eta_color = TEAL if (eta_p90 or 0) > 0.62 else (AMBER if (eta_p90 or 0) > 0.45 else RUST)
                if eta_p90 is not None and n_pts > 5:
                    st.markdown(
                        f"<div style='background:{BG2};border-radius:8px;padding:12px 16px;"
                        f"border-left:3px solid {eta_color};height:100%'>"
                        f"<div style='font-size:.65rem;font-weight:600;color:{TEXT};"
                        f"text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px'>"
                        f"η Collector (T_right − T_left)*</div>"
                        f"<div style='font-size:2.2rem;font-weight:700;color:{eta_color}'>{eta_p90:.3f}"
                        f"<span style='font-size:.8rem;font-weight:400;color:{MUTED};margin-left:6px'>p90</span></div>"
                        f"<div style='font-size:.8rem;color:{MUTED};margin-top:2px'>"
                        f"median {eta_median:.3f} · p95 {eta_p95:.3f} · n={n_pts}h</div>"
                        f"<div style='font-size:.68rem;color:{MUTED};margin-top:4px;line-height:1.4'>"
                        f"* Pure optical η — collector in/out only</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    st.info("Collector η: insufficient data")

            # System η card
            with ec2:
                sys_color = TEAL if (sys_p90 or 0) > 0.55 else (AMBER if (sys_p90 or 0) > 0.35 else RUST)
                if sys_p90 is not None and sys_pts > 5:
                    st.markdown(
                        f"<div style='background:{BG2};border-radius:8px;padding:12px 16px;"
                        f"border-left:3px solid {sys_color};height:100%'>"
                        f"<div style='font-size:.65rem;font-weight:600;color:{TEXT};"
                        f"text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px'>"
                        f"η System (T_forward − T_return)**</div>"
                        f"<div style='font-size:2.2rem;font-weight:700;color:{sys_color}'>{sys_p90:.3f}"
                        f"<span style='font-size:.8rem;font-weight:400;color:{MUTED};margin-left:6px'>p90</span></div>"
                        f"<div style='font-size:.8rem;color:{MUTED};margin-top:2px'>"
                        f"median {sys_median:.3f} · p95 {sys_p95:.3f} · n={sys_pts}h</div>"
                        f"<div style='font-size:.68rem;color:{MUTED};margin-top:4px;line-height:1.4'>"
                        f"** Includes pipe & HX losses — lower than collector η</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    st.info("System η: insufficient data")

            st.caption(f"η = flow × ΔT × cp ÷ (DNI_STRÅNG × {APERTURE} m²) · "
                       f"Hourly integration · LC10 spec η_peak ≈ 0.72")

            # Time series chart of η per measurement point
            fig_eta = go.Figure()

            # All qualifying points as scatter
            fig_eta.add_trace(go.Scatter(
                x=eta_clear["created_at"], y=eta_clear["eta_raw"],
                name="η per sample",
                mode="markers",
                marker=dict(color=SLATE, size=4, opacity=0.5),
            ))

            # Rolling median (window=10 points) as smoothed line
            eta_sorted = eta_clear.sort_values("created_at")
            eta_rolling = eta_sorted["eta_raw"].rolling(10, min_periods=3, center=True).median()
            fig_eta.add_trace(go.Scatter(
                x=eta_sorted["created_at"], y=eta_rolling,
                name="Rolling median (10 pts)",
                mode="lines",
                line=dict(color=TEAL, width=2.5),
            ))

            # Reference lines
            fig_eta.add_hline(y=eta_p90, line_dash="dot", line_color=TEAL,
                annotation_text=f"p90 = {eta_p90:.3f}",
                annotation_position="right", annotation_font_size=11)
            fig_eta.add_hline(y=0.72, line_dash="dash", line_color=MUTED,
                annotation_text="LC10 spec 0.72",
                annotation_position="right", annotation_font_size=10)

            fig_eta.update_layout(
                height=280, margin=dict(l=0, r=80, t=10, b=0),
                yaxis=dict(title="η (–)", range=[0, 0.9],
                           gridcolor=BORDER, color=MUTED,
                           tickformat=".2f"),
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02,
                            font=dict(size=10, color=MUTED, family="Inter")),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=MUTED, family="Inter"))
            fig_eta.update_xaxes(showgrid=False, color=MUTED)
            st.plotly_chart(fig_eta, use_container_width=True,
                config=PLOT_CONFIG)
            # System η scatter overlay
            if not sys_clear.empty:
                sys_sorted  = sys_clear.sort_values("created_at")
                sys_rolling = sys_sorted["eta_raw"].rolling(10, min_periods=3, center=True).median()
                fig_eta.add_trace(go.Scatter(
                    x=sys_sorted["created_at"], y=sys_sorted["eta_raw"],
                    name="η system (fwd/ret)",
                    mode="markers",
                    marker=dict(color=AMBER, size=4, opacity=0.4)))
                fig_eta.add_trace(go.Scatter(
                    x=sys_sorted["created_at"], y=sys_rolling,
                    name="System rolling median",
                    mode="lines",
                    line=dict(color=AMBER, width=2, dash="dash")))

            st.caption("Teal = collector η (T_right/T_left) · Amber dashed = system η (forward/return) · "
                       "Gap between the two = pipe and heat exchanger losses.")

        else:
            # Debug info — show why no samples qualified
            n_total   = len(eta_df) if not eta_df.empty else 0
            n_day     = len(eta_df[eta_df["ghi_s"] > 400]) if not eta_df.empty else 0
            n_running = len(eta_df[(eta_df["ghi_s"] > 400) & (eta_df["p_meas"] > 1.0)])                             if not eta_df.empty else 0
            st.info(f"Optical efficiency: insufficient qualifying samples. "
                    f"Overlap rows: {n_total} · GHI>400: {n_day} · GHI>400 & P>1kW: {n_running}. "
                    f"Select a window with clear sun and system running.")

        if efficiency_pct is not None:
            eff_color = TEAL if efficiency_pct > 75 else (AMBER if efficiency_pct > 40 else RUST)
            st.markdown(
                f"<div style='margin:8px 0 4px;font-size:.9rem;color:{TEXT}'>"
                f"Instantaneous system performance: <b style='color:{eff_color}'>{efficiency_pct:.0f}%</b> "
                f"of theoretical maximum"
                f"<span style='font-size:.75rem;color:{MUTED};margin-left:8px'>"
                f"({fmt(p_actual,2,'kW')} measured vs {fmt(p_theoretical,2,'kW')} theoretical)</span>"
                f"</div>",
                unsafe_allow_html=True
            )

        # ── Graf: GHI sensor vs STRÅNG GHI + DNI ──────────────────
        # ── Single combined chart: GHI sensor + DNI STRÅNG + Power + η ──
        st.markdown('<div class="section-title">Irradiance, power & optical efficiency — combined view</div>',
                    unsafe_allow_html=True)
        st.caption("Only periods with GHI > 100 W/m² or Power > 0.5 kW shown. "
                   "DNI from STRÅNG model (hourly). η = P / (DNI × 12.35 m²).")

        # Build combined dataframe: sensor irradiance + power + STRÅNG DNI
        irr_all = df_cmp[df_cmp["sensor"]=="irradiance"][["created_at","value"]].rename(columns={"value":"ghi"})
        pwr_all = df_cmp[df_cmp["sensor"]=="power"][["created_at","value"]].rename(columns={"value":"power"})

        if not irr_all.empty and not pwr_all.empty:
            combo = pd.merge_asof(irr_all.sort_values("created_at"),
                                  pwr_all.sort_values("created_at"),
                                  on="created_at", tolerance=pd.Timedelta("5min"))
            if not dni_strang_df.empty:
                combo = pd.merge_asof(combo.sort_values("created_at"),
                                      dni_strang_df.sort_values("created_at"),
                                      on="created_at", tolerance=pd.Timedelta("65min"),
                                      direction="nearest")
            else:
                combo["dni_strang"] = None

            # Filter: only show where sun is up or system running
            mask = (combo["ghi"] > 100) | (combo["power"] > 0.5)
            combo = combo[mask].copy()

            # Compute η per point where DNI available and meaningful
            if "dni_strang" in combo.columns:
                denom = (combo["dni_strang"] * 12.35 / 1000).replace(0, float("nan"))
                combo["eta_pt"] = (combo["power"] / denom).where(
                    (combo["dni_strang"] > 200) & (combo["power"] > 0.5))
                combo.loc[combo["eta_pt"] > 0.95, "eta_pt"] = float("nan")  # clip outliers

            if not combo.empty:
                fig_combo = go.Figure()

                # Left axis: irradiance W/m²
                fig_combo.add_trace(go.Scatter(
                    x=combo["created_at"], y=combo["ghi"],
                    name="GHI sensor (W/m²)", mode="lines",
                    line=dict(color=AMBER, width=2), yaxis="y"))

                if "dni_strang" in combo.columns:
                    fig_combo.add_trace(go.Scatter(
                        x=combo["created_at"], y=combo["dni_strang"],
                        name="DNI STRÅNG (W/m²)", mode="lines",
                        line=dict(color=RUST, width=1.5, dash="dash"), yaxis="y"))

                # Right axis: power kW
                fig_combo.add_trace(go.Scatter(
                    x=combo["created_at"], y=combo["power"],
                    name="Thermal power (kW)", mode="lines",
                    line=dict(color=TEAL, width=2.5), yaxis="y2"))

                # Right axis: η (0–1) — also on y2 scaled 0–10 to align with kW
                if "eta_pt" in combo.columns:
                    fig_combo.add_trace(go.Scatter(
                        x=combo["created_at"],
                        y=combo["eta_pt"] * 10,  # scale: η×10 so 0.65 → 6.5 kW-equiv
                        name="η × 10 (right axis)", mode="markers",
                        marker=dict(color=BLUE, size=3, opacity=0.6), yaxis="y2"))

                _eta_disp = f"η_p90 = {eta_p90:.3f}" if eta_p90 else "η not yet computed"
                fig_combo.update_layout(
                    height=380, margin=dict(l=0, r=60, t=10, b=0),
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                font=dict(size=10, color=MUTED, family="Inter")),
                    yaxis=dict(title=dict(text="W/m²", font=dict(color=AMBER)),
                               tickfont=dict(color=AMBER), gridcolor=BORDER, rangemode="tozero"),
                    yaxis2=dict(title=dict(text="kW  |  η×10", font=dict(color=TEAL)),
                                tickfont=dict(color=TEAL), overlaying="y", side="right",
                                showgrid=False, rangemode="tozero"),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color=MUTED, family="Inter"),
                    annotations=[dict(
                        text=_eta_disp, x=1, y=1.08, xref="paper", yref="paper",
                        showarrow=False, font=dict(size=11, color=TEAL)
                    )]
                )
                fig_combo.update_xaxes(showgrid=False, color=MUTED)
                st.plotly_chart(fig_combo, use_container_width=True,
                    config=PLOT_CONFIG)
                st.caption("η×10 plotted on power axis so 0.65 → 6.5 on right scale. "
                           "Gap between DNI-based theoretical and actual power = system losses.")

        # ── kt-tidsserie ──────────────────────────────────────────
        if not df_st.empty and not dni_strang_df.empty:
            st.markdown('<div class="section-title">Clearness index kt over time</div>',
                        unsafe_allow_html=True)
            # Compute kt = DNI_STRÅNG / GHI_sensor — only when sun is clearly up
            # Filter GHI > 150 to avoid division noise at dawn/dusk
            kt_combo = pd.merge_asof(
                irr_all[irr_all["ghi"] > 150].sort_values("created_at"),
                dni_strang_df.sort_values("created_at"),
                on="created_at", tolerance=pd.Timedelta("65min"), direction="nearest")
            kt_combo = kt_combo.dropna()
            # kt physically 0–1.5 max; clip and filter outliers
            kt_combo["kt"] = kt_combo["dni_strang"] / kt_combo["ghi"]
            kt_combo = kt_combo[(kt_combo["kt"] >= 0) & (kt_combo["kt"] <= 1.5)]
            fig_kt = go.Figure()
            fig_kt.add_trace(go.Scatter(
                x=kt_combo["created_at"], y=kt_combo["kt"],
                name="kt = DNI_STRÅNG / GHI_sensor", mode="lines",
                line=dict(color=TEAL, width=2),
                fill="tozeroy", fillcolor="rgba(22,122,94,0.1)"))
            fig_kt.add_hline(y=0.7, line_dash="dot", line_color=AMBER,
                             annotation_text="Clear sky (kt=0.7)")
            fig_kt.update_layout(
                height=200, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title="kt", range=[0, 1.5], gridcolor=BORDER, color=MUTED),
                hovermode="x unified",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=MUTED, family="Inter"))
            fig_kt.update_xaxes(showgrid=False, color=MUTED)
            st.plotly_chart(fig_kt, use_container_width=True, config=PLOT_CONFIG)
            st.caption("kt > 0.7 = clear sky, direct sunlight optimal for concentrating systems. "
                       "kt < 0.3 = heavy cloud cover, DNI too low for meaningful CSP output.")

# ── Om systemet tab ──────────────────────────────────────────
if page == "about":
    c_sys, c_map = st.columns([1, 1])
    with c_sys:
        st.markdown(f"<div class='section-title'>{T['about_spec']}</div>",
                    unsafe_allow_html=True)
        st.markdown(f"""<div style='font-size:.85rem;color:{MUTED};line-height:2.1'>
<b style='color:{TEXT}'>Helixis LC10 HW</b><br>
Linear Concentrator — CSP<br>
Aperture: 12.35 m² · 380 kg<br>
Peak output: 9.2 kW @ 1000 W/m²<br>
Max temp: 160°C · Max pressure: 6 bar
</div>""", unsafe_allow_html=True)

        st.markdown(f"<div class='section-title' style='margin-top:24px'>{T['about_location']}</div>",
                    unsafe_allow_html=True)
        st.markdown(f"""<div style='font-size:.85rem;color:{MUTED};line-height:2.1'>
<b style='color:{TEXT}'>Eket, Örkelljunga</b><br>
{T['about_coords']}: 56.248°N · 13.192°E<br>
{T['about_alt']}: ~130 m<br>
{T['about_region']}: Skåne
</div>""", unsafe_allow_html=True)

    with c_map:
        st.markdown(f"<div class='section-title'>{T['about_aerial']}</div>",
                    unsafe_allow_html=True)
        if os.path.exists("eket_aerial.png"):
            st.image("eket_aerial.png", caption="Eket, Örkelljunga · © Google Maps",
                     use_container_width=True)
        else:
            st.info(T['about_add_img'])

# ── Sidebar (minimal) ─────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='color:{TEXT};font-weight:600;font-size:.9rem;margin-bottom:8px'>Helixis LC10</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:.72rem;color:{MUTED}'>Eket · Örkelljunga · 56.248°N"
                f"<br><span style='font-size:.62rem;opacity:.75'>build {APP_BUILD}</span></div>",
                unsafe_allow_html=True)