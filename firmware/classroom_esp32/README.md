# Classroom ESP32 firmware, MQTT variant (future work, UNTESTED on hardware)

> The module firmware used for the project demo is now `wokwi/classroom/` (Wokwi + Blynk, PlatformIO fallback). This MQTT variant is what would feed the Node-RED platform from a real board on the lab network.

Port of the tested Python logic (`simulator/classroom_logic.py`). Nothing here has run on a board.

## Verify before trusting it
1. Pin numbers vs your board's pinout (GPIO34 is input-only, ADC1; GPIO25/26/27/4 are normally free).
2. PIR output voltage (HC-SR501 is 3.3 V on most modules; check yours) and its ~60 s warm-up.
3. LDR calibration constants `LDR_RAW_DARK` / `LDR_RAW_BRIGHT` (print raw values in Serial Monitor in the dark and in light).
4. Fan runs from its own supply through a transistor + flyback diode, never from a GPIO.
5. Library versions: PubSubClient 2.8, Adafruit DHT 1.4.x. `setBufferSize` exists in 2.8.

## Known gaps
- **QoS**: PubSubClient publishes at QoS 0 only; the spec wants QoS 1 for alerts/important telemetry. Swap in a library with QoS 1 publish (e.g. espMqttClient).
- **Time**: ISO timestamps need NTP. An isolated lab network has no internet, so point `NTP_HOST` at a server on the lab network (or a phone hotspot with internet). Without sync the firmware publishes nothing rather than a fake time.
- **Last will timestamp** is the time the will was set at connect, not the time of failure; the backend uses its own receive time.
- `"source":"hardware"` is only honest once it runs on a real board. Until then use the simulator, which says `"simulated"`.

## Setup
Copy `secrets.example.h` to `secrets.h` (gitignored) and fill in the lab Wi-Fi and broker IP. Open `classroom_esp32.ino` in Arduino IDE, board "ESP32 Dev Module".
