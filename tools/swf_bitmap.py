"""SWF tags that show RGBA bitmaps as exported sprites.

Shared by the movie patchers (battle_ui_hit_art, battle_ui_art,
battle_ui_marker_look): DefineBitsLossless2, a bitmap-filled DefineShape and a
one-frame DefineSprite per image, then one ExportAssets with the linkage names.
`tag` is the caller's SWF tag writer (code, body) -> bytes.
"""
from __future__ import annotations

import struct
import zlib


def rgba_to_swf(rgba):
    """SWF alpha bitmaps are premultiplied ARGB."""
    out = bytearray(len(rgba))
    for at in range(0, len(rgba), 4):
        red, green, blue, alpha = rgba[at:at + 4]
        out[at:at + 4] = bytes((alpha, red * alpha // 255, green * alpha // 255, blue * alpha // 255))
    return bytes(out)


class Bits:
    def __init__(self):
        self.value, self.size = 0, 0

    def put(self, count, value):
        self.value = self.value << count | (value & ((1 << count) - 1))
        self.size += count

    def signed_width(self, *values):
        return max(max(value.bit_length() + 1 for value in values), 1)

    def rect(self, x0, x1, y0, y1):
        count = self.signed_width(x0, x1, y0, y1)
        self.put(5, count)
        for value in (x0, x1, y0, y1):
            self.put(count, value)
        self.align()

    def align(self):
        if self.size % 8:
            self.put(8 - self.size % 8, 0)

    def bytes(self):
        self.align()
        return self.value.to_bytes(self.size // 8, 'big')


def bitmap_matrix(tx, ty):
    """One bitmap pixel is 20 twips, placed at (tx, ty) twips."""
    scale = 20 << 16
    bits = Bits()
    bits.put(1, 1)
    count = bits.signed_width(scale)
    bits.put(5, count)
    bits.put(count, scale)
    bits.put(count, scale)
    bits.put(1, 0)
    count = bits.signed_width(tx, ty)
    bits.put(5, count)
    bits.put(count, tx)
    bits.put(count, ty)
    return bits.bytes()


def shape(character, bitmap, width, height):
    """A rectangle the size of the bitmap, its origin at the centre."""
    w, h = width * 20, height * 20
    x0, y0 = -(w // 2), -(h // 2)
    bounds = Bits()
    bounds.rect(x0, x0 + w, y0, y0 + h)
    edges = Bits()
    edges.put(4, 1)
    edges.put(4, 0)
    # Style change: move to the corner, fill style 1 on the right of the edges.
    edges.put(6, 0b000101)
    count = edges.signed_width(x0, y0)
    edges.put(5, count)
    edges.put(count, x0)
    edges.put(count, y0)
    edges.put(1, 1)
    for vertical, delta in ((False, w), (True, h), (False, -w), (True, -h)):
        count = max(edges.signed_width(delta), 2)
        edges.put(2, 0b11)
        edges.put(4, count - 2)
        edges.put(1, 0)
        edges.put(1, int(vertical))
        edges.put(count, delta)
    edges.put(6, 0)
    return (struct.pack('<H', character) + bounds.bytes() + b'\x01\x41' + struct.pack('<H', bitmap)
            + bitmap_matrix(x0, y0) + b'\0' + edges.bytes())


def sprite_tags(tag, sprite, child):
    place = tag(26, b'\x06\x01\0' + struct.pack('<H', child) + b'\0')
    return tag(39, struct.pack('<HH', sprite, 1) + place + tag(1, b'') + tag(0, b''))


def tags(images, tag, first, export_empty=True):
    """(definition tags, ExportAssets tag) for {linkage: (width, height, rgba)}, three characters
    per image from `first`; no images and not `export_empty`: no ExportAssets tag."""
    out, exported, character = bytearray(), [], first
    for linkage in sorted(images):
        width, height, rgba = images[linkage]
        bitmap, drawn, sprite = character, character + 1, character + 2
        character += 3
        out += tag(36, struct.pack('<HBHH', bitmap, 5, width, height) + zlib.compress(rgba_to_swf(rgba), 9))
        out += tag(2, shape(drawn, bitmap, width, height))
        out += sprite_tags(tag, sprite, drawn)
        exported.append(struct.pack('<H', sprite) + linkage.encode('ascii') + b'\0')
    if not exported and not export_empty:
        return bytes(out), b''
    return bytes(out), tag(56, struct.pack('<H', len(exported)) + b''.join(exported))
