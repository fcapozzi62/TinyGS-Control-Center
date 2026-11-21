import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tinygs_control_center.phase_sweep import plan_phase_sweep, write_sweep_csv


class PhaseSweepTests(unittest.TestCase):
    def test_phase_sweep_shares_origin_and_packet_ids(self):
        runs = plan_phase_sweep(sample_rate=192000, period_ms="2000",
                                phases_ms=["0", "100", "200"],
                                packet_samples=38400, count=3)
        self.assertEqual([phase for phase, _ in runs], ["0", "100", "200"])
        self.assertEqual([e.start_sample for e in runs[0][1]],
                         [0, 384000, 768000])
        self.assertEqual([e.start_sample for e in runs[1][1]],
                         [19200, 403200, 787200])
        self.assertEqual([e.start_sample for e in runs[2][1]],
                         [38400, 422400, 806400])
        self.assertEqual([e.packet_id for e in runs[2][1]], [0, 1, 2])

    def test_fractional_phase(self):
        runs = plan_phase_sweep(sample_rate=192000, period_ms="2000",
                                phases_ms=["0.25"], packet_samples=4, count=1)
        self.assertEqual(runs[0][1][0].start_sample, 48)

    def test_reject_duplicate_or_invalid_phases(self):
        for phases in ([], ["0", "0.0"], ["-1"], ["2000"], ["nan"]):
            with self.subTest(phases=phases), self.assertRaises(ValueError):
                plan_phase_sweep(sample_rate=192000, period_ms="2000",
                                 phases_ms=phases, packet_samples=10, count=2)

    def test_csv_includes_run_id(self):
        runs = plan_phase_sweep(sample_rate=192000, period_ms="2000",
                                phases_ms=["0", "100"], packet_samples=100,
                                count=2)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "sweep.csv"
            write_sweep_csv(runs, path)
            with path.open(newline="", encoding="utf-8") as stream:
                data = list(csv.DictReader(stream))
        self.assertEqual(len(data), 4)
        self.assertEqual([row["run_id"] for row in data], ["0", "0", "1", "1"])
        self.assertEqual(data[2]["start_sample"], "19200")


if __name__ == "__main__":
    unittest.main()
