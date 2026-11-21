"""Tests for the side-effect-free MQTT preview contract."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from tinygs_control_center.cli import main
from tinygs_control_center.mqtt_adapter import DopplerConfig, build_foff_dry_run


class TestMqttDryRun(unittest.TestCase):
    def test_foff_serialization_and_topics(self):
        result = build_foff_dry_run(
            "fabio", "IZ0IBA_GS2", DopplerConfig(125.5, 250, 1000))
        self.assertEqual(result["topic"],
                         "tinygs/fabio/IZ0IBA_GS2/cmnd/foff")
        self.assertEqual(result["ack_topic"],
                         "tinygs/fabio/IZ0IBA_GS2/stat/foff")
        self.assertEqual(result["mode"], "dry-run")
        self.assertFalse(result["published"])
        self.assertEqual(json.loads(result["payload"]), [125.5, 250, 1000])

    def test_preserves_nonzero_and_negative_offset(self):
        for offset in (155.0, -270.5, 0.0):
            with self.subTest(offset=offset):
                result = build_foff_dry_run(
                    "a", "b", DopplerConfig(offset, 100, 4000))
                self.assertEqual(json.loads(result["payload"])[0], offset)

    def test_rejects_unsafe_segments(self):
        for value in ("", "my/name", "a+b", "a#", "../foo", "contains space",
                      "line\nbreak"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    build_foff_dry_run(value, "station", DopplerConfig(0, 100, 1000))
                with self.assertRaises(ValueError):
                    build_foff_dry_run("user", value, DopplerConfig(0, 100, 1000))

    def test_rejects_invalid_parameters(self):
        for config in (
            DopplerConfig(float("nan"), 100, 1000),
            DopplerConfig(float("inf"), 100, 1000),
            DopplerConfig(1_000_000, 100, 1000),
            DopplerConfig(None, 100, 1000),
            DopplerConfig(0, 0, 1000),
            DopplerConfig(0, 65536, 1000),
            DopplerConfig(0, 100, 0),
            DopplerConfig(0, 100, 65536),
            DopplerConfig(0, 250.5, 1000),
            DopplerConfig(0, 100, True),
        ):
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    build_foff_dry_run("user", "station", config)

    @patch("tinygs_control_center.cli.urlopen", side_effect=AssertionError("network accessed"))
    def test_cli_preview_does_not_use_network_or_database(self, _urlopen):
        capture = io.StringIO()
        argv = [
            "--db", "/path/that/does/not/exist/catalog.sqlite",
            "mqtt-dry-run", "--mqtt-user", "fabio",
            "--station", "IZ0IBA_GS2",
            "--offset-hz", "-45.5",
            "--tolerance-hz", "250", "--refresh-ms", "1000",
        ]
        with contextlib.redirect_stdout(capture):
            self.assertEqual(main(argv), 0)
        parsed = json.loads(capture.getvalue())
        self.assertFalse(parsed["published"])
        self.assertEqual(json.loads(parsed["payload"]), [-45.5, 250, 1000])

    def test_cli_rejects_unsafe_refresh(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([
                "mqtt-dry-run", "--mqtt-user", "fabio",
                "--station", "IZ0IBA_GS2", "--offset-hz", "0",
                "--tolerance-hz", "250", "--refresh-ms", "0",
            ]), 1)


if __name__ == "__main__":
    unittest.main()
