"""The committed gun dispersion table equals the original #717 client (tools/gun_dispersion.py)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import gun_dispersion as gd  # noqa: E402

CLIENT = Path('C:/WoT_0.9.1_RU_0717_original')


class Table(unittest.TestCase):
    def test_committed_table_and_pin_match_the_client(self):
        if not CLIENT.is_dir():
            self.skipTest('NOT_RUN: original #717 client copy absent')
        raw = gd.build(CLIENT)
        self.assertEqual(gd.OUT.read_bytes(), raw)
        self.assertEqual(gd.PINS.read_bytes(), gd.pins(raw))

    def test_rows_are_bounded_and_curated_guns_carry_their_compact_id(self):
        guns = json.loads(gd.OUT.read_text('utf-8'))['guns']
        self.assertGreaterEqual(len(guns), 233)
        for name, row in guns.items():
            self.assertTrue(0.05 <= row['radius_m'] <= 2.0, name)
            self.assertTrue(0.1 <= row['after_shot'] <= 30.0, name)
        for name, compact in gd.CURATED.items():
            self.assertEqual(guns[name]['compact'], compact, name)


if __name__ == '__main__':
    unittest.main()
