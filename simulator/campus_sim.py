"""Phase 7 (OPTIONAL): labelled simulator for the five modules that are NOT my real module.

EVERY message carries "source":"simulated". These are NOT real sensors; they exist only so the
campus overview looks complete. Nothing here touches mains, water, gas or smoke.

Devices (must match REGISTRY in platform/build_flow.py):
  parking  PARK-C-SIM-01..04  one ultrasonic-style sensor per numbered slot (slot_occupied)
  energy   ENERGY-A-SIM-01    power_w, energy_kwh      (simulated low-voltage demo circuit)
  water    WATER-B-SIM-01     tank_level_pct, water_flow_lpm
  waste    WASTE-B-SIM-01     bin_fill_pct
  safety   SAFE-B-SIM-01      temperature, smoke_detected (DEMO input, NOT a certified alarm)

Run:  python campus_sim.py --demo        scripted ~110 s run that trips every alert, then exits
      python campus_sim.py               runs until Ctrl+C; type commands (see HELP)
--speed N compresses slow physical processes (default 10) so alerts appear within minutes.
"""
import argparse, json, os, random, sys, threading, time
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

HOST, PORT = os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883"))
USER, PASS = os.getenv("MQTT_USER"), os.getenv("MQTT_PASS")
CAMPUS, BASE = "CHRIST-DEMO", "christ-smart-campus/v1"
TELEMETRY_S, HEARTBEAT_S, KEEPALIVE_S = 10, 45, 30

# Thresholds (configurable per the module rules)
WATER_LOW_PCT, WATER_OK_PCT = 20.0, 30.0       # alert below 20 %, clear above 30 % (hysteresis)
WASTE_FULL_PCT, WASTE_OK_PCT = 80.0, 60.0      # collection_required above 80 %
POWER_HIGH_W, POWER_OK_W = 1200.0, 1000.0      # abnormal-load alert (simulated circuit)
PARK_THRESHOLD_CM = 40.0                       # slot is occupied when distance < 40 cm

HELP = """commands: smoke on|off | spike | fill | empty | park <1-4> on|off | status | quit"""


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Dev:
    """One simulated device = one MQTT client with its own last will, heartbeat and alerts."""
    module = building = zone = ""

    def __init__(self, device_id):
        self.id = device_id
        self.base = f"{BASE}/{self.module}/{self.building}/{self.id}"
        self.active = {}                 # alert_type -> currently raised?
        self.changed = False             # state change -> publish immediately
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{self.id}")
        if USER:
            self.c.username_pw_set(USER, PASS)
        self.c.will_set(f"{self.base}/status", json.dumps(self.msg("device_online", False, "bool", "offline")),
                        qos=1, retain=True)                       # broker announces us dead if we vanish
        self.c.reconnect_delay_set(1, 30)
        self.c.on_connect = lambda c, u, f, rc, p: self.heartbeat() if rc == 0 else None
        self.last_tel = -1e9                     # first tick publishes readings at once
        self.last_hb = time.monotonic()    # on_connect sends the first heartbeat

    def msg(self, metric, value, unit, status="normal", **extra):
        d = {"schema_version": "1.0", "campus_id": CAMPUS, "module": self.module, "building_id": self.building,
             "zone_id": self.zone, "device_id": self.id, "timestamp": now_iso(), "metric": metric, "value": value,
             "unit": unit, "status": status, "source": "simulated"}
        d.update(extra)
        return d

    def pub(self, kind, payload, retain=False):
        self.c.publish(f"{self.base}/{kind}", json.dumps(payload), qos=1, retain=retain)

    def heartbeat(self):
        self.pub("status", self.msg("device_online", True, "bool", "online", **self.extras()), retain=True)

    def telemetry(self):
        for metric, value, unit, status in self.metrics():
            self.pub("telemetry", self.msg(metric, value, unit, status))

    def edge(self, kind, cond, severity, metric, value, unit):
        """Edge-triggered alert: publish only when the condition flips."""
        if cond != self.active.get(kind, False):
            self.active[kind] = cond
            state = "active" if cond else "cleared"
            print(f"[{self.id}] alert {kind} {severity} {state}")
            self.pub("alerts", self.msg(metric, value, unit, "alert" if cond else "normal",
                                        alert_type=kind, severity=severity, alert_state=state))
            self.changed = True

    def start(self):
        self.c.connect_async(HOST, PORT, keepalive=KEEPALIVE_S)
        self.c.loop_start()

    def tick(self, dt):
        self.step(dt)
        t = time.monotonic()
        if self.changed or t - self.last_tel >= TELEMETRY_S:
            self.telemetry(); self.last_tel = t
        if self.changed or t - self.last_hb >= HEARTBEAT_S:
            self.heartbeat(); self.last_hb = t
        self.changed = False

    def stop(self):
        try:
            self.c.publish(f"{self.base}/status", json.dumps(self.msg("device_online", False, "bool", "offline")),
                           qos=1, retain=True).wait_for_publish(2)
        except (RuntimeError, ValueError):
            pass
        self.c.loop_stop(); self.c.disconnect()

    def extras(self): return {}


class Parking(Dev):
    module, building, zone = "parking", "BLOCK-C", "LOT-1"

    def __init__(self, n, speed):
        self.slot = n; self.speed = speed
        self.occupied = random.random() < 0.4
        self.dist = 20.0 if self.occupied else 130.0
        super().__init__(f"PARK-C-SIM-0{n}")

    def set(self, occ): self.occupied = occ     # manual override for tests

    def step(self, dt):
        if random.random() < 0.01 * self.speed * dt:           # a car arrives or leaves
            self.occupied = not self.occupied
        target = random.uniform(12, 30) if self.occupied else random.uniform(110, 150)
        self.dist = round(target, 1)                           # simulated ultrasonic reading (cm)
        occ = self.dist < PARK_THRESHOLD_CM                    # calibrated threshold, same rule as real firmware
        if occ != self.active.get("occ"):
            self.active["occ"] = occ; self.changed = True

    def metrics(self): return [("slot_occupied", bool(self.active.get("occ", False)), "bool", "normal")]
    def extras(self): return {"slot": self.slot, "distance_cm": self.dist}


class Energy(Dev):
    module, building, zone = "energy", "BLOCK-A", "LAB-101"

    def __init__(self, speed):
        self.p, self.kwh, self.spike_until, self.speed = 150.0, 12.5, 0.0, speed
        super().__init__("ENERGY-A-SIM-01")

    def spike(self): self.spike_until = time.monotonic() + 25      # abnormal-load test

    def step(self, dt):
        base = 160 + 90 * (int(time.monotonic() / 20) % 3)         # stepped "lab load" 160/250/340 W
        self.p = round(base + random.uniform(-8, 8) + (1300 if time.monotonic() < self.spike_until else 0), 1)
        self.kwh += self.p * dt * self.speed / 3.6e6               # W*s -> kWh (time-compressed)
        self.edge("high_power", self.p > POWER_HIGH_W if not self.active.get("high_power") else self.p > POWER_OK_W,
                  "warning", "power_w", self.p, "W")

    def metrics(self):
        st = "warning" if self.active.get("high_power") else "normal"
        return [("power_w", self.p, "W", st), ("energy_kwh", round(self.kwh, 3), "kWh", "normal")]


class Water(Dev):
    module, building, zone = "water", "BLOCK-B", "TANK-1"

    def __init__(self, speed, start):
        self.lvl, self.flow, self.speed = start, 0.0, speed
        super().__init__("WATER-B-SIM-01")

    def fill(self): self.lvl = 90.0

    def step(self, dt):
        self.flow = round(random.uniform(6, 14), 1) if random.random() < 0.6 else 0.0   # outlet demand (L/min)
        self.lvl = max(0.0, self.lvl - self.flow * 0.0025 * self.speed * dt)
        if self.lvl < 8: self.lvl = 85.0                           # simulated demo pump refill
        self.lvl = round(self.lvl, 1)
        low = self.lvl < WATER_LOW_PCT if not self.active.get("low_tank_level") else self.lvl < WATER_OK_PCT
        self.edge("low_tank_level", low, "warning", "tank_level_pct", self.lvl, "pct")

    def metrics(self):
        st = "warning" if self.active.get("low_tank_level") else "normal"
        return [("tank_level_pct", self.lvl, "pct", st), ("water_flow_lpm", self.flow, "lpm", "normal")]


class Waste(Dev):
    module, building, zone = "waste", "BLOCK-B", "BIN-01"

    def __init__(self, speed, start):
        self.fillp, self.speed = start, speed
        super().__init__("WASTE-B-SIM-01")

    def empty(self): self.fillp = 4.0

    def step(self, dt):
        self.fillp = min(100.0, self.fillp + 0.01 * self.speed * dt)
        self.fillp = round(self.fillp, 1)
        need = self.fillp > WASTE_FULL_PCT if not self.active.get("collection_required") else self.fillp > WASTE_OK_PCT
        self.edge("collection_required", need, "info", "bin_fill_pct", self.fillp, "pct")

    def metrics(self):
        st = "warning" if self.active.get("collection_required") else "normal"
        return [("bin_fill_pct", self.fillp, "pct", st)]


class Safety(Dev):
    module, building, zone = "safety", "BLOCK-B", "LAB-2"

    def __init__(self):
        self.smoke, self.temp = False, 24.0
        super().__init__("SAFE-B-SIM-01")

    def set_smoke(self, on): self.smoke = on      # DEMO input only: a push-button, never real smoke

    def step(self, dt):
        self.temp = round(24.0 + random.uniform(-0.4, 0.4) + (3.0 if self.smoke else 0), 1)
        self.edge("smoke_alarm_demo", self.smoke, "critical", "smoke_detected", self.smoke, "bool")

    def metrics(self):
        return [("temperature", self.temp, "C", "normal"),
                ("smoke_detected", self.smoke, "bool", "alert" if self.smoke else "normal")]
    def extras(self): return {"buzzer": self.smoke, "demo_input": True}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true"); ap.add_argument("--speed", type=float, default=10.0)
    a = ap.parse_args()
    water_start, waste_start = (26.0, 74.0) if a.demo else (70.0, 20.0)   # demo starts near the thresholds
    parks = [Parking(n, a.speed) for n in (1, 2, 3, 4)]
    energy, water, waste, safety = Energy(a.speed), Water(a.speed, water_start), Waste(a.speed, waste_start), Safety()
    devs = parks + [energy, water, waste, safety]
    stop = threading.Event()

    def command(line):
        p = line.split()
        if not p: return
        c = p[0].lower()
        if c == "smoke" and len(p) > 1: safety.set_smoke(p[1] == "on")
        elif c == "spike": energy.spike()
        elif c == "fill": water.fill()
        elif c == "empty": waste.empty()
        elif c == "park" and len(p) > 2 and p[1] in "1234": parks[int(p[1]) - 1].set(p[2] == "on")
        elif c == "status":
            print({d.id: d.metrics() for d in devs})
        elif c in ("quit", "exit"): stop.set()
        else: print(HELP)

    if a.demo:
        timeline = [(12, "spike"), (40, "smoke on"), (62, "smoke off"), (75, "empty"), (80, "fill"), (110, "quit")]
        def script():
            t0 = time.monotonic()
            for at, cmd in timeline:
                stop.wait(max(0, at - (time.monotonic() - t0)))
                if stop.is_set(): return
                print(f"[demo +{at}s] {cmd}"); command(cmd)
        threading.Thread(target=script, daemon=True).start()
    else:
        print(HELP)
        def reader():
            for line in sys.stdin: command(line)
        threading.Thread(target=reader, daemon=True).start()

    for d in devs: d.start()
    last = time.monotonic()
    try:
        while not stop.is_set():
            stop.wait(1.0)
            t = time.monotonic(); dt, last = t - last, t
            for d in devs: d.tick(dt)
    except KeyboardInterrupt:
        pass
    for d in devs: d.stop()
    print("stopped")


if __name__ == "__main__":
    main()
