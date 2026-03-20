"""
mqtt_bridge.py
──────────────
Subscribes to helix/1/1234/data on eaasy.life:1883
and mirrors every sensor reading into Supabase.
"""

import os
import time
import uuid
import json
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
MQTT_TOPIC    = os.getenv("MQTT_TOPIC",    "helix/1/1234/data")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]

SKIP_FIELDS = {"timestamp", "time", "date"}

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_key(s):
    """Return ASCII-safe key or None if unusable."""
    try:
        cleaned = s.encode("ascii", errors="ignore").decode("ascii").strip()
        return cleaned if cleaned else None
    except Exception:
        return None


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        log.info(f"Connected to {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC, qos=0)
        log.info(f"Subscribed to: {MQTT_TOPIC}")
    else:
        log.error(f"Connection failed: reason_code={reason_code}")


def on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        log.warning(f"Unexpected disconnect (rc={reason_code}). Will reconnect...")


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", errors="ignore").strip()
    now = datetime.now(timezone.utc).isoformat()
    rows = []

    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            for sensor, value in data.items():
                sensor_clean = clean_key(sensor)
                if not sensor_clean:
                    continue
                if sensor_clean.lower() in SKIP_FIELDS:
                    continue
                try:
                    rows.append({
                        "sensor":     sensor_clean,
                        "value":      float(value),
                        "topic":      msg.topic,
                        "created_at": now,
                    })
                except (ValueError, TypeError):
                    log.debug(f"Skipping non-numeric: {sensor_clean}={value!r}")
        else:
            log.warning(f"Unexpected JSON type: {type(data)}")
    except json.JSONDecodeError:
        try:
            rows.append({
                "sensor":     msg.topic.split("/")[-1],
                "value":      float(payload),
                "topic":      msg.topic,
                "created_at": now,
            })
        except ValueError:
            log.warning(f"Could not parse payload: {payload!r}")
            return

    if not rows:
        return

    try:
        supabase.table("sensor_readings").insert(rows).execute()
        for r in rows:
            log.info(f"  {r['sensor']:<22} = {r['value']}")
    except Exception as exc:
        log.error(f"Supabase insert error: {exc}")


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

    log.info(f"Connecting to {MQTT_BROKER}:{MQTT_PORT} ...")

    retry_delay = 5
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            retry_delay = 5
            client.loop_forever()
        except OSError as exc:
            log.error(f"Network error: {exc}. Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        except KeyboardInterrupt:
            log.info("Shutting down.")
            client.disconnect()
            break


if __name__ == "__main__":
    main()
