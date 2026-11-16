// ESP32 adapter for a virtual time used ONLY by satellite orbital prediction.
// Do not call settimeofday(), configTime() or change system UTC.
#ifndef TCC_VIRTUAL_ORBIT_CLOCK_H
#define TCC_VIRTUAL_ORBIT_CLOCK_H
#include <stdint.h>
#include <time.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
#include "VirtualOrbitClockCore.h"

class VirtualOrbitClock {
public:
  static time_t now() {
    const time_t real_utc = time(NULL);
    const uint64_t mono_us = static_cast<uint64_t>(esp_timer_get_time());
    portENTER_CRITICAL(&mutex());
    const int64_t virtual_utc = core().now(static_cast<int64_t>(real_utc), mono_us);
    portEXIT_CRITICAL(&mutex());
    return static_cast<time_t>(virtual_utc);
  }

  static bool prepare(time_t utc_epoch) {
    portENTER_CRITICAL(&mutex());
    const bool ok = core().prepare(static_cast<int64_t>(utc_epoch));
    portEXIT_CRITICAL(&mutex());
    return ok;
  }

  static bool start(uint32_t speed_milli = 1000) {
    const uint64_t mono_us = static_cast<uint64_t>(esp_timer_get_time());
    portENTER_CRITICAL(&mutex());
    const bool ok = core().start(mono_us, speed_milli);
    portEXIT_CRITICAL(&mutex());
    return ok;
  }

  static void stop() {
    portENTER_CRITICAL(&mutex());
    core().stop();
    portEXIT_CRITICAL(&mutex());
  }

  static bool isActive() {
    portENTER_CRITICAL(&mutex());
    const bool running = core().isRunning();
    portEXIT_CRITICAL(&mutex());
    return running;
  }

private:
  static VirtualOrbitClockCore &core() {
    static VirtualOrbitClockCore instance; // RAM only: reboot disables replay.
    return instance;
  }
  static portMUX_TYPE &mutex() {
    static portMUX_TYPE instance = portMUX_INITIALIZER_UNLOCKED;
    return instance;
  }
};
#endif
