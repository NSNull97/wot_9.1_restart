"""UI-06c round 10: the project fire and ammo icons of the flying damage."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import battle_ui_marker_icons as icons


class IconTests(unittest.TestCase):
    def test_both_icons_are_white_premultiplied_on_the_native_canvas(self):
        for kind in (icons.FIRE, icons.AMMO):
            pixels = icons.argb(kind)
            self.assertEqual(len(pixels), icons.CANVAS * icons.CANVAS * 4)
            for at in range(0, len(pixels), 4):
                self.assertEqual(len(set(pixels[at:at + 4])), 1, 'white: every channel equals alpha')

    def test_icons_are_centred_and_leave_room_for_the_glow(self):
        for kind in (icons.FIRE, icons.AMMO):
            rows = icons.coverage(kind)
            ys = [y for y, row in enumerate(rows) if any(row)]
            xs = [x for row in rows for x, value in enumerate(row) if value]
            self.assertGreater(min(xs), 10, kind)
            self.assertLess(max(xs), icons.CANVAS - 10, kind)
            self.assertLess(abs((min(ys) + max(ys)) / 2 - icons.CANVAS / 2), 3, kind)

    def test_the_fire_icon_is_a_hollow_triangle_with_a_flame(self):
        rows, middle = icons.coverage(icons.FIRE), icons.CANVAS // 2
        self.assertEqual(rows[middle - 4][middle - 6], 0, 'inside the triangle, beside the flame')
        self.assertEqual(rows[middle + 4][middle + 2], 255, 'the flame body beside its hollow')

    def test_sparks_are_uneven(self):
        lengths = {round(outer - inner, 1) for _, inner, outer in icons.SPARKS}
        self.assertGreater(len(lengths), 5)
        self.assertGreater(max(outer for _, _, outer in icons.SPARKS), 20)


if __name__ == '__main__':
    unittest.main()
