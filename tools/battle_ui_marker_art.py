"""UI-06c: class icons above the vehicles, borrowed from the local Lesta copy.

Owner order 2026-11-03: «Иконки все же используем лестовские». Only the class
icons; the rest of the marker stays the project's own. The Lesta copy is read
only, the PNG files stay in local/ui-borrowed/ and never reach Git; this tool is
all Git carries. `extract` cuts the icons out of the pinned vehicle marker atlas;
`load` reads such a folder back for the movie. Any 8-bit RGBA PNG with a listed
name works, so the owner can swap in their own art. A missing file keeps the
native #717 icon of that class and colour.

    python -B -X utf8 tools/battle_ui_marker_art.py extract \
        --lesta D:/Games/Tanki --out D:/WoT_9.1_Server/local/ui-borrowed/vehicle-markers
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

PACKAGE = 'res/packages/gui-part1.pkg'
ATLAS = 'gui/flash/atlases/vehicleMarkerAtlas.dds'
ATLAS_XML = 'gui/flash/atlases/vehicleMarkerAtlas.xml'
ATLAS_SHA256 = '9989231d8e4de371750bf938c23e316c93b84459518d89080e7bd16661d57e06'
ATLAS_XML_SHA256 = 'c870029a29b70ba7828a4b84511a622ad95447cf5e09133e4899caa6f9825c61'
MANIFEST = 'manifest.json'
# The frame labels of the #717 marker and the class frames of its icon clip.
LABELS = ('green', 'red', 'gold', 'blue', 'yellow', 'purple')
CLASSES = ('lightTank', 'mediumTank', 'heavyTank', 'AT-SPG', 'mediumAT-SPG', 'heavyAT-SPG', 'SPG', 'mediumSPG',
           'heavySPG')
# Atlas names that differ from `<label>_<class>`.
ATLAS_NAMES = {'gold_heavyAT-SPG': 'gold_heavyAT_SPG'}
# The #717 icon canvas is 39 x 50 px; a larger file is refused.
MAX_WIDTH, MAX_HEIGHT = 39, 50
MAX_PNG_BYTES = 256 * 1024
MAX_PACKAGE_MEMBER = 32 * 1024 * 1024


def names():
    return tuple('%s_%s' % (label, cls) for label in LABELS for cls in CLASSES)


def linkage(name):
    return 'ProjectMarkerIcon_' + name


def _rgb565(value):
    return (value >> 11) * 255 // 31, ((value >> 5) & 63) * 255 // 63, (value & 31) * 255 // 31


def dxt5_box(raw, width, box):
    """Straight RGBA rows of `box` (x, y, w, h) of a DXT5 surface `width` wide;
    only the 4x4 blocks under the box are decoded."""
    x0, y0, w, h = box
    blocks = width // 4
    out = bytearray(w * h * 4)
    for top in range(y0 // 4 * 4, y0 + h, 4):
        for left in range(x0 // 4 * 4, x0 + w, 4):
            at = 128 + ((top // 4) * blocks + left // 4) * 16
            first, second = raw[at], raw[at + 1]
            bits = int.from_bytes(raw[at + 2:at + 8], 'little')
            colour0, colour1, picks = struct.unpack_from('<HHI', raw, at + 8)
            if first > second:
                alpha = [first, second] + [((7 - i) * first + i * second) // 7 for i in range(1, 7)]
            else:
                alpha = [first, second] + [((5 - i) * first + i * second) // 5 for i in range(1, 5)] + [0, 255]
            one, two = _rgb565(colour0), _rgb565(colour1)
            colours = (one, two, tuple((2 * a + b) // 3 for a, b in zip(one, two)),
                       tuple((a + 2 * b) // 3 for a, b in zip(one, two)))
            for y in range(4):
                for x in range(4):
                    px, py = left + x - x0, top + y - y0
                    if 0 <= px < w and 0 <= py < h:
                        at_pixel = (py * w + px) * 4
                        out[at_pixel:at_pixel + 3] = bytes(colours[(picks >> (2 * (4 * y + x))) & 3])
                        out[at_pixel + 3] = alpha[(bits >> (3 * (4 * y + x))) & 7]
    return bytes(out)


def atlas_rows(xml):
    """{name: (x, y, width, height)}; the text is a flat list, no XML parser."""
    pattern = (r'<name>\s*(\S+)\s*</name>\s*<x>\s*(\d+)\s*</x>\s*<y>\s*(\d+)\s*</y>'
               r'\s*<width>\s*(\d+)\s*</width>\s*<height>\s*(\d+)\s*</height>')
    return {m.group(1): tuple(int(v) for v in m.groups()[1:]) for m in re.finditer(pattern, xml)}


def write_png(width, height, rgba):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def _paeth(left, up, corner):
    guess = left + up - corner
    a, b, c = abs(guess - left), abs(guess - up), abs(guess - corner)
    return left if a <= b and a <= c else up if b <= c else corner


def read_png(raw):
    """(width, height, rgba) of an 8-bit RGBA PNG within the icon canvas; anything else is refused."""
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
    if head is None or head[2:4] != (8, 6) or head[6] != 0 or not (
            0 < head[0] <= MAX_WIDTH and 0 < head[1] <= MAX_HEIGHT):
        raise ValueError('8-bit RGBA PNG within the icon canvas required')
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
    if raw[:4] != b'DDS ' or raw[84:88] != b'DXT5':
        raise ValueError('DXT5 .dds required')
    width = struct.unpack_from('<I', raw, 16)[0]
    rows = atlas_rows(xml.decode('utf-8'))
    target = Path(out)
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in names():
        box = rows[ATLAS_NAMES.get(name, name)]
        if box[2] > MAX_WIDTH or box[3] > MAX_HEIGHT:
            raise ValueError('atlas icon exceeds the native canvas: ' + name)
        png = write_png(box[2], box[3], dxt5_box(raw, width, box))
        (target / (name + '.png')).write_bytes(png)
        files[name] = {'atlas_name': ATLAS_NAMES.get(name, name), 'atlas_box': box, 'sha256': _sha(png)}
    manifest = {'source': str(source).replace('\\', '/'), 'atlas': ATLAS, 'atlas_sha256': ATLAS_SHA256,
                'atlas_xml': ATLAS_XML, 'atlas_xml_sha256': ATLAS_XML_SHA256, 'files': files,
                'tool_sha256': _sha(Path(__file__).read_bytes())}
    (target / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding='utf-8')
    return manifest


def load(folder):
    """{linkage: (width, height, rgba)} of the listed PNG files present in `folder`;
    a missing folder or file is no error: that icon stays native."""
    images = {}
    if folder is None or not Path(folder).is_dir():
        return images
    for name in names():
        path = Path(folder) / (name + '.png')
        if path.is_file():
            images[linkage(name)] = read_png(path.read_bytes())
    return images


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='command', required=True)
    cut = sub.add_parser('extract')
    cut.add_argument('--lesta', required=True)
    cut.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    manifest = extract(args.lesta, args.out)
    print(json.dumps({'status': 'EXTRACTED', 'files': len(manifest['files']), 'out': args.out}))


if __name__ == '__main__':
    sys.exit(main())
