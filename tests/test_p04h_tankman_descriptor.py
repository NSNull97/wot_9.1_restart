"""Independent native P02 bytes, bounded catalog and descriptor adversaries."""
from copy import deepcopy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from p04h_tankman_descriptor import (encode_descriptor, decode_descriptor, recruit_descriptor,
    verify_catalog, ROLE_IDS, ROLE_RANK_IDS, CATALOG_BOUNDS, CATALOG_SOURCE)


class DescriptorTests(unittest.TestCase):
    def arguments(self):
        return dict(vehicle_type_id=13, role="commander", role_level=100,
                    first_name_id=1, last_name_id=1, icon_id=1)

    def test_two_independently_measured_original_P02_passports(self):
        # Actual native generate/parse/repack P02 export, not our own round trip.
        self.assertEqual(encode_descriptor(**self.arguments()).hex(), "080d0164000000010001000100410600000000420000000000")
        args = dict(self.arguments(), role="driver", first_name_id=2, last_name_id=2, icon_id=2)
        self.assertEqual(encode_descriptor(**args).hex(), "080d0364000000020002000200410600000000420000000000")

    def test_supported_qualification_rank_steps_and_all_roles_types(self):
        for vehicle in (13, 28):
            for role in ROLE_IDS:
                for level in range(50, 101):
                    with self.subTest(vehicle=vehicle, role=role, level=level):
                        raw = encode_descriptor(**dict(self.arguments(), vehicle_type_id=vehicle, role=role, role_level=level))
                        self.assertEqual(len(raw), 25)
                        actual = decode_descriptor(raw)
                        self.assertEqual((actual["vehicle_type_id"], actual["role"], actual["role_level"]), (vehicle, role, level))
                        self.assertEqual(actual["rank_id"], ROLE_RANK_IDS[role][int(level == 100)])
                        self.assertEqual(actual["levels_to_next_rank"], 50 - ((level - 50) % 50))
                        self.assertEqual((actual["skills"], actual["free_xp"], actual["dossier_hex"]), ([], 0, "420000000000"))

    def test_all_new_identity_components_are_deterministic_catalog_members(self):
        for number in range(4, 17):
            actual = decode_descriptor(recruit_descriptor(number, 28, "loader"))
            self.assertEqual([actual[k] for k in CATALOG_BOUNDS], [number] * 3)
            self.assertEqual(actual["role_level"], 50)

    def test_encoder_rejects_unknown_bounds_types_and_boolean_integers(self):
        for field, values in {"vehicle_type_id": (True, 0, 29, "13"), "role": ("radioman", "unknown", None),
            "role_level": (True, 49, 101, 50.0), "first_name_id": (True, 0, 113),
            "last_name_id": (0, 1037, 1.0), "icon_id": (-1, 31, True)}.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    encode_descriptor(**dict(self.arguments(), **{field: value}))
        for value in (True, 3, 17, 4.0):
            with self.assertRaises(ValueError): recruit_descriptor(value, 13, "driver")

    def test_decoder_rejects_malformed_header_skills_flags_xp_rank_and_dossier(self):
        baseline = encode_descriptor(**self.arguments())
        cases = [baseline[:-1], baseline + b"0", bytearray(baseline), baseline.hex(), b""]
        for offset in (0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 13, 15, 19, 21, 23):
            value = bytearray(baseline)
            value[offset] = 255
            cases.append(bytes(value))
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError): decode_descriptor(value)

    def test_catalog_real_source_and_modified_pin_rejection(self):
        config = Path(os.environ.get("WOT091_CONFIG", ROOT / "config/project.local.json"))
        if not config.is_file(): self.skipTest("NOT_RUN: original source config required")
        original = Path(json.loads(config.read_text(encoding="utf-8-sig"))["paths"]["original_client_root"])
        value = verify_catalog(original)
        for field, bound in CATALOG_BOUNDS.items(): self.assertEqual(value["ids"][field], list(range(1, bound + 1)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / CATALOG_SOURCE
            path.parent.mkdir(parents=True)
            raw = (original / CATALOG_SOURCE).read_bytes()
            path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            with self.assertRaisesRegex(ValueError, "digest"): verify_catalog(directory)
            path.write_bytes(raw + b"0")
            with self.assertRaisesRegex(ValueError, "size"): verify_catalog(directory)
