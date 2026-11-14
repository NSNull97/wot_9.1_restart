"""Tests for the read-only DDS census; no client files or external assets."""
from __future__ import annotations

import random
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from visual02_dds import DDSError, inspect_dds  # noqa: E402


def header(width=4, height=4, *, fmt=b"DXT1", mips=1, raw=False):
    data = bytearray(128)
    data[:4] = b"DDS "
    struct.pack_into("<I", data, 4, 124)
    struct.pack_into("<I", data, 8, 0x1007)
    struct.pack_into("<II", data, 12, height, width)
    struct.pack_into("<I", data, 28, mips)
    struct.pack_into("<I", data, 76, 32)
    if raw:
        struct.pack_into("<I", data, 80, 0x41)
        struct.pack_into("<IIIII", data, 88, 16, 0x0F00, 0x00F0, 0x000F, 0xF000)
    else:
        struct.pack_into("<I", data, 80, 4)
        data[84:88] = fmt
    return data


class DDSInspectionTests(unittest.TestCase):
    def test_dxt1_punchthrough_depends_on_block_not_header_flag(self):
        # FourCC flag alone neither announces nor excludes one-bit transparency.
        dds = header() + struct.pack("<HHI", 0, 65535, 0xFFFFFFFC)
        result = inspect_dds(dds)
        self.assertEqual(result["pixel_format_flags"], 4)
        self.assertEqual(result["alpha_values_top_mip"], [0, 255])
        self.assertEqual(result["alpha_storage"], "DXT1_1BIT_CONDITIONAL")
        self.assertEqual(result["alpha_semantics"], "UNKNOWN")
        opaque = header() + struct.pack("<HHI", 65535, 0, 0xFFFFFFFF)
        self.assertEqual(inspect_dds(opaque)["alpha_values_top_mip"], [255])

    def test_partial_blocks_ignore_padding(self):
        # Only pixel 0 belongs to this image, even when every padded pixel is 0.
        dxt1 = header(1, 1) + struct.pack("<HHI", 0, 65535, 0xFFFFFFFC)
        self.assertEqual(inspect_dds(dxt1)["alpha_values_top_mip"], [255])
        dxt3 = header(1, 1, fmt=b"DXT3") + struct.pack("<QQ", 0xFFFFFFFFFFFFFFF0, 0)
        self.assertEqual(inspect_dds(dxt3)["alpha_values_top_mip"], [0])

    def test_dxt3_alpha_and_raw_bitmasks(self):
        dxt3 = header(fmt=b"DXT3") + struct.pack("<QQ", 0xFFFFFFFFFFFFFF50, 0)
        self.assertEqual(inspect_dds(dxt3)["alpha_values_top_mip"], [0, 85, 255])
        raw = header(2, 2, raw=True) + struct.pack("<HHHH", 0xFFFF, 0x5FFF, 0x0FFF, 0xAFFF)
        result = inspect_dds(raw)
        self.assertEqual(result["format"], "RGB16")
        self.assertEqual(result["raw_masks"], [0xF00, 0xF0, 0xF, 0xF000])
        self.assertEqual(result["alpha_values_top_mip"], [0, 85, 170, 255])

    def test_dxt5_both_interpolation_modes(self):
        def block(a, b, selectors):
            bits = sum(v << (3 * i) for i, v in enumerate(selectors * 4))
            return struct.pack("<QQ", a | b << 8 | bits << 16, 0)

        six_alpha = header(fmt=b"DXT5") + block(100, 200, [0, 1, 6, 7])
        self.assertEqual(inspect_dds(six_alpha)["alpha_values_top_mip"], [0, 100, 200, 255])
        eight_alpha = header(fmt=b"DXT5") + block(255, 0, [0, 1, 2, 7])
        self.assertEqual(inspect_dds(eight_alpha)["alpha_values_top_mip"], [0, 36, 218, 255])

    def test_full_mip_lengths_checked_and_extra_data_reported(self):
        dds = header(4, 4, mips=3) + bytes(3 * 8) + b"extra"
        result = inspect_dds(dds)
        self.assertEqual(result["mip_sizes"], [8, 8, 8])
        self.assertEqual(result["trailing_bytes"], 5)
        with self.assertRaisesRegex(DDSError, "truncated"):
            inspect_dds(dds[:128 + 23])

    def test_rejects_malformed_or_unsupported_headers(self):
        cases = []
        cases.append(header() + bytes(7))
        cases.append(header(mips=4) + bytes(8))
        cases.append(header(fmt=b"DX10") + bytes(32))
        bad_magic = header() + bytes(8)
        bad_magic[:4] = b"xxxx"
        cases.append(bad_magic)
        cube = header() + bytes(8)
        struct.pack_into("<I", cube, 112, 0x200)
        cases.append(cube)
        overlaps = header(2, 2, raw=True) + bytes(8)
        struct.pack_into("<I", overlaps, 92, 0xF0)  # red overlaps green
        cases.append(overlaps)
        pitched_mips = header(2, 2, raw=True, mips=2) + bytes(10)
        struct.pack_into("<I", pitched_mips, 8, 0x100F)
        struct.pack_into("<I", pitched_mips, 20, 4)
        cases.append(pitched_mips)
        for case in cases:
            with self.subTest(case=bytes(case[:128]).hex()[:32]):
                with self.assertRaises(DDSError):
                    inspect_dds(case)

    def test_seeded_randomized_blocks_against_scalar_reference(self):
        rng = random.Random(20261114)
        for fmt in (b"DXT1", b"DXT3", b"DXT5"):
            for case in range(100):
                width, height = rng.randrange(1, 13), rng.randrange(1, 13)
                data, expected = header(width, height, fmt=fmt), set()
                for by in range((height + 3) // 4):
                    for bx in range((width + 3) // 4):
                        if fmt == b"DXT1":
                            c0, c1, indices = rng.randrange(65536), rng.randrange(65536), rng.getrandbits(32)
                            data += struct.pack("<HHI", c0, c1, indices)
                        elif fmt == b"DXT3":
                            indices = rng.getrandbits(64)
                            data += struct.pack("<QQ", indices, 0)
                        else:
                            a, b, indices = rng.randrange(256), rng.randrange(256), rng.getrandbits(48)
                            data += struct.pack("<QQ", a | b << 8 | indices << 16, 0)
                            palette = [a, b] + ([((7 - j) * a + j * b) // 7 for j in range(1, 7)]
                                                if a > b else [((5 - j) * a + j * b) // 5
                                                               for j in range(1, 5)] + [0, 255])
                        for y in range(4):
                            for x in range(4):
                                if by * 4 + y >= height or bx * 4 + x >= width:
                                    continue
                                i = y * 4 + x
                                if fmt == b"DXT1":
                                    value = 0 if c0 <= c1 and (indices >> (2 * i) & 3) == 3 else 255
                                elif fmt == b"DXT3":
                                    value = (indices >> (4 * i) & 15) * 17
                                else:
                                    value = palette[indices >> (3 * i) & 7]
                                expected.add(value)
                with self.subTest(fmt=fmt, case=case):
                    self.assertEqual(inspect_dds(data)["alpha_values_top_mip"], sorted(expected))


if __name__ == "__main__":
    unittest.main()
