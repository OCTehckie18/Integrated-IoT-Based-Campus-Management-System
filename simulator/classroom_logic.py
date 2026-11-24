"""Classroom local control logic (Phase 4).

Pure Python, no MQTT, no real clock: the caller passes `now` in seconds. This makes the
logic unit-testable AND portable: the same state machine is what the ESP32 firmware must run.

Rules (from the module spec):
  occupied + dark          -> light ON
  unoccupied 30 s straight -> light OFF
  occupied + temp > 30 C   -> fan ON
  temp < 27 C              -> fan OFF            (27..30 = hysteresis band: keep last state)
Safe behaviour on sensor error: 3 failed DHT reads in a row -> temperature unknown, fan OFF.
"""

# ---- Thresholds (all tunable; calibrate LDR in real hardware) -------------------------
DARK_ON_PCT = 30.0     # light_level below this  -> room is dark
BRIGHT_OFF_PCT = 40.0  # light_level above this  -> room is bright (hysteresis: 30..40 keeps state)
VACANCY_S = 30.0       # no motion this long     -> room is vacant
PIR_CONFIRM = 2        # consecutive PIR-high samples (1 Hz) needed to count as motion (debounce)
FAN_ON_C = 30.0
FAN_OFF_C = 27.0
DHT_FAIL_LIMIT = 3     # consecutive bad reads before declaring the sensor failed
TEMP_MIN, TEMP_MAX = -10.0, 60.0   # outside this a DHT value is treated as a bad read


class ClassroomController:
    def __init__(self):
        self.pir_run = 0            # consecutive PIR-high samples
        self.last_motion = None     # time of last CONFIRMED motion
        self.occupied = False
        self.dark = False           # latched with hysteresis, see step()
        self.light_on = False
        self.fan_on = False
        self.temp = None            # last good temperature, None when unknown/failed
        self.dht_fails = 0
        self.sensor_fault = False
        self.high_temp_alert = False
        self._rep_fault = False     # last alert state already reported to the caller
        self._rep_high = False

    # Called whenever a DHT read happens (DHT22 needs >= 2 s between reads).
    # `reading` is a float, or None if the read failed (the driver returned NaN).
    def update_temp(self, reading):
        bad = reading is None or reading != reading or not (TEMP_MIN <= reading <= TEMP_MAX)
        if bad:
            self.dht_fails += 1
            if self.dht_fails >= DHT_FAIL_LIMIT:
                self.temp = None
                self.sensor_fault = True
        else:
            self.dht_fails = 0
            self.temp = float(reading)
            self.sensor_fault = False

    # Called once per second. Returns a list of alert events: (alert_type, severity, state).
    def step(self, now, pir, light_pct):
        events = []

        # 1) Occupancy: debounce PIR, then hold "occupied" for VACANCY_S after the last motion.
        self.pir_run = self.pir_run + 1 if pir else 0
        if self.pir_run >= PIR_CONFIRM:
            self.last_motion = now
        self.occupied = self.last_motion is not None and (now - self.last_motion) < VACANCY_S

        # 2) Darkness with hysteresis (our own LED lights the LDR, so one threshold would flicker).
        if light_pct < DARK_ON_PCT:
            self.dark = True
        elif light_pct > BRIGHT_OFF_PCT:
            self.dark = False

        # 3) Light output.
        self.light_on = self.occupied and self.dark

        # 4) Fan output with hysteresis; fail-safe OFF if no valid temperature or room empty.
        if self.sensor_fault or self.temp is None or not self.occupied:
            self.fan_on = False
        elif self.temp > FAN_ON_C:
            self.fan_on = True
        elif self.temp < FAN_OFF_C:
            self.fan_on = False
        # else: 27..30 C -> keep previous state

        # 5) Alerts (edge-triggered: one event per transition, not one per second).
        if self.temp is not None:
            if self.temp > FAN_ON_C:
                self.high_temp_alert = True
            elif self.temp < FAN_OFF_C:
                self.high_temp_alert = False
        # Compare against what we last REPORTED (not against the start of this step), because
        # update_temp() can flip sensor_fault between two step() calls.
        if self.sensor_fault != self._rep_fault:
            self._rep_fault = self.sensor_fault
            events.append(("sensor_failure", "critical", "active" if self._rep_fault else "cleared"))
        if self.high_temp_alert != self._rep_high:
            self._rep_high = self.high_temp_alert
            events.append(("high_temperature", "warning", "active" if self._rep_high else "cleared"))
        return events
