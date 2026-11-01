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
