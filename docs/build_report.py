"""Builds docs/CHRIST_Smart_Campus_Report_v2.docx from docs/Project_Report_base.docx (made from LAB Temp T5.dotx).
Test results are read from tests/results.json so the report can never disagree with the evidence.
Run from project root:  python docs/build_report.py
"""
import json, pathlib, re, zipfile
from xml.sax.saxutils import escape
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = ROOT / "docs" / "Project_Report_base.docx"
OUT = ROOT / "docs" / "CHRIST_Smart_Campus_Report_v2.docx"
R = json.loads((ROOT / "tests" / "results.json").read_text(encoding="utf-8"))

media, rels = [], []          # (zip path, bytes), relationship xml


def run(t, b=False, i=False, sz=None, color=None):
    pr = ("<w:b/>" if b else "") + ("<w:i/>" if i else "") + (f'<w:color w:val="{color}"/>' if color else "") + (f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>' if sz else "")
    return f'<w:r>{"<w:rPr>" + pr + "</w:rPr>" if pr else ""}<w:t xml:space="preserve">{escape(t)}</w:t></w:r>'


def p(t="", style=None, b=False, i=False, sz=None, align=None, after=None, keep=False, runs=None, num=None, color=None):
    ppr = (f'<w:pStyle w:val="{style}"/>' if style else "") + ("<w:keepNext/>" if keep else "") + \
          (f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>' if num else "") + \
          (f'<w:spacing w:after="{after}"/>' if after is not None else "") + (f'<w:jc w:val="{align}"/>' if align else "")
    body = runs if runs is not None else (run(t, b, i, sz, color) if t else "")
    return f'<w:p>{"<w:pPr>" + ppr + "</w:pPr>" if ppr else ""}{body}</w:p>'


def h1(t): return p(t, "Heading1", keep=True)
def h2(t): return p(t, "Heading2", keep=True)
def bullet(t, lead=None):
    runs = (run(lead + " ", b=True) if lead else "") + run(t)
    return p(runs=runs, num=90, after=40)


def table(rows, widths, sz=18, header=True):
    tw = sum(widths)
    x = f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="{tw}" w:type="dxa"/><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>' + \
        "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>"
    for ri, row in enumerate(rows):
        hd = header and ri == 0
        x += "<w:tr>" + ("<w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" if hd else "<w:trPr><w:cantSplit/></w:trPr>")
        for ci, cell in enumerate(row):
            shade = '<w:shd w:val="clear" w:color="auto" w:fill="D9E2F3"/>' if hd else ""
            bold = hd or (cell in ("PASS", "FAIL", "NOT RUN"))
            col = {"PASS": "1B7A3E", "FAIL": "B3261E", "NOT RUN": "8A5A00"}.get(cell)
            x += f'<w:tc><w:tcPr><w:tcW w:w="{widths[ci]}" w:type="dxa"/>{shade}</w:tcPr>' + p(runs=run(str(cell), b=bold, sz=sz, color=col), after=0) + "</w:tc>"
        x += "</w:tr>"
    return x + "</w:tbl>" + p("", after=60)


def image(path, width_in, alt, caption):
    im = Image.open(path); w, h = im.size
    cx = int(width_in * 914400); cy = int(cx * h / w)
    n = len(media) + 1; rid = f"rIdImg{n}"; name = f"report_img{n}.png"
    media.append((f"word/media/{name}", pathlib.Path(path).read_bytes()))
    rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>')
    d = (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{100 + n}" name="Picture {n}" descr="{escape(alt)}"/>'
         f'<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
         f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{100 + n}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
         f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
         f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    return p(runs=d, align="center", after=40, keep=True) + p(caption, i=True, sz=18, align="center", after=160)


def code_block(path):
    out = ""
    for ln in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        r = ('<w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="14"/><w:szCs w:val="14"/></w:rPr>'
             f'<w:t xml:space="preserve">{escape(ln) if ln else " "}</w:t></w:r>')
        out += f'<w:p><w:pPr><w:spacing w:after="0" w:line="200" w:lineRule="exact"/></w:pPr>{r}</w:p>'
    return out


SH = ROOT / "docs" / "screenshots"
res = R["results"]; npass, nfail, nrun = R["passed"], R["failed"], R["not_run"]
RC = json.loads((ROOT / "tests" / "results_cpp.json").read_text(encoding="utf-8"))["results"]
CODE = ROOT / "docs" / "code"


def opt_image(name, width_in, alt, caption, what):
    """Real Wokwi/Blynk screenshots can only be taken by the student: use the PNG if present, else a visible placeholder."""
    f = SH / name
    if f.exists():
        return image(f, width_in, alt, caption)
    return p(f"[Insert screenshot {name}: {what}]", i=True, color="B3261E", after=160)

# ------------------------------------------------------------------------------ cover
cover = (p("", after=1200) + p("Integrated IoT-Based Campus Management System", "Title", align="center") +
         p("Project report: classroom module and shared platform", sz=30, align="center", after=360) +
         p("Module: classroom (device CLASS-A-ESP32-01, BLOCK-A / ROOM-204)", align="center", after=60) +
         p("Educational prototype on an isolated lab network. All device data is simulated (Wokwi, Blynk Cloud, Python simulators).", align="center", after=60) +
         p("Report date: 16 November 2026", align="center", after=60))

body = []
A = body.append

A(h1("1. Problem statement and scope"))
A(p("Empty classrooms often keep lights and fans running, which wastes energy, while occupied rooms can become too warm or too dark. "
    "This project builds a small, working slice of a campus IoT platform: one module that senses a classroom and acts on it locally, plus the shared platform "
    "(broker, validation, database, dashboard, alerts) that any module on the campus could use."))
A(p("Scope was deliberately limited to what one student can build and prove:"))
A(bullet("the classroom module (PIR occupancy, LDR light level, DHT22 temperature, a lamp and a fan). No hardware was available, so the ESP32 runs in the Wokwi simulator with its dashboard on Blynk Cloud; PlatformIO is the fallback build if Wokwi does not work;", "Real module:"))
A(bullet("Mosquitto broker, Node-RED ingestion with validation, SQLite storage, alerts with acknowledgement, stale/offline detection, filters, CSV export, simulated roles and an HTML dashboard, fed by Python device simulators that implement the same classroom rules;", "Shared platform:"))
A(bullet("a clearly labelled simulator that fills the other five modules (parking, energy, water, waste, safety) so the campus overview looks complete.", "Optional:"))
A(p("Boundaries respected: isolated lab network and localhost only; no mains, pumps, CCTV, access control or fire alarms; no personal data; no credentials in source. "
    "Every simulated message carries the field \"source\":\"simulated\" and the dashboard labels it SIMULATED. The safety module is a demo input, not a certified alarm."))

A(h1("2. System architecture"))
A(image(ROOT / "docs" / "architecture.png", 5.8, "Block diagram of devices, broker, Node-RED, SQLite and dashboard", "Figure 1. Two lanes: the Wokwi ESP32 shows its state on Blynk Cloud; Python simulators publish MQTT through Mosquitto to Node-RED, SQLite and the HTML dashboard."))
A(p("The design has two lanes that are not connected: Wokwi cannot reach the broker on localhost, so the Wokwi ESP32 sends its state to Blynk Cloud, which is the module's own dashboard, while the shared platform receives the same classroom behaviour from the Python simulators. Both lanes implement the same rules and were tested separately."))
A(p("On the platform lane, devices publish JSON over MQTT at QoS 1 to topics of the form christ-smart-campus/v1/{module}/{building}/{device_id}/{telemetry|status|alerts}. "
    "Each message carries one metric using the shared contract; a classroom cycle therefore sends three messages (temperature, light_level, occupancy_detected). "
    "A status heartbeat every 45 s is retained and also carries the lamp and fan state; a last-will message marks the device offline if it disappears."))
A(p("Example telemetry message:", b=True, after=40))
A(p('{"schema_version":"1.0","campus_id":"CHRIST-DEMO","module":"classroom","building_id":"BLOCK-A","zone_id":"ROOM-204","device_id":"CLASS-A-ESP32-01",'
    '"timestamp":"2026-11-15T18:29:08Z","metric":"temperature","value":29.2,"unit":"C","status":"normal","source":"simulated"}', sz=16, after=120))

A(h1("3. Classroom module design"))
A(table([["Rule", "Behaviour", "Why"],
         ["Light", "Occupied and dark: ON. Unoccupied 30 s continuously: OFF.", "Saves energy only when nobody is present."],
         ["Darkness", "Dark below 30 %, bright above 40 % (hysteresis).", "The lamp itself lights the LDR; one threshold would make it flicker."],
         ["Fan", "Occupied and above 30 C: ON. Below 27 C: OFF. Between: keep state.", "The band stops rapid on/off cycling."],
         ["PIR debounce", "Two consecutive 1 Hz samples count as motion.", "A single noise pulse must not switch the light."],
         ["Sensor failure", "Three bad DHT reads in a row: temperature unknown, fan OFF, critical alert, nothing fake published.", "Fail-safe: never run an actuator on data we do not trust."]],
        [1500, 4300, 3560]))
A(p("The control logic is a pure function of sensor inputs and a clock. It exists twice with identical rules: Python (simulator/classroom_logic.py, used by the platform simulators) and a header-only C++ port "
    "(classroom_logic.h) used by the Wokwi and PlatformIO firmware. Both pass the same 11 unit tests with a fake clock, the C++ one compiled and run on the PC. "
    "The sketch reads the sensors, runs the controller once a second, drives the lamp and fan outputs and mirrors the state to Blynk (V0 temperature, V1 light, V2 occupancy, V3 lamp, V4 fan, V5 status, V6 data source) "
    "and raises Blynk events for high_temperature and sensor_failure. Control keeps working if Wi-Fi or Blynk is down. "
    "In Wokwi the fan is a blue LED; the real circuit below uses a transistor and flyback diode. Planned pins (an assumption to verify): PIR GPIO27, LDR GPIO34 (ADC1), DHT22 GPIO15, lamp GPIO26, fan GPIO25."))

A(image(ROOT / "docs" / "circuit_diagram.png", 4.3, "Planned wiring diagram of the classroom module", "Figure 2. Planned wiring (not built or tested; pin numbers are assumptions to verify)."))

A(h1("4. Platform implementation"))
A(bullet("Node-RED subscribes to all devices and rejects, with a stored reason, any message that has malformed JSON, missing fields, an unknown module or device, "
         "a location that does not match the device registry, a topic that does not match the payload, an invalid or far-future timestamp, a wrong type or an out-of-range value.", "Validation (FR-02):"))
A(bullet("SQLite tables readings (history), latest (current value per device and metric), devices (last seen and health), alerts and rejects.", "Storage:"))
A(bullet("A device is Online, Stale (no message for the configurable timeout, default 120 s), Offline (last will received) or No data. Stale and offline devices raise a device_offline alert that clears on return.", "Device health:"))
A(bullet("An active alert is stored once even if the event repeats (QoS 1 can duplicate), shown as active, acknowledged (who and when) or cleared.", "Alerts:"))
A(bullet("A single HTML page polls the API every 2 s: campus overview, building/zone view, module page, device details, alert list, admin page; filters by module, building and zone; units and last-updated time everywhere.", "Dashboard:"))
A(bullet("Viewer reads; Operator also acknowledges alerts; Administrator also exports CSV and changes the timeout. The server enforces an X-Role header, but this is a demonstration, not authentication.", "Simulated roles:"))
A(bullet("campus_sim.py publishes the other five modules (four parking-slot devices, energy, water, waste, safety), all labelled simulated, with threshold alerts.", "Other modules:"))

A(h1("5. Validation and results"))
A(p(f"The automated runner (tests/run_tests.py) drives the live system: it publishes messages over MQTT, calls the HTTP API and controls the classroom simulator through its command interface. "
    f"Result of the final run: {npass} passed, {nfail} failed, {nrun} not run. "
    + ("All executed tests passed. " if nfail == 0 else "Failures are listed below and are discussed honestly in Section 7. ")
    + "The broker-outage test (T5b) needs an administrator to stop the Mosquitto service, so it is recorded as not run until done by hand."))
rows = [["ID", "Test", "Expected", "Actual", "Result"]] + [[r["id"], r["name"], r["expected"], r["actual"], r["result"]] for r in res]
A(table(rows, [520, 2000, 2400, 3600, 840], sz=15))
A(p("Wokwi / Blynk / PlatformIO files were checked offline (tests/run_cpp_checks.py). The eight behaviour tests W1-W8 were run in the Wokwi simulator (VS Code extension, PlatformIO build, DHT22 on GPIO15) with a Blynk account. W1, W2 and W6 were confirmed from the Serial log; W3-W8 were run and reported by the student. Results:", b=True, after=60))
A(table([["ID", "Test", "Expected", "Actual", "Result"]] + [[r["id"], r["name"], r["expected"], r["actual"], r["result"]] for r in RC], [520, 2400, 2200, 3400, 840], sz=15))
A(p("Common tests T1-T7 follow the specification: valid feed, missing field rejected, unknown device flagged, offline after timeout, reconnect resumes, alert correct, units and last update shown. "
    "Module tests: M1 normal, M2 threshold, M3 boundary, M4 sensor disconnect, M5 recovery, M6 vacancy timeout and the stationary-occupant limitation, M7 false trigger.", sz=20))

A(h1("6. Evidence"))
A(image(SH / "ph7_overview.png", 4.4, "Campus overview with nine devices", "Figure 3. Campus overview: nine devices online, SIMULATED labels, two active alerts."))
A(image(SH / "ph6_module_classroom.png", 4.2, "Classroom module page", "Figure 4. Classroom module page: values with units, update age, lamp and fan state."))
A(image(SH / "ph7_alerts.png", 4.6, "Alert list", "Figure 5. Alert list: active, acknowledged (with operator) and cleared alerts."))
A(opt_image("wokwi_simulation.png", 4.6, "Wokwi simulation running", "Figure 6. Wokwi: the ESP32 circuit running (lamp and fan LEDs, sensors).", "Wokwi canvas with the simulation running"))
A(opt_image("wokwi_serial.png", 5.4, "Wokwi serial monitor", "Figure 7. Serial Monitor output of the sketch.", "Wokwi Serial Monitor with occ/lamp/fan lines and ALERT lines"))
A(opt_image("blynk_dashboard.png", 4.6, "Blynk dashboard", "Figure 8. Blynk Cloud dashboard for the classroom module (token hidden).", "Blynk web dashboard showing the live values"))

A(h2("6.1 Wokwi test screenshots (W1-W8)"))
A(p("One screenshot per Wokwi behaviour test. Each file goes in docs/screenshots/ and is picked up automatically when the report is rebuilt.", sz=20))
for wid, nm, what in [
    ("W1", "Normal: occupied + dark, lamp ON", "Wokwi canvas and Serial Monitor showing occ=1, ldr=20 %, lamp=1"),
    ("W2", "31.5 C, fan ON + high_temperature event", "DHT22 set above 30 C, fan LED on, ALERT high_temperature in Serial"),
    ("W3", "Boundary 30.0 / 30.1 / 27.0 / 26.9 C", "Serial lines showing the fan flipping only above 30 C and below 27 C"),
    ("W4", "DHT SDA wire removed: sensor fault, fan OFF", "Disconnected DHT22 wire, sensor_failure alert, fan LED off"),
    ("W5", "Recovery after reconnecting DHT", "Wire restored, alert cleared, logic resumed"),
    ("W6", "Vacancy 30 s: lamp OFF", "Serial: room vacant -> occ=0 lamp=0 fan=0"),
    ("W7", "Short PIR pulse ignored", "PIR delayTime 1, lamp stays OFF"),
    ("W8", "Wrong Blynk token: local control still works", "Blynk connection failure with lamp and fan still reacting"),
]:
    A(opt_image(f"wokwi_{wid.lower()}.png", 4.8, f"Wokwi test {wid}", f"Figure 6.{wid}. {wid}: {nm}.", f"{wid} - {what}"))

A(h2("6.2 Module block diagram and pin connections"))
A(p("Block diagram of the classroom module: the three inputs (PIR, LDR, DHT22) feed the ESP32, which drives the lamp and fan outputs and reports to Blynk. "
    "Pin map used by the sketch and diagram.json:", sz=20))
A(image(ROOT / "docs" / "circuit_diagram.png", 4.3, "Classroom module block and wiring diagram", "Figure 9. Classroom module block diagram and pin connections (Wokwi simulation; real-hardware pins are unverified)."))
A(table([["Component", "ESP32 pin", "Direction", "Note"],
         ["PIR motion sensor", "GPIO27", "Input", "Occupancy; two consecutive samples = motion"],
         ["LDR light sensor", "GPIO34 (ADC1)", "Input", "Light level %, ADC1 is safe with Wi-Fi"],
         ["DHT22", "GPIO15", "Input", "Temperature; three bad reads = sensor fault"],
         ["Lamp LED", "GPIO26", "Output", "Classroom light"],
         ["Fan LED", "GPIO25", "Output", "Blue LED in Wokwi; transistor + flyback diode on real hardware"]],
        [2200, 1800, 1300, 4060]))

A(h1("Project links"))
A(table([["Item", "Link"],
         ["Wokwi project (classroom module)", "https://wokwi.com/projects/480812744829365249"],
         ["GitHub repository", "[Insert GitHub repository URL]"],
         ["Deployed dashboard", "[Insert deployed dashboard URL. The localhost address http://localhost:1880/campus only works on the lab PC]"]],
        [3000, 6360]))

A(h1("7. Limitations"))
A(bullet("No physical hardware was used. Sensor accuracy, PIR behaviour, LDR calibration and electrical wiring are unvalidated. The Wokwi/Blynk firmware passed offline checks (C++ unit tests, diagram.json validation) and the simulator tests W1-W8; screenshots of the running simulator and the Blynk dashboard are in Section 6; W1-W4, W6, W7 and W8 have per-test screenshots; W5 (recovery after reconnecting the DHT) relies on the student-reported run because Wokwi applies wiring changes only on restart."))
A(bullet("A PIR detects movement, not presence: a motionless person can lose the light after 30 s (recorded in test M6)."))
A(bullet("The Wokwi lane does not feed the Node-RED platform (Wokwi cannot reach localhost), so the shared platform shows simulator data, not the Wokwi device. The optional MQTT firmware (firmware/classroom_esp32) would bridge this on real hardware, but PubSubClient publishes at QoS 0 only."))
A(bullet("Blynk Cloud is a third-party service: the auth token is a secret kept out of the repository, and free-plan limits were not investigated. The ESP32 pin names in diagram.json are not documented by Wokwi and must be confirmed in the editor."))
A(bullet("Roles are simulated and offer no real security; the broker allows anonymous access on localhost only; there is no TLS."))
A(bullet("The last-will message carries its creation time, so the backend relies on its own receive time. Silent network loss is detected only by the timeout."))
A(bullet("The broker-outage test (T5b) was not executed automatically; evidence for it must be captured by hand."))
A(bullet("SQLite and a single Node-RED instance suit a demo, not a campus-scale deployment."))

A(h1("8. Future work"))
A(p("Capture screenshots of the Wokwi runs; build and calibrate the circuit and run the firmware on a real ESP32, bridging it to the platform with QoS 1 publishing and an NTP source on the lab network; replace the role dropdown with real login and broker ACLs with TLS; "
    "add a presence sensor to fix the stationary-occupant case; add trends and charts; and let the five other modules be implemented by their own devices using the same contract."))

A(h1("Appendix A. Files and how to run"))
A(table([["Path", "Purpose"],
         ["platform/build_flow.py, flows.json", "Generates and holds the Node-RED flow (ingest, API, alerts)."],
         ["platform/dashboard.html", "Dashboard served at http://localhost:1880/campus"],
         ["simulator/classroom_logic.py, test_logic.py", "Tested control logic and its unit tests."],
         ["simulator/classroom_sim.py, campus_sim.py", "Simulated classroom device and the other five modules."],
         ["tests/run_tests.py, results.json", "Automated live validation and its raw results."],
         ["wokwi/classroom/", "Wokwi project: sketch.ino, diagram.json, classroom_logic.h, libraries.txt, README with Blynk setup and tests W1-W8."],
         ["platformio/classroom/", "PlatformIO fallback project (platformio.ini, wokwi.toml, generated src/main.cpp)."],
         ["tests/cpp/, tests/run_cpp_checks.py", "Native C++ unit tests, stubbed type-check and offline checks."],
         ["firmware/classroom_esp32/", "Optional MQTT firmware for real hardware (untested, future work)."],
         ["docs/", "Design, validation notes, demo script, viva questions, screenshots."]], [3600, 5760]))
A(p("Run: start Mosquitto and Node-RED (node-red -u . from the project root), open /campus, then python simulator/classroom_sim.py and python simulator/campus_sim.py --demo.", sz=20))

A(h1("Appendix B. Source screenshots: Wokwi, PlatformIO, firmware"))
A(p("Rendered from the files in the repository (docs/make_code_images.py), so they always match the code.", sz=20))
A(image(CODE / "diagram_json.png", 4.4, "diagram.json", "Figure B1. wokwi/classroom/diagram.json: parts and connections of the Wokwi circuit."))
A(image(CODE / "sketch_1.png", 6.2, "sketch.ino part 1", "Figure B2. sketch.ino (1/2): header, pin map, calibration, Blynk helpers."))
A(image(CODE / "sketch_2.png", 6.2, "sketch.ino part 2", "Figure B3. sketch.ino (2/2): setup() and loop() with the non-blocking Blynk link."))
A(image(CODE / "classroom_logic_h.png", 5.8, "classroom_logic.h", "Figure B4. classroom_logic.h: the control logic shared by Wokwi and PlatformIO."))
A(image(CODE / "config_files.png", 4.8, "platformio.ini wokwi.toml libraries.txt", "Figure B5. platformio.ini, wokwi.toml and libraries.txt."))
A(image(CODE / "cpp_unit_tests.png", 4.2, "C++ unit tests output", "Figure B6. Native C++ unit tests: 11 passed."))

A(h1("Appendix C. Full source code"))
A(h2("C.1 wokwi/classroom/sketch.ino"))
A("".join([code_block(ROOT / "wokwi" / "classroom" / "sketch.ino")]))
A(h2("C.2 wokwi/classroom/classroom_logic.h"))
A(code_block(ROOT / "wokwi" / "classroom" / "classroom_logic.h"))

# ------------------------------------------------------------------------------ assemble
bul = ('<w:abstractNum w:abstractNumId="90"><w:multiLevelType w:val="hybridMultilevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
       '<w:lvlText w:val="&#8226;"/><w:lvlJc w:val="left"/><w:pPr><w:ind w:left="540" w:hanging="270"/></w:pPr></w:lvl></w:abstractNum>')
zin = zipfile.ZipFile(BASE)
doc = zin.read("word/document.xml").decode("utf-8")
head, tail = doc.split("<w:body>", 1)
sect = tail[tail.index("<w:sectPr"):]
pagebreak = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
new_doc = head + "<w:body>" + cover + pagebreak + "".join(body) + sect

numbering = zin.read("word/numbering.xml").decode("utf-8")
i = numbering.find("<w:num ")
numbering = (numbering[:i] + bul + numbering[i:]) if i != -1 else numbering.replace("</w:numbering>", bul + "</w:numbering>")
numbering = numbering.replace("</w:numbering>", '<w:num w:numId="90"><w:abstractNumId w:val="90"/></w:num></w:numbering>')
ct = zin.read("[Content_Types].xml").decode("utf-8")
if 'Extension="png"' not in ct:
    ct = ct.replace("<Default ", '<Default Extension="png" ContentType="image/png"/><Default ', 1)
drel = zin.read("word/_rels/document.xml.rels").decode("utf-8").replace("</Relationships>", "".join(rels) + "</Relationships>")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zo:
    for it in zin.infolist():
        if it.filename.endswith("/"):
            continue
        data = zin.read(it.filename)
        if it.filename == "word/document.xml": data = new_doc.encode("utf-8")
        elif it.filename == "word/numbering.xml": data = numbering.encode("utf-8")
        elif it.filename == "[Content_Types].xml": data = ct.encode("utf-8")
        elif it.filename == "word/_rels/document.xml.rels": data = drel.encode("utf-8")
        zo.writestr(it.filename, data)
    for name, data in media:
        zo.writestr(name, data)
words = len(re.sub(r"<[^>]+>", " ", new_doc).split())
print("wrote", OUT, f"({words} words, {len(media)} images)")
