# CHRIST Smart Campus - classroom module + shared platform (educational prototype)

A solo MCA project: one **classroom** module plus a small shared platform (MQTT broker, validation, SQLite, alerts, dashboard).
Educational prototype on an **isolated lab network, localhost only**. **All device data is simulated** (no hardware was available) and every simulated message carries `"source":"simulated"`.

## What works, what does not
| Works and is tested | Not done / not validated |
|---|---|
| Classroom control logic: 11 unit tests in Python and the same 11 in C++ (native), and a simulated device publishing over MQTT | Real hardware: wiring, sensor accuracy, PIR behaviour, LDR calibration |
| Wokwi project files: `diagram.json` validated, sketch type-checked against stubbed headers, PlatformIO copy in sync, no secrets in the repo | **Wokwi and Blynk behaviour (tests W1-W8) not run**: I could not run Wokwi or Blynk; real-API compile on PlatformIO not done |
| Validation (FR-02), storage, alerts with acknowledgement, stale/offline detection, filters, CSV export, simulated roles, dashboard | ESP32 firmware in `firmware/` is **untested and uncompiled** (future work) |
| Optional simulator for parking, energy, water, waste, safety (labelled simulated) | Broker-outage test T5b (needs admin to stop Mosquitto: do it by hand) |
| 25 automated live tests passed (`docs/test_results.md`) | Real login/TLS: roles are a demonstration, not security |

## Architecture: two lanes (not connected)
1. **Module lane**: the classroom ESP32 runs in the **Wokwi** simulator (PlatformIO is the fallback build) and shows its state on a **Blynk Cloud** dashboard. See `wokwi/classroom/README.md`.
2. **Platform lane**: Python device simulators -> **Mosquitto** (MQTT, QoS 1, last will) -> **Node-RED** (validate, route, API) -> **SQLite**; the HTML dashboard at `/campus` polls the API every 2 s.
Wokwi cannot reach `localhost`, so lane 1 does not feed lane 2; both implement the same classroom rules (Python and C++ copies of the logic, same 11 unit tests).
Diagram: `docs/architecture.png`. Planned circuit: `docs/circuit_diagram.png` (planned only, pin numbers are assumptions).

Topic: `christ-smart-campus/v1/{module}/{building}/{device_id}/{telemetry|status|alerts}` (building-level).
Example message:
```json
{"schema_version":"1.0","campus_id":"CHRIST-DEMO","module":"classroom","building_id":"BLOCK-A","zone_id":"ROOM-204","device_id":"CLASS-A-ESP32-01","timestamp":"2026-11-15T18:29:08Z","metric":"temperature","value":29.2,"unit":"C","status":"normal","source":"simulated"}
```

## Prerequisites (Windows 11 used here)
- Mosquitto 2.x (service running on 1883) - `platform/mosquitto.conf` is the config used for the lab (localhost listener). If you run Mosquitto as a service it uses its own config file; make sure it listens on 127.0.0.1:1883.
- Node.js 22 and Node-RED (`npm i -g node-red`) plus the SQLite node: `npm i -g node-red-node-sqlite` (needs a native build; if it fails, tell your tutor/see Troubleshooting). The dashboard widget package is **not** needed.
- Python 3.11+: `pip install -r simulator/requirements.txt` (paho-mqtt 2.x). The report/diagram scripts also use Pillow, matplotlib.

## Setup and run
1. **Broker**: start the Mosquitto service (or `mosquitto -c platform/mosquitto.conf -v`).
2. **Flow**: `python platform/build_flow.py` regenerates `flows.json` (do this with Node-RED stopped, or import the file in the editor).
3. **Node-RED**: from the project root run `node-red -u .` (the working folder matters: the DB is `data/campus.db` and the page is `platform/dashboard.html`). It listens on 127.0.0.1:1880 only (`uiHost` in `settings.js`).
4. **Dashboard**: open `http://localhost:1880/campus`. Pick a role (Viewer / Operator / Administrator) in the top bar.
5. **Classroom device (simulated)**: `python simulator/classroom_sim.py`, then type `enter`, `dark`, `temp 31.5`, `dhtfail`, `dhtok`, `still`, `leave`, `blip`, `status`, `quit`. `--demo` runs a 105 s scripted scenario.
6. **Other five modules (optional)**: `python simulator/campus_sim.py --demo` (110 s) or without `--demo` for commands `smoke on|off`, `spike`, `fill`, `empty`, `park 1 on`.
7. **One-off test messages**: `python simulator/send_one.py good|missing|badjson|unknown|badtime|range`.

## Wokwi + Blynk + PlatformIO (module lane)
Full steps, Blynk datastreams (V0-V6), events and the W1-W8 test procedure are in `wokwi/classroom/README.md`. In short:
1. Blynk Console: create a template with the datastreams and the events `high_temperature`, `sensor_failure`; create a device; copy the token.
2. Wokwi: new ESP32 Arduino project, paste `sketch.ino`, `diagram.json`, `classroom_logic.h`, `libraries.txt`, and add `secrets.h` (from `secrets.example.h`) with **your** token. Start the simulation.
3. Wokwi does not work for you? `platformio/classroom/`: copy `include/secrets.example.h` to `include/secrets.h`, `pio run`, then F1 -> Wokwi: Start Simulator (VS Code extension). `python tools/sync_platformio.py` regenerates `src/main.cpp` from the sketch.
4. Never commit or share the token. Capture screenshots for the report as `docs/screenshots/wokwi_simulation.png`, `wokwi_serial.png`, `blynk_dashboard.png`, then `python docs/build_report.py` (red "[Insert screenshot...]" lines in the report show what is still missing).

Deep links: `/campus#alerts`, `/campus#module:classroom`, `/campus#device:CLASS-A-ESP32-01`, `/campus#admin`.

## Roles (simulated)
Viewer: read only. Operator: also acknowledge alerts. Administrator: also CSV export and change the offline timeout (default 120 s, resets on backend restart). The server checks an `X-Role` header; anyone can change it, so this is **not authentication**.

## Tests
- Logic only: `python simulator/test_logic.py` (Python) and `python tests/run_cpp_checks.py` (C++ unit tests, sketch type-check, diagram/PlatformIO/secrets checks; needs g++). W1-W8 stay "NOT RUN" until done in Wokwi.
- Full live suite (needs Mosquitto + Node-RED running, simulators stopped, about 4 minutes): `python tests/run_tests.py` -> `docs/test_results.md`, `tests/results.json`. It leaves test rows in the database; delete `data/campus.db` (with Node-RED stopped) for a clean demo.
- Broker outage T5b by hand: see `docs/phase8_validation.md`.

## Files
| Path | What |
|---|---|
| `platform/build_flow.py`, `flows.json` | Node-RED flow generator and the generated flow (ingest, API, alerts, stale detection) |
| `platform/dashboard.html` | Dashboard page (no external libraries) |
| `simulator/classroom_logic.py`, `test_logic.py` | Tested control logic and its tests |
| `simulator/classroom_sim.py`, `campus_sim.py`, `send_one.py` | Simulated classroom device, other modules, single test message |
| `tests/run_tests.py` | Automated live validation |
| `wokwi/classroom/` | **Module firmware for Wokwi + Blynk**: `sketch.ino`, `diagram.json`, `classroom_logic.h`, `libraries.txt`, README |
| `platformio/classroom/` | PlatformIO fallback project (`platformio.ini`, `wokwi.toml`, generated `src/main.cpp`) |
| `tests/cpp/`, `tests/run_cpp_checks.py`, `tools/sync_platformio.py` | C++ unit tests + stubs, offline checks, sync script |
| `docs/make_code_images.py`, `docs/code/` | Renders `diagram.json`/sketch/config as images for the report |
| `firmware/classroom_esp32/` | Optional MQTT firmware for real hardware (untested; see its README for gaps) |
| `docs/` | Design (`phase1_design.md`), validation + demo script + BOM (`phase8_validation.md`), viva questions, report (`CHRIST_Smart_Campus_Report.docx`), diagrams, screenshots |

Secrets: never commit credentials. Copy `.env.example` to `.env` and `firmware/classroom_esp32/secrets.example.h` to `secrets.h` (both gitignored). Currently the broker allows anonymous access on localhost only.

## Safety
Lab bench, low voltage only. No mains, distribution boards, real pumps, CCTV, access control or fire alarms. The safety module is a demo input (push-button/scripted), **not** a certified life-safety system, and nothing generates smoke or releases gas. No personal data is used. See the safe power-up checklist in `docs/phase8_validation.md` before connecting any hardware.

## Troubleshooting
| Symptom | Likely cause / fix |
|---|---|
| `/campus` blank or 404 | Node-RED not started from the project root, or flow not deployed (restart it, check `flows.json`). |
| Dashboard says "Backend unreachable" | Node-RED stopped; it recovers by itself when it is back. |
| Nothing arrives | Mosquitto not running or not on 127.0.0.1:1883; check `mosquitto -v` output. |
| SQLite node will not install | Native build on your Node version failed; install build tools or try a different Node LTS. |
| Simulator exits with `CallbackAPIVersion` error | Old paho-mqtt; `pip install -U "paho-mqtt>=2"`. |
| Messages in Admin > rejected log | Validation working: read the reason (unknown device, out of range, ...). |
| `device_offline` alerts after you stop a simulator | Expected; they clear when the device is back. |
