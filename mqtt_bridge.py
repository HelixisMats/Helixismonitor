"""
mqtt_bridge.py
──────────────
Subscribes to helix/1/1234/data on eaasy.life:1883
and inserts readings into Supabase via direct HTTP REST calls.

Timestamps: uses the DEVICE'S OWN measurement timestamp (from the payload) as
created_at when available, falling back to the bridge receive time. This is what
keeps data correct after an outage: when a device buffers readings during a
disconnect and floods them on reconnect, each row keeps its true measurement time
instead of all collapsing onto the reconnect moment.
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

# Fields in the payload that are metadata, not sensor values (never stored as sensors)
SKIP_FIELDS = {"timestamp", "time", "date", "datetime", "ts", "epoch",
               "unixtime", "unix_time", "measured_at", "recorded_at"}

# Candidate keys that may carry the device's own measurement timestamp
TS_KEYS = ("timestamp", "time", "ts", "datetime", "date", "epoch",
           "unixtime", "unix_time", "measured_at", "recorded_at")

# Log the timestamp source only occasionally, so it is easy to verify without spam
_ts_log_counter = {"n": 0}


def parse_device_ts(data: dict):
    """Return an ISO-8601 UTC string from the device's own timestamp field, or
    None if it is absent / unparseable / implausible. Auto-detects epoch seconds,
    epoch milliseconds and ISO-8601 strings. Never raises."""
    if not isinstance(data, dict):
        return None
    for key in data:
        if str(key).lower() not in TS_KEYS:
            continue
        raw = data[key]
        try:
            # Numeric epoch (int/float or a numeric string)
            is_numeric_str = isinstance(raw, str) and raw.strip().replace(".", "", 1).isdigit()
            if isinstance(raw, (int, float)) or is_numeric_str:
                num = float(raw)
                if num > 1e12:        # milliseconds since epoch
                    dt = datetime.fromtimestamp(num / 1000, tz=timezone.utc)
                elif num > 1e9:       # seconds since epoch
                    dt = datetime.fromtimestamp(num, tz=timezone.utc)
                else:
                    continue          # too small to be a real epoch — skip this field
            else:
                # ISO-8601 string (handle trailing 'Z'; assume UTC if no offset)
                s = str(raw).strip().replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            # Sanity check — reject unset/garbage clocks (e.g. 1970 or far future)
            if dt.year < 2020 or dt.year > 2100:
                continue
            return dt.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError, OSError):
            continue
    return None


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

    recv_now = datetime.now(timezone.utc).isoformat()
    rows = []

    try:
        data = json.loads(payload)
        if isinstance(data, dict):
            # Prefer the device's own measurement time; fall back to receive time
            device_ts = parse_device_ts(data)
            ts = device_ts or recv_now

            # Verify/log the timestamp source occasionally (first msg, then every 500th)
            if _ts_log_counter["n"] % 500 == 0:
                if device_ts:
                    log.info(f"Timestamp: using device time {device_ts} "
                             f"(payload keys: {list(data.keys())})")
                else:
                    log.warning("Timestamp: NO device timestamp found — using receive "
                                f"time. Buffered data after an outage will collapse. "
                                f"Payload keys: {list(data.keys())}")
            _ts_log_counter["n"] += 1

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
                        "created_at": ts,
                    })
                except (ValueError, TypeError):
                    log.debug(f"Skipping non-numeric: {sensor_clean}={value!r}")
    except json.JSONDecodeError:
        # Non-JSON payload — no device timestamp available, use receive time
        try:
            rows.append({
                "sensor":     msg.topic.split("/")[-1],
                "value":      float(payload),
                "topic":      msg.topic,
                "created_at": recv_now,
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
