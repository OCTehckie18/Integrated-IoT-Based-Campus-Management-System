"""Builds wokwi/classroom/sketch_wokwi_web.ino: ONE file for the Wokwi web editor (sketch + classroom_logic.h inlined,
secrets as clearly marked placeholders). Paste it into the web editor's sketch.ino. Source of truth stays sketch.ino."""
import re, pathlib
d = pathlib.Path(__file__).resolve().parent.parent / "wokwi" / "classroom"
sk = (d / "sketch.ino").read_text(encoding="utf-8")
hd = (d / "classroom_logic.h").read_text(encoding="utf-8").replace("#pragma once\n", "")
sec = (d / "secrets.example.h").read_text(encoding="utf-8")
sec = "\n".join(l for l in sec.splitlines() if l.startswith("#define"))
block = ("// ===== EDIT THESE THREE LINES (Blynk Console > Devices > your device > Firmware Configuration) =====\n" + sec +
         "\n// ===== inlined classroom_logic.h (in Wokwi web you can instead add it as a separate file) =====\n")
# Blynk macros must precede the Blynk includes, so secrets go first; the logic header goes where it was included.
sk = re.sub(r'#include "secrets\.h".*\n', block.split("// ===== inlined")[0], sk, count=1)
sk = re.sub(r'#include "classroom_logic\.h"\n', "// ===== inlined classroom_logic.h =====\n" + hd + "\n", sk, count=1)
out = d / "sketch_wokwi_web.ino"
out.write_text(sk, encoding="utf-8")
print("wrote", out, len(sk.splitlines()), "lines")
