"""Phase 8 automated validation. Runs the common tests T1-T7 and the classroom module tests M1-M6
against the LIVE system (Mosquitto + Node-RED on this laptop) and records expected vs actual.

Prerequisites: Mosquitto and Node-RED running (flows deployed). No simulators running.
Run from the project root:   python tests/run_tests.py
Outputs: tests/results.json  and  docs/test_results.md

Test T5b (broker outage) cannot be automated without stopping the Windows service; it is
recorded as NOT RUN unless you do it by hand (see docs/phase8_validation.md).
All messages sent by this script carry "source":"simulated".
"""
import json, pathlib, subprocess, sys, time, urllib.request as U
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = "http://127.0.0.1:1880/api"
BASE = "christ-smart-campus/v1"
REG = {"ENERGY-A-SIM-01": ("energy", "BLOCK-A", "LAB-101"), "PARK-C-SIM-04": ("parking", "BLOCK-C", "LOT-1"),
       "CLASS-A-ESP32-01": ("classroom", "BLOCK-A", "ROOM-204")}
RES = []


def rec(tid, name, expected, actual, ok):
    RES.append({"id": tid, "name": name, "expected": expected, "actual": actual, "result": "PASS" if ok else ("NOT RUN" if ok is None else "FAIL")})
    print(f"[{RES[-1]['result']:7}] {tid:4} {name} -> {actual}", flush=True)


def api(path, role="viewer", data=None, raw=False):
    r = U.Request(B + path, headers={"X-Role": role, "Content-Type": "application/json"},
                  data=json.dumps(data).encode() if data is not None else None)
    try:
        resp = U.urlopen(r, timeout=8)
    except U.HTTPError as e:
        return e.code, None
    body = resp.read()
    return resp.status, (body if raw else json.loads(body))


def wait_for(fn, timeout, step=0.4):
    t = time.time()
    while time.time() - t < timeout:
        try:
            v = fn()
            if v:
                return v, time.time() - t
        except Exception:
            pass
        time.sleep(step)
    return None, time.time() - t


def dev(did):
    return next(d for d in api("/overview")[1]["devices"] if d["device_id"] == did)
def metric(did, m):
    return next((x for x in dev(did)["metrics"] if x["metric"] == m), None)
def alerts():
    return api("/alerts?state=all")[1]
def rejects():
    return api("/rejects")[1]
def max_alert_id():
    return max([a["id"] for a in alerts()] or [0])
def max_reject_id():
    return max([r["id"] for r in rejects()] or [0])


pc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test-harness")
pc.connect("127.0.0.1", 1883); pc.loop_start()


def msg(did, **kw):
    m, b, z = REG[did]
    d = {"schema_version": "1.0", "campus_id": "CHRIST-DEMO", "module": m, "building_id": b, "zone_id": z, "device_id": did,
         "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "metric": "power_w", "value": 321.5,
         "unit": "W", "status": "normal", "source": "simulated"}
    d.update(kw)
    return d


def send(did, kind, payload, topic_dev=None, module=None):
    m, b, _ = REG.get(topic_dev or did, REG[did])
    topic = f"{BASE}/{module or m}/{b}/{topic_dev or did}/{kind}"
    pc.publish(topic, payload if isinstance(payload, str) else json.dumps(payload), qos=1).wait_for_publish()


def reject_reason(contains, since):
    return wait_for(lambda: next((r["reason"] for r in rejects() if r["id"] > since and contains in r["reason"]), None), 6)


# =================================================================== common tests
def common():
    orig = api("/config")[1]["offline_s"]
    # T1 valid feed accepted, stored, visible, with latency
    t0 = time.time(); send("ENERGY-A-SIM-01", "telemetry", msg("ENERGY-A-SIM-01", value=321.5))
    v, dt = wait_for(lambda: (metric("ENERGY-A-SIM-01", "power_w") or {}).get("value") == 321.5, 8, 0.05)
    rec("T1", "Valid feed accepted and shown", "Reading visible via API within 5 s", f"visible after {dt:.2f} s", bool(v) and dt < 5)

    # T2 missing field rejected (+ other FR-02 flags)
    cases = [("T2", "Missing required field rejected", lambda: send("ENERGY-A-SIM-01", "telemetry", {k: v for k, v in msg("ENERGY-A-SIM-01").items() if k != "device_id"}), "missing_field:device_id"),
             ("T2b", "Malformed JSON flagged", lambda: send("ENERGY-A-SIM-01", "telemetry", "{not json"), "malformed_json"),
             ("T2c", "Invalid timestamp flagged", lambda: send("ENERGY-A-SIM-01", "telemetry", msg("ENERGY-A-SIM-01", timestamp="yesterday")), "invalid_timestamp"),
             ("T2d", "Out-of-range value flagged", lambda: send("ENERGY-A-SIM-01", "telemetry", msg("ENERGY-A-SIM-01", value=99999)), "out_of_range:power_w"),
             ("T3", "Unknown device flagged", lambda: send("ENERGY-A-SIM-01", "telemetry", msg("ENERGY-A-SIM-01", device_id="GHOST-99"), topic_dev="GHOST-99"), "unknown_device:GHOST-99"),
             ("T3b", "Unknown module flagged", lambda: send("ENERGY-A-SIM-01", "telemetry", msg("ENERGY-A-SIM-01", module="cafeteria"), module="cafeteria"), "unknown_module:cafeteria")]
    before = metric("ENERGY-A-SIM-01", "power_w")["rx"]
    for tid, name, action, reason in cases:
        since = max_reject_id(); action()
        got, dt = reject_reason(reason, since)
        rec(tid, name, f"Stored in rejects with reason {reason}", f"reason={got}", got == reason)
    unchanged = metric("ENERGY-A-SIM-01", "power_w")["rx"] == before
    rec("T2e", "Rejected messages never reach readings", "Latest value untouched by the 6 bad messages", "latest unchanged" if unchanged else "latest CHANGED", unchanged)

    # T4 stale: device sends data, then goes silent WITHOUT a last-will (clean disconnect semantics)
    api("/config", "administrator", {"offline_s": 10})
    aid = max_alert_id(); send("PARK-C-SIM-04", "telemetry", msg("PARK-C-SIM-04", metric="slot_occupied", value=True, unit="bool"))
    on, _ = wait_for(lambda: dev("PARK-C-SIM-04")["health"] == "online", 6)
    st, dt = wait_for(lambda: dev("PARK-C-SIM-04")["health"] == "stale", 30)
    al, dt2 = wait_for(lambda: next((a for a in alerts() if a["id"] > aid and a["device"] == "PARK-C-SIM-04" and a["alert_type"] == "device_offline" and a["state"] != "cleared"), None), 25)
    rec("T4", "Device silent > timeout becomes stale/offline + alert", "health=stale after offline_s=10 s, device_offline alert raised",
        f"online first={bool(on)}; stale after {dt:.1f} s; alert={'raised' if al else 'MISSING'}", bool(on) and bool(st) and bool(al))
    send("PARK-C-SIM-04", "telemetry", msg("PARK-C-SIM-04", metric="slot_occupied", value=False, unit="bool"))
    back, dt = wait_for(lambda: dev("PARK-C-SIM-04")["health"] == "online" and not any(a["device"] == "PARK-C-SIM-04" and a["alert_type"] == "device_offline" and a["state"] != "cleared" for a in alerts()), 25)
    rec("T4b", "Data resumes -> back online, offline alert clears", "health=online and alert cleared (<=10 s timer)", f"recovered after {dt:.1f} s", bool(back))
    api("/config", "administrator", {"offline_s": orig})

    # T6 alert correct: active, de-duplicated, acknowledged, cleared
    aid = max_alert_id()
    A = dict(metric="power_w", value=1500.0, unit="W", status="alert", alert_type="high_power", severity="warning", alert_state="active")
    send("ENERGY-A-SIM-01", "alerts", msg("ENERGY-A-SIM-01", **A)); send("ENERGY-A-SIM-01", "alerts", msg("ENERGY-A-SIM-01", **A))
    time.sleep(1.5)
    mine = [a for a in alerts() if a["id"] > aid and a["device"] == "ENERGY-A-SIM-01" and a["alert_type"] == "high_power"]
    ok1 = len(mine) == 1 and mine[0]["state"] == "active" and mine[0]["severity"] == "warning" and mine[0]["value"] == 1500.0
    code, _ = api(f"/alerts/{mine[0]['id']}/ack", "operator", {}) if mine else (0, None)
    st = next((a["state"] for a in alerts() if mine and a["id"] == mine[0]["id"]), None)
    send("ENERGY-A-SIM-01", "alerts", msg("ENERGY-A-SIM-01", **{**A, "alert_state": "cleared", "status": "normal"})); time.sleep(1.5)
    st2 = next((a["state"] for a in alerts() if mine and a["id"] == mine[0]["id"]), None)
    rec("T6", "Alert correct: severity/value, de-dup, ack, clear", "1 row (2 identical events), active -> acknowledged -> cleared",
        f"rows={len(mine)}, first={mine[0]['state'] if mine else None}, ack http={code}, after ack={st}, after clear={st2}",
        ok1 and code == 200 and st == "acknowledged" and st2 == "cleared")

    # T7 units + last update shown
    m = metric("ENERGY-A-SIM-01", "power_w"); page = U.urlopen("http://127.0.0.1:1880/campus", timeout=8).read().decode()
    ok = m and m["unit"] == "W" and m["rx"] and "ago(" in page and "SIMULATED" in page
    rec("T7", "Units and last-updated time shown", "metric has unit + received time; page renders 'x s ago' and SIMULATED label", f"unit={m and m['unit']}, rx={m and m['rx']}, page labels present={bool('ago(' in page and 'SIMULATED' in page)}", bool(ok))

    # Roles, export, filters, deep checks
    aid2 = max_alert_id(); send("ENERGY-A-SIM-01", "alerts", msg("ENERGY-A-SIM-01", **A)); time.sleep(1.5)
    new = next(a for a in alerts() if a["id"] > aid2)
    c_v, _ = api(f"/alerts/{new['id']}/ack", "viewer", {}); c_o, _ = api(f"/alerts/{new['id']}/ack", "operator", {})
    rec("R1", "Role check on acknowledge", "viewer 403, operator 200", f"viewer {c_v}, operator {c_o}", c_v == 403 and c_o == 200)
    send("ENERGY-A-SIM-01", "alerts", msg("ENERGY-A-SIM-01", **{**A, "alert_state": "cleared"}))
    c_op, _ = api("/export.csv?module=energy", "operator", raw=True); c_ad, body = api("/export.csv?module=energy", "administrator", raw=True)
    rows = body.decode().strip().splitlines() if body else []
    rec("R2", "CSV export (administrator only, filtered)", "operator 403; admin 200, header + data rows, only energy", f"operator {c_op}, admin {c_ad}, {len(rows)} lines, header ok={rows[:1] == ['ts,rx,module,building,zone,device,metric,value,unit,status,source']}, all energy={all(',energy,' in r for r in rows[1:])}",
        c_op == 403 and c_ad == 200 and len(rows) > 1 and all(",energy," in r for r in rows[1:]))
    f1 = [d["module"] for d in api("/overview?module=energy")[1]["devices"]]; f2 = {d["building"] for d in api("/overview?building=BLOCK-B")[1]["devices"]}
    f3 = [d["zone"] for d in api("/overview?building=BLOCK-C&zone=LOT-1")[1]["devices"]]
    rec("F1", "Filters by module / building / zone", "only matching devices returned", f"module=energy->{set(f1)}, BLOCK-B->{f2}, LOT-1->{set(f3)} x{len(f3)}",
        set(f1) == {"energy"} and f2 == {"BLOCK-B"} and set(f3) == {"LOT-1"})
    inj = api("/overview?module=x%27%20OR%201%3D1")[1]
    rec("S1", "Filter input is not injectable", "treated as 'no filter', no error, 9 registered devices", f"{len(inj['devices'])} devices returned", len(inj["devices"]) == 9)


# =================================================================== classroom module tests (live, via simulator)
def classroom():
    proc = subprocess.Popen([sys.executable, "classroom_sim.py"], cwd=ROOT / "simulator", stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    cmd = lambda c: (proc.stdin.write(c + "\n"), proc.stdin.flush())
    cls = lambda: dev("CLASS-A-ESP32-01")
    ex = lambda k: cls()["extras"].get(k)
    try:
        wait_for(lambda: cls()["health"] == "online", 10)
        cmd("bright"); cmd("temp 25"); cmd("enter"); time.sleep(5)
        ok_a = ex("occupied") is True and ex("light_on") is False and ex("fan_on") is False
        cmd("dark"); v, dt = wait_for(lambda: ex("light_on") is True, 8)
        rec("M1", "Normal: occupied + dark -> light ON, fan OFF", "occupied, daylight keeps light OFF; darkness turns light ON", f"bright: occ={ex('occupied')} light={False if ok_a else '?'}; dark -> light ON after {dt:.1f} s; fan={ex('fan_on')}", ok_a and bool(v) and ex("fan_on") is False)

        aid = max_alert_id(); cmd("temp 31.5")
        v, dt = wait_for(lambda: ex("fan_on") is True, 10)
        al = next((a for a in alerts() if a["id"] > aid and a["alert_type"] == "high_temperature" and a["state"] != "cleared"), None)
        rec("M2", "Threshold: 31.5 C occupied -> fan ON + alert", "fan ON, high_temperature alert active", f"fan ON after {dt:.1f} s; alert={'raised' if al else 'MISSING'}", bool(v) and bool(al))

        steps = [("30.0", True, "stays ON (inside 27-30 band)"), ("27.0", True, "stays ON (27.0 is not < 27)"), ("26.9", False, "turns OFF"), ("30.0", False, "stays OFF (30.0 is not > 30)"), ("30.1", True, "turns ON")]
        out, ok = [], True
        for t, want, why in steps:
            cmd(f"temp {t}"); time.sleep(5); got = ex("fan_on"); ok &= (got is want); out.append(f"{t}C->{'ON' if got else 'OFF'}")
        rec("M3", "Boundary: hysteresis at 30.0 / 30.1 / 27.0 / 26.9 C", "fan flips only above 30 C and below 27 C", ", ".join(out), ok)

        aid = max_alert_id(); cmd("dhtfail")
        v, dt = wait_for(lambda: ex("sensor_fault") is True and ex("fan_on") is False, 15)
        al = next((a for a in alerts() if a["id"] > aid and a["alert_type"] == "sensor_failure" and a["state"] == "active"), None)
        rec("M4", "Sensor disconnect: 3 bad reads -> fail-safe", "fan forced OFF, sensor_fault true, sensor_failure alert", f"fail-safe after {dt:.1f} s; fan={ex('fan_on')}; alert={'raised' if al else 'MISSING'}", bool(v) and bool(al))

        cmd("dhtok"); cmd("temp 25")
        v, dt = wait_for(lambda: ex("sensor_fault") is False and next((a for a in alerts() if a["id"] > aid and a["alert_type"] == "sensor_failure"), {}).get("state") == "cleared", 15)
        rec("M5", "Recovery: sensor returns -> alert clears, logic resumes", "sensor_fault false, alert cleared", f"recovered after {dt:.1f} s", bool(v))

        cmd("still"); time.sleep(20); mid = ex("occupied")
        v, dt = wait_for(lambda: ex("occupied") is False and ex("light_on") is False, 25)
        rec("M6", "Vacancy: no motion 30 s -> light OFF (stationary occupant limitation)", "still occupied at +20 s; vacant and light OFF by ~30 s", f"at +20 s occupied={mid}; vacant+light OFF after a further {dt:.1f} s", mid is True and bool(v))

        cmd("blip"); time.sleep(5)
        rec("M7", "False trigger: single PIR pulse ignored", "room stays vacant, light stays OFF", f"occupied={ex('occupied')}, light_on={ex('light_on')}", ex("occupied") is False and ex("light_on") is False)
    finally:
        proc.kill()
    # device-side reconnect
    v, dt = wait_for(lambda: cls()["health"] == "offline", 8)
    aid = max_alert_id()
    off, _ = wait_for(lambda: next((a for a in alerts() if a["device"] == "CLASS-A-ESP32-01" and a["alert_type"] == "device_offline" and a["state"] != "cleared"), None), 15)
    proc = subprocess.Popen([sys.executable, "classroom_sim.py"], cwd=ROOT / "simulator", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        on, dt2 = wait_for(lambda: cls()["health"] == "online", 15)
        clr, dt3 = wait_for(lambda: not any(a["device"] == "CLASS-A-ESP32-01" and a["alert_type"] == "device_offline" and a["state"] != "cleared" for a in alerts()), 20)
    finally:
        proc.kill()
    rec("T5a", "Device killed (last will) then restarted: resumes", "offline + alert after kill; online again and alert cleared after restart",
        f"offline={bool(v)}, alert={'raised' if off else 'MISSING'}, back online after {dt2:.1f} s, alert cleared after {dt3:.1f} s", bool(v) and bool(off) and bool(on) and bool(clr))


def main():
    t0 = datetime.now()
    logic = subprocess.run([sys.executable, "test_logic.py"], cwd=ROOT / "simulator", capture_output=True, text=True)
    last = logic.stdout.strip().splitlines()[-1] if logic.stdout.strip() else logic.stderr[-200:]
    rec("U1", "Logic unit tests (fake clock)", "all tests pass", last, logic.returncode == 0)
    common()
    classroom()
    rec("T5b", "Broker outage: stop/start Mosquitto, all parties reconnect", "Node-RED + device resume without restart", "NOT RUN: needs admin to stop the Mosquitto service; do it by hand (docs/phase8_validation.md)", None)
    api("/config", "administrator", {"offline_s": 120})
    pc.loop_stop()
    summary = {"started": t0.isoformat(timespec="seconds"), "finished": datetime.now().isoformat(timespec="seconds"),
               "passed": sum(r["result"] == "PASS" for r in RES), "failed": sum(r["result"] == "FAIL" for r in RES),
               "not_run": sum(r["result"] == "NOT RUN" for r in RES), "results": RES}
    (ROOT / "tests" / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    md = ["# Test results (automated run)\n", f"Run {summary['started']} to {summary['finished']} against the live system (Mosquitto + Node-RED, simulated devices).\n",
          f"**{summary['passed']} passed, {summary['failed']} failed, {summary['not_run']} not run.**\n", "| ID | Test | Expected | Actual | Result |", "|---|---|---|---|---|"]
    md += [f"| {r['id']} | {r['name']} | {r['expected']} | {r['actual']} | **{r['result']}** |".replace("\n", " ") for r in RES]
    (ROOT / "docs" / "test_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\n{summary['passed']} passed, {summary['failed']} failed, {summary['not_run']} not run")


if __name__ == "__main__":
    main()
