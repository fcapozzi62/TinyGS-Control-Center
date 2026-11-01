import json
import math
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tinygs_control_center.orbital import predict_passes, doppler_profile
from tinygs_control_center.stations import Station

class OrbitalTests(unittest.TestCase):
    def test_six_digit_omm_passes(self):
        fixture = Path(__file__).resolve().parents[1] / "examples/fossasat-2e27.json"
        omm = json.loads(fixture.read_text())[0]
        site = Station("rome-demo", 41.9, 12.5, 50, "Europe/Rome", 5)
        results = predict_passes(omm, site, datetime(2026,11,1,tzinfo=timezone.utc),
                                 hours=48, carrier_mhz=401.7)
        self.assertGreater(len(results), 0)
        for p in results:
            self.assertLess(p.aos_utc, p.tca_utc)
            self.assertLess(p.tca_utc, p.los_utc)
            self.assertGreaterEqual(p.max_elevation_deg, 5)
            self.assertTrue(math.isfinite(p.doppler_hz_at_tca))
            self.assertTrue(p.tca_local.endswith("+01:00"))

    def test_reject_naive_datetime(self):
        with self.assertRaises(ValueError):
            predict_passes({}, Station("x",41,12), datetime(2026,11,1))

    def test_doppler_full_pass_samples_and_sign(self):
        fixture = Path(__file__).resolve().parents[1] / "examples/fossasat-2e27.json"
        omm = json.loads(fixture.read_text())[0]
        site = Station("rome-demo", 41.9, 12.5, 50, "Europe/Rome", 0)
        windows = predict_passes(omm, site, datetime(2026,11,1,tzinfo=timezone.utc),
                                 hours=48, carrier_mhz=401.7)
        p = next(p for p in windows if p.max_elevation_deg > 60)
        parse = datetime.fromisoformat
        rows = doppler_profile(omm, site, parse(p.aos_utc), parse(p.tca_utc),
                              parse(p.los_utc), 401.7, 60)
        self.assertEqual(rows[0]["event"], "AOS")
        self.assertEqual(rows[-1]["event"], "LOS")
        self.assertEqual(len([r for r in rows if r["event"] == "TCA"]), 1)
        self.assertGreater(rows[0]["doppler_hz"], 0)
        self.assertLess(rows[-1]["doppler_hz"], 0)
        self.assertLess(abs(rows[-1]["elevation_deg"]), 0.2)
        self.assertTrue(all(math.isfinite(r["doppler_hz"]) for r in rows))

    def test_doppler_reject_bad_step(self):
        fixture = Path(__file__).resolve().parents[1] / "examples/fossasat-2e27.json"
        omm = json.loads(fixture.read_text())[0]
        site = Station("rome-demo", 41.9, 12.5, 50)
        from datetime import timedelta
        aos = datetime(2026,11,1,tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            doppler_profile(omm, site, aos, aos + timedelta(minutes=5),
                            aos + timedelta(minutes=10), 401.7, 0)
