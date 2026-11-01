# Architecture — draft 0.0.1

The Control Center is a **separate community project**, not an official TinyGS server and not an official TinyGS firmware distribution.

## Constraints

- Primarily one Python service, compatible with Linux x86-64 and Raspberry Pi ARM64.
- External MQTT broker configurable; existing Home Assistant Mosquitto can be reused.
- SQLite for persistent state; no required PostgreSQL, Redis, Celery or container runtime.
- Podman rootless, Docker and native systemd deployment are future packaging targets.
- Keep domain logic independent of NiceGUI: a browser must not be required for scheduling.
- Receiver configuration remains in the firmware. Do not assume arbitrary MQTT commands are supported.

## Proposed components (not yet implemented)

1. **Catalog:** satellite identities, temporary/definitive aliases, RF profiles, provenance.
2. **Orbital manager:** OMM import, freshness and validation, Skyfield/SGP4 propagation.
3. **Pass planner:** station-specific AOS/TCA/LOS and elevation predictions.
4. **Scheduler engine:** score, conflict resolution, full-pass lock, preemption policy.
5. **Radio adapter:** TinyGS-specific MQTT topic/payload serialization and telemetry.
6. **UI:** NiceGUI dashboard, catalog editor, scheduler configuration and diagnostics.

v0.0.1 implements only the first orbital catalog foundation. Neither Skyfield nor NiceGUI is a dependency yet.

## Critical protocol risk

Pointing TinyGS firmware at a third-party Mosquitto broker **does not guarantee** that packets will appear on TinyGS.com. The complete control/status/telemetry topic contract and server-side acceptance requirements must be verified against the firmware and permitted service behavior before enabling live control or forwarding. Prototype in dry-run mode first.

## Versioning

Feature branches and reviewed pull requests; automated tests before merging. Keep firmware Doppler experiments in a separate repository/fork. Never commit broker credentials, device flash images or private station configuration.
