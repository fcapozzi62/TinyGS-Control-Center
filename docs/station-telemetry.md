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

- Integrate the parser into `tcc mqtt-monitor` behind an explicit
  `--summarize-stations` mode, keeping raw read-only monitoring intact.
- Separate desired scheduler assignment, configured modem state and
  last RX report in the station state model.
- Determine explicit online/offline criteria and reboot detection.
- Optional SQLite event history, bounded and privacy-conscious.
- Compare reception statistics across pass/time windows and
  Doppler tolerance settings **using real reception records**.
