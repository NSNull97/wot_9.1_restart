# -*- coding: utf-8 -*-
"""UI-03b sprite tool: PNG round trip, atlas parsing, SWF tags, opt-in embedding and
the fallback. No Lesta file is needed; the real folder is checked when it exists."""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import battle_ui_art as art
import battle_ui_feed_flash as feed
import battle_ui_history_flash as history
import battle_ui_hit_flash as flash
from test_battle_ui_hit_flash import ORIGINAL, fake_movie

BORROWED = ROOT.parents[2] / 'local/ui-borrowed/battle-feed'
PIXEL = bytes((10, 20, 30, 128))


def image(width=2, height=2):
    return width, height, PIXEL * (width * height)


def folder(root, names):
    for name in names:
        (Path(root) / (name + '.png')).write_bytes(art.write_png(2, 2, PIXEL * 4))
    return root


def tag_rows(movie):
    body = flash.expanded(movie)
    return body, flash.tags(body, ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4)


class ImageTests(unittest.TestCase):
    def test_png_round_trip(self):
        raw = art.write_png(2, 2, PIXEL * 4)
        self.assertEqual(art.read_png(raw), (2, 2, PIXEL * 4))

    def test_a_foreign_png_is_refused(self):
        with self.assertRaises(ValueError):
            art.read_png(b'not a png')
        raw = bytearray(art.write_png(2, 2, PIXEL * 4))
        raw[25] = 2
        with self.assertRaises(ValueError):
            art.read_png(bytes(raw))

    def test_dxt5_block(self):
        block = bytes((255, 0)) + bytes(6) + struct.pack('<HHI', 0xffff, 0, 0)
        raw = b'DDS ' + bytes(8) + struct.pack('<II', 4, 4) + bytes(64) + b'DXT5' + bytes(40) + block
        self.assertEqual(art.dds_surface(raw)[2][:4], bytes((255, 255, 255, 255)))

    def test_atlas_rows(self):
        text = '<SubTexture><name> a </name><x> 1 </x><y> 2 </y><width> 3 </width><height> 4 </height></SubTexture>'
        self.assertEqual(art.atlas_rows(text), {'a': (1, 2, 3, 4)})

    def test_swf_alpha_is_premultiplied_argb(self):
        self.assertEqual(art._rgba_to_swf(bytes((255, 128, 0, 128))), bytes((128, 128, 64, 0)))


class TagTests(unittest.TestCase):
    def test_every_sprite_is_a_bitmap_a_shape_and_an_exported_clip(self):
        rows = flash.tags(art.tags({'b': image(), 'a': image()}) + flash.tag(0, b''), 0)
        self.assertEqual([row[0] for row in rows], [36, 2, 39, 36, 2, 39, 56, 0])

    def test_embed_puts_them_before_the_added_action(self):
        movie = flash.build(fake_movie(), feed.actions(True))
        _, rows = tag_rows(art.embed(movie, {'icon': image()}))
        self.assertEqual([row[0] for row in rows], [9, 71, 12, 36, 2, 39, 56, 12, 1, 0])

    def test_embed_keeps_the_movie_header_valid(self):
        result = art.embed(flash.build(fake_movie(), feed.actions(True)), {'icon': image()})
        self.assertEqual(result[:3], b'CWS')
        self.assertEqual(struct.unpack_from('<I', result, 4)[0], len(zlib.decompress(result[8:])) + 8)

    def test_no_images_leave_the_movie_alone(self):
        movie = flash.build(fake_movie(), feed.actions())
        self.assertIs(art.embed(movie, {}), movie)

    def test_a_movie_of_another_layout_is_refused(self):
        with self.assertRaises(ValueError):
            art.embed(fake_movie(), {'icon': image()})


class FolderTests(unittest.TestCase):
    def test_a_full_folder_loads(self):
        with tempfile.TemporaryDirectory() as root:
            images, missing = art.load(folder(root, art.HISTORY_SPRITES), art.HISTORY_SPRITES)
        self.assertEqual(sorted(images), sorted(art.HISTORY_SPRITES))
        self.assertEqual(missing, [])

    def test_one_missing_file_means_no_art_at_all(self):
        with tempfile.TemporaryDirectory() as root:
            images, missing = art.load(folder(root, art.HISTORY_SPRITES[1:]), art.HISTORY_SPRITES)
        self.assertEqual(images, {})
        self.assertEqual(missing, [art.HISTORY_SPRITES[0]])

    def test_a_missing_folder_means_no_art(self):
        images, missing = art.load('no/such/folder', art.FEED_SPRITES)
        self.assertEqual((images, missing), ({}, list(art.FEED_SPRITES)))

    def test_every_sprite_has_a_name_a_linkage_can_carry(self):
        self.assertEqual(len(set(art.ALL_SPRITES)), len(art.ALL_SPRITES))
        for name in art.ALL_SPRITES:
            name.encode('ascii')


@unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
class OriginalTests(unittest.TestCase):
    def check(self, module, art_folder, sprites):
        result, evidence = module.payload(ORIGINAL, art_folder)
        self.assertEqual(evidence['art'], 'embedded')
        self.assertEqual(evidence['art_sprites'], sorted(sprites))
        self.assertEqual(evidence['art_missing'], [])
        body, rows = tag_rows(result)
        exported = [row for row in rows if row[0] == 56 and sprites[0].encode() in body[row[1]:row[2]]]
        self.assertEqual(len(exported), 1)
        self.assertLess(exported[0][1], [row for row in rows if row[0] == 12][-1][1])
        bitmaps = [body[row[1] + (6 if body[row[1]] & 63 == 63 else 2):row[2]] for row in rows if row[0] == 36]
        own = [data for data in bitmaps if struct.unpack_from('<H', data)[0] >= art.FIRST_CHARACTER]
        self.assertEqual(len(own), len(sprites))
        for data in own:
            _, kind, width, height = struct.unpack_from('<HBHH', data)
            self.assertEqual(kind, 5)
            self.assertEqual(len(zlib.decompress(data[7:])), width * height * 4)
        return result

    def test_the_movies_take_any_folder_with_the_listed_names(self):
        with tempfile.TemporaryDirectory() as root:
            self.check(feed, folder(root, art.FEED_SPRITES), art.FEED_SPRITES)
            self.check(history, folder(root, art.HISTORY_SPRITES), art.HISTORY_SPRITES)

    def test_a_folder_without_a_sprite_builds_the_drawn_movie(self):
        plain = feed.payload(ORIGINAL)[0]
        with tempfile.TemporaryDirectory() as root:
            result, evidence = feed.payload(ORIGINAL, root)
        self.assertEqual(result, plain)
        self.assertEqual(evidence['art'], 'absent')
        self.assertEqual(evidence['art_missing'], list(art.FEED_SPRITES))

    @unittest.skipUnless(BORROWED.is_dir(), 'borrowed folder absent')
    def test_the_borrowed_folder_builds_both_movies(self):
        self.assertLess(len(self.check(feed, BORROWED, art.FEED_SPRITES)), 1024 * 1024)
        self.assertLess(len(self.check(history, BORROWED, art.HISTORY_SPRITES)), 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
