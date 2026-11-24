"""Unit tests for the classroom logic using a fake clock. Run: python simulator/test_logic.py
Maps to the test plan: M1 normal, M2 threshold, M3 boundary, M4 sensor failure, M5 recovery,
M6 vacancy timeout, plus false trigger and stationary occupant.
"""
from classroom_logic import ClassroomController


def run(c, seconds, pir, light, start=0):
    """Advance `seconds` one-second ticks; return all alert events and the final time."""
    ev = []
    for t in range(start, start + seconds):
        ev += c.step(t, pir, light)
    return ev, start + seconds


def test_m1_normal():
    c = ClassroomController(); c.update_temp(25.0)
    run(c, 3, pir=True, light=10)
    assert c.occupied and c.light_on and not c.fan_on


def test_daylight_no_light():
    c = ClassroomController(); c.update_temp(25.0)
    run(c, 3, pir=True, light=80)
    assert c.occupied and not c.light_on


def test_false_trigger_ignored():
    c = ClassroomController(); c.update_temp(25.0)
    c.step(0, True, 10)       # one-sample blip
    c.step(1, False, 10)
    assert not c.occupied and not c.light_on


def test_m2_fan_on_and_alert():
    c = ClassroomController(); c.update_temp(31.0)
    ev, _ = run(c, 3, pir=True, light=10)
    assert c.fan_on and ("high_temperature", "warning", "active") in ev


def test_m3_boundaries():
    c = ClassroomController(); t = 0
    for temp, expect_fan in [(29, False), (30.0, False), (30.1, True), (29, True),
                             (27.0, True), (26.9, False), (28, False)]:
        c.update_temp(temp)
        _, t = run(c, 2, pir=True, light=80, start=t)
        assert c.fan_on == expect_fan, (temp, c.fan_on)


def test_m4_sensor_failure_fail_safe():
    c = ClassroomController(); c.update_temp(31.0)
    run(c, 3, pir=True, light=10)
    assert c.fan_on
    for _ in range(2):
        c.update_temp(None)
    assert not c.sensor_fault         # 2 bad reads: still tolerated
    c.update_temp(None)               # 3rd bad read
    ev, _ = run(c, 1, pir=True, light=10, start=3)
    assert c.sensor_fault and not c.fan_on and c.temp is None
    assert ("sensor_failure", "critical", "active") in ev


def test_dht_out_of_range_counts_as_failure():
    c = ClassroomController()
    for v in (-40.0, 125.0, float("nan")):
        c.update_temp(v)
    assert c.sensor_fault


def test_m5_recovery():
    c = ClassroomController()
    for _ in range(3):
        c.update_temp(None)
    run(c, 1, True, 10)
    c.update_temp(24.0)
    ev, _ = run(c, 1, True, 10, start=1)
    assert not c.sensor_fault and ("sensor_failure", "critical", "cleared") in ev


def test_m6_vacancy_30s():
    c = ClassroomController(); c.update_temp(25.0)
    _, t = run(c, 3, True, 10)                  # motion confirmed at t=1,2 -> last_motion=2
    run(c, 29, False, 10, start=t)              # t=3..31 -> 29 s since last motion at t=2 (t=31)
    assert c.light_on, "still within 30 s"
    run(c, 1, False, 10, start=t + 29)          # t=32 -> 30 s since motion
    assert not c.occupied and not c.light_on


def test_light_hysteresis_no_flicker():
    c = ClassroomController(); c.update_temp(25.0)
    run(c, 3, True, 10)
    assert c.light_on
    # Our own LED raises the LDR reading to 35%: must stay ON (35 is inside 30..40 band)
    run(c, 3, True, 35, start=3)
    assert c.light_on
    run(c, 1, True, 45, start=6)                # genuinely bright -> OFF
    assert not c.light_on


def test_stationary_occupant_limitation():
    """KNOWN LIMITATION: a motionless person stops triggering the PIR -> lights go off after 30 s."""
    c = ClassroomController(); c.update_temp(25.0)
    _, t = run(c, 3, True, 10)
    run(c, 35, False, 10, start=t)              # person sits still, PIR silent
    assert not c.occupied


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn(); print("PASS", fn.__name__)
    print(f"{len(tests)} tests passed")
