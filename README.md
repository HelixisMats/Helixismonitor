# Helix Energy Monitor 🌡️

Real-time dashboard for your solar/heating system — MQTT → Supabase → Streamlit.

## Architecture

```
Device → eaasy.life:1883  (existing, untouched)
              │
         mqtt_bridge.py   ← runs on your PC
              │
         Supabase          ← stores all readings
              │
         Streamlit Cloud   ← dashboard (browser)
```

No changes to your device or local broker needed in Phase 1.

---

## Step 1 — Supabase setup

1. Open your Supabase project → **SQL Editor**
2. Paste and run the contents of `supabase_setup.sql`
3. Go to **Settings → API** and copy:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` secret key → `SUPABASE_KEY`  *(not the anon key)*

---

## Step 2 — Run the MQTT bridge on your PC

```bash
# Install dependencies
pip install paho-mqtt supabase python-dotenv

# Configure credentials
cp .env.example .env
# Edit .env with your Supabase URL and key

# Start the bridge (keep this terminal open)
python mqtt_bridge.py
```

You should see lines like:
```
2026-03-20 11:42:01 [INFO] Connected ✓ → eaasy.life:1883
2026-03-20 11:42:01 [INFO] Subscribed to testnod-mqtt-helix/#
2026-03-20 11:42:05 [INFO] power                  = 5.403
2026-03-20 11:42:05 [INFO] irradiance             = 1007.4
```

To run it permanently in the background on Windows:
```
pythonw mqtt_bridge.py
```
Or on Linux/Mac, use `nohup python mqtt_bridge.py &` or a systemd service.

---

## Step 3 — Deploy the Streamlit dashboard

1. Push this folder to a GitHub repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo and set **Main file path** to `streamlit_app.py`
4. Go to **Advanced settings → Secrets** and add:

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJ..."
```

5. Deploy — your dashboard is live!

---

## Sensors

| Sensor | Unit | Description |
|---|---|---|
| temp_right_coll | °C | Right solar collector temperature |
| temp_left_coll | °C | Left solar collector temperature |
| temp_tank | °C | Storage tank temperature |
| temp_forward | °C | Heating circuit forward temperature |
| temp_return | °C | Heating circuit return temperature |
| temp_difference | °C | Forward − return ΔT |
| temp_cell | °C | Solar cell temperature |
| power | kW | Thermal power output |
| heat_energy | kWh | Cumulative heat energy |
| Energifaktor | — | Energy factor (COP-like metric) |
| flow | m³/h | Flow rate |
| volume | L | Total volume |
| irradiance | W/m² | Solar irradiance |
| wind | m/s | Wind speed |
| pressure | bar | System pressure |

---

## Phase 2 — Your own broker (later)

When you're ready to cut over from eaasy.life:

```bash
# Install Mosquitto
sudo apt install mosquitto mosquitto-clients

# Edit /etc/mosquitto/mosquitto.conf
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd

# Create a user
sudo mosquitto_passwd -c /etc/mosquitto/passwd youruser

# Restart
sudo systemctl restart mosquitto
```

Then update your device to point at your broker IP and update the bridge `.env`:
```
MQTT_BROKER=192.168.x.x
MQTT_USERNAME=youruser
MQTT_PASSWORD=yourpassword
```
