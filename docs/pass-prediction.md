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
