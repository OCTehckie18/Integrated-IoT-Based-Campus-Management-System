"""Generates ../flows.json (the Node-RED flow) so function code needs no JSON escaping.

Run from anywhere:  python platform/build_flow.py     (STOP Node-RED first, then start it again)

Pipeline:  MQTT in -> validate+route -> SQLite (devices, latest, readings, alerts, rejects)
HTTP API:  /api/overview /api/alerts /api/alerts/:id/ack /api/device/:id/readings
           /api/export.csv /api/rejects /api/config      Page: /campus  (platform/dashboard.html)
Roles are SIMULATED: the page sends X-Role (viewer|operator|administrator). This is NOT
authentication; it only demonstrates role-based behaviour on an isolated lab network.
"""
import json
import pathlib

# Single source of truth for known devices: device_id -> [module, building, zone]
# Only CLASS-A-ESP32-01 is the real (simulated-hardware) module; the rest are for Phase 7's
# clearly labelled simulator and show as "no data" until it runs.
REGISTRY = {
    "CLASS-A-ESP32-01": ["classroom", "BLOCK-A", "ROOM-204"],
    # Parking: one sensor (= one device) per numbered slot, as in the module spec
    "PARK-C-SIM-01": ["parking", "BLOCK-C", "LOT-1"],
    "PARK-C-SIM-02": ["parking", "BLOCK-C", "LOT-1"],
    "PARK-C-SIM-03": ["parking", "BLOCK-C", "LOT-1"],
    "PARK-C-SIM-04": ["parking", "BLOCK-C", "LOT-1"],
    "ENERGY-A-SIM-01": ["energy", "BLOCK-A", "LAB-101"],
    "WATER-B-SIM-01": ["water", "BLOCK-B", "TANK-1"],
    "WASTE-B-SIM-01": ["waste", "BLOCK-B", "BIN-01"],
    "SAFE-B-SIM-01": ["safety", "BLOCK-B", "LAB-2"],
}

# ----------------------------------------------------------------------------------------
# Ingest: validate + route. Outputs: 0 reject, 1 device upsert, 2 reading, 3 latest,
# 4 alert insert, 5 alert clear. Each output carries EXACTLY the params its SQL uses
# (node-sqlite3 errors on unused named params).
# ----------------------------------------------------------------------------------------
VALIDATE = r'''
// FR-02 validation + routing for telemetry / status / alerts.
const REQ = ["schema_version","campus_id","module","building_id","zone_id",
             "device_id","timestamp","metric","value","unit","status"];
const MODULES = ["classroom","parking","energy","water","waste","safety"];
const REG = __REG__;                       // known devices: id -> [module, building, zone]
const KINDS = ["telemetry","status","alerts"];
const SEV = ["info","warning","critical"];
const RANGE = {temperature:[-10,60], light_level:[0,100], occupancy_count:[0,500],
               co2_ppm:[250,5000], power_w:[0,5000], energy_kwh:[0,100000],
               tank_level_pct:[0,100], bin_fill_pct:[0,100], water_flow_lpm:[0,200]};
const BOOLS = ["occupancy_detected","slot_occupied","smoke_detected","device_online"];

const raw = (msg.payload === undefined || msg.payload === null) ? "" : msg.payload.toString();
function reject(reason) {
    return [{params: {$ts: new Date().toISOString(), $topic: msg.topic, $reason: reason,
                      $raw: raw.substring(0, 500)}}, null, null, null, null, null];
}
const t = (msg.topic || "").split("/");   // [campus, v1, module, building, device, kind]
if (t.length !== 6 || t[0] !== "christ-smart-campus" || t[1] !== "v1") return reject("bad_topic");
const kind = t[5];
if (!KINDS.includes(kind)) return reject("unknown_topic_kind:" + kind);
let p;
try { p = JSON.parse(raw); } catch (e) { return reject("malformed_json"); }
if (typeof p !== "object" || p === null || Array.isArray(p)) return reject("malformed_json");
for (const k of REQ) if (p[k] === undefined || p[k] === null || p[k] === "") return reject("missing_field:" + k);
if (!MODULES.includes(p.module)) return reject("unknown_module:" + p.module);
const reg = REG[p.device_id];
if (!reg) return reject("unknown_device:" + p.device_id);
if (reg[0] !== p.module || reg[1] !== p.building_id || reg[2] !== p.zone_id) return reject("registry_mismatch");
if (t[2] !== p.module || t[3] !== p.building_id || t[4] !== p.device_id) return reject("topic_payload_mismatch");
if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(p.timestamp) ||
    isNaN(Date.parse(p.timestamp))) return reject("invalid_timestamp");
if (Date.parse(p.timestamp) > Date.now() + 300000) return reject("timestamp_in_future");
if (BOOLS.includes(p.metric)) {
    if (typeof p.value !== "boolean") return reject("wrong_type:" + p.metric);
} else if (RANGE[p.metric]) {
    if (typeof p.value !== "number" || !isFinite(p.value)) return reject("wrong_type:" + p.metric);
    if (p.value < RANGE[p.metric][0] || p.value > RANGE[p.metric][1]) return reject("out_of_range:" + p.metric);
} else return reject("unknown_metric:" + p.metric);
if (typeof p.unit !== "string" || typeof p.status !== "string") return reject("wrong_type:unit_or_status");

const isStatus = kind === "status";
if (isStatus && (p.metric !== "device_online" || typeof p.value !== "boolean")) return reject("status_metric_invalid");
if (kind === "alerts") {
    if (typeof p.alert_type !== "string" || !/^[a-z_]{1,40}$/.test(p.alert_type) ||
        !SEV.includes(p.severity) || !["active","cleared"].includes(p.alert_state))
        return reject("invalid_alert_fields");
}

const rx = new Date().toISOString();
const num = typeof p.value === "boolean" ? (p.value ? 1 : 0) : p.value;
const source = (typeof p.source === "string" ? p.source : "unknown").substring(0, 20);

// Extra boolean/numeric fields on STATUS messages (light_on, fan_on...) are kept for the device page.
let extras = {};
if (isStatus) {
    let n = 0;
    for (const k of Object.keys(p)) {
        if (REQ.includes(k) || k === "source" || n >= 10 || !/^[a-z][a-z0-9_]{0,23}$/.test(k)) continue;
        if (typeof p[k] === "boolean" || (typeof p[k] === "number" && isFinite(p[k]))) { extras[k] = p[k]; n++; }
    }
}
const dev = {params: {$id: p.device_id, $module: p.module, $building: p.building_id, $zone: p.zone_id,
    $rx: rx, $online: isStatus ? (p.value ? 1 : 0) : 1, $is_status: isStatus ? 1 : 0,
    $extras: JSON.stringify(extras), $source: source}};
let rd = null, lt = null, ai = null, ac = null;
if (kind === "telemetry") {
    rd = {params: {$ts: p.timestamp, $rx: rx, $module: p.module, $building: p.building_id, $zone: p.zone_id,
        $device: p.device_id, $metric: p.metric, $value: num, $unit: p.unit, $status: p.status, $source: source}};
    lt = {params: {$device: p.device_id, $metric: p.metric, $value: num, $unit: p.unit, $status: p.status,
        $ts: p.timestamp, $rx: rx, $source: source}};
}
if (kind === "alerts") {
    if (p.alert_state === "active") {
        ai = {params: {$ts: p.timestamp, $rx: rx, $device: p.device_id, $module: p.module, $building: p.building_id,
            $zone: p.zone_id, $type: p.alert_type, $severity: p.severity, $value: num, $unit: p.unit, $source: source}};
    } else {
        ac = {params: {$rx: rx, $device: p.device_id, $type: p.alert_type}};
    }
}
return [null, dev, rd, lt, ai, ac];
'''.replace("__REG__", json.dumps(REGISTRY))

# ----------------------------------------------------------------------------------------
# SQL
# ----------------------------------------------------------------------------------------
CREATES = [
    ("readings", "CREATE TABLE IF NOT EXISTS readings (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, rx TEXT, module TEXT, "
                 "building TEXT, zone TEXT, device TEXT, metric TEXT, value REAL, unit TEXT, status TEXT, source TEXT);"),
    ("rejects", "CREATE TABLE IF NOT EXISTS rejects (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, topic TEXT, reason TEXT, raw TEXT);"),
    ("devices", "CREATE TABLE IF NOT EXISTS devices (device_id TEXT PRIMARY KEY, module TEXT, building TEXT, zone TEXT, "
                "last_seen TEXT, reported_online INTEGER DEFAULT 0, extras TEXT DEFAULT '{}', source TEXT);"),
    ("latest", "CREATE TABLE IF NOT EXISTS latest (device TEXT, metric TEXT, value REAL, unit TEXT, status TEXT, ts TEXT, "
               "rx TEXT, source TEXT, PRIMARY KEY (device, metric));"),
    ("alerts", "CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, rx TEXT, device TEXT, module TEXT, "
               "building TEXT, zone TEXT, alert_type TEXT, severity TEXT, value REAL, unit TEXT, cleared_ts TEXT, "
               "ack_by TEXT, ack_ts TEXT, source TEXT);"),
    ("index", "CREATE INDEX IF NOT EXISTS idx_readings_dev ON readings (device, id);"),
]
SEED_SQL = ("INSERT OR IGNORE INTO devices (device_id,module,building,zone,last_seen,reported_online,extras,source) "
            "VALUES ($id,$module,$building,$zone,NULL,0,'{}','registry');")
SEED_FN = r'''
const REG = __REG__;
return [Object.keys(REG).map(id => ({params: {$id: id, $module: REG[id][0], $building: REG[id][1], $zone: REG[id][2]}}))];
'''.replace("__REG__", json.dumps(REGISTRY))

SQL_REJ = "INSERT INTO rejects (ts,topic,reason,raw) VALUES ($ts,$topic,$reason,$raw);"
SQL_DEV = ("INSERT INTO devices (device_id,module,building,zone,last_seen,reported_online,extras,source) "
           "VALUES ($id,$module,$building,$zone,$rx,$online,$extras,$source) "
           "ON CONFLICT(device_id) DO UPDATE SET last_seen=$rx, reported_online=$online, "
           "extras=CASE WHEN $is_status=1 THEN $extras ELSE extras END, source=$source;")
SQL_READ = ("INSERT INTO readings (ts,rx,module,building,zone,device,metric,value,unit,status,source) "
            "VALUES ($ts,$rx,$module,$building,$zone,$device,$metric,$value,$unit,$status,$source);")
SQL_LATEST = ("INSERT OR REPLACE INTO latest (device,metric,value,unit,status,ts,rx,source) "
              "VALUES ($device,$metric,$value,$unit,$status,$ts,$rx,$source);")
# Repeated 'active' event for an alert that is still open is ignored (de-duplication).
SQL_ALERT_INS = ("INSERT INTO alerts (ts,rx,device,module,building,zone,alert_type,severity,value,unit,source) "
                 "SELECT $ts,$rx,$device,$module,$building,$zone,$type,$severity,$value,$unit,$source "
                 "WHERE NOT EXISTS (SELECT 1 FROM alerts WHERE device=$device AND alert_type=$type AND cleared_ts IS NULL);")
SQL_ALERT_CLR = "UPDATE alerts SET cleared_ts=$rx WHERE device=$device AND alert_type=$type AND cleared_ts IS NULL;"
# Backend-generated device_offline alerts (heartbeat/stale detection), run every 10 s.
SQL_OFF_INS = ("INSERT INTO alerts (ts,rx,device,module,building,zone,alert_type,severity,value,unit,source) "
               "SELECT $now,$now,d.device_id,d.module,d.building,d.zone,'device_offline','warning',0,'bool','backend' "
               "FROM devices d WHERE d.last_seen IS NOT NULL AND (d.reported_online=0 OR d.last_seen < $cutoff) "
               "AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.device=d.device_id AND a.alert_type='device_offline' AND a.cleared_ts IS NULL);")
SQL_OFF_CLR = ("UPDATE alerts SET cleared_ts=$now WHERE alert_type='device_offline' AND cleared_ts IS NULL AND device IN "
               "(SELECT device_id FROM devices WHERE reported_online=1 AND last_seen >= $cutoff);")
FILTERS = "($module IS NULL OR {p}module=$module) AND ($building IS NULL OR {p}building=$building) AND ($zone IS NULL OR {p}zone=$zone)"
SQL_OVERVIEW = ("SELECT d.device_id,d.module,d.building,d.zone,d.last_seen,d.reported_online,d.extras,d.source AS dev_source,"
                "l.metric,l.value,l.unit,l.status,l.ts,l.rx,l.source FROM devices d LEFT JOIN latest l ON l.device=d.device_id WHERE "
                + FILTERS.format(p="d.") + " ORDER BY d.module,d.building,d.zone,d.device_id,l.metric;")
SQL_ALERTS = ("SELECT id,ts,rx,device,module,building,zone,alert_type,severity,value,unit,cleared_ts,ack_by,ack_ts,source FROM alerts WHERE "
              + FILTERS.format(p="") + " AND ($open=0 OR cleared_ts IS NULL) ORDER BY id DESC LIMIT 200;")
SQL_ACK = "UPDATE alerts SET ack_by=$by, ack_ts=$ts WHERE id=$id AND ack_ts IS NULL AND cleared_ts IS NULL;"
SQL_DEVREAD = ("SELECT ts,rx,metric,value,unit,status,source FROM readings WHERE device=$device ORDER BY id DESC LIMIT 40;")
SQL_CSV = ("SELECT ts,rx,module,building,zone,device,metric,value,unit,status,source FROM readings WHERE "
           + FILTERS.format(p="") + " AND ($device IS NULL OR device=$device) ORDER BY id DESC LIMIT 50000;")
SQL_REJECTS = "SELECT id,ts,topic,reason,raw FROM rejects ORDER BY id DESC LIMIT 50;"

# ----------------------------------------------------------------------------------------
# HTTP API functions
# ----------------------------------------------------------------------------------------
ROLE = r'''
function getRole(msg) {
    const r = String((msg.req.headers || {})["x-role"] || "viewer").toLowerCase();
    return ["viewer","operator","administrator"].includes(r) ? r : "viewer";
}
function deny(msg, need) { msg.statusCode = 403; msg.payload = {error: "role_forbidden", need: need}; return msg; }
function bad(msg, why) { msg.statusCode = 400; msg.payload = {error: why}; return msg; }
function filt(q) {
    const ok = v => (typeof v === "string" && /^[A-Za-z0-9_-]{1,40}$/.test(v)) ? v : null;
    return {$module: ok(q.module), $building: ok(q.building), $zone: ok(q.zone)};
}
'''
FN_OV_Q = ROLE + "msg.params = filt(msg.req.query || {});\nreturn msg;"
FN_OV_RES = r'''
const offline_s = flow.get("offline_s") || 120;
const now = Date.now();
const map = {};
for (const r of msg.payload) {
    let d = map[r.device_id];
    if (!d) {
        let extras = {}; try { extras = JSON.parse(r.extras || "{}"); } catch (e) {}
        const seen = r.last_seen ? Date.parse(r.last_seen) : null;
        const age = seen === null ? null : Math.max(0, Math.round((now - seen) / 1000));
        let health = "no_data";                       // never heard from
        if (seen !== null) health = !r.reported_online ? "offline" : (age > offline_s ? "stale" : "online");
        d = map[r.device_id] = {device_id: r.device_id, module: r.module, building: r.building, zone: r.zone,
            source: r.dev_source, last_seen: r.last_seen, age_s: age, health: health, extras: extras, metrics: []};
    }
    if (r.metric) d.metrics.push({metric: r.metric, value: r.value, unit: r.unit, status: r.status,
                                  ts: r.ts, rx: r.rx, source: r.source});
}
msg.payload = {now: new Date(now).toISOString(), offline_s: offline_s, devices: Object.values(map)};
return msg;
'''
FN_AL_Q = ROLE + r'''
const q = msg.req.query || {};
msg.params = Object.assign(filt(q), {$open: q.state === "all" ? 0 : 1});
return msg;
'''
FN_AL_RES = r'''
msg.payload = msg.payload.map(a => Object.assign(a, {
    state: a.cleared_ts ? "cleared" : (a.ack_ts ? "acknowledged" : "active")}));
return msg;
'''
FN_ACK = ROLE + r'''
if (getRole(msg) === "viewer") return [null, deny(msg, "operator")];
const id = parseInt(msg.req.params.id, 10);
if (!Number.isInteger(id) || id < 1) return [null, bad(msg, "bad_id")];
msg.params = {$by: getRole(msg), $ts: new Date().toISOString(), $id: id};
return [msg, null];
'''
FN_ACK_RES = "msg.payload = {ok: true};\nreturn msg;"
FN_DR_Q = ROLE + r'''
const id = msg.req.params.id;
if (!/^[A-Za-z0-9_-]{1,40}$/.test(id)) return [null, bad(msg, "bad_device")];   // output 2 = straight to the response
msg.params = {$device: id};
return [msg, null];
'''
FN_CSV_Q = ROLE + r'''
if (getRole(msg) !== "administrator") return [null, deny(msg, "administrator")];
const q = msg.req.query || {};
const dv = (typeof q.device === "string" && /^[A-Za-z0-9_-]{1,40}$/.test(q.device)) ? q.device : null;
msg.params = Object.assign(filt(q), {$device: dv});
return [msg, null];
'''
FN_CSV_RES = r'''
const cols = ["ts","rx","module","building","zone","device","metric","value","unit","status","source"];
// Quote fields, and neutralise spreadsheet formulas (text starting with = + - @).
function cell(v) {
    if (v === null || v === undefined) return "";
    let s = String(v);
    if (typeof v === "string" && /^[=+\-@]/.test(s)) s = "'" + s;
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
const lines = [cols.join(",")];
for (const r of msg.payload) lines.push(cols.map(c => cell(r[c])).join(","));
msg.payload = lines.join("\r\n") + "\r\n";
msg.headers = {"Content-Type": "text/csv; charset=utf-8",
               "Content-Disposition": 'attachment; filename="campus_readings.csv"'};
return msg;
'''
FN_CFG_GET = "msg.payload = {offline_s: flow.get('offline_s') || 120};\nreturn msg;"
FN_CFG_POST = ROLE + r'''
if (getRole(msg) !== "administrator") return deny(msg, "administrator");
const v = Number((msg.payload || {}).offline_s);
if (!Number.isInteger(v) || v < 10 || v > 3600) return bad(msg, "offline_s must be an integer 10..3600");
flow.set("offline_s", v);
msg.payload = {offline_s: v};
return msg;
'''
FN_PAGE = r'''
msg.headers = {"Content-Type": "text/html; charset=utf-8", "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"};
return msg;
'''
FN_TIMER = r'''
const offline_s = flow.get("offline_s") || 120;
const now = new Date();
msg.params = {$now: now.toISOString(), $cutoff: new Date(now.getTime() - offline_s * 1000).toISOString()};
return msg;
'''
FN_ERR = r'''
if (msg.req && msg.res) { msg.statusCode = 500; msg.payload = {error: "internal_error"}; return msg; }
return null;   // errors from the MQTT ingest branch are only logged
'''

TAB = "tab_main"
nodes = []
def add(**n):
    n.setdefault("z", TAB)
    nodes.append(n)

nodes.append({"id": TAB, "type": "tab", "label": "CHRIST Smart Campus", "disabled": False, "info": ""})
nodes.append({"id": "broker", "type": "mqtt-broker", "name": "Local Mosquitto", "broker": "127.0.0.1", "port": "1883",
              "clientid": "nodered-ingest", "autoConnect": True, "usetls": False, "protocolVersion": "4",
              "keepalive": "60", "cleansession": False})   # persistent session: QoS1 messages queued during a brief Node-RED outage
nodes.append({"id": "db", "type": "sqlitedb", "db": "data/campus.db", "mode": "RWC"})

def sql(id, name, query, x, y, wires, mode="prepared"):
    add(id=id, type="sqlite", mydb="db", sqlquery=mode, sql=query, name=name, x=x, y=y, wires=[wires])
def fn(id, name, code, x, y, wires, outputs=1):
    add(id=id, type="function", name=name, func=code.strip(), outputs=outputs, x=x, y=y, wires=wires)
def http_in(id, name, url, method, x, y, wires):
    add(id=id, type="http in", name=name, url=url, method=method, upload=False, swaggerDoc="", x=x, y=y, wires=[wires])

# ---- Ingest ----------------------------------------------------------------------------
add(id="mqin", type="mqtt in", name="telemetry/status/alerts", topic="christ-smart-campus/v1/+/+/+/+", qos="1",
    datatype="utf8", broker="broker", x=150, y=60, wires=[["validate"]])
fn("validate", "validate + route (FR-02)", VALIDATE, 400, 60,
   [["ins_rej", "dbg"], ["ins_dev"], ["ins_read"], ["ins_latest"], ["ins_alert"], ["clr_alert"]], outputs=6)
sql("ins_rej", "store reject", SQL_REJ, 700, 20, [])
add(id="dbg", type="debug", name="rejects", active=True, tosidebar=True, complete="params", x=700, y=60, wires=[])
sql("ins_dev", "upsert device (last_seen/health)", SQL_DEV, 720, 100, [])
sql("ins_read", "store reading", SQL_READ, 700, 140, [])
sql("ins_latest", "upsert latest", SQL_LATEST, 700, 180, [])
sql("ins_alert", "open alert (dedup)", SQL_ALERT_INS, 700, 220, [])
sql("clr_alert", "clear alert", SQL_ALERT_CLR, 700, 260, [])

# ---- Startup: tables + registry seed ---------------------------------------------------
add(id="init", type="inject", name="start: create tables", props=[{"p": "payload"}], repeat="", once=True, onceDelay="1",
    topic="", payload="", payloadType="date", x=140, y=340, wires=[["ct_readings"]])
chain = [c[0] for c in CREATES]
for i, (nm, q) in enumerate(CREATES):
    nxt = ["ct_" + chain[i + 1]] if i + 1 < len(CREATES) else ["seed_fn"]
    sql("ct_" + nm, "create " + nm, q, 340 + 170 * (i % 3), 340 + 40 * (i // 3), nxt, mode="fixed")
fn("seed_fn", "registry -> seed rows", SEED_FN, 340, 440, [["seed_sql"]])
sql("seed_sql", "seed devices", SEED_SQL, 560, 440, [])

# ---- Offline / stale detection (every 10 s) -------------------------------------------
add(id="timer", type="inject", name="every 10 s", props=[{"p": "payload"}], repeat="10", once=True, onceDelay="5",
    topic="", payload="", payloadType="date", x=130, y=500, wires=[["fn_timer"]])
fn("fn_timer", "cutoff = now - offline_s", FN_TIMER, 340, 500, [["off_ins"]])
sql("off_ins", "raise device_offline", SQL_OFF_INS, 570, 500, ["off_clr"])
sql("off_clr", "clear when back", SQL_OFF_CLR, 790, 500, [])

# ---- HTTP API --------------------------------------------------------------------------
Y = 580
http_in("h_ov", "GET /api/overview", "/api/overview", "get", 150, Y, ["fn_ov_q"])
fn("fn_ov_q", "filters", FN_OV_Q, 360, Y, [["sql_ov"]])
sql("sql_ov", "devices+latest", SQL_OVERVIEW, 540, Y, ["fn_ov_res"])
fn("fn_ov_res", "health + shape", FN_OV_RES, 740, Y, [["resp"]])

Y += 60
http_in("h_al", "GET /api/alerts", "/api/alerts", "get", 150, Y, ["fn_al_q"])
fn("fn_al_q", "filters", FN_AL_Q, 360, Y, [["sql_al"]])
sql("sql_al", "alerts", SQL_ALERTS, 540, Y, ["fn_al_res"])
fn("fn_al_res", "derive state", FN_AL_RES, 740, Y, [["resp"]])

Y += 60
http_in("h_ack", "POST /api/alerts/:id/ack", "/api/alerts/:id/ack", "post", 170, Y, ["fn_ack"])
fn("fn_ack", "role >= operator", FN_ACK, 400, Y, [["sql_ack"], ["resp"]], outputs=2)
sql("sql_ack", "acknowledge", SQL_ACK, 580, Y, ["fn_ack_res"])
fn("fn_ack_res", "ok", FN_ACK_RES, 760, Y, [["resp"]])

Y += 60
http_in("h_dr", "GET /api/device/:id/readings", "/api/device/:id/readings", "get", 180, Y, ["fn_dr_q"])
fn("fn_dr_q", "validate id", FN_DR_Q, 400, Y, [["sql_dr"], ["resp"]], outputs=2)
sql("sql_dr", "last 40 readings", SQL_DEVREAD, 580, Y, ["resp"])

Y += 60
http_in("h_csv", "GET /api/export.csv", "/api/export.csv", "get", 160, Y, ["fn_csv_q"])
fn("fn_csv_q", "role = administrator", FN_CSV_Q, 400, Y, [["sql_csv"], ["resp"]], outputs=2)
sql("sql_csv", "readings", SQL_CSV, 600, Y, ["fn_csv_res"])
fn("fn_csv_res", "to CSV", FN_CSV_RES, 780, Y, [["resp"]])

Y += 60
http_in("h_rj", "GET /api/rejects", "/api/rejects", "get", 150, Y, ["sql_rj"])
sql("sql_rj", "last 50 rejects", SQL_REJECTS, 360, Y, ["resp"], mode="fixed")

Y += 60
http_in("h_cg", "GET /api/config", "/api/config", "get", 150, Y, ["fn_cg"])
fn("fn_cg", "read config", FN_CFG_GET, 360, Y, [["resp"]])
Y += 40
http_in("h_cp", "POST /api/config", "/api/config", "post", 150, Y, ["fn_cp"])
fn("fn_cp", "admin: set offline_s", FN_CFG_POST, 360, Y, [["resp"]])

Y += 60
http_in("h_pg", "GET /campus", "/campus", "get", 130, Y, ["f_page"])
add(id="f_page", type="file in", name="platform/dashboard.html", filename="platform/dashboard.html", filenameType="str",
    format="utf8", chunk=False, sendError=True, encoding="none", allProps=False, x=360, y=Y, wires=[["fn_page"]])
fn("fn_page", "headers", FN_PAGE, 600, Y, [["resp"]])

add(id="resp", type="http response", name="", statusCode="", headers={}, x=980, y=700, wires=[])
add(id="catch", type="catch", name="", scope=None, uncaught=False, x=130, y=Y + 60, wires=[["fn_err"]])
fn("fn_err", "500 for API errors", FN_ERR, 340, Y + 60, [["resp"]])

out = pathlib.Path(__file__).resolve().parent.parent / "flows.json"
out.write_text(json.dumps(nodes, indent=2), encoding="utf-8")
print("wrote", out, f"({len(nodes)} nodes)")
