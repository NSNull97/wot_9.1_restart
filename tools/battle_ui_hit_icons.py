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

from gui_atlas import atlas_rows, crop, dds_surface, dxt5, sha as _sha, write_png
import gui_atlas

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


def read_png(raw):
    """(width, height, rgba) of an 8-bit RGBA PNG. Bounded; anything else is refused."""
    return gui_atlas.read_png(raw, MAX_PNG_BYTES, MAX_SIDE, MAX_SIDE)


def haloed(width, height, rgba, pad=2, strength=0.75):
    """The icon on a black halo: its alpha spread by a pixel, under it, padded."""
    big_w, big_h = width + 2 * pad, height + 2 * pad
    alpha = [0] * (big_w * big_h)
    for y in range(height):
        for x in range(width):
            alpha[(y + pad) * big_w + x + pad] = rgba[(y * width + x) * 4 + 3]
    out = bytearray(big_w * big_h * 4)
    for y in range(big_h):
        for x in range(big_w):
            near = max(alpha[yy * big_w + xx] for yy in range(max(0, y - 1), min(big_h, y + 2))
                       for xx in range(max(0, x - 1), min(big_w, x + 2)))
            under = near * strength / 255.0
            top = alpha[y * big_w + x] / 255.0
            total = top + under * (1 - top)
            at = (y * big_w + x) * 4
            if total:
                if pad <= x < pad + width and pad <= y < pad + height:
                    src = ((y - pad) * width + x - pad) * 4
                    out[at:at + 3] = bytes(int(round(rgba[src + k] * top / total)) for k in range(3))
                out[at + 3] = int(round(total * 255))
    return big_w, big_h, bytes(out)


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
