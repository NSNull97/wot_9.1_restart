"""Read-only native gate for explicit unavailable battle UI and own greeting.

Reuses the frozen profile3, crypto/stream, account and cleanup gates. This is a
new policy acceptance profile; it does not weaken the previous crew acceptance.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import struct

import verify_ms1_crew_native as crew
import verify_hangar_ui as ui
from client_audit import ROOT, config, output_dir, read_limited, save_json
from py27_static import inspect, opcode_table
from verify_hangar import (PROFILE_RETURNS, PROFILE_BATTLES_TYPE, digest, local_file,
                           mo_literal, original_contracts, require, same_literal)

entry = crew.entry
MODULES = crew.MODULES + ('ms1_crew_scenario', 'hangar_limits_scenario')
GREETING_PATH = 'res/text/LC_MESSAGES/system_messages.mo'
GREETING_ORIGINAL_SHA = 'c48a1f5d461c865c0e6b1ee8f9ec2afee21f29ca1fde5badd240aa566ba36992'
GREETING = 'Добро пожаловать на сервер «%s»!'
FIGHT_SOURCE = 'scripts/client/gui/Scaleform/daapi/view/lobby/header/FightButton.py'
FIGHT_SHA = '10582b200f622c2bad8623a5c04cc1c90adb28e6af80605efc5401f5c15a2b95'
FIGHT_META = 'scripts/client/gui/Scaleform/daapi/view/meta/FightButtonMeta.py'
FIGHT_META_SHA = '025a38d92700bf721f440347215e5d3b46c75db1d64feab27e42a1e39c79e4df'
GREETING_SOURCE = 'scripts/client/gui/Scaleform/SystemMessagesInterface.py'
GREETING_SOURCE_SHA = '3fdeea462f5922cdf88c5c8a9d51e8a0d7d2c0692783c1a4859e28bc3a71ce29'
VERSION = 1
SCREENSHOTS = ('limits_ms1', 'limits_is7', 'limits_profile', 'limits_return', 'limits_tooltip', 'limits_denied')
ACTIONS = ('select_ms1', 'select_is7', 'open_profile', 'close_profile',
           'select_ms1_after_profile', 'show_battle_tooltip', 'hide_battle_tooltip', 'deny_battle')
BATTLE_TOOLTIP = ('{HEADER}Бои пока недоступны{/HEADER}{BODY}Сейчас доступен ангар. '
                  'Подключение к боям появится позже.{/BODY}')
BATTLE_NOTICE = 'Бои пока недоступны. Сейчас доступен ангар. Подключение к боям появится позже.'
BATTLE_METHOD_HASHES = {
    'fightClick': '075a47213a9beee880cf1abc17bc24a25b88fbfed245f9ff1b2f068dfa3cb00c',
    '_FightButton__disableFightButton': '601bb3cc8f7f95b8acab71d36bd2b20c343f6b9e59f12d0d2047c35d1a6d9320',
    'update': 'e2fef36b4ffa347f5424829e5a3218dda6d45c32aa1c08c1bd867d0cf28aaa3e',
}


def compiled_sources(install, plan, outcome):
    """Exactly ten modules, preserving the frozen eight/nine-module gate."""
    sources = plan.get('sources')
    require(type(sources) is list and len(sources) == 10, 'limits policy requires exactly ten versioned modules')
    names = [r.get('path') for r in sources]
    require(set(names) == {'client_patch/' + n + '.py' for n in MODULES} and len(set(names)) == 10,
            'unknown/missing/duplicate limits module')
    evidence = []
    for source in sources:
        name = Path(source['path']).stem
        meta = entry.json_data(local_file(install, source['metadata'], 16384))
        compiled = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        matches = [r for r in plan['files'] if r.get('path') == relative]
        require(len(matches) == 1 and matches[0].get('runtime_mutable') is False, 'compiled limits install identity')
        require(meta.get('source') == name + '.py' and meta.get('source_sha256') == source.get('sha256')
                and re.fullmatch('[0-9a-f]{64}', source.get('sha256', '')) is not None
                and meta.get('source_executed') is False and meta.get('magic') == '03f30d0a'
                and meta.get('compiler', '').startswith('2.7.3 '), 'limits compiler metadata/source chain')
        sha = digest(compiled)
        require(compiled[:4] == bytes.fromhex('03f30d0a') and sha == meta.get('pyc_sha256')
                == matches[0].get('installed_sha256'), 'compiled limits byte/hash chain')
        require(local_file(install, 'postrun/' + relative, 1024 * 1024) == compiled, 'runtime limits module changed')
        evidence.append({'module': name, 'source_sha256': source['sha256'], 'pyc_sha256': sha})
    crew.same(outcome.get('source_provenance', {}).get('modules'), evidence, 'limits runner/compiler provenance mismatch')
    return {'status': 'PASS', 'modules': evidence}


def mo_entries(raw):
    """Bounded MO tables only; never instantiate an executable plural formula."""
    require(28 <= len(raw) <= 8 * 1024 * 1024, 'MO size bound')
    endian = '<' if raw[:4] == b'\xde\x12\x04\x95' else '>' if raw[:4] == b'\x95\x04\x12\xde' else None
    require(endian is not None, 'MO magic')
    _, revision, count, originals, translations, _, _ = struct.unpack_from(endian + '7I', raw)
    require(revision == 0 and 1 <= count <= 4096, 'MO version/count')
    require(all(28 <= base and base + count * 8 <= len(raw) for base in (originals, translations)), 'MO table bound')
    def item(base, index):
        length, offset = struct.unpack_from(endian + '2I', raw, base + 8 * index)
        require(length <= 65536 and offset + length < len(raw) and raw[offset + length] == 0, 'MO string bound/terminator')
        return raw[offset:offset + length]
    result = {}
    for index in range(count):
        key, value = item(originals, index), item(translations, index)
        require(key not in result, 'MO duplicate key')
        result[key] = value
    return result


def greeting_resource(install, plan):
    installed = [r for r in plan.get('files', []) if r.get('path') == GREETING_PATH]
    require(len(installed) == 1 and installed[0].get('runtime_mutable') is False, 'targeted greeting install ledger')
    row = installed[0]
    before = local_file(install, 'backup/' + GREETING_PATH, 8 * 1024 * 1024)
    after = local_file(install, 'postrun/' + GREETING_PATH, 8 * 1024 * 1024)
    original = local_file(config()[1]['original_client_root'], GREETING_PATH, 8 * 1024 * 1024)
    require(before == original and digest(before) == row.get('before_sha256') == GREETING_ORIGINAL_SHA
            and digest(after) == row.get('installed_sha256'), 'greeting original/backup/postrun hash chain')
    old, new = mo_entries(before), mo_entries(after)
    require(len(old) == len(new) == 656 and old.keys() == new.keys(), 'greeting catalog keys/count changed')
    require([k for k in old if old[k] != new[k]] == [b'connected']
            and new[b'connected'] == GREETING.encode('utf8'), 'more than the one agreed greeting changed')
    require(new[b'connected'].count(b'%s') == old[b'connected'].count(b'%s') == 1, 'greeting interpolation arity')
    require(not any('/text/' in r.get('path', '').lower() and r['path'].startswith('res_mods/')
                    for r in plan['files']), 'partial res_mods gettext directory would shadow original domains')
    restore = crew.read_json(install / 'restore.json', 2 * 1024 * 1024)
    restored = [r for r in restore.get('files', []) if r.get('path') == GREETING_PATH]
    require(restore.get('status') == 'PASS' and len(restored) == 1
            and restored[0].get('before_sha256') == digest(before)
            and restored[0].get('postrun_sha256') == digest(after), 'greeting restore ledger mismatch')
    return {'status': 'PASS', 'path': GREETING_PATH, 'original_sha256': digest(before), 'installed_sha256': digest(after),
            'entries': 656, 'unchanged_entries': 655, 'changed_key': 'connected', 'translation': GREETING}


def no_gameplay_commands(wire):
    require(wire.get('status') == 'PASS' and wire.get('native_logout') is True, 'complete native wire/logout proof required')
    commands = wire.get('commands')
    require(type(commands) is list and commands and all(r.get('kind') in ('sync', 'refresh')
            and r.get('command') in (100, 300, 600) for r in commands), 'battle/layout/other mutation command was sent')
    require(sorted(r['command'] for r in commands if r['kind'] == 'sync') == [100, 300, 600]
            and all(r['command'] == 100 for r in commands if r['kind'] == 'refresh'), 'measured read-only sync command scope')
    require(wire.get('application', {}).get('server_stats_complete') is True, 'server stats coverage incomplete')
    return {'status': 'PASS', 'observed_commands': sorted({r['command'] for r in commands}),
            'forbidden_commands': [108, 700, 701], 'forbidden_count': 0,
            'scope': 'All captured authenticated native commands; no application mutation/queue was attempted.'}


def original_battle_contracts():
    original = config()[1]['original_client_root']
    opcode = read_limited(ROOT / 'local/vendor/cpython-2.7.18/opcode.py', 32768)
    require(digest(opcode) == 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884', 'opcode source hash')
    table, evidence = opcode_table(opcode.decode('utf8')), []
    for source, sha, methods in ((FIGHT_SOURCE, FIGHT_SHA, [('fightClick', 196, 65), ('update', 103, 519), ('__disableFightButton', 204, 19)]),
                                 (FIGHT_META, FIGHT_META_SHA, [('as_disableFightButtonS', 30, 30), ('as_setFightButtonS', 42, 36)]),
                                 (GREETING_SOURCE, GREETING_SOURCE_SHA, [('__onConnected', 108, 31), ('pushI18nMessage', 74, 61)])):
        raw = local_file(original, 'res/' + source + 'c', 1024 * 1024)
        require(digest(raw) == sha, 'original battle source hash')
        records = inspect(raw, table)
        for method, line, offset in methods:
            functions = [r for r in records if r['qualified_name'].split('.')[-1] == method and r['firstlineno'] == line]
            require(len(functions) == 1, 'original battle function identity')
            operations = functions[0]['instructions']
            target = [i for i, op in enumerate(operations) if op['offset'] == offset]
            require(len(target) == 1 and operations[target[0]]['opname'] == 'RETURN_VALUE', 'original battle return offset')
            if source == FIGHT_META:
                require(operations[target[0] - 1]['opname'] == 'CALL_FUNCTION'
                        and any(op.get('value') == 'flashObject' for op in operations[:target[0]]), 'battle Flash bound return branch')
        evidence.append({'source': source, 'sha256': sha, 'returns': methods})
    return {'status': 'PASS', 'sources': evidence,
            'queue_wire_success': 'NOT_RUN; no queue implementation or fabricated failure callback'}


def crew_preservation(rows, expected):
    """Read-only observations before/after native view changes, no unload probe."""
    observations = [(i, r) for i, r in enumerate(rows) if r['event'] == 'ms1_crew_observation']
    require(2 <= len(observations) <= 4 and [r.get('observation_index') for _, r in observations]
            == list(range(1, len(observations) + 1)), 'limits scenario requires bounded before/after crew observations')
    fingerprints = [crew.crew_snapshot(r, expected) for _, r in observations]
    require(len(set(fingerprints)) == 1, 'server crew changed during native view/denial scenario')
    require(not any(r['event'] in ('crew_capability_denied', 'crew_capability_notice') for r in rows),
            'limits scenario unexpectedly attempted a crew action')
    policies = [r for r in rows if r['event'] == 'crew_capability_policy']
    require(len(policies) == 2 and [r.get('phase') for r in policies] == ['install', 'restore']
            and all(r.get('policy_version') == 2 for r in policies)
            and policies[0].get('crew_changes_available') is False and policies[0].get('personal_case_available') is False
            and policies[0].get('original_readers_preserved') is True
            and policies[1].get('original_binding_restored') is True, 'frozen crew availability policy changed')
    bindings = policies[0].get('bindings')
    require(type(bindings) is list and len(bindings) == len(set(bindings)) == 20
            and policies[1].get('restored_bindings') == bindings, 'crew policy restored binding set differs')
    return {'status': 'PASS', 'observation_lines': [i + 1 for i, _ in observations],
            'observations': len(observations), 'crew_fingerprint': fingerprints[0],
            'native_tankman_ids': [1, 2], 'is7_assigned_count': 0, 'crew_action_attempts': 0}


def battle_policy(rows):
    policies = [(i, r) for i, r in enumerate(rows) if r['event'] == 'battle_capability_policy']
    require(len(policies) == 2, 'battle policy install/restore count')
    (begin, installed), (end, restored) = policies
    bindings = ['fightClick', '_FightButton__disableFightButton']
    require(installed.get('phase') == 'install' and restored.get('phase') == 'restore'
            and installed.get('policy_version') == restored.get('policy_version') == 1
            and installed.get('battle_available') is False and installed.get('original_update_preserved') is True
            and installed.get('audited_source') == FIGHT_SOURCE and installed.get('audited_pyc_sha256') == FIGHT_SHA
            and installed.get('original_method_code_sha256') == BATTLE_METHOD_HASHES
            and installed.get('bindings') == restored.get('restored_bindings') == bindings
            and restored.get('original_binding_restored') is True, 'battle policy scope/original bindings')
    bootstrap = [(i, r) for i, r in enumerate(rows) if r['event'] == 'hangar_bootstrap_step' and r.get('stage') == 'module_capabilities']
    cleanup = [(i, r) for i, r in enumerate(rows) if r['event'] == 'hangar_cleanup' and r.get('stage') == 'module_capabilities']
    require(len(bootstrap) == 2 and [r.get('phase') for _, r in bootstrap] == ['begin', 'return']
            and bootstrap[0][0] < begin < bootstrap[1][0] < end
            and len(cleanup) == 1 and end < cleanup[0][0] and cleanup[0][1].get('outcome') == 'PASS', 'battle policy bootstrap/restore window')
    private = crew.pairs(rows, 'native_fight_call', '__disableFightButton', FIGHT_SOURCE, 204, 19, True)
    meta = crew.pairs(rows, 'native_fight_call', 'as_disableFightButtonS', FIGHT_META, 30, 30, True)
    updates = crew.pairs(rows, 'native_fight_call', 'update', FIGHT_SOURCE, 103, 519, True)
    labels = crew.pairs(rows, 'native_fight_call', 'as_setFightButtonS', FIGHT_META, 42, 36, True)
    disabled = [(i, r) for i, r in enumerate(rows) if r['event'] == 'battle_capability_disabled']
    require(private and len(private) == len(meta) == len(disabled) and updates and labels, 'original disable/update/Flash proof count')
    evidence = []
    for (start, call, stop, returned), (mark, marker) in zip(private, disabled):
        require(begin < start < stop < mark < end and marker.get('phase') == 'return'
                and marker.get('policy_version') == 1 and marker.get('disabled') is True
                and marker.get('tool_tip') == BATTLE_TOOLTIP and marker.get('original_disable_called') is True
                and marker.get('original_update_preserved') is True, 'battle disable policy marker/window')
        require(call.get('isDisabled') is True and call.get('toolTip') == BATTLE_TOOLTIP
                and returned.get('isDisabled') is True and returned.get('toolTip') == BATTLE_TOOLTIP, 'original disable input was not forced')
        nested = [p for p in meta if start < p[0] < p[2] < stop and p[1]['owner_id'] == call['owner_id']]
        require(len(nested) == 1 and nested[0][1].get('isDisabled') is True
                and nested[0][1].get('toolTip') == BATTLE_TOOLTIP, 'original bound Flash disable projection')
        parent = [p for p in updates if p[0] < start < mark < p[2] and p[1]['owner_id'] == call['owner_id']]
        require(len(parent) == 1, 'disabled projection is not inside preserved original update')
        evidence.append({'owner_id': call['owner_id'], 'original_update_call_id': parent[0][1]['call_id'],
                         'meta_call_id': nested[0][1]['call_id'], 'normal_return': 30, 'policy_marker_line': mark + 1})
    denied = [(i, r) for i, r in enumerate(rows) if r['event'] == 'battle_capability_denied']
    notices = [(i, r) for i, r in enumerate(rows) if r['event'] == 'battle_capability_notice']
    require(len(denied) == len(notices) == 1, 'one controlled battle denial/notice required')
    (denied_at, action), (notice_at, notice) = denied[0], notices[0]
    require(begin < denied_at < notice_at < end and action.get('policy_version') == 1
            and action.get('capability') == 'battle' and action.get('action') == 'fight'
            and action.get('origin') == 'project_test_service_policy'
            and action.get('original_callback_called') is False and action.get('dispatcher_called') is False
            and action.get('original_mutation_called') is False and notice.get('phase') == 'return'
            and notice.get('policy_version') == 1 and notice.get('channel') == 'original_SystemMessages_Warning',
            'battle denial was not explicit or original warning did not return')
    return {'status': 'PASS', 'original_update_preserved': True, 'bound_disable_projections': evidence,
            'denied_line': denied_at + 1, 'notice_line': notice_at + 1, 'tooltip': BATTLE_TOOLTIP,
            'native_button_readback': 'NOT_RUN: supplied separately by original Flash state observation'}


def native_greeting(rows):
    connected = crew.pairs(rows, 'native_greeting_call', '__onConnected', GREETING_SOURCE, 108, 31)
    translated = crew.pairs(rows, 'native_greeting_call', 'pushI18nMessage', GREETING_SOURCE, 74, 61)
    require(len(connected) == len(translated) == 1, 'exactly one original greeting path required')
    outer, inner = connected[0], translated[0]
    require(outer[0] < inner[0] < inner[2] < outer[2] and outer[1]['owner_id'] == inner[1]['owner_id'], 'greeting original nested owner/call chain')
    call, returned = inner[1], inner[3]
    require(call.get('key') == returned.get('key') == '#system_messages:connected'
            and call.get('args') == returned.get('args') == ['Стальной рубеж']
            and returned.get('text') == GREETING % 'Стальной рубеж', 'original greeting translation/endpoint text differs')
    return {'status': 'PASS', 'key': '#system_messages:connected', 'server_name': 'Стальной рубеж',
            'text': returned['text'], 'call_id': call['call_id'], 'original_returns': [31, 61],
            'native_pixels': 'NOT_RUN: separate exact-PNG review required'}


def state_identity(expected):
    return {'database_id': expected['native_id'],
            'resources': [expected['resources'][k] for k in ('credits', 'gold', 'free_xp')],
            'statistics': [expected['profile']['statistics'][k] for k in ('battles', 'wins', 'losses', 'draws')]}


def native_state(row, step, expected):
    """Readback is independent of the policy's request to disable the button."""
    state = row.get('state')
    require(type(state) is dict and set(state) == {'page', 'alias', 'flash_bound', 'waiting_visible',
            'selected_inventory_id', 'fight_button_enabled', 'tooltip_readback', 'fight_owner', 'identity'},
            'bounded original Flash state shape')
    profile = step == 2
    require(state['page'] == ('ProfilePage' if profile else 'Hangar')
            and state['alias'] == ('profile' if profile else 'hangar')
            and state['flash_bound'] is True and state['waiting_visible'] is False
            and type(state['selected_inventory_id']) is int and state['selected_inventory_id'] == (2 if step in (1, 2) else 1)
            and state['fight_button_enabled'] is False and type(state['fight_owner']) is int and state['fight_owner'] > 0,
            'original page/vehicle/button readback differs')
    crew.same(state['identity'], state_identity(expected), 'native Account/resources/statistics changed')
    tip = state['tooltip_readback']
    require(type(tip) is dict, 'tooltip readback shape')
    if tip.get('status') == 'OBSERVED':
        require(set(tip) == {'status', 'value'} and tip['value'] == BATTLE_TOOLTIP, 'observed native tooltip differs')
    else:
        require(tip.get('status') == 'UNKNOWN' and set(tip) == {'status', 'error_type'}
                and type(tip['error_type']) is str and re.fullmatch('[A-Za-z_]{1,64}', tip['error_type']),
                'missing private tooltip must remain explicit UNKNOWN')
    stable = row.get('stable_seconds')
    require(type(stable) in (int, float) and math.isfinite(stable) and 2 <= stable <= 600,
            'native state was not held for two seconds')
    return state


def original_profile(rows, expected, opened, screenshot, closed):
    """The original summary must populate Flash, not merely create a view."""
    title = mo_literal('profile.mo', '8728913c22505c7c389ca1e6791751360a94e304e9bf4504d0929d9a44a9fc5f', 'profile/title')['value']
    require(title.count('%s') == 1, 'native profile title format')
    title = title.replace('%s', expected['name'])
    selected = [r for r in rows if r['event'] == 'native_profile_call']
    require(0 < len(selected) <= 128 and all(r.get('method') in PROFILE_RETURNS for r in selected),
            'unexpected/missing original summary callback')
    proofs, all_pairs = {}, {}
    for method, (source, line, offset, _) in PROFILE_RETURNS.items():
        values = crew.pairs(rows, 'native_profile_call', method, source, line, offset, True)
        require(values, 'original summary callback absent')
        all_pairs[method] = values
        for start, call, end, returned in values:
            require(opened < start < end < screenshot < closed, 'profile callback outside original navigation window')
            for sample in (call, returned):
                owner = sample.get('owner_state', {})
                # Original ProfileSummary._populate39 calls __updateUserInfo52
                # before activation; only the dossier path requires active=True.
                active = owner.get('isActive')
                require(sample.get('owner_class') == 'ProfileSummaryPage'
                        and (type(active) is bool if method == 'as_setUserDataS' else active is True)
                        and '_userID' in owner and owner['_userID'] is None
                        and owner.get('_databaseID') == expected['native_id'] and owner.get('_userName') == expected['name'],
                        'original summary owner/identity differs')
            crew.same(call.get('data'), returned.get('data'), 'profile Flash data changed before return')
            if method == 'as_responseDossierS':
                data = call.get('data')
                require(type(data) is dict and call.get('type') == returned.get('type') == PROFILE_BATTLES_TYPE
                        and same_literal({k: data.get(k) for k in ('battlesCount', 'winsCount', 'lossesCount')},
                                         {'battlesCount': 0, 'winsCount': 0, 'lossesCount': 0}), 'native summary battle counts differ')
            elif method == 'as_setUserDataS':
                data = call.get('data')
                require(type(data) is dict and data.get('name') == title
                        and all(data.get(k) == '' for k in ('clanName', 'clanNameDescr', 'clanJoinTime', 'clanPosition'))
                        and 'clanEmblem' in data and data['clanEmblem'] is None, 'native summary nickname/clan differs')
        proofs[method] = [{'call_id': p[1]['call_id'], 'owner_id': p[1]['owner_id'], 'normal_return': offset} for p in values]
    for child in all_pairs['as_responseDossierS']:
        require(any(p[0] < child[0] < child[2] < p[2] and p[1]['owner_id'] == child[1]['owner_id']
                    for p in all_pairs['_sendAccountData']), 'summary dossier bypassed original renderer')
    require(len({p[1]['owner_id'] for values in all_pairs.values() for p in values}) == 1,
            'profile name and dossier belong to different native summary owners')
    return {'status': 'PASS', 'methods': proofs, 'title': title, 'battle_counts': [0, 0, 0]}


def limits_scenario(rows, outcome, plan, expected, local_root, preservation, policy):
    require(preservation.get('status') == policy.get('status') == 'PASS', 'crew/policy prerequisite missing')
    names = ('limits_scenario_start', 'limits_scenario_complete', 'diagnostic_condition_complete', 'quit_requested', 'fini_enter')
    events = {n: [(i, r) for i, r in enumerate(rows) if r['event'] == n] for n in names}
    require(all(len(v) == 1 for v in events.values()), 'limits scenario/condition/quit event count')
    positions = [events[n][0][0] for n in names]
    require(positions == sorted(set(positions)), 'limits completion/quit/fini order')
    require(not any(r['event'] in ('limits_scenario_error', 'diagnostic_condition_failed', 'crew_scenario_start', 'profile_scenario_start')
                    for r in rows), 'limits scenario failed or mixed with another scenario')
    start, complete = events[names[0]][0][1], events[names[1]][0][1]
    require(start.get('phase') == 'initial' and start.get('step') == 0 and complete.get('phase') == 'complete'
            and complete.get('step') == 5 and complete.get('screenshots') == 6 and complete.get('observations') == 3,
            'limits scenario start/completion shape')
    for item in (start, complete):
        require(item.get('version') == 1 and item.get('computer_input') is False and item.get('automatic_quit') is False
                and item.get('native_pixels_review') == item.get('human_manual_acceptance') == 'NOT_RUN', 'diagnostic scope inflated')
    crew.same(complete.get('identity'), state_identity(expected), 'limits completion identity changed')
    require(complete.get('crew_fingerprint') == preservation['crew_fingerprint'], 'scenario crew fingerprint mismatch')
    condition = events['diagnostic_condition_complete'][0][1]
    require(condition.get('condition') == 'hangar_limits_observed' and condition.get('timed_exit') is False
            and condition.get('compatibility_acceptance') is False, 'limits condition-based exit not proved')
    control = outcome.get('diagnostic_control', {})
    require(outcome.get('runner_mode') == 'diagnostic_until_client_condition' and outcome.get('control_consumed') is True
            and control.get('verify_hangar_limits') is True and control.get('verify_ms1_crew') is False
            and control.get('export_ms1_crew') is False and control.get('quit_when') == 'hangar_limits_observed'
            and control.get('quit_after_seconds') is None and control.get('ui_scenario') is None,
            'limits diagnostic control scope differs')
    actions = [(i, r) for i, r in enumerate(rows) if r['event'] == 'limits_scenario_action']
    require([(r.get('action'), r.get('moment')) for _, r in actions] == [(a, p) for a in ACTIONS for p in ('call', 'return')],
            'limits original action order differs')
    action_pairs = {a: (actions[n * 2][0], actions[n * 2 + 1][0]) for n, a in enumerate(ACTIONS)}
    require(all(r.get('version') == 1 and r.get('origin') == 'explicit_original_API_diagnostic'
                for _, r in actions if r['moment'] == 'call'), 'limits action origin differs')
    require(action_pairs['deny_battle'][0] < policy['denied_line'] - 1 < policy['notice_line'] - 1 < action_pairs['deny_battle'][1],
            'denial was not nested in exact diagnostic callback')
    states = [(i, r) for i, r in enumerate(rows) if r['event'] == 'limits_scenario_state']
    shots = [(i, r) for i, r in enumerate(rows) if r['event'] == 'limits_scenario_screenshot']
    requested = [(i, r) for i, r in enumerate(rows) if r['event'] == 'limits_scenario_screenshot_requested']
    require(len(states) == len(shots) == len(requested) == 6, 'six bounded state/native images required')
    directory = entry.owned(plan['settings']['screenshot_dir'], local_root, True)
    images, state_proofs = [], []
    for step, basename in enumerate(SCREENSHOTS):
        index, row = states[step]
        require(all(type(r.get('step')) is int and type(r.get('version')) is int
                    for r in (row, requested[step][1], shots[step][1]))
                and row.get('step') == requested[step][1].get('step') == shots[step][1].get('step') == step
                and row.get('phase') == requested[step][1].get('phase') == 'waiting_view'
                and shots[step][1].get('phase') == 'waiting_png'
                and all(r.get('version') == 1 for r in (row, requested[step][1], shots[step][1])), 'limits state/image phase/step')
        state = native_state(row, step, expected)
        require(positions[0] < index < requested[step][0] < shots[step][0] < positions[1], 'limits image/state order')
        if step:
            require(shots[step - 1][0] < index, 'limits images reordered')
        require(any(p['owner_id'] == state['fight_owner'] and p['policy_marker_line'] - 1 < index
                    for p in policy['bound_disable_projections']), 'readback not linked to original disabled receiver')
        # Independently observed native model must match the screenshot view.
        native = [r for r in rows[:index] if r['event'] == 'native_hangar']
        require(native and 0 <= row['elapsed_seconds'] - native[-1]['elapsed_seconds'] <= 2,
                'native image observation is stale')
        observed = native[-1]
        require(observed.get('native_connected') is True and observed.get('items_cache_synced') is True
                and observed.get('waiting_visible') is False and observed.get('selected_inventory_id') == state['selected_inventory_id']
                and observed.get('resources') == expected['resources'] and observed.get('statistics') == expected['profile']['statistics'],
                'passive native Account/readiness differs from scenario state')
        if step != 2:
            vehicle = observed.get('vehicle') or {}
            require(observed.get('vehicle_model_loaded') is True
                    and vehicle.get('type_compact_descr') == (7169 if step == 1 else 3329)
                    and vehicle.get('health') == vehicle.get('max_health') == (2150 if step == 1 else 90)
                    and observed.get('views', {}).get('lobby_sub', {}).get('class_name') == 'Hangar',
                    'original selected tank/model differs')
        shot = shots[step][1].get('screenshot', {})
        require(requested[step][1].get('basename') == shot.get('basename') == basename
                and requested[step][1].get('writer') == 'BigWorld.screenShot' and requested[step][1].get('extension') == 'png',
                'native limits screenshot writer/name')
        path = entry.owned(shot['path'], local_root)
        require(path.parent == directory and re.fullmatch(basename + r'_[0-9]{3,10}\.png', path.name), 'native limits screenshot owned path')
        raw = read_limited(path, 16 * 1024 * 1024)
        dimensions = crew.png_container(raw)
        require(len(raw) == shot.get('bytes') and digest(raw) == shot.get('sha256') and dimensions == shot.get('dimensions')
                and shot.get('png_container_valid') is True, 'native limits PNG hash/container proof')
        images.append({'step': step, 'file': path.name, 'path': str(path), 'bytes': len(raw), 'sha256': digest(raw),
                       'dimensions': dimensions, 'native_pixels_review': 'NOT_RUN'})
        state_proofs.append({'step': step, 'line': index + 1, 'stable_seconds': row['stable_seconds'], **state})
    expected_windows = [('select_ms1', positions[0], states[0][0]), ('select_is7', shots[0][0], states[1][0]),
                        ('open_profile', shots[1][0], states[2][0]), ('close_profile', shots[2][0], states[3][0]),
                        ('select_ms1_after_profile', action_pairs['close_profile'][1], states[3][0]),
                        ('show_battle_tooltip', shots[3][0], states[4][0]),
                        ('hide_battle_tooltip', shots[4][0], states[5][0]),
                        ('deny_battle', action_pairs['hide_battle_tooltip'][1], states[5][0])]
    require(all(lo < action_pairs[name][0] < action_pairs[name][1] < hi for name, lo, hi in expected_windows), 'action/state chronology')
    crew_positions = [line - 1 for line in preservation['observation_lines']]
    require(len(crew_positions) == 3 and states[0][0] < crew_positions[0] < requested[0][0]
            and states[3][0] < crew_positions[1] < requested[3][0]
            and shots[5][0] < crew_positions[2] < positions[1], 'crew observations do not bracket vehicle changes and denial')
    return {'status': 'PASS', 'states': state_proofs, 'images': images, 'actions': action_pairs,
            'profile_window': [action_pairs['open_profile'][0], requested[2][0], action_pairs['close_profile'][0]],
            'tooltip_window': [action_pairs['show_battle_tooltip'][0], requested[4][0], action_pairs['hide_battle_tooltip'][0]],
            'conditional_exit': 'hangar_limits_observed', 'human_manual_acceptance': 'NOT_RUN',
            'scope': 'Original API diagnostic and passive Flash readback; physical mouse/keyboard interaction NOT_RUN.'}


def battle_tooltip(rows, scenario):
    require(scenario.get('status') == 'PASS', 'limits scenario prerequisite missing')
    contracts, sources = ui.original_ui_contracts()
    proof = ui.tooltip_evidence(rows, contracts)
    require(proof.get('status') == 'PASS', 'original complex tooltip did not render')
    shown = [r for r in proof['displays'] if r['tooltip_id'] == BATTLE_TOOLTIP]
    require(len(shown) == 1, 'exactly one original battle-tooltip projection required')
    opened, shot, hidden = scenario['tooltip_window']
    require(rows[opened]['elapsed_seconds'] <= shown[0]['call_seconds'] < shown[0]['return_seconds']
            < rows[shot]['elapsed_seconds'] < rows[hidden]['elapsed_seconds'], 'battle tooltip outside diagnostic screenshot window')
    return {'status': 'PASS', 'display': shown[0], 'source_hashes': sources['sources'],
            'physical_hover': 'NOT_RUN', 'scope': 'Original Flash showComplex API; no physical input was generated.'}


def visual_review(install, trace_sha, scenario_report):
    require(scenario_report.get('status') == 'PASS', 'complete limits scenario required before pixel acceptance')
    path = install / 'visual-review-limits.json'
    if not path.is_file():
        return {'status': 'NOT_RUN', 'reason': 'Exact native PNG review absent'}
    raw = read_limited(path, 65536)
    review = entry.json_data(raw)
    require(review.get('version') == 1 and review.get('source') == 'assistant_native_png_review'
            and review.get('trace_sha256') == trace_sha, 'limits visual review trace/source mismatch')
    images = review.get('images')
    require(type(images) is list and len(images) == 6 and len({r.get('file') for r in images}) == 6,
            'six exact native limits images must be reviewed')
    for proof in scenario_report['images']:
        matches = [r for r in images if r.get('file') == proof['file']]
        require(len(matches) == 1 and matches[0].get('sha256') == proof['sha256'], 'limits review screenshot hash mismatch')
        row, step = matches[0], proof['step']
        require(all(row.get(k) is True for k in ('view_matches', 'battle_button_disabled_visible', 'resources_unchanged')),
                'native view/button/resources pixels do not meet limits card')
        field = {0: 'greeting_visible', 4: 'battle_tooltip_visible', 5: 'battle_warning_visible'}.get(step)
        if field:
            require(row.get(field) is True, 'required native greeting/tooltip/warning was not visually observed')
    return {'status': 'PASS', 'file': str(path), 'sha256': digest(raw), 'reviewed_images': 6,
            'human_manual_acceptance': 'NOT_RUN'}


def client_profile(plan, rows, local_root):
    """Bind the hash-checked plan to the actually selected native profile path.

    Only path provenance is inspected. Current mutable cache/preferences bytes
    are not substituted for the frozen native wire evidence from that run.
    """
    settings = plan['settings']
    directory = entry.owned(settings['profile_dir'], local_root, True)
    require(settings.get('preferences_resource') == 'sr_preferences.xml', 'native preferences resource differs')
    ready = [r for r in rows if r['event'] == 'preferences_local_ready']
    require(len(ready) == 1 and ready[0].get('class_name') == 'DataSection'
            and ready[0].get('native_writer_used') is False, 'native profile preferences binding absent')
    actual = Path(ready[0]['path']).resolve()
    require(actual.parent == directory and actual.name == settings['preferences_resource'], 'native profile path differs from plan')
    return {'status': 'PASS', 'directory': str(directory), 'native_preferences_path': str(actual),
            'scope': 'Hash-bound plan and actual DataSection path; no current mutable cache contents read.'}


def cache_hint_snapshot(session, require_cached):
    checks = session['checks']
    require(checks['wire'].get('status') == checks['cache_backend'].get('status') == 'PASS', 'cached wire/backend prerequisites')
    commands = checks['wire']['commands']
    selected = {n: [r for r in commands if r.get('kind') == 'sync' and r.get('command') == n] for n in (100, 300, 600)}
    require(all(len(rows) == 1 for rows in selected.values()), 'cached relogin sync coverage')
    account, shop, dossier = (selected[n][0] for n in (100, 300, 600))
    crc = account.get('persistent_crc', 0)
    size, shop_crc = shop.get('cached_bytes', 0), shop.get('cached_crc32_signed', 0)
    version, timestamp = dossier.get('revision'), dossier.get('last_change_time', 0)
    require(all(type(n) is int for n in (crc, size, shop_crc, version, timestamp))
            and -(2**31) <= crc < 2**31 and -(2**31) <= shop_crc < 2**31
            and 0 <= size <= 16448 and 0 <= timestamp < 2**31, 'cached relogin descriptor bounds')
    expected = session['identity_snapshot']['dossier_cache']
    if require_cached:
        require(crc != 0 and size > 0 and version == expected['version'] == 1
                and timestamp == expected['last_change_time'] > 0, 'repeat login lacks real nonzero native cache hints')
    else:
        require((version, timestamp) in ((0, 0), (expected['version'], expected['last_change_time'])), 'previous dossier cursor differs')
    refresh = [r for r in commands if r.get('kind') == 'refresh']
    require(refresh and all(r.get('command') == 100 and r.get('persistent_crc', 0) == crc for r in refresh),
            'cached refresh descriptor changed from initial request')
    return {'account_persistent_crc': crc, 'shop_bytes': size, 'shop_crc32_signed': shop_crc,
            'dossier_version': version, 'dossier_last_change_time': timestamp}


def relogin(current, previous):
    proof = crew.relogin(current, previous)
    profiles = [s['checks'].get('client_profile', {}) for s in (current, previous)]
    require(all(r.get('status') == 'PASS' for r in profiles), 'native client profile provenance absent')
    require(Path(profiles[0]['directory']) == Path(profiles[1]['directory']), 'relogin used another native client profile directory')
    now, before = cache_hint_snapshot(current, True), cache_hint_snapshot(previous, False)
    if before['account_persistent_crc']:
        require(now['account_persistent_crc'] == before['account_persistent_crc'], 'existing account cache descriptor changed across relogin')
    if before['shop_bytes']:
        require((now['shop_bytes'], now['shop_crc32_signed']) == (before['shop_bytes'], before['shop_crc32_signed']),
                'existing shop cache descriptor changed across relogin')
    proof.update(native_profile_directory=profiles[0]['directory'], previous_cache_hints=before, current_cache_hints=now,
                 real_cached_relogin=True,
                 scope='Two complete native sessions on the same profile directory, unchanged server identity/payload, '
                       'real nonzero cache hints and same existing descriptors. No battle/economy claim.')
    return proof


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
        checks['greeting_resource'] = crew.checked(lambda: greeting_resource(install, plan))
        stage = 'runtime_trace'
        rows, info = entry.runtime_rows(install, plan, outcome, local_root)
        checks[stage] = {'status': 'PASS', **info}
        checks['client_profile'] = crew.checked(lambda: client_profile(plan, rows, local_root))
        checks['runtime_common'] = crew.checked(lambda: crew.runtime_common(install, plan, outcome, rows))
        checks['module_policy'] = crew.checked(lambda: crew.module_policy_evidence(rows))
        checks['hangar'] = crew.checked(lambda: crew.hangar(rows, expected))
        checks['crew_preservation'] = crew.checked(lambda: crew_preservation(rows, expected))
        checks['original_crew_flash'] = crew.checked(lambda: crew.crew_flash(rows))
        checks['battle_policy'] = crew.checked(lambda: battle_policy(rows))
        checks['native_greeting'] = crew.checked(lambda: native_greeting(rows))
        checks['limits_scenario'] = crew.checked(lambda: limits_scenario(rows, outcome, plan, expected, local_root,
                                                                        checks['crew_preservation'], checks['battle_policy']))
        scenario = checks['limits_scenario']
        checks['original_profile'] = crew.checked(lambda: original_profile(rows, expected, *scenario['profile_window']))
        checks['battle_tooltip'] = crew.checked(lambda: battle_tooltip(rows, scenario))
        checks['visual_review'] = crew.checked(lambda: visual_review(install, info['sha256'], scenario))
        stage = 'wire'
        run = entry.owned(outcome['gateway_run'], local_root, True)
        client_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(client_digest) == 16 and type(outcome.get('gateway_log_span')) is dict, 'client digest/frozen backend span absent')
        wire = entry.wire(install, entry.owned(args.private_key, local_root), expected, password, client_digest,
                          dossier_cache=expected['dossier_cache'], cache_hints=True)
        checks['wire'] = wire
        checks['no_gameplay_commands'] = crew.checked(lambda: no_gameplay_commands(wire))
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
    report = {'version': VERSION, 'scope': 'Explicit unavailable native battle UI, own greeting, unchanged profile3 and cached relogin',
              'verifier_sha256': digest(read_limited(Path(__file__), 1024 * 1024)), 'checks': {},
              'human_manual_acceptance': 'NOT_RUN', 'relogin': {'status': 'NOT_RUN', 'reason': 'No previous install supplied'}}
    stage = 'inputs'
    try:
        install = entry.owned(args.install, local_root, True)
        fixture = entry.owned(args.fixture, local_root, True)
        native_export = entry.owned(args.native_export, local_root)
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
        report['checks']['original_battle_contracts'] = crew.checked(original_battle_contracts)
        report['checks']['original_profile_contracts'] = crew.checked(lambda: original_contracts(profile=True))
        report['session'] = verify_session(args, install, expected, password, local_root)
        report['checks']['native_session'] = {'status': report['session']['status']}
        if args.previous_install:
            previous_install = entry.owned(args.previous_install, local_root, True)
            report['previous_session'] = verify_session(args, previous_install, expected, password, local_root)
            report['relogin'] = crew.checked(lambda: relogin(report['session'], report['previous_session']))
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
    target = out / 'hangar-limits-verification.json'
    save_json(target, report)
    print(json.dumps({'status': report['status'], 'card_status': report['card_status'],
                      'report': str(target), 'sha256': digest(read_limited(target, 32 * 1024 * 1024))}))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
