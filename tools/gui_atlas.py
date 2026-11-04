"""Read-only pieces of the #717 / Lesta GUI atlases and bounded RGBA PNG files.

Shared by the borrowed-icon tools (battle_ui_art, battle_ui_marker_art,
battle_ui_hit_icons): the top DXT5 level of an atlas .dds, its XML list of
sub-images, a crop of one of them, and the 8-bit RGBA PNG files the owner may
swap in. Each caller passes its own limits; anything outside them is refused.
"""
from __future__ import annotations

import hashlib
import re
import struct
import zlib

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def rgb565(value):
    return (value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31


def dxt5(data, width, height):
    """Straight RGBA rows of one DXT5 surface; pinned input, plain formulas."""
    if width % 4 or height % 4 or len(data) < width * height:
        raise ValueError('DXT5 surface outside its bounds')
    pixels, at = bytearray(width * height * 4), 0
    for top in range(0, height, 4):
        for left in range(0, width, 4):
            first, second = data[at], data[at + 1]
            bits = int.from_bytes(data[at + 2:at + 8], 'little')
            colour0, colour1, picks = struct.unpack_from('<HHI', data, at + 8)
            at += 16
            if first > second:
                alpha = [first, second] + [((7 - i) * first + i * second) // 7 for i in range(1, 7)]
            else:
                alpha = [first, second] + [((5 - i) * first + i * second) // 5 for i in range(1, 5)] + [0, 255]
            one, two = rgb565(colour0), rgb565(colour1)
            colours = (one, two, tuple((2 * a + b) // 3 for a, b in zip(one, two)),
                       tuple((a + 2 * b) // 3 for a, b in zip(one, two)))
            for y in range(4):
                for x in range(4):
                    at_pixel = ((top + y) * width + left + x) * 4
                    pixels[at_pixel:at_pixel + 3] = bytes(colours[(picks >> (2 * (4 * y + x))) & 3])
                    pixels[at_pixel + 3] = alpha[(bits >> (3 * (4 * y + x))) & 7]
    return pixels


def dds_surface(raw):
    """(width, height, rgba) of the top level of a DXT5 .dds file."""
    if raw[:4] != b'DDS ' or len(raw) < 128 or raw[84:88] != b'DXT5':
        raise ValueError('DXT5 .dds required')
    height, width = struct.unpack_from('<II', raw, 12)
    if not (0 < width <= 4096 and 0 < height <= 4096):
        raise ValueError('DDS size outside its bounds')
    return width, height, dxt5(raw[128:], width, height)


def atlas_rows(xml):
    """{name: (x, y, width, height)}; the text is a flat list, no XML parser."""
    rows = {}
    pattern = (r'<name>\s*(\S+)\s*</name>\s*<x>\s*(\d+)\s*</x>\s*<y>\s*(\d+)\s*</y>'
               r'\s*<width>\s*(\d+)\s*</width>\s*<height>\s*(\d+)\s*</height>')
    for match in re.finditer(pattern, xml):
        rows[match.group(1)] = tuple(int(value) for value in match.groups()[1:])
    return rows


def crop(rgba, atlas_width, box):
    x, y, width, height = box
    rows = bytearray()
    for row in range(y, y + height):
        rows += rgba[(row * atlas_width + x) * 4:(row * atlas_width + x + width) * 4]
    return bytes(rows)


def write_png(width, height, rgba):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def read_png(raw, max_bytes, max_width, max_height, limit='the size limit'):
    """(width, height, rgba) of an 8-bit RGBA PNG within the caller's limits; anything else is refused."""
    if len(raw) > max_bytes or raw[:8] != PNG_SIGNATURE:
        raise ValueError('bounded PNG required')
    at, head, idat = 8, None, bytearray()
    while at + 8 <= len(raw):
        size, kind = struct.unpack_from('>I4s', raw, at)
        data = raw[at + 8:at + 8 + size]
        if len(data) != size:
            raise ValueError('truncated PNG chunk')
        at += 12 + size
        if kind == b'IHDR':
            head = struct.unpack('>IIBBBBB', data)
        elif kind == b'IDAT':
            idat += data
        elif kind == b'IEND':
            break
    if head is None or head[2:4] != (8, 6) or head[6] != 0 or not (
            0 < head[0] <= max_width and 0 < head[1] <= max_height):
        raise ValueError('8-bit RGBA PNG within %s required' % limit)
    width, height = head[:2]
    stride = width * 4
    expected = (stride + 1) * height
    rows = zlib.decompressobj().decompress(bytes(idat), expected)
    if len(rows) != expected:
        raise ValueError('PNG pixels differ from its header')
    pixels, above = bytearray(), bytearray(stride)
    for y in range(height):
        at = y * (stride + 1)
        kind, row = rows[at], bytearray(rows[at + 1:at + 1 + stride])
        if kind > 4:
            raise ValueError('unknown PNG filter')
        for i in range(stride):
            left = row[i - 4] if i >= 4 else 0
            up = above[i]
            corner = above[i - 4] if i >= 4 else 0
            row[i] = (row[i] + (0, left, up, (left + up) // 2, paeth(left, up, corner))[kind]) & 255
        pixels += row
        above = row
    return width, height, bytes(pixels)


def paeth(left, up, corner):
    guess = left + up - corner
    a, b, c = abs(guess - left), abs(guess - up), abs(guess - corner)
    return left if a <= b and a <= c else up if b <= c else corner


def sha(data):
    return hashlib.sha256(data).hexdigest()
