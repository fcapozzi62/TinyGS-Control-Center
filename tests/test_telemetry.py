"""Unit tests for TinyGS telemetry normalization and state replay."""
import contextlib
from datetime import datetime, timezone, timedelta
import io
import json
from pathlib import Path
import tempfile
import unittest

from tinygs_control_center.cli import main
from tinygs_control_center.telemetry import StationRegistry, decode_station_message


BASE = "tinygs/fabio/IZ0IBA_GS2/"
STAMP = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)


def encode(data):
    return json.dumps(data).encode("utf-8")


class TelemetryTests(unittest.TestCase):
    def test_welcome_status_rx_and_counters(self):
        registry = StationRegistry()
        registry.ingest(BASE + "tele/welcome", encode({
            "sat": "FOSSASAT-2E27", "version": 2610272, "ip": "secret",
            "mac": "secret"
        }), received_at=STAMP)
        registry.ingest(BASE + "stat/status", encode({
            "satellite": "FOSSASAT-2E27", "NORAD": 101140,
            "mode": "FSK", "frequency": 401.7,
            "frequency_offset": 125
        }), received_at=STAMP + timedelta(seconds=2))
        registry.ingest(BASE + "tele/rx", encode({
            "satellite": "FOSSASAT-2E27", "NORAD": 101140, "mode": "FSK",
            "frequency": 401.7, "f_doppler": -1200,
            "rssi": -122.5, "snr": -13, "frequency_error": 320,
            "crc_error": True, "noisy": True, "data": "sensitive raw bytes",
        }), received_at=STAMP + timedelta(seconds=5))
        state = registry.snapshots()[0]
        self.assertEqual(state["station_name"], "IZ0IBA_GS2")
        self.assertEqual(state["rx_count"], 1)
        self.assertEqual(state["crc_error_count"], 1)
        self.assertEqual(state["noisy_count"], 1)
        self.assertEqual(state["frequency_offset_hz"], 125)
        self.assertEqual(state["doppler_hz"], -1200)
        self.assertEqual(state["firmware_version"], 2610272)
        self.assertEqual(state["presence"], "observed_only")
        self.assertNotIn("ip", state)
        self.assertNotIn("mac", state)
        self.assertNotIn("data", state)

    def test_real_begine_profile_separated_from_status_and_rx(self):
        registry = StationRegistry()
        registry.ingest(BASE + "stat/status", encode({
            "satellite": "FrontierSat", "NORAD": 69015,
            "mode": "FSK", "frequency": 401.7,
        }), received_at=STAMP)
        registry.ingest(BASE + "tele/rx", encode({
            "satellite": "FrontierSat", "NORAD": 69015,
            "mode": "FSK", "frequency": 401.7, "rssi": -120.0,
        }), received_at=STAMP + timedelta(seconds=1))
        # Profile is based on a real command observed on IZ0IBA_GS2.
        event = registry.ingest(BASE + "cmnd/begine", encode({
            "mode": "LoRa", "freq": 400.45, "bw": 500, "sf": 9,
            "cr": 5, "sw": 18, "pwr": 5, "cl": 120, "pl": 8,
            "gain": 0, "crc": True, "fldro": 1, "sat": "Tianqi",
            "NORAD": 62366, "filter": [1, 0, 235],
            "tlx": "private-base64-orbit-profile",
        }), received_at=STAMP + timedelta(seconds=2))
        state = registry.snapshots()[0]
        self.assertEqual(event["kind"], "cmnd/begine")
        self.assertEqual(state["commanded_satellite"], "Tianqi")
        self.assertEqual(state["commanded_norad_cat_id"], 62366)
        self.assertEqual(state["commanded_frequency_mhz"], 400.45)
        self.assertEqual(state["commanded_sf"], 9)
        self.assertEqual(state["command_count"], 1)
        self.assertEqual(state["status_satellite"], "FrontierSat")
        self.assertEqual(state["last_rx_satellite"], "FrontierSat")
        self.assertEqual(state["satellite"], "FrontierSat")
        self.assertEqual(state["rx_count"], 1)
        self.assertNotIn("tlx", event)
        self.assertNotIn("tlx", state)
        self.assertNotIn("filter", state)
        # A later status proves a modem state independent from the command.
        registry.ingest(BASE + "stat/status", encode({
            "satellite": "Tianqi", "NORAD": 62366,
            "mode": "LoRa", "frequency": 400.45,
        }), received_at=STAMP + timedelta(seconds=3))
        state = registry.snapshots()[0]
        self.assertEqual(state["status_satellite"], "Tianqi")
        self.assertEqual(state["last_rx_satellite"], "FrontierSat")

    def test_new_command_clears_stale_profile(self):
        registry = StationRegistry()
        registry.ingest(BASE + "cmnd/begine", encode({
            "sat": "Tianqi", "mode": "LoRa", "freq": 400.45, "sf": 9,
        }), received_at=STAMP)
        registry.ingest(BASE + "cmnd/begine", encode({
            "sat": "TestFSK", "mode": "FSK", "freq": 435.0,
        }), received_at=STAMP + timedelta(seconds=1))
        state = registry.snapshots()[0]
        self.assertEqual(state["command_count"], 2)
        self.assertEqual(state["commanded_satellite"], "TestFSK")
        self.assertIsNone(state["commanded_sf"])

    def test_invalid_begine_does_not_create_state(self):
        self.assertIsNone(decode_station_message(
            BASE + "cmnd/begine", b"not-json", received_at=STAMP))
        self.assertIsNone(decode_station_message(
            BASE + "cmnd/begine", b"[]", received_at=STAMP))
        self.assertIsNone(decode_station_message(
            BASE + "cmnd/foff", b"[0,250,1000]", received_at=STAMP))

    def test_unknown_topics_and_bad_json_are_ignored(self):
        for topic, data in (
            ("tinygs/test/control-center", b"hi"),
            (BASE + "cmnd/foff", b"[125,250,1000]"),
            (BASE + "tele/rx", b"{not-json"),
            (BASE + "tele/rx", b"[]"),
            (BASE + "tele/rx", b"{}" * 40000),
            (BASE + "stat/foff", bytes([0, 0])),
        ):
            with self.subTest(topic=topic, data=data[:16]):
                self.assertIsNone(decode_station_message(topic, data))
        self.assertEqual(StationRegistry().snapshots(), [])

    def test_multiple_stations_and_out_of_order(self):
        registry = StationRegistry()
        registry.ingest(BASE + "stat/status", encode({"satellite": "NEW"}),
                        received_at=STAMP + timedelta(seconds=10))
        self.assertIsNone(registry.ingest(
            BASE + "stat/status", encode({"satellite": "OLD"}),
            received_at=STAMP))
        registry.ingest("tinygs/other/IZ0IBA_GS2/tele/welcome",
                        encode({"sat": "OTHER"}), received_at=STAMP)
        self.assertEqual(len(registry.snapshots()), 2)
        self.assertEqual(registry.snapshots()[0]["satellite"], "NEW")

    def test_null_and_invalid_numeric_types(self):
        event = decode_station_message(BASE + "tele/rx", encode({
            "rssi": True, "snr": "NaN", "f_doppler": float("nan"),
            "NORAD": "101140", "crc_error": "false",
        }), received_at=STAMP)
        self.assertIsNone(event["rssi_dbm"])
        self.assertIsNone(event["snr_db"])
        self.assertIsNone(event["doppler_hz"])
        self.assertIsNone(event["norad_cat_id"])
        self.assertIsNone(event["crc_error"])

    def test_reject_naive_datetime(self):
        with self.assertRaises(ValueError):
            decode_station_message(BASE + "tele/welcome",
                                   b"{}", received_at=datetime(2026, 11, 2))

    def test_cli_offline_replay(self):
        lines = [
            {"topic": BASE + "tele/welcome",
             "payload": {"version": 2610272, "sat": "TEST"}},
            {"topic": BASE + "tele/rx",
             "payload": {"satellite": "TEST", "NORAD": 101140,
                         "crc_error": False, "rssi": -120.0}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "messages.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in lines))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(["telemetry-replay", str(path)]), 0)
        states = json.loads(output.getvalue())
        self.assertEqual(states[0]["rx_count"], 1)
        self.assertEqual(states[0]["satellite"], "TEST")


if __name__ == "__main__":
    unittest.main()
