"""Pure TinyGS MQTT protocol serializer for offline validation only.

No broker client, socket, credentials or radio-control side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re


_TOPIC_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class DopplerConfig:
    """Station-calibrated runtime Doppler parameters.

    The offset is deliberately mandatory: 'foff' replaces it even when only
    a Doppler threshold is intended to change.
    """

    calibration_offset_hz: float
    tolerance_hz: int
    refresh_ms: int

    def validate(self) -> None:
        offset = self.calibration_offset_hz
        if isinstance(offset, bool) or not isinstance(offset, (int, float)):
            raise ValueError("calibration_offset_hz must be a known numeric value")
        if not math.isfinite(offset):
            raise ValueError("calibration_offset_hz must be finite")
        # Guard against accidental MHz/kHz units. This is an application
        # safety policy, not a verified TinyGS firmware limit.
        if abs(offset) > 100_000:
            raise ValueError("calibration_offset_hz exceeds dry-run safety limit (100000 Hz)")
        for name, value in (("tolerance_hz", self.tolerance_hz),
                            ("refresh_ms", self.refresh_ms)):
            if type(value) is not int or not (1 <= value <= 65535):
                raise ValueError(f"{name} must be an integer in 1..65535")


def _segment(value: str, name: str) -> str:
    if not isinstance(value, str) or not _TOPIC_SEGMENT.fullmatch(value):
        raise ValueError(f"{name} must be a single safe MQTT topic segment")
    return value


def build_foff_dry_run(mqtt_user: str, station_name: str,
                       config: DopplerConfig) -> dict:
    """Build a safe preview of the existing TinyGS 'foff' message.

    Does not publish messages; output is a self-describing preview, not a
    confirmed device setting. No default calibration offset is supplied.
    """
    user = _segment(mqtt_user, "mqtt_user")
    station = _segment(station_name, "station_name")
    config.validate()
    topic_root = f"tinygs/{user}/{station}"
    return {
        "mode": "dry-run",
        "published": False,
        "protocol": "tinygs-foff-runtime",
        "topic": f"{topic_root}/cmnd/foff",
        "ack_topic": f"{topic_root}/stat/foff",
        "payload": json.dumps([
            float(config.calibration_offset_hz),
            config.tolerance_hz,
            config.refresh_ms,
        ], separators=(",", ":"), allow_nan=False),
        "parameters": {
            "calibration_offset_hz": float(config.calibration_offset_hz),
            "doppler_tolerance_hz": config.tolerance_hz,
            "refresh_ms": config.refresh_ms,
        },
        "note": (
            "This previews an in-memory firmware setting only. "
            "No MQTT connection, message transmission or device verification."
        ),
    }
