"""Source-shaped byte fixtures are automatic codec evidence, not native captures."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from game_profile_tx import TransactionError
from p09e_native_commands import decode, decode_bundle, validate_selection


class NativeResearchCommandsTests(unittest.TestCase):
    fixtures = (
        (0x8e, struct.pack("<hhqii", 226, 201, 3329, 0, 0), (3329, 0, 0)),
        (0x8e, struct.pack("<hhqii", 227, 101, 1, 5891, 5892), (1, 5891, 5892)),
        (0x90, struct.pack("<hhqiii", 228, 301, 3, 7169, 0, -1), (3, 7169, 0, -1)),
        (0x90, struct.pack("<hhqiii", 229, 302, 3, 5892, 1, 0), (3, 5892, 1, 0)),
        (0x97, struct.pack("<hhI6i", 230, 308, 6, 3, 5891, 1, 0, 0, 5892), (3, 5891, 1, 0, 0, 5892)),
    )

    def test_all_source_argument_families_and_int64_width(self):
        for method, raw, args in self.fixtures:
            row = decode(method, raw)
            self.assertEqual(row.arguments, args)
            validate_selection(row, shop_revision=3)
        large = decode(0x8e, struct.pack("<hhqii", 1, 101, 2**40, 5892, 0))
        self.assertEqual(large.arguments[0], 2**40)
        with self.assertRaises(TransactionError):
            validate_selection(large, shop_revision=3)

    def test_every_truncation_suffix_wrong_method_and_request_id(self):
        for method, raw, _ in self.fixtures:
            for length in range(len(raw)):
                with self.assertRaises(TransactionError): decode(method, raw[:length])
            for suffix in (b"\x00", b"garbage"):
                with self.assertRaises(TransactionError): decode(method, raw + suffix)
            with self.assertRaises(TransactionError): decode(0xff, raw)
            for request_id in (0, -1, -32768):
                with self.assertRaises(TransactionError): decode(method, struct.pack("<h", request_id) + raw[2:])

    def test_whole_bundle_rejected_before_dispatch(self):
        frames = [struct.pack("<BH", m, len(p)) + p for m, p, _ in self.fixtures]
        self.assertEqual(len(decode_bundle(b"".join(frames))), 5)
        for body in (b"", frames[0] + frames[0], frames[0] + b"\x8e\x14", frames[0] + frames[1][:-1], b"x" * 513):
            with self.assertRaises(TransactionError): decode_bundle(body)

    def test_free_policy_never_accepts_gold_autobuy_or_forged_shop_revision(self):
        malformed = (
            (0x8e, struct.pack("<hhqii", 1, 201, 3329, -1, 0)),
            (0x8e, struct.pack("<hhqii", 1, 201, 3329, 0, 1)),
            (0x90, struct.pack("<hhqiii", 1, 301, 3, 7169, 17, 0)),
            (0x90, struct.pack("<hhqiii", 1, 301, 3, 7169, 0, 0)),
            (0x90, struct.pack("<hhqiii", 1, 301, 3, 7169, 0, 1)),
            (0x90, struct.pack("<hhqiii", 1, 301, 3, 7169, 0, 2)),
            (0x90, struct.pack("<hhqiii", 1, 301, 3, 7169, 0, -2)),
            (0x90, struct.pack("<hhqiii", 1, 301, 2, 7169, 0, -1)),
            (0x90, struct.pack("<hhqiii", 1, 302, 3, 5892, 1, 1)),
            (0x90, struct.pack("<hhqiii", 1, 302, 3, 5892, -1, 0)),
            (0x90, struct.pack("<hhqiii", 1, 302, 2, 5892, 1, 0)),
            (0x97, struct.pack("<hhI6i", 1, 308, 6, 3, 5891, 1, 0, 1, 5892)),
        )
        for method, raw in malformed:
            with self.assertRaises(TransactionError): validate_selection(decode(method, raw), shop_revision=3)

    def test_array_length_is_exact_and_cannot_allocate_from_count(self):
        raw = self.fixtures[-1][1]
        for count in (0, 5, 7, 0xffffffff):
            with self.assertRaises(TransactionError): decode(0x97, raw[:4] + struct.pack("<I", count) + raw[8:])


if __name__ == "__main__": unittest.main()
