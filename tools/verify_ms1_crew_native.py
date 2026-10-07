"""Independent snapshot3 crew evidence gate; never mutates a client or database.

The only pickle interpreter is the bounded, primitive-only existing wire reader.
Neither client code nor a state generator is imported or executed. Native pixels
and manual human input are separate from callback and PNG-container evidence.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import struct
import zlib

import verify_unified_entry as entry
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table
from verify_hangar import (ACCOUNT_RETURNS, ENTITY_ID, EXE_SHA, HEADER_RETURNS,
                           digest, literal, local_file, original_contracts, require, same_literal)
from verify_hangar_ui import entry_mode, module_policy_evidence, native_error_events

VERSION = 1
MODULES = ('sr_interactive', 'project_auth', 'project_preferences', 'hangar_bootstrap',
           'hangar_ui_probe', 'hangar_capabilities', 'crew_capabilities', 'ms1_crew_probe')
STAGES = ('music', 'messenger', 'post_processing', 'native_entities', 'native_spaces',
          'gui_personality', 'crew_capabilities', 'module_capabilities',
          'area_destructibles', 'vibration', 'battle_replay', 'predefined_hosts')
CREW = (
    ('commander', '080d0164000000010001000100410600000000420000000000',
     'Александр', 'Иванов', ['commander', 'gunner', 'radioman', 'loader']),
    ('driver', '080d0364000000020002000200410600000000420000000000',
     'Алексей', 'Петров', ['driver']),
)
CREW_SOURCES = (
    ('scripts/client/gui/Scaleform/daapi/view/meta/CrewMeta.py',
     'e3bbd2ef7ef897c7fb8d9f19f8f82f5c4c55a4ff3efe685fada0ba86aaeee22a',
     'as_tankmenResponseS', 59, 30),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/hangar/Crew.py',
     '8defb03050f4d903d40e466e11fed0b04c368f8fc0450263316e0b768edba136',
     'updateTankmen', 42, 1066),
)
GENERATOR_SHA = '40730f4c4c1a1d44c620577c58f40b757e9f1c891fb11ac9442ef1427bd1e810'
DEFAULT_REG = ROOT / 'local/evidence/20261004-p02-unified-account/operator-email-binding-01'


def same(a, b, message):
    require(same_literal(a, b), message)


def checked(function):
    try:
        return function()
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        # Never copy arbitrary error payloads: filesystem/JSON/crypto failures
        # can contain credential-bearing input. The phase identifies the gate.
        return {'status': 'FAIL', 'error_type': type(error).__name__,
                'reason': str(error) if type(error) is ValueError and not isinstance(error, json.JSONDecodeError)
                else 'Malformed, missing or inconsistent bounded evidence'}


def status(checks):
    values = [x.get('status') for x in checks.values()]
    return 'FAIL' if 'FAIL' in values else 'NOT_RUN' if 'NOT_RUN' in values else 'PASS'


def read_json(path, maximum=262144):
    value = entry.json_data(read_limited(path, maximum))
    budget = [100000]
    def walk(item, depth):
        budget[0] -= 1
        require(depth <= 24 and budget[0] >= 0, 'JSON depth/node bound')
        if type(item) is dict:
            require(all(type(k) is str for k in item), 'JSON object keys')
            for child in item.values():
                walk(child, depth + 1)
        elif type(item) is list:
            for child in item:
                walk(child, depth + 1)
        else:
            require(type(item) in (str, int, float, bool, type(None)), 'JSON primitive shape')
    walk(value, 0)
    return value


def compiled_sources(install, plan, outcome, scenario=None):
    sources = plan.get('sources')
    require(type(sources) is list and len(sources) in (8, 9), 'expected eight/nine versioned modules')
    names = [r.get('path') for r in sources]
    wanted = {'client_patch/' + n + '.py' for n in MODULES}
    if len(sources) == 9:
        wanted.add('client_patch/ms1_crew_scenario.py')
    require(set(names) == wanted and len(names) == len(set(names)), 'unknown/missing/duplicate compiled module')
    if scenario is True:
        require(len(sources) == 9, 'crew scenario module missing')
    evidence = []
    for source in sources:
        name = Path(source['path']).stem
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        compiled = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        matches = [r for r in plan['files'] if r.get('path') == relative]
        require(len(matches) == 1 and matches[0].get('runtime_mutable') is False, 'compiled install identity')
        require(meta.get('source') == name + '.py' and meta.get('source_sha256') == source.get('sha256')
                and re.fullmatch('[0-9a-f]{64}', source.get('sha256', '')) is not None
                and meta.get('source_executed') is False and meta.get('magic') == '03f30d0a'
                and meta.get('compiler', '').startswith('2.7.3 '), 'compiler metadata/source chain')
        sha = digest(compiled)
        require(compiled[:4] == bytes.fromhex('03f30d0a') and sha == meta.get('pyc_sha256')
                == matches[0].get('installed_sha256'), 'compiled byte/hash chain')
        require(local_file(install, 'postrun/' + relative, 1024 * 1024) == compiled, 'runtime compiled source changed')
        evidence.append({'module': name, 'source_sha256': source['sha256'], 'pyc_sha256': sha})
    same(outcome.get('source_provenance', {}).get('modules'), evidence, 'runner/compiler provenance mismatch')
    return {'status': 'PASS', 'modules': evidence,
            'scope': 'Frozen compiler, install, postrun and runner chain; no requirement that current source files remain the same.'}


def export_evidence(path, local_root):
    raw = read_limited(path, 65536)
    value = entry.json_data(raw)
    require(set(value) == {'version', 'kind', 'data', 'source'} and type(value['version']) is int
            and value['version'] == 1 and value['kind'] == 'native-ms1-crew', 'native export envelope')
    proof, data = value['source'], value['data']
    refs = {}
    for key in ('trace', 'install_plan', 'outcome'):
        refs[key] = entry.owned(proof[key + '_file'], local_root)
        require(digest(read_limited(refs[key], 17 * 1024 * 1024)) == proof[key + '_sha256'], 'native export proof hash')
    plan = read_json(refs['install_plan'], 1024 * 1024)
    outcome = read_json(refs['outcome'])
    require(refs['outcome'].parent == refs['install_plan'].parent and outcome.get('plan_sha256') == proof['install_plan_sha256']
            and outcome.get('client_started') is True and outcome.get('exit_code') == 0
            and outcome.get('timed_out') is False and outcome.get('restore') == 'PASS'
            and outcome.get('exe_sha256') == EXE_SHA, 'native export actual process proof')
    install = refs['install_plan'].parent
    compiled_sources(install, plan, outcome)
    rows, trace_info = entry.runtime_rows(install, plan, outcome, local_root)
    require(Path(trace_info['path']).resolve() == refs['trace'], 'native export trace path')
    index = proof['record_index']
    require(type(index) is int and 0 <= index < len(rows), 'native export record index')
    record = dict(rows[index])
    require(record.pop('event') == 'ms1_crew_descriptors', 'native export record kind')
    record.pop('elapsed_seconds')
    same(record, data, 'native export differs from original runtime record')
    require(data.get('inventory_mutation_requested') is False and data.get('selection_unchanged') is True
            and data['selection_before'] == data['selection_after'] and data.get('version') == 1
            and data.get('type_name') == 'ussr:MS-1' and data.get('vehicle_type_compact_descr') == 3329
            and data.get('tankman_item_type') == 8 and data.get('tankman_dossier_hex') == '420000000000', 'native export scope')
    require(type(data.get('crew')) is list and len(data['crew']) == 2, 'native export crew count')
    for index, (role, hexadecimal, _, _, combined) in enumerate(CREW):
        item = data['crew'][index]
        require(item['slot_index'] == index and item['role'] == role and item['combined_roles'] == combined
                and item['compact_descr_hex'] == hexadecimal and item['compact_descr_bytes'] == 25
                and item['compact_descr_sha256'] == digest(bytes.fromhex(hexadecimal))
                and item['original_parse_repack_equal'] is True and item['original_dossier_repack_equal'] is True,
                'native measured compact/role mismatch')
        decoded = item['decoded']
        for key, expected in {'nation_id': 0, 'vehicle_type_id': 13, 'role': role, 'role_level': 100,
                              'free_xp': 0, 'skills': [], 'last_skill_level': 0,
                              'is_premium': False, 'is_female': False, 'total_xp': 105030}.items():
            same(decoded.get(key), expected, 'native measured training descriptor mismatch')
    originals = config()[1]['original_client_root']
    require(type(data.get('sources')) is list and len(data['sources']) == 9, 'original crew source count')
    for source in data['sources']:
        source_raw = local_file(originals, source['relative_path'], 1024 * 1024)
        require(len(source_raw) == source['bytes'] and digest(source_raw) == source['sha256'], 'original crew source hash')
    return value, {'status': 'PASS', 'file': str(path), 'sha256': digest(raw), 'trace_sha256': proof['trace_sha256'],
                   'original_sources': data['sources'], 'native_compatibility': 'Original constructor export only; delivery checked separately.'}


def profile_delta(base_raw, profile, export_sha):
    base = entry.json_data(base_raw)
    require(base.get('profile_version') == base.get('snapshot_revision') == 2, 'expected immutable profile2 baseline')
    grant = profile.get('crew_grant')
    require(type(grant) is dict and set(grant) == {'grant_id', 'granted_at_ms', 'base_profile_sha256', 'native_export_sha256'}
            and grant['grant_id'] == 'test-ms1-crew-v1' and type(grant['granted_at_ms']) is int
            and base['test_grant']['granted_at_ms'] <= grant['granted_at_ms'] <= 4102444800000
            and grant['base_profile_sha256'] == digest(base_raw) and grant['native_export_sha256'] == export_sha,
            'crew grant identity/provenance')
    wanted = copy.deepcopy(base)
    wanted.update(profile_version=3, snapshot_revision=3, crew_grant=grant)
    wanted['inventory'][0]['crew_assigned'] = True
    account = base['account_id']
    wanted['crew'] = [{'crew_id': account + ':ms1-' + role + '-v1',
                      'vehicle_inventory_id': account + ':starter-vehicle-v1',
                      'role': role, 'role_level': 100, 'skills': []} for role, *_ in CREW]
    same(profile, wanted, 'profile3 contains a forbidden identity/progress/inventory delta')
    return base


def state_delta(before, after, export):
    same(before[b'inventory'][8], {b'compDescr': {}}, 'base tankman inventory is not empty')
    same(before[b'inventory'][1][b'crew'][1], [None, None], 'base MS1 crew is not empty')
    wanted = copy.deepcopy(before)
    wanted[b'inventory'][8] = {b'compDescr': {i + 1: bytes.fromhex(r['compact_descr_hex'])
                                          for i, r in enumerate(export['data']['crew'])}, b'vehicle': {1: 1, 2: 1}}
    wanted[b'inventory'][1][b'crew'][1] = [1, 2]
    same(after, wanted, 'wire state changed beyond two assigned native tankmen')
    same(after[b'inventory'][1][b'crew'][2], [None] * 5, 'IS7 crew changed')
    return {'status': 'PASS', 'native_tankman_ids': [1, 2], 'native_vehicle_id': 1,
            'compact_sha256': [digest(bytes.fromhex(r['compact_descr_hex'])) for r in export['data']['crew']]}


def crew_fixture(directory, export, export_report, local_root):
    manifest_raw = local_file(directory, 'manifest.json', 262144)
    manifest = entry.json_data(manifest_raw)
    require(set(manifest) == {'fixture_version', 'ruleset', 'profile_version', 'snapshot_revision',
        'wire_sync_revision', 'compatibility_catalog_revision', 'account_id', 'native_database_id',
        'profile_source', 'base_profile_source', 'native_descriptors', 'generator', 'files',
        'native_compatibility', 'preservation', 'grant'}, 'snapshot3 manifest schema')
    for key, value in {'fixture_version': 3, 'profile_version': 3, 'snapshot_revision': 3,
                       'wire_sync_revision': 1, 'compatibility_catalog_revision': 3, 'ruleset': 'test_lab'}.items():
        same(manifest.get(key), value, 'manifest version/scope mismatch')
    require(manifest['generator']['sha256'] == GENERATOR_SHA, 'unreviewed crew generator version')
    preservation = manifest['preservation']
    base_dir = entry.owned(preservation['base_fixture']['directory'], local_root, directory=True)
    base_manifest_raw = local_file(base_dir, 'manifest.json', 262144)
    base_manifest = entry.json_data(base_manifest_raw)
    require(digest(base_manifest_raw) == preservation['base_fixture']['manifest_sha256'], 'base manifest hash')
    profile_raw = local_file(directory, 'profile-input.json', 65536)
    profile, base_raw = entry.json_data(profile_raw), local_file(directory, 'base-profile-input.json', 65536)
    same(base_raw, local_file(base_dir, 'profile-input.json', 65536), 'immutable profile2 bytes differ')
    profile_delta(base_raw, profile, export_report['sha256'])
    for key, filename, raw in [('profile_source', 'profile-input.json', profile_raw),
                               ('base_profile_source', 'base-profile-input.json', base_raw)]:
        same(manifest[key], {'file': filename, 'relative_to': 'fixture_directory', 'sha256': digest(raw)}, 'manifest profile provenance')
    same(manifest['grant'], profile['test_grant'], 'existing IS7 grant changed')
    require(manifest['account_id'] == base_manifest['account_id'] == profile['account_id']
            and type(profile['native_database_id']) is int and 1 <= profile['native_database_id'] <= 2147483647
            and manifest['native_database_id'] == base_manifest['native_database_id'] == profile['native_database_id'], 'fixture identity')
    same(manifest['native_descriptors']['crew'], {'file': export_report['file'],
         'bytes': len(read_limited(Path(export_report['file']), 65536)), 'sha256': export_report['sha256']}, 'crew export provenance')
    descriptors = dict(manifest['native_descriptors'])
    descriptors.pop('crew')
    same(descriptors, base_manifest['native_descriptors'], 'old vehicle source provenance changed')
    files, raw, old_raw = manifest['files'], {}, {}
    require(type(files) is list and [r.get('file') for r in files] == ['state.bin', 'shop.bin', 'dossier.bin'], 'payload manifest rows')
    for row in files:
        name = row['file']
        raw[name] = local_file(directory, name, 16384)
        old_raw[name] = local_file(base_dir, name, 16384)
        require(len(raw[name]) == row['bytes'] and digest(raw[name]) == row['sha256'], 'payload file hash/size')
        old_rows = [r for r in base_manifest['files'] if r['file'] == name]
        require(len(old_rows) == 1 and digest(old_raw[name]) == old_rows[0]['sha256'], 'base payload file hash')
    state, old_state = literal(raw['state.bin']), literal(old_raw['state.bin'])
    delta = state_delta(old_state, state, export)
    for name in ('shop.bin', 'dossier.bin'):
        same(raw[name], old_raw[name], 'existing shop/dossier bytes changed')
        require(preservation[name.split('.')[0] + '_sha256'] == digest(raw[name]), 'preserved payload hash')
    require(preservation['base_state_sha256'] == preservation['restored_state_sha256'] == digest(old_raw['state.bin'])
            and preservation['account_dossier_sha256'] == digest(state[b'stats'][b'dossier']), 'preserved account/state hashes')
    same(preservation['crew_grant'], profile['crew_grant'], 'preservation grant mismatch')
    same(preservation['dossier_cache'], base_manifest['preservation']['dossier_cache'], 'dossier cursor changed')
    compatibility = entry.json_data(local_file(directory, 'compatibility.json', 65536))
    old_compat = entry.json_data(local_file(base_dir, 'compatibility.json', 65536))
    wanted = copy.deepcopy(old_compat)
    wanted.update(snapshot_revision=3, crew_mapping=[{'crew_id': r['crew_id'], 'native_inventory_id': i + 1,
                  'native_vehicle_inventory_id': 1, 'slot_index': i} for i, r in enumerate(profile['crew'])])
    same(compatibility, wanted, 'compatibility mapping changed beyond crew')
    require(compatibility['client_name'] == profile['username'], 'fixture nickname mismatch')
    expected = {'manifest': manifest, 'manifest_sha256': digest(manifest_raw), 'profile': profile,
                'profile_sha256': digest(profile_raw), 'account_id': profile['account_id'], 'name': profile['username'],
                'native_id': profile['native_database_id'], 'raw': raw, 'state': state,
                'resources': profile['resources'], 'dossier_cache': compatibility['dossier_cache'],
                'export': export, 'fixture': str(directory)}
    return expected, {'status': 'PASS', 'fixture': str(directory), 'manifest_sha256': digest(manifest_raw),
        'profile_sha256': digest(profile_raw), 'base_fixture': str(base_dir), 'base_profile_sha256': digest(base_raw),
        'account_id': profile['account_id'], 'native_database_id': profile['native_database_id'], 'nickname': profile['username'],
        'payloads': {k: {'bytes': len(v), 'sha256': digest(v)} for k, v in raw.items()}, 'literal_delta': delta,
        'resources': profile['resources'], 'statistics': profile['statistics'], 'dossier_cache': compatibility['dossier_cache']}


def identity(expected, registration_path, credentials_path, case):
    registration_raw = read_limited(registration_path, 65536)
    registration = entry.json_data(registration_raw)
    require(registration.get('status') == 'PASS', 'registration evidence failed')
    users = [r for r in registration.get('users', []) if r.get('case') == case]
    require(len(users) == 1, 'registration case ambiguity')
    user = users[0]
    require(user.get('registration') == user.get('web_login') == 'PASS'
            and user.get('account_id') == expected['account_id'] and user.get('nickname') == expected['name'], 'website account identity')
    email = entry.canonical_email(user['email'])
    require(email == user['email'], 'registration email is not canonical')
    private = entry.read_json(credentials_path, 65536)
    require(type(private) is list and 1 <= len(private) <= 16, 'private credential record count')
    matches = [r for r in private if r.get('case') == case]
    require(len(matches) == 1 and entry.canonical_email(matches[0].get('email')) == email
            and matches[0].get('nickname') == expected['name'], 'private registration binding')
    password = matches[0].get('password')
    require(type(password) is str and 15 <= len(password) <= 128 and len(password.encode('utf8')) <= 512, 'private credential bound')
    expected['login'] = email
    return password.encode('utf8'), {'status': 'PASS', 'registration_file': str(registration_path),
           'registration_sha256': digest(registration_raw), 'credentials_file': str(credentials_path),
           'account_id': expected['account_id'], 'native_database_id': expected['native_id'], 'nickname': expected['name'],
           'case': case, 'secret_values_and_hashes_recorded': False}


def original_crew_contracts():
    common = original_contracts()
    opcode = read_limited(ROOT / 'local/vendor/cpython-2.7.18/opcode.py', 32768)
    table, originals, evidence = opcode_table(opcode.decode('utf8')), config()[1]['original_client_root'], []
    for source, sha, method, line, offset in CREW_SOURCES:
        path = originals / 'res' / (source + 'c')
        raw = read_limited(path, 1024 * 1024)
        require(digest(raw) == sha, 'original crew source hash')
        records = [r for r in inspect(raw, table) if r['qualified_name'].split('.')[-1] == method and r['firstlineno'] == line]
        require(len(records) == 1, 'original crew function identity')
        instructions = records[0]['instructions']
        matching = [i for i, op in enumerate(instructions) if op['offset'] == offset]
        require(len(matching) == 1 and instructions[matching[0]]['opname'] == 'RETURN_VALUE', 'original crew normal return')
        if method == 'as_tankmenResponseS':
            require(instructions[matching[0] - 1]['opname'] == 'CALL_FUNCTION'
                    and any(op.get('value') == 'flashObject' for op in instructions[:matching[0]]), 'original crew Flash branch')
        evidence.append({'file': str(path), 'sha256': sha, 'method': method, 'line': line, 'return_offset': offset})
    return {'status': 'PASS', 'crew_sources': evidence, 'account_and_header_sources': common}


def runtime_common(install, plan, outcome, rows):
    checks = {}
    def gate(name, value, **detail):
        checks[name] = {'status': 'PASS' if value else 'FAIL', **detail}
    checks['entry_mode'] = checked(lambda: entry_mode(plan, rows, 'controlled'))
    checks['legacy_service_dialog_policy'] = checked(lambda: entry.legacy_dialog_policy(install, plan))
    init = [r for r in rows if r['event'] == 'init']
    gate('native_runtime', len(init) == 1 and init[0].get('sys_version', '').startswith('2.7.3 ')
         and init[0].get('pointer_bytes') == 4 and init[0].get('personality') == 'sr_interactive'
         and init[0].get('endpoint') == '127.0.0.1:20014')
    logins = [r for r in rows if r['event'] == 'native_login' and r.get('ready') is True]
    gate('original_login_view', bool(logins) and all(r.get('class_name') == 'LoginView'
         and r.get('flash_bound') is True and r.get('alias') == 'login' for r in logins))
    old_path = install / 'backup/python.log'
    old = read_limited(old_path, 16 * 1024 * 1024) if old_path.exists() else b''
    log_entry = [r for r in plan['files'] if r['path'] == 'python.log']
    require(len(log_entry) == 1 and log_entry[0].get('before_sha256') == (digest(old) if old_path.exists() else None), 'python.log baseline hash')
    fresh, bad, ignored = entry.fresh_python_log(old, local_file(install, 'postrun/python.log', 16 * 1024 * 1024))
    errors = native_error_events(rows)
    gate('native_errors', not errors and not bad, trace_error_count=len(errors), trace_errors=errors[:256],
         fresh_log_error_count=len(bad), fresh_log_errors=bad[:256], fresh_log_sha256=digest(fresh), ignored_baseline_bytes=ignored,
         scope='Locations only; arbitrary error contents are not copied.')
    begin = [i for i, r in enumerate(rows) if r['event'] == 'fini_enter']
    finish = [i for i, r in enumerate(rows) if r['event'] == 'fini']
    repository = [i for i, r in enumerate(rows) if r['event'] == 'account_repository_closed']
    cleanup = [(i, r) for i, r in enumerate(rows) if r['event'] == 'hangar_cleanup']
    exact = len(begin) == len(finish) == len(repository) == 1
    gate('engine_cleanup', exact and begin[0] < repository[0] < finish[0]
         and [r.get('stage') for _, r in cleanup] == list(STAGES)
         and all(begin[0] < i < repository[0] and r.get('outcome') == 'PASS' for i, r in cleanup),
         expected_stages=list(STAGES), observed_stages=[r.get('stage') for _, r in cleanup])
    restore = read_json(install / 'restore.json', 2 * 1024 * 1024)
    gate('process_restore', outcome.get('client_started') is True and type(outcome.get('exit_code')) is int
         and outcome['exit_code'] == 0 and outcome.get('timed_out') is False
         and outcome.get('forced_stop', False) is False and not outcome.get('capture_error')
         and outcome.get('exe_sha256') == EXE_SHA and outcome.get('restore') == restore.get('status') == 'PASS'
         and outcome.get('stop_method') == 'native_exit' and outcome.get('client_alive') is False,
         exit_code=outcome.get('exit_code'), timed_out=outcome.get('timed_out'), restore=restore.get('status'))
    unchanged = []
    for row in plan['files']:
        if row.get('runtime_mutable') is False:
            raw = local_file(install, 'postrun/' + row['path'], 4 * 1024 * 1024)
            unchanged.append({'path': row['path'], 'sha256': digest(raw), 'matches': digest(raw) == row['installed_sha256']})
    gate('installed_files_unchanged', bool(unchanged) and all(r['matches'] for r in unchanged), files=unchanged)
    callbacks = [r for r in rows if r['event'] == 'connection_callback']
    connected = [r for r in callbacks if r.get('stage') == 1 and r.get('status') == 'LOGGED_ON'
                 and r.get('native_connected') is True and r.get('after_fini') is False]
    gate('connection_until_fini', len(connected) == 1 and exact
         and [r for r in callbacks if r['elapsed_seconds'] < rows[begin[0]]['elapsed_seconds']] == connected
         and all(r.get('original_callback') == 'ConnectionManager.connectionWatcher' for r in callbacks), callbacks=callbacks)
    return {'status': status(checks), 'checks': checks}


def pairs(rows, event, method, source, line, offset, require_bound=False):
    selected = [(i, r) for i, r in enumerate(rows) if r['event'] == event and r.get('method') == method]
    require(len(selected) % 2 == 0 and len(selected) <= 4096, 'callback pair count/budget')
    pending, completed = {}, []
    for index, row in selected:
        require(row.get('source') == source and row.get('source_line') == line, 'callback source identity')
        call_id = row.get('call_id')
        require(type(call_id) is int and call_id > 0, 'callback call identity')
        if require_bound:
            require(row.get('flash_bound') is True and type(row.get('owner_id')) is int, 'original Flash owner is unbound')
        if row.get('phase') == 'call':
            require(call_id not in pending and not any(p[1]['call_id'] == call_id for p in completed), 'duplicate callback identity')
            pending[call_id] = (index, row)
        else:
            require(row.get('phase') == 'return' and call_id in pending and row.get('offset') == offset, 'callback lacks normal return')
            start, call = pending.pop(call_id)
            require(call.get('owner_id') == row.get('owner_id'), 'callback owner changed')
            completed.append((start, call, index, row))
    require(not pending, 'unterminated callback')
    return completed


def native_account(rows, wire, expected):
    calls = [r for r in rows if r['event'] == 'native_account_call']
    application = wire['application']
    require(all(any(r.get('source') == 'scripts/client/Account.py' and r.get('method') == method
                    and r.get('source_line') == line and r.get('offset') == offset and r.get('phase') == 'return' for r in calls)
                for method, line, offset in ACCOUNT_RETURNS), 'original Account lifecycle normal returns missing')
    players = [r for r in rows if r['event'] == 'native_player' and r.get('database_id') is not None]
    require(players and all(r.get('class_name') == 'PlayerAccount' and r.get('entity_id') == ENTITY_ID
                           and r.get('database_id') == expected['native_id'] and r.get('name') == expected['name'] for r in players), 'native Account identity')
    rpc = pairs(rows, 'native_account_call', 'onCmdResponseExt', 'scripts/client/Account.py', 302, 119)
    target = {r['request']: r['result'] for r in application['responses']}
    require(len(rpc) == len(target) and {r['requestID']: r['resultID'] for _, _, _, r in rpc} == target, 'wire/native RPC result correlation')
    stream_pairs = pairs(rows, 'native_account_call', 'onStreamComplete', 'scripts/client/Account.py', 351, 255)
    stream_events = [r for r in rows if r['event'] == 'native_stream']
    require(len(stream_pairs) == len(stream_events) == len(application['streams']) == 3, 'three native resource streams required')
    for stream in application['streams']:
        matching = [p for p in stream_pairs if p[1].get('stream_id') == stream['id']]
        events = [r for r in stream_events if r.get('stream_id') == stream['id']]
        require(len(matching) == len(events) == 1, 'native stream identity')
        same(matching[0][1].get('integrity'), [False, stream['bytes'], stream['bytes'],
                                           stream['crc32_signed'], stream['crc32_signed']], 'native stream CRC/size integrity')
        require(events[0].get('bytes') == stream['bytes'] and events[0].get('description_bytes') == len(bytes.fromhex(stream['description_hex']))
                and stream['raw_sha256'] == digest(expected['raw'][stream['fixture']]), 'native delivered stream differs from fixture')
    gui = pairs(rows, 'native_account_call', 'showGUI', 'scripts/client/Account.py', 573, 297)
    require(len(gui) == 1, 'original showGUI completion')
    return {'status': 'PASS', 'player_samples': len(players), 'rpc_requests': sorted(target),
            'streams': application['streams'], 'show_gui_normal_return': 297}


def hangar_ready(row, expected):
    flags = {'gui_initialized': True, 'interactive_movie_started': True, 'native_connected': True,
             'window_class': 'AppEntry', 'app_initialized': True, 'hangar_space_inited': True,
             'hangar_space_loaded': True, 'hangar_space_loading': False, 'waiting_visible': False,
             'items_cache_synced': True, 'selected_inventory_id': 1, 'vehicle_model_loaded': True}
    vehicle = {'inventory_id': 1, 'type_compact_descr': 3329, 'type_name': 'ussr:MS-1',
               'health': 90, 'max_health': 90, 'xp': 0, 'crew_slots': 2}
    if not (all(same_literal(row.get(k), v) for k, v in flags.items()) and same_literal(row.get('vehicle'), vehicle)
            and row.get('resources') == expected['resources'] and row.get('statistics') == expected['profile']['statistics']
            and type(row.get('vehicle_model_count')) is int and row['vehicle_model_count'] > 0
            and row.get('vehicle_models_visible') == [True] * row['vehicle_model_count']):
        return False
    views = row.get('views', {})
    return all(views.get(key, {}).get('class_name') == name and views.get(key, {}).get('alias') == alias
               and views.get(key, {}).get('flash_bound') is True for key, name, alias in
               [('main', 'LobbyView', 'lobby'), ('lobby_sub', 'Hangar', 'hangar')])


def hangar(rows, expected):
    samples = [r for r in rows if r['event'] == 'native_hangar' and r.get('items_cache_synced') is True]
    require(samples and all(r.get('resources') == expected['resources'] and r.get('statistics') == expected['profile']['statistics']
                           for r in samples), 'native resources/statistics changed')
    ready = [r for r in samples if hangar_ready(r, expected)]
    require(len(ready) >= 3, 'native MS1 hangar/model readiness missing')
    for method, (line, offset) in HEADER_RETURNS.items():
        completions = pairs(rows, 'native_header_call', method,
                            'scripts/client/gui/Scaleform/daapi/view/meta/LobbyHeaderMeta.py', line, offset, True)
        require(completions, 'original bound header callback absent')
        values = [p[1] for p in completions]
        if method == 'as_nameResponseS':
            require(all(r.get('name') == r.get('fullName') == expected['name'] and r.get('clan') is None for r in values), 'header nickname identity')
        elif method != 'as_setTankNameS':
            field, resource = {'as_creditsResponseS': ('credits', 'credits'), 'as_goldResponseS': ('gold', 'gold'),
                               'as_setFreeXPS': ('freeXP', 'free_xp')}[method]
            require(all(type(r.get(field)) is str and re.sub(r'[\s\u00a0]', '', r[field]) == str(expected['resources'][resource])
                        for r in values), 'header resource values')
    return {'status': 'PASS', 'synced_samples': len(samples), 'ms1_ready_samples': len(ready),
            'first_ready_seconds': ready[0]['elapsed_seconds'], 'last_ready_seconds': ready[-1]['elapsed_seconds'],
            'scope': 'Condition-based crew display, not a 60-second stability or long-session claim.'}


def crew_snapshot(row, expected):
    flags = {'version': 1, 'database_id': expected['native_id'], 'ready': True, 'issues': [],
             'selected_ms1': True, 'selected_inventory_id': 1, 'tankmen_count': 2,
             'ms1_assigned_ids': [1, 2], 'is7_assigned_count': 0,
             'inventory_mutation_requested': False, 'selection_changed_by_observer': False}
    for key, value in flags.items():
        same(row.get(key), value, 'native crew readiness/identity differs')
    require(type(row.get('tankmen')) is list and len(row['tankmen']) == 2
            and type(row.get('vehicles')) is list and len(row['vehicles']) == 2, 'native crew/vehicle collection size')
    for index, (role, hexadecimal, first, last, combined) in enumerate(CREW):
        item, measured = row['tankmen'][index], expected['export']['data']['crew'][index]
        for key, value in {'inventory_id': index + 1, 'vehicle_inventory_id': 1, 'vehicle_slot_index': index,
                           'is_in_tank': True, 'original_parse_repack_equal': True, 'compact_descr_hex': hexadecimal,
                           'compact_descr_bytes': 25, 'compact_descr_sha256': digest(bytes.fromhex(hexadecimal)),
                           'combined_roles': combined, 'first_name': first, 'last_name': last,
                           'base_role_level': 100, 'decoded': measured['decoded'], 'dossier_sha256': measured['dossier_sha256']}.items():
            same(item.get(key), value, 'actual tankman descriptor/assignment/name differs')
        require(type(item.get('effective_role_level')) in (int, float) and item['effective_role_level'] == (100, 110)[index]
                and type(item.get('efficiency_role_level')) in (int, float) and item['efficiency_role_level'] == 100,
                'actual tankman level/commander bonus differs')
        bonuses = item.get('bonuses')
        require(type(bonuses) is dict and set(bonuses) == {'brotherhood', 'commander', 'equipment', 'opt_devices', 'penalty'}
                and all(type(v) in (int, float) and v == ((0, 10)[index] if k == 'commander' else 0) for k, v in bonuses.items()),
                'unmeasured tankman bonus')
    for index, vehicle in enumerate(row['vehicles']):
        require(vehicle.get('inventory_id') == index + 1 and vehicle.get('type_compact_descr') == (3329, 7169)[index]
                and vehicle.get('type_name') == ('ussr:MS-1', 'ussr:IS-7')[index]
                and vehicle.get('descriptor_sha256') == digest(expected['state'][b'inventory'][1][b'compDescr'][index + 1]),
                'native vehicle descriptor identity differs')
        slots = vehicle.get('crew')
        require(type(slots) is list and len(slots) == (2, 5)[index], 'native crew slot count')
        roles = ('commander', 'driver') if index == 0 else ('commander', 'gunner', 'driver', 'loader', 'loader')
        for n, slot in enumerate(slots):
            same(slot, {'slot_index': n, 'role': roles[n], 'tankman_inventory_id': n + 1 if index == 0 else None,
                        'tankman_compact_descr_sha256': digest(bytes.fromhex(CREW[n][1])) if index == 0 else None},
                 'native vehicle crew slot mapping differs')
    stable = {k: v for k, v in row.items() if k not in ('event', 'elapsed_seconds', 'observation_index')}
    return digest(json.dumps(stable, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii'))


def crew_flash(rows):
    meta = pairs(rows, 'native_crew_call', 'as_tankmenResponseS', CREW_SOURCES[0][0], 59, 30, True)
    updates = pairs(rows, 'native_crew_call', 'updateTankmen', CREW_SOURCES[1][0], 42, 1066, True)
    successes = []
    for start, call, end, returned in meta:
        same(call.get('roles'), returned.get('roles'), 'CrewMeta roles changed before return')
        same(call.get('tankmen'), returned.get('tankmen'), 'CrewMeta data changed before return')
        if call.get('roles') != [{'roleType': 'commander', 'slot': 0, 'tankmanID': 1},
                                 {'roleType': 'driver', 'slot': 1, 'tankmanID': 2}]:
            continue  # IS7/initial empty projection is preserved, not called a crew success.
        tanks = call.get('tankmen')
        require(type(tanks) is list and len(tanks) == 2, 'CrewMeta two tankmen required')
        for index, (role, _, first, last, _) in enumerate(CREW):
            item = tanks[index]
            require(item.get('tankmanID') == index + 1 and item.get('roleType') == role
                    and item.get('firstname') == first and item.get('lastname') == last and item.get('inTank') is True,
                    'original Flash crew identity/name')
            for key, amount in {'specializationLevel': (100, 110)[index], 'efficiencyLevel': 100, 'bonus': (0, 10)[index]}.items():
                require(type(item.get(key)) in (int, float) and item[key] == amount, 'original Flash crew level differs')
        parent = [p for p in updates if p[0] < start < end < p[2] and p[1]['owner_id'] == call['owner_id']]
        require(len(parent) == 1, 'CrewMeta not nested in original Crew.updateTankmen')
        successes.append({'call_id': call['call_id'], 'owner_id': call['owner_id'], 'call_line': start + 1,
                          'return_line': end + 1, 'return_seconds': returned['elapsed_seconds'],
                          'roles': call['roles'], 'tankmen': tanks})
    require(successes, 'no original bound Flash projection of the two MS1 crew members')
    return {'status': 'PASS', 'projections': successes, 'scope': 'Native original Flash callback; visual review remains separate.'}


def crew_policy(rows):
    policies = [(i, r) for i, r in enumerate(rows) if r['event'] == 'crew_capability_policy']
    require(len(policies) == 2, 'crew policy lifecycle missing')
    (begin, start), (end, finish) = policies
    require(start.get('phase') == 'install' and finish.get('phase') == 'restore'
            and start.get('policy_version') == finish.get('policy_version') == 2
            and start.get('crew_changes_available') is False and start.get('personal_case_available') is False
            and start.get('original_readers_preserved') is True and finish.get('original_binding_restored') is True,
            'explicit crew policy version/lifecycle')
    bindings = start.get('bindings')
    require(type(bindings) is list and len(bindings) == len(set(bindings)) == 20
            and 'Crew.unloadTankman' in bindings and 'BusinessLobbyHandler.showCrewTankmanInfo' in bindings
            and finish.get('restored_bindings') == bindings, 'crew policy bindings/restoration')
    for source in start.get('audited_sources', []):
        raw = local_file(config()[1]['original_client_root'], 'res/' + source['source'] + 'c', 1024 * 1024)
        require(digest(raw) == source['sha256'], 'crew policy audited original source hash')
    stages = [(i, r) for i, r in enumerate(rows) if r['event'] == 'hangar_bootstrap_step' and r.get('stage') == 'crew_capabilities']
    require(len(stages) == 2 and [r.get('phase') for _, r in stages] == ['begin', 'return']
            and stages[0][0] < begin < stages[1][0] < end, 'crew policy bootstrap placement')
    actions = [(i, r) for i, r in enumerate(rows) if r['event'] in ('crew_capability_denied', 'crew_capability_notice')]
    require(len(actions) == 2, 'exactly one diagnostic denial and original warning required')
    (denied_at, denied), (notice_at, notice) = actions
    require(begin < denied_at < notice_at < end and denied['event'] == 'crew_capability_denied'
            and denied.get('capability') == 'crew_changes' and denied.get('action') == 'unload'
            and denied.get('callback') == 'Crew.unloadTankman' and denied.get('origin') == 'project_test_service_policy'
            and denied.get('original_callback_called') is False and denied.get('original_mutation_called') is False
            and notice['event'] == 'crew_capability_notice' and notice.get('phase') == 'return'
            and notice.get('channel') == 'original_SystemMessages_Warning'
            and notice.get('callback') == denied['callback'] and notice.get('action') == denied['action'], 'honest unavailable action/notice')
    return {'status': 'PASS', 'bindings': bindings, 'denied_line': denied_at + 1, 'notice_line': notice_at + 1,
            'original_mutation_called': False, 'server_mutation_acceptance': 'NOT_RUN'}


def png_container(data):
    require(45 <= len(data) <= 16 * 1024 * 1024 and data[:8] == b'\x89PNG\r\n\x1a\n', 'PNG signature/size')
    pos, count, image_bytes, dimensions = 8, 0, 0, None
    while pos < len(data):
        require(count < 1024 and pos + 12 <= len(data), 'PNG chunk bound')
        length = struct.unpack_from('>I', data, pos)[0]
        end = pos + length + 12
        require(end <= len(data), 'PNG truncated chunk')
        kind, body = data[pos + 4:pos + 8], data[pos + 8:end - 4]
        require(zlib.crc32(kind + body) & 0xffffffff == struct.unpack_from('>I', data, end - 4)[0], 'PNG checksum')
        if count == 0:
            require(kind == b'IHDR' and length == 13, 'PNG first IHDR')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            require(640 <= width <= 8192 and 480 <= height <= 8192 and depth == 8 and color in (2, 6)
                    and compression == filtering == 0 and interlace in (0, 1), 'native PNG dimensions/format')
            dimensions = [width, height]
        else:
            require(kind != b'IHDR', 'PNG duplicate IHDR')
        if kind == b'IDAT':
            image_bytes += length
        if kind == b'IEND':
            require(length == 0 and end == len(data) and image_bytes > 0, 'PNG IEND/data')
            return dimensions
        count, pos = count + 1, end
    raise ValueError('PNG missing IEND')


def scenario(rows, outcome, plan, expected, local_root):
    names = ('crew_scenario_start', 'crew_scenario_complete', 'diagnostic_condition_complete', 'quit_requested', 'fini_enter')
    events = {name: [(i, r) for i, r in enumerate(rows) if r['event'] == name] for name in names}
    require(all(len(value) == 1 for value in events.values()), 'scenario/condition/quit event count')
    positions = [events[name][0][0] for name in names]
    require(positions == sorted(positions) and len(set(positions)) == len(positions), 'scenario completion/quit/fini order')
    complete = events['crew_scenario_complete'][0][1]
    require(complete.get('version') == 1 and complete.get('phase') == 'complete'
            and complete.get('database_id') == expected['native_id'] and complete.get('observations') == 3
            and complete.get('screenshots') == 2 and complete.get('crew_unchanged') is True
            and complete.get('automatic_quit') is False and complete.get('user_manual_acceptance') == 'NOT_RUN', 'crew scenario completion')
    condition = events['diagnostic_condition_complete'][0][1]
    require(condition.get('condition') == 'ms1_crew_observed' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False
            and not any(r['event'] == 'diagnostic_condition_failed' for r in rows), 'native conditional completion failed/misreported')
    control = outcome.get('diagnostic_control', {})
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition' and control.get('verify_ms1_crew') is True
            and control.get('export_ms1_crew') is False and control.get('quit_when') == 'ms1_crew_observed'
            and outcome.get('control_consumed') is True, 'explicit diagnostic control scope')
    observations = [(i, r) for i, r in enumerate(rows) if r['event'] == 'ms1_crew_observation']
    require(len(observations) == 3 and [r.get('observation_index') for _, r in observations] == [1, 2, 3], 'three ordered original crew observations')
    fingerprints = [crew_snapshot(r, expected) for _, r in observations]
    require(len(set(fingerprints)) == 1, 'crew changed during denied action')
    actions = [(i, r) for i, r in enumerate(rows) if r['event'] == 'crew_scenario_action']
    require([(r.get('action'), r.get('moment')) for _, r in actions] ==
            [('select_ms1', 'call'), ('select_ms1', 'return'), ('deny_unload', 'call'), ('deny_unload', 'return')], 'original selection/denial action order')
    require(actions[0][1].get('original_handler') == 'TankCarousel.vehicleChange'
            and actions[0][1].get('inventory_id') == 1 and actions[2][1].get('callback') == 'Crew.unloadTankman'
            and actions[2][1].get('origin') == 'explicit_diagnostic_of_installed_UI_policy', 'scenario invokes wrong action')
    denied = [i for i, r in enumerate(rows) if r['event'] == 'crew_capability_denied']
    notices = [i for i, r in enumerate(rows) if r['event'] == 'crew_capability_notice']
    require(len(denied) == len(notices) == 1 and actions[2][0] < denied[0] < notices[0] < actions[3][0], 'denial not nested in diagnostic request')
    shots = [(i, r) for i, r in enumerate(rows) if r['event'] == 'crew_scenario_screenshot']
    requested = [(i, r) for i, r in enumerate(rows) if r['event'] == 'crew_scenario_screenshot_requested']
    require(len(shots) == len(requested) == 2, 'two original native screenshot writes required')
    require(actions[1][0] < observations[0][0] < requested[0][0] < shots[0][0] < actions[2][0]
            < actions[3][0] < observations[1][0] < requested[1][0] < shots[1][0] < observations[2][0] < positions[1], 'crew/image/action sequence')
    directory = entry.owned(plan['settings']['screenshot_dir'], local_root, True)
    images = []
    for n, basename in enumerate(('crew_ms1', 'crew_denied')):
        shot = shots[n][1]['screenshot']
        require(requested[n][1].get('basename') == shot.get('basename') == basename
                and requested[n][1].get('writer') == 'BigWorld.screenShot' and requested[n][1].get('extension') == 'png', 'native screenshot request binding')
        path = entry.owned(shot['path'], local_root)
        require(path.parent == directory and re.fullmatch(basename + r'_[0-9]{3,10}\.png', path.name), 'native screenshot path/name')
        raw = read_limited(path, 16 * 1024 * 1024)
        dimensions = png_container(raw)
        require(len(raw) == shot['bytes'] and digest(raw) == shot['sha256'] and dimensions == shot['dimensions']
                and shot.get('png_container_valid') is True, 'native screenshot byte proof')
        ready = [r for r in rows[:requested[n][0]] if r['event'] == 'native_hangar']
        require(ready and hangar_ready(ready[-1], expected), 'image was requested outside ready native MS1 hangar')
        images.append({'file': path.name, 'path': str(path), 'sha256': digest(raw), 'bytes': len(raw),
                       'dimensions': dimensions, 'native_pixels_review': 'NOT_RUN'})
    return {'status': 'PASS', 'observations': 3, 'crew_fingerprint': fingerprints[0], 'images': images,
            'original_selection': 'TankCarousel.vehicleChange', 'denied_action': 'Crew.unloadTankman',
            'conditional_exit': 'ms1_crew_observed', 'human_manual_acceptance': 'NOT_RUN'}


def visual_review(install, trace_sha, scenario_report):
    path = install / 'visual-review-crew.json'
    if not path.exists():
        return {'status': 'NOT_RUN', 'reason': 'Native PNG human/assistant visual review absent'}
    raw = read_limited(path, 65536)
    review = entry.json_data(raw)
    require(review.get('version') == 1 and review.get('source') == 'assistant_native_png_review'
            and review.get('trace_sha256') == trace_sha, 'visual review trace/source mismatch')
    images = review.get('images')
    require(type(images) is list and len(images) == 2 and len({r.get('file') for r in images}) == 2, 'two reviewed native images required')
    for n, proof in enumerate(scenario_report['images']):
        matches = [r for r in images if r.get('file') == proof['file']]
        require(len(matches) == 1 and matches[0].get('sha256') == proof['sha256'], 'review screenshot hash mismatch')
        row = matches[0]
        require(all(row.get(k) is True for k in ('hangar_visible', 'ms1_visible', 'two_crew_visible',
                    'crew_names_and_levels_visible', 'resources_unchanged')) and row.get('warning_visible') is (n == 1),
                'reviewed crew/native warning pixels do not meet this card')
    return {'status': 'PASS', 'file': str(path), 'sha256': digest(raw), 'images': images,
            'scope': 'Recorded inspection of exact native PNGs; no claim of manual keyboard/mouse acceptance.'}


def cache_backend(backend, wire, expected):
    require(backend.get('source_is_frozen_span') is True, 'immutable gateway span required')
    raw = read_limited(Path(backend['source']), 8 * 1024 * 1024)
    require(digest(raw) == backend.get('source_sha256'), 'gateway span changed')
    text, session = raw.decode('utf8'), backend['session_id']
    initial = re.findall(rf'^INITIAL_CACHE_HINT session={session} request=(\d+) command=(\d+) '
                         r'descriptor_a=(-?\d+) descriptor_b=(-?\d+) response=full_stream client_state_applied=false$', text, re.M)
    wanted = {}
    for command in wire['commands']:
        if command['kind'] == 'sync' and command['command'] == 100 and command.get('persistent_crc', 0):
            wanted[command['request']] = (100, command['persistent_crc'], 0)
        elif command['kind'] == 'sync' and command['command'] == 300 and command.get('cached_bytes', 0):
            wanted[command['request']] = (300, command['cached_bytes'], command['cached_crc32_signed'])
    require(len(initial) == len(wanted) and {int(q): (int(c), int(a), int(b)) for q, c, a, b in initial} == wanted,
            'server advisory cache/full-stream contract differs from wire')
    refresh = re.findall(rf'^REFRESH_CACHE_HINT session={session} request=(\d+) '
                         r'descriptor_a=(-?\d+) descriptor_b=0 response=no_change client_state_applied=false$', text, re.M)
    target = {r['request']: r['persistent_crc'] for r in wire['commands'] if r['kind'] == 'refresh' and r.get('persistent_crc', 0)}
    require(len(refresh) == len(target) and {int(q): int(a) for q, a in refresh} == target, 'cached refresh/no-change contract differs')
    dossier = [r for r in wire['commands'] if r['kind'] == 'sync' and r['command'] == 600]
    require(len(dossier) == 1, 'dossier request count')
    return {'status': 'PASS', 'initial': [{'request': q, 'command': v[0], 'a': v[1], 'b': v[2]} for q, v in wanted.items()],
            'refresh': [{'request': q, 'persistent_crc': v} for q, v in target.items()],
            'dossier_request': dossier[0], 'dossier_cursor': expected['dossier_cache'],
            'client_cache_state_applied': False}


def verify_session(args, install, expected, password, local_root):
    checks, report = {}, {'version': VERSION, 'install': str(install), 'human_manual_acceptance': 'NOT_RUN'}
    report['checks'] = checks
    stage = 'installation'
    try:
        plan_raw = local_file(install, 'install-plan.json', 1024 * 1024)
        plan = entry.json_data(plan_raw)
        outcome_raw = local_file(install, 'native-outcome.json', 262144)
        outcome = entry.json_data(outcome_raw)
        require(outcome.get('plan_sha256') == digest(plan_raw), 'outcome/plan hash mismatch')
        require(plan.get('mode') == 'interactive' and plan.get('normal_auto_login') is False
                and plan.get('normal_auto_quit') is False, 'normal defaults changed')
        same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'], 'postrun/plan settings differ')
        checks[stage] = {'status': 'PASS', 'plan_sha256': digest(plan_raw), 'outcome_sha256': digest(outcome_raw),
                         'started_utc': outcome.get('started_utc'), 'finished_utc': outcome.get('finished_utc')}
        checks['compiled_sources'] = checked(lambda: compiled_sources(install, plan, outcome, scenario=True))
        stage = 'runtime_trace'
        rows, info = entry.runtime_rows(install, plan, outcome, local_root)
        checks[stage] = {'status': 'PASS', **info}
        checks['runtime_common'] = checked(lambda: runtime_common(install, plan, outcome, rows))
        checks['module_policy'] = checked(lambda: module_policy_evidence(rows))
        checks['crew_policy'] = checked(lambda: crew_policy(rows))
        checks['hangar'] = checked(lambda: hangar(rows, expected))
        checks['original_crew_flash'] = checked(lambda: crew_flash(rows))
        checks['crew_scenario'] = checked(lambda: scenario(rows, outcome, plan, expected, local_root))
        checks['visual_review'] = checked(lambda: visual_review(install, info['sha256'], checks['crew_scenario']))
        stage = 'wire'
        run = entry.owned(outcome['gateway_run'], local_root, True)
        client_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(client_digest) == 16, 'client digest byte count')
        require(type(outcome.get('gateway_log_span')) is dict, 'frozen gateway span absent')
        wire = entry.wire(install, entry.owned(args.private_key, local_root), expected, password, client_digest,
                          dossier_cache=expected['dossier_cache'], cache_hints=True)
        checks['wire'] = wire
        checks['native_account'] = checked(lambda: native_account(rows, wire, expected))
        backend = checked(lambda: entry.backend_binding(install, outcome, wire, expected, local_root))
        checks['backend'] = backend
        checks['cache_backend'] = checked(lambda: cache_backend(backend, wire, expected))
        require(all(r['kind'] in ('sync', 'refresh') for r in wire['commands']), 'unmeasured crew session mutation command')
        report['identity_snapshot'] = {
            'account_id': expected['account_id'], 'native_database_id': expected['native_id'], 'nickname': expected['name'],
            'profile_sha256': expected['profile_sha256'], 'fixture_manifest_sha256': expected['manifest_sha256'],
            'payload_sha256': {k: digest(v) for k, v in expected['raw'].items()},
            'resources': expected['resources'], 'statistics': expected['profile']['statistics'],
            'crew_compact_sha256': [digest(bytes.fromhex(c[1])) for c in CREW], 'dossier_cache': expected['dossier_cache']}
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = {'status': 'FAIL', 'error_type': type(error).__name__,
                         'reason': str(error) if type(error) is ValueError and not isinstance(error, json.JSONDecodeError)
                         else 'Malformed, missing or inconsistent bounded evidence'}
    report['status'] = status(checks)
    return report


def relogin(current, previous):
    require(current.get('status') == previous.get('status') == 'PASS', 'both native sessions must pass independently')
    require(current['install'] != previous['install']
            and current['checks']['runtime_trace']['sha256'] != previous['checks']['runtime_trace']['sha256'], 'relogin reused same run')
    same(current['identity_snapshot'], previous['identity_snapshot'], 'relogin changed identity/profile/payload/crew')
    same(current['checks']['compiled_sources']['modules'], previous['checks']['compiled_sources']['modules'], 'relogin source/compiler versions differ')
    from datetime import datetime
    finished = datetime.fromisoformat(previous['checks']['installation']['finished_utc'].replace('Z', '+00:00'))
    started = datetime.fromisoformat(current['checks']['installation']['started_utc'].replace('Z', '+00:00'))
    require(finished <= started, 'relogin sessions overlap/out of order')
    return {'status': 'PASS', 'previous_install': previous['install'],
            'previous_trace_sha256': previous['checks']['runtime_trace']['sha256'],
            'current_trace_sha256': current['checks']['runtime_trace']['sha256'],
            'identity_and_fixture_unchanged': True, 'same_compiled_sources': True,
            'scope': 'Two complete native authenticated sessions, real logout and immutable server profile; no battle/economy claim.'}


def verify(args):
    local_root = config()[1]['local_artifacts_root']
    report = {'version': VERSION, 'scope': 'Assigned server MS1 crew, original native display, explicit unavailable action and repeat login',
              'verifier_sha256': digest(read_limited(Path(__file__), 1024 * 1024)), 'checks': {},
              'human_manual_acceptance': 'NOT_RUN', 'relogin': {'status': 'NOT_RUN', 'reason': 'No previous install supplied'}}
    stage = 'inputs'
    try:
        install = entry.owned(args.install, local_root, True)
        fixture = entry.owned(args.fixture, local_root, True)
        native_export = entry.owned(args.native_export, local_root)
        stage = 'native_export'
        exported, export_report = export_evidence(native_export, local_root)
        report['checks'][stage] = export_report
        stage = 'fixture'
        expected, proof = crew_fixture(fixture, exported, export_report, local_root)
        report['checks'][stage] = proof
        stage = 'identity'
        password, identity_report = identity(expected, entry.owned(args.registration, local_root),
                                               entry.owned(args.credentials, local_root), args.case)
        report['checks'][stage] = identity_report
        report['checks']['original_contracts'] = checked(original_crew_contracts)
        report['session'] = verify_session(args, install, expected, password, local_root)
        report['checks']['native_session'] = {'status': report['session']['status']}
        if args.previous_install:
            previous_install = entry.owned(args.previous_install, local_root, True)
            report['previous_session'] = verify_session(args, previous_install, expected, password, local_root)
            report['relogin'] = checked(lambda: relogin(report['session'], report['previous_session']))
            report['checks']['paired_relogin'] = report['relogin']
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        report['checks'][stage] = {'status': 'FAIL', 'error_type': type(error).__name__,
                                   'reason': str(error) if type(error) is ValueError and not isinstance(error, json.JSONDecodeError)
                                   else 'Malformed, missing or inconsistent bounded evidence'}
    report['status'] = status(report['checks'])
    report['card_status'] = 'FAIL' if report['status'] == 'FAIL' else 'PASS' if report['relogin']['status'] == 'PASS' else 'NOT_RUN'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'fixture', 'native-export', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--previous-install')
    parser.add_argument('--registration', default=str(DEFAULT_REG / 'registration.json'))
    parser.add_argument('--credentials', default=str(DEFAULT_REG / 'test-credentials.json'))
    parser.add_argument('--case', default='operator_shared')
    parser.add_argument('--private-key', default=str(ROOT / 'local/server/native-private.pem'))
    args = parser.parse_args()
    out = output_dir(args.out)
    require(not any(out.iterdir()), 'verification output directory must be fresh and empty')
    report = verify(args)
    target = out / 'ms1-crew-native-verification.json'
    save_json(target, report)
    print(json.dumps({'status': report['status'], 'card_status': report['card_status'],
                      'report': str(target), 'sha256': digest(read_limited(target, 32 * 1024 * 1024))}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
