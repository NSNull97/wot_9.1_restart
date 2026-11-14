"""Tests for preserving original DDS mip and exact enlarged alpha pixels."""
import random
import struct
import unittest
from tests.test_visual02_dds import header
from tools.visual02_dds import DDSError
from tools.visual03_mips import assemble_2x, mip_report


def dds(fmt, width, height, count, rng):
    out = header(width, height, fmt=fmt.encode('ascii'), mips=count)
    for level in range(count):
        w, h = max(1, width >> level), max(1, height >> level)
        for _ in range(((w + 3) // 4) * ((h + 3) // 4)):
            if fmt == 'DXT1':
                out += struct.pack('<HHI', 65535, 0, rng.getrandbits(32))
            else:
                out += rng.getrandbits(128).to_bytes(16, 'little')
    return bytes(out)


def independent_alpha(data, fmt, width, height):
    result = []
    blocks_x = (width + 3) // 4
    for y in range(height):
        for x in range(width):
            pos = 128 + ((y // 4) * blocks_x + x // 4) * 16
            raw = data[pos:pos + 8]
            px = (y % 4) * 4 + x % 4
            if fmt == 'DXT3':
                result.append(((int.from_bytes(raw, 'little') >> (4 * px)) & 15) * 17)
            else:
                a, b = raw[0], raw[1]
                idx = (int.from_bytes(raw[2:8], 'little') >> (3 * px)) & 7
                vals = ([a, b] + [((7-i)*a + i*b)//7 for i in range(1, 7)] if a > b else
                        [a, b] + [((5-i)*a+i*b)//5 for i in range(1, 5)] + [0, 255])
                result.append(vals[idx])
    return bytes(result)


class Visual03MipTests(unittest.TestCase):
    def test_all_original_mips_retained_and_alpha_exact(self):
        rng = random.Random(20261114)
        for fmt in ('DXT1', 'DXT3', 'DXT5'):
            for width, height, mips in ((8, 8, 4), (5, 3, 3), (1, 1, 1), (16, 8, 4)):
                with self.subTest(fmt=fmt, width=width, height=height):
                    source = dds(fmt, width, height, mips, rng)
                    top = dds(fmt, width * 2, height * 2, 1, rng)
                    result = assemble_2x(source, top)
                    original_report, result_report = mip_report(source), mip_report(result)
                    self.assertEqual(result_report['mip_count'], mips + 1)
                    self.assertEqual([x['sha256'] for x in result_report['levels'][1:]],
                                     [x['sha256'] for x in original_report['levels']])
                    if fmt != 'DXT1':
                        old = independent_alpha(source, fmt, width, height)
                        new = independent_alpha(result, fmt, width * 2, height * 2)
                        for y in range(height * 2):
                            for x in range(width * 2):
                                self.assertEqual(new[y * width * 2 + x], old[(y // 2) * width + x // 2])

    def test_rejects_wrong_dimensions_format_and_transparent_dxt1(self):
        rng = random.Random(7)
        source = dds('DXT1', 4, 4, 1, rng)
        for wrong in (dds('DXT1', 4, 4, 1, rng), dds('DXT3', 8, 8, 1, rng), dds('DXT1', 8, 8, 2, rng)):
            with self.assertRaises(DDSError):
                assemble_2x(source, wrong)
        transparent = bytes(header(4, 4)) + struct.pack('<HHI', 0, 65535, 0xffffffff)
        with self.assertRaisesRegex(DDSError, 'transparent'):
            assemble_2x(transparent, dds('DXT1', 8, 8, 1, rng))

    def test_rejects_truncated_and_trailing_mips(self):
        rng = random.Random(8)
        source = dds('DXT3', 8, 8, 3, rng)
        with self.assertRaises(DDSError):
            mip_report(source[:-1])
        with self.assertRaisesRegex(DDSError, 'trailing'):
            mip_report(source + b'junk')


if __name__ == '__main__':
    unittest.main()
