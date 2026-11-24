"""Simulated classroom ESP32 (CLASS-A-ESP32-01). Phases 3-5 merged.

EVERY message carries "source":"simulated". This is NOT real hardware.

Run:   python classroom_sim.py            interactive (type commands, see HELP below)
       python classroom_sim.py --demo     ~105 s scripted scenario, then exits

Publishing contract (spec): telemetry every 10 s, immediate event on state change,
heartbeat every 45 s, QoS 1, last-will marks the device offline if it vanishes.
"""
import argparse, json, os, sys, threading, time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt          # paho-mqtt 2.x API
from classroom_logic import ClassroomController

HOST = os.getenv("MQTT_HOST", "127.0.0.1")
PORT = int(os.getenv("MQTT_PORT", "1883"))
USER, PASS = os.getenv("MQTT_USER"), os.getenv("MQTT_PASS")

CAMPUS, MODULE = "CHRIST-DEMO", "classroom"
BUILDING, ZONE, DEVICE = "BLOCK-A", "ROOM-204", "CLASS-A-ESP32-01"
BASE = f"christ-smart-campus/v1/{MODULE}/{BUILDING}/{DEVICE}"   # building-level topic (agreed)

TELEMETRY_S, HEARTBEAT_S, DHT_PERIOD_S = 10, 45, 2   # DHT22 needs >= 2 s between reads
KEEPALIVE_S = 30                                     # broker declares us gone after ~1.5x this
LED_LIGHT_BOOST = 25.0                               # our own lamp raises the LDR reading

HELP = """commands: enter | still | leave | blip | dark | bright | temp <C> | dhtfail | dhtok
          status | help | quit
  enter  person walks in and moves     still  person present but motionless (PIR silent)
  leave  person leaves                 blip   single false PIR pulse (should be ignored)
  dark/bright  ambient light           temp 31.5  set room temperature
  dhtfail/dhtok  disconnect / reconnect the temperature sensor"""


class Room:
    """The simulated physical world that the 'sensors' read from."""
    def __init__(self):
        self.moving = False        # PIR output
        self.blip = False          # one-sample false trigger
        self.ambient = 75.0        # % light from windows
        self.temp = 25.0
        self.dht_ok = True


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(metric, value, unit, status="normal", **extra):
    d = {"schema_version": "1.0", "campus_id": CAMPUS, "module": MODULE, "building_id": BUILDING,
         "zone_id": ZONE, "device_id": DEVICE, "timestamp": now_iso(), "metric": metric,
         "value": value, "unit": unit, "status": status, "source": "simulated"}
    d.update(extra)
    return d


class Device:
    def __init__(self):
        self.room, self.ctl = Room(), ClassroomController()
        self.stop = threading.Event()
        self.connected = False
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{DEVICE}")
        if USER:
            self.client.username_pw_set(USER, PASS)
        # Last will: the BROKER publishes this if we drop without a clean disconnect.
        will = build("device_online", False, "bool", "offline")
        self.client.will_set(f"{BASE}/status", json.dumps(will), qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)   # automatic reconnect backoff
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    # ---- MQTT plumbing -------------------------------------------------------------
    def on_connect(self, c, ud, flags, rc, props):
        self.connected = (rc == 0)
        print(f"[mqtt] connected rc={rc}")
        if rc == 0:
            self.heartbeat()          # announce 'online' (retained) every time we (re)connect

    def on_disconnect(self, c, ud, flags, rc, props):
        self.connected = False
        print(f"[mqtt] disconnected rc={rc} (auto-reconnect running)")

    def pub(self, kind, payload, retain=False):
        # QoS 1 = delivered at least once. paho queues it if we are briefly offline.
        self.client.publish(f"{BASE}/{kind}", json.dumps(payload), qos=1, retain=retain)

    # ---- Message types -------------------------------------------------------------
    def light_pct(self):
        return min(100.0, self.room.ambient + (LED_LIGHT_BOOST if self.ctl.light_on else 0.0))

    def heartbeat(self):
        c = self.ctl
        self.pub("status", build("device_online", True, "bool", "online",
                                 light_on=c.light_on, fan_on=c.fan_on, occupied=c.occupied,
                                 sensor_fault=c.sensor_fault), retain=True)

    def telemetry(self):
        c = self.ctl
        if c.temp is not None:   # a failed sensor publishes NO temperature (never fake a value)
            self.pub("telemetry", build("temperature", round(c.temp, 1), "C",
                                        "warning" if c.high_temp_alert else "normal"))
        self.pub("telemetry", build("light_level", round(self.light_pct(), 1), "pct"))
        self.pub("telemetry", build("occupancy_detected", c.occupied, "bool"))

    def alert(self, kind, severity, state):
        c = self.ctl
        # high_temperature carries the temperature; sensor_failure carries "is the sensor
        # working?" on the contract metric device_online (False while the fault is active).
        value = round(c.temp, 1) if (kind == "high_temperature" and c.temp is not None) else state != "active"
        unit = "C" if kind == "high_temperature" else "bool"
        metric = "temperature" if kind == "high_temperature" else "device_online"
        print(f"[alert] {kind} {severity} {state}")
        self.pub("alerts", build(metric, value, unit, "alert" if state == "active" else "normal",
                                 alert_type=kind, severity=severity, alert_state=state))

    # ---- Main control loop (1 Hz) --------------------------------------------------
    def run(self):
        self.client.connect_async(HOST, PORT, keepalive=KEEPALIVE_S)   # retries if broker is down
        self.client.loop_start()
        t0 = time.monotonic()
        last_tel = last_dht = -999.0
        last_hb = 0.0                 # on_connect already sends the first heartbeat
        prev = (None, None, None)     # (occupied, light_on, fan_on) to detect state changes
        while not self.stop.is_set():
            t = time.monotonic() - t0
            r = self.room
            if t - last_dht >= DHT_PERIOD_S:                      # sensor acquisition
                self.ctl.update_temp(r.temp if r.dht_ok else None)
                last_dht = t
            pir = r.moving or r.blip
            r.blip = False
            events = self.ctl.step(t, pir, self.light_pct())      # local logic
            c = self.ctl
            state = (c.occupied, c.light_on, c.fan_on)
            if state != prev:                                     # immediate event on change
                print(f"[state] occupied={c.occupied} light={c.light_on} fan={c.fan_on} "
                      f"temp={c.temp} ldr={self.light_pct():.0f}%")
                if prev[0] is not None:
                    self.telemetry(); self.heartbeat()
                prev = state
            for ev in events:
                self.alert(*ev)
            if t - last_tel >= TELEMETRY_S:
                self.telemetry(); last_tel = t
            if t - last_hb >= HEARTBEAT_S:
                self.heartbeat(); last_hb = t
            self.stop.wait(1.0)
        try:   # clean shutdown: say goodbye (a clean disconnect does NOT trigger the last will)
            self.client.publish(f"{BASE}/status", json.dumps(build("device_online", False, "bool", "offline")),
                                qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass                      # never connected / already dropped: nothing to announce
        self.client.loop_stop(); self.client.disconnect()

    # ---- Scenario control ------------------------------------------------------------
    def command(self, line):
        p, r = line.split(), self.room
        if not p: return
        cmd = p[0].lower()
        if cmd == "enter": r.moving = True
        elif cmd == "still": r.moving = False
        elif cmd == "leave": r.moving = False
        elif cmd == "blip": r.blip = True
        elif cmd == "dark": r.ambient = 10.0
        elif cmd == "bright": r.ambient = 75.0
        elif cmd == "temp" and len(p) > 1: r.temp = float(p[1])
        elif cmd == "dhtfail": r.dht_ok = False
        elif cmd == "dhtok": r.dht_ok = True
        elif cmd == "status":
            c = self.ctl; print(f"occupied={c.occupied} light={c.light_on} fan={c.fan_on} temp={c.temp} fault={c.sensor_fault}")
        elif cmd in ("quit", "exit"): self.stop.set()
        else: print(HELP)


DEMO = [  # (seconds, command)  - exercises M1-M6 + false trigger + stationary occupant
    (0, "bright"), (4, "enter"), (10, "dark"), (18, "temp 31.5"), (34, "temp 26"),
    (40, "blip"), (46, "dhtfail"), (62, "dhtok"), (68, "still"), (105, "quit"),
]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    d = Device()
    if args.demo:
        def script():
            t0 = time.monotonic()
            for at, cmd in DEMO:
                d.stop.wait(max(0, at - (time.monotonic() - t0)))
                if d.stop.is_set(): return
                print(f"[demo +{at}s] {cmd}"); d.command(cmd)
        threading.Thread(target=script, daemon=True).start()
    else:
        print(HELP)
        def reader():
            for line in sys.stdin:
                try: d.command(line)
                except ValueError: print("bad number")
            # stdin closed (e.g. run as a background job): keep simulating until Ctrl+C / 'quit'
        threading.Thread(target=reader, daemon=True).start()
    try:
        d.run()
    except KeyboardInterrupt:
        d.stop.set()


if __name__ == "__main__":
    main()
