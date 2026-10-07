"""Immutable profile4: one explicit test_lab MS-1 ammunition grant.

Reads the exact accepted profile3 chain and an original-client export. It does
not modify the client, databases, previous fixtures or credential registry.
Only a measured mounted-gun tuple key extends the primitive pickle writer.
Encoding and local invariants are not evidence of native GUI compatibility.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import pickletools
import re
import struct

import ms1_crew_state as crew
import test_garage_state as garage
import hangar_state as legacy
from client_audit import config, read_limited, save_json, sha256
from verify_hangar import EXE_SHA

require = crew.require
digest = crew.digest
read_json = crew.read_json
CREW_GENERATOR_SHA = '40730f4c4c1a1d44c620577c58f40b757e9f1c891fb11ac9442ef1427bd1e810'
GRANT_ID = 'test-ms1-ammo-v1'
SHELL_ID = 'shell:ms1-stock-ap'
AMMO_COUNT = 20
MOUNTED_KEY = (5891, 5892)
SHELL_CDS = (2570, 2826, 3082)
LOADED = [2570, 20, 2826, 0, 3082, 0]
MAX_AMMO = 96
PROFILE_FIELDS = crew.PROFILE_FIELDS | {'ammunition', 'ammo_grant'}
MANIFEST_FIELDS = {'fixture_version', 'ruleset', 'profile_version', 'snapshot_revision',
    'wire_sync_revision', 'compatibility_catalog_revision', 'account_id', 'native_database_id',
    'profile_source', 'base_profile_source', 'native_descriptors', 'generator', 'files',
    'native_compatibility', 'preservation', 'grant'}


def dependencies():
    previous = crew.dependencies()
    require(previous['sha256'] == CREW_GENERATOR_SHA, 'frozen profile3 generator changed')
    return {'file': str(Path(__file__).resolve()), 'sha256': sha256(Path(__file__)),
            'base_generator': previous}


def validate_base(directory):
    """Reconstruct profile3 through its frozen generator and actual export."""
    directory = garage.local_file(directory)
    manifest, manifest_raw = read_json(directory / 'manifest.json')
    require(set(manifest) == MANIFEST_FIELDS, 'exact profile3 manifest fields required')
    versions = ('fixture_version', 'profile_version', 'snapshot_revision',
                'wire_sync_revision', 'compatibility_catalog_revision')
    require(all(type(manifest.get(k)) is int for k in versions)
            and tuple(manifest[k] for k in versions) == (3, 3, 3, 1, 3), 'exact r3-catalog3 base required')
    profile, profile_raw = read_json(directory / 'profile-input.json', 8192)
    origin, origin_raw = read_json(directory / 'base-profile-input.json', 8192)
    previous = crew.validate_base(manifest['preservation']['base_fixture']['directory'])
    require(origin_raw == previous['profile_raw'], 'profile3 prior profile bytes changed')
    data, source = crew.validate_export(manifest['native_descriptors']['crew']['file'])
    crew.validate_profile(profile, origin, digest(origin_raw), source['sha256'])
    require(data['selection_before']['database_id'] == profile['native_database_id'], 'profile3 native owner differs')
    model, compatibility, trees, preservation = crew.build(previous, profile, data)
    expected = deepcopy(previous['manifest'])
    expected.update(fixture_version=3, profile_version=3, snapshot_revision=3,
                    generator=crew.dependencies(), preservation=preservation)
    expected['native_descriptors']['crew'] = source
    for key, filename, raw in (('profile_source', 'profile-input.json', profile_raw),
                              ('base_profile_source', 'base-profile-input.json', origin_raw)):
        expected[key] = {'file': filename, 'relative_to': 'fixture_directory', 'sha256': digest(raw)}
    payloads = {name: legacy.encode_data(value) for name, value in trees.items()}
    expected['files'] = file_records(payloads)
    require(crew._same(manifest, expected), 'profile3 exact provenance/manifest changed')
    for name, raw in payloads.items():
        require(read_limited(directory / name, 16384) == raw, 'profile3 payload changed: ' + name)
        require(encode_data(trees[name]) == raw, 'new bounded encoder does not preserve profile3 bytes')
    for name, value in (('fixture.json', model), ('compatibility.json', compatibility),
                        ('preservation.json', preservation)):
        require(crew._same(read_json(directory / name)[0], value), 'profile3 metadata changed: ' + name)
    return dict(directory=directory, manifest=manifest, manifest_raw=manifest_raw,
                profile=profile, profile_raw=profile_raw, model=model, compatibility=compatibility,
                trees=trees, payloads=payloads)


def promote_profile(base, base_sha, export_sha, timestamp):
    require(type(base) is dict and set(base) == crew.PROFILE_FIELDS
            and type(base['profile_version']) is int and base['profile_version'] == 3
            and type(base['snapshot_revision']) is int and base['snapshot_revision'] == 3,
            'exact profile3 input required')
    previous = deepcopy(base)
    del previous['crew']; del previous['crew_grant']
    previous.update(profile_version=2, snapshot_revision=2)
    require(type(previous['inventory']) is list and len(previous['inventory']) == 2
            and previous['inventory'][0].get('crew_assigned') is True, 'assigned MS-1 crew required')
    previous['inventory'][0]['crew_assigned'] = False
    original = {key: previous[key] for key in garage.PROFILE_FIELDS}
    original.update(profile_version=1, snapshot_revision=1)
    garage.validate_profile(previous, original, previous['test_grant']['base_profile_sha256'])
    crew.validate_profile(base, previous, base['crew_grant']['base_profile_sha256'],
                          base['crew_grant']['native_export_sha256'])
    garage.bounded_int(timestamp, 'ammo grant timestamp', base['crew_grant']['granted_at_ms'], 2147483647999)
    crew._sha(base_sha, 'base profile3'); crew._sha(export_sha, 'native ammo export')
    require(type(base['inventory']) is list and len(base['inventory']) == 2
            and type(base['inventory'][0]['ammunition_count']) is int
            and base['inventory'][0]['ammunition_count'] == 0, 'refusing existing MS-1 ammunition')
    value = deepcopy(base)
    value.update(profile_version=4, snapshot_revision=4)
    value['inventory'][0]['ammunition_count'] = AMMO_COUNT
    value['ammunition'] = [{'vehicle_inventory_id': base['account_id'] + ':starter-vehicle-v1',
                           'shell_definition_id': SHELL_ID, 'count': AMMO_COUNT}]
    value['ammo_grant'] = dict(grant_id=GRANT_ID, granted_at_ms=timestamp,
                              base_profile_sha256=base_sha, native_export_sha256=export_sha)
    return value


def validate_profile(value, base, base_sha, export_sha):
    crew._schema(value, PROFILE_FIELDS, 'profile4')
    crew._schema(value['ammo_grant'], ('grant_id', 'granted_at_ms', 'base_profile_sha256',
                                    'native_export_sha256'), 'ammo grant')
    expected = promote_profile(base, base_sha, export_sha, value['ammo_grant']['granted_at_ms'])
    require(crew._same(value, expected), 'profile4 unauthorized delta')
    return value


def encode_data(value):
    """Protocol2 primitives; only the observed MS-1 shellsLayout tuple key.

    No constructors, object methods, imports, memo, unpickle or incoming code.
    Insertion order and opcodes match the frozen writer for its original domain.
    """
    output, active, nodes = bytearray(b'\x80\x02'), set(), 0

    def emit(raw):
        require(len(output) + len(raw) <= legacy.MAX_BYTES, 'pickle output bound')
        output.extend(raw)

    def visit(item, depth, path):
        nonlocal nodes
        nodes += 1
        require(nodes <= legacy.MAX_NODES and depth <= legacy.MAX_DEPTH, 'pickle node/depth bound')
        kind = type(item)
        if item is None:
            emit(b'N')
        elif kind is bool:
            emit(b'\x88' if item else b'\x89')
        elif kind is int:
            require(-(1 << 31) <= item < (1 << 31), 'signed32 fixture integer required')
            emit(b'K' + bytes([item]) if 0 <= item <= 255 else
                 b'M' + struct.pack('<H', item) if 0 <= item <= 65535 else b'J' + struct.pack('<i', item))
        elif kind is float:
            require(math.isfinite(item), 'finite fixture number required')
            emit(b'G' + struct.pack('>d', item))
        elif kind in (str, bytes):
            raw = item.encode('utf-8') if kind is str else item
            require(len(raw) <= legacy.MAX_BYTES, 'fixture string bound')
            emit((b'U' + bytes([len(raw)]) if len(raw) < 256 else b'T' + struct.pack('<I', len(raw))) + raw)
        elif kind in (dict, list, tuple):
            require(id(item) not in active and len(item) <= legacy.MAX_NODES, 'cyclic/oversized fixture container')
            active.add(id(item))
            if kind is dict:
                emit(b'}')
                if item:
                    emit(b'(')
                    seen = set()
                    for key, child in item.items():
                        if type(key) is tuple:
                            require(path == ('inventory', 1, 'shellsLayout', 1)
                                    and len(key) == 2 and all(type(x) is int for x in key)
                                    and key == MOUNTED_KEY, 'unmeasured tuple dictionary key')
                        else:
                            require(type(key) in (str, bytes, int), 'primitive dictionary key required')
                        wire = key.encode('utf-8') if type(key) is str else key
                        require(wire not in seen, 'dictionary keys collide in Python2')
                        seen.add(wire)
                        label = key.decode('ascii') if type(key) is bytes and key.isascii() else key
                        visit(key, depth + 1, path + ('<key>',))
                        visit(child, depth + 1, path + (label,))
                    emit(b'u')
            elif kind is list:
                emit(b']')
                if item:
                    emit(b'(')
                    for index, child in enumerate(item):
                        visit(child, depth + 1, path + (index,))
                    emit(b'e')
            elif not item:
                emit(b')')
            else:
                emit(b'(')
                for index, child in enumerate(item):
                    visit(child, depth + 1, path + (index,))
                emit(b't')
            active.remove(id(item))
        else:
            raise ValueError('fixture type is not a primitive')
    visit(value, 0, ())
    emit(b'.')
    return bytes(output)


def file_records(payloads):
    return [dict(file=name, bytes=len(raw), sha256=digest(raw),
                 opcodes=sorted({op.name for op, _, _ in pickletools.genops(raw)}))
            for name, raw in payloads.items()]


def build(base, profile, data):
    require(type(data.get('max_ammo')) is int and data['max_ammo'] == MAX_AMMO
            and [row['compact_descr'] for row in data['shells']] == list(SHELL_CDS)
            and tuple(data[name]['compact_descr'] for name in ('turret', 'gun')) == MOUNTED_KEY,
            'measured mounted ammunition contract required')
    trees = deepcopy(base['trees'])
    state = trees['state.bin']
    vehicles = state['inventory'][1]
    require(vehicles['shells'][1] == [] and vehicles['shellsLayout'][1] == {},
            'existing loaded ammunition/layout cannot be replaced')
    require(set(state['inventory']) == {1, 8}, 'unexpected inventory/storage shell state')
    vehicles['shells'][1] = list(LOADED)
    vehicles['shellsLayout'][1] = {MOUNTED_KEY: list(LOADED)}
    reversed_state = deepcopy(state)
    reversed_state['inventory'][1]['shells'][1] = []
    reversed_state['inventory'][1]['shellsLayout'][1] = {}
    reversed_raw = encode_data(reversed_state)
    require(reversed_raw == base['payloads']['state.bin'], 'ammo changed unrelated native state')
    preservation = dict(status='PASS_LOCAL_INVARIANTS_ONLY', ammo_grant=profile['ammo_grant'],
        base_fixture={'directory': str(base['directory']), 'manifest_sha256': digest(base['manifest_raw'])},
        base_state_sha256=digest(base['payloads']['state.bin']), restored_state_sha256=digest(reversed_raw),
        shop_sha256=digest(base['payloads']['shop.bin']), dossier_sha256=digest(base['payloads']['dossier.bin']),
        account_dossier_sha256=digest(state['stats']['dossier']),
        dossier_cache=deepcopy(base['manifest']['preservation']['dossier_cache']),
        delta=['inventory[1].shells[1]=[2570,20,2826,0,3082,0]',
               'inventory[1].shellsLayout[1][(5891,5892)]=[2570,20,2826,0,3082,0]'],
        native_compatibility='NOT_RUN')
    model, compat = deepcopy(base['model']), deepcopy(base['compatibility'])
    model.update(fixture_version=4, profile_version=4, snapshot_revision=4, inventory=profile['inventory'],
                 ammunition=profile['ammunition'], ammo_grant=profile['ammo_grant'])
    compat['snapshot_revision'] = 4
    compat['ammo_mapping'] = [dict(shell_definition_id=SHELL_ID, native_shell_compact_descr=2570,
        vehicle_inventory_id=profile['inventory'][0]['inventory_id'], native_vehicle_inventory_id=1,
        native_turret_compact_descr=MOUNTED_KEY[0], native_gun_compact_descr=MOUNTED_KEY[1])]
    return model, compat, trees, preservation


_schema = crew._schema
_sha = crew._sha
_same = crew._same
_strict_evidence_json = crew._strict_evidence_json
_relative_artifact = crew._relative_artifact


# Measured compiler output; native execution is a separate export gate.
PROBE_CHECKPOINTS = {
    '0cbc86441910931f29f6211dee93b997781a4d5681a98a9ea0b82c8d80237218':
    'ab2405800682418180372745c7872901b0dafa19ef86c554c96a8cd59cba9814',
}


NATIVE_AMMO_SOURCES = {'res/scripts/common/items/__init__.pyc': '587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176', 'res/scripts/common/items/vehicles.pyc': '805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6', 'res/scripts/common/account_shared.pyc': '187f914c508a359a0fa4f9cc4a0764080a9d71c9214a3b74e9f7ef72cfa6f65c', 'res/scripts/client/CurrentVehicle.pyc': 'a57c32ca6e84c2ae4c343bba3b88213680c65f3a28adb50d8009e0c9df833953', 'res/scripts/client/gui/shared/gui_items/Vehicle.pyc': 'ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8', 'res/scripts/client/gui/shared/gui_items/vehicle_modules.pyc': '8541c30f9258511e80decb3a5ed5545e59238343ae532e8112895b6539797c7b', 'res/scripts/client/gui/shared/utils/requesters/inventoryrequester.pyc': '4e2c79a4f826740b3363b14b00dba7aeaa9a539dc3c1b32671eb5256f4103e84', 'res/scripts/client/gui/shared/utils/requesters/itemsrequester.pyc': '41e5e9bacbb68e89202116bd267c6cd9fceeda4edb0ed605c7b87cc9315c0c44', 'res/scripts/client/gui/Scaleform/daapi/view/lobby/hangar/ammunitionpanel.pyc': '54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8', 'res/scripts/client/gui/Scaleform/daapi/view/meta/ammunitionpanelmeta.pyc': 'b8ff5d7e1f986ef9b8165703d42ec6f51f042a485d1004f7a1713eddb73a856a', 'res/scripts/item_defs/vehicles/ussr/ms-1.xml': 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535', 'res/scripts/item_defs/vehicles/ussr/components/guns.xml': '889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b', 'res/scripts/item_defs/vehicles/ussr/components/shells.xml': 'ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96'}


def _validate_compiled_probe(plan, directory, outcome):
    require(type(plan.get('sources')) is list and 1 <= len(plan['sources']) <= 16, 'prepared source list bound')
    rows = [r for r in plan['sources'] if type(r) is dict and r.get('path') == 'client_patch/ms1_ammo_probe.py']
    require(len(rows) == 1, 'one measured native ammo probe source required')
    row = rows[0]
    _schema(row, ('path', 'sha256', 'compiled', 'metadata'), 'prepared ammo source')
    require(row['sha256'] in PROBE_CHECKPOINTS, 'unmeasured native ammo producer source')
    compiled = _relative_artifact(directory, row['compiled'])
    metadata = _strict_evidence_json(read_limited(_relative_artifact(directory, row['metadata']), 8192), 8192)
    _schema(metadata, ('magic', 'source_sha256', 'source', 'pyc_sha256', 'source_executed', 'compiler'), 'compiled metadata')
    raw = read_limited(compiled, 256 * 1024)
    expected_pyc = PROBE_CHECKPOINTS[row['sha256']]
    require(len(raw) >= 8 and raw[:8] == bytes.fromhex('03f30d0a00000000')
            and digest(raw) == expected_pyc and metadata['pyc_sha256'] == expected_pyc
            and metadata['source_sha256'] == row['sha256'] and metadata['source'] == 'ms1_ammo_probe.py'
            and metadata['magic'] == '03f30d0a' and metadata['source_executed'] is False
            and type(metadata['compiler']) is str and metadata['compiler'].startswith('2.7.3 '),
            'prepared ammo bytecode/source chain differs')
    target = 'res_mods/0.9.1/scripts/client/ms1_ammo_probe.pyc'
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
    observed = [m for m in provenance['modules'] if type(m) is dict and m.get('module') == 'ms1_ammo_probe']
    require(len(observed) == 1 and observed[0] == {'module': 'ms1_ammo_probe',
            'source_sha256': row['sha256'], 'pyc_sha256': expected_pyc}, 'runtime probe provenance differs')



def validate_export(path):
    value, raw = read_json(path, 32768)
    _schema(value, ('version', 'kind', 'data', 'source'), 'native export envelope')
    require(type(value['version']) is int and value['version'] == 1 and value['kind'] == 'native-ms1-ammo',
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
    exports = [i for i, row in enumerate(events) if row.get('event') == 'ms1_ammo_descriptors']
    require(exports == [index] and not any(row.get('event') in ('ms1_ammo_descriptors_error',
            'ms1_ammo_observation_error', 'hangar_bootstrap_error') for row in events), 'native export missing/duplicated/failed')
    event = deepcopy(events[index])
    event.pop('event')
    elapsed = event.pop('elapsed_seconds', None)
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed < 86400, 'native marker timestamp')
    require(_same(event, value['data']), 'export is not exact type-sensitive observed native marker')
    _validate_native_ammo_data(value['data'], paths)
    return value['data'], {'file': str(garage.local_file(path)), 'bytes': len(raw), 'sha256': digest(raw)}


def _flat(value, name):
    require(type(value) is list and len(value) <= 6 and len(value) % 2 == 0, 'bounded ' + name)
    seen, total = set(), 0
    for index in range(0, len(value), 2):
        cd = garage.bounded_int(value[index], name + ' CD', -65535, 65535)
        amount = garage.bounded_int(value[index + 1], name + ' count', 0, MAX_AMMO)
        require(abs(cd) in SHELL_CDS and abs(cd) not in seen, 'foreign/duplicate shell in ' + name)
        seen.add(abs(cd)); total += amount
    require(total <= MAX_AMMO, 'native ammunition capacity exceeded')
    return value


def _validate_native_ammo_data(data, paths):
    _schema(data, ('version', 'type_name', 'type_id', 'vehicle_inventory_id', 'vehicle_type_compact_descr',
        'vehicle_compact_descr_sha256', 'turret', 'gun', 'max_ammo', 'shell_item_type', 'shells',
        'native_empty_ammo', 'native_default_ammo', 'observation', 'sources', 'selection_before',
        'selection_after', 'selection_unchanged', 'inventory_mutation_requested', 'loaded_module_files'),
        'native ammo data')
    for key, expected in (('version', 1), ('type_name', 'ussr:MS-1'), ('type_id', [0, 13]),
                          ('vehicle_inventory_id', 1), ('vehicle_type_compact_descr', 3329),
                          ('max_ammo', MAX_AMMO), ('shell_item_type', 10),
                          ('selection_unchanged', True), ('inventory_mutation_requested', False),
                          ('turret', {'resource_name': 'T-18_Standart', 'compact_descr': 5891}),
                          ('gun', {'resource_name': '_37mm_Gochkins', 'compact_descr': 5892})):
        require(_same(data[key], expected), 'native ammo type/policy differs: ' + key)
    _sha(data['vehicle_compact_descr_sha256'], 'MS-1 vehicle descriptor')
    for key in ('selection_before', 'selection_after'):
        row = data[key]
        _schema(row, ('database_id', 'selected_inventory_id', 'selected_descriptor_sha256'), 'native selection')
        garage.bounded_int(row['database_id'], 'native owner', 1)
        garage.bounded_int(row['selected_inventory_id'], 'selected inventory', 1, 2)
        _sha(row['selected_descriptor_sha256'], 'selected descriptor')
    require(_same(data['selection_before'], data['selection_after']), 'export changed native selection')
    require(_same(data['loaded_module_files'], {'vehicles': 'scripts/common/items/vehicles.pyc',
            'account_shared': 'scripts/common/account_shared.pyc'}), 'native original module path differs')
    require(type(data['sources']) is list and len(data['sources']) == len(NATIVE_AMMO_SOURCES), 'native ammo source count')
    seen, contents = set(), {}
    for row in data['sources']:
        _schema(row, ('relative_path', 'bytes', 'sha256'), 'ammo resource')
        relative = row['relative_path']
        require(type(relative) is str and relative in NATIVE_AMMO_SOURCES and relative not in seen,
                'unexpected/duplicate ammo resource')
        seen.add(relative)
        raw = read_limited(paths['original_client_root'] / relative, 1024 * 1024)
        garage.bounded_int(row['bytes'], 'original resource size', 1, 1024 * 1024)
        require(row['bytes'] == len(raw) and row['sha256'] == digest(raw) == NATIVE_AMMO_SOURCES[relative],
                'ammo resource differs from pinned original')
        contents[relative] = raw
    # Read the vehicle-specific override, not the shared 92-shell gun default.
    vehicle_xml = dict(garage.walk(garage.decode(contents['res/scripts/item_defs/vehicles/ussr/ms-1.xml'])))
    require(vehicle_xml['/turrets0[1]/T-18_Standart[1]/guns[1]/_37mm_Gochkins[1]/maxAmmo[1]'] == MAX_AMMO,
            'original mounted maxAmmo differs')
    require(type(data['shells']) is list and len(data['shells']) == 3, 'three native compatible shells required')
    definitions = (('_37mm_UBRT1', 10, 2570, 'ARMOR_PIERCING'),
                   ('_37mm_BPT1', 11, 2826, 'HOLLOW_CHARGE'),
                   ('_37mm_UOT1', 12, 3082, 'HIGH_EXPLOSIVE'))
    for row, (name, identifier, cd, kind) in zip(data['shells'], definitions):
        require(_same(row, {'resource_name': name, 'item_id': [0, identifier], 'compact_descr': cd,
                'kind': kind, 'compatible_with_mounted_gun': True}), 'native ordered shot/compatibility differs')
    require(_same(data['native_empty_ammo'], [2570, 0, 2826, 0, 3082, 0]), 'native empty ammo differs')
    default = _flat(data['native_default_ammo'], 'native default ammo')
    defaults = {abs(default[i]): (default[i + 1], default[i] < 0) for i in range(0, len(default), 2)}
    observation = data['observation']
    _schema(observation, ('raw_shells', 'raw_layouts', 'layout_index', 'mounted_layout_present',
        'storage_shells', 'gui_shells', 'native_loaded_pairs', 'native_layout_rows', 'ammo_sum',
        'default_ammo_sum', 'ammo_max_size', 'is_ammo_full', 'is_auto_load'), 'ammo observation')
    for key, expected in (('raw_shells', []), ('raw_layouts', []), ('layout_index', list(MOUNTED_KEY)),
                          ('mounted_layout_present', False), ('storage_shells', []), ('native_loaded_pairs', []),
                          ('ammo_sum', 0), ('ammo_max_size', MAX_AMMO), ('is_ammo_full', False), ('is_auto_load', False),
                          ('native_layout_rows', [[abs(default[i]), default[i+1], default[i] < 0]
                                                  for i in range(0, len(default), 2)]),
                          ('default_ammo_sum', sum(default[1::2]))):
        require(_same(observation[key], expected), 'native pre-grant observation differs: ' + key)
    require(type(observation['gui_shells']) is list and len(observation['gui_shells']) == 3,
            'three actual GUI shells required')
    for row, (_, _, cd, kind) in zip(observation['gui_shells'], definitions):
        _schema(row, ('compact_descr', 'kind', 'count', 'default_count', 'is_bought_for_credits',
                     'default_layout_value', 'inventory_count', 'buy_price', 'default_price'), 'native GUI shell')
        count, flag = defaults.get(cd, (0, False))
        for key, expected in (('compact_descr', cd), ('kind', kind), ('count', 0), ('default_count', count),
                              ('is_bought_for_credits', flag), ('default_layout_value', [-cd if flag else cd, count]),
                              ('inventory_count', 0), ('buy_price', [0, 0])):
            require(_same(row[key], expected), 'native GUI shell disagrees with raw inventory/defaults')
        require(type(row['default_price']) is list and len(row['default_price']) == 2, 'native reference pair required')
        for price in row['default_price']:
            garage.bounded_int(price, 'native reference price')


def generate(profile_path, base_fixture, native_ammo, out):
    dependency = dependencies()
    base = validate_base(base_fixture)
    data, source = validate_export(native_ammo)
    selection = data['selection_before']
    require(selection['database_id'] == base['profile']['native_database_id'], 'native ammo export owner differs')
    descriptors = base['trees']['state.bin']['inventory'][1]['compDescr']
    require(data['vehicle_compact_descr_sha256'] == digest(descriptors[1])
            and selection['selected_descriptor_sha256'] == digest(descriptors[selection['selected_inventory_id']]),
            'native export descriptor differs from exact base')
    profile, profile_raw = read_json(profile_path, 8192)
    validate_profile(profile, base['profile'], digest(base['profile_raw']), source['sha256'])
    model, compat, trees, preservation = build(base, profile, data)
    payloads = {name: encode_data(value) for name, value in trees.items()}
    for name in ('shop.bin', 'dossier.bin'):
        require(payloads[name] == base['payloads'][name], 'ammo modified preserved payload: ' + name)
    manifest = deepcopy(base['manifest'])
    manifest.update(fixture_version=4, profile_version=4, snapshot_revision=4,
                    generator=dependency, preservation=preservation)
    inputs = {'profile-input.json': profile_raw, 'base-profile-input.json': base['profile_raw']}
    for key, filename in (('profile_source', 'profile-input.json'), ('base_profile_source', 'base-profile-input.json')):
        manifest[key] = {'file': filename, 'relative_to': 'fixture_directory', 'sha256': digest(inputs[filename])}
    manifest['native_descriptors']['ammo'] = source
    manifest['files'] = file_records(payloads)
    require(set(manifest) == MANIFEST_FIELDS and len(manifest) == 16
            and len(json.dumps(manifest).encode()) < 32768, 'native loader manifest bound')
    destination = garage.local_file(out, exists=False)
    require(not destination.exists(), 'immutable ammunition snapshot requires a new directory')
    destination.mkdir(parents=True, exist_ok=False)
    for name, raw in {**inputs, **payloads}.items():
        with (destination / name).open('xb') as stream:
            stream.write(raw)
    for name, value in (('manifest.json', manifest), ('fixture.json', model), ('compatibility.json', compat),
                       ('preservation.json', preservation),
                       ('payloads.json', {k: legacy.json_tree(v) for k, v in trees.items()})):
        save_json(destination / name, value)
    return dict(output=str(destination), snapshot_revision=4, wire_sync_revision=1,
                compatibility_catalog_revision=3, files=manifest['files'], native_compatibility='NOT_RUN')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    generate_parser = commands.add_parser('generate')
    for name in ('profile', 'base-fixture', 'native-ammo', 'out'):
        generate_parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.profile, args.base_fixture, args.native_ammo, args.out)))


if __name__ == '__main__':
    main()

