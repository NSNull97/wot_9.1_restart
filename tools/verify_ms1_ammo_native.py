"""Independent native MS-1 ammunition evidence, separate from frozen readers.

This card's literal reader accepts bounded primitive protocol2 data, including
the measured two-integer turret/gun layout key. It never loads pickle objects,
executes a client module, starts a process, or imports a state generator.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import struct

import verify_account_switch as switch
import verify_long_hangar as sustained
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table
from verify_hangar import digest, local_file

crew, entry, previous, limits = switch.crew, switch.entry, switch.previous, switch.limits


MAX_RAW = 16384
MAX_NODES = 4096
MAX_DEPTH = 16
VERSION = 1
FLAT = [2570, 20, 2826, 0, 3082, 0]
LAYOUT = (5891, 5892)
MODULES = sustained.MODULES + ('ms1_ammo_probe', 'ms1_ammo_scenario')
PROBE_SHA = '0cbc86441910931f29f6211dee93b997781a4d5681a98a9ea0b82c8d80237218'
# These new producer/build inputs are deliberately not inferred from a report.
# Their independently reviewed freezes are required before native acceptance.
SCENARIO_SHA = 'b16f84d38fa1ca8b1ccb676a65180d2463c1efbd4ecee57f01786431e2bd0594'
PERSONALITY_SHA = 'e0c0c6afc6dcfcd4333c74f341969ef9467bb251e2681b0d7f896f2537290e3a'
EXPORT_PERSONALITY_SHA = '55b09306b5772484b648f0c2f5d6c07eb6d64ee4772a55e521344884f1917178'
INSTALLER_SHA = '9cb8009a82ce8ed957b63cd1a99f25689baee99d423f131c38978baa5d617ef8'
RUNNER_SHA = '7f1d9e9e0de39ccea6a83e3021ebc0c99c0454714ee01bd026b3da322239fd99'
GENERATOR_SHA = 'a837cf94c037a5726d34b6450be8ec7c17170df4f7fd9c7076bf33fc09f708a2'
BUILD_HELPER_SHA = '06277aea47d177903bf6d14499feeba368efbc27b7d09530e2a019095ae63037'
BUILD_MANIFEST_SHA = 'd6cf3917e224359ecec66e6bd10c99c8449850721fdd56909019d150d0b7b6c5'
HANGAR_SHA = 'aa6e1e279a99ae79676faa1e88bba65c386fe91e116f567c94b2f058e8bf8442'
ACCEPTED_LONG = ROOT / 'local/evidence/20261005-p02-long-hangar/wire/verify-long01-03/long-hangar-verification.json'
ACCEPTED_LONG_SHA = 'c74df14374e053bab68c13a5c1b366814834b50ba8a084123340b32062b95d25'
BASE_MANIFEST_SHA = 'c979a7dafe36ec0130c0c472ccfdda328300e12f8d3ecdadde1881a6435ff685'
BASE_PROFILE_SHA = '5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888'
DEFAULT_BUILD = ROOT / 'local/evidence/20261005-p02-ms1-ammo/server-rebuild-01'
AMMO_SOURCES = (
    ('scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py',
     '54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8', '__updateAmmo', 147, 504),
    ('scripts/client/gui/Scaleform/daapi/view/meta/AmmunitionPanelMeta.py',
     'b8ff5d7e1f986ef9b8165703d42ec6f51f042a485d1004f7a1713eddb73a856a', 'as_setAmmoS', 61, 27),
)
PROBE_SOURCES = (
    ('res/scripts/common/items/__init__.pyc', '587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176'),
    ('res/scripts/common/items/vehicles.pyc', '805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6'),
    ('res/scripts/common/account_shared.pyc', '187f914c508a359a0fa4f9cc4a0764080a9d71c9214a3b74e9f7ef72cfa6f65c'),
    ('res/scripts/client/CurrentVehicle.pyc', 'a57c32ca6e84c2ae4c343bba3b88213680c65f3a28adb50d8009e0c9df833953'),
    ('res/scripts/client/gui/shared/gui_items/Vehicle.pyc', 'ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8'),
    ('res/scripts/client/gui/shared/gui_items/vehicle_modules.pyc', '8541c30f9258511e80decb3a5ed5545e59238343ae532e8112895b6539797c7b'),
    ('res/scripts/client/gui/shared/utils/requesters/inventoryrequester.pyc', '4e2c79a4f826740b3363b14b00dba7aeaa9a539dc3c1b32671eb5256f4103e84'),
    ('res/scripts/client/gui/shared/utils/requesters/itemsrequester.pyc', '41e5e9bacbb68e89202116bd267c6cd9fceeda4edb0ed605c7b87cc9315c0c44'),
    ('res/scripts/client/gui/Scaleform/daapi/view/lobby/hangar/ammunitionpanel.pyc', AMMO_SOURCES[0][1]),
    ('res/scripts/client/gui/Scaleform/daapi/view/meta/ammunitionpanelmeta.pyc', AMMO_SOURCES[1][1]),
    ('res/scripts/item_defs/vehicles/ussr/ms-1.xml', 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535'),
    ('res/scripts/item_defs/vehicles/ussr/components/guns.xml', '889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b'),
    ('res/scripts/item_defs/vehicles/ussr/components/shells.xml', 'ed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96'),
)
SHELLS = (('_37mm_UBRT1', 10, 2570, 'ARMOR_PIERCING'),
          ('_37mm_BPT1', 11, 2826, 'HOLLOW_CHARGE'), ('_37mm_UOT1', 12, 3082, 'HIGH_EXPLOSIVE'))
OTHER_OPERATIONS = ('export_ms1_crew', 'verify_ms1_crew', 'verify_hangar_limits',
                    'verify_hangar_windows', 'verify_inprocess_relogin',
                    'verify_account_switch', 'alternate_credentials_present')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, low=0, high=2147483647):
    require(type(value) is int and low <= value <= high, 'bounded integer required')
    return value


def number(value, low=0, high=2000):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
            'bounded finite number required')
    return value


def same_tree(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return (left.keys() == right.keys()
                and all(same_tree(left[key], right[key]) for key in left))
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(same_tree(a, b) for a, b in zip(left, right))
    return left == right


def public_control(outcome, operation='verify'):
    require(operation in ('export', 'verify'), 'unknown ammunition diagnostic operation')
    value = outcome.get('diagnostic_control')
    keys = set(OTHER_OPERATIONS) | {'bytes', 'credentials_present', 'submit_via', 'screenshot_when',
                                   'quit_when', 'plaintext_recorded', 'export_ms1_ammo', 'verify_ms1_ammo'}
    require(type(value) is dict and set(value) == keys,
            'exact public ammunition metadata required; secrets and derived digests forbidden')
    integer(value['bytes'], 1, 8192)
    condition = 'ms1_ammo_exported' if operation == 'export' else 'ms1_ammo_observed'
    require(value['credentials_present'] is True and value['plaintext_recorded'] is False
            and all(value[key] is False for key in OTHER_OPERATIONS)
            and value['export_ms1_ammo'] is (operation == 'export')
            and value['verify_ms1_ammo'] is (operation == 'verify')
            and value['submit_via'] == 'python' and value['screenshot_when'] is None
            and value['quit_when'] == condition,
            'ammunition diagnostic operation/conditional exit differs')
    return value


def state_ammo_delta(before, after, flat, layout_key):
    """Only the two measured MS-1 inventory fields may differ from the r3 tree."""
    import copy
    require(type(flat) is list and len(flat) == 6
            and all(type(value) is int for value in flat)
            and flat == [2570, 20, 2826, 0, 3082, 0], 'exact twenty-AP test grant required')
    require(type(layout_key) is tuple and layout_key == (5891, 5892)
            and all(type(value) is int for value in layout_key), 'original mounted turret/gun key differs')
    require(type(before) is dict and type(after) is dict, 'state root dictionary required')
    old = before[b'inventory'][1]
    current = after[b'inventory'][1]
    require(same_tree(old[b'shells'], {1: [], 2: []})
            and same_tree(old[b'shellsLayout'], {1: {}, 2: {}}), 'previous ammunition is not the accepted empty r3 state')
    require(same_tree(current[b'shells'], {1: flat, 2: []})
            and same_tree(current[b'shellsLayout'], {1: {layout_key: flat}, 2: {}}),
            'native mounted counts/layout or IS-7 ammunition differs')
    restored = copy.deepcopy(after)
    restored[b'inventory'][1][b'shells'][1] = []
    restored[b'inventory'][1][b'shellsLayout'][1] = {}
    require(same_tree(restored, before), 'ammunition changed identity, crew, resources, progression or other state')
    return {'status': 'PASS', 'changed_fields': ['inventory[1].shells[1]', 'inventory[1].shellsLayout[1]'],
            'flat_shells': list(flat), 'layout_key': list(layout_key), 'total': sum(flat[1::2]),
            'comparison': 'type-sensitive literal tree; exact wire payload identity is verified separately'}


def exact_state_bytes(before, after):
    """Independent literal splice; no production encoder is imported."""
    old = b'U\x06shells}(K\x01]K\x02]uU\x0cshellsLayout}(K\x01}K\x02}u'
    values = b'](M\x0a\x0aK\x14M\x0a\x0bK\x00M\x0a\x0cK\x00e'
    new = b'U\x06shells}(K\x01' + values + b'K\x02]uU\x0cshellsLayout}(K\x01}((M\x03\x17M\x04\x17t' + values + b'uK\x02}u'
    require(type(before) is bytes and type(after) is bytes and before.count(old) == 1,
            'unique accepted empty native ammunition fields required')
    wanted = before.replace(old, new, 1)
    require(after == wanted and after.count(new) == 1 and after.replace(new, old, 1) == before,
            'native wire bytes changed beyond the exact mounted ammunition splice')
    return {'status': 'PASS', 'old_sha256': digest(before), 'new_sha256': digest(after),
            'restored_sha256': digest(after.replace(new, old, 1)), 'changed_fields': 2}


def literal_ammo(data):
    """Bounded independent primitive reader; tuple keys are two UINT16 IDs only.

    The surrounding fixture gate must additionally restrict that key to the
    original mounted turret/gun and the single MS-1 shellsLayout dictionary.
    Parsing alone is never native compatibility or profile acceptance.
    """
    require(type(data) is bytes and 4 <= len(data) <= MAX_RAW
            and data[:2] == b'\x80\x02', 'ammunition literal size/protocol')
    stack, cursor, nodes = [], 2, 0
    marker = object()

    def take(size):
        nonlocal cursor
        require(type(size) is int and 0 <= size <= len(data) - cursor,
                'ammunition literal truncated')
        part = data[cursor:cursor + size]
        cursor += size
        return part

    def key_allowed(key):
        if type(key) in (bytes, int):
            return True
        return (type(key) is tuple and len(key) == 2
                and all(type(value) is int and 1 <= value <= 65535 for value in key))

    while cursor < len(data):
        nodes += 1
        require(nodes <= MAX_NODES, 'ammunition literal node bound')
        opcode = take(1)[0]
        depth = 0
        if opcode == 0x4e:
            value = None
        elif opcode in (0x88, 0x89):
            value = opcode == 0x88
        elif opcode in (0x4b, 0x4d, 0x4a):
            kind = {0x4b: '<B', 0x4d: '<H', 0x4a: '<i'}[opcode]
            value = struct.unpack(kind, take(struct.calcsize(kind)))[0]
        elif opcode == 0x47:
            value = struct.unpack('>d', take(8))[0]
            require(math.isfinite(value), 'ammunition literal nonfinite float')
        elif opcode in (0x55, 0x54):
            length = take(1)[0] if opcode == 0x55 else struct.unpack('<I', take(4))[0]
            value = take(length)
        elif opcode in (0x5d, 0x7d, 0x29):
            value = {0x5d: list, 0x7d: dict, 0x29: tuple}[opcode]()
            depth = 1
        elif opcode == 0x28:
            value = marker
        elif opcode in (0x65, 0x75, 0x74):
            mark = next((i for i in range(len(stack) - 1, -1, -1)
                         if stack[i][0] is marker), None)
            require(mark is not None, 'ammunition literal MARK absent')
            values = stack[mark + 1:]
            depth = 1 + max((nested for _, nested in values), default=0)
            require(depth <= MAX_DEPTH, 'ammunition literal depth bound')
            if opcode == 0x74:
                value = tuple(item for item, _ in values)
                del stack[mark:]
            else:
                require(mark > 0, 'ammunition literal container absent')
                container, previous_depth = stack[mark - 1]
                if opcode == 0x65:
                    require(type(container) is list, 'ammunition APPENDS target')
                    container.extend(item for item, _ in values)
                else:
                    require(type(container) is dict and len(values) % 2 == 0,
                            'ammunition SETITEMS target/arity')
                    for i in range(0, len(values), 2):
                        key, child = values[i][0], values[i + 1][0]
                        require(key_allowed(key), 'ammunition dictionary key type/bound')
                        require(key not in container, 'ammunition duplicate dictionary key')
                        container[key] = child
                stack[mark - 1] = (container, max(previous_depth, depth))
                del stack[mark:]
                continue
        elif opcode == 0x2e:
            require(cursor == len(data) and len(stack) == 1 and stack[0][0] is not marker,
                    'ammunition literal STOP/trailing/stack')
            return stack[0][0]
        else:
            raise ValueError('ammunition literal forbidden opcode')
        stack.append((value, depth))
        require(len(stack) <= MAX_NODES
                and sum(item is marker for item, _ in stack) <= MAX_DEPTH,
                'ammunition literal stack/depth bound')
    raise ValueError('ammunition literal STOP absent')


def dependencies():
    proof = switch.frozen_dependencies()
    for name, pin in (
        ('verify_account_switch.py', '60ffcbbe4f0146b02d73dab3b7dea1d524b74921fc0ccdfebca14d877e3b29d4'),
        ('verify_long_hangar.py', '297f5b11a8f3ada5c11b9f0fde3f3a33ae4acafc74ec43c5d7d2fc2af85deddd'),
    ):
        path = ROOT / 'tools' / name
        require(digest(read_limited(path, 1024 * 1024)) == pin, 'frozen inherited evidence reader changed')
        proof['files'].append({'file': str(path), 'sha256': pin})
    proof['original_crew'] = crew.original_crew_contracts()
    proof['original_lifecycle'] = previous.original_logoff_contracts()
    for name, pin in (('interactive_client.py', INSTALLER_SHA), ('diagnostic_client_run.py', RUNNER_SHA)):
        path = ROOT / 'tools' / name
        require(type(pin) is str and digest(read_limited(path, 1024 * 1024)) == pin,
                'reviewed ammunition host integration source changed')
        proof['files'].append({'file': str(path), 'sha256': pin})
    table = opcode_table(read_limited(ROOT / 'local/vendor/cpython-2.7.18/opcode.py', 32768).decode('utf8'))
    original = config()[1]['original_client_root']
    original_ammo = []
    for source, pin, method, line, offset in AMMO_SOURCES:
        raw = local_file(original, 'res/' + source + 'c', 1024 * 1024)
        require(digest(raw) == pin, 'original ammunition callback source changed')
        methods = [c for c in inspect(raw, table)
                   if c['qualified_name'].split('.')[-1] == method and c['firstlineno'] == line]
        require(len(methods) == 1 and any(i['offset'] == offset and i['opname'] == 'RETURN_VALUE'
                                        for i in methods[0]['instructions']), 'original ammunition normal return differs')
        original_ammo.append({'source': source, 'sha256': pin, 'method': method,
                              'source_line': line, 'normal_return': offset})
    proof['original_ammunition'] = original_ammo
    return proof


def compiled_sources(install, plan, outcome, operation='verify'):
    accepted_raw = read_limited(ACCEPTED_LONG, 32 * 1024 * 1024)
    require(digest(accepted_raw) == ACCEPTED_LONG_SHA, 'accepted previous compiled-source anchor changed')
    accepted = entry.json_data(accepted_raw)
    require(accepted.get('status') == accepted.get('card_status') == 'PASS', 'accepted source anchor did not pass')
    old = {r['module']: r for r in accepted['checks']['compiled_sources']['modules']}
    require(operation in ('verify', 'export'), 'unknown compiled ammunition operation')
    pins = {'sr_interactive': EXPORT_PERSONALITY_SHA if operation == 'export' else PERSONALITY_SHA,
            'ms1_ammo_probe': PROBE_SHA, 'ms1_ammo_scenario': SCENARIO_SHA}
    require(all(type(pin) is str and re.fullmatch('[0-9a-f]{64}', pin) for pin in pins.values()),
            'ammunition client producer sources are not frozen; native acceptance NOT_RUN')
    sources = plan.get('sources')
    require(type(sources) is list and len(sources) == 16
            and {r.get('path') for r in sources} == {'client_patch/' + n + '.py' for n in MODULES},
            'sixteen exact versioned ammunition modules required')
    proof = []
    for source in sources:
        name = Path(source['path']).stem
        pin = pins[name] if name in pins else old[name]['source_sha256']
        require(source.get('sha256') == pin, 'ammunition compiled source/version changed')
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        pyc = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        matches = [r for r in plan['files'] if r.get('path') == relative]
        require(len(matches) == 1 and matches[0].get('runtime_mutable') is False
                and meta.get('source') == name + '.py' and meta.get('source_sha256') == pin
                and meta.get('source_executed') is False and meta.get('magic') == '03f30d0a'
                and meta.get('compiler', '').startswith('2.7.3 ') and pyc[:4] == bytes.fromhex('03f30d0a')
                and digest(pyc) == meta.get('pyc_sha256') == matches[0].get('installed_sha256')
                and local_file(install, 'postrun/' + relative, 1024 * 1024) == pyc,
                'compiled/postrun/source byte chain differs')
        if name not in pins:
            require(digest(pyc) == old[name]['pyc_sha256'], 'inherited compiled module changed')
        proof.append({'module': name, 'source_sha256': pin, 'pyc_sha256': digest(pyc)})
    crew.same(outcome.get('source_provenance', {}).get('modules'), proof, 'runner/compiler source chain differs')
    return {'status': 'PASS', 'modules': proof, 'inherited_unchanged_modules': 13}


def artifacts(install, local_root, operation='verify'):
    evidence = {}
    def saved(name, maximum):
        raw = local_file(install, name, maximum)
        evidence[name] = {'file': str(install / name), 'bytes': len(raw), 'sha256': digest(raw)}
        return entry.json_data(raw)
    plan = saved('install-plan.json', 1024 * 1024)
    outcome = saved('native-outcome.json', 262144)
    ledger = saved('patch-ledger.json', 2 * 1024 * 1024)
    started = saved('native-run-started.json', 262144)
    process = saved('native-process.json', 262144)
    installed = saved('install.json', 65536)
    saved('wire/capture.json', 4 * 1024 * 1024)
    backend = local_file(install, 'gateway-span.log', 8 * 1024 * 1024)
    evidence['gateway-span.log'] = {'file': str(install / 'gateway-span.log'), 'bytes': len(backend), 'sha256': digest(backend)}
    require(plan.get('mode') == 'interactive' and plan.get('normal_auto_login') is False
            and plan.get('normal_auto_quit') is False and outcome.get('plan_sha256')
            == ledger.get('plan_sha256') == evidence['install-plan.json']['sha256'], 'original install/ledger/defaults differ')
    for key in plan:
        crew.same(ledger.get(key), plan[key], 'original ledger/plan differs')
    require(installed.get('status') == 'PASS' and installed.get('client_exe_modified') is False
            and installed.get('files') == len(plan['files']), 'native package installation failed')
    require(started.get('client_started') is False and process.get('client_started') is True
            and integer(process.get('client_pid'), 1, 2**32 - 1) == outcome.get('client_pid'), 'actual spawned native process absent')
    for key in ('scope', 'runner_mode', 'exe_sha256', 'plan_sha256', 'started_utc', 'wire_source',
                'gateway_run', 'diagnostic_control', 'source_provenance'):
        crew.same(started.get(key), process.get(key), 'pre-spawn/process provenance differs')
        crew.same(process.get(key), outcome.get(key), 'process/outcome provenance differs')
    public_control(outcome, operation)
    require(type(INSTALLER_SHA) is str and outcome.get('source_provenance', {}).get('installer_sha256') == INSTALLER_SHA,
            'reviewed ammunition installer provenance differs')
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition'
            and outcome.get('control_consumed') is True, 'native conditional runner/input consumption absent')
    crew.same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)),
              plan['settings'], 'postrun/native settings differ')
    rows, trace = entry.runtime_rows(install, plan, outcome, local_root)
    return plan, outcome, rows, {'artifacts': evidence, 'trace': trace}, backend


def profile_delta(base_raw, profile, export_sha):
    base = entry.json_data(base_raw)
    require(digest(base_raw) == BASE_PROFILE_SHA and base.get('profile_version') == base.get('snapshot_revision') == 3,
            'accepted immutable profile3 baseline differs')
    grant = profile.get('ammo_grant')
    require(type(grant) is dict and set(grant) == {'grant_id', 'granted_at_ms', 'base_profile_sha256', 'native_export_sha256'}
            and grant.get('grant_id') == 'test-ms1-ammo-v1'
            and type(grant.get('granted_at_ms')) is int
            and base['crew_grant']['granted_at_ms'] <= grant['granted_at_ms'] <= 4102444800000
            and grant.get('base_profile_sha256') == digest(base_raw)
            and grant.get('native_export_sha256') == export_sha, 'ammunition grant identity/provenance differs')
    wanted = copy.deepcopy(base)
    wanted.update(profile_version=4, snapshot_revision=4, ammo_grant=grant,
                  ammunition=[{'vehicle_inventory_id': base['inventory'][0]['inventory_id'],
                               'shell_definition_id': 'shell:ms1-stock-ap', 'count': 20}])
    wanted['inventory'][0]['ammunition_count'] = 20
    require(same_tree(profile, wanted), 'profile4 changed identity, inventory, crew or progress beyond explicit ammunition grant')
    return base


def ammo_fixture(directory, base, export, export_report, local_root):
    manifest_raw = local_file(directory, 'manifest.json', 262144)
    manifest = entry.json_data(manifest_raw)
    require(set(manifest) == set(base['manifest']), 'ammunition manifest sixteen-field schema differs')
    for key, wanted in {'fixture_version': 4, 'profile_version': 4, 'snapshot_revision': 4,
                        'wire_sync_revision': 1, 'compatibility_catalog_revision': 3, 'ruleset': 'test_lab'}.items():
        crew.same(manifest.get(key), wanted, 'ammunition fixture version/scope differs')
    require(type(GENERATOR_SHA) is str and manifest['generator']['sha256'] == GENERATOR_SHA,
            'ammunition generator has not been frozen or changed')
    crew.same(manifest['generator'], {'file': str(ROOT / 'tools/ms1_ammo_state.py'), 'sha256': GENERATOR_SHA,
                                     'base_generator': base['manifest']['generator']}, 'ammunition generator/dependency provenance differs')
    require(digest(read_limited(ROOT / 'tools/ms1_ammo_state.py', 1024 * 1024)) == GENERATOR_SHA,
            'reviewed ammunition generator source changed')
    base_directory = Path(base['fixture'])
    require(digest(local_file(base_directory, 'manifest.json', 262144)) == BASE_MANIFEST_SHA,
            'accepted base manifest changed')
    preservation = manifest['preservation']
    require(entry.owned(preservation['base_fixture']['directory'], local_root, True) == base_directory
            and preservation['base_fixture']['manifest_sha256'] == BASE_MANIFEST_SHA, 'ammunition base fixture binding differs')
    profile_raw = local_file(directory, 'profile-input.json', 65536)
    profile = entry.json_data(profile_raw)
    base_raw = local_file(directory, 'base-profile-input.json', 65536)
    require(base_raw == local_file(base_directory, 'profile-input.json', 65536), 'copied immutable profile3 bytes differ')
    profile_delta(base_raw, profile, export_report['sha256'])
    for key, name, raw in (('profile_source', 'profile-input.json', profile_raw),
                           ('base_profile_source', 'base-profile-input.json', base_raw)):
        crew.same(manifest[key], {'file': name, 'relative_to': 'fixture_directory', 'sha256': digest(raw)},
                  'profile4 manifest source binding differs')
    crew.same(manifest['grant'], base['manifest']['grant'], 'existing IS-7 grant changed')
    for key in ('account_id', 'native_database_id'):
        crew.same(manifest[key], base['manifest'][key], 'ammunition identity changed')
    descriptors = copy.deepcopy(base['manifest']['native_descriptors'])
    descriptors['ammo'] = {'file': export_report['file'], 'bytes': export_report['bytes'], 'sha256': export_report['sha256']}
    crew.same(manifest['native_descriptors'], descriptors, 'ammunition native source descriptors changed')
    payloads = manifest.get('files')
    require(type(payloads) is list and [r.get('file') for r in payloads] == ['state.bin', 'shop.bin', 'dossier.bin'],
            'three exact ammunition wire payload records required')
    raw = {}
    for row in payloads:
        name = row['file']
        raw[name] = local_file(directory, name, MAX_RAW)
        require(integer(row.get('bytes'), 4, MAX_RAW) == len(raw[name]) and digest(raw[name]) == row.get('sha256'),
                'ammunition payload hash/size differs')
    state = literal_ammo(raw['state.bin'])
    delta = state_ammo_delta(base['state'], state, FLAT, LAYOUT)
    byte_delta = exact_state_bytes(base['raw']['state.bin'], raw['state.bin'])
    for name in ('shop.bin', 'dossier.bin'):
        require(raw[name] == base['raw'][name], 'ammunition changed authoritative shop/dossier bytes')
    wanted_preservation = {
        'status': 'PASS_LOCAL_INVARIANTS_ONLY', 'ammo_grant': profile['ammo_grant'],
        'base_fixture': {'directory': str(base_directory), 'manifest_sha256': BASE_MANIFEST_SHA},
        'base_state_sha256': digest(base['raw']['state.bin']), 'restored_state_sha256': digest(base['raw']['state.bin']),
        'shop_sha256': digest(raw['shop.bin']), 'dossier_sha256': digest(raw['dossier.bin']),
        'account_dossier_sha256': digest(state[b'stats'][b'dossier']),
        'dossier_cache': base['manifest']['preservation']['dossier_cache'],
        'delta': ['inventory[1].shells[1]=[2570,20,2826,0,3082,0]',
                  'inventory[1].shellsLayout[1][(5891,5892)]=[2570,20,2826,0,3082,0]'],
        'native_compatibility': 'NOT_RUN'}
    crew.same(preservation, wanted_preservation, 'ammunition preservation metadata differs')
    crew.same(entry.json_data(local_file(directory, 'preservation.json', 65536)), preservation, 'ammunition preservation copies differ')
    old_compat = entry.json_data(local_file(base_directory, 'compatibility.json', 65536))
    wanted_compat = copy.deepcopy(old_compat)
    wanted_compat.update(snapshot_revision=4, ammo_mapping=[{
        'shell_definition_id': 'shell:ms1-stock-ap', 'native_shell_compact_descr': 2570,
        'vehicle_inventory_id': base['profile']['inventory'][0]['inventory_id'], 'native_vehicle_inventory_id': 1,
        'native_turret_compact_descr': 5891, 'native_gun_compact_descr': 5892}])
    compatibility = entry.json_data(local_file(directory, 'compatibility.json', 65536))
    crew.same(compatibility, wanted_compat, 'ammunition compatibility mapping differs')
    wanted_model = entry.json_data(local_file(base_directory, 'fixture.json', 65536))
    wanted_model.update(fixture_version=4, profile_version=4, snapshot_revision=4, inventory=profile['inventory'],
                        ammunition=profile['ammunition'], ammo_grant=profile['ammo_grant'])
    crew.same(entry.json_data(local_file(directory, 'fixture.json', 65536)), wanted_model, 'ammunition model differs')
    expected = dict(base, manifest=manifest, manifest_sha256=digest(manifest_raw), profile=profile,
                    profile_sha256=digest(profile_raw), raw=raw, state=state, fixture=str(directory), ammo_export=export)
    import account_switch_expectations as expectations
    public = expectations.snapshot(expected, compatibility)
    return expected, public, {'status': 'PASS', 'fixture': str(directory), 'base_fixture': str(base_directory),
        'manifest_sha256': digest(manifest_raw), 'profile_sha256': digest(profile_raw),
        'base_profile_sha256': digest(base_raw), 'account_id': expected['account_id'],
        'native_database_id': expected['native_id'], 'nickname': expected['name'],
        'payloads': {k: {'bytes': len(v), 'sha256': digest(v)} for k, v in raw.items()},
        'literal_delta': delta, 'exact_byte_delta': byte_delta, 'public_snapshot': public,
        'native_compatibility': 'NOT_RUN until independent native delivery and original GUI gates'}


def source_manifest_rows(manifest):
    require(type(manifest) is dict and set(manifest) == {'version', 'files'}
            and type(manifest['version']) is int and manifest['version'] == 1,
            'exact build source manifest envelope required')
    rows = manifest['files']
    require(type(rows) is list and 1 <= len(rows) < 1000, 'bounded build source manifest required')
    names, total = set(), 0
    allowed = ('tools/wg_probe/src/', 'local/vendor/wg-toolkit-rs/wg-toolkit/src/',
               'local/vendor/wg-toolkit-rs/serde-pickle/src/')
    fixed = {'tools/wg_probe/Cargo.toml', 'tools/wg_probe/Cargo.lock',
             'local/vendor/wg-toolkit-rs/Cargo.toml', 'local/vendor/wg-toolkit-rs/wg-toolkit/Cargo.toml',
             'local/vendor/wg-toolkit-rs/serde-pickle/Cargo.toml',
             'local/vendor/wg-toolkit-rs/wg-toolkit/build.rs', 'local/vendor/wg-toolkit-rs/serde-pickle/build.rs'}
    for row in rows:
        require(type(row) is dict and set(row) == {'relative_path', 'bytes', 'sha256'}, 'build source record shape differs')
        name = row['relative_path']
        require(type(name) is str and name not in names and '\\' not in name and ':' not in name
                and not name.startswith('/') and all(p not in ('', '.', '..') for p in name.split('/'))
                and (name in fixed or name.startswith(allowed)), 'duplicate/out-of-scope build source path')
        names.add(name)
        total += integer(row['bytes'], 1, 4 * 1024 * 1024 - 1)
        require(type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'build source digest shape differs')
    require(total < 16 * 1024 * 1024 and fixed - {p for p in fixed if p.endswith('build.rs')} <= names
            and {'tools/wg_probe/src/hangar091.rs', 'tools/wg_probe/src/gateway091.rs'} <= names,
            'build source inputs/budget incomplete')
    return rows


def build_chronology(before, stopped, test, build, built, start, started, after, outcome):
    stamps = [before['captured_utc'], stopped['captured_utc'], test['started_utc'], test['finished_utc'],
              build['started_utc'], build['finished_utc'], built['captured_utc'], start['started_utc'],
              start['finished_utc'], started['captured_utc'], after['captured_utc'],
              outcome['started_utc'], outcome['finished_utc']]
    times = [previous.utc_timestamp(s) for s in stamps]
    require(all(a <= b for a, b in zip(times, times[1:])) and times[-2] < times[-1],
            'saved stop/test/build/start/client order differs')
    return {'startup_observed_utc': started['captured_utc'], 'client_started_utc': outcome['started_utc'],
            'client_start_after_observed_start_seconds': (times[-2] - times[-4]).total_seconds(),
            'stop_uses_capture_utc_not_stale_state_utc': True}


def backend_build(directory, outcome, local_root):
    directory = entry.owned(directory, local_root, True)
    require(type(BUILD_HELPER_SHA) is str and type(BUILD_MANIFEST_SHA) is str,
            'reviewed ammunition build inputs are not frozen; native acceptance NOT_RUN')
    files = []
    def saved(name, maximum=262144, decode=True):
        raw = local_file(directory, name, maximum)
        files.append({'file': str(directory / name), 'bytes': len(raw), 'sha256': digest(raw)})
        return entry.json_data(raw) if decode else raw
    helper = read_limited(directory.parent / 'rebuild_server.py', 65536)
    require(digest(helper) == BUILD_HELPER_SHA, 'reviewed two-stage build helper changed')
    files.append({'file': str(directory.parent / 'rebuild_server.py'), 'bytes': len(helper), 'sha256': digest(helper)})
    manifest_raw = saved('source-manifest.json', 1024 * 1024, False)
    require(digest(manifest_raw) == BUILD_MANIFEST_SHA, 'frozen actual Cargo input manifest changed')
    sources = source_manifest_rows(entry.json_data(manifest_raw))
    for row in sources:
        source = local_file(directory / 'sources', row['relative_path'], 4 * 1024 * 1024)
        require(len(source) == row['bytes'] and digest(source) == row['sha256'], 'saved actual build source changed')
    own = {r['relative_path']: r['sha256'] for r in sources}
    require(own['tools/wg_probe/src/hangar091.rs'] == HANGAR_SHA
            and own['tools/wg_probe/src/gateway091.rs'] == previous.GATEWAY_SHA,
            'ammunition loader or unchanged native gateway source differs')
    before, stopped, built, started, after = [saved(n + '.json') for n in ('before', 'stop', 'built', 'start', 'after')]
    test, build, start, stop = [saved(n + '.command.json') for n in ('cargo-test', 'cargo-build', 'start', 'stop')]
    logs = {n: saved(n + '.log', 4 * 1024 * 1024, False) for n in (
        'cargo-test.stdout', 'cargo-test.stderr', 'cargo-build.stdout', 'cargo-build.stderr',
        'stop.stdout', 'stop.stderr', 'start.stdout', 'start.stderr')}
    old_exe = saved('gateway-before.exe', 64 * 1024 * 1024, False)
    new_exe = saved('gateway-built.exe', 64 * 1024 * 1024, False)
    new_sha = digest(new_exe)
    require(before.get('status') == built.get('status') == after.get('status') == 'PASS'
            and before.get('source_manifest_sha256') == built.get('source_manifest_sha256')
            == after.get('source_manifest_sha256') == BUILD_MANIFEST_SHA
            and before.get('old_executable_sha256') == after.get('old_executable_sha256')
            == digest(old_exe) == previous.GATEWAY_EXE_SHA
            and built.get('executable_sha256') == after.get('executable_sha256') == new_sha
            and new_sha != previous.GATEWAY_EXE_SHA and built.get('server') == 'STOPPED'
            and built.get('client_started') is False, 'saved old/source/new executable chain differs')
    cargo = ROOT / 'local/toolchains/rustup/toolchains/1.90.0-x86_64-pc-windows-gnu/bin/cargo.exe'
    for command, verb in ((test, 'test'), (build, 'build')):
        require(type(command.get('exit_code')) is int and command['exit_code'] == 0
                and command.get('argv') == [str(cargo), verb, '--offline', '--locked', '--manifest-path', 'tools/wg_probe/Cargo.toml']
                and Path(command.get('cwd', '')).resolve() == ROOT, 'pinned successful direct offline Cargo command required')
    require(b'test result: ok.' in logs['cargo-test.stdout'] and b'FAILED' not in logs['cargo-test.stdout']
            and b'Finished `dev` profile' in logs['cargo-build.stderr'] and not logs['cargo-build.stdout'],
            'actual Rust test/build output missing or failed')
    for command, verb, captured in ((stop, 'stop', False), (start, 'start', True)):
        argv = command.get('argv')
        tail = ['-B', '-X', 'utf8', 'tools/local_server.py', verb, '--config', 'local/server/service.json']
        if captured: tail.append('--capture')
        require(type(command.get('exit_code')) is int and command['exit_code'] == 0
                and type(argv) is list and len(argv) == len(tail) + 1
                and Path(argv[0]).is_absolute() and Path(argv[0]).name.lower() == 'python.exe'
                and argv[1:] == tail and Path(command.get('cwd', '')).resolve() == ROOT,
                'saved successful owned server stop/start command required')
    require(not logs['stop.stderr'] and not logs['start.stderr'], 'server stop/start recorded an error')
    crew.same(entry.json_data(logs['stop.stdout']), stopped['state'], 'stop command/state bytes differ')
    crew.same(entry.json_data(logs['start.stdout']), started['state'], 'start command/state bytes differ')
    crew.same(started['state'], after['state'], 'after/start state differs')
    state = after['state']
    require(stopped.get('status') == stopped['state'].get('status') == 'STOPPED'
            and stopped['state'].get('run_dir') == before['state'].get('run_dir')
            and started.get('status') == state.get('status') == 'RUNNING'
            and state.get('run_dir') != before['state'].get('run_dir')
            and state.get('native_wire_capture') is True and state.get('website_owned') is False
            and after.get('client_started') is False and after.get('website_restarted') is False,
            'saved owned service scope differs')
    processes = state.get('processes')
    require(type(processes) is list and len(processes) == 2
            and {p.get('role') for p in processes} == {'identity', 'gateway'}, 'owned process set differs')
    gateway = next(p for p in processes if p['role'] == 'gateway')
    integer(gateway.get('pid'), 1, 2**32 - 1)
    require(Path(gateway.get('executable', '')).resolve() == ROOT / 'local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe'
            and gateway.get('executable_sha256') == new_sha, 'recorded started image differs from new executable')
    run = entry.owned(state['run_dir'], local_root, True)
    require(Path(outcome.get('gateway_run', '')).resolve() == run
            and Path(outcome.get('wire_source', '')).resolve() == run / 'wire', 'native run used another gateway build')
    crew.same(before['config_checks'], after['config_checks'], 'server configuration changed during rebuild')
    configuration = after['config_checks']
    require(type(configuration) is list and len(configuration) == 4
            and {r.get('path') for r in configuration} == {'config/project.local.json', 'local/server/service.json', 'local/server/bridge.json', 'local/server/gateway.json'}
            and all(set(r) == {'path', 'sha256'} and re.fullmatch('[0-9a-f]{64}', r['sha256']) for r in configuration),
            'configuration preservation hash set differs')
    chronology = build_chronology(before, stopped, test, build, built, start, started, after, outcome)
    require(previous.utc_timestamp(stop['finished_utc']) <= previous.utc_timestamp(stopped['captured_utc']),
            'stop evidence capture preceded successful command completion')
    return {'status': 'PASS', 'directory': str(directory), 'files': files, 'source_inputs': sources,
            'source_manifest_sha256': BUILD_MANIFEST_SHA, 'gateway_run': str(run), 'gateway_pid_at_start': gateway['pid'],
            'executable_sha256': new_sha, 'previous_executable_sha256': digest(old_exe), 'chronology': chronology,
            'current_service_state_required': False,
            'scope': 'Saved complete own/path-dependency sources, direct offline locked Cargo build, immutable image copy and observed startup; no live process inspected.'}


def native_sources(value):
    require(type(value) is list and len(value) == len(PROBE_SOURCES), 'thirteen exact original ammunition sources required')
    original = config()[1]['original_client_root']
    for row, (relative, pin) in zip(value, PROBE_SOURCES):
        require(type(row) is dict and set(row) == {'relative_path', 'bytes', 'sha256'}
                and row.get('relative_path') == relative and row.get('sha256') == pin, 'original ammunition source identity differs')
        raw = local_file(original, relative, 1024 * 1024)
        require(integer(row.get('bytes'), 1, 1024 * 1024) == len(raw) and digest(raw) == pin,
                'original ammunition source bytes differ')
    return value


def ammo_observation(value, expected, loaded=True, selected_ms1=True):
    require(type(value) is dict, 'native ammunition observation object required')
    keys = {'version', 'type_name', 'type_id', 'vehicle_inventory_id', 'vehicle_type_compact_descr',
            'vehicle_compact_descr_sha256', 'turret', 'gun', 'max_ammo', 'shell_item_type', 'shells',
            'native_empty_ammo', 'native_default_ammo', 'observation', 'selection_before', 'selection_after',
            'selection_unchanged', 'inventory_mutation_requested', 'loaded_module_files'}
    require(keys <= set(value) <= keys | {'sources', 'observation_index'}, 'native ammunition observation schema differs')
    fixed = {'version': 1, 'type_name': 'ussr:MS-1', 'type_id': [0, 13], 'vehicle_inventory_id': 1,
             'vehicle_type_compact_descr': 3329,
             'vehicle_compact_descr_sha256': digest(expected['state'][b'inventory'][1][b'compDescr'][1]),
             'turret': {'resource_name': 'T-18_Standart', 'compact_descr': 5891},
             'gun': {'resource_name': '_37mm_Gochkins', 'compact_descr': 5892},
             'max_ammo': 96, 'shell_item_type': 10, 'selection_unchanged': True, 'inventory_mutation_requested': False,
             'native_empty_ammo': [2570, 0, 2826, 0, 3082, 0],
             'native_default_ammo': [2570, 96, 2826, 0, 3082, 0]}
    for key, wanted in fixed.items():
        require(same_tree(value.get(key), wanted), 'native original mounted ammunition contract differs')
    shells = [{'resource_name': name, 'item_id': [0, item], 'compact_descr': compact,
               'kind': kind, 'compatible_with_mounted_gun': True} for name, item, compact, kind in SHELLS]
    require(same_tree(value.get('shells'), shells), 'native ordered shell types/compatibility differ')
    selected = value.get('selection_before')
    require(type(selected) is dict and set(selected) == {'database_id', 'selected_inventory_id', 'selected_descriptor_sha256'}
            and same_tree(selected, value.get('selection_after'))
            and type(selected['database_id']) is int and selected['database_id'] == expected['native_id'],
            'native ammo read changed Account or selection')
    identifier = integer(selected['selected_inventory_id'], 1, 2)
    require((not selected_ms1 or identifier == 1)
            and selected['selected_descriptor_sha256'] == digest(expected['state'][b'inventory'][1][b'compDescr'][identifier]),
            'native ammo read references a foreign selected vehicle')
    files = value['loaded_module_files']
    require(type(files) is dict and set(files) == {'vehicles', 'account_shared'}
            and all(type(s) is str and 1 <= len(s) <= 1024 for s in files.values())
            and files['vehicles'].replace('\\', '/').lower().endswith('items/vehicles.pyc')
            and files['account_shared'].replace('\\', '/').lower().endswith('account_shared.pyc'),
            'original native module file provenance differs')
    observation = value.get('observation')
    fields = {'raw_shells', 'raw_layouts', 'layout_index', 'mounted_layout_present', 'storage_shells', 'gui_shells',
              'native_loaded_pairs', 'native_layout_rows', 'ammo_sum', 'default_ammo_sum', 'ammo_max_size',
              'is_ammo_full', 'is_auto_load'}
    require(type(observation) is dict and set(observation) == fields, 'native ammo getter projection schema differs')
    counts = (20, 0, 0) if loaded else (0, 0, 0)
    defaults = (20, 0, 0) if loaded else (96, 0, 0)
    fixed = {
        'raw_shells': FLAT if loaded else [], 'raw_layouts': [{'layout_index': list(LAYOUT), 'shells': FLAT}] if loaded else [],
        'layout_index': list(LAYOUT), 'mounted_layout_present': loaded, 'storage_shells': [],
        'native_loaded_pairs': [[shell[2], count] for shell, count in zip(SHELLS, counts)] if loaded else [],
        'native_layout_rows': [[shell[2], count, False] for shell, count in zip(SHELLS, defaults)],
        'ammo_sum': sum(counts), 'default_ammo_sum': sum(defaults), 'ammo_max_size': 96,
        'is_ammo_full': loaded, 'is_auto_load': False}
    for key, wanted in fixed.items():
        require(same_tree(observation.get(key), wanted), 'actual raw/iterator/layout/storage count differs from explicit grant')
    gui = observation.get('gui_shells')
    require(type(gui) is list and len(gui) == 3, 'three actual original GUI shell getters required')
    for row, shell, count, default in zip(gui, SHELLS, counts, defaults):
        require(type(row) is dict and set(row) == {'compact_descr', 'kind', 'count', 'default_count', 'is_bought_for_credits',
                                                'default_layout_value', 'inventory_count', 'buy_price', 'default_price'},
                'GUI shell getter shape differs')
        required = {'compact_descr': shell[2], 'kind': shell[3], 'count': count, 'default_count': default,
                    'is_bought_for_credits': False, 'default_layout_value': [shell[2], default], 'inventory_count': 0}
        for key, wanted in required.items():
            require(same_tree(row[key], wanted), 'GUI shell getter disagrees with authoritative count/layout')
        for key in ('buy_price', 'default_price'):
            require(type(row[key]) is list and len(row[key]) == 2, 'bounded observed price pair required')
            for amount in row[key]: integer(amount)
    if 'sources' in value: native_sources(value['sources'])
    if 'observation_index' in value: integer(value['observation_index'], 1, 8)
    return observation


def export_evidence(path, base, local_root):
    raw = read_limited(path, 65536)
    value = entry.json_data(raw)
    require(type(value) is dict and set(value) == {'version', 'kind', 'data', 'source'}
            and type(value['version']) is int and value['version'] == 1 and value['kind'] == 'native-ms1-ammo',
            'exact native ammunition export envelope required')
    proof = value['source']
    require(type(proof) is dict and set(proof) == {'trace_file', 'trace_sha256', 'record_index', 'install_plan_file',
                                                'install_plan_sha256', 'outcome_file', 'outcome_sha256'},
            'exact actual native export provenance required')
    paths = {}
    for name in ('trace', 'install_plan', 'outcome'):
        paths[name] = entry.owned(proof[name + '_file'], local_root)
        require(digest(read_limited(paths[name], 17 * 1024 * 1024)) == proof[name + '_sha256'],
                'native ammunition export source hash differs')
    require(paths['install_plan'].parent == paths['outcome'].parent, 'export plan/outcome came from different runs')
    install = paths['outcome'].parent
    plan, outcome, rows, original, _ = artifacts(install, local_root, 'export')
    require(Path(original['trace']['path']).resolve() == paths['trace'], 'export trace path differs from actual native process')
    compiled = compiled_sources(install, plan, outcome, 'export')
    process = previous.process_runtime(install, plan, outcome, rows)
    require(process.get('status') == 'PASS', 'native ammunition export process/lifecycle failed')
    index = integer(proof['record_index'], 0, len(rows) - 1)
    record = dict(rows[index])
    require(record.pop('event') == 'ms1_ammo_descriptors', 'export did not originate from the actual native descriptor event')
    record.pop('elapsed_seconds')
    require(same_tree(record, value['data']), 'native export data differs from recorded original observation')
    data = value['data']
    require('sources' in data and 'observation_index' not in data, 'one explicit native export required')
    ammo_observation(data, base, loaded=False, selected_ms1=False)
    exported = [i for i, r in enumerate(rows) if r['event'] == 'ms1_ammo_descriptors']
    condition_i, condition = previous.only(rows, 'diagnostic_condition_complete')
    fini_i, _ = previous.only(rows, 'fini_enter')
    logged = [(i, r) for i, r in enumerate(rows) if r['event'] == 'connection_callback' and i < fini_i]
    require(exported == [index] and len(logged) == 1 and logged[0][1].get('stage') == 1
            and logged[0][1].get('status') == 'LOGGED_ON' and logged[0][1].get('native_connected') is True
            and logged[0][0] < index < condition_i < fini_i
            and condition.get('condition') == 'ms1_ammo_exported' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False, 'native export actual login/conditional exit differs')
    return value, {'status': 'PASS', 'file': str(path), 'bytes': len(raw), 'sha256': digest(raw),
                   'original_install': str(install), 'original': original, 'compiled_sources': compiled,
                   'process_runtime_status': process['status'], 'original_sources': data['sources'],
                   'descriptor_line': index + 1, 'source_gateway_run': outcome['gateway_run'],
                   'scope': 'Original inventory/descriptor export before grant; this does not establish populated ammunition delivery.'}


def lifecycle(rows, plan, outcome):
    public_control(outcome)
    fini, _ = previous.only(rows, 'fini_enter')
    callbacks = [(i, r) for i, r in enumerate(rows) if r['event'] == 'connection_callback']
    live = [(i, r) for i, r in callbacks if i < fini]
    require(len(live) == 1 and live[0][1].get('stage') == 1 and live[0][1].get('status') == 'LOGGED_ON'
            and live[0][1].get('native_connected') is True and live[0][1].get('after_fini') is False
            and all(r.get('original_callback') == 'ConnectionManager.connectionWatcher' for _, r in callbacks),
            'one actual uninterrupted native authentication required')
    require(all(i > fini and r.get('stage') == 6 and r.get('native_connected') is False
                for i, r in callbacks if i != live[0][0]), 'unexpected native connection transition')
    connected = live[0][0]
    constructors = {}
    for line, offset in ((47, 674), (1640, 298)):
        selected = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call'
                    and r.get('method') == '__init__' and r.get('source_line') == line]
        pairs = crew.pairs([r for _, r in selected], 'native_account_call', '__init__', 'scripts/client/Account.py', line, offset)
        require(len(pairs) == 1, 'one fresh original Account/repository constructor required')
        p = pairs[0]
        constructors[line] = (selected[p[0]][0], selected[p[2]][0], p[1]['owner_id'])
    require(len([r for r in rows if r['event'] == 'native_account_call' and r.get('method') == '__init__']) == 4,
            'extra Account or repository construction')
    a, repository = constructors[47], constructors[1640]
    becomes = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_account_call'
               and r.get('method') == 'onBecomePlayer' and r.get('phase') == 'call' and r.get('offset') == -1]
    require(len(becomes) == 1 and becomes[0][1].get('source') == 'scripts/client/Account.py'
            and becomes[0][1].get('source_line') == 210
            and connected < a[0] < repository[0] < repository[1] < a[1] < becomes[0][0] < fini,
            'original Account construction preceded authenticated callback or escaped its lifetime')
    gone = crew.pairs(rows, 'native_account_call', 'onBecomeNonPlayer', 'scripts/client/Account.py', 246, 366)
    require(len(gone) == 1 and gone[0][0] > fini, 'Account disappeared before final native cleanup')
    control_i, consumed = previous.only(rows, 'test_control_consumed')
    submitted = [(i, r) for i, r in enumerate(rows) if r['event'] == 'project_login_submit']
    diagnostic = [(i, r) for i, r in enumerate(rows) if r['event'] == 'diagnostic_login_submit']
    require(len(submitted) == 1 and len(diagnostic) == 2
            and [r.get('phase') for _, r in diagnostic] == ['begin', 'return']
            and all(r.get('source') == 'original_LoginView.onLogin' and r.get('submit_via') == 'python' for _, r in diagnostic)
            and submitted[0][1].get('source') == 'original_LoginView.onLogin'
            and submitted[0][1].get('credentials_logged') is False and submitted[0][1].get('endpoint') == '127.0.0.1:20014'
            and control_i < diagnostic[0][0] < submitted[0][0] < diagnostic[1][0] < connected,
            'one real original diagnostic login submission required')
    require(consumed.get('verify_ms1_ammo') is True and consumed.get('export_ms1_ammo') is False
            and consumed.get('verify_long_hangar') is False
            and all(consumed.get(k) is False for k in OTHER_OPERATIONS if k != 'alternate_credentials_present')
            and consumed.get('credentials_present') is True and consumed.get('input_removed') is True
            and consumed.get('quit_after_seconds') is None and type(plan['settings'].get('test_control')) is str,
            'native one-shot ammunition control flags differ')
    return {'status': 'PASS', 'native_sessions': 1, 'native_accounts': 1, 'native_repositories': 1,
            'actual_logins': 1, 'connected_line': connected + 1, 'fini_line': fini + 1, 'account_owner': a[2],
            'account_constructor_lines': [a[0] + 1, a[1] + 1]}


def expected_public_ammo(expected, public):
    return {'version': 1, 'account': public, 'vehicle_inventory_id': 1,
            'vehicle_compact_descr_sha256': digest(expected['state'][b'inventory'][1][b'compDescr'][1]),
            'turret_compact_descr': 5891, 'gun_compact_descr': 5892, 'max_ammo': 96,
            'shells': [{'compact_descr': cd, 'count': count} for cd, count in zip(FLAT[::2], FLAT[1::2])],
            'auto_load': False, 'storage_shells': []}


def observation_state(value, public, account_owner):
    require(type(value) is dict and set(value) == {'account_state', 'account_owner', 'ammunition_owner', 'ammunition_flash_bound'},
            'exact native ammunition owner/context required')
    switch.context(value['account_state'], public)
    require(integer(value['account_owner'], 1, 2**64 - 1) == account_owner
            and value['ammunition_flash_bound'] is True, 'native ammunition Account/Flash owner differs')
    integer(value['ammunition_owner'], 1, 2**64 - 1)
    return value


def scenario(rows, plan, expected, public, life, local_root):
    require(life.get('status') == 'PASS', 'actual single Account lifetime required')
    names = ('ms1_ammo_start', 'ms1_ammo_complete', 'diagnostic_condition_complete', 'quit_requested', 'fini_enter')
    selected = {name: previous.only(rows, name) for name in names}
    positions = [selected[name][0] for name in names]
    require(positions == sorted(set(positions)), 'ammo start/completion/condition/quit/fini order differs')
    begin, end = positions[:2]
    start, complete, condition = (selected[name][1] for name in names[:3])
    # Construction/arming is deliberately possible while waiting for login.
    # Only actual observations/actions may establish the authenticated interval.
    require(life['connected_line'] - 1 < end < life['fini_line'] - 1,
            'ammunition scenario escaped authenticated lifetime')
    events = [(i, r) for i, r in enumerate(rows) if r['event'].startswith('ms1_ammo_')]
    allowed = {'ms1_ammo_start', 'ms1_ammo_state', 'ms1_ammo_snapshot', 'ms1_ammo_screenshot_requested',
               'ms1_ammo_screenshot', 'ms1_ammo_complete', 'ms1_ammo_action', 'ms1_ammo_observation'}
    require(events and all(r['event'] in allowed and type(r.get('version')) is int and r['version'] == 1 for _, r in events),
            'unknown/error/version-mismatched ammunition event')
    account_ready = life['account_constructor_lines'][1] - 1
    consumed = previous.only(rows, 'test_control_consumed')[0]
    require(consumed < begin and all(max(begin, account_ready) < i <= end for i, r in events
                                    if r['event'] != 'ms1_ammo_start'),
            'ammunition observation/action escaped the constructed Account lifetime')
    require(not any(r['event'] == 'diagnostic_condition_failed' or r['event'].endswith('_scenario_start')
                    for r in rows), 'another diagnostic scenario ran or a native condition failed')
    wanted = {'expected': expected_public_ammo(expected, public), 'required_stable_seconds': 15.0,
              'hold_seconds': 16.0, 'middle_seconds': 8.0, 'max_sample_gap': 2.5,
              'screenshot_basenames': ['ammo_start', 'ammo_end'], 'expected_snapshots': 3,
              'computer_input': False, 'inventory_mutation_requested': False, 'timed_exit': False,
              'native_pixels_review': 'NOT_RUN', 'human_manual_acceptance': 'NOT_RUN'}
    for key, value in wanted.items():
        crew.same(start.get(key), value, 'ammunition scenario input/bound/scope differs')
    require(start.get('phase') == 'waiting_hangar' and complete.get('phase') == 'complete'
            and complete.get('screenshots') == 2 and complete.get('observations') == 3
            and all(complete.get(k) is False for k in ('computer_input', 'inventory_mutation_requested', 'timed_exit'))
            and complete.get('native_pixels_review') == complete.get('human_manual_acceptance') == 'NOT_RUN'
            and condition.get('condition') == 'ms1_ammo_observed' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False, 'native conditional ammunition completion differs')
    states = [(i, r) for i, r in events if r['event'] == 'ms1_ammo_state']
    require(2 <= len(states) <= 160, 'bounded continuous native ammo states required')
    identity, times = None, []
    for n, (i, row) in enumerate(states):
        state = observation_state(row.get('state'), public, life['account_owner'])
        if identity is None: identity = state
        require(same_tree(state, identity) and begin < i < end and row.get('phase') == 'stable_hangar',
                'actual Account/ammunition/Hangar/crew state changed')
        now = number(row.get('observed_at'), 0, 1e9)
        if times: require(0 < now - times[-1] <= 2.5, 'native ammo sample time gap/order differs')
        times.append(now)
        require(row.get('began_at') == times[0] and type(row.get('samples')) is int and row['samples'] == n + 1
                and number(row.get('stable_seconds'), 0, 400) == now - times[0]
                and number(row.get('max_gap'), 0, 2.5) == max((b - a for a, b in zip(times, times[1:])), default=0.0),
                'native ammo cumulative observation measures differ')
    require(times[-1] - times[0] >= 16 and complete.get('began_at') == times[0]
            and complete.get('ended_at') == times[-1] and complete.get('stable_seconds') == times[-1] - times[0]
            and complete.get('samples') == len(states) and complete.get('max_gap') == states[-1][1]['max_gap'],
            'ammunition completion duration/sample summary differs')
    ready = previous.ready_interval(rows, states[0][0], states[-1][0], expected, 15.0)
    probes = [(i, r) for i, r in events if r['event'] == 'ms1_ammo_observation']
    snapshots = [(i, r) for i, r in events if r['event'] == 'ms1_ammo_snapshot']
    require(len(probes) == len(snapshots) == 3, 'three independent native ammunition reads/snapshots required')
    fingerprints, observations, snapshot_proof = [], [], []
    for n, ((probe_i, probe), (i, row)) in enumerate(zip(probes, snapshots)):
        data = {k: v for k, v in probe.items() if k not in ('event', 'elapsed_seconds')}
        require(integer(data.get('observation_index'), 1, 8) == n + 1
                and ('sources' in data) is (n == 0), 'native ammunition observation index/source coverage differs')
        observed = ammo_observation(data, expected)
        value = {'account': public, 'ammo': observed}
        fingerprint = switch.fingerprint(value)
        require(same_tree(row.get('snapshot'), value) and row.get('fingerprint') == fingerprint
                and row.get('moment') == ('start', 'middle', 'end')[n]
                and row.get('ammo_observation_index') == n + 1
                and row.get('inventory_mutation_requested') is False and row.get('selection_changed_by_observer') is False,
                'actual ammo snapshot/fingerprint/native read binding differs')
        preceding = [(j, s) for j, s in states if j < i]
        require(preceding and preceding[-1][0] < probe_i < i < end
                and row.get('observed_at') == preceding[-1][1]['observed_at']
                and 0 <= row['elapsed_seconds'] - preceding[-1][1]['elapsed_seconds'] <= 2.5,
                'ammo snapshot moved outside its original state/read iteration')
        age = row['observed_at'] - times[0]
        require(age == 0 if n == 0 else (8 <= age <= 10.5 if n == 1 else 16 <= age <= 18.5),
                'native ammo snapshot start/middle/end timing differs')
        fingerprints.append(fingerprint); observations.append(observed)
        snapshot_proof.append({'moment': row['moment'], 'line': i + 1, 'native_observation_line': probe_i + 1,
                               'fingerprint': fingerprint, 'ready_seconds': age})
    require(len(set(fingerprints)) == 1 and complete.get('snapshot_fingerprints') == fingerprints,
            'native account/ammunition changed during stable interval')
    requests = [(i, r) for i, r in events if r['event'] == 'ms1_ammo_screenshot_requested']
    shots = [(i, r) for i, r in events if r['event'] == 'ms1_ammo_screenshot']
    require(len(requests) == len(shots) == 2, 'two native ammunition screenshot requests/completions required')
    require(shots[0][0] < snapshots[2][0], 'initial ammunition PNG completed after the final snapshot')
    directory = entry.owned(plan['settings']['screenshot_dir'], local_root, True)
    images = []
    for n, basename in enumerate(('ammo_start', 'ammo_end')):
        req_i, req = requests[n]; shot_i, shot = shots[n]
        snapshot_i, snapshot = snapshots[n * 2]
        preceding = [(j, s) for j, s in states if j < shot_i]
        require(snapshot_i < req_i < shot_i < end and req.get('basename') == basename
                and req.get('writer') == 'BigWorld.screenShot' and req.get('extension') == 'png'
                and req.get('observed_at') == snapshot['observed_at'] and preceding
                and shot.get('observed_at') == preceding[-1][1]['observed_at']
                and same_tree(shot.get('state'), identity)
                and 0 <= shot['elapsed_seconds'] - preceding[-1][1]['elapsed_seconds'] <= 2.5,
                'native PNG was not taken in the actual ready snapshot interval')
        proof = shot.get('screenshot', {})
        path = entry.owned(proof['path'], local_root)
        require(path.parent == directory and proof.get('basename') == basename
                and re.fullmatch(basename + r'_[0-9]{3,10}\.png', path.name), 'native ammunition PNG path differs')
        raw = read_limited(path, 16 * 1024 * 1024)
        dimensions = crew.png_container(raw)
        require(integer(proof.get('bytes'), 1, 16 * 1024 * 1024) == len(raw) and proof.get('sha256') == digest(raw)
                and proof.get('dimensions') == dimensions and proof.get('png_container_valid') is True,
                'native ammunition PNG container/hash differs')
        images.append({'moment': ('start', 'end')[n], 'file': path.name, 'path': str(path),
                       'bytes': len(raw), 'sha256': digest(raw), 'dimensions': dimensions})
    actions = [r for _, r in events if r['event'] == 'ms1_ammo_action']
    require(not actions or len(actions) == 2 and [r.get('moment') for r in actions] == ['call', 'return']
            and all(r.get('action') == 'select_ms1' and r.get('inventory_id') == 1 and r.get('phase') == 'waiting_hangar' for r in actions)
            and actions[0].get('callback') == 'TankCarousel.vehicleChange', 'unmeasured ammunition scenario action')
    return {'status': 'PASS', 'observations': 3, 'snapshots': snapshot_proof, 'fingerprint': fingerprints[0],
            'native_ammunition': observations[0], 'continuous_ready': ready, 'state_samples': len(states),
            'account_owner': identity['account_owner'], 'ammunition_owner': identity['ammunition_owner'],
            'images': images, 'screenshots': 2, 'conditional_exit': 'ms1_ammo_observed',
            'human_manual_acceptance': 'NOT_RUN', 'scope': '20/96 loaded shells; legacy isAmmoFull is a minimum-load flag, not full capacity.'}


def visual(install, trace_sha, proof):
    require(proof.get('status') == 'PASS', 'native ammunition scenario required before visual acceptance')
    path = install / 'visual-review-ms1-ammo.json'
    if not path.is_file(): return {'status': 'NOT_RUN', 'reason': 'Actual native ammunition PNG review absent'}
    raw = read_limited(path, 65536); value = entry.json_data(raw)
    require(value.get('version') == 1 and value.get('source') == 'assistant_native_png_review'
            and value.get('trace_sha256') == trace_sha and type(value.get('images')) is list and len(value['images']) == 2,
            'ammunition visual review source/trace/image count differs')
    for image in proof['images']:
        matches = [r for r in value['images'] if type(r.get('file')) is str and
                   (r['file'] == image['file'] or Path(r['file']) == Path(image['path']))]
        require(len(matches) == 1 and matches[0].get('sha256') == image['sha256']
                and matches[0].get('moment') == image['moment']
                and all(matches[0].get(k) is True for k in ('hangar_visible', 'player_name_visible', 'ms1_visible',
                                                        'two_crew_visible', 'ammo_20_0_0_visible', 'resources_unchanged')),
                'native reviewed ammunition pixels failed or refer to another image')
    return {'status': 'PASS', 'file': str(path), 'sha256': digest(raw), 'reviewed_images': 2,
            'human_manual_acceptance': 'NOT_RUN'}


def flash_ammo_data(value):
    require(type(value) is dict and set(value) == {'gunName', 'maxAmmo', 'defaultAmmoCount', 'vehicleLocked',
                                                'stateMsg', 'stateLevel', 'stateWarning', 'shells'},
            'original ammo Flash argument shape differs')
    require(type(value['gunName']) is str and 1 <= len(value['gunName']) <= 256
            and type(value['maxAmmo']) is int and value['maxAmmo'] == 96
            and type(value['defaultAmmoCount']) is int and value['defaultAmmoCount'] == 20
            and value['vehicleLocked'] is False and type(value['stateMsg']) is str and len(value['stateMsg']) <= 4096
            and type(value['stateLevel']) is str and 1 <= len(value['stateLevel']) <= 64,
            'original MS-1 Flash capacity/default/load state differs')
    integer(value['stateWarning'], 0, 2147483647)
    shells = value['shells']
    require(type(shells) is list and len(shells) == 3, 'three original MS-1 Flash shell rows required')
    for row, shell, count in zip(shells, SHELLS, FLAT[1::2]):
        require(type(row) is dict and set(row) == {'id', 'type', 'label', 'icon', 'count', 'historicalBattleID'}
                and row['id'] == str(shell[2]) and row['type'] == shell[3]
                and type(row['count']) is int and row['count'] == count
                and type(row['label']) is str and 1 <= len(row['label']) <= 512
                and type(row['icon']) is str and 1 <= len(row['icon']) <= 512,
                'actual original Flash shell identity/count differs')
        if row['historicalBattleID'] is not None: integer(row['historicalBattleID'], -1, 2147483647)
    return {'maximum': 96, 'default_count': 20, 'shells': [{'compact_descr': s[2], 'count': n}
             for s, n in zip(SHELLS, FLAT[1::2])], 'total': 20}


def native_ammo_flash(rows, scenario_proof):
    require(scenario_proof.get('status') == 'PASS', 'ready ammunition scenario is required before Flash acceptance')
    selected = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_ammo_call']
    require(selected and len(selected) <= 4096, 'bounded original ammunition callback trace required')
    known = {r[2]: r for r in AMMO_SOURCES}
    pending, completed, seen = {}, [], set()
    for i, row in selected:
        method = row.get('method')
        require(method in known, 'unmeasured native ammunition callback')
        source, _, _, line, normal = known[method]
        require(row.get('source') == source and row.get('source_line') == line,
                'original ammo callback source identity differs')
        call_id = integer(row.get('call_id'), 1, 2**31 - 1)
        integer(row.get('owner_id'), 1, 2**64 - 1)
        if row.get('phase') == 'call':
            require(type(row.get('offset')) is int and row['offset'] == -1,
                    'native ammo callback did not enter its original function')
            require(call_id not in pending and call_id not in seen, 'reused native ammo callback identity')
            pending[call_id] = (i, row); seen.add(call_id)
        else:
            require(row.get('phase') == 'return' and call_id in pending, 'unmatched native ammo return')
            first_i, first = pending.pop(call_id)
            require(first['owner_id'] == row['owner_id'] and first['method'] == method
                    and type(first.get('flash_bound')) is bool and first['flash_bound'] is row.get('flash_bound'),
                    'native ammo callback owner/binding changed')
            fallback = method == 'as_setAmmoS' and row.get('offset') == 31 and row.get('flash_bound') is False
            require(type(row.get('offset')) is int and (row['offset'] == normal or fallback),
                    'native ammo callback did not reach an original normal return')
            if method == 'as_setAmmoS':
                require(same_tree(first.get('data'), row.get('data')), 'native ammo Flash arguments changed before return')
                require(fallback or row.get('flash_bound') is True, 'accepted ammo Flash branch is unbound')
            completed.append((first_i, first, i, row, fallback))
    require(not pending, 'unfinished native ammo callback')
    panels = [p for p in completed if p[1]['method'] == '__updateAmmo']
    success, pre_ready_unbound = [], 0
    first_ready = scenario_proof['continuous_ready']['first_line'] - 1
    last_ready = scenario_proof['continuous_ready']['last_line'] - 1
    for begin, call, end, returned, fallback in completed:
        if call['method'] != 'as_setAmmoS': continue
        if fallback:
            require(end < first_ready, 'unbound ammunition Flash call during accepted ready interval')
            pre_ready_unbound += 1
            continue
        parents = [p for p in panels if p[0] < begin < end < p[2] and p[1]['owner_id'] == call['owner_id']]
        require(len(parents) == 1 and call.get('parent_call_id') == returned.get('parent_call_id') == parents[0][1]['call_id']
                and call.get('parent_owner_id') == returned.get('parent_owner_id') == call['owner_id'],
                'native Flash ammo projection is not nested in the exact original panel callback')
        require(same_tree(parents[0][3].get('data'), call.get('data')),
                'original panel returned ammunition differs from its nested Flash argument')
        # Initial IS-7/empty/loading callbacks remain in the complete trace.
        # They cannot prove MS-1 acceptance and cannot replace its exact callback.
        data = call.get('data')
        if type(data) is not dict or data.get('maxAmmo') != 96:
            require(end < first_ready, 'another ammunition projection appeared during accepted MS-1 interval')
            continue
        projected = flash_ammo_data(data)
        require(call['owner_id'] == scenario_proof['ammunition_owner'] and end <= last_ready,
                'MS-1 Flash projection belongs to another panel or later lifetime')
        success.append({'call_id': call['call_id'], 'owner_id': call['owner_id'], 'call_line': begin + 1,
                        'return_line': end + 1, 'parent_call_id': parents[0][1]['call_id'], 'projection': projected})
    require(success and any(p['return_line'] < scenario_proof['snapshots'][0]['line'] for p in success),
            'original bound MS-1 ammo projection missing before first accepted snapshot')
    return {'status': 'PASS', 'projections': success, 'unbound_pre_ready_observations': pre_ready_unbound,
            'original_normal_returns': {'__updateAmmo': 504, 'as_setAmmoS': 27},
            'scope': 'Original nested bound Flash data is independently tied to native raw/getter snapshots; physical click/hover NOT_RUN.'}


SESSION_GATES = ('installation', 'compiled_sources', 'backend_build', 'process_runtime', 'client_profile',
                 'single_lifecycle', 'full_capture', 'wire', 'backend', 'cache', 'no_mutation_commands',
                 'native_account', 'original_crew_flash', 'hangar_data', 'scenario', 'original_ammo_flash', 'visual_review')


def verify_session(args, install, expected, public, password, local_root):
    checks = {}
    report = {'version': VERSION, 'original_install': str(install), 'checks': checks,
              'human_manual_acceptance': 'NOT_RUN'}
    stage = 'installation'
    try:
        plan, outcome, rows, original, backend_raw = artifacts(install, local_root)
        report['original'] = original
        checks[stage] = {'status': 'PASS', 'artifacts': original['artifacts'], 'trace': original['trace'],
                         'started_utc': outcome['started_utc'], 'finished_utc': outcome['finished_utc']}
        checks['compiled_sources'] = crew.checked(lambda: compiled_sources(install, plan, outcome))
        checks['backend_build'] = crew.checked(lambda: backend_build(args.build_proof, outcome, local_root))
        checks['process_runtime'] = crew.checked(lambda: previous.process_runtime(install, plan, outcome, rows))
        checks['process_runtime']['scope'] = 'One native EXE/init/fini and twelve cleanup stages; one authenticated Account lifetime is checked independently.'
        checks['client_profile'] = crew.checked(lambda: limits.client_profile(plan, rows, local_root))
        checks['single_lifecycle'] = crew.checked(lambda: lifecycle(rows, plan, outcome))
        stage = 'full_capture'
        captures, packets, checks[stage] = previous.read_capture(install, outcome)
        run = entry.owned(outcome['gateway_run'], local_root, True)
        client_digest = read_limited(run.parent / 'client-digest.bin', 16)
        private_path = entry.owned(args.private_key, local_root)
        stage = 'wire'
        wire = entry.wire(install, private_path, expected, password, client_digest,
                          dossier_cache=expected['dossier_cache'], cache_hints=True)
        checks[stage] = wire
        checks['backend'] = crew.checked(lambda: sustained.backend_single(backend_raw,
            entry.backend_binding(install, outcome, wire, expected, local_root), wire))
        checks['cache'] = crew.checked(lambda: crew.cache_backend(checks['backend'], wire, expected))
        checks['no_mutation_commands'] = crew.checked(lambda: limits.no_gameplay_commands(wire))
        checks['native_account'] = crew.checked(lambda: crew.native_account(rows, wire, expected))
        checks['original_crew_flash'] = crew.checked(lambda: crew.crew_flash(rows))
        def active_hangar():
            life = checks['single_lifecycle']
            require(life.get('status') == 'PASS', 'actual Account lifetime prerequisite missing')
            proof = crew.hangar(rows[life['connected_line'] - 1:life['fini_line'] - 1], expected)
            proof['module_policy'] = crew.module_policy_evidence(rows)
            require(proof['module_policy'].get('status') == 'PASS', 'unchanged module-change policy failed')
            return proof
        checks['hangar_data'] = crew.checked(active_hangar)
        checks['scenario'] = crew.checked(lambda: scenario(rows, plan, expected, public, checks['single_lifecycle'], local_root))
        checks['original_ammo_flash'] = crew.checked(lambda: native_ammo_flash(rows, checks['scenario']))
        checks['visual_review'] = crew.checked(lambda: visual(install, original['trace']['sha256'], checks['scenario']))
        for meta in original['artifacts'].values():
            raw = read_limited(Path(meta['file']), 8 * 1024 * 1024)
            require(len(raw) == meta['bytes'] and digest(raw) == meta['sha256'], 'original ammunition evidence changed during verification')
        require(digest(read_limited(Path(original['trace']['path']), 17 * 1024 * 1024)) == original['trace']['sha256'],
                'native ammunition trace changed during verification')
        for row, raw in zip(captures, packets):
            require(local_file(install / 'wire', row['file'], 4096) == raw, 'original encrypted packet changed during verification')
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = previous.failure(error)
    for name in SESSION_GATES:
        checks.setdefault(name, {'status': 'NOT_RUN', 'reason': 'Required earlier evidence gate did not complete'})
    report['identity_snapshot'] = {'account_id': expected['account_id'], 'native_database_id': expected['native_id'],
        'name': expected['name'], 'manifest_sha256': expected['manifest_sha256'], 'profile_sha256': expected['profile_sha256'],
        'payload_sha256': {name: digest(raw) for name, raw in expected['raw'].items()},
        'public_snapshot': public, 'dossier_cache': expected['dossier_cache'], 'loaded_ammunition': FLAT}
    report['status'] = crew.status(checks)
    return report


def relogin(current, earlier):
    require(current.get('status') == earlier.get('status') == 'PASS', 'two complete independent native sessions required')
    require(Path(current['original_install']) != Path(earlier['original_install']), 'relogin reused the same recorded process')
    require(same_tree(current['identity_snapshot'], earlier['identity_snapshot']), 'ammunition profile/identity/payload changed across relogin')
    now, before = current['checks'], earlier['checks']
    require(previous.utc_timestamp(before['installation']['finished_utc']) <= previous.utc_timestamp(now['installation']['started_utc']),
            'relogin process started before preceding native exit')
    require(current['original']['trace']['sha256'] != earlier['original']['trace']['sha256']
            and now['installation']['artifacts']['native-outcome.json']['sha256'] != before['installation']['artifacts']['native-outcome.json']['sha256'],
            'relogin reused prior trace/outcome evidence')
    require(Path(now['client_profile']['directory']) == Path(before['client_profile']['directory']), 'cached relogin used another native profile directory')
    crew.same(now['compiled_sources']['modules'], before['compiled_sources']['modules'], 'client sources changed across ammunition relogin')
    require(now['backend_build']['executable_sha256'] == before['backend_build']['executable_sha256'], 'server image changed across ammunition relogin')
    def hints(report, require_cached):
        return limits.cache_hint_snapshot({'checks': {'wire': report['checks']['wire'], 'cache_backend': report['checks']['cache']},
                                           'identity_snapshot': report['identity_snapshot']}, require_cached)
    current_hints, previous_hints = hints(current, True), hints(earlier, False)
    if previous_hints['shop_bytes']:
        require((current_hints['shop_bytes'], current_hints['shop_crc32_signed']) ==
                (previous_hints['shop_bytes'], previous_hints['shop_crc32_signed']), 'unchanged shop cache changed across relogin')
    if previous_hints['dossier_version']:
        require((current_hints['dossier_version'], current_hints['dossier_last_change_time']) ==
                (previous_hints['dossier_version'], previous_hints['dossier_last_change_time']), 'unchanged dossier cursor changed across relogin')
    require(current['checks']['scenario']['fingerprint'] == earlier['checks']['scenario']['fingerprint'],
            'native ammunition/account/crew getter snapshot changed across relogin')
    return {'status': 'PASS', 'previous_install': earlier['original_install'], 'current_install': current['original_install'],
            'native_profile_directory': now['client_profile']['directory'], 'previous_cache_hints': previous_hints,
            'current_cache_hints': current_hints, 'real_cached_relogin': True, 'native_sessions': 2,
            'account_hint_change_observed': current_hints['account_persistent_crc'] != previous_hints['account_persistent_crc'],
            'same_exact_authoritative_payloads': True, 'same_native_ammunition': True,
            'scope': 'First login may carry the pre-grant account descriptor. Each session independently receives the complete same profile4 state; initial/refresh CRC equality is checked within that session. Cache input is advisory, not authoritative state.'}


def verify(args):
    checks = {}
    report = {'version': VERSION, 'verifier_sha256': digest(read_limited(Path(__file__), 1024 * 1024)),
              'original_install': str(Path(args.install).resolve()), 'checks': checks,
              'human_manual_acceptance': 'NOT_RUN',
              'scope': 'One explicit twenty-AP test grant to native MS-1 with unchanged identity, resources, progression, crew and IS-7; no purchase, refill, firing or economy acceptance.'}
    stage = 'frozen_dependencies'
    try:
        local_root = config()[1]['local_artifacts_root']
        checks[stage] = dependencies()
        stage = 'base_fixture'
        fixture = entry.owned(args.fixture, local_root, True)
        manifest = entry.json_data(local_file(fixture, 'manifest.json', 262144))
        base_dir = entry.owned(manifest['preservation']['base_fixture']['directory'], local_root, True)
        require(digest(local_file(base_dir, 'manifest.json', 262144)) == BASE_MANIFEST_SHA
                and digest(local_file(base_dir, 'profile-input.json', 65536)) == BASE_PROFILE_SHA,
                'accepted profile3 ancestor differs')
        crew_export, crew_proof = crew.export_evidence(entry.owned(args.native_crew_export, local_root), local_root)
        base, checks[stage] = crew.crew_fixture(base_dir, crew_export, crew_proof, local_root)
        stage = 'native_ammo_export'
        exported, checks[stage] = export_evidence(entry.owned(args.native_ammo_export, local_root), base, local_root)
        stage = 'ammo_fixture'
        expected, public, checks[stage] = ammo_fixture(fixture, base, exported, checks['native_ammo_export'], local_root)
        stage = 'independent_identity'
        password, checks[stage] = crew.identity(expected, entry.owned(args.registration, local_root),
                                               entry.owned(args.credentials, local_root), args.case)
        stage = 'current_session'
        report['current'] = verify_session(args, entry.owned(args.install, local_root, True), expected, public, password, local_root)
        checks[stage] = {'status': report['current']['status']}
        if args.previous_install:
            stage = 'previous_session'
            report['previous'] = verify_session(args, entry.owned(args.previous_install, local_root, True), expected, public, password, local_root)
            checks[stage] = {'status': report['previous']['status']}
            report['paired_relogin'] = crew.checked(lambda: relogin(report['current'], report['previous']))
        else:
            report['paired_relogin'] = {'status': 'NOT_RUN', 'reason': 'A second independent cached native session is required for the card.'}
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = previous.failure(error)
    for name in ('frozen_dependencies', 'base_fixture', 'native_ammo_export', 'ammo_fixture', 'independent_identity', 'current_session'):
        checks.setdefault(name, {'status': 'NOT_RUN', 'reason': 'Required earlier evidence gate did not complete'})
    report.setdefault('paired_relogin', {'status': 'NOT_RUN', 'reason': 'Prerequisite native evidence unavailable'})
    report['status'] = crew.status(checks)
    report['card_status'] = crew.status({'session': {'status': report['status']}, 'paired_relogin': report['paired_relogin']})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'fixture', 'native-ammo-export', 'native-crew-export', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--build-proof', default=str(DEFAULT_BUILD))
    parser.add_argument('--previous-install')
    parser.add_argument('--registration', default=str(crew.DEFAULT_REG / 'registration.json'))
    parser.add_argument('--credentials', default=str(crew.DEFAULT_REG / 'test-credentials.json'))
    parser.add_argument('--case', default='operator_shared')
    parser.add_argument('--private-key', default=str(ROOT / 'local/server/native-private.pem'))
    args = parser.parse_args()
    out = output_dir(args.out)
    require(not any(out.iterdir()), 'ammunition verifier output must be fresh and empty')
    report = verify(args)
    path = out / 'ms1-ammo-verification.json'
    save_json(path, report)
    print(json.dumps({'status': report['status'], 'card_status': report['card_status'], 'report': str(path),
                      'sha256': digest(read_limited(path, 32 * 1024 * 1024))}))
    return 0 if report['status'] == 'PASS' and report['card_status'] != 'FAIL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
