/*
 * CHRIST Smart Campus - classroom module firmware (ESP32, Arduino core)
 *
 * STATUS: UNTESTED ON HARDWARE. This is a line-for-line port of the logic in
 * simulator/classroom_logic.py (which IS unit-tested). Treat it as future work: pins, ADC
 * calibration and library versions below are ASSUMPTIONS that must be verified on a real board.
 *
 * Libraries (Library Manager): "PubSubClient" (Nick O'Leary), "DHT sensor library" (Adafruit)
 *                              + "Adafruit Unified Sensor".
 * Board: "ESP32 Dev Module".  Copy secrets.example.h -> secrets.h first.
 *
 * KNOWN LIMITATION: PubSubClient can only PUBLISH at QoS 0 (it can subscribe at QoS 1). The spec
 * asks for QoS 1 on important messages. Fix for a real build: use a library with QoS 1 publish
 * (e.g. espMqttClient) - the message building below stays the same.
 */
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>
#include "secrets.h"

// ---------- Identity (must match platform/build_flow.py REGISTRY) ----------
#define CAMPUS_ID   "CHRIST-DEMO"
#define MODULE_NAME "classroom"
#define BUILDING_ID "BLOCK-A"
#define ZONE_ID     "ROOM-204"
#define DEVICE_ID   "CLASS-A-ESP32-01"
#define SOURCE_TAG  "hardware"        // NOT "simulated": only set once this runs on a real board
#define TOPIC_BASE  "christ-smart-campus/v1/" MODULE_NAME "/" BUILDING_ID "/" DEVICE_ID

// ---------- Pin map (ASSUMPTION - verify against your board's pinout) ----------
const int PIN_PIR = 27;     // PIR output (HC-SR501 output is ~3.3 V; verify on your module)
const int PIN_LDR = 34;     // ADC1 pin (ADC2 is unusable while Wi-Fi is on); input-only
const int PIN_DHT = 4;      // DHT22 data (+ pull-up if bare sensor)
const int PIN_LIGHT = 26;   // LED = "classroom light" through 220 ohm
const int PIN_FAN = 25;     // -> transistor base via 1k (NEVER drive a fan straight from a GPIO)
const int PIN_STATUS = 2;   // on-board LED: on = MQTT connected

// ---------- Thresholds (same as classroom_logic.py) ----------
const float DARK_ON_PCT = 30.0, BRIGHT_OFF_PCT = 40.0;
const unsigned long VACANCY_MS = 30000UL;
const int PIR_CONFIRM = 2;                 // consecutive 1 Hz samples
const float FAN_ON_C = 30.0, FAN_OFF_C = 27.0;
const int DHT_FAIL_LIMIT = 3;
const float TEMP_MIN = -10.0, TEMP_MAX = 60.0;
const unsigned long PIR_WARMUP_MS = 60000UL;   // HC-SR501 needs ~1 min after power-up: ignore it until then
// LDR calibration: raw ADC (0..4095) in the dark and in bright light. PLACEHOLDERS - measure yours (Phase 3).
const int LDR_RAW_DARK = 3500, LDR_RAW_BRIGHT = 500;   // depends on divider orientation

// ---------- Timing ----------
const unsigned long TELEMETRY_MS = 10000UL, HEARTBEAT_MS = 45000UL, DHT_MS = 2000UL, TICK_MS = 1000UL;

DHT dht(PIN_DHT, DHT22);
WiFiClient net;
PubSubClient mqtt(net);

// ---------- Controller state ----------
int pirRun = 0;
unsigned long lastMotion = 0; bool haveMotion = false;
bool occupied = false, dark = false, lightOn = false, fanOn = false;
float temp = NAN; int dhtFails = 0; bool sensorFault = false, highTempAlert = false;
bool repFault = false, repHigh = false;          // last alert state reported
unsigned long tLast = 0, tTel = 0, tHb = 0, tDht = 0, tRetry = 0;
unsigned long retryDelay = 1000;                 // reconnect backoff, 1 s .. 30 s

// ---------- Helpers ----------
bool nowIso(char *out, size_t n) {               // UTC ISO 8601 with Z; false if clock not synced yet
  struct tm t;
  if (!getLocalTime(&t, 50) || t.tm_year < (2024 - 1900)) return false;
  strftime(out, n, "%Y-%m-%dT%H:%M:%SZ", &t);
  return true;
}

float readLightPct() {
  int raw = analogRead(PIN_LDR);
  float pct = 100.0f * (raw - LDR_RAW_DARK) / (float)(LDR_RAW_BRIGHT - LDR_RAW_DARK);
  return constrain(pct, 0.0f, 100.0f);
}

// Builds one contract-compliant JSON message. `value` is already formatted ("29.2", "true").
// `extra` is raw JSON fragment starting with a comma, or "".
bool publishMsg(const char *kind, const char *metric, const char *value, const char *unit,
                const char *status, const char *extra, bool retain) {
  char ts[24];
  if (!nowIso(ts, sizeof ts)) return false;      // never publish a made-up timestamp
  char topic[128], buf[480];
  snprintf(topic, sizeof topic, TOPIC_BASE "/%s", kind);
  snprintf(buf, sizeof buf,
    "{\"schema_version\":\"1.0\",\"campus_id\":\"" CAMPUS_ID "\",\"module\":\"" MODULE_NAME "\","
    "\"building_id\":\"" BUILDING_ID "\",\"zone_id\":\"" ZONE_ID "\",\"device_id\":\"" DEVICE_ID "\","
    "\"timestamp\":\"%s\",\"metric\":\"%s\",\"value\":%s,\"unit\":\"%s\",\"status\":\"%s\","
    "\"source\":\"" SOURCE_TAG "\"%s}", ts, metric, value, unit, status, extra);
  return mqtt.publish(topic, buf, retain);
}

void publishTelemetry(float lightPct) {
  char v[16];
  if (!isnan(temp)) {                            // a failed sensor publishes NO temperature
    snprintf(v, sizeof v, "%.1f", temp);
    publishMsg("telemetry", "temperature", v, "C", highTempAlert ? "warning" : "normal", "", false);
  }
  snprintf(v, sizeof v, "%.1f", lightPct);
  publishMsg("telemetry", "light_level", v, "pct", "normal", "", false);
  publishMsg("telemetry", "occupancy_detected", occupied ? "true" : "false", "bool", "normal", "", false);
}

void publishHeartbeat() {
  char extra[120];
  snprintf(extra, sizeof extra, ",\"light_on\":%s,\"fan_on\":%s,\"occupied\":%s,\"sensor_fault\":%s",
           lightOn ? "true" : "false", fanOn ? "true" : "false",
           occupied ? "true" : "false", sensorFault ? "true" : "false");
  publishMsg("status", "device_online", "true", "bool", "online", extra, true);   // retained
}

void publishAlert(const char *type, const char *severity, bool active, const char *metric,
                  const char *value, const char *unit) {
  char extra[100];
  snprintf(extra, sizeof extra, ",\"alert_type\":\"%s\",\"severity\":\"%s\",\"alert_state\":\"%s\"",
           type, severity, active ? "active" : "cleared");
  publishMsg("alerts", metric, value, unit, active ? "alert" : "normal", extra, false);
}

// ---------- Logic (port of ClassroomController) ----------
void updateTemp(float reading) {
  bool bad = isnan(reading) || reading < TEMP_MIN || reading > TEMP_MAX;
  if (bad) {
    if (++dhtFails >= DHT_FAIL_LIMIT) { temp = NAN; sensorFault = true; }
  } else { dhtFails = 0; temp = reading; sensorFault = false; }
}

bool stepLogic(unsigned long now, bool pir, float lightPct) {
  bool changed = false;
  bool o0 = occupied, l0 = lightOn, f0 = fanOn;
  pirRun = pir ? pirRun + 1 : 0;
  if (now > PIR_WARMUP_MS && pirRun >= PIR_CONFIRM) { lastMotion = now; haveMotion = true; }
  occupied = haveMotion && (now - lastMotion) < VACANCY_MS;
  if (lightPct < DARK_ON_PCT) dark = true; else if (lightPct > BRIGHT_OFF_PCT) dark = false;
  lightOn = occupied && dark;
  if (sensorFault || isnan(temp) || !occupied) fanOn = false;       // fail-safe OFF
  else if (temp > FAN_ON_C) fanOn = true;
  else if (temp < FAN_OFF_C) fanOn = false;                          // 27..30 C: keep previous state
  if (!isnan(temp)) { if (temp > FAN_ON_C) highTempAlert = true; else if (temp < FAN_OFF_C) highTempAlert = false; }
  digitalWrite(PIN_LIGHT, lightOn); digitalWrite(PIN_FAN, fanOn);
  changed = (o0 != occupied) || (l0 != lightOn) || (f0 != fanOn);

  char v[16];
  if (sensorFault != repFault) { repFault = sensorFault; publishAlert("sensor_failure", "critical", repFault, "device_online", repFault ? "false" : "true", "bool"); }
  if (highTempAlert != repHigh) { repHigh = highTempAlert; snprintf(v, sizeof v, "%.1f", isnan(temp) ? 0.0f : temp); publishAlert("high_temperature", "warning", repHigh, "temperature", v, "C"); }
  return changed;
}

// ---------- Connectivity (non-blocking, with backoff) ----------
void ensureConnected() {
  if (WiFi.status() != WL_CONNECTED) { digitalWrite(PIN_STATUS, LOW); return; }   // WiFi.begin auto-reconnects
  if (mqtt.connected()) return;
  digitalWrite(PIN_STATUS, LOW);
  if (millis() - tRetry < retryDelay) return;
  tRetry = millis();
  char ts[24] = "1970-01-01T00:00:00Z";
  nowIso(ts, sizeof ts);                          // NOTE: a will carries the time it was set, not the failure time
  char will[400];
  snprintf(will, sizeof will,
    "{\"schema_version\":\"1.0\",\"campus_id\":\"" CAMPUS_ID "\",\"module\":\"" MODULE_NAME "\","
    "\"building_id\":\"" BUILDING_ID "\",\"zone_id\":\"" ZONE_ID "\",\"device_id\":\"" DEVICE_ID "\","
    "\"timestamp\":\"%s\",\"metric\":\"device_online\",\"value\":false,\"unit\":\"bool\","
    "\"status\":\"offline\",\"source\":\"" SOURCE_TAG "\"}", ts);
  bool ok = (strlen(MQTT_USER) > 0)
    ? mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS, TOPIC_BASE "/status", 1, true, will)
    : mqtt.connect(DEVICE_ID, TOPIC_BASE "/status", 1, true, will);
  if (ok) { retryDelay = 1000; digitalWrite(PIN_STATUS, HIGH); publishHeartbeat(); tHb = millis(); }
  else retryDelay = min(retryDelay * 2, 30000UL);  // exponential backoff 1,2,4..30 s
}

void setup() {
  pinMode(PIN_LIGHT, OUTPUT); pinMode(PIN_FAN, OUTPUT); pinMode(PIN_STATUS, OUTPUT);
  digitalWrite(PIN_LIGHT, LOW); digitalWrite(PIN_FAN, LOW);          // outputs OFF before anything else
  pinMode(PIN_PIR, INPUT);
  Serial.begin(115200);
  dht.begin();
  WiFi.mode(WIFI_STA); WiFi.begin(WIFI_SSID, WIFI_PASS);
  configTime(0, 0, NTP_HOST);                    // UTC; needs a reachable NTP server (see README)
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);                       // default 256 B is too small for our JSON
  updateTemp(dht.readTemperature());
}

void loop() {
  ensureConnected();
  mqtt.loop();
  unsigned long now = millis();
  if (now - tDht >= DHT_MS) { tDht = now; updateTemp(dht.readTemperature()); }   // NaN on failure
  if (now - tLast >= TICK_MS) {
    tLast = now;
    float lp = readLightPct();
    bool changed = stepLogic(now, digitalRead(PIN_PIR) == HIGH, lp);
    Serial.printf("occ=%d light=%d fan=%d temp=%.1f ldr=%.0f%% fault=%d\n", occupied, lightOn, fanOn, temp, lp, sensorFault);
    if (mqtt.connected()) {
      if (changed || now - tTel >= TELEMETRY_MS) { publishTelemetry(lp); tTel = now; }
      if (changed || now - tHb >= HEARTBEAT_MS)  { publishHeartbeat(); tHb = now; }
    }
  }
}
