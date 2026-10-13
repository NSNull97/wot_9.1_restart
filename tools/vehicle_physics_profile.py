"""Source-pinned #717 IS-7 test_lab physics profile and homogeneous pool v2.

No client code is executed, no client is modified and no worker is launched.
The six-support/engine/brake mapping is explicit test_lab policy, not a claim
that Jolt reproduces the original engine, BSP collision or traction model.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import zipfile

from client_audit import read_limited
from geometry_spike import collision_mesh
from packed_xml import decode, walk

PROFILE_REVISION = 'is7-717-s70-no-optional-six-support-traction-v2'
PROFILE_SHA256 = '2fefea06de45fd172894ea7330f59d8efa9f9914a4f88192bb7b5f6ce8d47a90'
SOURCE_PINS = {
    'res/scripts/item_defs/vehicles/ussr/is-7.xml': '8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d',
    'res/scripts/item_defs/vehicles/ussr/components/engines.xml': '196e52561bd04d2d4e5838442f62704456f4b901627248e04b2c9bd37d32f60d',
    'res/scripts/item_defs/vehicles/ussr/components/fueltanks.xml': '1f182b76fceeabf2ff1d828cc5b2aea37b94585f78488bd2dd7c195f8862b013',
    'res/scripts/item_defs/vehicles/ussr/components/radios.xml': '099292b8b5f5e250b2cd506419d18620f4f2504950776b54983bc303b2ca201a',
    'res/scripts/item_defs/vehicles/ussr/components/guns.xml': '889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b',
    'res/scripts/common/items/vehicles.pyc': '805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6',
}
PACKAGE = 'res/packages/vehicles_russian.pkg'
PACKAGE_BYTES = 1182066680
PACKAGE_SHA256 = 'c2e16aef6fe7a7e44e476e2cb96e009b9f4eb7edab55fda2861601ba783415aa'
HULL = 'vehicles/russian/R45_IS-7/collision/Hull.primitives'
HULL_SHA256 = 'da571210838ac9899451c7beaa49f3157c497cd52c1c690aefb8f1ba0a2c38d7'
PHYSICS_FIELDS = (
    'body_half_extents', 'body_center_offset', 'wheel_points', 'mass_kg',
    'max_forward_mps', 'max_reverse_mps', 'engine_max_torque_nm', 'wheel_radius',
    'suspension_min', 'suspension_max', 'track_max_brake_torque',
    'longitudinal_friction', 'lateral_friction', 'stationary_steering_ratio',
)
CONFIG_FIELDS = (set(PHYSICS_FIELDS) - {'longitudinal_friction', 'lateral_friction', 'stationary_steering_ratio'}) | {
    'version', 'profile', 'map', 'terrain', 'obstacles', 'spawn_origin', 'spawn_yaw', 'bounds_xz',
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True,
                      separators=(',', ':')).encode('ascii') + b'\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def no_links(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        require(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()),
                'symlink/junction forbidden')
    return path


def owned(local, path):
    require(Path(path).is_absolute(), 'absolute owned path required')
    path = no_links(path).resolve()
    require(path != local and path.is_relative_to(local), 'path outside owned local root')
    return path


def read_json(path, maximum=16384):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    try:
        value = json.loads(read_limited(path, maximum), object_pairs_hook=pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except RecursionError as error:
        raise ValueError('JSON depth limit') from error
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        require(depth <= 16 and nodes <= 4096, 'JSON depth/node limit')
        if isinstance(item, dict):
            require(len(item) <= 128 and all(len(k) <= 4096 for k in item), 'JSON object limit')
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            require(len(item) <= 512, 'JSON array limit')
            pending.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            require(len(item) <= 4096, 'JSON string limit')
    return value


def verified_file(original, relative, expected):
    path = no_links(original / relative)
    raw = read_limited(path, 1024 * 1024)
    require(sha(raw) == expected, 'original source hash mismatch: ' + relative)
    return raw


def build_profile(original):
    original = no_links(original).resolve(strict=True)
    source = {name: verified_file(original, name, h) for name, h in SOURCE_PINS.items()}
    descriptor = dict(walk(decode(source['res/scripts/item_defs/vehicles/ussr/is-7.xml'])))
    shared = {}
    for file in ('engines', 'fueltanks', 'radios', 'guns'):
        shared[file] = dict(walk(decode(source[f'res/scripts/item_defs/vehicles/ussr/components/{file}.xml'])))
    chassis = '/chassis[1]/IS-7[1]'
    turret = '/turrets0[1]/IS-7[1]'
    def number(value):
        require(not isinstance(value, bool), 'numeric source field required')
        n = float(value)
        require(math.isfinite(n), 'finite source field required')
        return n
    def vec(value, count):
        value = value.split() if isinstance(value, str) else value
        require(isinstance(value, list) and len(value) == count, 'source vector width')
        return [number(v) for v in value]
    require(descriptor[chassis + '/rotationIsAroundCenter[1]'] is False, 'IS7 rotation mode changed')
    hull_position = vec(descriptor[chassis + '/hullPosition[1]'], 3)
    carrying = vec(descriptor[chassis + '/topRightCarryingPoint[1]'], 2)
    radius = vec(descriptor[chassis + '/wheels[1]/group[1]/radius[1]'], 1)[0]
    require(radius == vec(descriptor[chassis + '/wheels[1]/group[2]/radius[1]'], 1)[0], 'asymmetric radius')
    module_names = {'engines': 'M-50T', 'fueltanks': 'Large', 'radios': '_10RK-26', 'guns': '_130mm_S-70'}
    weights = [number(descriptor[k + '/weight[1]']) for k in ['/hull[1]', chassis, turret]]
    weights += [number(shared[k]['/shared[1]/' + name + '[1]/weight[1]']) for k, name in module_names.items()]
    power = number(shared['engines']['/shared[1]/M-50T[1]/power[1]']) * 735.5
    package = no_links(original / PACKAGE)
    require(package.stat().st_size == PACKAGE_BYTES, 'original package size mismatch')
    with package.open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == PACKAGE_SHA256, 'original package hash mismatch')
    with zipfile.ZipFile(package) as archive:
        info = archive.getinfo(HULL)
        require(info.file_size == 21184 and 0 < info.compress_size <= info.file_size, 'hull member size')
        with archive.open(info) as stream:
            raw = stream.read(21185)
        require(len(raw) == 21184 and sha(raw) == HULL_SHA256, 'hull primitive hash mismatch')
    bounds = collision_mesh(raw)['bounds']
    low, high = bounds['min'], bounds['max']
    physics = {
        'body_half_extents': [(high[i] - low[i]) / 2 for i in range(3)],
        'body_center_offset': [(high[i] + low[i]) / 2 + hull_position[i] for i in range(3)],
        'wheel_points': [[x, radius + .28, z] for x in [-carrying[0], carrying[0]] for z in [-carrying[1], 0, carrying[1]]],
        'mass_kg': sum(weights),
        'max_forward_mps': number(descriptor['/speedLimits[1]/forward[1]']) * .27778,
        'max_reverse_mps': number(descriptor['/speedLimits[1]/backward[1]']) * .27778,
        'engine_max_torque_nm': power / (2 * math.pi * 2500 / 60),
        'wheel_radius': radius, 'suspension_min': .1, 'suspension_max': .35,
        'track_max_brake_torque': number(descriptor[chassis + '/brakeForce[1]']) * 9.81 * radius / 2,
        # Bounded real-worker controllability policy; these are not source values.
        'longitudinal_friction': 1.2, 'lateral_friction': .4, 'stationary_steering_ratio': .2,
    }
    source_pins = dict(SOURCE_PINS)
    source_pins[PACKAGE] = PACKAGE_SHA256
    source_pins[PACKAGE + '!' + HULL] = HULL_SHA256
    profile = {'version': 1, 'profile': 'test_lab', 'vehicle': 'is7', 'revision': PROFILE_REVISION,
               'sources': source_pins, 'physics': physics}
    return profile


def validate_profile(profile):
    require(sha(canonical(profile)) == PROFILE_SHA256, 'unadmitted physics profile')


def project_config(config, profile):
    validate_profile(profile)
    require(set(config) == CONFIG_FIELDS and config['version'] == 1 and config['profile'] == 'test_lab', 'base config schema')
    require(config['map'] in ('01_karelia', '05_prohorovka'), 'unsupported map')
    result = copy.deepcopy(config)
    result.update(copy.deepcopy(profile['physics']))
    result['version'] = 2
    return result


def export(project_root, base_pool, out):
    root = no_links(project_root).resolve(strict=True)
    settings = read_json(root / 'config/project.local.json', 65536)
    local = no_links(settings['paths']['local_artifacts_root']).resolve(strict=True)
    original = no_links(settings['paths']['original_client_root']).resolve(strict=True)
    require(not original.is_relative_to(local), 'original must be outside local')
    out = owned(local, out)
    require(not out.exists() and out.parent.is_dir(), 'fresh output directory required')
    base_pool = owned(local, base_pool)
    pool = read_json(base_pool)
    require(set(pool) == {'version', 'profile', 'worker', 'maps'} and pool['version'] == 1
            and pool['profile'] == 'test_lab', 'base pool must be legacy v1')
    require(isinstance(pool['maps'], list) and len(pool['maps']) == 2, 'two maps required')
    profile = build_profile(original)
    validate_profile(profile)
    projected, inputs = [], [{'path': str(base_pool), 'sha256': sha(read_limited(base_pool, 16384))}]
    seen = set()
    for row in pool['maps']:
        require(set(row) == {'asset', 'arena_type_id', 'config', 'config_sha256'}, 'map row schema')
        require((row['asset'], row['arena_type_id']) in [('01_karelia', 1), ('05_prohorovka', 4)], 'map binding')
        require(row['asset'] not in seen, 'duplicate map')
        seen.add(row['asset'])
        path = owned(local, row['config'])
        raw = read_limited(path, 16384)
        require(sha(raw) == row['config_sha256'], 'base configuration hash mismatch')
        cfg = project_config(read_json(path), profile)
        require(cfg['map'] == row['asset'], 'config/map mismatch')
        projected.append((row, cfg))
        inputs.append({'path': str(path), 'sha256': row['config_sha256']})
    out.mkdir()
    profile_path = out / 'is7-physics-profile.json'
    profile_path.write_bytes(canonical(profile))
    result = copy.deepcopy(pool)
    result['version'] = 2
    result['vehicle_profile'] = {'path': str(profile_path), 'sha256': PROFILE_SHA256}
    for row, (_, cfg) in zip(result['maps'], projected):
        path = out / (row['asset'] + '-is7-config.json')
        raw = canonical(cfg)
        path.write_bytes(raw)
        row['config'], row['config_sha256'] = str(path), sha(raw)
    pool_path = out / 'pool-is7.json'
    pool_path.write_bytes(canonical(result))
    receipt = {'status': 'PASS_SOURCE_IMPORT_NOT_RUNTIME', 'profile_sha256': PROFILE_SHA256,
               'pool_sha256': sha(canonical(result)), 'source_inputs': inputs,
               'original_root': str(original), 'sources': profile['sources'],
               'policy': 'source hull primitive box; six supports; power at2500RPM; equal brake force split; config2 approximate traction1.2/.4 and powered stationary ratio.2',
               'native_bbox': 'NOT_RUN', 'historical_movement_law': 'UNKNOWN',
               'worker_runs': 'NOT_RUN', 'original_modified': False}
    (out / 'receipt.json').write_bytes(canonical(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--base-pool', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.project_root, args.base_pool, args.out), indent=2))


if __name__ == '__main__':
    main()
