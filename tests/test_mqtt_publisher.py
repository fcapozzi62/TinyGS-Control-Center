"""Unit tests for controlled publishing and CLI safety gates."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tinygs_control_center.cli import main
from tinygs_control_center.mqtt_publisher import publish_message
from tinygs_control_center.mqtt_command import decode_begine_ack


class MqttPublishTests(unittest.TestCase):
    def test_rejects_invalid_topic_and_credentials_before_network(self):
        for topic in ("", "tinygs/+/cmnd", "tinygs/#", "tinygs//test"):
            with self.subTest(topic=topic), self.assertRaises(ValueError):
                publish_message("localhost", 1883, "user", "secret", topic, "hello")
        with self.assertRaises(ValueError):
            publish_message("localhost", 1883, "user", "", "tinygs/test/probe", "hello")
        with self.assertRaises(ValueError):
            publish_message("localhost", 8883, "user", "secret", "tinygs/test/probe", "hello")

    @patch("tinygs_control_center.mqtt_publisher.publish_message")
    def test_fake_publisher_not_used_by_test_topic_validator(self, mocked):
        # Invalid scopes must be rejected before the transport is called.
        with contextlib.redirect_stderr(io.StringIO()):
            rc = main(["mqtt-publish-test", "--host", "localhost",
                       "--mqtt-user", "user", "--topic", "tinygs/a/b/cmnd/begine"])
        self.assertEqual(rc, 1)
        mocked.assert_not_called()

    @patch.dict("os.environ", {"TCC_MQTT_PASSWORD": "test-password"})
    @patch("tinygs_control_center.mqtt_publisher.publish_message")
    def test_probe_calls_publisher_only_on_test_topic(self, transport):
        transport.return_value = {"published": True, "receiver_ack": False}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = main(["mqtt-publish-test", "--host", "127.0.0.1",
                       "--mqtt-user", "localuser"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(output.getvalue())["published"], True)
        self.assertEqual(transport.call_args.args[4], "tinygs/test/control-center")

    def test_binary_ack_decoder(self):
        self.assertEqual(decode_begine_ack(b"\\x00\\x00"), 0)
        self.assertEqual(decode_begine_ack(b"\\x01\\x00"), 1)
        self.assertEqual(decode_begine_ack(b"\\xff\\x00"), 255)
        self.assertEqual(decode_begine_ack(b"\\x00\\x01"), 256)
        self.assertEqual(decode_begine_ack(b"\\xff\\xff"), 65535)
        for invalid in (b"", b"\\x00", b"\\x00\\x00\\x00", "ok"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                decode_begine_ack(invalid)

    @patch.dict("os.environ", {"TCC_MQTT_PASSWORD": "test-password"})
    @patch("tinygs_control_center.mqtt_command.publish_begine_and_wait")
    def test_cli_nonzero_or_missing_ack_is_failure(self, transport):
        profile = {
            "mode": "FSK", "sat": "ION-SCV-006", "NORAD": 52761,
            "freq": 401.41561, "bw": 7.3, "pl": 8, "pwr": 5,
            "br": 1.2, "fd": 0.6, "fsw": [147, 11, 81, 222],
            "ook": 0.7, "len": 255, "enc": 0, "fr": 10,
            "cSw": False, "tle": "GgFAARbHngAAM58O5YwRzaAAADk1K2rlC4IlXEz37wBhgQ==",
        }
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "profile.json"
            file.write_text(json.dumps(profile), encoding="utf-8")
            args = ["mqtt-begine-send", "--host", "127.0.0.1",
                    "--mqtt-user", "fabio", "--station", "IZ0IBA_GS1",
                    "--profile", str(file), "--confirm-tune"]
            for result in (
                {"published": True, "receiver_accepted": False, "ack_status": "timeout"},
                {"published": True, "receiver_accepted": False, "ack_status": "rejected", "ack_code": 1},
            ):
                with self.subTest(result=result):
                    transport.return_value = result
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(main(args), 1)

    def test_live_begine_requires_explicit_confirm(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                main(["mqtt-begine-send", "--host", "127.0.0.1",
                      "--mqtt-user", "localuser", "--station", "IZ0IBA_GS1",
                      "--profile", "/tmp/example.json"])
        self.assertEqual(raised.exception.code, 2)

    @patch.dict("os.environ", {"TCC_MQTT_PASSWORD": "test-password"})
    @patch("tinygs_control_center.mqtt_command.publish_begine_and_wait")
    def test_live_begine_uses_validated_payload_and_topic(self, transport):
        profile = {
            "mode": "FSK", "sat": "ION-SCV-006", "NORAD": 52761,
            "freq": 401.41561, "bw": 7.3, "pl": 8, "pwr": 5,
            "br": 1.2, "fd": 0.6, "fsw": [147, 11, 81, 222],
            "ook": 0.7, "len": 255, "enc": 0, "fr": 10,
            "cSw": False, "tle": "GgFAARbHngAAM58O5YwRzaAAADk1K2rlC4IlXEz37wBhgQ==",
        }
        transport.return_value = {"published": True, "receiver_ack": True, "receiver_accepted": True}
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "profile.json"
            file.write_text(json.dumps(profile), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = main([
                    "mqtt-begine-send", "--host", "127.0.0.1",
                    "--mqtt-user", "fabio", "--station", "IZ0IBA_GS1",
                    "--profile", str(file), "--confirm-tune"])
        self.assertEqual(rc, 0)
        args = transport.call_args.args
        self.assertEqual(args[4], "tinygs/fabio/IZ0IBA_GS1/cmnd/begine")
        self.assertEqual(json.loads(args[5]), profile)


if __name__ == "__main__":
    unittest.main()
