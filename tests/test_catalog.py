import json
import tempfile
import unittest
from pathlib import Path

from tinygs_control_center.catalog import OrbitalCatalog, parse_omm_json, validate_omm


RECORD = {
    "OBJECT_NAME": "FOSSASAT-2E27",
    "OBJECT_ID": "2026-237AF",
    "NORAD_CAT_ID": 101140,
    "EPOCH": "2026-11-01T07:04:15.758112",
    "MEAN_MOTION": 14.9184836,
    "ECCENTRICITY": 0.00060165,
    "INCLINATION": 52.9832,
    "BSTAR": 0.000047099117,
}


class TestCatalog(unittest.TestCase):
    def test_six_digit_norad_id_and_history(self):
        with tempfile.TemporaryDirectory() as folder:
            with OrbitalCatalog(Path(folder) / "catalog.sqlite") as catalog:
                self.assertEqual(catalog.import_records([RECORD], "celestrak"), (1, 1))
                self.assertEqual(catalog.import_records([RECORD], "celestrak"), (1, 0))
                later = dict(RECORD, EPOCH="2026-11-02T07:04:15.758112")
                self.assertEqual(catalog.import_records([later], "celestrak"), (1, 1))
                self.assertEqual(catalog.list_satellites()[0]["element_sets"], 2)
                latest = catalog.latest(101140)
                self.assertEqual(latest["omm"]["NORAD_CAT_ID"], 101140)
                self.assertTrue(latest["epoch"].startswith("2026-11-02"))
                self.assertEqual(latest["source"], "celestrak")

    def test_transactional_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            with OrbitalCatalog(Path(folder) / "catalog.sqlite") as catalog:
                invalid = dict(RECORD, MEAN_MOTION=-1)
                with self.assertRaises(ValueError):
                    catalog.import_records([RECORD, invalid], "test")
                self.assertEqual(catalog.list_satellites(), [])

    def test_json_and_validation(self):
        self.assertEqual(parse_omm_json(json.dumps(RECORD)), [RECORD])
        self.assertEqual(parse_omm_json(json.dumps([RECORD])), [RECORD])
        self.assertEqual(validate_omm(RECORD)["norad"], 101140)
        with self.assertRaises(ValueError):
            validate_omm(dict(RECORD, NORAD_CAT_ID="A1140"))
        with self.assertRaises(ValueError):
            validate_omm(dict(RECORD, ECCENTRICITY=1.2))
        with self.assertRaises(ValueError):
            parse_omm_json('"invalid"')

    def test_utc_normalization(self):
        record = dict(RECORD, EPOCH="2026-11-01T08:04:15+01:00")
        self.assertEqual(
            validate_omm(record)["epoch"],
            "2026-11-01T07:04:15.000000+00:00",
        )


if __name__ == "__main__":
    unittest.main()
