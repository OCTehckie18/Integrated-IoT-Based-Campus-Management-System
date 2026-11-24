#pragma once
#include "Arduino.h"
#define WL_CONNECTED 3
#define WIFI_STA 1
struct WiFiStub { void mode(int); void begin(const char *, const char *); int status(); };
extern WiFiStub WiFi;
