"""Immutable profile3 representation of two native-exported MS-1 tankmen.

No database or client writes. The frozen profile2 encoder/fixtures are validated
and the new state must reverse exactly to their bytes. Own training policy is
explicitly test_lab 100 percent, with no skills, earned XP or invented history.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import pickletools
import re
import struct

import test_garage_state as garage
import hangar_state as legacy
from client_audit import ROOT, config, read_limited, save_json, sha256
from verify_hangar import literal, EXE_SHA

BASE_GENERATOR_SHA = 'dec1f884dd8b22ef0d4a6c21389cb37c075f008feb6a12bc7d43888c5b4c5825'
GRANT_ID = 'test-ms1-crew-v1'
ROLES = ('commander', 'driver')
PROFILE_FIELDS = garage.PROFILE_FIELDS | {'inventory', 'test_grant', 'crew', 'crew_grant'}
digest = lambda raw: hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path, maximum=32768):
    path = garage.local_file(path)
    raw = read_limited(path, maximum)
    return garage.bounded_json(raw, maximum), raw


def dependencies():
    dep = garage.verify_encoder()
    path = Path(garage.__file__).resolve()
    require(sha256(path) == BASE_GENERATOR_SHA, 'frozen profile2 generator changed')
    return {'file': str(Path(__file__).resolve()), 'sha256': sha256(Path(__file__)),
            'dependency': dep, 'base_generator': {'file': str(path), 'sha256': BASE_GENERATOR_SHA}}


def validate_base(directory):
    directory = garage.local_file(directory)
    manifest, manifest_raw = read_json(directory / 'manifest.json')
    require(set(manifest) == {'fixture_version', 'ruleset', 'profile_version', 'snapshot_revision',
            'wire_sync_revision', 'compatibility_catalog_revision', 'account_id', 'native_database_id',
            'profile_source', 'base_profile_source', 'native_descriptors', 'generator', 'files',
            'native_compatibility', 'preservation', 'grant'}, 'exact base manifest keys required')
    version_keys = ('fixture_version', 'profile_version', 'snapshot_revision',
                    'wire_sync_revision', 'compatibility_catalog_revision')
    require(all(type(manifest.get(k)) is int for k in version_keys)
            and tuple(manifest[k] for k in version_keys) == (2, 2, 2, 1, 3), 'exact r2 base required')
    profile, profile_raw = read_json(directory / 'profile-input.json', 8192)
    origin, origin_raw = read_json(directory / 'base-profile-input.json', 8192)
    garage.validate_profile(profile, origin, digest(origin_raw))
    require(manifest.get('account_id') == profile['account_id'] and
            type(manifest.get('native_database_id')) is int and
            manifest['native_database_id'] == profile['native_database_id'] and manifest.get('ruleset') == 'test_lab',
            'base manifest identity/ruleset differs')
    for key, filename, raw in (('profile_source', 'profile-input.json', profile_raw),
                              ('base_profile_source', 'base-profile-input.json', origin_raw)):
        require(manifest[key] == {'file': filename, 'relative_to': 'fixture_directory', 'sha256': digest(raw)},
                'immutable base profile provenance differs')
    require(manifest['generator']['sha256'] == BASE_GENERATOR_SHA, 'base fixture generator provenance')
    sources = manifest['native_descriptors']
    ms1, is7, native_sources = garage.read_native_inputs(sources['ms1']['file'], sources['is7']['file'])
    require(native_sources == sources, 'base native sources changed')
    model, compatibility, trees, preservation = garage.build_payloads(profile, origin, digest(origin_raw), ms1, is7)
    payloads = {}
    for name, tree in trees.items():
        raw = read_limited(directory / name, 16384)
        records = [r for r in manifest['files'] if r['file'] == name]
        require(len(records) == 1 and records[0]['sha256'] == digest(raw) and records[0]['bytes'] == len(raw),
                'base native payload hash mismatch')
        require(raw == legacy.encode_data(tree), 'base differs from frozen deterministic generator')
        require(legacy.encode_data(literal(raw)) == raw, 'bounded literal decoder disagrees with base')
        payloads[name] = raw
    same = lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    require(same(read_json(directory / 'compatibility.json')[0], compatibility), 'base compatibility mapping differs')
    require(same(read_json(directory / 'fixture.json')[0], model), 'base domain fixture differs')
    require(same(manifest['preservation'], preservation) and same(manifest['grant'], profile['test_grant']),
            'base preservation/grant provenance differs')
    return dict(directory=directory, manifest=manifest, manifest_raw=manifest_raw,
                profile=profile, profile_raw=profile_raw, model=model, compatibility=compatibility,
                trees=trees, payloads=payloads)


# Measured source/compiled pair from export01-prepare, exercised by the real
# export01 native run. A future producer revision needs an explicit checkpoint;
# validation never trusts whichever helper happens to be in the working tree.
PROBE_CHECKPOINTS = {
    '37d1444bb58663bddfdfe118e1a8a6315ece894d26036b276033ee913e690ded':
    'ea83f9bbeb90e803fd899f0fd561513cae06789c29aed675c06eb19a945494f7',
}
NATIVE_CREW_SOURCES = {
    'res/scripts/common/items/tankmen.pyc': '74f914b1e5e7e574086dd865d87e4cfbf8cace6e60b5e506757eba28ca8bc530',
    'res/scripts/common/items/__init__.pyc': '587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176',
    'res/scripts/common/dossiers2/__init__.pyc': '7aa74deb47f9718f4eae0d331da2e8ef07ac4e4673b1ec49ab72ee4c1ab58d3b',
    'res/scripts/common/dossiers2/custom/builders.pyc': 'e973a914947a4183946494afe566e8e9118c6f2c27448c8e74bf772aae5a76c6',
    'res/scripts/common/dossiers2/common/dossierbuilder.pyc': 'eed33c28730668a7da5bf7fe6a5a74ac2d0dfd83be5c32a55ff365652aab157e',
    'res/scripts/common/dossiers2/common/dossierdescr.pyc': '7396051744955d9911490d1b73a7fa7cd286915764c07a52e9743ab65a712179',
    'res/scripts/item_defs/tankmen/tankmen.xml': 'a8604e50bf829072d083535ea3339302a1584582d42e62814a3a871e310ea73b',
    'res/scripts/item_defs/tankmen/ussr.xml': '7277417f9ffac7f742cd6b1bfce02cc7a182558fbdf7db137604323403552cee',
    'res/scripts/item_defs/vehicles/ussr/MS-1.xml': 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535',
}


def _schema(value, fields, label):
    require(type(value) is dict and set(value) == set(fields), 'exact ' + label + ' fields required')


def _same(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def _sha(value, label):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'bounded SHA256: ' + label)
    return value


def _strict_evidence_json(raw, maximum):
    require(type(raw) is bytes and len(raw) <= maximum, 'bounded evidence JSON required')
    def pairs(values):
        result = {}
        require(len(values) <= 128, 'evidence object field bound')
        for key, value in values:
            require(key not in result and len(key) <= 128, 'duplicate/oversized evidence key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('nonfinite evidence number')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (RecursionError, UnicodeError) as error:
        raise ValueError('invalid bounded evidence JSON') from error
    nodes = 0
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        require(nodes <= 4096 and depth <= 12, 'evidence structural bound')
        if type(item) is dict:
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            require(len(item) <= 256, 'evidence array bound')
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            require(len(item) <= 8192 and '\0' not in item, 'evidence string bound')
        elif type(item) is float:
            require(math.isfinite(item), 'nonfinite evidence float')
        elif type(item) is int:
            require(-(1 << 63) <= item < (1 << 63), 'evidence integer bound')
    visit(value, 0)
    return value


def _relative_artifact(directory, relative):
    require(type(relative) is str and 0 < len(relative) <= 256 and '\0' not in relative,
            'bounded artifact relative path')
    result = garage.local_file(directory / relative)
    require(result.is_relative_to(directory) and result != directory, 'artifact escaped prepared directory')
    return result


def _validate_compiled_probe(plan, directory, outcome):
    require(type(plan.get('sources')) is list and 1 <= len(plan['sources']) <= 16, 'prepared source list bound')
    rows = [r for r in plan['sources'] if type(r) is dict and r.get('path') == 'client_patch/ms1_crew_probe.py']
    require(len(rows) == 1, 'one measured native crew probe source required')
    row = rows[0]
    _schema(row, ('path', 'sha256', 'compiled', 'metadata'), 'prepared crew source')
    require(row['sha256'] in PROBE_CHECKPOINTS, 'unmeasured native crew producer source')
    compiled = _relative_artifact(directory, row['compiled'])
    metadata = _strict_evidence_json(read_limited(_relative_artifact(directory, row['metadata']), 8192), 8192)
    _schema(metadata, ('magic', 'source_sha256', 'source', 'pyc_sha256', 'source_executed', 'compiler'), 'compiled metadata')
    raw = read_limited(compiled, 256 * 1024)
    expected_pyc = PROBE_CHECKPOINTS[row['sha256']]
    require(len(raw) >= 8 and raw[:8] == bytes.fromhex('03f30d0a00000000')
            and digest(raw) == expected_pyc and metadata['pyc_sha256'] == expected_pyc
            and metadata['source_sha256'] == row['sha256'] and metadata['source'] == 'ms1_crew_probe.py'
            and metadata['magic'] == '03f30d0a' and metadata['source_executed'] is False
            and type(metadata['compiler']) is str and metadata['compiler'].startswith('2.7.3 '),
            'prepared crew bytecode/source chain differs')
    target = 'res_mods/0.9.1/scripts/client/ms1_crew_probe.pyc'
    require(type(plan.get('files')) is list and 1 <= len(plan['files']) <= 128, 'prepared file bound')
    installed = [f for f in plan['files'] if type(f) is dict and f.get('path') == target]
    require(len(installed) == 1 and installed[0].get('runtime_mutable') is False
            and type(installed[0].get('bytes')) is int and installed[0]['bytes'] == len(raw)
            and installed[0].get('installed_sha256') == expected_pyc, 'installed probe differs from compilation')
    require(read_limited(_relative_artifact(directory, 'bundle/' + target), 256 * 1024) == raw,
            'prepared bundle probe differs from compilation')
    provenance = outcome.get('source_provenance')
    require(type(provenance) is dict and type(provenance.get('modules')) is list
            and len(provenance['modules']) <= 16, 'runtime source provenance missing')
    observed = [m for m in provenance['modules'] if type(m) is dict and m.get('module') == 'ms1_crew_probe']
    require(len(observed) == 1 and observed[0] == {'module': 'ms1_crew_probe',
            'source_sha256': row['sha256'], 'pyc_sha256': expected_pyc}, 'runtime probe provenance differs')


def _native_passports(xml_raw):
    rows = list(garage.walk(garage.decode(xml_raw)))
    values = dict(rows)
    groups = [path for path, _ in rows if re.fullmatch(r'/normalGroups\[1\]/[^/]+\[1\]', path)]
    require(groups == ['/normalGroups[1]/men1[1]'], 'audited original Russian normal group differs')
    identifiers = []
    for kind in ('firstNames', 'lastNames', 'icons'):
        prefix = groups[0] + '/' + kind + '[1]/_'
        found = [int(path[len(prefix):-3]) for path, _ in rows
                 if path.startswith(prefix) and re.fullmatch(r'[0-9]+\[1\]', path[len(prefix):])]
        require(2 <= len(found) <= 2048 and len(set(found)) == len(found), 'original passport ID list differs')
        identifiers.append(sorted(found))
    ranks = [re.fullmatch(r'/ranks\[1\]/([^/]+)\[1\]', path).group(1) for path, _ in rows
             if re.fullmatch(r'/ranks\[1\]/([^/]+)\[1\]', path)]
    require(2 <= len(ranks) <= 32 and len(set(ranks)) == len(ranks), 'original rank list differs')
    result = []
    for slot, role in enumerate(ROLES):
        role_ranks = values['/roleRanks[1]/' + role + '[1]'].split()
        require(2 <= len(role_ranks) <= 32 and role_ranks[1] in ranks, 'native role rank mapping differs')
        result.append({'first_name_id': identifiers[0][slot], 'last_name_id': identifiers[1][slot],
                       'icon_id': identifiers[2][slot], 'rank_id': ranks.index(role_ranks[1])})
    return result


def _validate_native_crew_data(data, paths):
    _schema(data, ('version', 'type_name', 'type_id', 'vehicle_type_compact_descr', 'tankman_item_type',
        'policy', 'crew', 'tankman_dossier_hex', 'tankman_dossier_sha256', 'sources', 'selection_before',
        'selection_after', 'selection_unchanged', 'inventory_mutation_requested', 'loaded_module_files'), 'native crew data')
    for key, expected in (('version', 1), ('type_id', [0, 13]), ('type_name', 'ussr:MS-1'),
                          ('vehicle_type_compact_descr', 3329), ('tankman_item_type', 8),
                          ('policy', 'test_lab_role_level_100_no_skills'),
                          ('selection_unchanged', True), ('inventory_mutation_requested', False)):
        require(_same(data[key], expected), 'native crew policy/type differs: ' + key)
    for key in ('selection_before', 'selection_after'):
        selection = data[key]
        _schema(selection, ('database_id', 'selected_inventory_id', 'selected_descriptor_sha256'), 'native selection')
        garage.bounded_int(selection['database_id'], 'observed native account', 1)
        garage.bounded_int(selection['selected_inventory_id'], 'observed inventory vehicle', 1, 2)
        _sha(selection['selected_descriptor_sha256'], 'selected vehicle descriptor')
    require(_same(data['selection_before'], data['selection_after']), 'export changed account/selected vehicle')
    require(data['loaded_module_files'] == {
        'dossiers2': 'scripts/common/dossiers2/__init__.pyc', 'tankmen': 'scripts/common/items/tankmen.pyc',
        'vehicles': 'scripts/common/items/vehicles.pyc'}, 'unmeasured native loaded module path')
    require(type(data['sources']) is list and len(data['sources']) == len(NATIVE_CREW_SOURCES), 'native source count')
    seen, source_raw = set(), {}
    for source in data['sources']:
        _schema(source, ('relative_path', 'bytes', 'sha256'), 'native resource source')
        relative = source['relative_path']
        require(type(relative) is str and relative in NATIVE_CREW_SOURCES and relative not in seen,
                'unexpected/duplicate native resource source')
        seen.add(relative)
        original = paths['original_client_root'] / relative
        content = read_limited(original, 1024 * 1024)
        garage.bounded_int(source['bytes'], 'source bytes', 1, 1024 * 1024)
        require(source['bytes'] == len(content) and source['sha256'] == digest(content) == NATIVE_CREW_SOURCES[relative],
                'native resource differs from audited original')
        source_raw[relative] = content
    passports = _native_passports(source_raw['res/scripts/item_defs/tankmen/ussr.xml'])
    dossier = legacy.bounded_hex(data['tankman_dossier_hex'], 'native tankman dossier', 2048)
    # Original empty TANKMAN version66 has two absent blocks. Measured native
    # export01 confirms the six-byte header; no client resource is embedded here.
    require(len(dossier) == 6 and struct.unpack('<3H', dossier) == (66, 0, 0)
            and digest(dossier) == _sha(data['tankman_dossier_sha256'], 'tankman dossier'),
            'native empty tankman dossier differs')
    require(type(data['crew']) is list and len(data['crew']) == 2, 'exactly two MS-1 native crew required')
    for slot, (row, role) in enumerate(zip(data['crew'], ROLES)):
        _schema(row, ('slot_index', 'role', 'combined_roles', 'compact_descr_hex', 'compact_descr_sha256',
            'compact_descr_bytes', 'decoded', 'dossier_sha256', 'original_parse_repack_equal',
            'original_dossier_repack_equal'), 'native tankman row')
        compact = legacy.bounded_hex(row['compact_descr_hex'], 'native tankman', 4096)
        garage.bounded_int(row['slot_index'], 'native slot index', 0, 1)
        garage.bounded_int(row['compact_descr_bytes'], 'native descriptor bytes', 19, 4096)
        require(row['slot_index'] == slot and row['role'] == role and row['original_parse_repack_equal'] is True
                and row['original_dossier_repack_equal'] is True and len(compact) == row['compact_descr_bytes']
                and digest(compact) == _sha(row['compact_descr_sha256'], 'tankman descriptor')
                and len(compact) == 19 + len(dossier) and compact[19:] == dossier
                and row['dossier_sha256'] == digest(dossier), 'native compact roundtrip/slot differs')
        # Independent read-only parser for the measured no-skill19-byte prefix.
        # It never creates a native descriptor and refuses extra skills/trailing bytes.
        header, vehicle_id, role_id, level, skills, last, flags, first, surname, icon, rank, free_xp = struct.unpack(
            '<7B4Hi', compact[:19])
        require((header, vehicle_id, role_id, level, skills, last, flags, rank, free_xp) ==
                (8, 13, (1, 3)[slot], 100, 0, 0, 0, 1 | (50 << 5), 0), 'native compact prefix/policy differs')
        decoded = row['decoded']
        expected = {'nation_id': 0, 'vehicle_type_id': 13, 'role': role, 'role_level': 100,
                    'free_xp': 0, 'last_skill_level': 0, 'skills': [], 'is_premium': False, 'is_female': False,
                    'levels_to_next_rank': 50, **passports[slot]}
        _schema(decoded, set(expected) | {'total_xp'}, 'native decoded tankman')
        require(all(_same(decoded[k], v) for k, v in expected.items()), 'decoded native crew policy differs')
        garage.bounded_int(decoded['total_xp'], 'native derived training XP')
        require((first, surname, icon) == tuple(passports[slot][k] for k in
                ('first_name_id', 'last_name_id', 'icon_id')), 'native compact passport differs from original normal group')
        require(row['combined_roles'] == (['commander', 'gunner', 'radioman', 'loader'] if slot == 0 else ['driver']),
                'native combined roles differ')


def validate_export(path):
    value, raw = read_json(path, 32768)
    _schema(value, ('version', 'kind', 'data', 'source'), 'native export envelope')
    require(type(value['version']) is int and value['version'] == 1 and value['kind'] == 'native-ms1-crew',
            'native export envelope version/kind')
    proof = value['source']
    _schema(proof, ('trace_file', 'trace_sha256', 'record_index', 'install_plan_file',
                   'install_plan_sha256', 'outcome_file', 'outcome_sha256'), 'native export proof')
    artifacts, files = {}, {}
    for name, limit in (('trace', 4 * 1024 * 1024), ('install_plan', 1024 * 1024), ('outcome', 65536)):
        require(type(proof[name + '_file']) is str and 0 < len(proof[name + '_file']) <= 1024, 'proof path bound')
        files[name] = garage.local_file(proof[name + '_file'])
        artifacts[name] = read_limited(files[name], limit)
        require(digest(artifacts[name]) == _sha(proof[name + '_sha256'], name), 'native proof changed: ' + name)
    plan = _strict_evidence_json(artifacts['install_plan'], 1024 * 1024)
    outcome = _strict_evidence_json(artifacts['outcome'], 65536)
    directory = files['install_plan'].parent
    require(files['install_plan'].name == 'install-plan.json' and files['outcome'] == directory / 'native-outcome.json',
            'native proof does not identify the same prepared run')
    require(type(outcome) is dict and outcome.get('client_started') is True and type(outcome.get('exit_code')) is int
            and outcome['exit_code'] == 0 and outcome.get('exe_sha256') == EXE_SHA
            and outcome.get('timed_out') is False and outcome.get('client_alive') is False
            and outcome.get('restore') == 'PASS' and outcome.get('capture_status') == 'PASS'
            and outcome.get('process_status') == 'PASS' and type(outcome.get('harness_exit_code')) is int
            and outcome['harness_exit_code'] == 0 and outcome.get('plan_sha256') == proof['install_plan_sha256'],
            'native export process not clean')
    _, paths = config()
    require(type(plan) is dict and type(plan.get('schema_version')) is int and plan['schema_version'] == 1
            and plan.get('mode') == 'interactive' and type(plan.get('settings')) is dict,
            'native prepared plan schema')
    require(Path(plan['research_root']).resolve() == paths['research_client_root']
            and Path(plan['original_root']).resolve() == paths['original_client_root'], 'native plan client roots differ')
    trace_root = garage.local_file(plan['settings']['trace_dir'])
    pid = garage.bounded_int(outcome.get('client_pid'), 'actual native PID', 1)
    require(files['trace'].parent == trace_root and re.fullmatch(r'native-' + str(pid) + r'-[0-9]{10,16}\.jsonl',
            files['trace'].name), 'trace does not belong to the prepared native process')
    _validate_compiled_probe(plan, directory, outcome)
    lines = artifacts['trace'].splitlines()
    require(1 <= len(lines) <= 8192, 'native trace row bound')
    index = garage.bounded_int(proof['record_index'], 'trace index', 0, len(lines) - 1)
    events = [_strict_evidence_json(line, 65536) for line in lines]
    require(all(type(row) is dict for row in events), 'native trace row must be an object')
    exports = [i for i, row in enumerate(events) if row.get('event') == 'ms1_crew_descriptors']
    require(exports == [index] and not any(row.get('event') in ('ms1_crew_descriptors_error',
            'ms1_crew_observation_error', 'hangar_bootstrap_error') for row in events), 'native export missing/duplicated/failed')
    event = deepcopy(events[index])
    event.pop('event')
    elapsed = event.pop('elapsed_seconds', None)
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed < 86400, 'native marker timestamp')
    require(_same(event, value['data']), 'export is not exact type-sensitive observed native marker')
    _validate_native_crew_data(value['data'], paths)
    return value['data'], {'file': str(garage.local_file(path)), 'bytes': len(raw), 'sha256': digest(raw)}


def promote_profile(base, base_sha, export_sha, timestamp):
    garage.bounded_int(timestamp, 'crew grant timestamp', base['test_grant']['granted_at_ms'], 2147483647999)
    require(all(type(s) is str and re.fullmatch('[0-9a-f]{64}', s) for s in (base_sha, export_sha)), 'crew grant SHA256')
    value = deepcopy(base)
    value.update(profile_version=3, snapshot_revision=3)
    value['inventory'][0]['crew_assigned'] = True
    value['crew'] = [dict(crew_id=base['account_id'] + ':ms1-' + role + '-v1',
                         vehicle_inventory_id=base['account_id'] + ':starter-vehicle-v1',
                         role=role, role_level=100, skills=[]) for role in ROLES]
    value['crew_grant'] = dict(grant_id=GRANT_ID, granted_at_ms=timestamp,
                              base_profile_sha256=base_sha, native_export_sha256=export_sha)
    return value


def validate_profile(value, base, base_sha, export_sha):
    require(type(value) is dict and set(value) == PROFILE_FIELDS, 'exact profile3 fields required')
    grant = value['crew_grant']
    require(type(grant) is dict and set(grant) == {'grant_id', 'granted_at_ms', 'base_profile_sha256', 'native_export_sha256'},
            'crew grant schema differs')
    expected = promote_profile(base, base_sha, export_sha, grant['granted_at_ms'])
    # JSON type-sensitive equality rejects bool/int substitutions recursively.
    require(json.dumps(value, sort_keys=True) == json.dumps(expected, sort_keys=True), 'profile3 unauthorized delta')
    return value


def build(base, profile, data):
    trees = deepcopy(base['trees'])
    state = trees['state.bin']
    require(state['inventory'][8] == {'compDescr': {}} and state['inventory'][1]['crew'][1] == [None, None],
            'base has existing MS-1 crew; refusing replacement')
    require(state['inventory'][1]['crew'][2] == [None] * 5, 'IS-7 crew baseline differs')
    descriptors = {i + 1: bytes.fromhex(c['compact_descr_hex']) for i, c in enumerate(data['crew'])}
    state['inventory'][8] = {'compDescr': descriptors, 'vehicle': {1: 1, 2: 1}}
    state['inventory'][1]['crew'][1] = [1, 2]
    restored = deepcopy(state)
    restored['inventory'][8] = {'compDescr': {}}
    restored['inventory'][1]['crew'][1] = [None, None]
    restored_raw = legacy.encode_data(restored)
    require(restored_raw == base['payloads']['state.bin'], 'crew changed unrelated state')
    preservation = dict(status='PASS_LOCAL_INVARIANTS_ONLY', crew_grant=profile['crew_grant'],
        base_fixture={'directory': str(base['directory']), 'manifest_sha256': digest(base['manifest_raw'])},
        base_state_sha256=digest(base['payloads']['state.bin']), restored_state_sha256=digest(restored_raw),
        shop_sha256=digest(base['payloads']['shop.bin']), dossier_sha256=digest(base['payloads']['dossier.bin']),
        account_dossier_sha256=digest(state['stats']['dossier']),
        dossier_cache=deepcopy(base['manifest']['preservation']['dossier_cache']),
        delta=['inventory[8] two native tankmen assigned to vehicle1', 'inventory[1].crew[1]=[1,2]'],
        native_compatibility='NOT_RUN')
    model, compat = deepcopy(base['model']), deepcopy(base['compatibility'])
    model.update(fixture_version=3, profile_version=3, snapshot_revision=3, inventory=profile['inventory'],
                 crew=profile['crew'], crew_grant=profile['crew_grant'])
    compat['snapshot_revision'] = 3
    compat['crew_mapping'] = [dict(crew_id=c['crew_id'], native_inventory_id=i+1,
        native_vehicle_inventory_id=1, slot_index=i) for i, c in enumerate(profile['crew'])]
    return model, compat, trees, preservation


def generate(profile_path, base_fixture, native_crew, out):
    dependency = dependencies()
    base = validate_base(base_fixture)
    data, source = validate_export(native_crew)
    require(data['selection_before']['database_id'] == base['profile']['native_database_id'], 'native export account differs')
    profile, profile_raw = read_json(profile_path, 8192)
    validate_profile(profile, base['profile'], digest(base['profile_raw']), source['sha256'])
    model, compat, trees, preservation = build(base, profile, data)
    destination = garage.local_file(out, exists=False)
    require(not destination.exists(), 'immutable crew snapshot requires a new directory')
    payloads = {name: legacy.encode_data(value) for name, value in trees.items()}
    for name in ('shop.bin', 'dossier.bin'):
        require(payloads[name] == base['payloads'][name], 'crew modified preserved payload: ' + name)
    manifest = deepcopy(base['manifest'])
    manifest.update(fixture_version=3, profile_version=3, snapshot_revision=3, generator=dependency, preservation=preservation)
    inputs = {'profile-input.json': profile_raw, 'base-profile-input.json': base['profile_raw']}
    for key, filename in (('profile_source', 'profile-input.json'), ('base_profile_source', 'base-profile-input.json')):
        manifest[key] = {'file': filename, 'relative_to': 'fixture_directory', 'sha256': digest(inputs[filename])}
    manifest['native_descriptors']['crew'] = source
    manifest['files'] = [dict(file=name, bytes=len(raw), sha256=digest(raw),
                            opcodes=sorted({op.name for op, _, _ in pickletools.genops(raw)})) for name, raw in payloads.items()]
    require(len(manifest) == 16 and len(json.dumps(manifest).encode()) < 32768, 'native loader manifest bound')
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in {**inputs, **payloads}.items():
        with (destination / name).open('xb') as stream:
            stream.write(raw)
    for name, value in (('manifest.json', manifest), ('fixture.json', model), ('compatibility.json', compat),
            ('preservation.json', preservation), ('payloads.json', {k: legacy.json_tree(v) for k, v in trees.items()})):
        save_json(destination / name, value)
    return dict(output=str(destination), snapshot_revision=3, wire_sync_revision=1,
                compatibility_catalog_revision=3, files=manifest['files'], native_compatibility='NOT_RUN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    generate_parser = commands.add_parser('generate')
    for name in ('profile', 'base-fixture', 'native-crew', 'out'):
        generate_parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.profile, args.base_fixture, args.native_crew, args.out)))


if __name__ == '__main__':
    main()
