"""Offline tests for MQTT read-only monitoring; no broker required."""
import contextlib
import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tinygs_control_center.cli import main
from tinygs_control_center.mqtt_monitor import (format_message, validate_monitor_settings,
                                                process_monitor_message, station_summary)
from tinygs_control_center.telemetry import StationRegistry


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

    def test_summary_ignores_test_topic_and_collects_real_telemetry(self):
        registry = StationRegistry()
        def msg(topic, payload):
            return SimpleNamespace(topic=topic, payload=payload, qos=0, retain=False)
        test = msg("tinygs/test/control-center", b"hello")
        self.assertEqual(process_monitor_message(test, registry)["payload"], "hello")
        self.assertEqual(station_summary(registry)["stations"], [])
        rx = msg("tinygs/fabio/IZ0IBA_GS2/tele/rx", json.dumps({
            "satellite": "FOSSASAT-2E27", "NORAD": 101140,
            "mode": "FSK", "frequency": 401.7,
            "rssi": -120.0, "crc_error": False,
        }).encode())
        rendered = process_monitor_message(rx, registry)
        self.assertEqual(rendered["topic"], rx.topic)
        summary = station_summary(registry)
        self.assertEqual(summary["type"], "station_summary")
        self.assertEqual(len(summary["stations"]), 1)
        self.assertEqual(summary["stations"][0]["rx_count"], 1)
        self.assertEqual(summary["stations"][0]["presence"], "observed_only")

    def test_monitor_summary_accepts_scheduler_command_without_rx(self):
        registry = StationRegistry()
        received = SimpleNamespace(
            topic="tinygs/account/IZ0IBA_GS2/cmnd/begine",
            payload=json.dumps({"sat": "Tianqi", "NORAD": 62366,
                                "mode": "LoRa", "freq": 400.45, "sf": 9}).encode(),
            qos=0, retain=False,
        )
        process_monitor_message(received, registry)
        summary = station_summary(registry)
        self.assertEqual(summary["stations"][0]["commanded_satellite"], "Tianqi")
        self.assertEqual(summary["stations"][0]["commanded_frequency_mhz"], 400.45)
        self.assertEqual(summary["stations"][0]["rx_count"], 0)
        self.assertIsNone(summary["stations"][0]["status_satellite"])

    @patch.dict("os.environ", {"TCC_MQTT_PASSWORD": "test-only"}, clear=True)
    @patch("tinygs_control_center.mqtt_monitor.monitor")
    def test_cli_summary_flag_is_forwarded(self, mocked_monitor):
        mocked_monitor.return_value = 0
        code = main(["mqtt-monitor", "--host", "127.0.0.1",
                     "--mqtt-user", "tinygs_local", "--summarize-stations",
                     "--timeout-sec", "2"])
        self.assertEqual(code, 0)
        self.assertTrue(mocked_monitor.call_args.args[-2])
        self.assertIsNone(mocked_monitor.call_args.args[-1])
        self.assertEqual(mocked_monitor.call_args.args[2], "tinygs_local")

    def test_cli_tls_ca_is_forwarded_without_network(self):
        with patch.dict("os.environ", {"TCC_MQTT_PASSWORD": "test-only"}, clear=True):
            with patch("tinygs_control_center.mqtt_monitor.monitor") as fake:
                fake.return_value = 0
                code = main(["mqtt-monitor", "--host", "mqtt.tinygs.com",
                             "--port", "8883", "--mqtt-user", "official-id",
                             "--cafile", "/tmp/synthetic-ca.pem",
                             "--summarize-stations"])
        self.assertEqual(code, 0)
        self.assertEqual(fake.call_args.args[-1], "/tmp/synthetic-ca.pem")

    @patch.dict("os.environ", {}, clear=True)
    def test_cli_requires_password_without_opening_network(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["mqtt-monitor", "--host", "127.0.0.1",
                                   "--mqtt-user", "tinygs_local"]), 1)


if __name__ == "__main__":
    unittest.main()
