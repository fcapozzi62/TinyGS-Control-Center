"""Offline tests for the AioP13 34-byte TLE wire format."""
import base64
import unittest

from tinygs_control_center.tle_codec import (
    encode_tinygs_tle,
    encode_tinygs_tle_base64,
)


def _line(number: str, fields: list[tuple[int, int, str]]) -> str:
    """Build a valid 69-column TLE fixture with a computed checksum."""
    chars = list(" " * 68)
    chars[0] = number
    chars[2:7] = list("61784")
    for start, end, value in fields:
        assert len(value) == end - start, (start, end, value)
        chars[start:end] = list(value)
    body = "".join(chars)
    checksum = sum(int(c) if c.isdigit() else 1 if c == "-" else 0
                   for c in body) % 10
    return body + str(checksum)


def _fixture(ndot: str = " .00001234"):
    line1 = _line("1", [
        (18, 20, "26"),
        (20, 32, "319.34204248"),
        (33, 43, ndot),
    ])
    line2 = _line("2", [
        (8, 16, " 97.3830"),
        (17, 25, "198.9020"),
        (26, 33, "0006200"),
        (34, 42, "297.7592"),
        (43, 51, " 62.3016"),
        (52, 63, "15.23424607"),
        (63, 68, "27372"),
    ])
    return line1, line2


class TinyGsTleCodecTests(unittest.TestCase):
    def test_big_endian_fields_match_aiop13_offsets(self):
        raw = encode_tinygs_tle(*_fixture())
        self.assertEqual(len(raw), 34)
        self.assertEqual(raw[0], 26)
        self.assertEqual(int.from_bytes(raw[1:3], "big"), 319)
        self.assertEqual(int.from_bytes(raw[3:7], "big"), 34_204_248)
        self.assertEqual(int.from_bytes(raw[7:11], "big", signed=True), 1234)
        self.assertEqual(int.from_bytes(raw[11:14], "big"), 973_830)
        self.assertEqual(int.from_bytes(raw[14:17], "big"), 1_989_020)
        self.assertEqual(int.from_bytes(raw[17:21], "big"), 6200)
        self.assertEqual(int.from_bytes(raw[21:24], "big"), 2_977_592)
        self.assertEqual(int.from_bytes(raw[24:27], "big"), 623_016)
        self.assertEqual(int.from_bytes(raw[27:31], "big"), 1_523_424_607)
        self.assertEqual(int.from_bytes(raw[31:34], "big"), 27_372)

    def test_negative_derivative_is_twos_complement(self):
        raw = encode_tinygs_tle(*_fixture("-.00001234"))
        self.assertEqual(raw[7:11], (-1234).to_bytes(4, "big", signed=True))

    def test_base64_matches_34_byte_wire_format(self):
        lines = _fixture()
        encoded = encode_tinygs_tle_base64(*lines)
        self.assertEqual(len(encoded), 48)
        self.assertEqual(base64.b64decode(encoded, validate=True),
                         encode_tinygs_tle(*lines))

    def test_reject_checksum_mismatch(self):
        l1, l2 = _fixture()
        bad = l1[:-1] + str((int(l1[-1]) + 1) % 10)
        with self.assertRaisesRegex(ValueError, "checksum"):
            encode_tinygs_tle(bad, l2)

    def test_reject_inconsistent_catalog_number(self):
        l1, l2 = _fixture()
        wrong = _line("2", [(2, 7, "12345")])
        with self.assertRaisesRegex(ValueError, "catalog"):
            encode_tinygs_tle(l1, wrong)

    def test_reject_malformed_tle(self):
        l1, l2 = _fixture()
        with self.assertRaises(ValueError):
            encode_tinygs_tle(l1[:-1], l2)
        with self.assertRaises(ValueError):
            encode_tinygs_tle(l2, l1)


if __name__ == "__main__":
    unittest.main()
