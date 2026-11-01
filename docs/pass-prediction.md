# OMM pass prediction (v0.1.0 in development)

The application uses Skyfield `EarthSatellite.from_omm()` and SGP4 without
converting six-digit NORAD IDs to TLE. Stored elements are used offline.

## Example

```sh
tcc station-add roma-demo --lat 41.9 --lon 12.5 --elevation-m 50 --timezone Europe/Rome --min-elevation 5
tcc passes 101140 --station roma-demo --start 2026-11-01T00:00:00Z --hours 48 --freq-mhz 401.7
```

**The example coordinates are illustrative, not measured station coordinates.**
Configure the exact station coordinates for meaningful comparisons with Orbitron.

AOS/LOS are crossings of the configurable minimum elevation. TCA is the
culmination. Times include UTC and IANA-zone-local ISO-8601 strings.

Only passes fully inside the interval are returned; boundary passes are skipped.
Optional Doppler at TCA is the signed geometric **receiver** frequency shift:
positive means higher observed carrier, excluding equipment offsets and drift.
The OMM epoch and its age at TCA are included; there is no automatic freshness
approval in this version. This is not a radio controller.

## Doppler profile test

For a 2-hour window around the 1 November 2026 evening FOSSASAT-2E27 pass:

```sh
tcc doppler 101140 --station roma-demo1 --start 2026-11-01T18:00:00Z --hours 2 --freq-mhz 401.7 --step-sec 60
```

The command includes AOS, exact TCA, LOS and interval samples. It reports
received geometric Doppler in Hz (positive for approaching satellite), range
rate in km/s, apparent received frequency in MHz, elevation and azimuth.
It does **not** send commands to a receiver. This is an ideal geometric
prediction; it excludes RF oscillator errors and calibration offsets. Verify
AOS/LOS station threshold and timezone when comparing with other trackers.

## Sub-second time precision

AOS/TCA/LOS timestamps now retain microseconds. Doppler can vary by
tens of Hz per second near TCA; rounding a time to a whole second before
replaying it may materially alter the predicted shift. The `doppler`
command uses the precise predicted event timestamps and rounds the
displayed shift only after performing the calculation.

## Virtual-clock retune strategy simulator

```sh
tcc simulate-doppler 101140 --station roma-demo1 \
  --start 2026-11-01T18:00:00Z --hours 2 \
  --freq-mhz 401.7 --thresholds 100 250 500 --step-sec 1
```

For a synthetic test with regularly occurring packet-busy windows:

```sh
tcc simulate-doppler 101140 --station roma-demo1 \
  --start 2026-11-01T18:00:00Z --hours 2 \
  --freq-mhz 401.7 --thresholds 100 250 500 \
  --step-sec 1 --busy-period-sec 30 --busy-duration-sec 5 \
  --show-retunes
```

The simulation samples receive Doppler at the given **virtual clock** cadence.
It sets the initial tuned offset to the Doppler at AOS and holds it until the
absolute *difference* from the desired offset reaches the chosen threshold.
At the first idle sample exceeding the threshold, it instantaneously retunes.
If an artificial packet-busy interval is active, the retune is deferred.

Metrics are **sample based**, not continuous-time guarantees: a large step
can underestimate maximum residual error or miss an excursion. The threshold
does not cover oscillator errors, stepwise synthesizer quantization, on-air
interruptions, retune latency or actual radio state. Busy periods are synthetic,
not obtained from TinyGS. The model currently assumes an instantaneous zero-cost
retune and no buffering or missed packets. `retunes_after_aos` excludes the
initial AOS tune. The `--show-retunes` flag emits each hypothetical event.
**No MQTT, RF hardware, or TinyGS official service is contacted.**

## TinyGS firmware legacy strategy comparison

Use `--with-tinygs-legacy` to include the original TinyGS-style decision
rule: check every 4 seconds; if `abs(new_freqDoppler - freqDoppler)>1200`
set the applied Doppler to `new_freqDoppler - 1200` Hz. This is not a
correction to the exact expected frequency.

```sh
tcc simulate-doppler 101140 --station roma-demo1 \
  --start 2026-11-01T18:00:00Z --hours 2 \
  --freq-mhz 401.7 --thresholds 100 250 500 --step-sec 1 \
  --with-tinygs-legacy --legacy-refresh-sec 4 --legacy-tolerance-hz 1200
```

This is a discrete approximation of upstream firmware defaults, **not a
bit-exact hardware emulator**. The first check is anchored to AOS, though a
real firmware loop has an independent timer; remote MQTT configuration can
override both defaults. The legacy comparison does not defer for synthetic
busy periods. Retune latencies and lost packets are not modeled.
