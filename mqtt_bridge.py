"""
mqtt_bridge.py
──────────────
Subscribes to eaasy.life:1883 and mirrors every reading into Supabase.
"""

import os
import time
import uuid
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from supabase import create_client, Client
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
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]

# Subscribe to each sensor individually to avoid wildcard restrictions
SENSORS = [
    "Energifaktor", "wind", "pressure", "temp_right_coll", "temp_left_coll",
    "temp_tank", "temp_difference", "temp_return", "temp_forward",
    "flow", "power", "volume", "heat_energy", "temp_cell", "irradiance",
]
TOPICS = [f"testnod-mqtt-helix/{s}" for s in SENSORS]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        log.info(f"Connected ✓ → {MQTT_BROKER}:{MQTT_PORT}")
        for topic in TOPICS:
            client.subscribe(topic, qos=0)
            log.info(f"  Subscribed: {topic}")
    else:
        log.error(f"Connection failed: reason_code={reason_code}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        log.warning(f"Unexpected disconnect (rc={reason_code}). Will reconnect…")


def on_message(client, userdata, msg):
    topic   = msg.topic
    sensor  = topic.split("/")[-1]
    payload = msg.payload.decode("utf-8", errors="replace").strip()

    try:
        value = float(payload)
    except ValueError:
        log.debug(f"Skipping non-numeric payload on {topic!r}: {payload!r}")
        return

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


def main():
    # Random client ID avoids conflicts with other connected clients
    client_id = f"helix-bridge-{uuid.uuid4().hex[:8]}"
    log.info(f"Client ID: {client_id}")

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=True,
    )

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
            retry_delay = 5
            client.loop_forever()
        except OSError as exc:
            log.error(f"Network error: {exc}. Retrying in {retry_delay}s…")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        except KeyboardInterrupt:
            log.info("Shutting down bridge.")
            client.disconnect()
            break


if __name__ == "__main__":
    main()
