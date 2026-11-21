"""Repeat one packet schedule at several phases without changing Doppler time.

This module only generates offline IQ-sample schedules. It does not control
TinyGS retuning, GNU Radio, HackRF, or the station clock.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .phase_tx import plan_tx


def _decimal(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def plan_phase_sweep(*, sample_rate: int, period_ms, phases_ms,
                     packet_samples: int, count: int):
    """Return runs sharing the same sample-time origin and packet spacing.

    Phase is *within* a packet period. Runs are independent replays of the
    same orbit, not several simultaneous transmitters.
    """
    phases = tuple(phases_ms)
    if not phases:
        raise ValueError("at least one phase is required")
    normalized = [_decimal(p, "phase_ms") for p in phases]
    if len(set(normalized)) != len(normalized):
        raise ValueError("duplicate phases would repeat the same experiment")
    runs = []
    for phase in normalized:
        events = plan_tx(sample_rate=sample_rate, period_ms=period_ms,
                         phase_ms=str(phase), packet_samples=packet_samples,
                         count=count)
        runs.append((str(phase), events))
    return runs


def write_sweep_csv(runs, destination):
    """Emit a portable sample-exact schedule with explicit run identifiers."""
    with Path(destination).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("run_id", "phase_ms", "packet_id", "start_sample",
                         "end_sample", "start_seconds", "end_seconds"))
        for run_id, (phase, events) in enumerate(runs):
            for event in events:
                writer.writerow((run_id, phase, event.packet_id,
                                 event.start_sample, event.end_sample,
                                 f"{event.start_seconds:.9f}",
                                 f"{event.end_seconds:.9f}"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export repeated phased-TX runs at 1x virtual time (offline)")
    parser.add_argument("--sample-rate", type=int, required=True)
    parser.add_argument("--period-ms", required=True)
    parser.add_argument("--phases-ms", nargs="+", required=True)
    parser.add_argument("--packet-samples", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args(argv)
    runs = plan_phase_sweep(
        sample_rate=args.sample_rate, period_ms=args.period_ms,
        phases_ms=args.phases_ms, packet_samples=args.packet_samples,
        count=args.count)
    write_sweep_csv(runs, args.csv)
    print(f"Created {len(runs)} phase runs, {sum(len(events) for _,events in runs)} events in {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
