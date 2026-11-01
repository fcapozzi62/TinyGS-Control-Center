import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tinygs_control_center.cli import fetch_celestrak, main


class TestCLI(unittest.TestCase):
    def test_import_and_show(self):
        data = {
            "NORAD_CAT_ID": 101140,
            "OBJECT_NAME": "FOSSASAT-2E27",
            "EPOCH": "2026-11-01T07:04:15",
            "MEAN_MOTION": 14.9184836,
            "ECCENTRICITY": 0.00060165,
            "INCLINATION": 52.9832,
        }
        with tempfile.TemporaryDirectory() as folder:
            location = Path(folder)
            source = location / "input.json"
            source.write_text(json.dumps(data), encoding="utf-8")
            db = location / "test.sqlite"
            self.assertEqual(main(["--db", str(db), "import-omm", str(source)]), 0)
            self.assertEqual(main(["--db", str(db), "show", "101140"]), 0)
            self.assertEqual(main(["--db", str(db), "show", "99999"]), 1)

    @patch("tinygs_control_center.cli.urlopen")
    def test_fetch_rejects_wrong_satellite(self, mock_urlopen):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self, _limit): return b'[{"NORAD_CAT_ID": 12345}]'
        mock_urlopen.return_value = Response()
        with self.assertRaises(ValueError):
            fetch_celestrak(101140)


if __name__ == "__main__":
    unittest.main()
