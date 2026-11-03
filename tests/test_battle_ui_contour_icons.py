"""UI-06c round 11: the contour icons of the vehicles in the flat project style."""
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import battle_ui_contour_icons as contour

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')


class PixelTests(unittest.TestCase):
    def test_a_body_pixel_is_the_class_colour_and_opaque(self):
        for kind, body in contour.BODY.items():
            self.assertEqual(contour.restyle_pixel(body, body, body, 170, kind), contour.COLOURS[kind] + (255,))

    def test_a_dark_line_is_a_darker_shade_of_the_class_colour(self):
        r, g, b, a = contour.restyle_pixel(0, 0, 0, 200, 'td')
        self.assertEqual((r, g, b), tuple(round(c * contour.LINE_SHADE) for c in contour.COLOURS['td']))

    def test_transparent_stays_transparent_and_a_soft_edge_stays_soft(self):
        self.assertEqual(contour.restyle_pixel(90, 90, 90, 0, 'tank'), (0, 0, 0, 0))
        self.assertEqual(contour.restyle_pixel(125, 125, 125, 60, 'tank')[3], 90)

    def test_a_png_of_another_layout_is_left_native(self):
        self.assertIsNone(contour.restyle(b'not a png', 'tank'))


@unittest.skipUnless((ORIGINAL / contour.PACKAGE).is_file(), 'original client absent')
class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads, cls.evidence = contour.payloads(ORIGINAL)

    def test_every_vehicle_icon_is_restyled_by_its_class(self):
        self.assertEqual(self.evidence['left_native_no_class'], ['noImage', 'unknown'])
        self.assertEqual(self.evidence['left_native_other_layout'], [])
        classes = contour.vehicle_classes(ORIGINAL)
        self.assertEqual((classes['ussr-is-7'], classes['uk-gb48_fv215b_183'], classes['ussr-object_261']),
                         ('tank', 'td', 'spg'))

    def test_every_icon_has_one_set_per_colour_of_an_ears_row(self):
        for folder, colours in contour.SETS.items():
            path = contour.FOLDER + folder + '/uk-GB48_FV215b_183.png'
            width, height, rows = contour._decode(self.payloads[path])
            body = [tuple(row[x * 4:x * 4 + 3]) for row in rows for x in range(width) if row[x * 4 + 3] == 255]
            self.assertIn(colours['td'], body, folder)
        self.assertEqual(len(self.payloads), len(contour.SETS) * self.evidence['contour_icons'])
        self.assertEqual(contour.SETS['contour'], contour.SETS['contour_ally'], 'the default path is the ally set')
        self.assertEqual(set(contour.SETS['contour_own'].values()), {contour.OWN})
        self.assertEqual(set(contour.SETS['contour_tk'].values()), {contour.TEAM_KILLER})

    def test_a_restyled_icon_keeps_the_native_size_and_shape(self):
        with zipfile.ZipFile(ORIGINAL / contour.PACKAGE) as package:
            native = contour._decode(package.read(contour.PREFIX + 'ussr-IS-7.png'))
        styled = contour._decode(self.payloads[contour.TARGET + 'ussr-IS-7.png'])
        self.assertEqual(styled[:2], native[:2])
        for old, new in zip(native[2], styled[2]):
            self.assertEqual([bool(old[x]) for x in range(3, len(old), 4)], [bool(new[x]) for x in range(3, len(new), 4)])


if __name__ == '__main__':
    unittest.main()
