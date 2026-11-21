"""Side-effect-free preview of TinyGS' existing MQTT `cmnd/begine` payload.

Input is a complete modem profile captured from TinyGS or maintained locally.
An optional two-line TLE replaces any pre-existing orbital field. This module
never publishes to a broker or modifies the firmware.
"""
from __future__ import annotations

import base64
import json
import math

from .mqtt_adapter import _segment
from .tle_codec import encode_tinygs_tle_base64

_REQUIRED_COMMON = ("mode", "sat", "NORAD", "freq", "bw", "pl", "pwr")
_REQUIRED_FSK = ("br", "fd", "fsw", "ook", "len", "enc", "fr", "cSw")
_REQUIRED_LORA = ("sf", "cr", "sw", "gain", "crc", "fldro")
_NUMERIC = ("freq", "bw", "br", "fd", "ook")


def _validate_profile(profile: dict) -> None:
    if not isinstance(profile, dict):
        raise ValueError("Profile must be a JSON object")
    mode = profile.get("mode")
    if mode not in ("FSK", "LoRa"):
        raise ValueError("Only FSK and LoRa profiles are supported")
    required = _REQUIRED_COMMON + (_REQUIRED_FSK if mode == "FSK" else _REQUIRED_LORA)
    missing = [key for key in required if key not in profile]
    if missing:
        raise ValueError(f"Missing modem profile fields: {', '.join(missing)}")
    satellite = profile["sat"]
    if not isinstance(satellite, str) or not satellite or len(satellite.encode("utf-8")) >= 25:
        raise ValueError("Satellite name must fit the firmware's 24-byte buffer")
    if type(profile["NORAD"]) is not int or profile["NORAD"] <= 0:
        raise ValueError("NORAD must be a positive integer")
    for key in _NUMERIC:
        if key in profile:
            val = profile[key]
            if isinstance(val, bool) or not isinstance(val, (float, int)) or not math.isfinite(val):
                raise ValueError(f"{key} must be finite and numeric")
    if profile["freq"] <= 0 or profile["bw"] <= 0:
        raise ValueError("RF frequency and bandwidth must be positive")
    if mode == "FSK" and (profile["br"] <= 0 or profile["fd"] < 0):
        raise ValueError("FSK bit rate must be positive and deviation nonnegative")
    for name in ("fsw", "filter"):
        val = profile.get(name, [])
        if not isinstance(val, list) or len(val) > 8 or any(
            type(item) is not int or not 0 <= item <= 255 for item in val
        ):
            raise ValueError(f"{name} must contain at most 8 octets")
    if "tle" in profile and "tlx" in profile:
        raise ValueError("Profile must not contain both tle and tlx")
    for name in ("tle", "tlx"):
        if name in profile:
            encoded = profile[name]
            if not isinstance(encoded, str):
                raise ValueError(f"{name} must be a Base64 string")
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise ValueError(f"{name} is not valid Base64") from exc
            if len(decoded) != 34 or decoded[0] == 0:
                raise ValueError(f"{name} must decode to 34 orbit bytes")


def build_begine_dry_run(
    mqtt_user: str,
    station_name: str,
    profile: dict,
    tle_lines: tuple[str, str] | None = None,
) -> dict:
    """Serialize a complete profile to an offline MQTT command preview.

    When tle_lines is supplied, the original orbital field is replaced by
    freshly encoded P13 data and active Doppler (tle) is selected.
    """
    user = _segment(mqtt_user, "mqtt_user")
    station = _segment(station_name, "station_name")
    if not isinstance(profile, dict):
        raise ValueError("Profile must be an object")
    modem = dict(profile)
    if tle_lines is not None:
        if len(tle_lines) != 2:
            raise ValueError("Two TLE lines are required")
        modem.pop("tle", None)
        modem.pop("tlx", None)
        modem["tle"] = encode_tinygs_tle_base64(*tle_lines)
    _validate_profile(modem)
    payload = json.dumps(modem, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return {
        "mode": "dry-run",
        "published": False,
        "protocol": "tinygs-begine",
        "topic": f"tinygs/{user}/{station}/cmnd/begine",
        "payload": payload,
        "payload_bytes": len(payload.encode("utf-8")),
        "satellite": modem["sat"],
        "norad": modem["NORAD"],
        "orbit": "tle" if "tle" in modem else "tlx" if "tlx" in modem else "none",
        "note": "Offline preview only; no MQTT connection or receiver tuning.",
    }
