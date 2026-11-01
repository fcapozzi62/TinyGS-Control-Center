# Scheduler concept — not implemented

The project's core innovation is explainable, pass-aware tuning.

## Proposed rules for discussion

- Numerical base priority `0..127` per satellite; optional family-level defaults with clear precedence.
- Build candidate passes for the configured station and supported RF profiles.
- Explicit conflict detection: one receiver cannot tune to two satellites at once.
- Default preference: maintain tracking for the complete planned pass (AOS to LOS), not arbitrary minute-by-minute changes.
- Preemption is **policy driven**, not assumed: higher-priority targets may be allowed or forbidden to interrupt a locked pass.
- Consider good-frame reception as a possible lock criterion, but do not assume that every firmware profile exposes consistent frame-validity semantics.
- Record the *reason* for every decision: candidate scores, stale elements, exclusions and lock state.
- Dry-run mode and a virtual clock must enable reproducible schedule simulations without a radio.

Future discussions will settle thresholds, scoring functions, visibility cutoffs, tie-breaking, Doppler ownership and safeguards. No implementation decisions are frozen by this document.
