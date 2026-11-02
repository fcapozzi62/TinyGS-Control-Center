"""Offline tests for MQTT read-only monitoring; no broker required."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from tinygs_control_center.cli import main
from tinygs_control_center.mqtt_monitor import format_message, validate_monitor_settings


class TestMqttMonitor(unittest.TestCase):
    def test_format_text(self):
        item = format_message("tinygs/test/control-center", b"hello", 0, False)
        self.assertEqual(item["payload"], "hello")
        self.assertEqual(item["encoding"], "utf-8")
        self.assertEqual(item["payload_size"], 5)

    def test_format_binary(self):
        item = format_message("tinygs/a/b/stat/foff", bytes([0, 255]), 0, False)
        self.assertEqual(item["encoding"], "hex")
        self.assertEqual(item["payload_hex"], "00ff")

    def test_valid_topic_filters(self):
        for topic in ("tinygs/#", "tinygs/+/+/tele/#", "tinygs/a/b/stat/foff"):
            validate_monitor_settings("192.168.1.61", 1883, topic, 5, 0)

    def test_rejects_invalid_settings(self):
        cases = [
            ("", 1883, "tinygs/#", 30, 0),
            ("x", 0, "tinygs/#", 30, 0),
            ("x", 1883, "tinygs/a#b", 30, 0),
            ("x", 1883, "tinygs/#/tail", 30, 0),
            ("x", 1883, "tinygs/a+", 30, 0),
            ("x", 1883, "tinygs/#", 0, 0),
            ("x", 1883, "tinygs/#", 5, -1),
        ]
        for params in cases:
            with self.subTest(params=params):
                with self.assertRaises(ValueError):
                    validate_monitor_settings(*params)

    @patch.dict("os.environ", {}, clear=True)
    def test_cli_requires_password_without_opening_network(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["mqtt-monitor", "--host", "127.0.0.1",
                                   "--mqtt-user", "tinygs_local"]), 1)


if __name__ == "__main__":
    unittest.main()
