"""Build the fixed 0.9.1 web fact catalog from verified research data, never execute client code."""
from __future__ import annotations
import argparse
import copy
import gettext
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
sys.path.insert(0, str(ROOT / 'tools'))
from packed_xml import decode

NATIONS = ['ussr', 'germany', 'usa', 'france', 'uk', 'china', 'japan']
CLASSES = ['lightTank', 'mediumTank', 'heavyTank', 'AT-SPG', 'SPG']


def convert(node):
    if not isinstance(node, dict) or 'children' not in node:
        return node
    result, repeated = {}, set()
    if node['value'] not in ('', None):
        result['$'] = node['value']
    for child in node['children']:
        key, value = child['name'], convert(child['data'])
        if key in result:
            if key not in repeated:
                result[key] = [result[key]]
                repeated.add(key)
            result[key].append(value)
        else:
            result[key] = value
    return result


def number(value):
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get('$')
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a catalog number')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('Non-finite number')
    return int(result) if result.is_integer() else result


def numbers(value):
    if value is None:
        return []
    return [number(x) for x in (value.split() if isinstance(value, str) else value)]


def merged(base, override):
    result = copy.deepcopy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if key != '$':
            result[key] = merged(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else copy.deepcopy(value)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    evidence = (ROOT / args.evidence).resolve()
    if not evidence.is_relative_to((ROOT / 'local/web').resolve()):
        raise ValueError('Evidence must stay in local/web')
    evidence.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / 'config/project.local.json').read_text(encoding='utf-8-sig'))
    research = Path(config['paths']['research_client_root']).resolve(strict=True)
    if research == Path(config['paths']['original_client_root']).resolve():
        raise ValueError('Research must be separate from original')
    if config['target']['exact_build'] != 'v.0.9.1 #717':
        raise ValueError('Wrong configured build')
    baseline_path = ROOT / 'local/evidence/20261002-p00-p01/baseline/research-manifest.json'
    baseline = {x['path'].lower(): x for x in json.loads(baseline_path.read_text(encoding='utf-8-sig'))['files']}
    sources, translations, warnings = {}, {}, []

    def read(relative):
        path = (research / relative).resolve(strict=True)
        if not path.is_relative_to(research) or path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Unbounded or invalid source')
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        expected = baseline.get(relative.lower())
        if not expected or digest != expected['sha256'] or len(data) != expected['bytes']:
            raise ValueError(f'Baseline mismatch: {relative}')
        sources[relative] = {'path': relative, 'sha256': digest, 'bytes': len(data), 'baselineMatch': True}
        return data

    def xml(relative):
        return convert(decode(read(relative)))

    def localize(reference, fallback=None):
        if not isinstance(reference, str):
            raise ValueError(f'Expected localization reference: {reference!r}')
        if not reference.startswith('#'):
            warnings.append({'kind': 'literalDisplayName', 'reference': reference, 'display': fallback or reference})
            return fallback or reference
        domain, key = reference[1:].split(':', 1)
        if domain not in translations:
            translations[domain] = gettext.GNUTranslations(io.BytesIO(read(f'res/text/lc_messages/{domain}.mo')))
        value = translations[domain].gettext(key).strip()
        # A valid translated proper name may equal its key (e.g. Hummel).
        if key not in translations[domain]._catalog or not value or value == '?empty?':
            if fallback is not None:
                warnings.append({'kind': 'missingModuleDisplayName', 'reference': reference, 'display': fallback})
                return fallback
            raise ValueError(f'Missing display name: {reference}')
        return value

    def armor(node):
        keys = node.get('primaryArmor', '').split()
        return [number(node.get('armor', {}).get(k)) for k in keys] if keys else []

    vehicles = []
    for nation in NATIONS:
        prefix = f'res/scripts/item_defs/vehicles/{nation}'
        listing = xml(f'{prefix}/list.xml')
        components = {kind: xml(f'{prefix}/components/{kind}.xml') for kind in ['guns', 'shells', 'engines', 'radios']}

        def resolve(kind, key, data):
            shared = data == 'shared' or (isinstance(data, dict) and data.get('$') == 'shared')
            if shared:
                return merged(components[kind]['shared'][key], data)
            if not isinstance(data, dict):
                raise ValueError(f'Unknown module reference {nation}/{kind}/{key}: {data!r}')
            return data

        for key, info in listing.items():
            source = f'{prefix}/{key.lower()}.xml'
            v = xml(source)
            tags = info['tags'].split()
            vehicle_class = [tag for tag in CLASSES if tag in tags]
            if len(vehicle_class) != 1:
                raise ValueError(f'Unknown class {nation}/{key}')
            turrets = []
            for turret_key, turret in v.get('turrets0', {}).items():
                guns = []
                for gun_key, override in turret.get('guns', {}).items():
                    gun = resolve('guns', gun_key, override)
                    shots = []
                    for shot_key, shot in gun.get('shots', {}).items():
                        shell = components['shells'][shot_key]
                        shots.append({'key': shot_key, 'name': localize(shell['userString'], shot_key.lstrip('_')), 'kind': shell['kind'],
                            'premium': isinstance(shell.get('price'), dict) and 'gold' in shell['price'],
                            'caliber': number(shell['caliber']), 'damage': number(shell['damage']['armor']),
                            'penetration': numbers(shot['piercingPower']), 'speed': number(shot['speed'])})
                    guns.append({'key': gun_key, 'name': localize(gun['userString'], gun_key.lstrip('_')),
                        'level': number(gun['level']), 'reloadTime': number(gun.get('reloadTime')),
                        'aimingTime': number(gun.get('aimingTime')), 'dispersion': number(gun.get('shotDispersionRadius')),
                        'ammoCapacity': number(gun.get('maxAmmo')), 'magazine': number(gun.get('clip', {}).get('count')),
                        'burst': number(gun.get('burst', {}).get('count')), 'shots': shots})
                turrets.append({'key': turret_key, 'name': localize(turret['userString'], f'Орудийная установка {len(turrets) + 1}'),
                    'level': number(turret.get('level')), 'armor': armor(turret),
                    'hitPoints': number(v['hull']['maxHealth']) + number(turret['maxHealth']),
                    'viewRange': number(turret.get('circularVisionRadius')), 'rotation': number(turret.get('rotationSpeed')),
                    'guns': guns})
            engines, radios = [], []
            for kind, target, field, output in [('engines', engines, 'power', 'power'), ('radios', radios, 'distance', 'range')]:
                for module_key, override in v.get(kind, {}).items():
                    module = resolve(kind, module_key, override)
                    target.append({'key': module_key, 'name': localize(module['userString'], module_key.lstrip('_')), output: number(module[field])})
            slug = nation + '-' + re.sub('[^a-z0-9]+', '-', key.lower()).strip('-')
            vehicles.append({'id': slug, 'key': key, 'nation': nation, 'name': localize(info['userString'], key if 'secret' in tags else None),
                'tier': number(info['level']), 'class': vehicle_class[0], 'archived': 'secret' in tags,
                'event': 'event_battles' in tags, 'special': 'special' in tags,
                'premium': isinstance(info.get('price'), dict) and 'gold' in info['price'],
                'speed': {k: number(val) for k, val in v['speedLimits'].items()},
                'crew': sum(len(role) if isinstance(role, list) else 1 for role in v['crew'].values()),
                'hullArmor': armor(v['hull']), 'turrets': turrets,
                'engines': engines, 'radios': radios, 'source': source})

    map_names = json.loads((WEB / 'data/map-names.v1.json').read_text(encoding='utf-8'))
    arena_list = xml('res/scripts/arena_defs/_list_.xml')['map']
    listed = {row['name']: row['id'] for row in arena_list}
    defaults = xml('res/scripts/arena_defs/_default_.xml')
    maps = []
    for path in sorted((research / 'res/scripts/arena_defs').glob('*.xml')):
        if path.name.startswith('_'):
            continue
        source = path.relative_to(research).as_posix()
        arena = xml(source)
        authored = map_names['maps'][path.stem]
        bottom = numbers(arena['boundingBox']['bottomLeft'])
        top = numbers(arena['boundingBox']['upperRight'])
        modes = []
        for mode, properties in arena['gameplayTypes'].items():
            properties = properties if isinstance(properties, dict) else {}
            mode_defaults = defaults['gameplayTypes'].get(mode, {})
            mode_defaults = mode_defaults if isinstance(mode_defaults, dict) else {}
            duration = properties.get('roundLength', mode_defaults.get('roundLength', arena.get('roundLength', defaults['roundLength'])))
            bases = []
            for team, positions in properties.get('teamBasePositions', {}).items():
                if not isinstance(positions, dict):
                    continue
                for position, point in positions.items():
                    if position.startswith('position'):
                        vector = numbers(point)
                        if len(vector) != 2:
                            raise ValueError('Expected two base coordinates')
                        bases.append({'team': team, 'position': vector})
            control = numbers(properties.get('controlPoint'))
            modes.append({'id': mode, 'durationSeconds': number(duration), 'bases': bases, 'controlPoint': control})
        maps.append({'id': path.stem, **authored, 'originalName': localize(arena['name']),
            'size': [top[0] - bottom[0], top[1] - bottom[1]], 'bounds': {'min': bottom, 'max': top}, 'camouflage': arena['vehicleCamouflageKind'],
            'modes': modes, 'registered': path.stem in listed,
            'special': authored['terrain'] in ['training', 'event'], 'source': source})
    if len(set(v['id'] for v in vehicles)) != len(vehicles) or len(set(m['name'] for m in maps)) != len(maps):
        raise ValueError('Duplicate catalog identity')
    if set(map_names['maps']) != {m['id'] for m in maps}:
        raise ValueError('Map display mapping does not match source coverage')
    for relative, expected in sources.items():
        if hashlib.sha256((research / relative).read_bytes()).hexdigest() != expected['sha256']:
            raise ValueError(f'Source changed during extraction: {relative}')
    catalog = {'schemaVersion': 'static-catalog.v1', 'build': '0.9.1 #717', 'namingVersion': map_names['version'],
        'vehicleCount': len(vehicles), 'mapCount': len(maps), 'vehicles': vehicles, 'maps': maps}
    output = WEB / 'data/catalog.v1.json'
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    audit = {'status': 'PASS', 'build': config['target']['exact_build'], 'baseline': str(baseline_path.relative_to(ROOT)),
        'vehicleCount': len(vehicles), 'regularVehicles': sum(not v['archived'] for v in vehicles),
        'mapCount': len(maps), 'unlistedMaps': [m['id'] for m in maps if not m['registered']],
        'sources': list(sources.values()), 'sourceCount': len(sources),
        'catalogSha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'warnings': warnings, 'scope': 'Read-only descriptor facts; source hashes rechecked after extraction; client NOT_RUN'}
    (evidence / 'sources.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in audit.items() if k not in ['sources', 'warnings']} | {'warningCount': len(warnings)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
