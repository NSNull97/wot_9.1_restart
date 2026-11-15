"""Export project-calibrated foliage from the pinned Prokhorovka #717 assets."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from tools.content0_s5a_fallen_foliage import catalog_crown_rows, numeric_vector, pinned_json
from tools.content0_s5a_stand import ROOT, json_unique, read_stable
from tools.malinovka_bush_volumes import volume
from tools.map_package import decode, file_digest, member, no_links, open_archive, signed16, walk


ASSET = '05_prohorovka'
SCHEMA = 'content0-s5a-prohorovka-bush-volumes.v1'
CALIBRATION_SCHEMA = 'content0-s5a-prohorovka-bush-calibration.v1'
CLASSIFICATION = 'PROJECT_CALIBRATION_NOT_HISTORICAL'
CALIBRATION = ROOT / f'config/rulesets/{CALIBRATION_SCHEMA}.json'
PREFIX = 'speedtree/05_Prohorovka/'
PACKAGE_PIN = {'bytes': 87810684, 'sha256': '05081facbe1451688fd853612a85c725ed7140a4d83ddf134c2283512980cd6d'}
CATALOG_SHA256 = '61ce7951421091427a122e1c3875481f4053f3a6b9c910cb98195a644daff6d6'
PHYSICS_SHA256 = '9d358a48da303abaf15572f478dddc16971864960d9341943cc6d207b32b3265'
PROJECTILE_SHA256 = '3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7'
PROHOROVKA_FOLIAGE_SHA256 = 'b5efc1e078b46988ed673d1316604bc5b38445e97f4c404b8907bd8931d9c83d'
CHUNK = re.compile(r'spaces/05_prohorovka/([0-9a-f]{4})([0-9a-f]{4})o\.chunk\Z')
BUSH_COUNTS = {PREFIX + name + '.spt': count for name, count in (('Bush', 723), ('Bush_1', 598), ('Shrub_1', 771))}
TREE_COUNTS = {PREFIX + name + '.spt': count for name, count in (
    ('BirchFall', 35), ('BirchFall_1', 135), ('Fir', 91), ('Linden', 82), ('Maple', 96),
    ('Maple_1', 49), ('Poplar', 116), ('Poplar_1', 22))}
MAX_OUTPUT = 2 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def calibration_rows(raw):
    config = json_unique(raw)
    keys = {'schema', 'map', 'classification', 'description', 'fire_near_distance_m', 'fire_near_multiplier',
            'bushes', 'crowns'}
    if (type(config) is not dict or set(config) != keys or config['schema'] != CALIBRATION_SCHEMA
            or config['map'] != ASSET or config['classification'] != CLASSIFICATION
            or type(config['description']) is not str or not 0 < len(config['description']) <= 1024
            or config['fire_near_distance_m'] != 15.0 or config['fire_near_multiplier'] != 0.25):
        raise ValueError('Prokhorovka calibration identity or fire parameters')
    for section, names in (('bushes', BUSH_COUNTS), ('crowns', TREE_COUNTS)):
        rows = config[section]
        if type(rows) is not dict or set(rows) != set(names):
            raise ValueError('Prokhorovka calibration resource set')
        fields = {'bytes', 'sha256', 'center_local', 'radii_local', 'concealment_additive'}
        if section == 'crowns':
            fields.add('canopy_class')
        for row in rows.values():
            if (type(row) is not dict or set(row) != fields
                    or type(row['bytes']) is not int or not 0 < row['bytes'] <= 8 * 1024 * 1024
                    or type(row['sha256']) is not str or re.fullmatch('[a-f0-9]{64}', row['sha256']) is None
                    or not numeric_vector(row['center_local'], 3, -100, 100)
                    or not numeric_vector(row['radii_local'], 3, 0.01, 100)
                    or not numeric_vector([row['concealment_additive']], 1, 0.001, 1)
                    or (section == 'crowns' and row['canopy_class'] not in ('leafy', 'needle'))):
                raise ValueError('Prokhorovka resource calibration bounds')
    return config


def export_bushes(archive, settings):
    rows, chunk_pins, counts = [], [], Counter()
    files = sorted(info.filename for info in archive.infolist() if info.filename.endswith('.chunk'))
    if len(files) != 144:
        raise ValueError('unexpected Prokhorovka chunk count')
    seen_chunks = set()
    for path in files:
        match = CHUNK.fullmatch(path)
        if match is None:
            raise ValueError('unexpected Prokhorovka chunk path')
        chunk = tuple(signed16(value) for value in match.groups())
        if chunk in seen_chunks or any(not -6 <= value <= 5 for value in chunk):
            raise ValueError('invalid Prokhorovka chunk coordinate')
        seen_chunks.add(chunk)
        raw = member(archive, path)
        chunk_pins.append({'chunk': list(chunk), 'sha256': digest(raw)})
        trees = (item for item in decode(raw)['children'] if item['name'] == 'speedtree')
        for index, item in enumerate(trees, start=1):
            if index > 5000:
                raise ValueError('per-chunk SpeedTree bound')
            fields = dict(walk(item['data']))
            resource = fields.get('/spt[1]')
            if type(resource) is not str or len(resource) > 512:
                raise ValueError('invalid SpeedTree resource')
            if resource not in settings:
                continue
            seed = fields.get('/seed[1]')
            if type(seed) is not int or not 0 <= seed <= 0xffffffff:
                raise ValueError('invalid SpeedTree seed')
            counts[resource] += 1
            if counts[resource] > BUSH_COUNTS[resource]:
                raise ValueError('unexpected additional Prokhorovka bush')
            source = {'chunk': list(chunk), 'speedtree_index': index, 'resource': resource,
                      'seed': seed, 'transform': fields.get('/transform[1]')}
            rows.append(volume(source, settings[resource]))
    if counts != BUSH_COUNTS:
        raise ValueError('Prokhorovka bush instance count differs')
    return rows, chunk_pins


def export_crowns(catalog_path, physics_path, settings):
    catalog_path = no_links(catalog_path)
    physics_path = no_links(physics_path)
    catalog = pinned_json(catalog_path, catalog_path.parent, CATALOG_SHA256)
    physics = pinned_json(physics_path, physics_path.parent, PHYSICS_SHA256)
    if (catalog['map'] != ASSET or catalog['version'] != 8 or catalog['contacts'] is not True
            or catalog['physics_manifest_sha256'] != PHYSICS_SHA256
            or catalog['projectile_manifest_sha256'] != PROJECTILE_SHA256 or physics['map'] != ASSET):
        raise ValueError('Prokhorovka contact, collision and map identity differ')
    trees = [row for row in catalog['objects'] if row['kind'] == 'tree']
    if Counter(row['resource'] for row in trees) != TREE_COUNTS:
        raise ValueError('Prokhorovka crown catalogue coverage differs')
    return catalog_crown_rows(trees, physics['instances'], settings)


def build(original, catalog_path, physics_path):
    """Return reproducible export bytes, using only checked source files and calibration."""
    raw = read_stable(no_links(CALIBRATION), limit=32 * 1024)
    config = calibration_rows(raw)
    package = no_links(Path(original) / 'res/packages' / f'{ASSET}.pkg')
    before = package.stat()
    if file_digest(package) != PACKAGE_PIN:
        raise ValueError('Prokhorovka #717 map package pin differs')
    with open_archive(package) as archive:
        for name, row in (config['bushes'] | config['crowns']).items():
            source = member(archive, name)
            if len(source) != row['bytes'] or digest(source) != row['sha256'] or b'__IdvSpt_02_' not in source[:32]:
                raise ValueError('Prokhorovka SpeedTree resource pin differs: ' + name)
        bushes, chunks = export_bushes(archive, config['bushes'])
    after = package.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Prokhorovka map package changed during export')
    crowns = export_crowns(catalog_path, physics_path, config['crowns'])
    document = {
        'schema': SCHEMA, 'map': ASSET, 'classification': CLASSIFICATION,
        'calibration_schema': CALIBRATION_SCHEMA, 'calibration_sha256': digest(raw),
        'map_package_pin': PACKAGE_PIN, 'chunk_pins': chunks, 'instances': bushes,
        'selected_resource_pins': {name: {'bytes': row['bytes'], 'sha256': row['sha256']}
                                   for name, row in config['bushes'].items()},
        'geometry_contract': 'unit u: world=center_world+sum(u[i]*basis_world_rows[i]); dot(u,u)<=1',
        'aabb_contract': 'center_world +/- aabb_half_extents_world contains the calibrated ellipsoid',
        'effect_contract': 'project v3: stacked shrubs and authoritative fallen tree crowns',
        'fire_near_distance_m': config['fire_near_distance_m'], 'fire_near_multiplier': config['fire_near_multiplier'],
        'fallen_tree_catalog_sha256': CATALOG_SHA256, 'fallen_trees': crowns,
    }
    result = (json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
              + '\n').encode('ascii')
    if len(result) > MAX_OUTPUT:
        raise ValueError('Prokhorovka foliage exceeds gateway byte bound')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('original', 'catalog', 'physics', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    evidence = no_links(ROOT / 'local/evidence').resolve(strict=True)
    out = no_links(args.out).resolve()
    if not out.is_relative_to(evidence) or out.suffix != '.json' or not out.parent.is_dir():
        raise ValueError('output must be a new JSON file under local/evidence')
    raw = build(args.original, args.catalog, args.physics)
    sha256 = digest(raw)
    if sha256 != PROHOROVKA_FOLIAGE_SHA256:
        raise ValueError('Prokhorovka foliage export differs from the accepted source and calibration')
    with out.open('xb') as stream:
        stream.write(raw)
    print(json.dumps({'output': str(out), 'sha256': sha256, 'bytes': len(raw),
                      'calibration_sha256': json_unique(raw)['calibration_sha256'],
                      'shrubs': sum(BUSH_COUNTS.values()), 'crowns': sum(TREE_COUNTS.values())}))


if __name__ == '__main__':
    main()
