"""UI-06c round 11: the contour icons of the vehicles in the project's flat style.

Owner 2026-11-03: the battle interface goes towards a simple modern look and the
shaded contour icons stood out. The owner chose "flat with details" from a
preview (local/codex-tasks/BATTLE-UI-screens/round11) and asked to keep the class
colouring of the ears: #717 bakes the class into the picture (tanks olive grey,
tank destroyers blue grey, artillery brown), and PlayersPanel shows it as it is.

Round 13 (owner palette, preview round13/palette-preview.html accepted): one set
per colour of an ears row, the class a shade of the team colour (tank destroyers
cooler, artillery warmer): contour_ally and contour (the default path, which the
markers and other screens load) ally shades, contour_enemy enemy shades,
contour_own #D9B66F and contour_tk #38B8C8 for every class.
tools/battle_ui_ears_flash.py points each ears row at its set.

Prepare writes a res_mods copy of every contour icon of the client package,
restyled from the original pixels: a flat class colour, the native dark lines a
darker shade of it, the alpha lifted so the body is opaque. The class comes from
the native vehicle lists (item_defs/vehicles/<nation>/list.xml, the first class
tag). Nothing of the client enters Git. The vehicle markers (battle_ui_marker_look)
divide their bar colour by the class colour, so a marker shows its bar colour
with the same details.
"""
from __future__ import annotations

from pathlib import Path
import struct
import zipfile
import zlib

PACKAGE = 'res/packages/gui.pkg'
PREFIX = 'gui/maps/icons/vehicle/contour/'
TARGET = 'res_mods/0.9.1/' + PREFIX
FOLDER = 'res_mods/0.9.1/gui/maps/icons/vehicle/'
LISTS = 'res/scripts/item_defs/vehicles'
MAX_ICON_BYTES = 64 * 1024
MAX_SIDE = 256
# Class tag of a vehicle list -> class of the icon colour.
CLASSES = {'lightTank': 'tank', 'mediumTank': 'tank', 'heavyTank': 'tank', 'AT-SPG': 'td', 'SPG': 'spg'}
# Owner palette round 13: allies #9BAA8E, enemies #B3968F, own #D9B66F, team killer
# #38B8C8; tank destroyers and artillery the shades of the accepted preview.
ALLY = {'tank': (155, 170, 142), 'td': (136, 159, 175), 'spg': (179, 165, 132)}
ENEMY = {'tank': (179, 150, 143), 'td': (177, 145, 163), 'spg': (189, 157, 132)}
OWN, TEAM_KILLER = (217, 182, 111), (56, 184, 200)
SETS = {'contour': ALLY, 'contour_ally': ALLY, 'contour_enemy': ENEMY,
        'contour_own': {kind: OWN for kind in ALLY}, 'contour_tk': {kind: TEAM_KILLER for kind in ALLY}}
# The colours of the default path, which the vehicle markers divide by.
COLOURS = ALLY
# Brightness of a native icon body of each class (mean of the brightest channel of
# its opaque pixels on IS-7/113, FV215b 183/JagdPz E100, Object 261/G_E): a pixel
# that bright or brighter is the full class colour, darker ones are its lines.
BODY = {'tank': 125, 'td': 97, 'spg': 105}
LINE_SHADE = 0.45
ALPHA_GAIN = 1.5


def vehicle_classes(original: Path) -> dict:
    """{'<nation>-<vehicle>': class} from the native vehicle lists."""
    import packed_xml
    found = {}
    for path in sorted((Path(original) / LISTS).glob('*/list.xml')):
        nation = path.parent.name
        rows = dict(packed_xml.walk(packed_xml.decode(path.read_bytes())))
        for key, value in rows.items():
            parts = key.split('/')
            if len(parts) == 3 and parts[2] == 'tags[1]' and isinstance(value, str):
                name = parts[1].rsplit('[', 1)[0]
                kind = next((CLASSES[tag] for tag in value.split() if tag in CLASSES), None)
                if kind:
                    # Icon file names differ in case from the lists (UK-GB09_Churchill_VII, japan-Ha_go).
                    found[f'{nation}-{name}'.lower()] = kind
    if not found:
        raise ValueError('no vehicle classes in the native lists')
    return found


def _decode(data: bytes):
    """(width, height, RGBA rows) of an 8-bit RGBA non-interlaced PNG, or None."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    at, idat, head = 8, bytearray(), None
    while at + 8 <= len(data):
        size, kind = struct.unpack('>I4s', data[at:at + 8])
        chunk = data[at + 8:at + 8 + size]
        if kind == b'IHDR':
            head = struct.unpack('>IIBBBBB', chunk)
        elif kind == b'IDAT':
            idat += chunk
        at += 12 + size
    if head is None:
        return None
    width, height, depth, colour, _, _, interlace = head
    if depth != 8 or colour != 6 or interlace or not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
        return None
    raw = zlib.decompressobj().decompress(bytes(idat), (width * 4 + 1) * height + 1)
    if len(raw) != (width * 4 + 1) * height:
        return None
    stride, prev, rows, o = width * 4, bytearray(width * 4), [], 0
    for _ in range(height):
        kind, line = raw[o], bytearray(raw[o + 1:o + 1 + stride])
        o += 1 + stride
        for x in range(stride):
            a = line[x - 4] if x >= 4 else 0
            b = prev[x]
            c = prev[x - 4] if x >= 4 else 0
            if kind == 1:
                line[x] = (line[x] + a) & 255
            elif kind == 2:
                line[x] = (line[x] + b) & 255
            elif kind == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif kind == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            elif kind != 0:
                return None
        rows.append(bytes(line))
        prev = line
    return width, height, rows


def _encode(width: int, height: int, rows) -> bytes:
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    raw = b''.join(b'\0' + row for row in rows)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def restyle_pixel(r, g, b, a, kind, colours=COLOURS):
    """One native RGBA pixel in the flat style of its class, in `colours`."""
    if not a:
        return 0, 0, 0, 0
    shade = LINE_SHADE + (1 - LINE_SHADE) * min(1.0, max(r, g, b) / BODY[kind])
    colour = colours[kind]
    return (round(colour[0] * shade), round(colour[1] * shade), round(colour[2] * shade),
            min(255, round(a * ALPHA_GAIN)))


def restyle(data: bytes, kind: str, colours=COLOURS):
    """PNG bytes of the icon in the flat style of `kind` in `colours`, or None for a
    PNG of another layout (left native)."""
    decoded = _decode(data)
    if decoded is None:
        return None
    width, height, rows = decoded
    out = []
    for row in rows:
        line = bytearray()
        for x in range(width):
            line += bytes(restyle_pixel(*row[x * 4:x * 4 + 4], kind, colours))
        out.append(bytes(line))
    return _encode(width, height, out)


def payloads(original: Path):
    """({res_mods path: PNG bytes}, evidence) of every contour icon of a known class,
    in every set."""
    classes = vehicle_classes(original)
    out, skipped, unknown = {}, [], []
    with zipfile.ZipFile(Path(original) / PACKAGE) as package:
        for info in package.infolist():
            if not info.filename.startswith(PREFIX) or not info.filename.endswith('.png'):
                continue
            name = info.filename[len(PREFIX):-4]
            if '/' in name:
                continue
            kind = classes.get(name.lower())
            if kind is None:
                unknown.append(name)
                continue
            if info.file_size > MAX_ICON_BYTES:
                skipped.append(name)
                continue
            native = package.read(info)
            if _decode(native) is None:
                skipped.append(name)
                continue
            for folder, colours in SETS.items():
                out[FOLDER + folder + '/' + name + '.png'] = restyle(native, kind, colours)
    icons = [path for path in out if path.startswith(TARGET)]
    evidence = {'contour_icons': len(icons), 'sets': sorted(SETS),
                'by_class': {k: sum(1 for n in icons if classes[n[len(TARGET):-4].lower()] == k) for k in COLOURS},
                'left_native_other_layout': sorted(skipped), 'left_native_no_class': sorted(unknown)}
    return out, evidence
