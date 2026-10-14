"""Source-bound movement-only whole fragiles alongside accepted P06Q objects.

This first P06R slice does not implement compound modules or replacement rubble.
Eligibility follows original material/geometry contracts, never filenames or
instance IDs. Native indices require a complete fresh two-pass passive export.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import tree_contact_catalog as tc

dc = tc.dc
MAP = tc.MAP
MAX_OBJECTS = 2048
MAX_CHUNKS = 128
MAX_FRAGILES_PER_CHUNK = 125
MAX_TREES_PER_CHUNK = 62
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_WORKER_BYTES = 512 * 1024
KINDS = ('fragile', 'tree', 'movement_fragile')
RAM_POLICY = 'test_lab-fence-energy-v1'
FENCE_ENERGY_J = 8000
WHOLE_CONTACT_RAM_POLICY = 'test_lab-whole-object-energy-v1'
# Explicit project policy only; original reference HP does not establish this
# energy cost or the closed historical server's resistance/ram damage law.
WHOLE_CONTACT_ENERGY_J = 8000
MOVING_FENCE_RAM_POLICY = 'test_lab-fence-total-energy-v1'
ANGULAR_FENCE_RAM_POLICY = 'test_lab-fence-linear-angular-energy-v1'
require = dc.require
sha = dc.sha


def movement_eligibility(row, contract):
    """Require one complete removable material, without a replacement visual."""
    reasons = []
    target = row['material_name']
    material_rows = contract['materials']
    materials = {material['name']: material for material in material_rows}
    if len(materials) != len(material_rows):
        reasons.append('duplicate_visual_material')
    if set(materials) != {target}:
        reasons.append('replacement_or_additional_visual_requires_separate_contract')
    intact = materials.get(target)
    if not intact or intact['material_kind'] != 73 or intact['collision_flags'] != 128:
        reasons.append('not_original_movement_only_fragile_material')
    if set(contract['bsp_material_triangle_counts']) != {target}:
        reasons.append('mixed_or_unmatched_bsp_material_requires_partial_contract')
    if row['physics_triangle_count'] <= 0 or row['physics_triangle_count'] != contract['bsp_triangles']:
        reasons.append('movement_span_not_complete_source_instance')
    if row['projectile_triangle_count'] != 0:
        reasons.append('projectile_mask128_must_remain_empty')
    if row['initial_state'] != 'undamaged':
        reasons.append('initial_state_not_undamaged')
    if type(row['reference_health']) is not int or not 1 <= row['reference_health'] <= 32767:
        reasons.append('reference_health_outside_fragile_bound')
    return reasons


def _validate_inventory(inventory):
    require(inventory.get('version') == 3 and inventory.get('map') == MAP and
            inventory.get('kind') == 'p06r_compound_destructible_catalog_inventory',
            'P06R inventory identity')
    rows = inventory['eligible']
    require(type(rows) is list and 0 < len(rows) <= MAX_OBJECTS, 'P06R object count bound')
    chunks = inventory['area_chunks']
    require(type(chunks) is list and 0 < len(chunks) <= MAX_CHUNKS and
            all(type(chunk) is int and 0 <= chunk <= 65535 for chunk in chunks) and
            chunks == sorted(set(chunks)), 'sorted unique bounded area_chunks required')
    spec = inventory['probe_spec']
    require(spec == {'version': 2, 'kind': 'p06q_tree_contact_catalog_spec', 'map': MAP,
                     'source_pins': inventory['source_pins'], 'chunk_ids': chunks},
            'probe and area chunk/source binding')
    ids = []
    fragiles, trees = Counter(), Counter()
    for row in rows:
        instance_id = dc.integer(row['instance_id'], 0, 9999, 'source instance ID')
        ids.append(instance_id)
        require(row['kind'] in KINDS and row['chunk_id'] in chunks, 'object kind/area membership')
        dc.resource(row['resource'])
        dc.matrix_bits(row['transform'])
        dc.digest(row['object_revision'])
        dc.integer(row['reference_health'], 1, 0xffffffff, 'reference health')
        dc.integer(row['physics_first_triangle'], 0, 2_000_000, 'physics first triangle')
        dc.integer(row['physics_triangle_count'], 1, 2_000_000, 'physics count')
        dc.integer(row['projectile_first_triangle'], 0, 2_000_000, 'projectile first triangle')
        dc.integer(row['projectile_triangle_count'], 0, 2_000_000, 'projectile count')
        if row['kind'] == 'tree':
            trees[row['chunk_id']] += 1
            require(row['projectile_triangle_count'] == 0, 'tree projectile span must stay empty')
        else:
            fragiles[row['chunk_id']] += 1
            if row['kind'] == 'movement_fragile':
                require(row['projectile_triangle_count'] == 0, 'movement fragile projectile span must stay empty')
            else:
                require(row['projectile_triangle_count'] > 0, 'legacy fragile projectile span required')
    require(ids == sorted(set(ids)), 'sorted unique source instance IDs required')
    require(max(fragiles.values(), default=0) <= MAX_FRAGILES_PER_CHUNK,
            'fragile cumulative property exceeds per-area budget')
    require(max(trees.values(), default=0) <= MAX_TREES_PER_CHUNK,
            'tree cumulative property exceeds per-area budget')


def build_inventory(sources=None):
    """Preserve accepted P06Q rows and add complete movement-only fragiles."""
    sources = tc.load_sources() if sources is None else sources
    base = tc.build_inventory(sources)
    meshes = dc.verify_sources(sources)
    legacy = dc.build_inventory(sources)
    rows, added = [], []
    accepted_ids = {row['instance_id'] for row in base['eligible']}
    for source_row in legacy['fragiles']:
        contract = legacy['material_contracts'][source_row['resource']]
        reasons = movement_eligibility(source_row, contract)
        row = copy.deepcopy(source_row)
        row.update(kind='movement_fragile', eligible=not reasons, exclusions=reasons)
        if not reasons:
            require(row['instance_id'] not in accepted_ids, 'movement admission overlaps accepted object')
            physics = meshes['physics']['instances'][row['instance_id']]
            projectile = meshes['projectile']['instances'][row['instance_id']]
            require(physics['resource'] == projectile['resource'] == row['resource'] and
                    physics['transform'] == projectile['transform'] == row['transform'],
                    'movement source instance identity')
            points = dc._points(sources, 'physics', physics)
            require(dc._points(sources, 'projectile', projectile) == b'',
                    'movement-only projectile geometry must remain empty')
            row['world_triangle_points_sha256'] = sha(points)
            identity = {
                'schema': 'destructible-object-source.v3', 'map': MAP,
                'kind': 'movement_fragile', 'destructibles_sha256': dc.DESTRUCTIBLES_SHA256,
                'physics_manifest_sha256': dc.map_profile(MAP).files()['physics'][1],
                'projectile_manifest_sha256': dc.map_profile(MAP).files()['projectile'][1],
                'material_contract': contract,
                'instance': {key: value for key, value in row.items()
                             if key not in ('eligible', 'exclusions', 'native_index')},
                'collision_flags': 128, 'material_kind': 73,
            }
            row['object_revision'] = sha(dc.canonical(identity))
            added.append(row)
        rows.append(row)
    require(added, 'no complete movement-only fragile source objects found')
    inventory = copy.deepcopy(base)
    eligible = sorted(inventory['eligible'] + added, key=lambda row: row['instance_id'])
    chunks = sorted({row['chunk_id'] for row in eligible})
    inventory.update(version=3, kind='p06r_compound_destructible_catalog_inventory',
                     eligible=eligible, movement_fragiles=rows, area_chunks=chunks,
                     movement_material_contracts=legacy['material_contracts'])
    inventory['probe_spec']['chunk_ids'] = chunks
    inventory['summary'].update(
        accepted_baseline_objects=len(base['eligible']), movement_eligible_instances=len(added),
        movement_eligible_resources=len({row['resource'] for row in added}),
        eligible_instances=len(eligible), probe_chunks=len(chunks),
        movement_exclusion_reasons=dict(Counter(reason for row in rows for reason in row['exclusions'])))
    inventory['limits'].extend([
        'P06R first slice admits movement-only whole fragiles with no replacement/additional visual material.',
        'Compound modules, mixed materials and replacement geometry remain excluded with source reasons.',
        'No filename/instance allowlist and no synthetic native indices are used.',
        'Domain v3 records all area_chunks; worker v4 projects movement_fragile as fragile.',
    ])
    _validate_inventory(inventory)
    return inventory


def probe_spec_bytes(inventory):
    _validate_inventory(inventory)
    return dc.canonical(inventory['probe_spec']) + b'\n'


def join_exports(inventory, exports, *, fence_response=False, whole_contact_response=False,
                 moving_fence_response=False, angular_fence_response=False):
    """Require complete stable native mappings; no partial admission fallback."""
    responses = (fence_response, whole_contact_response, moving_fence_response, angular_fence_response)
    require(all(type(value) is bool for value in responses),
            'response flags must be booleans')
    require(sum(responses) <= 1, 'response policies are mutually exclusive')
    _validate_inventory(inventory)
    require(type(exports) is list and 1 <= len(exports) <= 2, 'one or two native exports required')
    mappings, digests = [], []
    for raw, expected in exports:
        require(type(raw) is bytes and sha(raw) == dc.digest(expected), 'native export SHA256 before parse')
        mappings.append(tc.validate_native(raw, inventory))
        digests.append(expected)
    require(len(set(digests)) == len(digests) and all(row == mappings[0] for row in mappings),
            'native exports disagree or duplicate')
    objects, worker_objects, seen = [], [], set()
    for row in inventory['eligible']:
        identity = (row['resource'], dc.matrix_bits(row['transform']))
        matches = [index for index, candidate in mappings[0][row['chunk_id']].items() if candidate == identity]
        require(len(matches) == 1, 'missing or ambiguous native source instance match')
        native_index = matches[0]
        key = (row['chunk_id'], native_index)
        require(key not in seen, 'two source objects share native ID')
        seen.add(key)
        kind = row['kind']
        obj = {'object_id': row['instance_id'] + 1, 'instance_id': row['instance_id'], 'kind': kind,
               'chunk_id': row['chunk_id'], 'native_index': native_index, 'resource': row['resource'],
               'health': row['reference_health'], 'material_kind': 71 if kind == 'tree' else 73,
               'projectile_first_triangle': row['projectile_first_triangle'],
               'projectile_triangle_count': row['projectile_triangle_count'],
               'physics_first_triangle': row['physics_first_triangle'],
               'physics_triangle_count': row['physics_triangle_count'], 'object_revision': row['object_revision']}
        objects.append(obj)
        worker_objects.append({'object_id': obj['object_id'], 'instance_id': obj['instance_id'],
                               'kind': 'tree' if kind == 'tree' else 'fragile',
                               'first_triangle': obj['physics_first_triangle'],
                               'triangle_count': obj['physics_triangle_count'],
                               'object_revision': obj['object_revision']})
    files = dc.map_profile(MAP).files()
    worker = {'version': 4, 'profile': 'test_lab', 'map': MAP,
              'physics_manifest_sha256': files['physics'][1],
              'projectile_manifest_sha256': files['projectile'][1], 'contacts': True, 'objects': worker_objects}
    if fence_response:
        worker.update(version=5, ram_policy=RAM_POLICY)
        for projection, source in zip(worker_objects, objects):
            projection['ram_energy_j'] = FENCE_ENERGY_J if source['kind'] == 'movement_fragile' else 0
    elif whole_contact_response:
        worker.update(version=6, ram_policy=WHOLE_CONTACT_RAM_POLICY)
        for projection in worker_objects:
            projection['ram_energy_j'] = WHOLE_CONTACT_ENERGY_J
    elif moving_fence_response:
        worker.update(version=7, ram_policy=MOVING_FENCE_RAM_POLICY)
        for projection, source in zip(worker_objects, objects):
            response = 'total_linear' if source['kind'] == 'movement_fragile' else 'normal_linear'
            source['ram_response'] = response
            projection.update(ram_energy_j=WHOLE_CONTACT_ENERGY_J, ram_response=response)
    elif angular_fence_response:
        worker.update(version=8, ram_policy=ANGULAR_FENCE_RAM_POLICY)
        for projection, source in zip(worker_objects, objects):
            response = 'total_linear_angular_fallback' if source['kind'] == 'movement_fragile' else 'normal_linear'
            source['ram_response'] = response
            projection.update(ram_energy_j=WHOLE_CONTACT_ENERGY_J, ram_response=response)
    worker_raw = dc.canonical(worker) + b'\n'
    dc.json_value(worker_raw, MAX_WORKER_BYTES, 64000, 12)
    manifest = {'version': 3, 'profile': 'test_lab', 'map': MAP,
                'destructibles_sha256': dc.DESTRUCTIBLES_SHA256,
                'physics_manifest_sha256': files['physics'][1],
                'projectile_manifest_sha256': files['projectile'][1],
                'native_exports_sha256': sorted(digests), 'area_chunks': inventory['area_chunks'],
                'worker': {'file': 'physics-removals.json', 'sha256': sha(worker_raw)},
                'contacts': True, 'objects': objects}
    if fence_response:
        manifest.update(version=4, ram_policy=RAM_POLICY)
    elif whole_contact_response:
        manifest.update(version=5, ram_policy=WHOLE_CONTACT_RAM_POLICY)
    elif moving_fence_response:
        manifest.update(version=6, ram_policy=MOVING_FENCE_RAM_POLICY)
    elif angular_fence_response:
        manifest.update(version=7, ram_policy=ANGULAR_FENCE_RAM_POLICY)
    manifest_raw = dc.canonical(manifest) + b'\n'
    dc.json_value(manifest_raw, MAX_MANIFEST_BYTES, 64000, 12)
    return manifest_raw, worker_raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='fresh output directory under configured local/')
    parser.add_argument('--native-export', action='append', default=[])
    parser.add_argument('--native-sha256', action='append', default=[])
    response = parser.add_mutually_exclusive_group()
    response.add_argument('--fence-response', action='store_true',
                        help='Explicit test_lab energy response: domain v4 / worker v5; requires a native join')
    response.add_argument('--whole-contact-response', action='store_true',
                         help='Explicit 8000J project policy for existing whole fragiles/trees: domain v5 / worker v6; requires a native join')
    response.add_argument('--moving-fence-response', action='store_true',
                         help='Explicit 8000J total-linear fence / normal-linear other response: domain v6 / worker v7; requires a native join')
    response.add_argument('--angular-fence-response', action='store_true',
                         help='Explicit linear-first fence response with bounded angular fallback: domain v7 / worker v8; requires a native join')
    args = parser.parse_args(argv)
    require(len(args.native_export) == len(args.native_sha256) <= 2,
            'zero, one or two paired native exports/hashes required')
    require(not args.fence_response or args.native_export, 'fence response requires pinned native exports')
    require(not args.whole_contact_response or args.native_export, 'whole contact response requires pinned native exports')
    require(not args.moving_fence_response or args.native_export, 'moving fence response requires pinned native exports')
    require(not args.angular_fence_response or args.native_export, 'angular fence response requires pinned native exports')
    inventory = build_inventory()
    manifest_raw = worker_raw = None
    if args.native_export:
        local = dc.configured_paths()['local_artifacts_root']
        exports = []
        for path, digest in zip(args.native_export, args.native_sha256):
            path = dc.no_links(Path(path).absolute())
            require(path.is_relative_to(local), 'native evidence must be under local')
            exports.append((dc.read(path, tc.MAX_NATIVE_BYTES, digest), digest))
        manifest_raw, worker_raw = join_exports(inventory, exports, fence_response=args.fence_response,
                                              whole_contact_response=args.whole_contact_response,
                                              moving_fence_response=args.moving_fence_response,
                                              angular_fence_response=args.angular_fence_response)
    output = dc.fresh_output(args.out, dc.configured_paths()['local_artifacts_root'])
    inventory_raw = dc.canonical(inventory) + b'\n'
    require(len(inventory_raw) <= 16 * 1024 * 1024, 'inventory output byte bound')
    dc.save(output/'inventory.json', inventory_raw)
    dc.save(output/'probe-spec.json', probe_spec_bytes(inventory))
    result = {'status': 'SOURCE_INVENTORY_READY_NATIVE_JOIN_NOT_RUN',
              'inventory_sha256': sha(inventory_raw), 'spec_sha256': sha(probe_spec_bytes(inventory)),
              'objects': len(inventory['eligible']), 'area_chunks': len(inventory['area_chunks']),
              'movement_objects': inventory['summary']['movement_eligible_instances'],
              'native_acceptance': 'NOT_RUN'}
    if manifest_raw is not None:
        dc.save(output/'manifest.json', manifest_raw)
        dc.save(output/'physics-removals.json', worker_raw)
        result.update(status='SOURCE_AND_NATIVE_JOIN_PASS_VISUALS_NOT_RUN',
                      manifest_sha256=sha(manifest_raw), worker_sha256=sha(worker_raw))
    dc.save(output/'receipt.json', dc.canonical(result) + b'\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
