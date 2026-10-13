"""Export a source-pinned P05B handling pool into fresh private local storage.

Pool1/MS-1 and pool2/IS-7 inputs retain their original bytes. Pool3 profiles
carry explicit test_lab control policy; no historical solver parity is claimed.
No client code executes, no client is modified and no worker is launched.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import math
from pathlib import Path

import vehicle_physics_profile as legacy
from client_audit import read_limited
from packed_xml import decode, walk

REPO = Path(__file__).resolve().parents[1]
REVISION = 'p05b-tracked-handling-v1'
POLICY = 'p05b-track-yaw-v1'
PROFILE_SHA256 = {
    'ms1': '48f8ac675afafbe8605bd97bd92dc2c37f26673b65a548d4f0402b815f7ee9a1',
    'is7': '2b72923c904678b5471ca4c8e01125f787d0baeb8cf2153c322a126fa1b6cfd7',
}
MS1_CONFIG = 'local/server/map-drive/05_prohorovka-v1.json'
MS1_CONFIG_SHA256 = 'eb7e9f3042ce00b8c5f1b84f43c4c3a77530b35e05bdf63c4b6225e1256caf7c'
MS1_SOURCE = 'res/scripts/item_defs/vehicles/ussr/ms-1.xml'
MS1_SOURCE_SHA256 = 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535'
PHYSICS_SOURCE = 'res/scripts/common/physics_shared.pyc'
PHYSICS_SOURCE_SHA256 = '487e2453c8e4540a9921353ebe651e833fd4145a1cc0623d70927cbb57863a77'
TRACTION_FIELDS = {'longitudinal_friction', 'lateral_friction', 'stationary_steering_ratio'}
HANDLING_FIELDS = {'version', 'policy', 'max_yaw_rate_rad_s'}
MAP_BINDINGS = {'01_karelia': 1, '05_prohorovka': 4}
require, canonical, sha = legacy.require, legacy.canonical, legacy.sha


def fields(value, names, reason):
    require(isinstance(value, dict) and set(value) == set(names), reason)


def verified_json(path, expected, maximum=16384):
    raw = read_limited(legacy.no_links(path), maximum)
    require(sha(raw) == expected, 'source hash mismatch: ' + str(path))
    return legacy.read_json(path, maximum)


def context(project_root):
    root = legacy.no_links(project_root).resolve(strict=True)
    settings = legacy.read_json(root / 'config/project.local.json', 65536)
    local = legacy.no_links(settings['paths']['local_artifacts_root']).resolve(strict=True)
    original = legacy.no_links(settings['paths']['original_client_root']).resolve(strict=True)
    require(not original.is_relative_to(local), 'original must be outside local')
    return root, local, original


def baseline_profiles(project_root):
    root, _, _ = context(project_root)
    ms1 = verified_json(root / MS1_CONFIG, MS1_CONFIG_SHA256)
    is7 = verified_json(REPO / 'server/gateway/src/drive/worker/is7-physics-profile.json', legacy.PROFILE_SHA256)
    legacy.validate_profile(is7)
    fields(ms1, legacy.CONFIG_FIELDS, 'legacy MS1 baseline schema')
    require(ms1['version'] == 1 and ms1['profile'] == 'test_lab', 'legacy MS1 baseline version')
    return ms1, is7


def build_profile(project_root, kind):
    require(kind in PROFILE_SHA256, 'unsupported vehicle')
    _, _, original = context(project_root)
    ms1, is7 = baseline_profiles(project_root)
    if kind == 'ms1':
        physics = {key: copy.deepcopy(ms1[key]) for key in legacy.PHYSICS_FIELDS if key in ms1}
        sources = {key: value for key, value in is7['sources'].items()
                   if key.startswith('res/scripts/') and not key.endswith('/is-7.xml')}
        sources.update({MS1_SOURCE: MS1_SOURCE_SHA256, 'accepted/ms1-map-config-v1': MS1_CONFIG_SHA256})
        source, chassis = MS1_SOURCE, 'T-18'
    else:
        physics, sources = copy.deepcopy(is7['physics']), dict(is7['sources'])
        sources['accepted/is7-physics-profile-v1'] = legacy.PROFILE_SHA256
        source, chassis = 'res/scripts/item_defs/vehicles/ussr/is-7.xml', 'IS-7'
    sources[PHYSICS_SOURCE] = PHYSICS_SOURCE_SHA256
    for relative, expected in sources.items():
        # Geometry/package provenance remains bound to the previously admitted
        # physical profile. Original scripts/descriptors are freshly rehashed.
        if relative.startswith('res/scripts/'):
            legacy.verified_file(original, relative, expected)
    descriptor = dict(walk(decode(legacy.verified_file(original, source, sources[source]))))
    rate = float(descriptor[f'/chassis[1]/{chassis}[1]/rotationSpeed[1]'])
    require(rate == {'ms1': 34, 'is7': 28}[kind], 'mounted chassis rotation changed')
    physics.update(longitudinal_friction=1.2, lateral_friction=1.0, stationary_steering_ratio=.2)
    result = {'version': 2, 'profile': 'test_lab', 'vehicle': kind, 'revision': REVISION,
              'sources': sources, 'physics': physics,
              'handling': {'version': 1, 'policy': POLICY, 'max_yaw_rate_rad_s': math.radians(rate)}}
    validate_profile(result, kind)
    return result


def validate_profile(profile, kind):
    require(kind in PROFILE_SHA256 and sha(canonical(profile)) == PROFILE_SHA256[kind], 'unadmitted handling profile')


def same_numeric(actual, expected):
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            same_numeric(a, b) for a, b in zip(actual, expected))
    return type(actual) in (int, float) and type(expected) in (int, float) and math.isfinite(actual) and actual == expected


def project_config(config, source_physics, source_version, profile, kind):
    validate_profile(profile, kind)
    require(type(source_version) is int and source_version in (1, 2), 'legacy source version required')
    names = set(legacy.CONFIG_FIELDS) | (TRACTION_FIELDS if source_version == 2 else set())
    fields(config, names, 'source config schema')
    require(type(config['version']) is int and config['version'] == source_version
            and config['profile'] == 'test_lab' and config['map'] in MAP_BINDINGS, 'source config identity')
    for key in set(legacy.PHYSICS_FIELDS) - (TRACTION_FIELDS if source_version == 1 else set()):
        require(same_numeric(config[key], source_physics[key]), 'source physics mismatch: ' + key)
    result = copy.deepcopy(config)
    result.update(copy.deepcopy(profile['physics']))
    result.update(version=3, handling=copy.deepcopy(profile['handling']))
    return result


def verify_projection(config, profile, kind):
    validate_profile(profile, kind)
    fields(config, set(legacy.CONFIG_FIELDS) | TRACTION_FIELDS | {'handling'}, 'handling config schema')
    require(type(config['version']) is int and config['version'] == 3 and config['profile'] == 'test_lab'
            and config['map'] in MAP_BINDINGS, 'handling config identity')
    for key in legacy.PHYSICS_FIELDS:
        require(same_numeric(config[key], profile['physics'][key]), 'handling physics mismatch: ' + key)
    fields(config['handling'], HANDLING_FIELDS, 'handling policy schema')
    require(type(config['handling']['version']) is int and config['handling']['version'] == 1
            and config['handling']['policy'] == POLICY
            and same_numeric(config['handling']['max_yaw_rate_rad_s'], profile['handling']['max_yaw_rate_rad_s']),
            'handling policy mismatch')


def worker_reference(local, executable, manifest):
    executable, manifest = legacy.owned(local, executable), legacy.owned(local, manifest)
    runtime = executable.parent
    require(executable.suffix == '.exe' and executable.is_relative_to(local / 'build'), 'fresh local/build worker required')
    require(not manifest.is_relative_to(runtime), 'manifest must be outside worker runtime')
    value = legacy.read_json(manifest, 131072)
    fields(value, {'version', 'files'}, 'worker manifest schema')
    rows = value['files']
    require(type(value['version']) is int and value['version'] == 1 and isinstance(rows, list)
            and 0 < len(rows) <= 256, 'worker manifest version/count')
    seen, total = set(), 0
    for row in rows:
        fields(row, {'relative_path', 'bytes', 'sha256'}, 'worker asset schema')
        relative, size, expected = row['relative_path'], row['bytes'], row['sha256']
        require(isinstance(relative, str) and relative and '\\' not in relative and ':' not in relative
                and all(part not in ('', '.', '..') for part in relative.split('/')), 'worker asset relative path')
        require(type(size) is int and size >= 0 and isinstance(expected, str)
                and len(expected) == 64 and all(c in '0123456789abcdef' for c in expected), 'worker asset size/hash')
        path = legacy.owned(runtime, runtime / relative)
        total += size
        require(path not in seen and total <= 256 * 1024 * 1024 and path.stat().st_size == size, 'worker asset bounds')
        with path.open('rb') as stream:
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == expected, 'worker asset hash mismatch')
        seen.add(path)
    actual, directories, pending = set(), 0, [runtime]
    while pending:
        directory = pending.pop()
        directories += 1
        require(directories <= 256, 'worker directory bound')
        for path in directory.iterdir():
            path = legacy.no_links(path).resolve(strict=True)
            if path.is_dir():
                pending.append(path)
            else:
                require(path.is_file() and len(actual) < 256, 'worker file bound')
                actual.add(path)
    require(executable in seen and actual == seen, 'worker file set mismatch')
    return {'executable': str(executable), 'artifact_manifest': str(manifest),
            'artifact_manifest_sha256': sha(read_limited(manifest, 131072))}


def export(project_root, base_pool, kind, executable, manifest, out):
    root, local, _ = context(project_root)
    out, base_pool = legacy.owned(local, out), legacy.owned(local, base_pool)
    require(not out.exists() and out.parent.is_dir(), 'fresh output directory required')
    ms1, is7 = baseline_profiles(root)
    pool = legacy.read_json(base_pool)
    source_version = pool.get('version')
    require(type(source_version) is int and source_version in (1, 2), 'source pool must be legacy1/2')
    names = {'version', 'profile', 'worker', 'maps'} | ({'vehicle_profile'} if source_version == 2 else set())
    fields(pool, names, 'source pool schema')
    require(pool['profile'] == 'test_lab', 'source pool profile')
    fields(pool['worker'], {'executable', 'artifact_manifest', 'artifact_manifest_sha256'}, 'source worker reference schema')
    source_physics = ms1 if source_version == 1 else is7['physics']
    if source_version == 2:
        ref = pool['vehicle_profile']
        fields(ref, {'path', 'sha256'}, 'source profile reference schema')
        require(ref['sha256'] == legacy.PROFILE_SHA256, 'source profile reference mismatch')
        source = verified_json(legacy.owned(local, ref['path']), legacy.PROFILE_SHA256)
        legacy.validate_profile(source)
    profile = build_profile(root, kind)
    worker = worker_reference(local, executable, manifest)
    rows = pool['maps']
    require(isinstance(rows, list) and len(rows) == 2, 'two source maps required')
    projected, seen, inputs = [], set(), [{'path': str(base_pool), 'sha256': sha(read_limited(base_pool, 16384))}]
    for row in rows:
        fields(row, {'asset', 'arena_type_id', 'config', 'config_sha256'}, 'source map schema')
        asset = row['asset']
        require(asset in MAP_BINDINGS and type(row['arena_type_id']) is int
                and row['arena_type_id'] == MAP_BINDINGS[asset] and asset not in seen, 'source map binding')
        seen.add(asset)
        path = legacy.owned(local, row['config'])
        config = verified_json(path, row['config_sha256'])
        require(config['map'] == asset, 'source config/map mismatch')
        for field in ('terrain', 'obstacles'):
            ref = config[field]
            fields(ref, {'path', 'sha256'}, 'source geometry reference schema')
            geom = legacy.owned(local, ref['path'])
            require(sha(read_limited(geom, 16 * 1024 * 1024)) == ref['sha256'], 'source geometry manifest changed')
        new_config = project_config(config, source_physics, source_version, profile, kind)
        verify_projection(new_config, profile, kind)
        projected.append((asset, new_config))
        inputs.append({'path': str(path), 'sha256': row['config_sha256']})
    result = {'version': 3, 'profile': 'test_lab', 'worker': worker, 'maps': [],
              'vehicle_profile': {'path': str(out / (kind + '-handling-profile.json')), 'sha256': PROFILE_SHA256[kind]}}
    out.mkdir()
    (out / (kind + '-handling-profile.json')).write_bytes(canonical(profile))
    for asset, config in projected:
        path = out / (asset + '-' + kind + '-handling-config.json')
        raw = canonical(config)
        path.write_bytes(raw)
        result['maps'].append({'asset': asset, 'arena_type_id': MAP_BINDINGS[asset],
                               'config': str(path), 'config_sha256': sha(raw)})
    raw = canonical(result)
    pool_path = out / ('pool-' + kind + '-handling.json')
    pool_path.write_bytes(raw)
    receipt = {'status': 'PASS_PINNED_HANDLING_EXPORT_NOT_RUNTIME', 'vehicle': kind,
               'pool_path': str(pool_path), 'pool_sha256': sha(raw), 'profile_sha256': PROFILE_SHA256[kind],
               'source_inputs': inputs, 'worker': worker, 'sources': profile['sources'],
               'policy': 'P05B project control; lateral1.0 longitudinal1.2; legacy stationary ratio retained but unused; source mounted yaw rate',
               'native_acceptance': 'NOT_RUN', 'historical_solver': 'UNKNOWN', 'original_modified': False}
    (out / 'receipt.json').write_bytes(canonical(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=REPO)
    parser.add_argument('--base-pool', type=Path, required=True)
    parser.add_argument('--vehicle', choices=tuple(PROFILE_SHA256), required=True)
    parser.add_argument('--worker-executable', type=Path, required=True)
    parser.add_argument('--worker-manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(canonical(export(args.project_root, args.base_pool, args.vehicle, args.worker_executable,
                           args.worker_manifest, args.out)).decode('ascii'), end='')


if __name__ == '__main__':
    main()
