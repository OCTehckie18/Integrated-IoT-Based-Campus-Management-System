"""Renders the Wokwi/Blynk/PlatformIO source files as syntax-highlighted PNG 'screenshots' for the report (docs/code/*.png).
These are rendered from the files in the repository, so they always match the code. REAL Wokwi/Blynk screenshots
(running simulation, dashboard) must be captured by hand: see wokwi/classroom/README.md.
Run from the project root: python docs/make_code_images.py
"""
import pathlib
import subprocess
import sys
import tempfile

from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import CppLexer, IniLexer, JsonLexer, TextLexer

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "code"
OUT.mkdir(exist_ok=True)
W = ROOT / "wokwi" / "classroom"


def render(name, text, lexer, first_line=1):
    fmt = ImageFormatter(font_name="Consolas", font_size=15, line_numbers=True, line_number_start=first_line,
                         style="default", image_pad=10, line_pad=2, line_number_bg="#f0f0f0", line_number_fg="#777777")
    (OUT / f"{name}.png").write_bytes(highlight(text, lexer, fmt))
    print("wrote", f"docs/code/{name}.png", f"({len(text.splitlines())} lines)")


lines = lambda p: p.read_text(encoding="utf-8").splitlines()
sk = lines(W / "sketch.ino")
render("diagram_json", (W / "diagram.json").read_text(encoding="utf-8"), JsonLexer())
render("sketch_1", "\n".join(sk[:63]), CppLexer(), 1)
render("sketch_2", "\n".join(sk[63:]), CppLexer(), 64)
render("classroom_logic_h", (W / "classroom_logic.h").read_text(encoding="utf-8"), CppLexer())
cfg = ["; ---- platformio/classroom/platformio.ini ----"] + lines(ROOT / "platformio/classroom/platformio.ini") + \
      ["", "; ---- platformio/classroom/wokwi.toml ----"] + lines(ROOT / "platformio/classroom/wokwi.toml") + \
      ["", "; ---- wokwi/classroom/libraries.txt ----"] + lines(W / "libraries.txt")
render("config_files", "\n".join(cfg), IniLexer())

# Real output of the native C++ unit tests (compiled and run now)
with tempfile.TemporaryDirectory() as td:
    exe = pathlib.Path(td) / "t.exe"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-I", str(W), str(ROOT / "tests/cpp/test_logic.cpp"), "-o", str(exe)], check=True)
    res = subprocess.run([str(exe)], capture_output=True, text=True)
    render("cpp_unit_tests", "$ g++ -std=c++17 -Wall -Wextra -I wokwi/classroom tests/cpp/test_logic.cpp\n$ ./test_logic\n" + res.stdout, TextLexer())
    sys.exit(res.returncode)
