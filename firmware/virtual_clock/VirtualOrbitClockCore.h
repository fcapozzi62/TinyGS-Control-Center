// Portable orbit-only virtual clock state. No Arduino, ESP32 or RF dependency.
// All methods must be called under the same lock on an embedded target.
#ifndef TCC_VIRTUAL_ORBIT_CLOCK_CORE_H
#define TCC_VIRTUAL_ORBIT_CLOCK_CORE_H
#include <stdint.h>

class VirtualOrbitClockCore {
public:
  VirtualOrbitClockCore()
      : epoch_seconds_(0), start_monotonic_us_(0), speed_milli_(1000),
        prepared_(false), running_(false) {}

  // Preparation has NO effect on the time reported by now().
  bool prepare(int64_t epoch_seconds) {
    if (epoch_seconds <= 0) return false;
    epoch_seconds_ = epoch_seconds;
    prepared_ = true;
    running_ = false;
    return true;
  }

  // speed_milli=1000 means real time, 4000 means 4x speed.
  // Use a monotonic clock in microseconds; UTC wall clock is never changed.
  bool start(uint64_t monotonic_us, uint32_t speed_milli = 1000) {
    if (!prepared_ || speed_milli < 1 || speed_milli > 16000) return false;
    start_monotonic_us_ = monotonic_us;
    speed_milli_ = speed_milli;
    running_ = true;
    return true;
  }

  void stop() {
    running_ = false;
    prepared_ = false;
    epoch_seconds_ = 0;
    speed_milli_ = 1000;
  }

  int64_t now(int64_t real_utc_seconds, uint64_t monotonic_us) const {
    if (!running_) return real_utc_seconds;
    if (monotonic_us < start_monotonic_us_) return epoch_seconds_;
    const uint64_t elapsed_us = monotonic_us - start_monotonic_us_;
    // Split whole seconds and fractional microseconds first to avoid
    // overflow on long runs; 16x is the maximum supported speed.
    const uint64_t whole = elapsed_us / 1000000ULL;
    const uint64_t fraction = elapsed_us % 1000000ULL;
    return epoch_seconds_
         + static_cast<int64_t>(whole * speed_milli_ / 1000ULL)
         + static_cast<int64_t>(
               ((whole * speed_milli_) % 1000ULL) * 1000000ULL
               + fraction * speed_milli_) / 1000000000LL;
  }

  bool isRunning() const { return running_; }
  bool isPrepared() const { return prepared_; }
  uint32_t speedMilli() const { return speed_milli_; }

private:
  int64_t epoch_seconds_;
  uint64_t start_monotonic_us_;
  uint32_t speed_milli_;
  bool prepared_;
  bool running_;
};
#endif
