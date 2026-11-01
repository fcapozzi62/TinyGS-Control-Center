# TinyGS Control Center

> **Experimental pre-alpha — v0.1.0 development branch**

An independent, open-source satellite scheduling and MQTT control project for TinyGS-compatible ground stations. **Not affiliated with or endorsed by the official TinyGS project.**

The long-term goal is an explainable, pass-aware scheduler: numerical priorities (0–127), satellite-family policies, conflict resolution, whole-pass tracking and explicit preemption rules. The control application should run on modest Linux devices, including Raspberry Pi, without requiring a database server.

## v0.1.0 (development) — orbital catalog and pass prediction

This initial release deliberately has **no receiver control**. It provides:

- Import of CCSDS-style OMM JSON (single object or array), including six-digit NORAD IDs.
- SQLite storage of satellite identities and historical element sets, with provenance and timestamps.
- A command-line interface to import, inspect and list stored data.
- A CelesTrak GP OMM JSON fetch command (requires network access).
- Offline unit tests using Python's standard library.

**Not implemented yet:** scheduling, NiceGUI, MQTT commands, TinyGS.com forwarding or an automated orbital update service. Nothing in this release transmits radio commands.

### Requirements

Python 3.11+; Skyfield is required for pass prediction. Supported target platforms include Linux x86-64 and ARM64 (Raspberry Pi); real-device resource measurements are still pending.

### Quick start

Clone the repository and run from its root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
tcc --db ./data/catalog.sqlite import-omm examples/fossasat-2e27.json --source example
tcc --db ./data/catalog.sqlite list
tcc --db ./data/catalog.sqlite show 101140
```

To fetch recent orbital elements from CelesTrak (internet required):

```bash
tcc --db ./data/catalog.sqlite fetch-omm 101140
```

CelesTrak may return no data for an object. The fetch command validates the returned NORAD ID; it does not silently substitute another satellite. Avoid unnecessarily frequent automated requests to orbital providers.

To run tests:

```bash
python -m unittest discover -s tests -v
```

### Predict passes (development branch)

```bash
tcc station-add roma-demo --lat 41.9 --lon 12.5 --elevation-m 50 --timezone Europe/Rome --min-elevation 5
tcc passes 101140 --station roma-demo --start 2026-11-01T00:00:00Z --hours 48 --freq-mhz 401.7
```

The sample coordinates are illustrative only. See [pass prediction](docs/pass-prediction.md).

### Design notes

- The database stores original parsed OMM objects as JSON and extracts only a few indexed fields.
- Historical elements are append-only by source and epoch; duplicate imports are ignored.
- The official NORAD ID remains unchanged in the database. Do **not** substitute a legacy five-digit identifier for an Alpha-5/6-digit object.
- No claim is made that a downloaded element set is accurate merely because it is recent.
- Security: never commit MQTT credentials, device backups, tokens or local station configuration.

See [architecture](docs/architecture.md), [orbital data](docs/orbital-data.md), [scheduler design](docs/scheduler-design.md), and [roadmap](docs/roadmap.md).

### License

MIT — see [LICENSE](LICENSE). External dependencies and source data retain their own terms.
