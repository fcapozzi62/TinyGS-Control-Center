"""Offline `begine` previews never send MQTT messages."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tinygs_control_center.begine import build_begine_dry_run
from tinygs_control_center.cli import main

# Manually saved TinyGS profile supplied by the station operator.
PROFILE = {
    "mode": "FSK", "sat": "ION-SCV-006", "NORAD": 52761,
    "freq": 401.41561, "bw": 7.3, "pl": 8, "pwr": 5,
    "br": 1.2, "fd": 0.6, "fsw": [147, 11, 81, 222],
    "ook": 0.7, "len": 255, "enc": 0, "fr": 10, "cSw": False,
    "tle": "GgFAARbHngAAM58O5YwRzaAAADk1K2rlC4IlXEz37wBhgQ==",
}


class BeginEDryRunTests(unittest.TestCase):
    def test_real_profile_serialized_without_modification(self):
        original = dict(PROFILE)
        result = build_begine_dry_run("fabio", "IZ0IBA_GS2", PROFILE)
        self.assertFalse(result["published"])
        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["orbit"], "tle")
        self.assertEqual(result["topic"], "tinygs/fabio/IZ0IBA_GS2/cmnd/begine")
        self.assertEqual(json.loads(result["payload"]), PROFILE)
        self.assertEqual(PROFILE, original)

    def test_invalid_orbit_rejected(self):
        for tle in ("not base64!", "YQ==", ""):
            profile = dict(PROFILE, tle=tle)
            with self.subTest(tle=tle), self.assertRaises(ValueError):
                build_begine_dry_run("fabio", "IZ0IBA_GS2", profile)

    def test_reject_oversized_arrays_and_unsafe_topic(self):
        for field in ("fsw", "filter"):
            with self.assertRaises(ValueError):
                build_begine_dry_run("fabio", "IZ0IBA_GS2",
                                     dict(PROFILE, **{field: list(range(9))}))
        with self.assertRaises(ValueError):
            build_begine_dry_run("fabio/#", "IZ0IBA_GS2", PROFILE)

    def test_missing_profile_fields_fail_closed(self):
        profile = dict(PROFILE)
        del profile["fd"]
        with self.assertRaisesRegex(ValueError, "fd"):
            build_begine_dry_run("fabio", "IZ0IBA_GS2", profile)

    @patch("tinygs_control_center.cli.urlopen", side_effect=AssertionError("network used"))
    def test_cli_offline_preview(self, _mock):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps(PROFILE), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["mqtt-begine-dry-run", "--mqtt-user", "fabio",
                               "--station", "IZ0IBA_GS2", "--profile", str(path)])
            self.assertEqual(result, 0)
            parsed = json.loads(output.getvalue())
            self.assertFalse(parsed["published"])
            self.assertEqual(json.loads(parsed["payload"]), PROFILE)


if __name__ == "__main__":
    unittest.main()
