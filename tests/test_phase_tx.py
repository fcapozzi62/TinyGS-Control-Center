import unittest
from tinygs_control_center.phase_tx import plan_tx


class PhaseTxTests(unittest.TestCase):
    def test_phase_100_ms_at_192ksps(self):
        events = plan_tx(sample_rate=192000, period_ms='2000', phase_ms='100',
                         packet_samples=38400, count=3)
        self.assertEqual([e.start_sample for e in events], [19200, 403200, 787200])
        self.assertEqual([e.packet_id for e in events], [0, 1, 2])
        self.assertEqual(events[0].end_sample, 57600)

    def test_phase_zero(self):
        events = plan_tx(sample_rate=192000, period_ms='2000', phase_ms='0',
                         packet_samples=100, count=2)
        self.assertEqual([e.start_sample for e in events], [0, 384000])

    def test_refuse_overlap_and_bad_phase(self):
        for kw in [dict(period_ms='100', phase_ms='100', packet_samples=1),
                   dict(period_ms='100', phase_ms='0', packet_samples=20000),
                   dict(period_ms='100', phase_ms='-1', packet_samples=1)]:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                plan_tx(sample_rate=192000, count=2, **kw)

    def test_repeated_runs_are_identical(self):
        args = dict(sample_rate=192000, period_ms='2000', phase_ms='200',
                    packet_samples=38400, count=10)
        self.assertEqual(plan_tx(**args), plan_tx(**args))

    def test_fractional_phase(self):
        events = plan_tx(sample_rate=192000, period_ms='2000', phase_ms='0.25',
                         packet_samples=100, count=1)
        self.assertEqual(events[0].start_sample, 48)


if __name__ == '__main__':
    unittest.main()
