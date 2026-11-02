"""Pure offline virtual-clock simulation of threshold-based Doppler retuning.

A tick is a prediction sample. The output is a *hypothetical* frequency plan,
not a radio-control command. Packet-busy periods are artificial test fixtures,
not measured packet reception.
"""
from __future__ import annotations

from datetime import datetime
import math


def simulate_threshold(samples: list[dict], threshold_hz: float, *,
                       busy_period_s: int = 0, busy_duration_s: int = 0) -> dict:
    """Simulate zero-latency retunes at sampled timestamps.

    The desired shift (doppler_hz) comes from the orbital model. The tuned
    shift starts at AOS and is held until its difference exceeds threshold.
    Retunes are deferred while busy. Residual error is measured *after* a
    possible retune at every sample.
    """
    if not math.isfinite(threshold_hz) or threshold_hz <= 0:
        raise ValueError("threshold_hz must be positive and finite")
    if busy_period_s < 0 or busy_duration_s < 0:
        raise ValueError("busy intervals cannot be negative")
    if (busy_period_s == 0 and busy_duration_s != 0) or (
        busy_period_s != 0 and not 0 <= busy_duration_s < busy_period_s
    ):
        raise ValueError("Require 0 <= busy_duration_s < busy_period_s, or both zero")
    if not samples:
        raise ValueError("Doppler samples are empty")

    times = []
    for sample in samples:
        timestamp = datetime.fromisoformat(sample["time_utc"])
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("Sample timestamps must have timezone offsets")
        times.append(timestamp)
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Doppler samples must have strictly increasing timestamps")

    tuned = float(samples[0]["doppler_hz"])
    if not math.isfinite(tuned):
        raise ValueError("Non-finite Doppler shift")
    count = 0
    blocked_ticks = 0
    over_threshold_ticks = 0
    errors = []
    pre_retune_errors = []
    events = []
    origin = times[0]
    for index, (timestamp, sample) in enumerate(zip(times, samples)):
        desired = float(sample["doppler_hz"])
        if not math.isfinite(desired):
            raise ValueError("Non-finite Doppler shift")
        elapsed_s = (timestamp - origin).total_seconds()
        # Synthetic on-air window starts at AOS and repeats periodically.
        busy = (busy_period_s > 0 and
                (elapsed_s % busy_period_s) < busy_duration_s)
        pending_error = desired - tuned
        pre_retune_errors.append(pending_error)
        if index > 0 and abs(pending_error) >= threshold_hz:
            if busy:
                blocked_ticks += 1
            else:
                tuned = desired
                count += 1
                events.append({
                    "time_utc": sample["time_utc"],
                    "time_local": sample.get("time_local", sample["time_utc"]),
                    "elapsed_s": round(elapsed_s, 3),
                    "old_shift_hz": round(tuned - pending_error, 2),
                    "new_shift_hz": round(tuned, 2),
                    "correction_hz": round(pending_error, 2),
                    "reason": "threshold_exceeded",
                })
        residual = desired - tuned
        errors.append(residual)
        if abs(residual) >= threshold_hz:
            over_threshold_ticks += 1

    # Sample-based metrics; at a 1-second cadence they approximate elapsed time.
    return {
        "threshold_hz": threshold_hz,
        "retunes_after_aos": count,
        "initial_tune_at_aos": 1,
        "busy_period_s": busy_period_s,
        "busy_duration_s": busy_duration_s,
        "deferred_sample_count": blocked_ticks,
        "sample_count": len(samples),
        "over_threshold_sample_count": over_threshold_ticks,
        "max_abs_pre_retune_error_hz": round(max(abs(e) for e in pre_retune_errors), 2),
        "max_abs_residual_hz": round(max(abs(e) for e in errors), 2),
        "mean_abs_residual_hz": round(sum(abs(e) for e in errors)/len(errors), 2),
        "rms_residual_hz": round(math.sqrt(sum(e*e for e in errors)/len(errors)), 2),
        "retunes": events,
    }


def simulate_tinygs_legacy(samples: list[dict], *, tolerance_hz: float = 1200,
                           refresh_s: float = 4.0) -> dict:
    """Approximate the upstream TinyGS Doppler control defaults offline.

    At each refresh check, when abs(new-applied)>tolerance, set the applied
    Doppler to new-tolerance. Sampled checkpoints approximate firmware timing.
    """
    if not math.isfinite(tolerance_hz) or tolerance_hz <= 0:
        raise ValueError("tolerance_hz must be finite and positive")
    if not math.isfinite(refresh_s) or refresh_s <= 0:
        raise ValueError("refresh_s must be finite and positive")
    if not samples:
        raise ValueError("Doppler samples are empty")
    times = [datetime.fromisoformat(s["time_utc"]) for s in samples]
    if any(t.tzinfo is None or t.utcoffset() is None for t in times):
        raise ValueError("Sample timestamps require timezone offsets")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Sample timestamps must increase strictly")
    shifts = [float(s["doppler_hz"]) for s in samples]
    if any(not math.isfinite(v) for v in shifts):
        raise ValueError("Non-finite Doppler")
    origin = times[0]
    applied = shifts[0]
    checks = 0
    next_check_s = refresh_s
    retunes = []
    errors = []
    pre_retune_errors = []
    over = 0
    for t, s, desired in zip(times, samples, shifts):
        elapsed = (t - origin).total_seconds()
        pre_retune_errors.append(desired - applied)
        if elapsed + 1e-9 >= next_check_s:
            checks += 1
            if abs(desired - applied) > tolerance_hz:
                previous = applied
                applied = desired - tolerance_hz
                retunes.append({
                    "time_utc": s["time_utc"],
                    "time_local": s.get("time_local", s["time_utc"]),
                    "elapsed_s": round(elapsed, 3),
                    "old_shift_hz": round(previous, 2),
                    "new_shift_hz": round(applied, 2),
                    "correction_hz": round(applied - previous, 2),
                    "reason": "tinygs_legacy_freqTol_exceeded",
                })
            next_check_s = (math.floor((elapsed + 1e-9) / refresh_s) + 1) * refresh_s
        residual = desired - applied
        errors.append(residual)
        if abs(residual) >= tolerance_hz:
            over += 1
    return {
        "strategy": "tinygs_legacy",
        "tolerance_hz": tolerance_hz,
        "refresh_s": refresh_s,
        "checks_after_aos": checks,
        "retunes_after_aos": len(retunes),
        "initial_tune_at_aos": 1,
        "sample_count": len(samples),
        "over_tolerance_sample_count": over,
        "max_abs_pre_retune_error_hz": round(max(abs(e) for e in pre_retune_errors), 2),
        "max_abs_residual_hz": round(max(abs(e) for e in errors), 2),
        "mean_abs_residual_hz": round(sum(abs(e) for e in errors) / len(errors), 2),
        "rms_residual_hz": round(math.sqrt(sum(e*e for e in errors) / len(errors)), 2),
        "retunes": retunes,
    }
