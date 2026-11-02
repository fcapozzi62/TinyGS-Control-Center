"""Offline AX.100 Mode 5 Golay diagnostic, compatible with TinyGS Stage2.

The input contains hardware-demodulated bytes *after* the FSK syncword.
This tool does not perform Reed-Solomon or CRC verification. A Golay
candidate is not evidence that a satellite packet was recovered.
"""
from __future__ import annotations

import re

_H = (
    0x8008ED, 0x4001DB, 0x2003B5, 0x100769,
    0x080ED1, 0x040DA3, 0x020B47, 0x01068F,
    0x008D1D, 0x004A3B, 0x002477, 0x001FFE,
)


def encode_golay24(data: int) -> int:
    """Replicate TinyGS src/BitCode/golay24.cpp (systematic code)."""
    if type(data) is not int or not 0 <= data < 4096:
        raise ValueError("Golay data must be a 12-bit unsigned integer")
    parity = 0
    for row in _H:
        parity = (parity << 1) | ((row & data).bit_count() & 1)
    return (parity << 12) | data


_CODEWORDS = tuple(encode_golay24(x) for x in range(4096))


def decode_header(header: int) -> dict:
    """Find *all* nearest Golay words. Only distance <=3 is correctable."""
    if type(header) is not int or not 0 <= header < (1 << 24):
        raise ValueError("Header must be exactly 24 bits")
    distance = 25
    words = []
    for codeword in _CODEWORDS:
        current = (header ^ codeword).bit_count()
        if current < distance:
            distance, words = current, [codeword]
        elif current == distance:
            words.append(codeword)
    correctable = distance <= 3
    return {
        "raw_header_hex": f"{header:06X}",
        "minimum_distance_bits": distance,
        "golay_correctable": correctable,
        "nearest_candidate_count": len(words),
        "nearest_codewords_hex": [f"{x:06X}" for x in words],
        "decoded_frame_len": (words[0] & 255) if correctable else None,
        "decoded_flags_nibble": ((words[0] >> 8) & 15) if correctable else None,
    }


def parse_hex_dump(content: str) -> bytes:
    """Parse plain whitespace-separated byte pairs with optional # comments.

    Copy only the HEX columns from Stage2, not the printable ASCII column.
    """
    tokens = re.split(
        r"\s+", "\n".join(line.split("#", 1)[0]
                         for line in content.splitlines()).strip()
    )
    if not tokens or tokens == [""]:
        raise ValueError("Hex dump is empty")
    if any(re.fullmatch(r"[0-9a-fA-F]{2}", t) is None for t in tokens):
        raise ValueError("Use only whitespace-separated two-digit hex bytes")
    if len(tokens) > 65536:
        raise ValueError("Hex dump exceeds 65536 bytes")
    return bytes(int(t, 16) for t in tokens)


def _bits_window(data: bytes, start_bit: int) -> int:
    """Extract 24 bits with the MSB-first convention used by Stage2."""
    first, shift = divmod(start_bit, 8)
    block = int.from_bytes(data[first:first + 4].ljust(4, b"\0"), "big")
    return (block >> (8 - shift)) & 0xFFFFFF


def analyze_ax100(data: bytes, max_shift_bits: int = 31) -> dict:
    """Check the expected header and nearby bit windows, without changing RX.

    A length candidate is plausible only if 33 <= length <= 255 and
    no more than 3 trailing bytes would be missing from the RS block.
    This is a necessary condition, not RS or syncword verification.
    """
    if not isinstance(data, bytes) or len(data) < 4:
        raise ValueError("At least 4 post-sync bytes are required")
    if type(max_shift_bits) is not int or not 0 <= max_shift_bits <= 256:
        raise ValueError("max_shift_bits must be an integer from 0 to 256")
    limit = min(max_shift_bits, len(data) * 8 - 25)
    rows = []
    for shift in range(limit + 1):
        result = decode_header(_bits_window(data, shift))
        available = (len(data) * 8 - shift - 24) // 8
        frame_len = result["decoded_frame_len"]
        plausible = (frame_len is not None and 33 <= frame_len <= 255
                     and frame_len <= available + 3)
        rows.append({
            "bit_offset": shift,
            "byte_offset": shift // 8,
            "bit_offset_in_byte": shift % 8,
            "available_rs_bytes": available,
            "candidate_length_feasible": plausible,
            **result,
        })
    return {
        "format": "ax100-mode5-golay-diagnostic-v1",
        "input_bytes": len(data),
        "input_assumption": "post_syncword_hardware_payload",
        "golay_header_bit_order": "msb_first",
        "search_max_shift_bits": limit,
        "at_expected_offset": rows[0],
        "plausible_candidates": [r for r in rows if r["candidate_length_feasible"]],
        "all_offsets": rows,
        "rs_verified": False,
        "conclusion": ("golay_header_feasible_at_offset_0"
                       if rows[0]["candidate_length_feasible"]
                       else "no_validated_frame_at_expected_offset"),
        "warning": (
            "Golay proximity or plausible length does not prove frame sync "
            "or successful Reed-Solomon decoding; random data yields matches. "
            "Only correlated RF reception plus RS/CRC validation can confirm a packet."
        ),
    }
