#pragma once
struct TempAndHumidity { float temperature; float humidity; };
class DHTesp { public: enum DHT_MODEL_t { DHT22 }; enum DHT_ERROR_t { ERROR_NONE = 0, ERROR_TIMEOUT };
  void setup(int pin, DHT_MODEL_t m); TempAndHumidity getTempAndHumidity(); DHT_ERROR_t getStatus(); const char *getStatusString(); };
