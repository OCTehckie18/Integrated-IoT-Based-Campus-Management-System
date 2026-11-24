// Native (PC) unit tests for classroom_logic.h - same cases as simulator/test_logic.py.
// Build: g++ -std=c++17 -Wall -Wextra -I wokwi/classroom tests/cpp/test_logic.cpp -o test_logic && ./test_logic
#include <cmath>
#include <cstdio>
#include <cstring>
#include "classroom_logic.h"
using namespace classroom;

static int failures = 0, passed = 0;
#define CHECK(cond) do { if (!(cond)) { std::printf("  FAIL line %d: %s\n", __LINE__, #cond); ++failures; return; } } while (0)

// Advance `seconds` one-second ticks starting at second `start`; returns all alert events seen.
struct Seen { bool active[2] = {false, false}; bool cleared[2] = {false, false}; };   // [0]=sensor_failure [1]=high_temperature
static uint32_t run(Controller &c, int seconds, bool pir, float light, uint32_t start, Seen *s = nullptr) {
  for (int t = (int)start; t < (int)start + seconds; ++t) {
    AlertEvent ev[2]; int n = c.step((uint32_t)t * 1000UL, pir, light, ev);
    for (int i = 0; i < n && s; ++i) {
      int k = std::strcmp(ev[i].type, "sensor_failure") == 0 ? 0 : 1;
      (ev[i].active ? s->active : s->cleared)[k] = true;
    }
  }
  return start + seconds;
}
#define TEST(name) static void name(); static struct R_##name { R_##name() { reg(#name, name); } } r_##name; static void name()
typedef void (*Fn)(); static Fn fns[32]; static const char *names[32]; static int nf = 0;
static void reg(const char *n, Fn f) { names[nf] = n; fns[nf++] = f; }

TEST(m1_normal) { Controller c; c.updateTemp(25.0f); run(c, 3, true, 10, 0); CHECK(c.occupied && c.lightOn && !c.fanOn); }
TEST(daylight_no_light) { Controller c; c.updateTemp(25.0f); run(c, 3, true, 80, 0); CHECK(c.occupied && !c.lightOn); }
TEST(false_trigger_ignored) {
  Controller c; c.updateTemp(25.0f); AlertEvent ev[2];
  c.step(0, true, 10, ev); c.step(1000, false, 10, ev);
  CHECK(!c.occupied && !c.lightOn);
}
TEST(m2_fan_on_and_alert) { Controller c; c.updateTemp(31.0f); Seen s; run(c, 3, true, 10, 0, &s); CHECK(c.fanOn && s.active[1]); }
TEST(m3_boundaries) {
  Controller c; uint32_t t = 0;
  const float temps[] = {29, 30.0f, 30.1f, 29, 27.0f, 26.9f, 28};
  const bool want[]   = {false, false, true, true, true, false, false};
  for (int i = 0; i < 7; ++i) { c.updateTemp(temps[i]); t = run(c, 2, true, 80, t); CHECK(c.fanOn == want[i]); }
}
TEST(m4_sensor_failure_fail_safe) {
  Controller c; c.updateTemp(31.0f); run(c, 3, true, 10, 0); CHECK(c.fanOn);
  c.updateTemp(0, false); c.updateTemp(0, false); CHECK(!c.sensorFault);   // 2 bad reads tolerated
  c.updateTemp(0, false);                                                   // 3rd
  Seen s; run(c, 1, true, 10, 3, &s);
  CHECK(c.sensorFault && !c.fanOn && !c.tempKnown && s.active[0]);
}
TEST(dht_out_of_range_counts_as_failure) {
  Controller c; c.updateTemp(-40.0f); c.updateTemp(125.0f); c.updateTemp(std::nanf("")); CHECK(c.sensorFault);
}
TEST(m5_recovery) {
  Controller c; for (int i = 0; i < 3; ++i) c.updateTemp(0, false);
  run(c, 1, true, 10, 0); c.updateTemp(24.0f); Seen s; run(c, 1, true, 10, 1, &s);
  CHECK(!c.sensorFault && s.cleared[0]);
}
TEST(m6_vacancy_30s) {
  Controller c; c.updateTemp(25.0f); uint32_t t = run(c, 3, true, 10, 0);   // last confirmed motion at t=2 s
  run(c, 29, false, 10, t); CHECK(c.lightOn);                                // t=3..31: 29 s since motion
  run(c, 1, false, 10, t + 29); CHECK(!c.occupied && !c.lightOn);            // t=32: 30 s since motion
}
TEST(light_hysteresis_no_flicker) {
  Controller c; c.updateTemp(25.0f); run(c, 3, true, 10, 0); CHECK(c.lightOn);
  run(c, 3, true, 35, 3); CHECK(c.lightOn);          // our own lamp lifts the LDR to 35 %: stays ON
  run(c, 1, true, 45, 6); CHECK(!c.lightOn);         // genuinely bright: OFF
}
TEST(stationary_occupant_limitation) {
  Controller c; c.updateTemp(25.0f); uint32_t t = run(c, 3, true, 10, 0); run(c, 35, false, 10, t); CHECK(!c.occupied);
}

int main() {
  for (int i = 0; i < nf; ++i) {
    int before = failures; fns[i]();
    if (failures == before) { ++passed; std::printf("PASS %s\n", names[i]); } else std::printf("FAIL %s\n", names[i]);
  }
  std::printf("%d tests passed, %d failed\n", passed, failures);
  return failures ? 1 : 0;
}
