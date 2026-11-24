"""Draws docs/circuit_diagram.png: planned wiring for the classroom module.
PLANNED ONLY: never built or tested. Pin numbers are the assumptions from docs/phase1_design.md.
Run from project root: python docs/draw_circuit.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, Polygon, Circle

K = "#1b2430"
fig, ax = plt.subplots(figsize=(10, 7.6), dpi=150)
ax.set_xlim(0, 100); ax.set_ylim(-4, 76); ax.axis("off")


def line(pts, c=K, lw=1.4):
    ax.plot([p[0] for p in pts], [p[1] for p in pts], color=c, lw=lw, solid_capstyle="round", solid_joinstyle="round")

def txt(x, y, s, fs=7.5, ha="left", c=K, **k):
    ax.text(x, y, s, fontsize=fs, ha=ha, va="center", color=c, **k)

def dot(x, y):
    ax.add_patch(Circle((x, y), 0.5, color=K, zorder=5))

def box(x0, y0, x1, y1, fc="white", lw=1.2):
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=fc, ec=K, lw=lw, zorder=3))

def hres(x, y, w, label):
    box(x, y - 1.2, x + w, y + 1.2); txt(x + w / 2, y + 2.8, label, 7, "center")

def vres(x, y0, y1):
    box(x - 1.2, y0, x + 1.2, y1)

def gnd(x, y):
    line([(x, y), (x, y - 1.2)]); line([(x - 2, y - 1.2), (x + 2, y - 1.2)])
    line([(x - 1.2, y - 2.0), (x + 1.2, y - 2.0)]); line([(x - 0.5, y - 2.8), (x + 0.5, y - 2.8)])


txt(50, 74.5, "Classroom module - planned wiring (NOT built, NOT tested)", 11, "center", weight="bold")
txt(50, 71.5, "Pin numbers are assumptions: verify against your board's pinout before wiring", 8, "center", c="#a3262a")

# ESP32
ax.add_patch(FancyBboxPatch((3, 4), 21, 60, boxstyle="round,pad=0.3,rounding_size=1", fc="#e8f1ff", ec=K, lw=1.6))
txt(13.5, 61, "ESP32 DevKit", 10, "center", weight="bold"); txt(13.5, 58.4, "3.3 V logic", 7.5, "center")
txt(13.5, 8, "3V3, 5V (VIN), GND:\nsee labels on parts", 7, "center", c="#445")
for name, yy in {"GPIO34 (ADC1, in-only)": 56, "GPIO15": 42, "GPIO27": 31, "GPIO26": 24, "GPIO25": 14}.items():
    txt(23, yy, name, 7.5, "right", weight="bold"); dot(24, yy)

# 1) LDR divider -> GPIO34
y = 56
line([(24, y), (46, y)]); dot(46, y)
box(44.8, 58.5, 47.2, 64.5, fc="#fff6d6"); txt(49, 61.5, "LDR", 7.5)
line([(46, 64.5), (46, 66.4)]); txt(46, 67.8, "3V3", 7.5, "center", weight="bold")
line([(46, y), (46, 54.5)]); vres(46, 49.5, 54.5); txt(48.4, 52, "10 kOhm", 7)
line([(46, 49.5), (46, 48.2)]); gnd(46, 48.2)
txt(56, 56, "light level: LDR + 10k divider (calibrate in Phase 3)", 7, c="#445")

# 2) DHT22 -> GPIO4
y = 42
line([(24, y), (62, y)]); dot(37, y)
line([(37, y), (37, 45)]); vres(37, 45, 50.5); txt(35, 47.8, "10 kOhm\npull-up", 7, "right")
line([(37, 50.5), (37, 52)]); txt(37, 53.4, "3V3", 7.5, "center", weight="bold")
box(62, 37.2, 80, 47.2, fc="#e9f7ee"); txt(71, 45, "DHT22", 8.5, "center", weight="bold")
txt(63, 42.4, "DATA <- GPIO15", 7); txt(63, 40.4, "VCC  -> 3V3", 7); txt(63, 38.6, "GND  -> GND", 7)

# 3) PIR -> GPIO27
y = 31
line([(24, y), (62, y)])
box(62, 26.5, 80, 35.5, fc="#e9f7ee"); txt(71, 33.5, "PIR HC-SR501", 8.5, "center", weight="bold")
txt(63, 31, "OUT -> GPIO27", 7); txt(63, 29.2, "VCC -> 5V (VIN)", 7); txt(63, 27.6, "GND -> GND", 7)
txt(82, 31, "check OUT is 3.3 V;\n~60 s warm-up", 6.8, c="#a3262a")

# 4) Lamp LED -> GPIO26
y = 24
line([(24, y), (33, y)]); hres(33, y, 7, "220 Ohm"); line([(40, y), (47, y)])
ax.add_patch(Polygon([(47, y - 1.8), (47, y + 1.8), (51, y)], fc="white", ec=K, lw=1.3, zorder=3)); line([(51, y - 1.8), (51, y + 1.8)])
line([(51, y), (53.5, y)]); gnd(53.5, y); txt(42, y + 4.6, "LED = \"classroom light\"", 7, c="#445")

# 5) Fan through transistor -> GPIO25
y = 14
line([(24, y), (31, y)]); hres(31, y, 7, "1 kOhm"); line([(38, y), (46, y)])
line([(46, y - 3), (46, y + 3)], lw=2.2)                                  # transistor base plate
line([(46, y + 1), (50, y + 3.8), (50, 19.5)]); line([(46, y - 1), (50, y - 3.8), (50, 7.0)])
ax.add_patch(Polygon([(47.6, y - 2.4), (49.6, y - 2.4), (49.0, y - 3.4)], fc=K, ec=K))   # emitter arrow
gnd(50, 7.0); txt(53, 9.4, "NPN / logic-level MOSFET", 6.8, c="#445"); txt(53, 7.6, "(check fan current rating)", 6.8, c="#445")
line([(50, 19.5), (58, 19.5)])
ax.add_patch(Circle((62, 19.5), 3.6, fc="#eee", ec=K, lw=1.4, zorder=3)); txt(62, 19.5, "FAN", 7, "center", weight="bold")
line([(65.6, 19.5), (84, 19.5)]); txt(85, 19.5, "+V ext.\n5-12 V\nsupply (+)", 7, weight="bold")
txt(62, 14.4, "low-voltage DC fan, own supply", 6.8, "center", c="#445")
line([(58, 19.5), (58, 24.5), (61, 24.5)]); line([(65, 24.5), (70, 24.5), (70, 19.5)])      # flyback diode across the fan
ax.add_patch(Polygon([(61, 23.2), (61, 25.8), (64.2, 24.5)], fc="white", ec=K, lw=1.3, zorder=3)); line([(64.6, 23.1), (64.6, 25.9)], lw=2)
txt(72, 24.5, "flyback diode\n(cathode to +V)", 6.8, c="#445")
dot(58, 19.5); dot(70, 19.5)

# Notes
box(3, -3.2, 97, 2.6, fc="#fff1c9", lw=1)
txt(5, 0.9, "Common ground: external supply (-) MUST connect to ESP32 GND.  Never power the fan from a GPIO.  ESP32 powered from USB only.", 6.8, weight="bold")
txt(5, -1.5, "No mains, no pump, no distribution board. Lab bench, low voltage only.", 7.2)
plt.savefig("docs/circuit_diagram.png", bbox_inches="tight", facecolor="white")
print("ok")
