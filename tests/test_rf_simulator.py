import unittest

from tinygs_control_center.rf_simulator import (
    SX1262_SYNTH_STEP_HZ, simulate_rf,
)


def samples(shifts, spacing_s=1):
    from datetime import datetime, timedelta, timezone
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    return [
        {"time_utc": (start + timedelta(seconds=i * spacing_s)).isoformat(),
         "doppler_hz": shift}
        for i, shift in enumerate(shifts)
    ]


class RFSimulatorTests(unittest.TestCase):
    def test_default_synth_step(self):
        self.assertAlmostEqual(SX1262_SYNTH_STEP_HZ, 0.95367431640625)

    def test_zero_latency_completes_in_sample(self):
        result = simulate_rf(samples([0, 300, 300]), 100, 401.7, latency_ms=0,
                             synthesizer_step_hz=1)
        self.assertEqual(result["retunes_after_aos"], 1)
        self.assertEqual(result["max_abs_pre_retune_error_hz"], 300)
        self.assertEqual(result["max_abs_post_retune_error_hz"], 0)

    def test_nonzero_latency_blocks_receiver_until_completion(self):
        result = simulate_rf(samples([0, 300, 300], spacing_s=0.005),
                             100, 401.7, latency_ms=6.2,
                             synthesizer_step_hz=1)
        self.assertEqual(result["retunes_after_aos"], 1)
        self.assertEqual(result["latency_blocked_sample_count"], 1)
        self.assertEqual(result["unavailable_time_ms"], 6.2)
        self.assertEqual(result["retunes"][0]["completion_s"], 0.0112)

    def test_synthesizer_rounding_residual(self):
        result = simulate_rf(samples([0, 3, 3]), 2, 401.7, latency_ms=0,
                             synthesizer_step_hz=2)
        self.assertEqual(result["retunes_after_aos"], 1)
        self.assertEqual(result["max_abs_post_retune_error_hz"], 1)

    def test_defer_busy_and_resume(self):
        result = simulate_rf(samples([0, 200, 200, 200, 200]),
                             100, 401.7, latency_ms=6.2,
                             synthesizer_step_hz=1,
                             packet_period_s=3, packet_duration_ms=1500)
        self.assertEqual(result["deferred_sample_count"], 1)
        self.assertEqual(result["retunes_after_aos"], 1)
        self.assertEqual(result["retunes"][0]["elapsed_s"], 2)
        self.assertEqual(result["synthetic_packets_overlapped"], 0)

    def test_retune_collides_with_next_packet(self):
        result = simulate_rf(samples([0, 300]), 100, 401.7,
                             latency_ms=300, synthesizer_step_hz=1,
                             packet_period_s=1.1, packet_duration_ms=100,
                             defer_while_busy=True)
        self.assertEqual(result["retunes_after_aos"], 1)
        self.assertEqual(result["synthetic_packets_overlapped"], 1)
        self.assertEqual(result["retunes"][0]["packet_overlap_count"], 1)

    def test_defer_disabled_interrupts_active_packet(self):
        result = simulate_rf(samples([0, 300]), 100, 401.7,
                             latency_ms=6.2, synthesizer_step_hz=1,
                             packet_period_s=1, packet_duration_ms=500,
                             defer_while_busy=False)
        self.assertEqual(result["retunes_after_aos"], 1)
        self.assertEqual(result["synthetic_packets_overlapped"], 1)

    def test_invalid_parameters_and_samples(self):
        series = samples([0, 100])
        for kwargs in ({"latency_ms": -1}, {"synthesizer_step_hz": 0},
                       {"packet_period_s": 1, "packet_duration_ms": 1000},
                       {"packet_duration_ms": 5},
                       {"threshold_hz": float("nan")}):
            with self.subTest(kwargs=kwargs):
                threshold = kwargs.pop("threshold_hz", 100)
                with self.assertRaises(ValueError):
                    simulate_rf(series, threshold, 401.7, **kwargs)
        with self.assertRaises(ValueError):
            simulate_rf(series[::-1], 100, 401.7)

    def test_zero_doppler_change_never_retunes(self):
        result = simulate_rf(samples([500] * 10), 100, 401.7)
        self.assertEqual(result["retunes_after_aos"], 0)
        self.assertEqual(result["synthetic_packets_overlapped"], 0)
