# Virtual orbit clock (experimental staging)

This code is staged in Control Center because the user's local
`tinyGS-fsk-fifo` firmware checkout is not presently exposed via the GitHub
connector. It is **not deployed** to GS1 or GS2. It is shared code suitable
for both the ESP32/SX1278 and ESP32-S3/SX1262 targets.

## Design

- Normal mode is the default. On boot, `now()` returns `time(NULL)`.
- `prepare(utc_epoch)` saves an orbital epoch but does **not** affect P13.
- `start(speed_milli)` enables virtual time, referenced to
  `esp_timer_get_time()` rather than wall-clock time; 1000 = 1x, 4000 = 4x.
- `stop()` immediately returns P13 to the real UTC clock.
- There is no persistence: reset/power-cycle returns to real time.
- Only `Radio::tle()` uses this clock. Wi-Fi, MQTT, logging, timestamps,
  telemetry and received-packet time remain on the actual UTC system clock.
- No radio-specific dependencies, no changes to FIFO, AFC, P13 or the Doppler
  threshold.
- This first stage has **no remote control command**. It remains disabled
  until a later experimental, local-broker-only MQTT handler is added.
- Maximum supported replay speed is 16x; at accelerated rates the firmware
  P13 update cadence must be reviewed before measuring packet performance.

## Preview on Debian without modifying the receiver firmware

```bash
cd ~/Scaricati/gitRoot/TinyGS-Control-Center
git fetch origin
git switch feature/virtual-orbit-clock-staging
python firmware/virtual_clock/apply_orbit_clock.py \
  ~/Scaricati/gitRoot/tinyGS-fsk-fifo
```

The script shows a unified diff only. It will refuse to proceed if it cannot
identify exactly one `time(NULL)` inside `Radio::tle()`.

Later, after the satellite passes, the hook can be applied explicitly by adding
`--apply`. The script creates a backup, copies both headers and modifies
`Radio.cpp`; **it does not compile or flash** the firmware. Any existing
target header or backup causes it to fail rather than overwrite.

```bash
python -m unittest discover -s tests -p 'test_virtual_orbit_clock.py' -v
```

The test compiles the core with host `g++`, so no ESP32 device is needed.

## Important future work

1. Implement `prepare/start/stop/status` MQTT commands restricted to a
   dedicated experimental broker; official TinyGS broker ignores them.
2. Confirm acknowledgment and radio configuration before starting replay.
3. Share a single epoch/start timestamp with GNU Radio/HackRF.
4. Coordinate TLE update cadence with replay speed, and log virtual UTC,
   target Doppler, applied offset and packet errors.
5. Compare both receivers at real speed before using accelerated passes.

The original standard TinyGS `begine` path remains unchanged.
