// classroom_logic.h - classroom control logic, header-only, NO Arduino dependencies.
// Same rules as simulator/classroom_logic.py (which is unit-tested); this C++ port is tested on the PC
// with tests/cpp/test_logic.cpp (same 11 tests). Used unchanged by the Wokwi sketch and PlatformIO.
//
//   occupied + dark          -> light ON
//   unoccupied 30 s straight -> light OFF
//   occupied + temp > 30 C   -> fan ON
//   temp < 27 C              -> fan OFF            (27..30 = hysteresis band: keep last state)
//   3 bad DHT reads in a row -> temperature unknown, fan OFF (fail-safe), alert
#pragma once
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
