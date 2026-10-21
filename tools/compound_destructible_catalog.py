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
import math
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
# MAPS-02 kind 'falling_atom' is joined separately (join_falling_atoms), never in inventory['eligible'].
RAM_POLICY = 'test_lab-fence-energy-v1'
FENCE_ENERGY_J = 8000
WHOLE_CONTACT_RAM_POLICY = 'test_lab-whole-object-energy-v1'
# Explicit project policy only; original reference HP does not establish this
# energy cost or the closed historical server's resistance/ram damage law.
WHOLE_CONTACT_ENERGY_J = 8000
MOVING_FENCE_RAM_POLICY = 'test_lab-fence-total-energy-v1'
ANGULAR_FENCE_RAM_POLICY = 'test_lab-fence-linear-angular-energy-v1'
# Static native-index provenance (tools/map_package.py static_native_index):
# OBSERVED on the recorded Karelia/Prohorovka passive exports, INFERRED elsewhere.
STATIC_INDEX_RULE = 'static-chunk-order-v1'
# Fence resources whose total-linear/angular ram response the gateway admits
# (server/gateway/src/shared/fragiles.rs FENCE_TOTAL_RESOURCES). Other complete
# movement-only fragiles are excluded with a reason instead of failing the map.
FENCE_TOTAL_RESOURCES = (
    'content/GatesAndFences/gaf010_Fence/normal/lod0/gaf010_FenceTile1.model',
    'content/GatesAndFences/gaf010_Fence/normal/lod0/gaf010_FenceTile2.model',
    'content/GatesAndFences/gaf011_Fence/normal/lod0/gaf011_FenceTile1.model',
    'content/GatesAndFences/gaf011_Fence/normal/lod0/gaf011_FenceTile2.model',
    'content/GatesAndFences/gaf011_Fence/normal/lod0/gaf011_FenceTile3.model',
    'content/GatesAndFences/gaf012_Fence/normal/lod0/gaf012_FenceTile1.model',
    'content/GatesAndFences/gaf012_Fence/normal/lod0/gaf012_FenceTile2.model',
)
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
    name = inventory.get('map')
    dc.map_profile(name)
    require(inventory.get('version') == 3 and
            inventory.get('kind') == 'p06r_compound_destructible_catalog_inventory',
            'P06R inventory identity')
    rows = inventory['eligible']
    require(type(rows) is list and 0 < len(rows) <= MAX_OBJECTS, 'P06R object count bound')
    chunks = inventory['area_chunks']
    limit = inventory.get('area_chunk_limit', MAX_CHUNKS)
    require(limit in (MAX_CHUNKS, tc.MAX_STATIC_AREAS), 'area chunk limit')
    require(type(chunks) is list and 0 < len(chunks) <= limit and
            all(type(chunk) is int and 0 <= chunk <= 65535 for chunk in chunks) and
            chunks == sorted(set(chunks)), 'sorted unique bounded area_chunks required')
    spec = inventory['probe_spec']
    require(spec == {'version': 2, 'kind': 'p06q_tree_contact_catalog_spec', 'map': name,
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


def build_inventory(sources=None, *, fence_policy_only=False):
    """Preserve accepted P06Q rows and add complete movement-only fragiles.

    fence_policy_only (new maps) additionally excludes complete movement-only
    fragiles whose resource has no admitted ram response in the gateway.
    """
    sources = tc.load_sources() if sources is None else sources
    name = sources['map']
    limit = tc.MAX_STATIC_AREAS if fence_policy_only else MAX_CHUNKS
    base = tc.build_inventory(sources, chunk_limit=limit, generalized=fence_policy_only)
    meshes = dc.verify_sources(sources)
    legacy = dc.build_inventory(sources, generalized=fence_policy_only)
    rows, added = [], []
    accepted_ids = {row['instance_id'] for row in base['eligible']}
    for source_row in legacy['fragiles']:
        contract = legacy['material_contracts'][source_row['resource']]
        reasons = movement_eligibility(source_row, contract)
        if fence_policy_only and not reasons and source_row['resource'] not in FENCE_TOTAL_RESOURCES:
            reasons.append('movement_fragile_outside_admitted_fence_ram_policy')
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
                'schema': 'destructible-object-source.v3', 'map': name,
                'kind': 'movement_fragile', 'destructibles_sha256': dc.DESTRUCTIBLES_SHA256,
                'physics_manifest_sha256': dc.map_profile(name).files()['physics'][1],
                'projectile_manifest_sha256': dc.map_profile(name).files()['projectile'][1],
                'material_contract': contract,
                'instance': {key: value for key, value in row.items()
                             if key not in ('eligible', 'exclusions', 'native_index')},
                'collision_flags': 128, 'material_kind': 73,
            }
            row['object_revision'] = sha(dc.canonical(identity))
            added.append(row)
        rows.append(row)
    require(added or fence_policy_only, 'no complete movement-only fragile source objects found')
    inventory = copy.deepcopy(base)
    eligible = sorted(inventory['eligible'] + added, key=lambda row: row['instance_id'])
    chunks = sorted({row['chunk_id'] for row in eligible})
    inventory.update(version=3, kind='p06r_compound_destructible_catalog_inventory',
                     eligible=eligible, movement_fragiles=rows, area_chunks=chunks,
                     movement_material_contracts=legacy['material_contracts'])
    if fence_policy_only:
        inventory['area_chunk_limit'] = tc.MAX_STATIC_AREAS
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


def static_mapping(inventory, package_dir, *, duplicates_allowed=False):
    """Static native-index mapping of every probe chunk, in tc.validate_native form."""
    import map_package
    _validate_inventory(inventory)
    directory = dc.no_links(Path(package_dir).absolute())
    package, _ = map_package.verify(directory)
    require(package['map'] == inventory['map'], 'package map differs from inventory')
    raw = dc.read(directory / 'destructibles/static-index.json', 64 * 1024 * 1024,
                  package['files']['destructibles/static-index.json']['sha256'])
    index = dc.json_value(raw, 64 * 1024 * 1024, 2_000_000, 12)
    require(index.get('rule') == STATIC_INDEX_RULE and index.get('kind') == 'static_chunk_destructible_order',
            'static index identity')
    physics_raw = dc.read(directory / 'physics/manifest.json', 64 * 1024 * 1024,
                          package['files']['physics/manifest.json']['sha256'])
    physics = dc.json_value(physics_raw, 64 * 1024 * 1024, 4_000_000, 32)
    transforms = {(tuple(r['chunk']), r['instance']): r['transform'] for r in physics['instances']}
    ambiguous = set(index['ambiguous_chunks'])
    mapping = {}
    for chunk_id in inventory['probe_spec']['chunk_ids']:
        require(chunk_id not in ambiguous, 'ambiguous static native index chunk')
        row = index['chunks'].get(str(chunk_id))
        require(row is not None and 0 < len(row['items']) <= tc.MAX_ITEMS_PER_CHUNK, 'static chunk index bound')
        by_index, identities = {}, set()
        for position, item in enumerate(row['items']):
            require(item['index'] == position, 'static index order')
            identity = (dc.resource(item['resource']),
                        dc.matrix_bits(transforms[tuple(row['chunk']), item['instance']]))
            require(duplicates_allowed or identity not in identities, 'ambiguous static filename/matrix')
            identities.add(identity)
            by_index[position] = identity
        mapping[chunk_id] = by_index
    return mapping, sha(raw)


def join_exports(inventory, exports, *, fence_response=False, whole_contact_response=False,
                 moving_fence_response=False, angular_fence_response=False):
    """Require complete stable native mappings; no partial admission fallback."""
    _validate_inventory(inventory)
    require(type(exports) is list and 1 <= len(exports) <= 2, 'one or two native exports required')
    mappings, digests = [], []
    for raw, expected in exports:
        require(type(raw) is bytes and sha(raw) == dc.digest(expected), 'native export SHA256 before parse')
        mappings.append(tc.validate_native(raw, inventory))
        digests.append(expected)
    require(len(set(digests)) == len(digests) and all(row == mappings[0] for row in mappings),
            'native exports disagree or duplicate')
    return join_mapping(inventory, mappings[0], {'native_exports_sha256': sorted(digests)},
                        fence_response=fence_response, whole_contact_response=whole_contact_response,
                        moving_fence_response=moving_fence_response, angular_fence_response=angular_fence_response)


def exclude_duplicate_identities(inventory, package_dir):
    """Objects whose (resource, matrix) repeats inside one chunk cannot be joined
    by identity; they stay static with a reason instead of guessing."""
    _validate_inventory(inventory)
    mapping, _ = static_mapping(inventory, package_dir, duplicates_allowed=True)
    duplicates = {(chunk, identity) for chunk, rows in mapping.items()
                  for identity in set(rows.values()) if list(rows.values()).count(identity) > 1}
    kept, dropped = [], []
    for row in inventory['eligible']:
        key = (row['chunk_id'], (row['resource'], dc.matrix_bits(row['transform'])))
        (dropped if key in duplicates else kept).append(row)
    if not dropped:
        return inventory
    inventory = copy.deepcopy(inventory)
    chunks = sorted({row['chunk_id'] for row in kept})
    inventory.update(eligible=kept, area_chunks=chunks)
    inventory['probe_spec']['chunk_ids'] = chunks
    inventory['static_index_exclusions'] = [{'instance_id': row['instance_id'], 'kind': row['kind'],
                                             'reason': 'duplicate_resource_matrix_in_chunk_static_index_ambiguous'}
                                            for row in dropped]
    inventory['summary'].update(eligible_instances=len(kept), probe_chunks=len(chunks),
                                static_index_exclusions=len(dropped))
    _validate_inventory(inventory)
    return inventory


def join_static(inventory, package_dir):
    """Domain v7 / worker v8 (current angular policy) with an explicit static native index source."""
    # Duplicate identities may remain in a chunk; the join below still admits
    # only rows whose identity has exactly one native index.
    mapping, digest = static_mapping(inventory, package_dir, duplicates_allowed=True)
    source = {'rule': STATIC_INDEX_RULE, 'static_index_sha256': digest,
              'classification': 'INFERRED_STATIC_RULE_NATIVE_CONFIRMATION_NOT_RUN'}
    return join_mapping(inventory, mapping, {'native_index_source': source}, angular_fence_response=True)


def join_mapping(inventory, mapping, provenance, *, fence_response=False, whole_contact_response=False,
                 moving_fence_response=False, angular_fence_response=False):
    responses = (fence_response, whole_contact_response, moving_fence_response, angular_fence_response)
    require(all(type(value) is bool for value in responses),
            'response flags must be booleans')
    require(sum(responses) <= 1, 'response policies are mutually exclusive')
    require(set(provenance) in ({'native_exports_sha256'}, {'native_index_source'}), 'index provenance')
    static = 'native_index_source' in provenance
    require(not static or angular_fence_response, 'static index requires the current angular policy')
    _validate_inventory(inventory)
    name = inventory['map']
    objects, worker_objects, seen = [], [], set()
    for row in inventory['eligible']:
        identity = (row['resource'], dc.matrix_bits(row['transform']))
        matches = [index for index, candidate in mapping[row['chunk_id']].items() if candidate == identity]
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
    files = dc.map_profile(name).files()
    worker = {'version': 4, 'profile': 'test_lab', 'map': name,
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
    manifest = {'version': 3, 'profile': 'test_lab', 'map': name,
                'destructibles_sha256': dc.DESTRUCTIBLES_SHA256,
                'physics_manifest_sha256': files['physics'][1],
                'projectile_manifest_sha256': files['projectile'][1],
                **provenance, 'area_chunks': inventory['area_chunks'],
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


# ---------------------------------------------------------------- MAPS-02 falling atoms

FALLING_ATOM_POLICY = 'test_lab-falling-atom-client-break-predicate-v1'
FALLING_ATOM_DOMAIN_RESPONSE = 'client_break_predicate'
FALLING_ATOM_WORKER_RESPONSE = 'sensor_trigger'
TRIGGER_PREFIX = 'falling-atom-triggers'
MAX_TRIGGER_TRIANGLES = 262_144
MAX_TRIGGER_TRIANGLES_PER_OBJECT = 256
MAX_COLUMNS_PER_CHUNK = 125
MAX_TRIGGER_BYTES = MAX_TRIGGER_TRIANGLES * 3 * 12


def load_triggers(trigger_dir, package_dir):
    """Hash-check one tools/map_package.py triggers output against its package."""
    import map_package
    package, digest = map_package.verify(dc.no_links(Path(package_dir).absolute()))
    directory = dc.no_links(Path(trigger_dir).absolute())
    raw = dc.read(directory / (TRIGGER_PREFIX + '.json'), 16 * 1024 * 1024)
    manifest = dc.json_value(raw, 16 * 1024 * 1024, 400000, 12)
    require(manifest.get('version') == 1 and manifest.get('kind') == 'wot091_falling_atom_trigger_mesh' and
            manifest.get('map') == package['map'] and manifest.get('package_sha256') == digest and
            manifest.get('inventory_sha256') == package['files']['destructibles/inventory.json']['sha256'],
            'trigger mesh identity/package binding')
    files = {}
    for key, fmt in (('vertices', 'float32_xyz'), ('triangles', 'uint32_abc')):
        part = manifest[key]
        require(part['file'] == TRIGGER_PREFIX + ('.vertices.f32' if key == 'vertices' else '.triangles.u32') and
                part['format'] == fmt and part['stride'] == 12 and part['bytes'] == part['count'] * 12 and
                0 < part['count'] <= MAX_TRIGGER_TRIANGLES * (3 if key == 'vertices' else 1), 'trigger part shape')
        files[part['file']] = dc.read(directory / part['file'], MAX_TRIGGER_BYTES, part['sha256'])
    return manifest, sha(raw), package, digest, files


def falling_definitions():
    original = dc.configured_paths()['original_client_root']
    raw = dc.read(original / 'res/scripts/destructibles.xml', 512 * 1024, dc.DESTRUCTIBLES_SHA256)
    _, by_resource, _ = dc.parse_definitions(raw)
    return {name: row for name, row in by_resource.items() if row['family'] == 'fallingAtoms'}


def falling_atom_rows(inventory, package_dir, trigger_dir):
    """Eligible falling atoms with reasons for every excluded instance.

    Native index: the same static chunk-order rule as the whole catalog
    (OBSERVED for Prohorovka poles 71/71 against native exports, INFERRED elsewhere).
    """
    import map_package
    manifest, manifest_sha, package, _, files = load_triggers(trigger_dir, package_dir)
    directory = dc.no_links(Path(package_dir).absolute())
    index = dc.json_value(dc.read(directory / 'destructibles/static-index.json', 64 * 1024 * 1024,
                                  package['files']['destructibles/static-index.json']['sha256']),
                          64 * 1024 * 1024, 2_000_000, 12)
    physics = dc.json_value(dc.read(directory / 'physics/manifest.json', 64 * 1024 * 1024,
                                    package['files']['physics/manifest.json']['sha256']), 64 * 1024 * 1024, 4_000_000, 32)
    pkg_inventory = dc.json_value(dc.read(directory / 'destructibles/inventory.json', 64 * 1024 * 1024,
                                          package['files']['destructibles/inventory.json']['sha256']),
                                  64 * 1024 * 1024, 4_000_000, 12)
    require(index.get('rule') == STATIC_INDEX_RULE, 'static index identity')
    definitions = falling_definitions()
    transforms = {(tuple(r['chunk']), r['instance']): r['transform'] for r in physics['instances']}
    by_instance = {row['instance_id']: row for row in pkg_inventory['instances']}
    taken = {row['instance_id'] for row in inventory['eligible']}
    ambiguous = set(index['ambiguous_chunks'])
    rows, excluded = [], []
    for trigger in manifest['instances']:
        source = by_instance[trigger['instance_id']]
        require(source['family'] == 'fallingAtoms' and source['resource'] == trigger['resource'] and
                source['instance'] == trigger['instance'] and source['chunk'] == trigger['chunk'], 'trigger/inventory identity')
        definition = definitions.get(trigger['resource'])
        require(definition is not None, 'falling atom definition missing')
        fields = definition['fields']
        reasons = []
        if trigger['instance_id'] in taken:
            reasons.append('instance_already_admitted_as_other_kind')
        if trigger['blocking_physics_triangles'] or trigger['blocking_projectile_triangles']:
            reasons.append('falling_atom_blocking_geometry_unknown')
        if trigger['triangles'] == 0:
            reasons.append('falling_atom_no_trigger_geometry')
        if trigger['triangles'] > MAX_TRIGGER_TRIANGLES_PER_OBJECT:
            reasons.append('falling_atom_trigger_over_bound')
        if '/preferredTiltDirections[1]' in fields:
            reasons.append('falling_atom_preferred_tilt_unsupported')
        health = definition['reference_health']
        if type(health) is not int or not 1 <= health <= 65535:
            reasons.append('reference_health_outside_bound')
        kdc = fields.get('/kineticDamageCorrection[1]', 0.0)
        if type(kdc) is str:
            kdc = float(kdc)
        if type(kdc) not in (int, float) or not math.isfinite(kdc) or not 0 <= kdc <= 8:
            reasons.append('kinetic_damage_correction_outside_bound')
        chunk_id = source['chunk_id']
        native_index = None
        if chunk_id in ambiguous:
            reasons.append('ambiguous_static_native_index_rule')
        else:
            chunk = index['chunks'].get(str(chunk_id))
            identity = (trigger['resource'], dc.matrix_bits(transforms[tuple(trigger['chunk']), trigger['instance']]))
            matches = [item['index'] for item in chunk['items']
                       if (item['resource'], dc.matrix_bits(transforms[tuple(chunk['chunk']), item['instance']])) == identity]
            if len(matches) != 1:
                reasons.append('duplicate_resource_matrix_in_chunk_static_index_ambiguous')
            elif matches[0] > 255:
                reasons.append('falling_atom_index_over_255')
            else:
                native_index = matches[0]
        if reasons:
            excluded.append({'instance_id': trigger['instance_id'], 'resource': trigger['resource'], 'reasons': reasons})
            continue
        scaled = int(math.ceil(trigger['scale'] * trigger['scale'] * health))
        require(1 <= scaled <= 65535, 'scaled health bound')
        identity = {'schema': 'destructible-object-source.v4-falling-atom', 'map': inventory['map'],
                    'kind': 'falling_atom', 'destructibles_sha256': dc.DESTRUCTIBLES_SHA256,
                    'trigger_manifest_sha256': manifest_sha, 'policy': FALLING_ATOM_POLICY,
                    'instance': {k: trigger[k] for k in ('instance_id', 'chunk', 'chunk_id', 'instance', 'resource',
                                                          'first_triangle', 'triangles', 'scale')},
                    'reference_health': health, 'kinetic_damage_correction': float(kdc)}
        rows.append({'object_id': trigger['instance_id'] + 1, 'instance_id': trigger['instance_id'],
                     'chunk_id': chunk_id, 'native_index': native_index, 'resource': trigger['resource'],
                     'health': health, 'material_kind': 0,
                     'projectile_first_triangle': source['projectile_first_triangle'], 'projectile_triangle_count': 0,
                     'physics_first_triangle': source['physics_first_triangle'], 'physics_triangle_count': 0,
                     'object_revision': sha(dc.canonical(identity)), 'kind': 'falling_atom',
                     'ram_response': FALLING_ATOM_DOMAIN_RESPONSE, 'scaled_health': scaled,
                     'kinetic_damage_correction': float(kdc),
                     'trigger_first_triangle': trigger['first_triangle'], 'trigger_triangle_count': trigger['triangles']})
    per_chunk = Counter(row['chunk_id'] for row in rows)
    require(max(per_chunk.values(), default=0) <= MAX_COLUMNS_PER_CHUNK, 'fallenColumns per-area budget')
    return rows, excluded, manifest, manifest_sha, files


def join_falling_atoms(inventory, package_dir, trigger_dir, manifest_raw, worker_raw):
    """Domain v8 / worker v9: the static domain v7 / worker v8 catalog plus falling atoms."""
    manifest = json.loads(manifest_raw)
    worker = json.loads(worker_raw)
    require(manifest['version'] == 7 and 'native_index_source' in manifest and worker['version'] == 8,
            'falling atoms extend the static-index angular catalog only')
    rows, excluded, triggers, triggers_sha, files = falling_atom_rows(inventory, package_dir, trigger_dir)
    require(rows, 'no eligible falling atoms')
    limit = inventory.get('area_chunk_limit', MAX_CHUNKS)
    chunks = sorted(set(manifest['area_chunks']) | {row['chunk_id'] for row in rows})
    require(len(chunks) <= limit, 'area chunk budget with falling atoms')
    require(len(manifest['objects']) + len(rows) <= MAX_OBJECTS, 'catalog object bound with falling atoms')
    manifest['objects'] = sorted(manifest['objects'] + rows, key=lambda row: row['object_id'])
    ids = [row['object_id'] for row in manifest['objects']]
    require(ids == sorted(set(ids)), 'unique object IDs with falling atoms')
    manifest.update(version=8, falling_atom_policy=FALLING_ATOM_POLICY, area_chunks=chunks)
    worker['objects'] = sorted(worker['objects'] + [
        {'object_id': row['object_id'], 'instance_id': row['instance_id'], 'kind': 'falling_atom',
         'first_triangle': row['trigger_first_triangle'], 'triangle_count': row['trigger_triangle_count'],
         'object_revision': row['object_revision'], 'ram_energy_j': 0, 'ram_response': FALLING_ATOM_WORKER_RESPONSE}
        for row in rows], key=lambda row: row['object_id'])
    worker.update(version=9, falling_atom_triggers={key: {k: triggers[key][k] for k in ('file', 'format', 'stride', 'count', 'bytes', 'sha256')}
                                                     for key in ('vertices', 'triangles')})
    worker_raw = dc.canonical(worker) + b'\n'
    dc.json_value(worker_raw, MAX_WORKER_BYTES, 64000, 12)
    manifest['worker'] = {'file': 'physics-removals.json', 'sha256': sha(worker_raw)}
    manifest_raw = dc.canonical(manifest) + b'\n'
    dc.json_value(manifest_raw, MAX_MANIFEST_BYTES, 64000, 12)
    report = {'falling_atoms': len(rows), 'falling_atom_exclusions': dict(Counter(r for e in excluded for r in e['reasons'])),
              'trigger_manifest_sha256': triggers_sha, 'excluded': excluded}
    return manifest_raw, worker_raw, files, report


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
    parser.add_argument('--package', help='tools/map_package.py package directory of a map other than '
                        'the default Prohorovka sources')
    parser.add_argument('--static-index', action='store_true',
                        help='join the package static native index (domain v7 / worker v8, INFERRED); '
                        'never mixed with native exports')
    parser.add_argument('--falling-atoms', metavar='TRIGGER_DIR',
                        help='MAPS-02: add fallingAtoms from a tools/map_package.py triggers output '
                        '(domain v8 / worker v9; requires --static-index)')
    args = parser.parse_args(argv)
    require(not args.falling_atoms or args.static_index, '--falling-atoms requires --static-index')
    require(len(args.native_export) == len(args.native_sha256) <= 2,
            'zero, one or two paired native exports/hashes required')
    require(not args.static_index or (args.package and not args.native_export and not
            (args.fence_response or args.whole_contact_response or args.moving_fence_response or
             args.angular_fence_response)), '--static-index needs --package and excludes native/policy flags')
    require(not args.fence_response or args.native_export, 'fence response requires pinned native exports')
    require(not args.whole_contact_response or args.native_export, 'whole contact response requires pinned native exports')
    require(not args.moving_fence_response or args.native_export, 'moving fence response requires pinned native exports')
    require(not args.angular_fence_response or args.native_export, 'angular fence response requires pinned native exports')
    if args.package:
        import map_package
        name = map_package.verify(args.package)[0]['map']
        builtin = name in [profile.name for profile in dc.PROFILES]
        # Accepted maps keep their legacy pinned sources; only the index comes
        # from the package, so the result is comparable with the accepted catalog.
        profile = dc.map_profile(name) if builtin else dc.register_package(args.package)
        # Only the accepted Prohorovka catalog keeps its exact historical bounds.
        generalized = profile.name != tc.MAP
        inventory = build_inventory(tc.load_sources(profile.name), fence_policy_only=generalized)
        if args.static_index:
            inventory = exclude_duplicate_identities(inventory, args.package)
    else:
        inventory = build_inventory()
    manifest_raw = worker_raw = None
    falling = None
    if args.static_index:
        manifest_raw, worker_raw = join_static(inventory, args.package)
        if args.falling_atoms:
            manifest_raw, worker_raw, trigger_files, falling = join_falling_atoms(
                inventory, args.package, args.falling_atoms, manifest_raw, worker_raw)
    elif args.native_export:
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
        if falling is not None:
            for name, raw in sorted(trigger_files.items()):
                dc.save(output/name, raw)
            dc.save(output/'falling-atoms.json', dc.canonical(falling) + b'\n')
        result.update(status='SOURCE_AND_STATIC_INDEX_JOIN_PASS_NATIVE_NOT_RUN' if args.static_index
                      else 'SOURCE_AND_NATIVE_JOIN_PASS_VISUALS_NOT_RUN',
                      manifest_sha256=sha(manifest_raw), worker_sha256=sha(worker_raw))
        if falling is not None:
            result.update(falling_atoms=falling['falling_atoms'], falling_atom_exclusions=falling['falling_atom_exclusions'],
                          falling_atom_policy=FALLING_ATOM_POLICY)
    dc.save(output/'receipt.json', dc.canonical(result) + b'\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
