// Copy this file to secrets.h (same folder). secrets.h is gitignored: NEVER commit real values.
// Use the isolated LAB network only: not campus production Wi-Fi.
#pragma once
#define WIFI_SSID   "your-lab-ssid"
#define WIFI_PASS   "your-lab-password"
#define MQTT_HOST   "192.168.0.10"   // the laptop running Mosquitto (check with ipconfig)
#define MQTT_PORT   1883
#define MQTT_USER   ""               // leave empty if the broker allows anonymous (Phase 2 config)
#define MQTT_PASS   ""
#define NTP_HOST    "192.168.0.10"   // MUST be reachable from the lab network, see README (time sync)
