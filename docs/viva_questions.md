# 10 likely viva questions about my own design choices

Answers are short on purpose: say the "why", then admit the limitation.

1. **Why MQTT instead of HTTP for the devices?**
   Devices publish small messages often; MQTT keeps one persistent TCP connection, is lightweight, decouples publishers from subscribers (the dashboard and any other consumer can subscribe without the device knowing), and has built-in last will and QoS. HTTP would need polling or a server endpoint per device.

2. **Why one metric per message with `metric`/`value`/`unit`?**
   The shared contract is fixed so any module can be validated by one generic validator and stored in one table. Cost: a classroom needs three messages per cycle. Extra context (light_on, fan_on) goes in the status heartbeat as additional fields.

3. **What does QoS 1 give you, and what does it cost?**
   At-least-once delivery: the broker acknowledges and the sender retries, so a dropped packet does not lose an alert. Cost: duplicates are possible, so my backend de-duplicates alerts (an active alert for the same device and type is not inserted twice). The ESP32 sketch uses PubSubClient which publishes QoS 0 only: a documented gap.

4. **How does the last will work and what is its weakness?**
   At connect the client registers an "offline" message with the broker; the broker publishes it if the client vanishes without a clean disconnect. Weakness: it carries the timestamp from connect time, so the backend uses its own receive time. A silent network failure takes about 1.5 x keepalive (45 s) to be detected, which is why the backend also has a heartbeat timeout.

5. **Why 30 / 27 degC hysteresis for the fan, and 30 / 40 % for light?**
   A single threshold makes the output chatter when the value hovers around it. The fan's 3 C band stops rapid on/off cycling. For light, my own lamp raises the LDR reading, so with one threshold the light would switch itself off then on (flicker); the 30-40 % band keeps it stable. Both are tested (M3 and a unit test).

6. **What happens when the DHT sensor fails?**
   After 3 consecutive bad reads the temperature is treated as unknown, the fan is forced OFF (fail-safe), a critical `sensor_failure` alert is raised and no temperature is published (I never publish a fake value). It clears when a valid reading returns.

7. **Why is a stationary person a problem, and what would you do?**
   A PIR detects movement, not presence. A seated person can stop triggering it, so lights turn off after 30 s. It is a known limitation recorded in the tests. Fixes: longer timeout, a second sensor type (mmWave presence), or CO2 as a secondary occupancy hint.

8. **How do you decide a device is offline, and why two mechanisms?**
   (a) Last-will status = immediate, for crashes/power loss. (b) Timeout: no message for `offline_s` (default 120 s, configurable) = "stale", for silent network loss. Both raise a `device_offline` alert that clears when the device returns.

9. **What does your validation reject and why on the backend?**
   Malformed JSON, missing fields, unknown module or device, device/location not matching the registry, topic not matching the payload (spoofing), invalid or far-future timestamps, wrong types and out-of-range values (FR-02). Rejects are stored with a reason so errors are visible, not silently dropped. Devices cannot be trusted to validate themselves.

10. **Are your roles secure? What is real and what is simulated?**
    No. The role is a dropdown that sends an `X-Role` header; the server enforces it (viewer read-only, operator acknowledge, administrator export/config) to demonstrate role-based behaviour, but anyone can change the header. Real security needs authentication (login/tokens), TLS and broker ACLs. Also: the whole system runs on an isolated laptop, all device data is simulated and labelled, and sensor accuracy was not validated on hardware.

**Bonus**: *Why Wokwi and Blynk, and why do they not feed Node-RED?* No hardware was available, so Wokwi simulates the ESP32 and sensors, and Blynk Cloud gives the module a ready-made dashboard and event notifications. Wokwi cannot reach `localhost`, so the shared platform is fed by Python simulators with the same rules. The logic is a header-only C++ file tested natively, so it is the same code in Wokwi and PlatformIO. Not verified: the behaviour inside Wokwi/Blynk (tests W1-W8).

**Bonus**: *Why Node-RED + SQLite?* One tool for ingest, API and storage fits a solo, one-night prototype and the spec allows equivalent tools if the interface is preserved; SQLite needs no server. Limits: single writer, no horizontal scaling.
