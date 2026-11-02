"""Offline regression tests for the AX100 header analyzer."""
import contextlib
import io
import json
from pathlib import Path
import unittest

from tinygs_control_center.ax100_analyzer import (
    analyze_ax100, decode_header, encode_golay24, parse_hex_dump,
)
from tinygs_control_center.cli import main


EXAMPLE = (Path(__file__).resolve().parents[1]
           / "examples/frontiersat-stage2-20261102-103915.hex")


class Ax100AnalyzerTests(unittest.TestCase):
    def test_known_codeword_and_correctable_errors(self):
        codeword = encode_golay24(0x1FF)
        self.assertEqual(decode_header(codeword)["minimum_distance_bits"], 0)
        self.assertEqual(decode_header(codeword)["decoded_frame_len"], 255)
        for mask in (0x000001, 0x000101, 0x110101):
            decoded = decode_header(codeword ^ mask)
            self.assertEqual(decoded["minimum_distance_bits"], mask.bit_count())
            self.assertEqual(decoded["decoded_frame_len"], 255)
            self.assertTrue(decoded["golay_correctable"])

    def test_four_bit_errors_cannot_be_unambiguously_corrected(self):
        codeword = encode_golay24(0x0FF)
        decoded = decode_header(codeword ^ 0x00000F)
        self.assertEqual(decoded["minimum_distance_bits"], 4)
        self.assertFalse(decoded["golay_correctable"])
        self.assertIsNone(decoded["decoded_frame_len"])

    def test_frontiersat_real_dump_first_header_fails(self):
        raw = parse_hex_dump(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(len(raw), 255)
        report = analyze_ax100(raw)
        header = report["at_expected_offset"]
        self.assertEqual(header["raw_header_hex"], "EBACEE")
        self.assertEqual(header["minimum_distance_bits"], 4)
        self.assertEqual(header["nearest_candidate_count"], 6)
        self.assertIn("6B8C6A", header["nearest_codewords_hex"])
        self.assertFalse(header["golay_correctable"])
        self.assertEqual(report["rs_verified"], False)
        self.assertEqual(len(report["all_offsets"]), 32)
        self.assertTrue(report["plausible_candidates"])
        self.assertFalse(header["candidate_length_feasible"])

    def test_padded_frame_at_expected_offset(self):
        # 3-byte header plus 252 received RS bytes; up to 3 missing.
        header = encode_golay24(255).to_bytes(3, "big")
        data = header + bytes(252)
        candidate = analyze_ax100(data, max_shift_bits=0)["at_expected_offset"]
        self.assertTrue(candidate["candidate_length_feasible"])
        self.assertEqual(candidate["available_rs_bytes"], 252)

    def test_parse_rejects_ambiguous_or_empty_dump(self):
        for bad in ("", "EB AC E", "EB AC EE | ...", "EB\nxx"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_hex_dump(bad)

    def test_bad_max_shift_and_short_data(self):
        for shift in (-1, 257, 1.5):
            with self.assertRaises(ValueError):
                analyze_ax100(bytes(10), shift)
        with self.assertRaises(ValueError):
            analyze_ax100(bytes(3))

    def test_cli_example(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["ax100-analyze", str(EXAMPLE), "--max-shift-bits", "7"])
        self.assertEqual(rc, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["at_expected_offset"]["minimum_distance_bits"], 4)
        self.assertNotIn("all_offsets", report)
        self.assertEqual(report["search_max_shift_bits"], 7)


if __name__ == "__main__":
    unittest.main()
