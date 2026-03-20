"""
mqtt_bridge.py
──────────────
Subscribes to eaasy.life:1883 and mirrors every reading into Supabase.
Run this on the PC that already logs data — no changes to the device needed.

Setup:
  pip install paho-mqtt supabase python-dotenv
  cp .env.example .env   # fill in your credentials
  python mqtt_bridge.py
"""

import os
import time
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config (edit here or via .env) ────────────────────────────
MQTT_BROKER   = os.getenv("MQTT_BROKER",   "eaasy.life")
MQTT_PORT     = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC    = os.getenv("MQTT_TOPIC",    "testnod-mqtt-helix/#")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

SUPABASE_URL  = os.environ["SUPABASE_URL"]   # required
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]   # required — use service-role key
# ──────────────────────────────────────────────────────────────

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── MQTT callbacks ─────────────────────────────────────────────

def on_connect(client, userdata, flags, rc):
    codes = {
        0: "Connected ✓",
        1: "Wrong protocol version",
        2: "Client ID rejected",
        3: "Broker unavailable",
        4: "Bad username/password",
        5: "Not authorised",
    }
    msg = codes.get(rc, f"Unknown rc={rc}")
    if rc == 0:
        log.info(f"{msg} → {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        log.info(f"Subscribed to  {MQTT_TOPIC}")
    else:
        log.error(f"Connection failed: {msg}")


def on_disconnect(client, userdata, rc):
    if rc != 0:
        log.warning(f"Unexpected disconnect (rc={rc}). Will reconnect…")


def on_message(client, userdata, msg):
    topic   = msg.topic                        # e.g. testnod-mqtt-helix/power
    sensor  = topic.split("/")[-1]             # last segment → sensor name
    payload = msg.payload.decode("utf-8", errors="replace").strip()

    # Parse numeric value
    try:
        value = float(payload)
    except ValueError:
        log.debug(f"Skipping non-numeric payload on {topic!r}: {payload!r}")
        return

    # Insert into Supabase
    try:
        supabase.table("sensor_readings").insert({
            "sensor":     sensor,
            "value":      value,
            "topic":      topic,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        log.info(f"  {sensor:<22} = {value}")
    except Exception as exc:
        log.error(f"Supabase insert error for {sensor!r}: {exc}")


# ── Main loop with auto-reconnect ─────────────────────────────

def main():
    client = mqtt.Client(client_id="helix-bridge-v1", clean_session=True)

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        log.info(f"Using MQTT credentials for user: {MQTT_USERNAME}")

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message

    log.info(f"Connecting to {MQTT_BROKER}:{MQTT_PORT} …")

    retry_delay = 5
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            retry_delay = 5                  # reset backoff on success
            client.loop_forever()            # blocks; handles reconnects internally
        except OSError as exc:
            log.error(f"Network error: {exc}. Retrying in {retry_delay}s…")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)   # exponential backoff, max 60s
        except KeyboardInterrupt:
            log.info("Shutting down bridge.")
            client.disconnect()
            break


if __name__ == "__main__":
    main()
