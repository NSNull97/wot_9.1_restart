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

from gui_atlas import atlas_rows, crop, dds_surface, dxt5, sha as _sha, write_png
import gui_atlas
import swf_bitmap

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


def read_png(raw):
    """(width, height, rgba) of an 8-bit RGBA PNG. Bounded; anything else is refused."""
    return gui_atlas.read_png(raw, MAX_PNG_BYTES, MAX_SIDE, MAX_SIDE)


def tags(images):
    """Definition tags and the ExportAssets tag for {linkage: (width, height, rgba)}."""
    definitions, export = swf_bitmap.tags(images, flash.tag, FIRST_CHARACTER)
    return definitions + export


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
