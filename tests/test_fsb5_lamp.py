"""Project lamp bank builder; synthetic banks only, no client resource is read."""
import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fsb5_lamp as f


def original_like(samples=640):
    # Same layout as #717 gui_notifications_fx_intuition.fsb: FSB5 v1, one mono
    # IMA sample at 48 kHz, one loop chunk, 48-byte name table.
    pcm = [int(12000 * math.sin(i / 7.0)) for i in range(samples)]
    data = f.ima_encode(pcm); data += b'\0' * (-len(data) % 32)
    packed = 1 | (9 << 1) | (samples << 34)
    sample = struct.pack('<QIII', packed, (3 << 25) | (8 << 1), 0, samples - 20)
    names = struct.pack('<I', 4) + b'intuition_03' + b'\0' * 32
    return b'FSB5' + struct.pack('<6I', 1, 1, 20, 48, len(data), 7) + bytes(range(32)) + sample + names + data


class Fsb5LampTests(unittest.TestCase):
    def test_build_keeps_hash_area_names_and_format_with_new_sample(self):
        source = original_like()
        pcm = [int(20000 * math.sin(i / 11.0)) for i in range(96000)]
        bank = f.build(source, pcm); head = f.parse(bank); old = f.parse(source)
        self.assertEqual((head['hash_area'], head['names']), (old['hash_area'], old['names']))
        self.assertEqual(head['samples'], 96000); self.assertEqual(head['loop'], (0, 95999))
        self.assertEqual(len(head['data']) % 32, 0)
        decoded = f.ima_decode(head['data'][:96000 * 36 // 64])
        error = sum((a - b) ** 2 for a, b in zip(pcm, decoded)); signal = sum(a * a for a in pcm)
        self.assertGreater(10 * math.log10(signal / error), 20)

    def test_foreign_or_unbounded_banks_and_samples_fail_closed(self):
        source = original_like()
        for change in (lambda b: b'FSB4' + b[4:], lambda b: b[:24] + struct.pack('<I', 11) + b[28:],
                       lambda b: b[:8] + struct.pack('<I', 2) + b[12:], lambda b: b + b'x'):
            with self.assertRaises(ValueError): f.parse(change(source))
        with self.assertRaises(ValueError): f.build(source, [])
        with self.assertRaises(ValueError): f.build(source, [0] * (f.RATE * f.MAX_SECONDS + 1))


if __name__ == '__main__':
    unittest.main()
