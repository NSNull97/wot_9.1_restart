"""UI-03b: borrowed feed and history icons as local files and SWF tags.

Owner order 2026-11-02 (round 3): "Иконки все же используем лестовские" -- the
icons only: backgrounds, gradients, layout and halos stay the project's own. They
come from the installed Lesta copy, read only, and stay in local/; git carries
this tool and no image. `extract` cuts PNG files out of the Lesta battle atlas;
`embed` adds a folder of such PNG files to the native battle movie as exported
clips before its last frame action. Any 8-bit RGBA PNG with a listed name works,
so the owner can later swap in their own art. Without the folder the widgets draw
their own glyphs.

    python -B -X utf8 tools/battle_ui_art.py extract \
        --lesta D:/Games/Tanki --out D:/WoT_9.1_Server/local/ui-borrowed/battle-icons
"""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import battle_ui_hit_flash as flash

PACKAGE = 'res/packages/gui-part1.pkg'
ATLAS = 'gui/flash/atlases/battleAtlas.dds'
ATLAS_XML = 'gui/flash/atlases/battleAtlas.xml'
ATLAS_SHA256 = '47ef0583ba7ed7d326283a67eba8b1420249d34cd99cf09d64453cd1fe9a7698'
ATLAS_XML_SHA256 = 'a128d17896001989794820ad5ccab6e026b00381bc7a4ea92ca09023cc1dc8a5'
MANIFEST = 'manifest.json'
RIBBONS = tuple('ribbons' + name for name in (
    'Damage', 'DamageEnemy', 'Armor', 'Defence', 'Capture', 'Spotted', 'Ram', 'Kill', 'Crits', 'CritsEnemy', 'Burn',
    'BurnEnemy', 'AssistSpot', 'AssistTrack'))
CLASSES = tuple('whiteIcon%s16x16' % name for name in ('LightTank', 'MediumTank', 'HeavyTank', 'SPG', 'At-SPG'))
DAMAGE_LOG = tuple('damageLog_%s_16x16' % name for name in (
    'damage', 'damage_enemy', 'critical', 'critical_enemy', 'reflect', 'ram', 'ram_enemy', 'fire', 'fire_enemy',
    'coordinate', 'immobilized', 'assist', 'kill'))
FEED_SPRITES = RIBBONS
HISTORY_SPRITES = DAMAGE_LOG + CLASSES
ALL_SPRITES = RIBBONS + DAMAGE_LOG + CLASSES
# Above the characters of the #717 battle.swf (679 at most).
FIRST_CHARACTER = 1000
MAX_SIDE = 1024
MAX_PNG_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_MEMBER = 32 * 1024 * 1024


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
            one, two = _rgb565(colour0), _rgb565(colour1)
            colours = (one, two, tuple((2 * a + b) // 3 for a, b in zip(one, two)),
                       tuple((a + 2 * b) // 3 for a, b in zip(one, two)))
            for y in range(4):
                for x in range(4):
                    at_pixel = ((top + y) * width + left + x) * 4
                    pixels[at_pixel:at_pixel + 3] = bytes(colours[(picks >> (2 * (4 * y + x))) & 3])
                    pixels[at_pixel + 3] = alpha[(bits >> (3 * (4 * y + x))) & 7]
    return pixels


def _rgb565(value):
    return (value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31


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
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def read_png(raw):
    """(width, height, rgba) of an 8-bit RGBA PNG. Bounded; anything else is refused."""
    if len(raw) > MAX_PNG_BYTES or raw[:8] != b'\x89PNG\r\n\x1a\n':
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
    if head is None or head[2:4] != (8, 6) or head[6] != 0 or not (0 < head[0] <= MAX_SIDE and 0 < head[1] <= MAX_SIDE):
        raise ValueError('8-bit RGBA PNG within the size limit required')
    width, height = head[:2]
    stride = width * 4
    expected = (stride + 1) * height
    stream = zlib.decompressobj()
    rows = stream.decompress(bytes(idat), expected)
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
            row[i] = (row[i] + (0, left, up, (left + up) // 2, _paeth(left, up, corner))[kind]) & 255
        pixels += row
        above = row
    return width, height, bytes(pixels)


def _paeth(left, up, corner):
    guess = left + up - corner
    a, b, c = abs(guess - left), abs(guess - up), abs(guess - corner)
    return left if a <= b and a <= c else up if b <= c else corner


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def extract(lesta, out):
    """Read the pinned atlas out of the package, write PNG files and a manifest."""
    source = Path(lesta) / PACKAGE
    with zipfile.ZipFile(source) as package:
        for member in (ATLAS, ATLAS_XML):
            if package.getinfo(member).file_size > MAX_PACKAGE_MEMBER:
                raise ValueError('atlas member is oversized')
        raw, xml = package.read(ATLAS), package.read(ATLAS_XML)
    if _sha(raw) != ATLAS_SHA256 or _sha(xml) != ATLAS_XML_SHA256:
        raise ValueError('Lesta atlas differs from the pinned bytes')
    width, _, rgba = dds_surface(raw)
    rows = atlas_rows(xml.decode('ascii'))
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ALL_SPRITES:
        box = rows[name]
        png = write_png(box[2], box[3], crop(rgba, width, box))
        (target / (name + '.png')).write_bytes(png)
        files[name] = {'atlas_box': box, 'sha256': _sha(png)}
    manifest = {'source': str(source).replace('\\', '/'), 'atlas': ATLAS, 'atlas_sha256': ATLAS_SHA256,
                'atlas_xml': ATLAS_XML, 'atlas_xml_sha256': ATLAS_XML_SHA256, 'files': files,
                'tool_sha256': _sha(Path(__file__).read_bytes())}
    (target / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding='utf-8')
    return manifest


def _rgba_to_swf(rgba):
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


def sprite_tags(sprite, child):
    place = flash.tag(26, b'\x06\x01\0' + struct.pack('<H', child) + b'\0')
    return flash.tag(39, struct.pack('<HH', sprite, 1) + place + flash.tag(1, b'') + flash.tag(0, b''))


def tags(images):
    """Definition tags and the ExportAssets tag for {linkage: (width, height, rgba)}."""
    out, exported, character = bytearray(), [], FIRST_CHARACTER
    for linkage in sorted(images):
        width, height, rgba = images[linkage]
        bitmap, drawn, sprite = character, character + 1, character + 2
        character += 3
        out += flash.tag(36, struct.pack('<HBHH', bitmap, 5, width, height) + zlib.compress(_rgba_to_swf(rgba), 9))
        out += flash.tag(2, shape(drawn, bitmap, width, height))
        out += sprite_tags(sprite, drawn)
        exported.append(struct.pack('<H', sprite) + linkage.encode('ascii') + b'\0')
    return bytes(out) + flash.tag(56, struct.pack('<H', len(exported)) + b''.join(exported))


def embed(movie, images, actions):
    """The built movie with the sprites exported just before its last DoAction,
    the added one, so that action can attach them; `actions` is the DoAction
    count the built movie must have. No images: the same bytes."""
    if not images:
        return movie
    body = flash.expanded(movie)
    start = ((5 + 4 * (body[0] >> 3) + 7) // 8) + 4
    rows = [row for row in flash.tags(body, start) if row[0] == 12]
    if len(rows) != actions:
        raise ValueError('built movie layout differs')
    at = rows[-1][1]
    out = body[:at] + tags(images) + body[at:]
    return movie[:4] + struct.pack('<I', len(out) + 8) + zlib.compress(out, 9)


def load(folder, names):
    """({linkage: image}, missing names). One missing file gives ({}, missing):
    the caller keeps the drawn graphics."""
    root = Path(folder)
    missing = [name for name in names if not (root / (name + '.png')).is_file()]
    if missing:
        return {}, missing
    return dict((name, read_png((root / (name + '.png')).read_bytes())) for name in names), []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    cut = commands.add_parser('extract')
    cut.add_argument('--lesta', type=Path, required=True)
    cut.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = extract(args.lesta, args.out)
    print('%d sprites written to %s' % (len(manifest['files']), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
