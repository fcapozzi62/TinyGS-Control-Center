# Orbital data — draft 0.0.1

## Primary format

Use CCSDS-style OMM JSON as the canonical imported orbital format; support six-digit and future NORAD identifiers without truncation. Preserve the supplied OMM object and record source, epoch and retrieval timestamp. Keep historical sets instead of overwriting them.

### Current schema

- `satellites`: local database key, catalog NORAD identifier, object name and international designator.
- `orbital_elements`: source, UTC epoch, fetch time, selected numeric fields and original parsed JSON object.

Data and metadata are local-only in v0.0.1. No automatic refresh, propagation, TLE conversion, orbital accuracy scoring or provisional-ID reconciliation is implemented.

## Identity model — next iteration

A provisional catalog number, e.g. 98187, **must not** silently replace an official NORAD ID, e.g. 101140. Add an internal stable satellite key plus a separate identifier/alias history table, backed by verified mapping provenance. Never assume two objects are the same because their orbital elements resemble one another.

## Freshness and reliability

Distinguish `EPOCH` (when the element set applies) from `fetched_at` (when we obtained it). Newer elements are not necessarily more accurate. Future scheduler warnings should flag stale data, conflicting sources and missing identity mappings.

## CelesTrak integration

The CLI command `fetch-omm <NORAD>` fetches GP OMM JSON by catalog number via HTTPS. This is an explicit action, not a background updater. Avoid aggressive polling; respect source policies. The offline fixture in `examples/` is a snapshot supplied during initial project discussions and **not** a source of live orbital truth.

## Receiver compatibility

TLE and Alpha-5 are **output compatibility formats only**. An SX1262/SX1278 firmware parser's Alpha-5 support must be checked before claiming full six-digit NORAD interoperability.
