# Roadmap

All items are indicative and subject to validated tests, upstream compatibility and community feedback.

- **v0.0.1:** project bootstrap, offline OMM JSON import and SQLite catalog, CLI, unit tests.
- **v0.1.x:** source adapters, identifier alias/history model, orbital freshness policies, station configuration and Skyfield pass prediction.
- **v0.2.x:** deterministic scheduler simulation, 0–127 priority model, full-pass locking, conflict rules and decision logs.
- **v0.3.x:** NiceGUI configuration/dashboard and measured Raspberry Pi memory/CPU budget.
- **v0.4.x:** MQTT dry-run adapter, documented TinyGS firmware protocol, reconnect and command safety.
- **Later:** controlled live-station integration, observability, packaging, CI for additional architectures and community releases.

A private-broker MQTT connection does not guarantee forwarding to TinyGS.com; treat this as a separate feasibility milestone.
