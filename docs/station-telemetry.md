# TinyGS station telemetry registry (initial offline prototype)

The registry is **in memory**, independent of the SQLite orbital ground
station catalog. It is keyed by `(mqtt_user, station_name)`; the latter
is the name appearing in TinyGS MQTT topics, NOT necessarily the name
used for Skyfield's local observer.

## Reviewed upstream TinyGS source

The firmware `tinyGS/src/Mqtt/MQTT_Client.cpp` on branch `beta` emits:

| Topic suffix | Important fields | Meaning |
|---|---|---|
| `tele/welcome` | `sat`, `version` | Initial connection/status; not definitive online evidence |
| `stat/status` | `satellite`, `NORAD`, `mode`, `frequency`, `frequency_offset` | Radio state snapshot |
| `tele/rx` | `satellite`, `NORAD`, `mode`, `frequency`, `f_doppler`, `rssi`, `snr`, `frequency_error`, `crc_error`, `noisy` | Received-frame report |
| `cmnd/begine` | `sat`, `NORAD`, `mode`, `freq`, `bw`, `sf`, `cr`, `sw`, `pl` | Requested tuning profile (observed scheduler command) |

Note that `tele/rx` fields come from a received frame's stored modem
configuration and need not describe the currently selected satellite at
the moment the report is ingested. `stat/status` reports the modem state
at the time of the message. An observed `cmnd/begine` message is
**not an acknowledgement that the radio applied the new profile**.
The registry now preserves separate `commanded_*`, `status_*`
and `last_rx_*` fields and separate timestamps. The older top-level
`satellite`, `mode`, `frequency_mhz` fields are retained for
compatibility; these reflect the latest non-command observation and
must not be interpreted as a scheduler assignment. The compact
`tlx` string (and `filter`, IP, MAC, data) is never copied to
the station summary; this iteration does not attempt to decode it.

**Unknown topics, broken JSON and non-object payloads are ignored.**
The registry deliberately does NOT retain IP, MAC, raw payloads,
packet data or arbitrary firmware fields. `rx_count`,
`crc_error_count` and `noisy_count` are **observed MQTT report counts**
since registry startup, not RF frame totals or independent decoder
success rates. RSSI and SNR may be absent or modality-dependent.

`presence: observed_only` is intentional. A message proves that a
report was seen, not that a device is connected now. Future versions
need broker session/will data and a heartbeat timeout before using
`online` / `offline` status for scheduling.

## Offline test

After updating the development branch:

```bash
python -m pip install -e .
tcc telemetry-replay examples/tinygs-telemetry-sample.jsonl
python -m unittest discover -s tests -q
```

The example is **synthetic**, not actual observed reception. A
`telemetry-replay` input is JSONL with one object per line containing
`topic` and `payload` (a JSON object), optionally
`received_at_utc` as an ISO-8601 timezone-aware timestamp.
The command only parses local files and prints JSON snapshots; it does
not contact Mosquitto or write to SQLite.

## Remaining work

- The monitor integration is now implemented via `--summarize-stations`.
- Add an explicit modem-configuration acknowledgement or reconciliation
  rule; an observed scheduler command is not an applied configuration.
- Correlate a command with subsequent status and RX reports, with
  timestamps and reliable pass identifiers.
- Determine explicit online/offline criteria and reboot detection.
- Optional SQLite event history, bounded and privacy-conscious.
- Compare reception statistics across pass/time windows and
  Doppler tolerance settings **using real reception records**.

## Read-only live monitor with station summaries

The monitor's default mode remains unchanged: it prints one JSON object for
every MQTT message, with no registry. Opting in to `--summarize-stations`
adds an in-memory registry and prints one final JSON object after stopping:

```json
{"type":"station_summary","stations":[]}
```

The `stations` array is empty if only unknown/test topics were received.
Only `tele/welcome`, `tele/rx`, `stat/status` and `cmnd/begine` with valid JSON
objects contribute to a station snapshot; `tinygs/test/control-center`
does **not** count as genuine device telemetry. Reports remain ephemeral:
no station rows or raw data are written to SQLite.

Example, on a trusted LAN (password is entered privately and is not
passed on the command line):

```bash
read -r -s -p "MQTT password: " TCC_MQTT_PASSWORD; echo
export TCC_MQTT_PASSWORD
tcc mqtt-monitor --host 192.168.1.61 --port 1883 \
  --mqtt-user tinygs_local --topic 'tinygs/#' \
  --timeout-sec 60 --summarize-stations
unset TCC_MQTT_PASSWORD
```

This produces a summary only when the command completes or is interrupted.
The monitor **does not publish** MQTT messages, change radio configuration,
or cause official TinyGS traffic to appear on a different broker.

## Monitoring the official TinyGS broker

The firmware was observed receiving a real
`tinygs/{account}/IZ0IBA_GS2/cmnd/begine` message for Tianqi
(NORAD 62366, LoRa 400.45 MHz). A second client successfully subscribed
and received the command, establishing **observability**, not authorization
to take over scheduling or publish commands.

After storing the official account credentials in the environment, the
same read-only monitor can connect using the TLS CA certificate:

```bash
source ~/.tinygs-mqtt.env
export TCC_MQTT_PASSWORD="$MQTT_PASS"
tcc mqtt-monitor --host mqtt.tinygs.com --port 8883 \\
  --mqtt-user "$MQTT_USER" --topic "tinygs/$MQTT_USER/IZ0IBA_GS2/#" \\
  --timeout-sec 900 --summarize-stations \\
  --cafile ~/.config/tinygs/tinygs-ca.pem
unset TCC_MQTT_PASSWORD
```

`--cafile` enables TLS with certificate validation against the supplied
CA PEM, including the official TinyGS self-signed root. The monitor
still performs only SUBSCRIBE (no application-level MQTT PUBLISH).
The optional `--summarize-stations` extracts observed scheduler
commands and station reports at shutdown. Use `Ctrl+C` to end early.
Keep the TLS root and MQTT credentials private.
