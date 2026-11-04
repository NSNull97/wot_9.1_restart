"""Client resource patch for the stand-only test vehicle T-62A (T).

Owner order 2026-11-04/05: a fully separate vehicle copied from the 0.9.1 T-62A,
named "Т-62А (Т)", tier 11, armour 1000 mm. The server is authoritative for hits
(stand manifest test_armor_mm); the client copy carries 1000 mm too so the
vehicle stats show it. Not in the nation tree XML (the client hides such a
vehicle from the tree) and not in the shop (notInShop + secret, as T62A_sport).

Everything is derived at install time from the local original client and
written as ignored install payloads; nothing from the client is committed.

Payloads (relative to the client root):
- res_mods/0.9.1/scripts/common/items/vehicles.pyc: `_readLevel` bound 1..11
  (VERIFIED original bound 1..10 rejects tier 11), via client_level_bound27.py.
- res_mods/0.9.1/scripts/item_defs/vehicles/ussr/list.xml: original list plus
  T62A_T (copy of T62A: new id, own name keys, level 11, price 0, notInShop, secret).
- .../ussr/components/chassis.xml, turrets.xml: original ids plus the test
  vehicle's own chassis/turret names (as T62A_sport has its own pair).
- .../ussr/t62a_t.xml: T62A definition with the chassis/turret renamed and every
  nonzero hull/turret/gun armour value set to 1000 (tracks and zero-armour records stay).
- res/text/LC_MESSAGES/ussr_vehicles.mo: original catalog plus three new keys,
  res/text/LC_MESSAGES/tooltips.mo: plus `level/11` = XI (original `level/10` = X);
  both replaced in place like menu.mo (a res_mods text dir would shadow every domain).
- res_mods/0.9.1/gui/maps/icons/levels/tank_level_11.png and
  .../filters/levels/level_11.png: owner-supplied Lesta icons from
  local/assets/lesta-level11 (provenance.json), never committed.
"""
import argparse
import copy
import gettext
import hashlib
import io
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import packed_xml_writer as pxml  # noqa: E402

SCHEMA = 'wot091-test-vehicle-client.v1'
BASE = 'T62A'
NAME = 'T62A_T'
VEHICLE_ID = 50
CHASSIS = ('Chassis_T62A', 'Chassis_T62A_T', 62)
TURRET = ('Turret_1_T62A', 'Turret_1_T62A_T', 50)
LEVEL = 11
ARMOR_MM = 1000
TEXT = {
    'T62A_T': 'Т-62А (Т)',
    'T62A_T_short': 'Т-62А (Т)',
    'T62A_T_descr': 'Тестовая машина стенда: копия Т-62А, броня 1000 мм. Не историческая машина.',
}
DEFS = 'scripts/item_defs/vehicles/ussr/'
OUT_DEFS = 'res_mods/0.9.1/' + DEFS
ICONS = {
    'gui__maps__icons__levels__tank_level_11.png': 'res_mods/0.9.1/gui/maps/icons/levels/tank_level_11.png',
    'gui__maps__icons__filters__levels__level_11.png': 'res_mods/0.9.1/gui/maps/icons/filters/levels/level_11.png',
}
MO = 'res/text/LC_MESSAGES/ussr_vehicles.mo'
TOOLTIPS_MO = 'res/text/LC_MESSAGES/tooltips.mo'
TOOLTIPS = {'level/11': 'XI'}
DEFAULT_PY27 = ROOT / 'local/toolchains-py27-20261019/cpython-2.7.3-x86/python.exe'
DEFAULT_ICONS = ROOT / 'local/assets/lesta-level11'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, limit=16 * 1024 * 1024):
    raw = Path(path).read_bytes()
    if len(raw) > limit:
        raise ValueError(f'{path}: size bound')
    return raw


def ids_of(document):
    node = document['root'].child('ids')
    return {name: pxml.value_int(value) for name, value in node.children}


def add_id(raw, name, wanted):
    document = pxml.parse(raw)
    ids = ids_of(document)
    if name in ids or wanted in ids.values():
        raise ValueError(f'component {name} or id {wanted} already present')
    document['root'].child('ids').children.append((name, pxml.integer(wanted)))
    return pxml.encode(document)


def vehicle_list(raw):
    document = pxml.parse(raw)
    root = document['root']
    used = {pxml.value_int(entry.child('id')) for _, entry in root.children}
    if root.has(NAME) or VEHICLE_ID in used:
        raise ValueError('test vehicle name or id already in the original list')
    entry = copy.deepcopy(root.child(BASE))
    if pxml.value_int(entry.child('level')) != 10:
        raise ValueError('unmeasured base level')
    entry.replace('id', pxml.integer(VEHICLE_ID))
    entry.replace('userString', pxml.text('#ussr_vehicles:' + NAME))
    entry.replace('shortUserString', pxml.text('#ussr_vehicles:' + NAME + '_short'))
    entry.replace('description', pxml.text('#ussr_vehicles:' + NAME + '_descr'))
    entry.replace('level', pxml.integer(LEVEL))
    entry.replace('price', pxml.integer(0))
    entry.replace('tags', pxml.text(pxml.value_text(entry.child('tags')) + ' secret'))
    if entry.has('notInShop'):
        raise ValueError('unmeasured base entry: notInShop present')
    at = [i for i, (key, _) in enumerate(entry.children) if key == 'price'][0] + 1
    entry.children.insert(at, ('notInShop', (pxml.BOOL, b'\x01')))
    root.children.append((NAME, entry))
    return pxml.encode(document)


def vehicle_definition(raw):
    document = pxml.parse(raw)
    root = document['root']
    root.child('chassis').rename(CHASSIS[0], CHASSIS[1])
    root.child('turrets0').rename(TURRET[0], TURRET[1])
    turret = root.child('turrets0').child(TURRET[1])
    gun = [data for key, data in turret.child('guns').children if isinstance(data, pxml.Element)]
    changed = 0
    for armour in [root.child('hull').child('armor'), turret.child('armor')] + [g.child('armor') for g in gun]:
        for i, (key, data) in enumerate(armour.children):
            if isinstance(data, pxml.Element):
                if data.own[0] == pxml.INT and pxml.value_int(data.own) > 0:
                    data.own = pxml.integer(ARMOR_MM); changed += 1
            elif data[0] == pxml.INT and pxml.value_int(data) > 0:
                armour.children[i] = (key, pxml.integer(ARMOR_MM)); changed += 1
    if changed < 10:
        raise ValueError('unmeasured armour layout')
    return pxml.encode(document)


def add_mo_keys(raw, additions):
    if len(raw) > 8 * 1024 * 1024 or len(raw) < 28 or raw[:4] != b'\xde\x12\x04\x95':
        raise ValueError('unmeasured MO header')
    _, revision, count, originals, translations, _, _ = struct.unpack_from('<7I', raw)
    if revision != 0 or not 1 <= count <= 50000:
        raise ValueError('unmeasured MO version/count')

    def entry(base, index):
        length, offset = struct.unpack_from('<2I', raw, base + index * 8)
        if offset + length >= len(raw) or raw[offset + length] != 0:
            raise ValueError('invalid MO string boundary')
        return raw[offset:offset + length]

    mapping = dict((entry(originals, i), entry(translations, i)) for i in range(count))
    if len(mapping) != count:
        raise ValueError('duplicate MO keys')
    for key, value in additions.items():
        if key.encode('utf-8') in mapping:
            raise ValueError('MO key already present: ' + key)
        mapping[key.encode('utf-8')] = value.encode('utf-8')
    pairs = sorted(mapping.items())
    total = len(pairs)
    start = 28 + 16 * total
    tables, strings = [], bytearray()
    for original, _ in pairs:
        tables.append((len(original), start + len(strings)))
        strings.extend(original + b'\0')
    for _, translation in pairs:
        tables.append((len(translation), start + len(strings)))
        strings.extend(translation + b'\0')
    result = (struct.pack('<7I', 0x950412de, 0, total, 28, 28 + 8 * total, 0, 0)
              + b''.join(struct.pack('<2I', *t) for t in tables) + bytes(strings))
    check = gettext.GNUTranslations(io.BytesIO(result))
    before = gettext.GNUTranslations(io.BytesIO(raw))
    for key, value in additions.items():
        if check.gettext(key) != value:
            raise ValueError('generated MO verification failed')
    for key in mapping:
        text = key.decode('utf-8')
        if key and text not in additions and check.gettext(text) != before.gettext(text):
            raise ValueError('generated MO changed an original key')
    return result


def level_pyc(original, python27, scratch):
    source = original / 'res/scripts/common/items/vehicles.pyc'
    target = scratch / 'vehicles.pyc'
    subprocess.run([str(python27), '-E', '-S', str(ROOT / 'tools/client_level_bound27.py'), str(source), str(target)],
                   check=True, capture_output=True, timeout=60)
    return read(target)


def build(original, python27=DEFAULT_PY27, icons=DEFAULT_ICONS, scratch=None):
    original = Path(original)
    scratch = Path(scratch) if scratch else ROOT / 'local/build/test-vehicle-client'
    scratch.mkdir(parents=True, exist_ok=True)
    defs = original / 'res' / DEFS
    payloads, sources = {}, {}
    for name in ('list.xml', 'components/chassis.xml', 'components/turrets.xml', 't62a.xml'):
        sources[DEFS + name] = read(defs / name)
    payloads[OUT_DEFS + 'list.xml'] = vehicle_list(sources[DEFS + 'list.xml'])
    payloads[OUT_DEFS + 'components/chassis.xml'] = add_id(sources[DEFS + 'components/chassis.xml'], CHASSIS[1], CHASSIS[2])
    payloads[OUT_DEFS + 'components/turrets.xml'] = add_id(sources[DEFS + 'components/turrets.xml'], TURRET[1], TURRET[2])
    payloads[OUT_DEFS + 't62a_t.xml'] = vehicle_definition(sources[DEFS + 't62a.xml'])
    payloads['res_mods/0.9.1/scripts/common/items/vehicles.pyc'] = level_pyc(original, python27, scratch)
    sources[MO] = read(original / MO, 8 * 1024 * 1024)
    payloads[MO] = add_mo_keys(sources[MO], TEXT)
    sources[TOOLTIPS_MO] = read(original / TOOLTIPS_MO, 8 * 1024 * 1024)
    payloads[TOOLTIPS_MO] = add_mo_keys(sources[TOOLTIPS_MO], TOOLTIPS)
    provenance = json.loads((Path(icons) / 'provenance.json').read_text(encoding='utf-8'))
    pinned = {Path(row['member']).name: row['sha256'] for row in provenance['files'] if 'member' in row}
    for stored, target in ICONS.items():
        raw = read(Path(icons) / stored, 65536)
        if pinned.get(Path(target).name) != sha(raw):
            raise ValueError('icon does not match its provenance pin: ' + stored)
        payloads[target] = raw
    evidence = {
        'schema': SCHEMA, 'vehicle': NAME, 'base': BASE, 'vehicle_id': VEHICLE_ID, 'level': LEVEL,
        'chassis': list(CHASSIS), 'turret': list(TURRET), 'text': TEXT,
        'sources': {k: sha(v) for k, v in sources.items()},
        'payloads': {k: sha(v) for k, v in sorted(payloads.items())},
        'icons_provenance': provenance.get('note'),
        'overwrites_original': [MO, TOOLTIPS_MO], 'armor_mm': ARMOR_MM,
    }
    return payloads, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('command', choices=('build',))
    parser.add_argument('--original', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise SystemExit('fresh --out directory required')
    payloads, evidence = build(args.original, scratch=out / 'scratch')
    for relative, raw in payloads.items():
        path = out / 'payload' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (out / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(evidence['payloads'], indent=1))


if __name__ == '__main__':
    main()
