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

Note that `tele/rx` fields come from a received frame's stored modem
configuration and need not describe the currently selected satellite at
the moment the report is ingested. `stat/status` reports the modem state
at the time of the message. The first implementation reports
`satellite` as the most recently observed value; do NOT treat this as
a confirmed scheduler assignment. A later release will separate
`configured_satellite` from `last_rx_satellite`.

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
- Separate desired scheduler assignment, configured modem state and
  last RX report in the station state model.
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
Only `tele/welcome`, `tele/rx`, and `stat/status` with valid JSON
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
