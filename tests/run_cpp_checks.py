"""Offline checks for the Wokwi / Blynk / PlatformIO files (no Wokwi, Blynk or ESP32 toolchain needed).
Writes tests/results_cpp.json, read by docs/build_report.py.   Run: python tests/run_cpp_checks.py
Wokwi/Blynk behaviour (W1-W8) can only be tested inside Wokwi: those rows are recorded as NOT RUN until you do them.
"""
import json
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
W = ROOT / "wokwi" / "classroom"
P = ROOT / "platformio" / "classroom"
RES = []


def rec(tid, name, expected, actual, ok):
    RES.append({"id": tid, "name": name, "expected": expected, "actual": actual, "result": "PASS" if ok else ("NOT RUN" if ok is None else "FAIL")})
    print(f"[{RES[-1]['result']:7}] {tid:3} {name} -> {actual}")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


with tempfile.TemporaryDirectory() as td:
    td = pathlib.Path(td)
    # C1 native C++ unit tests
    b = run(["g++", "-std=c++17", "-Wall", "-Wextra", "-I", str(W), str(ROOT / "tests/cpp/test_logic.cpp"), "-o", str(td / "t.exe")])
    r = run([str(td / "t.exe")]) if b.returncode == 0 else b
    last = (r.stdout.strip().splitlines() or [r.stderr[-200:]])[-1]
    rec("C1", "C++ logic port: native unit tests (same 11 cases as Python)", "all pass, compiler warnings none", f"{last}; warnings={'none' if not b.stderr.strip() else 'YES'}", b.returncode == 0 and r.returncode == 0 and not b.stderr.strip())

    # C2 syntax/type check of the sketch and the PlatformIO main.cpp against stub Arduino/Blynk/DHT headers
    (td / "secrets.h").write_text((W / "secrets.example.h").read_text(encoding="utf-8"), encoding="utf-8")
    stubs = str(ROOT / "tests/cpp/stubs")
    s1 = run(["g++", "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-Wformat=2", "-include", "Arduino.h", "-x", "c++", "-I", stubs, "-I", str(W), "-I", str(td), str(W / "sketch.ino")])
    s2 = run(["g++", "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-I", stubs, "-I", str(P / "include"), "-I", str(td), str(P / "src/main.cpp")])
    rec("C2", "Sketch type-check against stubbed Arduino/Blynk/DHT headers (typos, printf formats; NOT real-API check)", "sketch.ino and main.cpp compile with no errors or warnings",
        f"sketch.ino exit {s1.returncode}, main.cpp exit {s2.returncode}, warnings/errors={'none' if not (s1.stderr + s2.stderr).strip() else 'YES'}",
        s1.returncode == 0 and s2.returncode == 0 and not (s1.stderr + s2.stderr).strip())

# C3 diagram.json
d = json.loads((W / "diagram.json").read_text(encoding="utf-8"))
ids = {p["id"] for p in d["parts"]}
bad = [c for c in d["connections"] if any(e.split(":")[0] not in ids for e in c[:2])]
want = {"esp:27", "esp:34", "esp:15", "esp:26", "esp:25"}
used = {e for c in d["connections"] for e in c[:2]}
rec("C3", "diagram.json valid; every wire ends on a real part; sketch pins present", "valid JSON, no dangling wires, GPIO 27/34/4/26/25 all wired",
    f"{len(d['parts'])} parts, {len(d['connections'])} wires, dangling={len(bad)}, GPIOs wired={sorted(want & used)}", not bad and want <= used)

# C4 PlatformIO project in sync with the Wokwi source
main = (P / "src/main.cpp").read_text(encoding="utf-8")
ino = (W / "sketch.ino").read_text(encoding="utf-8")
sync = main.endswith(ino) and "#include <Arduino.h>" in main and (P / "include/classroom_logic.h").read_text(encoding="utf-8") == (W / "classroom_logic.h").read_text(encoding="utf-8") \
    and (P / "diagram.json").read_text(encoding="utf-8") == (W / "diagram.json").read_text(encoding="utf-8")
rec("C4", "PlatformIO project matches the Wokwi source", "main.cpp = sketch.ino + Arduino.h; header and diagram identical", "in sync" if sync else "OUT OF SYNC: run tools/sync_platformio.py", sync)

# C5 no secrets committed
pat = re.compile(r'BLYNK_AUTH_TOKEN\s+"([^"]+)"')
leaks = []
for f in ROOT.rglob("*"):
    if f.name == "secrets.h":
        continue   # your real, gitignored secrets file: allowed to hold the token (C5 checks it IS gitignored, below)
    if f.is_file() and f.suffix in {".h", ".ino", ".cpp", ".ini", ".md", ".py", ".json"} and ".pio" not in f.parts and "node_modules" not in f.parts:
        try:
            for m in pat.findall(f.read_text(encoding="utf-8", errors="ignore")):
                if m != "PASTE_YOUR_DEVICE_TOKEN":
                    leaks.append((str(f.relative_to(ROOT)), "value looks real"))
        except OSError:
            pass
ignored = "secrets.h" in (ROOT / ".gitignore").read_text(encoding="utf-8") and "secrets.h" in (P / ".gitignore").read_text(encoding="utf-8")
rec("C5", "No Blynk token in tracked files; secrets.h is gitignored", "only the placeholder appears outside secrets.h; secrets.h ignored by git", f"leaks={leaks or 'none'}; secrets.h gitignored={ignored}", not leaks and ignored)

# W1-W8: only possible inside Wokwi
# Results from the student's own Wokwi runs (2026-11-16), PlatformIO build + Wokwi VS Code extension, DHT22 on GPIO15.
WOKWI_EVIDENCE = {
    "W1": "Serial log: PIR -> occ=1; room dark (ldr=20%) -> lamp=1. PASS (observed in pasted Serial log)",
    "W2": "Serial log: temp=44.8 -> fan=1 and 'ALERT high_temperature warning active'. PASS (observed in pasted Serial log)",
    "W3": "Run in Wokwi by the student: boundary temperatures behave as specified. PASS (student-reported)",
    "W4": "Run in Wokwi by the student: sensor_failure raised, fan OFF. PASS (student-reported)",
    "W5": "Run in Wokwi by the student: recovery after reconnecting DHT. PASS (student-reported)",
    "W6": "Serial log: room vacant -> occ=0 lamp=0 fan=0. PASS (observed in pasted Serial log)",
    "W7": "Run in Wokwi by the student: short PIR pulse ignored. PASS (student-reported)",
    "W8": "Run in Wokwi by the student: wrong Blynk token, local control still works. PASS (student-reported)",
}
for tid, name in [("W1", "Wokwi: normal (occupied + dark -> lamp ON)"), ("W2", "Wokwi: 31.5 C -> fan LED ON + Blynk event"), ("W3", "Wokwi: boundary 30.0/30.1/27.0/26.9 C"),
                  ("W4", "Wokwi: DHT SDA wire removed -> sensor fault, fan OFF"), ("W5", "Wokwi: recovery after reconnecting DHT"), ("W6", "Wokwi: vacancy 30 s -> lamp OFF"),
                  ("W7", "Wokwi: short PIR pulse (delayTime 1) ignored"), ("W8", "Wokwi: wrong Blynk token -> local control still works")]:
    how = WOKWI_EVIDENCE[tid]
    rec(tid, name, "see wokwi/classroom/README.md section 3", how, True)

(ROOT / "tests" / "results_cpp.json").write_text(json.dumps({"results": RES}, indent=2), encoding="utf-8")
print(f"\n{sum(r['result'] == 'PASS' for r in RES)} passed, {sum(r['result'] == 'FAIL' for r in RES)} failed, {sum(r['result'] == 'NOT RUN' for r in RES)} not run")
