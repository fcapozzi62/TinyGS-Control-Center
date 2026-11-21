"""Encode a standard two-line TLE for TinyGS AioP13's 34-byte orbit format.

The firmware receives these bytes as Base64 in the MQTT `begine.tle` field.
No MQTT connections, radio changes, or disk writes are performed here.
"""
from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _checksum(line: str) -> int:
    return sum(int(ch) if ch.isdigit() else 1 if ch == "-" else 0
               for ch in line[:68]) % 10


def _scaled(text: str, multiplier: int, name: str) -> int:
    try:
        number = Decimal(text.strip())
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {name}: {text!r}") from exc
    if not number.is_finite():
        raise ValueError(f"Non-finite {name}")
    return int((number * multiplier).to_integral_value(rounding=ROUND_HALF_UP))


def _unsigned(value: int, nbytes: int, name: str) -> bytes:
    if not 0 <= value < 1 << (nbytes * 8):
        raise ValueError(f"{name} does not fit in {nbytes} bytes: {value}")
    return value.to_bytes(nbytes, "big")


def encode_tinygs_tle(line1: str, line2: str) -> bytes:
    """Encode TLE lines into the exact AioP13 34-byte big-endian layout.

    AioP13 reads the first mean-motion derivative as a signed 32-bit
    two's-complement quantity. This is TLE line 1's n-dot / 2 field.
    Quantities are rounded at their on-air storage precision.
    """
    lines = (line1.rstrip("\r\n"), line2.rstrip("\r\n"))
    if any(len(line) != 69 for line in lines):
        raise ValueError("Each TLE line must contain exactly 69 characters")
    if lines[0][0] != "1" or lines[1][0] != "2":
        raise ValueError("Expected TLE line numbers 1 and 2")
    if lines[0][2:7] != lines[1][2:7]:
        raise ValueError("TLE catalog identifiers do not match")
    for index, line in enumerate(lines, start=1):
        if not line[68].isdigit() or _checksum(line) != int(line[68]):
            raise ValueError(f"Invalid checksum in TLE line {index}")

    l1, l2 = lines
    year = int(l1[18:20])
    day = int(l1[20:23])
    fraction = _scaled("0." + l1[24:32], 100_000_000, "epoch fraction")
    if not 1 <= day <= 366 or not 0 <= fraction < 100_000_000:
        raise ValueError("Invalid TLE epoch day or fraction")

    ndot_half = _scaled(l1[33:43], 100_000_000, "mean-motion derivative")
    if not -(1 << 31) <= ndot_half < (1 << 31):
        raise ValueError("Mean-motion derivative does not fit signed int32")

    incl = _scaled(l2[8:16], 10_000, "inclination")
    raan = _scaled(l2[17:25], 10_000, "RAAN")
    ecc_text = l2[26:33]
    if len(ecc_text) != 7 or not ecc_text.isdigit():
        raise ValueError("Invalid eccentricity field")
    eccentricity = int(ecc_text)
    argp = _scaled(l2[34:42], 10_000, "argument of perigee")
    anomaly = _scaled(l2[43:51], 10_000, "mean anomaly")
    motion = _scaled(l2[52:63], 100_000_000, "mean motion")
    revolution = int(l2[63:68])

    if not 0 <= incl <= 1_800_000:
        raise ValueError("Inclination must be 0..180 degrees")
    for name, value in (("RAAN", raan), ("perigee argument", argp),
                        ("mean anomaly", anomaly)):
        if not 0 <= value < 3_600_000:
            raise ValueError(f"{name} must be within 0..360 degrees")
    if not 0 < motion < (1 << 31):
        raise ValueError("Mean motion must be positive and fit signed int32")

    data = b"".join((
        _unsigned(year, 1, "epoch year"),
        _unsigned(day, 2, "epoch day"),
        _unsigned(fraction, 4, "epoch fraction"),
        ndot_half.to_bytes(4, "big", signed=True),
        _unsigned(incl, 3, "inclination"),
        _unsigned(raan, 3, "RAAN"),
        _unsigned(eccentricity, 4, "eccentricity"),
        _unsigned(argp, 3, "argument of perigee"),
        _unsigned(anomaly, 3, "mean anomaly"),
        _unsigned(motion, 4, "mean motion"),
        _unsigned(revolution, 3, "revolution number"),
    ))
    if len(data) != 34:
        raise AssertionError("TinyGS TLE must be exactly 34 bytes")
    return data


def encode_tinygs_tle_base64(line1: str, line2: str) -> str:
    """Return the 48-character Base64 value for MQTT `begine.tle`."""
    return base64.b64encode(encode_tinygs_tle(line1, line2)).decode("ascii")
