#pragma once
#include "Arduino.h"
#define V0 0
#define V1 1
#define V2 2
#define V3 3
#define V4 4
#define V5 5
#define V6 6
#define BLYNK_CONNECTED() void blynkConnectedCallback()
struct BlynkStub {
  void config(const char *auth); bool connected(); void run(); bool connect(unsigned long timeout);
  void virtualWrite(int pin, double v); void virtualWrite(int pin, int v); void virtualWrite(int pin, const char *v);
  void logEvent(const char *code, const char *desc);
};
extern BlynkStub Blynk;
