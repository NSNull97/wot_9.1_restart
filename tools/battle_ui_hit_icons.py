"""UI-02b: the hit indicator's icons from the local Lesta copy, kept in local/.

Owner order 2026-11-02 (round 3): "Иконки все же используем лестовские" — the
vehicle class icon at the name and the module icon of a critical hit come from
the installed Lesta copy, read only; the marker itself stays the project's own
(tools/battle_ui_hit_art.py). Git carries this tool and no image. A folder
without an icon leaves its place empty: the indicator works on its own art.

    python -B -X utf8 tools/battle_ui_hit_icons.py extract \\
        --lesta D:/Games/Tanki --out D:/WoT_9.1_Server/local/ui-borrowed/hit-indicator
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
ATLAS = 'gui/flash/atlases/damageIndicator.dds'
ATLAS_XML = 'gui/flash/atlases/damageIndicator.xml'
ATLAS_SHA256 = 'f96726a712031017f7c778a605ef78a82fe2f958b0fde39f3f96db0dfb5bb286'
ATLAS_XML_SHA256 = 'f727194b0b18e5901217c7e4e64e2710c22f065765ae3bba3850acbc57d05515'
MANIFEST = 'manifest.json'
MODULES = ('ammoCircle', 'commanderCircle', 'driverCircle', 'engineCircle', 'gunCircle', 'gunnerCircle',
           'radioCircle', 'radiomanCircle', 'reloaderCircle', 'tanksCircle', 'tracksCircle', 'triplexCircle',
           'turretCircle')
CLASSES = ('lightTank', 'mediumTank', 'heavyTank', 'SPG', 'AT-SPG')
VEHICLES = CLASSES + tuple('ally_' + name for name in CLASSES)
ICONS = MODULES + VEHICLES
MAX_SIDE = 64
MAX_PNG_BYTES = 256 * 1024
MAX_PACKAGE_MEMBER = 8 * 1024 * 1024


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
    """Read the pinned atlas out of the package, write the icon PNG files and a manifest."""
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
    for name in ICONS:
        box = rows[name]
        png = write_png(box[2], box[3], crop(rgba, width, box))
        (target / (name + '.png')).write_bytes(png)
        files[name] = {'atlas_box': box, 'sha256': _sha(png)}
    manifest = {'source': str(source).replace('\\', '/'), 'atlas': ATLAS, 'atlas_sha256': ATLAS_SHA256,
                'atlas_xml': ATLAS_XML, 'atlas_xml_sha256': ATLAS_XML_SHA256, 'files': files,
                'tool_sha256': _sha(Path(__file__).read_bytes())}
    (target / MANIFEST).write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding='utf-8')
    return manifest


def load(folder):
    """({linkage: image}, missing names). No folder or no file: that icon is absent."""
    root = Path(folder) if folder is not None else None
    images, missing = {}, []
    for name in ICONS:
        path = root / (name + '.png') if root is not None else None
        if path is not None and path.is_file():
            images[name] = read_png(path.read_bytes())
        else:
            missing.append(name)
    return images, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    cut = commands.add_parser('extract')
    cut.add_argument('--lesta', type=Path, required=True)
    cut.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = extract(args.lesta, args.out)
    print('%d icons written to %s' % (len(manifest['files']), args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
