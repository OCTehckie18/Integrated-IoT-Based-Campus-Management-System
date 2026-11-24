/*
 * CHRIST Smart Campus - classroom module (ESP32 in Wokwi, dashboard on Blynk Cloud)
 * Device CLASS-A-ESP32-01, BLOCK-A / ROOM-204.   ALL VALUES COME FROM THE SIMULATOR: nothing here is real hardware.
 *
 * Local control (classroom_logic.h, tested on a PC) keeps working even if Wi-Fi or Blynk is down;
 * the cloud connection only mirrors the state to Blynk and sends events.
 *
 * Blynk datastreams (create these in the Blynk template, see README):
 *   V0 temperature  (double, C)        V3 lamp ON/OFF  (integer 0/1)
 *   V1 light level  (double, %)        V4 fan ON/OFF   (integer 0/1)
 *   V2 occupancy    (integer 0/1)      V5 status text  (string)      V6 data-source label (string)
 * Blynk events (create in the template): high_temperature, sensor_failure
 *
 * Libraries: "Blynk" (blynkkk) and "DHT sensor library for ESPx" (beegee-tokyo, class DHTesp).
 * Copy secrets.example.h to secrets.h and fill in YOUR Blynk values. Never share a project containing the real token.
 */
// ===== EDIT THESE THREE LINES (Blynk Console > Devices > your device > Firmware Configuration) =====
#define BLYNK_TEMPLATE_ID   "TMPLxxxxxxxx"            // from Blynk Console > Templates
#define BLYNK_TEMPLATE_NAME "CHRIST Classroom"
#define BLYNK_AUTH_TOKEN    "PASTE_YOUR_DEVICE_TOKEN"  // from Blynk Console > Devices (secret!)
#define WIFI_SSID "Wokwi-GUEST"                        // Wokwi's built-in simulated Wi-Fi (open, no password)
#define WIFI_PASS ""
#define BLYNK_PRINT Serial      // Blynk connection messages in the Serial Monitor
#include <WiFi.h>
#include <BlynkSimpleEsp32.h>
#include <DHTesp.h>
// ===== inlined classroom_logic.h =====
// classroom_logic.h - classroom control logic, header-only, NO Arduino dependencies.
// Same rules as simulator/classroom_logic.py (which is unit-tested); this C++ port is tested on the PC
// with tests/cpp/test_logic.cpp (same 11 tests). Used unchanged by the Wokwi sketch and PlatformIO.
//
//   occupied + dark          -> light ON
//   unoccupied 30 s straight -> light OFF
//   occupied + temp > 30 C   -> fan ON
//   temp < 27 C              -> fan OFF            (27..30 = hysteresis band: keep last state)
//   3 bad DHT reads in a row -> temperature unknown, fan OFF (fail-safe), alert
#include <stdint.h>

namespace classroom {

// ---- Thresholds (tunable) -----------------------------------------------------------------
const float DARK_ON_PCT = 30.0f;      // light_level below this  -> dark
const float BRIGHT_OFF_PCT = 40.0f;   // light_level above this  -> bright (30..40 keeps state)
const uint32_t VACANCY_MS = 30000UL;  // no motion this long     -> vacant
const int PIR_CONFIRM = 2;            // consecutive 1 Hz PIR-high samples = real motion (debounce)
const float FAN_ON_C = 30.0f;
const float FAN_OFF_C = 27.0f;
const int DHT_FAIL_LIMIT = 3;
const float TEMP_MIN = -10.0f, TEMP_MAX = 60.0f;   // outside this a reading is treated as bad

struct AlertEvent {            // one edge-triggered alert transition
  const char *type;            // "sensor_failure" | "high_temperature"
  const char *severity;        // "critical" | "warning"
  bool active;                 // true = raised, false = cleared
};

class Controller {
 public:
  bool occupied = false, dark = false, lightOn = false, fanOn = false;
  bool tempKnown = false;      // false until a valid reading, and again after a sensor failure
  float temp = 0.0f;
  bool sensorFault = false, highTempAlert = false;

  // Call after every DHT read (DHT22 needs >= 2 s between reads). readOk=false if the driver reported an error.
  void updateTemp(float reading, bool readOk = true) {
    bool bad = !readOk || reading != reading || reading < TEMP_MIN || reading > TEMP_MAX;   // x != x  <=> NaN
    if (bad) {
      if (++dhtFails_ >= DHT_FAIL_LIMIT) { tempKnown = false; sensorFault = true; }
    } else {
      dhtFails_ = 0; temp = reading; tempKnown = true; sensorFault = false;
    }
  }

  // Call once per second. `nowMs` is a millisecond clock (millis()). Fills `out` (room for 2); returns count.
  int step(uint32_t nowMs, bool pir, float lightPct, AlertEvent *out) {
    // 1) occupancy: debounce the PIR, then stay "occupied" for VACANCY_MS after the last confirmed motion
    pirRun_ = pir ? pirRun_ + 1 : 0;
    if (pirRun_ >= PIR_CONFIRM) { lastMotion_ = nowMs; haveMotion_ = true; }
    occupied = haveMotion_ && (uint32_t)(nowMs - lastMotion_) < VACANCY_MS;
    // 2) darkness with hysteresis
    if (lightPct < DARK_ON_PCT) dark = true; else if (lightPct > BRIGHT_OFF_PCT) dark = false;
    // 3) light
    lightOn = occupied && dark;
    // 4) fan: fail-safe OFF without a valid temperature or in an empty room
    if (sensorFault || !tempKnown || !occupied) fanOn = false;
    else if (temp > FAN_ON_C) fanOn = true;
    else if (temp < FAN_OFF_C) fanOn = false;
    // 5) alerts: compare with what was last REPORTED (updateTemp can flip sensorFault between steps)
    if (tempKnown) { if (temp > FAN_ON_C) highTempAlert = true; else if (temp < FAN_OFF_C) highTempAlert = false; }
    int n = 0;
    if (sensorFault != repFault_) { repFault_ = sensorFault; out[n++] = {"sensor_failure", "critical", repFault_}; }
    if (highTempAlert != repHigh_) { repHigh_ = highTempAlert; out[n++] = {"high_temperature", "warning", repHigh_}; }
    return n;
  }

 private:
  int pirRun_ = 0, dhtFails_ = 0;
  uint32_t lastMotion_ = 0;
  bool haveMotion_ = false, repFault_ = false, repHigh_ = false;
};

}  // namespace classroom


// ---------- Pin map (matches wokwi diagram.json; the real build is in docs/circuit_diagram.png) ----------
const int PIN_PIR = 27;     // PIR OUT
const int PIN_LDR = 34;     // photoresistor module AO (ADC1)
const int PIN_DHT = 15;     // DHT22 SDA
const int PIN_LAMP = 26;    // green LED = classroom light (via 220 ohm)
const int PIN_FAN = 25;     // blue LED = fan command (real build: transistor + low-voltage fan)

// ---------- Calibration / timing ----------
// Wokwi photoresistor module: AO FALLS as light increases. Derived from its datasheet formula
// (10 k divider, gamma 0.7, RL10 50 k) with VCC=3.3 V: ~5 lux -> raw ~3650, ~500 lux -> raw ~1000. VERIFY in Serial Monitor.
const int LDR_RAW_DARK = 3600, LDR_RAW_BRIGHT = 1000;
#ifndef PIR_WARMUP_MS
#define PIR_WARMUP_MS 5000UL    // simulator: short. A real HC-SR501 needs ~60000 ms after power-up.
#endif
// DHT22 minimum sample period is 2 s: read every 3 s so a sensor that rejects requests arriving even slightly early still answers.
const unsigned long TICK_MS = 1000UL, DHT_MS = 3000UL, BLYNK_MS = 5000UL, BLYNK_RETRY_MS = 10000UL;

DHTesp dht;
classroom::Controller ctl;
unsigned long tTick = 0, tDht = 0, tBlynk = 0, tBlynkTry = 0;

float readLightPct() {
  int raw = analogRead(PIN_LDR);                                           // 0..4095
  float pct = 100.0f * (raw - LDR_RAW_DARK) / (float)(LDR_RAW_BRIGHT - LDR_RAW_DARK);
  return constrain(pct, 0.0f, 100.0f);
}

void pushToBlynk(float lightPct) {
  if (!Blynk.connected()) return;
  if (ctl.tempKnown) Blynk.virtualWrite(V0, ctl.temp);                     // no fake value when the sensor failed
  Blynk.virtualWrite(V1, lightPct);
  Blynk.virtualWrite(V2, ctl.occupied ? 1 : 0);
  Blynk.virtualWrite(V3, ctl.lightOn ? 1 : 0);
  Blynk.virtualWrite(V4, ctl.fanOn ? 1 : 0);
  Blynk.virtualWrite(V5, ctl.sensorFault ? "SENSOR FAULT" : (ctl.highTempAlert ? "HIGH TEMPERATURE" : "OK"));
}

BLYNK_CONNECTED() {                                                        // runs on every (re)connect
  Blynk.virtualWrite(V6, "SIMULATED (Wokwi)");
  // Alerts raised BEFORE the cloud link came up were only printed: report what is still active now.
  if (ctl.sensorFault) Blynk.logEvent("sensor_failure", "Temperature sensor failed");
  if (ctl.highTempAlert) Blynk.logEvent("high_temperature", "Classroom above 30 C");
}

void setup() {
  pinMode(PIN_LAMP, OUTPUT); pinMode(PIN_FAN, OUTPUT);
  digitalWrite(PIN_LAMP, LOW); digitalWrite(PIN_FAN, LOW);                 // outputs OFF before anything else
  pinMode(PIN_PIR, INPUT);
  Serial.begin(115200);
  dht.setup(PIN_DHT, DHTesp::DHT22);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);                                        // Wokwi: "Wokwi-GUEST", empty password
  Blynk.config(BLYNK_AUTH_TOKEN);                                          // non-blocking: we connect later in loop()
  // No DHT read here: the sensor needs ~1-2 s after power-up, and a failed first read would count towards the 3-strike fail-safe.
  Serial.printf("DHT22 on GPIO%d, first read at ~%lu ms\n", PIN_DHT, DHT_MS);
}

void loop() {
  unsigned long now = millis();

  // ---- cloud link: never allowed to block the control loop for long ----
  if (WiFi.status() == WL_CONNECTED) {
    if (Blynk.connected()) Blynk.run();
    else if (now - tBlynkTry >= BLYNK_RETRY_MS) { tBlynkTry = now; Blynk.connect(3000); }   // 3 s attempt
  }

  // ---- sensor acquisition ----
  if (now - tDht >= DHT_MS) {                                              // DHT22 needs >= 2 s between reads (we use 3 s)
    tDht = now;
    TempAndHumidity d = dht.getTempAndHumidity();
    bool ok = dht.getStatus() == DHTesp::ERROR_NONE;
    ctl.updateTemp(d.temperature, ok);
    Serial.printf("DHT read: status=%s temp=%.1f hum=%.1f\n", dht.getStatusString(), d.temperature, d.humidity);   // diagnostics
  }

  // ---- control tick (1 Hz) ----
  if (now - tTick >= TICK_MS) {
    tTick = now;
    float lightPct = readLightPct();
    bool pir = digitalRead(PIN_PIR) == HIGH && now > PIR_WARMUP_MS;        // ignore PIR while it warms up
    bool occ0 = ctl.occupied, lamp0 = ctl.lightOn, fan0 = ctl.fanOn;
    classroom::AlertEvent ev[2];
    int n = ctl.step(now, pir, lightPct, ev);
    digitalWrite(PIN_LAMP, ctl.lightOn); digitalWrite(PIN_FAN, ctl.fanOn);

    Serial.printf("occ=%d lamp=%d fan=%d temp=%s%.1f ldr=%.0f%% fault=%d blynk=%d\n", ctl.occupied, ctl.lightOn, ctl.fanOn,
                  ctl.tempKnown ? "" : "?", ctl.temp, lightPct, ctl.sensorFault, Blynk.connected());
    for (int i = 0; i < n; ++i) {
      Serial.printf("ALERT %s %s %s\n", ev[i].type, ev[i].severity, ev[i].active ? "active" : "cleared");
      if (ev[i].active && Blynk.connected())
        Blynk.logEvent(ev[i].type, ev[i].type[0] == 's' ? "Temperature sensor failed" : "Classroom above 30 C");
    }
    bool changed = (occ0 != ctl.occupied) || (lamp0 != ctl.lightOn) || (fan0 != ctl.fanOn) || n > 0;
    if (changed || now - tBlynk >= BLYNK_MS) { tBlynk = now; pushToBlynk(lightPct); }   // immediate on change, else every 5 s
  }
}
