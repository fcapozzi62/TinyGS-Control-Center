# TinyGS MQTT contract: firmware-owned Doppler control

Status: source-reviewed protocol note (2026-11-02), **not validated on a live station**.
Reviewed upstream source: `tinygs/tinyGS` branch `beta`:
- `tinyGS/src/Mqtt/MQTT_Client.h`
- `tinyGS/src/Mqtt/MQTT_Client.cpp`, `manageMQTTData()`
- `tinyGS/src/Radio/Radio.cpp`, `remoteSetFreqOffset()` and `tle()`
- `tinyGS/src/Status.h`, `struct Tle`
- `tinyGS/tinyGS.ino`, periodic TLE update loop

## Ownership

**Server:** selects the satellite and RF profile, holds pass assignment, sets
configuration parameters when needed, logs observed performance.

**Firmware:** computes current TLE Doppler, decides when to retune using
`freqTol` and `refresh`, and performs local radio frequency changes.
The MQTT server MUST NOT issue periodic frequency commands for Doppler
tracking. The radio operates autonomously between MQTT messages when
valid orbital data and a working clock are available.

## Verified topic and payload shape

Target topic template:

```text
tinygs/{mqtt_user}/{station_name}/cmnd/foff
```

JSON payload is a 3-element positional array:

```json
[calibration_offset_hz, doppler_tolerance_hz, refresh_interval_ms]
```

For example, `[125.0, 250, 1000]` means 125 Hz crystal calibration
offset, 250 Hz Doppler tolerance and 1000 ms refresh. **125 Hz here is an
illustrative value, not a recommended station calibration.**

The firmware also accepts legacy single-value forms for the calibration
offset alone. Sending `[0, 250, 1000]` will reset the currently applied
calibration offset to zero, which may be WRONG for the receiver.

A normal command outcome is emitted on:

```text
tinygs/{mqtt_user}/{station_name}/stat/foff
```

The response is **two raw binary bytes**, written from a `uint16_t`
status value, not an ASCII or JSON string. A value of zero indicates
the handler returned zero. Treat endianness as firmware/platform-specific,
and verify on a test receiver; do not assume this ack proves actual
oscillator error, live radio tuning or persistent application.

## Defaults and implementation caveats

Upstream `Status.h` defines:
- `freqTol = 1200` Hz, stored as `uint16_t`.
- `refresh = 4000` ms, stored as `uint16_t`.
- `freqDoppler` and `new_freqDoppler` as floating point values.

`tinyGS.ino` triggers `radio.tle()` periodically based on
`status.tle.refresh`. The current upstream `Radio::tle()` applies
a retune only for positive elevation and when the absolute Doppler
difference exceeds `freqTol`. It currently assigns
`freqDoppler = new_freqDoppler - freqTol` before `setFrequency()`;
this is **asymmetric**, and is not equivalent to tuning exactly to the
predicted Doppler. The simulator's legacy mode approximates this logic.

Values from `foff` are applied to in-memory status structures.
No persistence call is visible in `remoteSetFreqOffset()`; assume the
parameters must be re-established after reboot or profile change until
tested on actual firmware. The function performs no obvious range checks
for the 3-element payload; the Control Center MUST validate inputs before
allowing a publish, including preventing zero refresh.

The reviewed `beta` may differ from custom Stage 2B firmware.
Confirm the checked-out firmware commit and exact patch before any live
transmission. A change from full `begin()` to fast SX1262 retune does not
change who owns the Doppler decision.

## Safe Control Center design (planned)

1. Track station identity, connectivity and selected satellite separately.
2. Store per-radio-profile `doppler_tolerance_hz` and `refresh_ms`.
3. Store **station-level** crystal `calibration_offset_hz`, and never
   assume it is zero; require an explicit known value before sending `foff`.
4. On pass assignment, apply a validated configuration **once** if needed,
   not a continuous stream of retune commands.
5. Require and log status/acks; never infer success from MQTT QoS PUBACK
   alone. Re-check after reconnect/reboot, with rate limits.
6. Do not generate live MQTT messages before dry-run integration tests.
7. Capture RX frame counts, decoder success, receive frequency and Doppler
   diagnostics to compare thresholds in the field. No synthetic packet count
   is a substitute for a measured reception metric.
8. Respect the separate TinyGS.com forwarding feasibility milestone.

### Proposed UI defaults, not firmware limits

- Initial experimental threshold choices: 100, 250 and 500 Hz.
- Initial refresh: 1000 ms for FSK experiments, not a validated optimum.
- Treat `calibration_offset_hz` as mandatory known station configuration.
- Label all threshold/refresh values as **runtime** settings unless a
  persistence mechanism is verified.

## Open validation items

- Confirm the exact custom firmware's `foff` handler and fast-retune path.
- Test live ack decoding and ensure a resulting retune is not triggered
  immediately by updating only the threshold/offset.
- Verify what happens across reconnection, reboot, new `begine` profile,
  local web configuration and radio initialization.
- Determine whether a reliable packet-busy signal exists, and whether
  any proposed retune deferral can be implemented safely in the firmware.
- Calibrate actual RF frequency accuracy and frame yields by threshold
  on multiple passes.

## Offline CLI prototype (implemented)

The first protocol adapter is deliberately **dry-run only**. It does not
connect to Mosquitto, write to SQLite, apply settings, or send any radio
commands. Run with a **known station calibration offset** (example value):

```sh
tcc mqtt-dry-run --mqtt-user fabio --station IZ0IBA_GS2 \
  --offset-hz 125 --tolerance-hz 250 --refresh-ms 1000
```

The command produces JSON with `mode: "dry-run"`, `published: false`,
`topic`, `ack_topic`, a serialized JSON-array `payload` and typed
`parameters`. The MQTT user is a topic identifier, **not a password**;
never provide the MQTT password on the command line.

The adapter refuses absent/invalid calibration offsets, non-finite values,
unsafe MQTT topic segments and threshold/refresh values outside the
`uint16_t` range 1..65535. An application-level safety check limits
absolute offset to 100000 Hz; this limit is not a firmware specification.
There is intentionally no default calibration offset and no publish flag.
The station name must match the MQTT station identifier, which may differ
from the local orbital catalog station label.

## Read-only MQTT monitor (implemented)

`tcc mqtt-monitor` is a **subscriber only**. No command publishing,
no oscillator adjustment, and no radio retuning. First confirm the broker
works independently using `mosquitto_sub` and `mosquitto_pub` with an
isolated test topic; do not change a working TinyGS station's broker.

On Debian 12, with the virtual environment activated:

```bash
python -m pip install -e .
read -r -s -p "MQTT password: " TCC_MQTT_PASSWORD; echo
export TCC_MQTT_PASSWORD
tcc mqtt-monitor --host 192.168.1.61 --port 1883 \
    --mqtt-user tinygs_local --topic 'tinygs/#' \
    --timeout-sec 60
unset TCC_MQTT_PASSWORD
```

The password must NOT be committed, logged, or supplied via a `--password`
command-line argument. The monitor prints JSON lines with UTC timestamp,
topic, QoS, retained flag and payload; binary payloads are shown in
hexadecimal. The runtime uses MQTT 3.1.1 / paho-mqtt 2.x, a transient
client and a 30-second default timeout. `--max-messages N` stops after
N messages; zero means no message-count limit. Ctrl-C also stops it.

The initial broker test uses `tinygs/test/control-center`; this is
only a test payload, NOT telemetry from `IZ0IBA_GS2`. If the Heltec is
still connected to the official TinyGS MQTT broker, the local Mosquitto
will not receive its telemetry automatically. No integration or forwarding
to TinyGS.com has been claimed or enabled.

Port 1883 is plaintext and should only be used on a trusted local network;
add TLS and certificate validation before any remote/untrusted deployment.
