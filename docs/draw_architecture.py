"""Draws docs/architecture.png: two lanes. Run from project root: python docs/draw_architecture.py
Lane 1 (module UI):   Wokwi ESP32 -> Blynk Cloud.
Lane 2 (platform):    Python device simulators -> Mosquitto -> Node-RED -> SQLite + HTML dashboard.
The lanes are NOT connected (Wokwi cannot reach localhost); both implement the same classroom rules.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

K = "#223"
fig, ax = plt.subplots(figsize=(9.2, 5.4), dpi=160)
ax.set_xlim(0, 100); ax.set_ylim(0, 60); ax.axis("off")


def box(x, y, w, h, t, fc):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=K, lw=1.2))
    ax.text(x + w / 2, y + h / 2, t, ha="center", va="center", fontsize=7.4)


def arr(x1, y1, x2, y2, ls="-"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", lw=1.3, color=K, ls=ls))


ax.text(50, 58, "CHRIST Smart Campus prototype: two lanes, isolated lab laptop, all data simulated", ha="center", fontsize=8.6, weight="bold")

# Lane 1: module dashboard
ax.text(1, 52, "LANE 1  Classroom module UI", fontsize=7.6, weight="bold", color="#1f5fbf")
box(1, 38, 26, 12, "Wokwi simulated ESP32\nC++ firmware: PIR, LDR, DHT22,\nlocal logic (classroom_logic.h)\nPlatformIO = fallback build", "#d9ecff")
box(40, 38, 22, 12, "Blynk Cloud\nmodule dashboard,\ndatastreams V0..V6,\nevents", "#ffe3cc")
arr(27.5, 44, 40, 44); ax.text(33.7, 46.3, "Wi-Fi (Wokwi-GUEST)", fontsize=6.6, ha="center", color=K)
box(72, 38, 26, 12, "Browser / phone\nBlynk dashboard\n(gauges, LEDs, status,\nevent notifications)", "#e8e8e8")
arr(62.5, 44, 72, 44)

# separator
ax.plot([1, 99], [33, 33], color="#999", lw=0.8, ls="--")
ax.text(50, 34.6, "no link between lanes (Wokwi cannot reach localhost); both implement the same classroom rules", fontsize=6.6, ha="center", color="#a3262a")

# Lane 2: platform
ax.text(1, 29, "LANE 2  Shared platform (validated MQTT contract)", fontsize=7.6, weight="bold", color="#1f5fbf")
box(1, 7, 20, 18, "Python device\nsimulators\nclassroom_sim.py\ncampus_sim.py\n(all 6 modules,\nlabelled SIMULATED)", "#eadcf8")
box(30, 9, 18, 14, "Mosquitto\nMQTT broker\n127.0.0.1:1883\nQoS 1, last will", "#fff1c9")
box(57, 9, 20, 14, "Node-RED\nvalidate (FR-02)\nroute, alerts,\nstale detection,\nHTTP API", "#dff3e8")
box(87, 15, 12, 12, "SQLite\nreadings, latest,\nalerts, rejects", "#f3dcdc")
box(87, 1, 12, 11, "HTML\ndashboard\n/campus", "#e8e8e8")
arr(21.5, 16, 30, 16); arr(48.5, 16, 57, 16); arr(77.5, 18, 87, 21); arr(87, 8, 77.5, 12)
ax.text(25.7, 18.4, "MQTT", fontsize=6.6, ha="center"); ax.text(52.8, 18.4, "subscribe", fontsize=6.6, ha="center")
ax.text(82, 6, "poll 2 s", fontsize=6.4, ha="center")
plt.savefig("docs/architecture.png", bbox_inches="tight", facecolor="white")
print("ok")
