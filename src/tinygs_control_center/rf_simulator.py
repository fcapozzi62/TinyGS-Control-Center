"""Offline sampled RF retune model; not an SX1262 hardware emulator.

Time is a virtual UTC clock. A retune blocks reception for its configured
latency. Packet windows are synthetic and do not assert real packet validity.
"""
from __future__ import annotations

from datetime import datetime
import math

SX1262_SYNTH_STEP_HZ = 32_000_000 / (2 ** 25)


def simulate_rf(samples: list[dict], threshold_hz: float, carrier_mhz: float, *,
                latency_ms: float = 6.2,
                synthesizer_step_hz: float = SX1262_SYNTH_STEP_HZ,
                packet_period_s: float = 0.0,
                packet_duration_ms: float = 0.0,
                defer_while_busy: bool = True) -> dict:
    """Simulate corrections on Doppler samples with radio-side limitations.

    All frequencies are quantized on a grid anchored to zero Hz, representing
    ideal synthesizer register rounding; actual reference crystal errors are
    excluded. The receiver is unavailable from start to completion of retune.
    Pre/post errors are evaluated at samples, not guaranteed between samples.
    """
    for name, value in (("threshold_hz", threshold_hz),
                        ("carrier_mhz", carrier_mhz),
                        ("latency_ms", latency_ms),
                        ("synthesizer_step_hz", synthesizer_step_hz),
                        ("packet_period_s", packet_period_s),
                        ("packet_duration_ms", packet_duration_ms)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if threshold_hz <= 0 or carrier_mhz <= 0 or synthesizer_step_hz <= 0:
        raise ValueError("Threshold, carrier and synthesizer step must be positive")
    if latency_ms < 0 or packet_period_s < 0 or packet_duration_ms < 0:
        raise ValueError("Latency and packet windows must be nonnegative")
    duration_s = packet_duration_ms / 1000
    if packet_period_s == 0 and packet_duration_ms != 0:
        raise ValueError("Packet duration requires a positive period")
    if packet_period_s and not 0 < duration_s < packet_period_s:
        raise ValueError("Packet duration must be less than period")
    if not samples:
        raise ValueError("No Doppler samples supplied")
    timestamps = [datetime.fromisoformat(s["time_utc"]) for s in samples]
    if any(t.tzinfo is None or t.utcoffset() is None for t in timestamps):
        raise ValueError("Samples must have timezone-aware timestamps")
    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("Sample times must strictly increase")
    shifts = [float(s["doppler_hz"]) for s in samples]
    if any(not math.isfinite(v) for v in shifts):
        raise ValueError("Doppler must be finite")
    origin = timestamps[0]
    base_hz = carrier_mhz * 1_000_000

    def quantize(target_hz: float) -> float:
        return math.floor(target_hz / synthesizer_step_hz + 0.5) * synthesizer_step_hz

    # A sample at the exact start of a window is busy, its end is not.
    def packet_busy(t: float) -> bool:
        return packet_period_s > 0 and (t % packet_period_s) < duration_s

    # Returns synthetic packet indices whose on-air intervals overlap a retune.
    def overlapping_packets(start: float, end: float) -> set[int]:
        if packet_period_s == 0 or end <= start:
            return set()
        n_start = max(0, math.floor((start - duration_s) / packet_period_s))
        n_end = math.ceil(end / packet_period_s)
        return {n for n in range(n_start, n_end)
                if n * packet_period_s < end
                and n * packet_period_s + duration_s > start}

    tuned_hz = quantize(base_hz + shifts[0])
    # The initial AOS tune is assumed complete, as in the ideal simulator.
    tuning_until_s = 0.0
    pending_hz = None
    retunes = []
    pre_errors = []
    post_errors = []
    busy_deferrals = 0
    latency_blocked_samples = 0
    interrupted_packets = set()
    for index, (timestamp, desired) in enumerate(zip(timestamps, shifts)):
        elapsed = (timestamp - origin).total_seconds()
        if pending_hz is not None and elapsed >= tuning_until_s:
            tuned_hz, pending_hz = pending_hz, None
        target_hz = base_hz + desired
        pre_error = target_hz - tuned_hz
        pre_errors.append(pre_error)
        if pending_hz is not None:
            latency_blocked_samples += 1
        elif index and abs(pre_error) >= threshold_hz:
            if defer_while_busy and packet_busy(elapsed):
                busy_deferrals += 1
            else:
                new_hz = quantize(target_hz)
                if new_hz != tuned_hz:
                    finish = elapsed + latency_ms / 1000
                    overlap = overlapping_packets(elapsed, finish)
                    interrupted_packets.update(overlap)
                    retunes.append({
                        "time_utc": timestamp.isoformat(timespec="microseconds"),
                        "elapsed_s": round(elapsed, 6),
                        "completion_s": round(finish, 6),
                        "frequency_hz": round(new_hz, 4),
                        "packet_overlap_count": len(overlap),
                    })
                    if latency_ms == 0:
                        tuned_hz = new_hz
                    else:
                        pending_hz = new_hz
                        tuning_until_s = finish
        # During retune the receiver is unavailable: do not interpret its
        # residual as a demodulation error. For diagnostics, report the last
        # frequency's hypothetical error separately from availability.
        post_errors.append(target_hz - tuned_hz)
    return {
        "strategy": "rf_threshold",
        "threshold_hz": threshold_hz,
        "latency_ms": latency_ms,
        "synthesizer_step_hz": synthesizer_step_hz,
        "packet_period_s": packet_period_s,
        "packet_duration_ms": packet_duration_ms,
        "defer_while_busy": defer_while_busy,
        "sample_count": len(samples),
        "initial_tune_at_aos": 1,
        "retunes_after_aos": len(retunes),
        "deferred_sample_count": busy_deferrals,
        "latency_blocked_sample_count": latency_blocked_samples,
        "unavailable_time_ms": round(len(retunes) * latency_ms, 4),
        "synthetic_packets_overlapped": len(interrupted_packets),
        "max_abs_pre_retune_error_hz": round(max(map(abs, pre_errors)), 2),
        "max_abs_post_retune_error_hz": round(max(map(abs, post_errors)), 2),
        "rms_post_retune_error_hz": round(
            math.sqrt(sum(e * e for e in post_errors) / len(post_errors)), 2),
        "retunes": retunes,
    }
