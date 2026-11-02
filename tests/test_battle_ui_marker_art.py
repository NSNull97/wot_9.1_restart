# -*- coding: utf-8 -*-
"""UI-06c: the borrowed class icon tool. Synthetic inputs only, except one read
of the local Lesta copy (read only) when it is there; no image enters Git."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import importlib.util
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import battle_ui_marker_art as art

LESTA = Path('D:/Games/Tanki')
ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')


def dds(width, height, blocks):
    """A DXT5 .dds of `blocks` (one 16-byte block per 4x4 tile, rows first)."""
    head = bytearray(128)
    head[:4] = b'DDS '
    struct.pack_into('<II', head, 12, height, width)
    head[84:88] = b'DXT5'
    return bytes(head) + b''.join(blocks)


def block(alpha, colour):
    """One DXT5 block: every pixel alpha index 0 and colour index 0."""
    return bytes((alpha, alpha)) + bytes(6) + struct.pack('<HHI', colour, colour, 0)


class ArtTests(unittest.TestCase):
    def test_names_cover_six_labels_and_nine_classes(self):
        self.assertEqual(len(art.names()), 54)
        self.assertIn('gold_heavyAT-SPG', art.names())
        self.assertEqual(art.ATLAS_NAMES['gold_heavyAT-SPG'], 'gold_heavyAT_SPG')
        self.assertEqual(art.linkage('red_SPG'), 'ProjectMarkerIcon_red_SPG')

    def test_a_box_decodes_only_its_blocks(self):
        red, green = 0xf800, 0x07e0
        raw = dds(8, 4, [block(255, red), block(128, green)])
        pixels = art.dxt5_box(raw, 8, (2, 1, 4, 2))
        rows = [pixels[i:i + 4] for i in range(0, len(pixels), 4)]
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[0], bytes((255, 0, 0, 255)))
        self.assertEqual(rows[2], bytes((0, 255, 0, 128)))

    def test_png_round_trip_and_the_canvas_limit(self):
        rgba = bytes(range(256)) * (39 * 50 * 4 // 256) + bytes(39 * 50 * 4 % 256)
        self.assertEqual(art.read_png(art.write_png(39, 50, rgba)), (39, 50, rgba))
        with self.assertRaises(ValueError):
            art.read_png(art.write_png(40, 50, bytes(40 * 50 * 4)))
        with self.assertRaises(ValueError):
            art.read_png(b'not a png')

    def test_a_missing_folder_or_file_keeps_the_native_icons(self):
        self.assertEqual(art.load(None), {})
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(art.load(Path(folder) / 'absent'), {})
            (Path(folder) / 'green_heavyTank.png').write_bytes(art.write_png(39, 50, bytes(39 * 50 * 4)))
            (Path(folder) / 'other.png').write_bytes(art.write_png(1, 1, bytes(4)))
            self.assertEqual(set(art.load(folder)), {'ProjectMarkerIcon_green_heavyTank'})

    def test_other_atlas_bytes_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / art.PACKAGE
            package.parent.mkdir(parents=True)
            with zipfile.ZipFile(package, 'w') as out:
                out.writestr(art.ATLAS, dds(4, 4, [block(255, 0)]))
                out.writestr(art.ATLAS_XML, '<root/>')
            with self.assertRaises(ValueError):
                art.extract(folder, Path(folder) / 'out')
            self.assertFalse((Path(folder) / 'out').exists())

    @unittest.skipUnless((LESTA / art.PACKAGE).is_file(), 'local Lesta copy absent')
    def test_the_local_atlas_is_the_pinned_one_and_has_every_icon_on_the_native_canvas(self):
        with zipfile.ZipFile(LESTA / art.PACKAGE) as package:
            raw, xml = package.read(art.ATLAS), package.read(art.ATLAS_XML)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), art.ATLAS_SHA256)
        self.assertEqual(hashlib.sha256(xml).hexdigest(), art.ATLAS_XML_SHA256)
        rows = art.atlas_rows(xml.decode('utf-8'))
        for name in art.names():
            self.assertEqual(rows[art.ATLAS_NAMES.get(name, name)][2:], (art.MAX_WIDTH, art.MAX_HEIGHT))


class PrepareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('_ui06c_art_interactive', ROOT / 'tools/interactive_client.py')
        cls.client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.client)

    def test_the_art_folder_belongs_to_the_project_markers(self):
        with self.assertRaises(ValueError):
            self.client.vehicle_markers(SimpleNamespace(native_vehicle_markers=True, vehicle_marker_art=Path('x')),
                                        True, ORIGINAL, {})

    @unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
    def test_a_folder_of_icons_is_embedded_and_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('green_heavyTank', 'red_AT-SPG'):
                (Path(folder) / (name + '.png')).write_bytes(art.write_png(39, 50, bytes(39 * 50 * 4)))
            evidence = {}
            self.client.vehicle_markers(SimpleNamespace(vehicle_marker_art=Path(folder)), True, ORIGINAL, evidence)
            row = evidence['project_vehicle_markers_movie']
            self.assertEqual((row['icons'], row['icon_folder']), (2, Path(folder).as_posix()))


if __name__ == '__main__':
    unittest.main()
