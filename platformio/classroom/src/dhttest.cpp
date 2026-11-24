// DHT22 diagnostic: NOT part of the product firmware. Built only by the envs dhttest / dhttest_wifi (see platformio.ini).
// Purpose: find out why the main sketch gets DHT "TIMEOUT" in Wokwi, by testing the sensor in isolation.
//   dhttest       : no Wi-Fi, no Blynk.      -> if this works, something in the main sketch disturbs the read.
//   dhttest_wifi  : same + Wi-Fi connecting. -> if only this fails, Wi-Fi activity breaks the timing-critical DHT read.
// idle_level is the data line's level just before the read: it must be 1 (HIGH, pulled up). 0 means the line is stuck low
// (wire not attached to GPIO15, pull-up missing or shorted).
#include <Arduino.h>
#include <DHTesp.h>
#ifdef TEST_WIFI
#include <WiFi.h>
#endif
#ifndef DHT_PIN
#define DHT_PIN 15
#endif

DHTesp dht;

void setup() {
  Serial.begin(115200);
  delay(500);
#ifdef TEST_WIFI
  Serial.printf("DHT test on GPIO%d WITH Wi-Fi\n", DHT_PIN);
  WiFi.mode(WIFI_STA);
  WiFi.begin("Wokwi-GUEST", "");
#else
  Serial.printf("DHT test on GPIO%d, no Wi-Fi\n", DHT_PIN);
#endif
  dht.setup(DHT_PIN, DHTesp::DHT22);
}

void loop() {
  pinMode(DHT_PIN, INPUT);
  delay(5);
  int idle = digitalRead(DHT_PIN);
  TempAndHumidity d = dht.getTempAndHumidity();
  Serial.printf("t=%lu ms idle_level=%d status=%s temp=%.1f hum=%.1f\n", millis(), idle, dht.getStatusString(), d.temperature, d.humidity);
  delay(3000);
}
