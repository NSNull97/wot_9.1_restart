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

    def test_the_glow_is_baked_around_a_white_icon(self):
        pixels, middle = icons.argb(icons.FIRE, (255, 55, 28)), icons.CANVAS // 2
        def at(x, y):
            return pixels[(y * icons.CANVAS + x) * 4:(y * icons.CANVAS + x) * 4 + 4]
        self.assertEqual(at(middle + 2, middle + 4), bytes((255, 255, 255, 255)), 'the flame stays white')
        rows = icons.coverage(icons.FIRE)
        edge = next(x for x in range(icons.CANVAS) if rows[middle][x])
        a, r, g, b = at(edge - 3, middle)
        self.assertGreater(a, 60, 'a halo outside the triangle')
        self.assertGreater(r, b, 'in the red of the colour')
        self.assertEqual(at(0, 0), bytes(4), 'the corners stay clear')

    def test_sparks_are_uneven(self):
        lengths = {round(outer - inner, 1) for _, inner, outer in icons.SPARKS}
        self.assertGreater(len(lengths), 5)
        self.assertGreater(max(outer for _, _, outer in icons.SPARKS), 20)


if __name__ == '__main__':
    unittest.main()
