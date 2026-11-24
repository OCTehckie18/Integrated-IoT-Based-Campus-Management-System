# Test results (automated run)

Run 2026-11-16T00:12:21 to 2026-11-16T00:14:27 against the live system (Mosquitto + Node-RED, simulated devices).

**25 passed, 0 failed, 1 not run.**

| ID | Test | Expected | Actual | Result |
|---|---|---|---|---|
| U1 | Logic unit tests (fake clock) | all tests pass | 11 tests passed | **PASS** |
| T1 | Valid feed accepted and shown | Reading visible via API within 5 s | visible after 0.02 s | **PASS** |
| T2 | Missing required field rejected | Stored in rejects with reason missing_field:device_id | reason=missing_field:device_id | **PASS** |
| T2b | Malformed JSON flagged | Stored in rejects with reason malformed_json | reason=malformed_json | **PASS** |
| T2c | Invalid timestamp flagged | Stored in rejects with reason invalid_timestamp | reason=invalid_timestamp | **PASS** |
| T2d | Out-of-range value flagged | Stored in rejects with reason out_of_range:power_w | reason=out_of_range:power_w | **PASS** |
| T3 | Unknown device flagged | Stored in rejects with reason unknown_device:GHOST-99 | reason=unknown_device:GHOST-99 | **PASS** |
| T3b | Unknown module flagged | Stored in rejects with reason unknown_module:cafeteria | reason=unknown_module:cafeteria | **PASS** |
| T2e | Rejected messages never reach readings | Latest value untouched by the 6 bad messages | latest unchanged | **PASS** |
| T4 | Device silent > timeout becomes stale/offline + alert | health=stale after offline_s=10 s, device_offline alert raised | online first=True; stale after 10.8 s; alert=raised | **PASS** |
| T4b | Data resumes -> back online, offline alert clears | health=online and alert cleared (<=10 s timer) | recovered after 10.3 s | **PASS** |
| T6 | Alert correct: severity/value, de-dup, ack, clear | 1 row (2 identical events), active -> acknowledged -> cleared | rows=1, first=active, ack http=200, after ack=acknowledged, after clear=cleared | **PASS** |
| T7 | Units and last-updated time shown | metric has unit + received time; page renders 'x s ago' and SIMULATED label | unit=W, rx=2026-11-15T18:42:21.267Z, page labels present=True | **PASS** |
| R1 | Role check on acknowledge | viewer 403, operator 200 | viewer 403, operator 200 | **PASS** |
| R2 | CSV export (administrator only, filtered) | operator 403; admin 200, header + data rows, only energy | operator 403, admin 200, 28 lines, header ok=True, all energy=True | **PASS** |
| F1 | Filters by module / building / zone | only matching devices returned | module=energy->{'energy'}, BLOCK-B->{'BLOCK-B'}, LOT-1->{'LOT-1'} x4 | **PASS** |
| S1 | Filter input is not injectable | treated as 'no filter', no error, 9 registered devices | 9 devices returned | **PASS** |
| M1 | Normal: occupied + dark -> light ON, fan OFF | occupied, daylight keeps light OFF; darkness turns light ON | bright: occ=True light=False; dark -> light ON after 0.9 s; fan=False | **PASS** |
| M2 | Threshold: 31.5 C occupied -> fan ON + alert | fan ON, high_temperature alert active | fan ON after 2.1 s; alert=raised | **PASS** |
| M3 | Boundary: hysteresis at 30.0 / 30.1 / 27.0 / 26.9 C | fan flips only above 30 C and below 27 C | 30.0C->ON, 27.0C->ON, 26.9C->OFF, 30.0C->OFF, 30.1C->ON | **PASS** |
| M4 | Sensor disconnect: 3 bad reads -> fail-safe | fan forced OFF, sensor_fault true, sensor_failure alert | fail-safe after 5.4 s; fan=False; alert=raised | **PASS** |
| M5 | Recovery: sensor returns -> alert clears, logic resumes | sensor_fault false, alert cleared | recovered after 6.8 s | **PASS** |
| M6 | Vacancy: no motion 30 s -> light OFF (stationary occupant limitation) | still occupied at +20 s; vacant and light OFF by ~30 s | at +20 s occupied=True; vacant+light OFF after a further 10.4 s | **PASS** |
| M7 | False trigger: single PIR pulse ignored | room stays vacant, light stays OFF | occupied=False, light_on=False | **PASS** |
| T5a | Device killed (last will) then restarted: resumes | offline + alert after kill; online again and alert cleared after restart | offline=True, alert=raised, back online after 0.4 s, alert cleared after 9.7 s | **PASS** |
| T5b | Broker outage: stop/start Mosquitto, all parties reconnect | Node-RED + device resume without restart | NOT RUN: needs admin to stop the Mosquitto service; do it by hand (docs/phase8_validation.md) | **NOT RUN** |
