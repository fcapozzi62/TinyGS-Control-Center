import unittest

from tinygs_control_center.simulator import simulate_threshold, simulate_tinygs_legacy


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

class LegacyTests(unittest.TestCase):
    def test_four_second_checks_and_downward_overshoot(self):
        data = [sample(t, 6000-100*t) for t in range(17)]
        out = simulate_tinygs_legacy(data, tolerance_hz=1200, refresh_s=4)
        self.assertEqual(out["checks_after_aos"], 4)
        self.assertEqual(out["retunes_after_aos"], 1)
        self.assertEqual(out["retunes"][0]["elapsed_s"], 16)
        self.assertEqual(out["retunes"][0]["new_shift_hz"], 3200)
        self.assertEqual(out["retunes"][0]["correction_hz"], -2800)

    def test_strict_threshold_and_ascending(self):
        data = [sample(t, 100*t) for t in range(13)]
        out = simulate_tinygs_legacy(data, tolerance_hz=400, refresh_s=4)
        self.assertEqual(out["retunes"][0]["elapsed_s"], 8)
        self.assertEqual(out["retunes"][0]["new_shift_hz"], 400)
        self.assertEqual(out["retunes_after_aos"], 2)
        self.assertEqual(out["retunes"][1]["elapsed_s"], 12)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            simulate_tinygs_legacy([], tolerance_hz=1200)
        with self.assertRaises(ValueError):
            simulate_tinygs_legacy([sample(0,0)], refresh_s=0)

class ValidationDiagnosticsTests(unittest.TestCase):
    def test_instant_retune_does_not_hide_pre_retune_error(self):
        data = [sample(0, 0), sample(1, 300), sample(2, 300)]
        output = simulate_threshold(data, 100)
        self.assertEqual(output["retunes_after_aos"], 1)
        self.assertEqual(output["max_abs_residual_hz"], 0)
        self.assertEqual(output["max_abs_pre_retune_error_hz"], 300)

    def test_busy_window_exposes_uncompensated_error(self):
        data = [sample(t, -100*t) for t in range(8)]
        output = simulate_threshold(data, 200, busy_period_s=5, busy_duration_s=3)
        self.assertGreater(output["max_abs_pre_retune_error_hz"],
                           output["max_abs_residual_hz"] - 0.01)
        self.assertGreater(output["deferred_sample_count"], 0)
        self.assertTrue(all(event["elapsed_s"] % 5 >= 3
                            for event in output["retunes"]))

    def test_zero_change_has_no_retunes_or_residual(self):
        data = [sample(t, 1200) for t in range(10)]
        for tolerance in (100, 250, 500):
            out = simulate_threshold(data, tolerance)
            self.assertEqual(out["retunes_after_aos"], 0)
            self.assertEqual(out["max_abs_pre_retune_error_hz"], 0)
            self.assertEqual(out["rms_residual_hz"], 0)

    def test_legacy_reports_pre_retune_peak_separately(self):
        data = [sample(t, 6000-100*t) for t in range(17)]
        out = simulate_tinygs_legacy(data, tolerance_hz=1200, refresh_s=4)
        self.assertEqual(out["max_abs_pre_retune_error_hz"], 1600)
        self.assertEqual(out["retunes_after_aos"], 1)
