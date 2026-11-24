# Classroom module in Wokwi + Blynk Cloud (PlatformIO as fallback)

What this is: the classroom ESP32 (`CLASS-A-ESP32-01`) running in the **Wokwi simulator**, mirroring its state to a **Blynk Cloud** dashboard.
Everything is **simulated**: the PIR, light and temperature are set by clicking parts in Wokwi. Local control (`classroom_logic.h`) keeps working without Wi-Fi.

**Status honesty.** I could not run Wokwi or Blynk myself. What was verified on a PC: `classroom_logic.h` passes 11 native unit tests (`tests/cpp/test_logic.cpp`), `diagram.json` is valid JSON with every wire pointing at a real part, and `sketch.ino` type-checks against stubbed Arduino/Blynk/DHT headers (catches typos and printf-format errors, **not** real-API mismatches). Everything marked VERIFY below must be confirmed in Wokwi.

## Relation to the Node-RED platform
This Wokwi/Blynk path is the **module's own dashboard**. It does not publish to Mosquitto (Wokwi cannot reach `localhost`). The shared Node-RED platform is fed by the Python simulators, which implement the same rules. The older MQTT firmware in `firmware/classroom_esp32/` is the variant that would feed Node-RED from real hardware on the lab network.

## 1. Blynk Cloud setup (Blynk Console, web)
1. Create a **Template**: hardware ESP32, connection Wi-Fi. Name it e.g. `CHRIST Classroom`. Note the **Template ID** and **Template Name**.
2. Add **datastreams** (Virtual Pin):

| Pin | Name | Type | Unit | Range |
|---|---|---|---|---|
| V0 | temperature | Double | C | -10..60 |
| V1 | light_level | Double | % | 0..100 |
| V2 | occupancy | Integer | - | 0..1 |
| V3 | lamp | Integer | - | 0..1 |
| V4 | fan | Integer | - | 0..1 |
| V5 | status | String | - | - |
| V6 | data_source | String | - | - |

3. Add **events** with the codes `high_temperature` and `sensor_failure` (the sketch calls `Blynk.logEvent` with exactly these codes).
4. Build the **web dashboard**: Gauge on V0, Gauge on V1, LED widgets on V2/V3/V4 (or Switch, read-only), Label on V5 and V6.
5. Create a **Device** from the template. Copy its **Auth Token** (a secret).

## 2. Wokwi project (web: https://wokwi.com)
1. New project -> ESP32 -> Arduino. Delete the default parts and sketch.
2. Replace `sketch.ino` and `diagram.json` with the ones in this folder; add the files `classroom_logic.h` and `libraries.txt` (Wokwi: "new file").
3. Add `secrets.h` (copy of `secrets.example.h`) with **your** Blynk Template ID/Name/Auth Token. Wi-Fi is `Wokwi-GUEST` with an empty password.
4. Start the simulation. The Serial Monitor shows one line per second, and `[...] Ready` / connection messages from Blynk.
5. VERIFY: ESP32 pin names in `diagram.json` (`esp:27`, `esp:34`, `esp:15`, `esp:26`, `esp:25`, `esp:3V3`, `esp:GND.1`). The Wokwi docs do not list them; if a wire fails to attach, hover over the pin in the editor and use the name shown. Part positions in `diagram.json` are approximate: drag parts if they overlap.

**Never share the project publicly with the real token inside.** If you do, regenerate the token in Blynk Console.

## 3. Test procedure (record screenshots as evidence)
| ID | Do in Wokwi | Expect (Serial Monitor + Blynk + LEDs) |
|---|---|---|
| W1 normal | LDR lux 500 (default); click PIR -> *Simulate Motion*. Then set LDR lux to 10 | Occupancy 1. Bright: lamp OFF. Dark: green LED (lamp) ON |
| W2 threshold | DHT22 temperature 31.5 | Blue LED (fan) ON, `ALERT high_temperature`, Blynk event, V5 `HIGH TEMPERATURE` |
| W3 boundary | 30.0 / 30.1 / 27.0 / 26.9 in that order starting from fan ON | Fan changes only above 30 and below 27 |
| W4 sensor disconnect | **Before starting**, delete the DHT SDA wire; start | After ~3 reads: `ALERT sensor_failure`, fan OFF, V5 `SENSOR FAULT`, no temperature pushed |
| W5 recovery | Reconnect the wire, restart; temperature 24 | Fault clears, status `OK` |
| W6 vacancy | Occupied + dark, then stop triggering the PIR | About 30 s after the last motion: lamp OFF (note: PIR OUT stays high 5 s per trigger) |
| W7 false trigger | Single quick *Simulate Motion* in a vacant room | PIR high for the 5 s `delayTime` counts as motion in this simulator, so set the part attribute `delayTime` to 1 to reproduce a short pulse; document what you saw |
| W8 cloud loss | Stop and start the sim with the token deliberately wrong | Local control (LEDs) still works; Serial shows `blynk=0` |

Evidence to capture: Wokwi canvas (running), Serial Monitor, Blynk dashboard, Blynk event notification, and the `diagram.json` / `sketch.ino` views (these are rendered for the report by `docs/make_code_images.py`).

## 4. PlatformIO fallback (if Wokwi does not work)
`platformio/classroom/` is the same code as a PlatformIO project (`src/main.cpp` is generated from `sketch.ino` by `python tools/sync_platformio.py`).
1. Install VS Code + the PlatformIO extension (and the Wokwi extension if you still want to simulate).
2. Copy `include/secrets.example.h` to `include/secrets.h` and fill in your values.
3. `pio run` (build). VERIFY the library versions in `platformio.ini` resolve.
4. Simulate: open the folder in VS Code, F1 -> **Wokwi: Start Simulator** (uses `wokwi.toml` + `diagram.json`; Wokwi does not compile, build first).
5. On a real ESP32 later: `pio run -t upload`, then see `docs/phase8_validation.md` safe power-up checklist and re-check the pin map and LDR calibration.

## Differences from the real build
- Fan: a blue LED stands in for the fan command; the real circuit uses a transistor, flyback diode and its own supply (`docs/circuit_diagram.png`).
- PIR powered from 3V3 in the simulator (real HC-SR501 is 5 V with ~3.3 V output; verify). PIR warm-up shortened to 5 s (real: ~60 s).
- Wokwi does not model the lamp lighting the LDR, so the light hysteresis is demonstrated only by the unit tests.
- LDR calibration constants (`LDR_RAW_DARK 3600`, `LDR_RAW_BRIGHT 1000`) are derived from the Wokwi part's formula, not measured: VERIFY in the Serial Monitor.
