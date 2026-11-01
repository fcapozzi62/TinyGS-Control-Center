import unittest

from tinygs_control_center.simulator import simulate_threshold


def sample(t, shift):
    return {"time_utc": f"2026-11-01T00:00:{t:02d}.000000+00:00",
            "time_local": f"2026-11-01T01:00:{t:02d}.000000+01:00",
            "doppler_hz": shift}


class SimulatorTests(unittest.TestCase):
    def test_threshold_and_retune_count(self):
        series = [sample(t, hz) for t, hz in enumerate([1000, 900, 800, 700, 600])]
        result = simulate_threshold(series, 200)
        self.assertEqual(result["initial_tune_at_aos"], 1)
        self.assertEqual(result["retunes_after_aos"], 2)
        self.assertEqual(result["max_abs_residual_hz"], 100)
        self.assertEqual(result["retunes"][0]["correction_hz"], -200)
        self.assertEqual(result["over_threshold_sample_count"], 0)

    def test_busy_defers_retune_and_allows_threshold_violation(self):
        series = [sample(t, hz) for t, hz in enumerate([1000, 900, 800, 700, 600])]
        result = simulate_threshold(series, 200, busy_period_s=5, busy_duration_s=3)
        self.assertEqual(result["retunes_after_aos"], 1)
        self.assertEqual(result["retunes"][0]["elapsed_s"], 3)
        self.assertEqual(result["deferred_sample_count"], 1)
        self.assertEqual(result["over_threshold_sample_count"], 1)
        self.assertEqual(result["max_abs_residual_hz"], 200)

    def test_bad_inputs(self):
        series = [sample(0, 100), sample(1, 90)]
        with self.assertRaises(ValueError):
            simulate_threshold([], 100)
        with self.assertRaises(ValueError):
            simulate_threshold(series, 0)
        with self.assertRaises(ValueError):
            simulate_threshold(series, 100, busy_period_s=5, busy_duration_s=5)
        with self.assertRaises(ValueError):
            simulate_threshold(series[::-1], 100)

    def test_time_precision_retained(self):
        series = [
            {"time_utc":"2026-11-01T00:00:00.100000+00:00","doppler_hz":100},
            {"time_utc":"2026-11-01T00:00:00.750000+00:00","doppler_hz":-300}
        ]
        result = simulate_threshold(series, 250)
        self.assertEqual(result["retunes"][0]["elapsed_s"], 0.65)


if __name__ == "__main__":
    unittest.main()
