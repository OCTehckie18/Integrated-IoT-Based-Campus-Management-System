"""Phase 2: publish ONE message as the simulated ESP32 (CLASS-A-ESP32-01).
Usage: python send_one.py [good|missing|badjson|unknown|badtime|range]
Every message carries source=simulated so it can never pass as real hardware.
"""
import json, os, sys
from datetime import datetime, timezone
import paho.mqtt.client as mqtt  # paho-mqtt 2.x API (verify: pip show paho-mqtt)

HOST = os.getenv("MQTT_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT", "1883"))
BASE = "christ-smart-campus/v1"
MODULE, BUILDING, ZONE, DEVICE = "classroom", "BLOCK-A", "ROOM-204", "CLASS-A-ESP32-01"


def good():
    return {
        "schema_version": "1.0", "campus_id": "CHRIST-DEMO", "module": MODULE,
        "building_id": BUILDING, "zone_id": ZONE, "device_id": DEVICE,
        # ISO 8601, UTC, explicit timezone, so the backend can compare clocks safely
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metric": "temperature", "value": 29.2, "unit": "C",
        "status": "normal", "source": "simulated",
    }


case = sys.argv[1] if len(sys.argv) > 1 else "good"
msg, topic_device = good(), DEVICE
if case == "missing":
    del msg["device_id"]                                   # T2: missing field rejected
elif case == "unknown":
    msg["device_id"] = topic_device = "GHOST-99"           # T3: unknown device flagged
elif case == "badtime":
    msg["timestamp"] = "yesterday-ish"
elif case == "range":
    msg["value"] = 250.0                                   # out of range for temperature
payload = "{not json" if case == "badjson" else json.dumps(msg)

topic = f"{BASE}/{MODULE}/{BUILDING}/{topic_device}/telemetry"
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{DEVICE}-once")
c.connect(HOST, PORT, 30)
c.loop_start()
info = c.publish(topic, payload, qos=1)   # QoS 1: broker acknowledges receipt
info.wait_for_publish()
c.loop_stop()
c.disconnect()
print(f"[{case}] published to {topic}\n{payload}")
