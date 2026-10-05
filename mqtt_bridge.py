"""
mqtt_bridge.py — Helixis LC Monitor
Subscribes to helix/3/1/data on eaasy.life:1883
Decodes the plc_block register array and inserts into Supabase.

Message format:
  {"plc_block": {"ts": "2026-10-05T14:11:32Z", "r": [mode, h0,l0, h1,l1, ...]}}

Decoding:
  r[0]         = concentrator mode (int)
  r[1+2i], r[2+2i] = high/low 16-bit words of signed int32, value = raw / 100
"""

import os, time, uuid, json, logging, urllib.request, urllib.error
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

MQTT_BROKER   = os.getenv("MQTT_BROKER",   "eaasy.life")
MQTT_PORT     = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC    = os.getenv("MQTT_TOPIC",    "helix/3/1/data")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]

# V[i] field names — index matches i in the register pairs
FIELDS = [
    "temp_supply",          # V[0]
    "temp_return",          # V[1]
    "temp_tank",            # V[2]
    "pressure",             # V[3]
    "flow",                 # V[4]
    "wind",                 # V[5]
    "irradiance",           # V[6]
    "heat_power",           # V[7]
    "heat_energy_total",    # V[8]
    "heat_energy_yesterday",# V[9]
    "heat_energy_today",    # V[10]
    "heat_energy_last_hour",# V[11]
    "heat_energy_this_hour",# V[12]
    "sun_azimuth",          # V[13]
    "sun_elevation",        # V[14]
    "conc_azimuth",         # V[15]
    "conc_elevation",       # V[16]
    "reserve",              # V[17]
]

MODE_NAMES = {
    0: "Stop", 1: "Tracking", 2: "Parking", 3: "Rain",
    4: "Manual", 5: "StandBy", 6: "Calibration", 7: "Wind protection"
}

def decode_registers(r):
    """Decode PLC register array into {sensor: value} dict."""
    result = {}

    # r[0] = concentrator mode
    result["concentrator_mode"] = int(r[0])
    log.info(f"  mode = {r[0]} ({MODE_NAMES.get(int(r[0]), 'Unknown')})")

    # r[1..] = pairs of 16-bit words forming signed int32, scaled /100
    for i, name in enumerate(FIELDS):
        idx_hi = 1 + 2 * i
        idx_lo = 2 + 2 * i
        if idx_lo >= len(r):
            break
        hi = int(r[idx_hi]) & 0xFFFF
        lo = int(r[idx_lo]) & 0xFFFF
        raw = (hi << 16) | lo
        # Convert to signed int32
        if raw >= 0x80000000:
            raw -= 0x100000000
        value = raw / 100.0
        result[name] = value

    return result


def insert_rows(rows):
    """Insert rows into Supabase via HTTP REST."""
    url = f"{SUPABASE_URL}/rest/v1/sensor_readings"
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "apikey":        SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        log.error(f"Supabase HTTP {e.code}: {e.read().decode('utf-8','ignore')}")
    except Exception as exc:
        log.error(f"Supabase error: {exc}")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        log.info(f"Connected to {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC, qos=1)
        log.info(f"Subscribed to: {MQTT_TOPIC}")
    else:
        log.error(f"Connection failed: rc={reason_code}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        log.warning(f"Disconnected (rc={reason_code}). Will reconnect…")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse error: {e}")
        return

    # Find the block containing 'ts' and 'r' — regardless of wrapper name
    block = None
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, dict) and "ts" in v and "r" in v:
                block = v
                break
        if block is None and "ts" in payload and "r" in payload:
            block = payload

    if not block:
        log.warning(f"No valid block found in payload: {str(payload)[:100]}")
        return

    ts_str = block.get("ts")
    r      = block.get("r", [])

    # Use message timestamp if available, otherwise now
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).isoformat()
    except Exception:
        ts = datetime.now(timezone.utc).isoformat()

    sensors = decode_registers(r)

    rows = []
    for sensor, value in sensors.items():
        if sensor == "reserve":
            continue
        rows.append({
            "sensor":     sensor,
            "value":      float(value),
            "topic":      msg.topic,
            "created_at": ts,
        })

    if not rows:
        return

    status = insert_rows(rows)
    if status and status < 300:
        log.info(f"  ✓ Inserted {len(rows)} sensors @ {ts}")
    else:
        log.error(f"  ✗ Insert failed (status={status})")


def main():
    client_id = f"helix-bridge-{uuid.uuid4().hex[:8]}"
    log.info(f"Client ID: {client_id}")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=True,
    )
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    retry = 5
    while True:
        try:
            log.info(f"Connecting to {MQTT_BROKER}:{MQTT_PORT}…")
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            retry = 5
            client.loop_forever()
        except OSError as e:
            log.error(f"Network error: {e}. Retry in {retry}s…")
            time.sleep(retry)
            retry = min(retry * 2, 60)
        except KeyboardInterrupt:
            log.info("Shutting down.")
            client.disconnect()
            break


if __name__ == "__main__":
    main()
