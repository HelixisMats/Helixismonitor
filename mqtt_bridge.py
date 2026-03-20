"""
mqtt_bridge.py
──────────────
Subscribes to helix/1/1234/data on eaasy.life:1883
and inserts readings into Supabase via direct HTTP REST calls.
"""

import os
import time
import uuid
import json
import logging
import urllib.request
import urllib.error
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
MQTT_TOPIC    = os.getenv("MQTT_TOPIC",    "helix/1/1234/data")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]

SKIP_FIELDS = {"timestamp", "time", "date"}


def insert_rows(rows):
    """Insert rows into Supabase using plain urllib — no encoding issues."""
    url = f"{SUPABASE_URL}/rest/v1/sensor_readings"
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
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
        body = e.read().decode("utf-8", errors="ignore")
        log.error(f"Supabase HTTP error {e.code}: {body}")
    except Exception as exc:
        log.error(f"Supabase request error: {exc}")


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
    try:
        payload = msg.payload.decode("utf-8", errors="ignore").strip()
    except Exception as e:
        log.error(f"Payload decode error: {e}")
        return

    now = datetime.now(timezone.utc).isoformat()
    rows = []

    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            for sensor, value in data.items():
                # Keep only printable ASCII in sensor name
                sensor_clean = "".join(c for c in sensor if 32 <= ord(c) < 128).strip()
                if not sensor_clean or sensor_clean.lower() in SKIP_FIELDS:
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

    status = insert_rows(rows)
    if status and status < 300:
        for r in rows:
            log.info(f"  {r['sensor']:<22} = {r['value']}")


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
