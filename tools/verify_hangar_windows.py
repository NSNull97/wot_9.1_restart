"""Independent native evidence for two explicitly unavailable hangar windows.

The previous crew/limits verifiers are imported unchanged. No client, service,
database, fixture generator, incoming Python object or physical input is run.
"""
import argparse
import json
import math
from pathlib import Path
import re
import struct

import verify_hangar_limits as limits
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table, parse_pyc, records
from verify_hangar import digest, local_file, require

crew, entry = limits.crew, limits.entry
VERSION = 1
MODULES = limits.MODULES + ('hangar_windows_scenario',)
PANEL_SOURCE = 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py'
PANEL_SHA = '54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8'
METHODS = (
    ('appearance', 'showCustomization', 210, 31, 'd28d6e4e11a2034e09b5812b6a24657eb95eb6410ce82755b153e180eb3e08d4'),
    ('maintenance', 'showTechnicalMaintenance', 207, 25, '7e3f421e0d1abeb42750293bb4f1754b350bbd44f99c6c139c211797ebf8d527'),
)
UNSUPPORTED = (
    ('VehicleCustomization', 'scripts/client/gui/Scaleform/daapi/view/lobby/customization/VehicleCustomization.py',
     '69e84f26da398cc68e0a497841f6c399a2f0c8f96d7bb4846a3a168cb294357d', 62),
    ('TechnicalMaintenance', 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/TechnicalMaintenance.py',
     '11933820a86f74bebc5caae8f11a47d887bab911e517f51c2e1d17c094a2259d', 43),
)
SCREENSHOTS = ('windows_ms1', 'windows_appearance', 'windows_maintenance')
DEPENDENCIES = {'verify_ms1_crew_native.py': '91e6ad71a0b964406dd44d1954aad752695701e11e33385df28a8caf689ef522',
                'verify_hangar_limits.py': '73fa5db5bfaeabf3fd4c6c71301dd47435cf838abda60cb7c95668f974bc34f0'}


def frozen_dependencies():
    files = []
    for name, expected in DEPENDENCIES.items():
        path = ROOT / 'tools' / name
        actual = digest(read_limited(path, 1024 * 1024))
        require(actual == expected, 'previous acceptance verifier changed')
        files.append({'file': str(path), 'sha256': actual})
    return {'status': 'PASS', 'files': files}


def compiled_sources(install, plan, outcome):
    sources = plan.get('sources')
    require(type(sources) is list and len(sources) == 11, 'windows policy requires exactly eleven versioned modules')
    paths = [r.get('path') for r in sources]
    require(set(paths) == {'client_patch/' + n + '.py' for n in MODULES} and len(set(paths)) == 11,
            'unknown/missing/duplicate windows module')
    evidence = []
    for source in sources:
        name = Path(source['path']).stem
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        raw = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        files = [r for r in plan['files'] if r.get('path') == relative]
        require(len(files) == 1 and files[0].get('runtime_mutable') is False, 'compiled windows install identity')
        require(meta.get('source') == name + '.py' and meta.get('source_sha256') == source.get('sha256')
                and re.fullmatch('[0-9a-f]{64}', source.get('sha256', '')) is not None
                and meta.get('source_executed') is False and meta.get('magic') == '03f30d0a'
                and meta.get('compiler', '').startswith('2.7.3 '), 'windows compiler metadata/source chain')
        sha = digest(raw)
        require(raw[:4] == bytes.fromhex('03f30d0a') and sha == meta.get('pyc_sha256') == files[0].get('installed_sha256'),
                'compiled windows byte/hash chain')
        require(local_file(install, 'postrun/' + relative, 1024 * 1024) == raw, 'runtime windows module changed')
        evidence.append({'module': name, 'source_sha256': source['sha256'], 'pyc_sha256': sha})
    crew.same(outcome.get('source_provenance', {}).get('modules'), evidence, 'windows runner/compiler provenance mismatch')
    return {'status': 'PASS', 'modules': evidence}


def original_contracts():
    opcode = read_limited(ROOT / 'local/vendor/cpython-2.7.18/opcode.py', 32768)
    require(digest(opcode) == 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884', 'opcode source hash')
    table = opcode_table(opcode.decode('utf8'))
    original = config()[1]['original_client_root']
    raw = local_file(original, 'res/' + PANEL_SOURCE + 'c', 1024 * 1024)
    require(digest(raw) == PANEL_SHA, 'original panel source hash')
    codes, disassembled, evidence = list(records(parse_pyc(raw))), inspect(raw, table), []
    for action, method, line, offset, sha in METHODS:
        code = [c for name, c in codes if name.split('.')[-1] == method and c['firstlineno'] == line]
        require(len(code) == 1 and digest(code[0]['code']) == sha and code[0]['argcount'] == 1
                and code[0]['varnames'][:1] == [b'self'], 'original window entry signature/code hash')
        functions = [r for r in disassembled if r['qualified_name'].split('.')[-1] == method and r['firstlineno'] == line]
        require(len(functions) == 1 and any(op['offset'] == offset and op['opname'] == 'RETURN_VALUE' for op in functions[0]['instructions'])
                and 'fireEvent' in functions[0]['names'], 'original window entry event/return contract')
        evidence.append({'action': action, 'method': method, 'source': PANEL_SOURCE, 'source_sha256': PANEL_SHA,
                         'code_sha256': sha, 'source_line': line, 'normal_return': offset})
    unsupported = []
    for name, source, sha, line in UNSUPPORTED:
        raw = local_file(original, 'res/' + source + 'c', 1024 * 1024)
        require(digest(raw) == sha, 'original unsupported window source hash')
        functions = [r for r in inspect(raw, table) if r['qualified_name'].split('.')[-1] == '_populate' and r['firstlineno'] == line]
        require(len(functions) == 1 and functions[0]['source_filename'] == source, 'original unsupported population identity')
        unsupported.append({'class_name': name, 'source': source, 'sha256': sha, 'method': '_populate', 'source_line': line})
    container_source = 'scripts/client/gui/Scaleform/framework/managers/containers.py'
    raw = local_file(original, 'res/' + container_source + 'c', 1024 * 1024)
    require(digest(raw) == '2eeb5825c15b99f1acacaec06db376973ecbfe37164172bd042c48b4e970753a', 'original container hash')
    parsed = inspect(raw, table)
    scans = []
    for method, line, offset in (('getView', 205, 109), ('getViewCount', 218, 145), ('__findByDictCriteria', 234, 160)):
        found = [r for r in parsed if r['qualified_name'] == '<module>._PopUpContainer.' + method and r['firstlineno'] == line]
        require(len(found) == 1 and any(op['offset'] == offset and op['opname'] == 'RETURN_VALUE' for op in found[0]['instructions']),
                'original popup query/return contract')
        if method == 'getView':
            require(any(op['offset'] == 15 and op['opname'] == 'POP_JUMP_IF_FALSE' and op['arg'] == 106
                        for op in found[0]['instructions']) and '_PopUpContainer__findByDictCriteria' in found[0]['names'],
                    'popup None bypass/dict lookup source differs')
        if method == '__findByDictCriteria':
            require('VIEW_ALIAS' in found[0]['names'], 'popup alias criterion absent')
        scans.append({'method': method, 'source_line': line, 'normal_return': offset})
    return {'status': 'PASS', 'entry_contracts': evidence, 'unsupported_populate': unsupported,
            'targeted_container_query': {'source': container_source, 'sha256': digest(raw), 'methods': scans,
                                        'unqualified_getView_proves_absence': False},
            'scope': 'Original bytecode read as bounded data; these unsupported windows were not executed.'}


def window_policy(rows):
    policies = [(i, r) for i, r in enumerate(rows) if r['event'] == 'window_capability_policy']
    require(len(policies) == 2, 'window policy install/restore count')
    (begin, installed), (end, restored) = policies
    bindings = [r[1] for r in METHODS]
    hashes = {r[1]: r[4] for r in METHODS}
    require(installed.get('phase') == 'install' and restored.get('phase') == 'restore'
            and installed.get('policy_version') == restored.get('policy_version') == 1
            and installed.get('unavailable_windows') == ['appearance', 'maintenance']
            and installed.get('original_module_details_preserved') is True
            and installed.get('audited_source') == PANEL_SOURCE and installed.get('audited_pyc_sha256') == PANEL_SHA
            and installed.get('original_method_code_sha256') == hashes
            and installed.get('bindings') == restored.get('restored_bindings') == bindings
            and restored.get('original_binding_restored') is True, 'window policy scope/source/restore differs')
    bootstrap = [(i, r) for i, r in enumerate(rows) if r['event'] == 'hangar_bootstrap_step' and r.get('stage') == 'module_capabilities']
    cleanup = [(i, r) for i, r in enumerate(rows) if r['event'] == 'hangar_cleanup' and r.get('stage') == 'module_capabilities']
    require(len(bootstrap) == 2 and [r.get('phase') for _, r in bootstrap] == ['begin', 'return']
            and bootstrap[0][0] < begin < bootstrap[1][0] < end
            and len(cleanup) == 1 and end < cleanup[0][0] and cleanup[0][1].get('outcome') == 'PASS', 'window policy lifecycle window')
    denied = [(i, r) for i, r in enumerate(rows) if r['event'] == 'window_capability_denied']
    notices = [(i, r) for i, r in enumerate(rows) if r['event'] == 'window_capability_notice']
    require(len(denied) == len(notices) == 2, 'two explicit window refusals/notices required')
    evidence = []
    for n, (action, callback, _, _, _) in enumerate(METHODS):
        (denied_at, deny), (notice_at, notice) = denied[n], notices[n]
        require(begin < denied_at < notice_at < end and deny.get('policy_version') == notice.get('policy_version') == 1
                and deny.get('action') == notice.get('action') == action and deny.get('callback') == notice.get('callback') == callback
                and deny.get('origin') == 'project_test_service_policy' and deny.get('original_callback_called') is False
                and deny.get('native_event_called') is False and deny.get('original_mutation_called') is False
                and notice.get('phase') == 'return' and notice.get('channel') == 'original_SystemMessages_Warning',
                'window denial called original/event/mutation or warning did not return')
        if n:
            require(notices[n - 1][0] < denied_at, 'window refusals reordered')
        evidence.append({'action': action, 'callback': callback, 'denied_line': denied_at + 1, 'notice_line': notice_at + 1})
    require(not any(r['event'] in ('crew_capability_denied', 'battle_capability_denied', 'capability_denied') for r in rows),
            'window scenario attempted another unsupported capability')
    return {'status': 'PASS', 'denials': evidence, 'original_module_details_preserved': True,
            'scope': 'Guarded void callbacks, no claim of catalogue, repair, customization or physical clicks.'}


def observer_coverage(install, plan):
    """Inspect the installed profiler as data before treating absent calls as proof."""
    sources = [r for r in plan['sources'] if r.get('path') == 'client_patch/sr_interactive.py']
    require(len(sources) == 1, 'unique installed profiler required')
    raw = local_file(install, sources[0]['compiled'], 1024 * 1024)
    relative = 'res_mods/0.9.1/scripts/client/sr_interactive.pyc'
    require(raw == local_file(install, 'postrun/' + relative, 1024 * 1024), 'profiler compiled/postrun bytes differ')
    candidates = [(name, code) for name, code in records(parse_pyc(raw)) if name.split('.')[-1] == 'profile_calls']
    require(len(candidates) == 1, 'unique original-code profiler function required')
    code = candidates[0][1]
    strings = set()
    def visit(value, depth=0):
        require(depth <= 16, 'profiler literal nesting bound')
        if type(value) is bytes:
            strings.add(value.decode('utf8', 'strict'))
        elif type(value) is str:
            strings.add(value)
        elif type(value) is list:
            require(len(value) <= 4096, 'profiler literal count bound')
            for item in value:
                visit(item, depth + 1)
    visit(code['consts'])
    targets = {PANEL_SOURCE, 'showCustomization', 'showTechnicalMaintenance', '_populate',
               'native_unsupported_window_call', *(row[1] for row in UNSUPPORTED)}
    require(targets <= strings and b'record' in code['names'], 'installed observer lacks exact unsupported entry/populate targets')
    return {'status': 'PASS', 'compiled_sha256': digest(raw), 'profiler_code_sha256': digest(code['code']),
            'source_sha256': sources[0]['sha256'], 'event': 'native_unsupported_window_call',
            'original_entry_methods': [r[1] for r in METHODS],
            'unsupported_sources': [r[1] for r in UNSUPPORTED],
            'scope': 'Installed bounded bytecode contains the exact original-source targets; dynamic coverage is checked separately.'}


def unsupported_absence(rows, coverage, policy):
    require(coverage.get('status') == policy.get('status') == 'PASS', 'window observer/policy prerequisite absent')
    require(not any(r['event'] == 'native_unsupported_window_call' for r in rows), 'original unsupported entry or population executed')
    require(not any(r['event'] == 'observation_limit' for r in rows), 'passive original profiler reached observation budget')
    completed = crew.pairs(rows, 'native_account_call', 'onBecomeNonPlayer', 'scripts/client/Account.py', 246, 366)
    require(len(completed) == 1 and completed[0][0] > max(r['notice_line'] - 1 for r in policy['denials']),
            'original profiler completion after both guarded actions absent')
    return {'status': 'PASS', 'unsupported_entry_and_populate_calls': 0,
            'profiler_active_after_both_actions': {'call_id': completed[0][1]['call_id'], 'return_offset': 366},
            'scope': 'No targeted original AmmunitionPanel entry or unsupported _populate ran while native profiling remained active.'}


def window_state(state, expected):
    """Validate the targeted query, not an invented all-windows/topmost scan."""
    require(type(state) is dict and set(state) == {'database_id', 'resources', 'statistics',
            'selected_inventory_id', 'hangar_owner', 'crew_owner', 'ammunition_owner', 'view_scan'},
            'exact bounded original Hangar state required')
    crew.same({k: state[k] for k in ('database_id', 'resources', 'statistics')},
              limits.state_identity(expected), 'window action changed Account/resources/statistics')
    require(type(state['selected_inventory_id']) is int and state['selected_inventory_id'] == 1,
            'window action must retain native MS1')
    require(all(type(state[k]) is int and 0 < state[k] <= 0xffffffffffffffff
                for k in ('hangar_owner', 'crew_owner', 'ammunition_owner')), 'native component owner bound')
    scan = state['view_scan']
    require(type(scan) is dict and set(scan) == {'version', 'scope', 'lobby_sub', 'window', 'unsupported_present'}
            and type(scan['version']) is int and scan['version'] == 1
            and scan['scope'] == 'LOBBY_SUB_current_and_WINDOW_alias' and scan['unsupported_present'] is False,
            'bounded targeted original view scan required')
    crew.same(scan['lobby_sub'], {'class_name': 'Hangar', 'alias': 'hangar', 'flash_bound': True,
                                 'owner_id': state['hangar_owner']}, 'current original Hangar differs or is unbound')
    window = scan['window']
    require(type(window) is dict and set(window) == {'view_count', 'queried_alias', 'matched_view'}
            and type(window['view_count']) is int and 0 <= window['view_count'] <= 64
            and window['queried_alias'] == 'technicalMaintenance' and window['matched_view'] is None,
            'bounded maintenance alias query must be clear; getView(None) is not proof')
    return state


def passive_ms1(rows, position, expected):
    native = [r for r in rows[:position] if r['event'] == 'native_hangar']
    require(native, 'passive native Hangar absent before window evidence')
    time, previous = rows[position].get('elapsed_seconds'), native[-1].get('elapsed_seconds')
    require(all(type(t) in (int, float) and math.isfinite(t) for t in (time, previous))
            and 0 <= time - previous <= 2, 'passive native image observation is stale')
    require(crew.hangar_ready(native[-1], expected), 'window image outside actual ready original MS1/model')
    return previous


def window_actions(rows, states, shots, policy, expected, start_position):
    actions = [(i, r) for i, r in enumerate(rows) if r['event'] == 'windows_scenario_action']
    selected = bool(actions and actions[0][1].get('action') == 'select_ms1')
    wanted = (['select_ms1'] if selected else []) + ['appearance', 'maintenance']
    require([(r.get('action'), r.get('moment')) for _, r in actions]
            == [(action, phase) for action in wanted for phase in ('call', 'return')], 'window action order/count differs')
    pairs = {action: (actions[n * 2], actions[n * 2 + 1]) for n, action in enumerate(wanted)}
    if selected:
        (begin, call), (end, returned) = pairs['select_ms1']
        require(start_position < begin < end < states[0][0]
                and call.get('callback') == 'TankCarousel.vehicleChange'
                and call.get('inventory_id') == returned.get('inventory_id') == 1
                and type(call.get('inventory_id')) is type(returned.get('inventory_id')) is int
                and call.get('step') == returned.get('step') == 0
                and call.get('phase') == returned.get('phase') == 'initial', 'optional native MS1 selection differs')
    owner = states[0][1]['state']['ammunition_owner']
    for step, (action, callback, _, _, _) in enumerate(METHODS, 1):
        (begin, call), (end, returned) = pairs[action]
        refusal = policy['denials'][step - 1]
        require(shots[step - 1][0] < begin < refusal['denied_line'] - 1 < refusal['notice_line'] - 1 < end < states[step][0],
                'window denial/warning must occur inside its exact callback before next image')
        require(call.get('origin') == 'explicit_diagnostic_of_installed_UI_policy'
                and call.get('callback') == returned.get('callback') == 'AmmunitionPanel.' + callback
                and type(call.get('owner_id')) is type(returned.get('owner_id')) is int
                and call['owner_id'] == returned['owner_id'] == owner
                and call.get('step') == returned.get('step') == step
                and call.get('phase') == returned.get('phase') == 'waiting_png', 'guarded window callback owner/phase differs')
        before, after = window_state(call.get('state'), expected), window_state(returned.get('state'), expected)
        crew.same(before, after, 'guarded callback changed native window or selected vehicle')
        for state in (before, after):
            crew.same({k: v for k, v in state.items() if k != 'view_scan'},
                      {k: v for k, v in states[0][1]['state'].items() if k != 'view_scan'}, 'window callback changed stable native owner')
    require(all(type(r.get('version')) is int and r['version'] == 1 for _, r in actions), 'window action schema version')
    return {key: [value[0][0], value[1][0]] for key, value in pairs.items()}


def windows_scenario(rows, outcome, plan, expected, local_root, preservation, policy):
    require(preservation.get('status') == policy.get('status') == 'PASS', 'crew/window policy prerequisite missing')
    names = ('windows_scenario_start', 'windows_scenario_complete', 'diagnostic_condition_complete', 'quit_requested', 'fini_enter')
    events = {name: [(i, r) for i, r in enumerate(rows) if r['event'] == name] for name in names}
    require(all(len(value) == 1 for value in events.values()), 'windows scenario/condition/quit event count')
    positions = [events[name][0][0] for name in names]
    require(positions == sorted(set(positions)), 'windows completion/quit/fini order')
    require(not any(r['event'] in ('windows_scenario_error', 'diagnostic_condition_failed', 'crew_scenario_start',
                                   'profile_scenario_start', 'limits_scenario_start') for r in rows),
            'windows scenario failed or mixed with another scenario')
    known = {'windows_scenario_' + suffix for suffix in ('start', 'action', 'state', 'screenshot_requested', 'screenshot', 'complete')}
    require(all(r['event'] in known for r in rows if r['event'].startswith('windows_scenario_')), 'unknown windows scenario event')
    start, complete = events[names[0]][0][1], events[names[1]][0][1]
    require(start.get('phase') == 'initial' and type(start.get('step')) is int and start['step'] == 0
            and complete.get('phase') == 'complete' and type(complete.get('step')) is int and complete['step'] == 2
            and type(complete.get('screenshots')) is type(complete.get('observations')) is int
            and complete['screenshots'] == complete['observations'] == 3
            and start.get('screenshot_basenames') == list(SCREENSHOTS)
            and type(start.get('expected_crew_observations')) is int and start['expected_crew_observations'] == 3,
            'windows scenario start/completion shape')
    for item in (start, complete):
        require(type(item.get('version')) is int and item['version'] == 1 and item.get('computer_input') is False
                and item.get('automatic_quit') is False
                and item.get('native_pixels_review') == item.get('human_manual_acceptance') == 'NOT_RUN', 'diagnostic scope inflated')
    crew.same(complete.get('identity'), limits.state_identity(expected), 'windows completion identity changed')
    require(complete.get('crew_unchanged') is True and complete.get('crew_fingerprint') == preservation['crew_fingerprint'],
            'scenario crew fingerprint mismatch')
    condition = events['diagnostic_condition_complete'][0][1]
    require(condition.get('condition') == 'hangar_windows_observed' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False, 'windows condition-based exit not proved')
    control = outcome.get('diagnostic_control', {})
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition' and outcome.get('control_consumed') is True
            and control.get('verify_hangar_windows') is True and control.get('verify_hangar_limits') is False
            and control.get('verify_ms1_crew') is False and control.get('export_ms1_crew') is False
            and control.get('quit_when') == 'hangar_windows_observed' and control.get('quit_after_seconds') is None
            and control.get('ui_scenario') is None, 'windows diagnostic control scope differs')
    states = [(i, r) for i, r in enumerate(rows) if r['event'] == 'windows_scenario_state']
    shots = [(i, r) for i, r in enumerate(rows) if r['event'] == 'windows_scenario_screenshot']
    requested = [(i, r) for i, r in enumerate(rows) if r['event'] == 'windows_scenario_screenshot_requested']
    require(len(states) == len(shots) == len(requested) == 3, 'three bounded state/native images required')
    directory = entry.owned(plan['settings']['screenshot_dir'], local_root, True)
    images, state_proofs, stable_owner = [], [], None
    for step, basename in enumerate(SCREENSHOTS):
        index, row = states[step]
        require(all(type(r.get('step')) is type(r.get('version')) is int and r['step'] == step and r['version'] == 1
                    for r in (row, requested[step][1], shots[step][1]))
                and row.get('phase') == requested[step][1].get('phase') == 'waiting_view'
                and shots[step][1].get('phase') == 'waiting_png', 'windows state/image phase/step')
        state = window_state(row.get('state'), expected)
        shot_state = window_state(shots[step][1].get('state'), expected)
        stable = row.get('stable_seconds')
        require(type(stable) in (int, float) and math.isfinite(stable) and 2 <= stable <= 600,
                'native Hangar was not held for two seconds')
        require(positions[0] < index < requested[step][0] < shots[step][0] < positions[1], 'windows image/state order')
        if step:
            require(shots[step - 1][0] < index, 'windows images reordered')
        for current in (state, shot_state):
            owner = {k: v for k, v in current.items() if k != 'view_scan'}
            if stable_owner is None:
                stable_owner = owner
            crew.same(owner, stable_owner, 'window actions changed stable native owner/identity')
        passive_ms1(rows, index, expected)
        passive_ms1(rows, shots[step][0], expected)
        shot = shots[step][1].get('screenshot', {})
        require(requested[step][1].get('basename') == shot.get('basename') == basename
                and requested[step][1].get('writer') == 'BigWorld.screenShot' and requested[step][1].get('extension') == 'png',
                'native windows screenshot writer/name')
        path = entry.owned(shot['path'], local_root)
        require(path.parent == directory and re.fullmatch(basename + r'_[0-9]{3,10}\.png', path.name), 'native windows screenshot owned path')
        raw = read_limited(path, 16 * 1024 * 1024)
        dimensions = crew.png_container(raw)
        require(type(shot.get('bytes')) is int and len(raw) == shot['bytes'] and digest(raw) == shot.get('sha256')
                and dimensions == shot.get('dimensions') and shot.get('png_container_valid') is True, 'native windows PNG hash/container proof')
        images.append({'step': step, 'file': path.name, 'path': str(path), 'bytes': len(raw), 'sha256': digest(raw),
                       'dimensions': dimensions, 'native_pixels_review': 'NOT_RUN'})
        state_proofs.append({'step': step, 'line': index + 1, 'stable_seconds': stable, **state,
                             'screenshot_scan': shot_state['view_scan']})
    action_pairs = window_actions(rows, states, shots, policy, expected, positions[0])
    crew_positions = [line - 1 for line in preservation['observation_lines']]
    require(len(crew_positions) == 3 and states[0][0] < crew_positions[0] < requested[0][0]
            and shots[1][0] < crew_positions[1] < action_pairs['maintenance'][0]
            and shots[2][0] < crew_positions[2] < positions[1], 'crew observations do not bracket both guarded windows')
    final = window_state(complete.get('state'), expected)
    crew.same(final, shots[2][1]['state'], 'final window/crew observation changed native state')
    return {'status': 'PASS', 'states': state_proofs, 'images': images, 'actions': action_pairs,
            'targeted_query': 'LOBBY_SUB current Hangar and WINDOW technicalMaintenance alias only',
            'conditional_exit': 'hangar_windows_observed', 'human_manual_acceptance': 'NOT_RUN',
            'scope': 'Installed guarded API diagnostic; no unsupported original entry/populate, physical clicks NOT_RUN.'}


def visual_review(install, trace_sha, scenario_report):
    require(scenario_report.get('status') == 'PASS', 'complete windows scenario required before pixel acceptance')
    path = install / 'visual-review-windows.json'
    if not path.is_file():
        return {'status': 'NOT_RUN', 'reason': 'Exact native PNG review absent'}
    raw = read_limited(path, 65536)
    review = entry.json_data(raw)
    require(review.get('version') == 1 and review.get('source') == 'assistant_native_png_review'
            and review.get('trace_sha256') == trace_sha, 'windows review trace/source mismatch')
    images = review.get('images')
    require(type(images) is list and len(images) == 3 and len({r.get('file') for r in images}) == 3,
            'three exact native windows images must be reviewed')
    for proof in scenario_report['images']:
        # Both established review forms identify the very same owned file.
        # Do not accept an arbitrary path merely because its basename matches.
        matching = [r for r in images if r.get('file') in (proof['file'], proof['path'])]
        require(len(matching) == 1 and matching[0].get('sha256') == proof['sha256'], 'windows review image hash mismatch')
        row = matching[0]
        require(all(row.get(k) is True for k in ('hangar_visible', 'ms1_visible', 'crew_names_and_levels_visible', 'resources_unchanged'))
                and row.get('unsupported_window_visible') is False, 'native original Hangar/preserved data/absence pixels failed')
        field = {1: 'appearance_warning_visible', 2: 'maintenance_warning_visible'}.get(proof['step'])
        if field:
            require(row.get(field) is True, 'required window warning was not visually observed')
    return {'status': 'PASS', 'file': str(path), 'sha256': digest(raw), 'reviewed_images': 3,
            'human_manual_acceptance': 'NOT_RUN'}


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
        crew.same(entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384)), plan['settings'], 'postrun/plan settings differ')
        checks[stage] = {'status': 'PASS', 'plan_sha256': digest(plan_raw), 'outcome_sha256': digest(outcome_raw),
                         'started_utc': outcome.get('started_utc'), 'finished_utc': outcome.get('finished_utc')}
        checks['compiled_sources'] = crew.checked(lambda: compiled_sources(install, plan, outcome))
        checks['observer_coverage'] = crew.checked(lambda: observer_coverage(install, plan))
        stage = 'runtime_trace'
        rows, info = entry.runtime_rows(install, plan, outcome, local_root)
        checks[stage] = {'status': 'PASS', **info}
        checks['client_profile'] = crew.checked(lambda: limits.client_profile(plan, rows, local_root))
        checks['runtime_common'] = crew.checked(lambda: crew.runtime_common(install, plan, outcome, rows))
        checks['module_policy'] = crew.checked(lambda: crew.module_policy_evidence(rows))
        checks['hangar'] = crew.checked(lambda: crew.hangar(rows, expected))
        checks['crew_preservation'] = crew.checked(lambda: limits.crew_preservation(rows, expected))
        checks['original_crew_flash'] = crew.checked(lambda: crew.crew_flash(rows))
        checks['window_policy'] = crew.checked(lambda: window_policy(rows))
        checks['unsupported_absence'] = crew.checked(lambda: unsupported_absence(rows, checks['observer_coverage'], checks['window_policy']))
        checks['windows_scenario'] = crew.checked(lambda: windows_scenario(rows, outcome, plan, expected, local_root,
                                                                          checks['crew_preservation'], checks['window_policy']))
        checks['visual_review'] = crew.checked(lambda: visual_review(install, info['sha256'], checks['windows_scenario']))
        stage = 'wire'
        run = entry.owned(outcome['gateway_run'], local_root, True)
        client_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(client_digest) == 16 and type(outcome.get('gateway_log_span')) is dict, 'client digest/frozen backend span absent')
        wire = entry.wire(install, entry.owned(args.private_key, local_root), expected, password, client_digest,
                          dossier_cache=expected['dossier_cache'], cache_hints=True)
        checks['wire'] = wire
        checks['no_gameplay_commands'] = crew.checked(lambda: limits.no_gameplay_commands(wire))
        checks['native_account'] = crew.checked(lambda: crew.native_account(rows, wire, expected))
        backend = crew.checked(lambda: entry.backend_binding(install, outcome, wire, expected, local_root))
        checks['backend'] = backend
        checks['cache_backend'] = crew.checked(lambda: crew.cache_backend(backend, wire, expected))
        report['identity_snapshot'] = {
            'account_id': expected['account_id'], 'native_database_id': expected['native_id'], 'nickname': expected['name'],
            'profile_sha256': expected['profile_sha256'], 'fixture_manifest_sha256': expected['manifest_sha256'],
            'payload_sha256': {k: digest(v) for k, v in expected['raw'].items()},
            'resources': expected['resources'], 'statistics': expected['profile']['statistics'],
            'crew_compact_sha256': [digest(bytes.fromhex(c[1])) for c in crew.CREW], 'dossier_cache': expected['dossier_cache']}
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        checks[stage] = {'status': 'FAIL', 'error_type': type(error).__name__,
                         'reason': str(error) if type(error) is ValueError and not isinstance(error, json.JSONDecodeError)
                         else 'Malformed, missing or inconsistent bounded evidence'}
    report['status'] = crew.status(checks)
    return report


def verify(args):
    local_root = config()[1]['local_artifacts_root']
    report = {'version': VERSION, 'scope': 'Guarded native Appearance/Maintenance entries, unchanged profile3 and real cached relogin',
              'verifier_sha256': digest(read_limited(Path(__file__), 1024 * 1024)), 'checks': {},
              'human_manual_acceptance': 'NOT_RUN', 'relogin': {'status': 'NOT_RUN', 'reason': 'No previous install supplied'}}
    stage = 'inputs'
    try:
        install = entry.owned(args.install, local_root, True)
        fixture = entry.owned(args.fixture, local_root, True)
        native_export = entry.owned(args.native_export, local_root)
        report['checks']['frozen_dependencies'] = frozen_dependencies()
        stage = 'native_export'
        exported, export_report = crew.export_evidence(native_export, local_root)
        report['checks'][stage] = export_report
        stage = 'fixture'
        expected, proof = crew.crew_fixture(fixture, exported, export_report, local_root)
        report['checks'][stage] = proof
        stage = 'identity'
        password, identity_report = crew.identity(expected, entry.owned(args.registration, local_root),
                                                   entry.owned(args.credentials, local_root), args.case)
        report['checks'][stage] = identity_report
        report['checks']['original_crew_contracts'] = crew.checked(crew.original_crew_contracts)
        report['checks']['original_window_contracts'] = crew.checked(original_contracts)
        report['session'] = verify_session(args, install, expected, password, local_root)
        report['checks']['native_session'] = {'status': report['session']['status']}
        if args.previous_install:
            previous_install = entry.owned(args.previous_install, local_root, True)
            report['previous_session'] = verify_session(args, previous_install, expected, password, local_root)
            report['relogin'] = crew.checked(lambda: limits.relogin(report['session'], report['previous_session']))
            report['checks']['paired_relogin'] = report['relogin']
    except (ValueError, KeyError, IndexError, TypeError, OSError, struct.error) as error:
        report['checks'][stage] = {'status': 'FAIL', 'error_type': type(error).__name__,
                                   'reason': str(error) if type(error) is ValueError and not isinstance(error, json.JSONDecodeError)
                                   else 'Malformed, missing or inconsistent bounded evidence'}
    report['status'] = crew.status(report['checks'])
    report['card_status'] = 'FAIL' if report['status'] == 'FAIL' else 'PASS' if report['relogin']['status'] == 'PASS' else 'NOT_RUN'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'fixture', 'native-export', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--previous-install')
    parser.add_argument('--registration', default=str(crew.DEFAULT_REG / 'registration.json'))
    parser.add_argument('--credentials', default=str(crew.DEFAULT_REG / 'test-credentials.json'))
    parser.add_argument('--case', default='operator_shared')
    parser.add_argument('--private-key', default=str(ROOT / 'local/server/native-private.pem'))
    args = parser.parse_args()
    out = output_dir(args.out)
    require(not any(out.iterdir()), 'verification output directory must be fresh and empty')
    report = verify(args)
    target = out / 'hangar-windows-verification.json'
    save_json(target, report)
    print(json.dumps({'status': report['status'], 'card_status': report['card_status'],
                      'report': str(target), 'sha256': digest(read_limited(target, 32 * 1024 * 1024))}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
