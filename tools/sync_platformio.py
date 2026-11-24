"""Keeps the PlatformIO project in step with the Wokwi project (wokwi/classroom is the single source of truth).
  sketch.ino          -> platformio/classroom/src/main.cpp   (adds #include <Arduino.h>, which the Arduino IDE does implicitly)
  classroom_logic.h   -> platformio/classroom/include/
  diagram.json, secrets.example.h -> copied alongside
Run from the project root:  python tools/sync_platformio.py
"""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "wokwi" / "classroom"
DST = ROOT / "platformio" / "classroom"
(DST / "src").mkdir(parents=True, exist_ok=True)
(DST / "include").mkdir(parents=True, exist_ok=True)

ino = (SRC / "sketch.ino").read_text(encoding="utf-8")
(DST / "src" / "main.cpp").write_text("// GENERATED from wokwi/classroom/sketch.ino by tools/sync_platformio.py - edit the .ino instead.\n"
                                      "#include <Arduino.h>\n" + ino, encoding="utf-8")
shutil.copy(SRC / "classroom_logic.h", DST / "include" / "classroom_logic.h")
shutil.copy(SRC / "secrets.example.h", DST / "include" / "secrets.example.h")
shutil.copy(SRC / "diagram.json", DST / "diagram.json")
print("synced ->", DST)
