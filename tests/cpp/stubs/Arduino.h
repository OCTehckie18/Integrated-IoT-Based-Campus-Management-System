// STUB of the Arduino core, only to type-check the sketch on a PC. Not a real implementation.
#pragma once
#include <stdint.h>
#include <stdio.h>
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define constrain(x, a, b) ((x) < (a) ? (a) : ((x) > (b) ? (b) : (x)))
void pinMode(int, int); void digitalWrite(int, int); int digitalRead(int); int analogRead(int); unsigned long millis();
struct SerialStub { void begin(long); int printf(const char *, ...) __attribute__((format(printf, 2, 3))); };
extern SerialStub Serial;
