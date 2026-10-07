"""Rejection controls, not invented native battle compatibility evidence."""
import copy
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_hangar_limits as v

CREW = ROOT / 'local/evidence/20261005-p02-ms1-crew'


class LimitsProtocolControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = CREW / 'wire/verify-crew03-final-01/ms1-crew-native-verification.json'
        if not report.is_file():
            raise unittest.SkipTest('Actual frozen crew03 wire corpus is absent; NOT_RUN')
        cls.wire = json.loads(report.read_text(encoding='utf8'))['session']['checks']['wire']

    def test_actual_previous_readonly_wire_is_acceptable_scope(self):
        self.assertEqual(v.no_gameplay_commands(self.wire)['forbidden_count'], 0)

    def test_measured_layout_refusal_still_violates_no_layout_attempt(self):
        wire = copy.deepcopy(self.wire)
        wire['commands'].append({'kind': 'unavailable', 'command': 108, 'request': 300})
        with self.assertRaises(ValueError):
            v.no_gameplay_commands(wire)

    def test_enqueue_and_dequeue_cannot_hide_as_sync(self):
        for command in (700, 701):
            wire = copy.deepcopy(self.wire)
            wire['commands'].append({'kind': 'sync', 'command': command, 'request': 202})
            with self.subTest(command=command), self.assertRaises(ValueError):
                v.no_gameplay_commands(wire)

    def test_native_parser_candidate_enqueue_forms_are_rejected(self):
        for command, inventory in ((700, 1), (700, 2), (701, 0)):
            candidate = b'\x8e\x14\0' + struct.pack('<hhqii', 202, command, inventory, 0, 0)
            with self.subTest(command=command, inventory=inventory), self.assertRaises(ValueError):
                v.entry.client_requests(candidate, cache_hints=True)

    def test_unknown_command_and_kind_are_rejected(self):
        for item in ({'kind': 'other', 'command': 100}, {'kind': 'sync', 'command': 999}):
            wire = copy.deepcopy(self.wire)
            wire['commands'].append(item)
            with self.assertRaises(ValueError):
                v.no_gameplay_commands(wire)

    def test_missing_full_wire_proof_is_not_a_pass(self):
        for key, value in (('status', 'FAIL'), ('native_logout', False), ('commands', [])):
            wire = copy.deepcopy(self.wire)
            wire[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.no_gameplay_commands(wire)

    def test_missing_counter_reply_is_rejected(self):
        wire = copy.deepcopy(self.wire)
        wire['application']['server_stats_complete'] = False
        with self.assertRaises(ValueError):
            v.no_gameplay_commands(wire)

    def test_missing_initial_sync_is_rejected(self):
        wire = copy.deepcopy(self.wire)
        wire['commands'] = [r for r in wire['commands'] if r.get('command') != 300]
        with self.assertRaises(ValueError):
            v.no_gameplay_commands(wire)


class LimitsSourceControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = v.local_file(v.config()[1]['original_client_root'], v.GREETING_PATH, 8 * 1024 * 1024)

    def test_original_mo_hash_and_656_entries(self):
        self.assertEqual(v.digest(self.original), v.GREETING_ORIGINAL_SHA)
        self.assertEqual(len(v.mo_entries(self.original)), 656)

    def test_unrecognized_mo_magic_rejected(self):
        with self.assertRaises(ValueError):
            v.mo_entries(b'X' * 4 + self.original[4:])

    def test_mo_unbounded_count_rejected(self):
        raw = bytearray(self.original)
        struct.pack_into('<I', raw, 8, 4097)
        with self.assertRaises(ValueError):
            v.mo_entries(bytes(raw))

    def test_mo_table_outside_file_rejected(self):
        raw = bytearray(self.original)
        struct.pack_into('<I', raw, 12, len(raw))
        with self.assertRaises(ValueError):
            v.mo_entries(bytes(raw))

    def test_mo_duplicate_keys_rejected(self):
        raw = bytearray(self.original)
        table = struct.unpack_from('<I', raw, 12)[0]
        raw[table + 8:table + 16] = raw[table:table + 8]
        with self.assertRaises(ValueError):
            v.mo_entries(bytes(raw))

    def test_mo_missing_terminator_rejected(self):
        raw = bytearray(self.original)
        table = struct.unpack_from('<I', raw, 12)[0]
        length, offset = struct.unpack_from('<II', raw, table)
        raw[offset + length] = 1
        with self.assertRaises(ValueError):
            v.mo_entries(bytes(raw))

    def test_original_return_offsets_checked_without_execution(self):
        self.assertEqual(v.original_battle_contracts()['status'], 'PASS')

    def test_old_nine_module_install_is_not_new_limits_acceptance(self):
        install = CREW / 'crew03-prepare'
        plan = v.crew.read_json(install / 'install-plan.json', 1024 * 1024)
        outcome = v.crew.read_json(install / 'native-outcome.json')
        with self.assertRaisesRegex(ValueError, 'exactly ten'):
            v.compiled_sources(install, plan, outcome)

    def test_old_install_without_greeting_delta_is_not_new_acceptance(self):
        install = CREW / 'crew03-prepare'
        plan = v.crew.read_json(install / 'install-plan.json', 1024 * 1024)
        with self.assertRaisesRegex(ValueError, 'greeting install ledger'):
            v.greeting_resource(install, plan)

    def test_previous_crew_gate_is_frozen(self):
        self.assertEqual(v.digest((ROOT / 'tools/verify_ms1_crew_native.py').read_bytes()),
                         '91e6ad71a0b964406dd44d1954aad752695701e11e33385df28a8caf689ef522')


def synthetic_policy_rows():
    """Verifier parser-only vector. Never emitted as a native acceptance report."""
    rows = []
    def event(kind, **fields):
        rows.append({'event': kind, 'elapsed_seconds': len(rows) / 10, **fields})
    def call(method, source, line, identity, phase, offset, **fields):
        event('native_fight_call', method=method, source=source, source_line=line,
              call_id=identity, owner_id=50, phase=phase, offset=offset, flash_bound=True, **fields)
    event('hangar_bootstrap_step', stage='module_capabilities', phase='begin')
    event('battle_capability_policy', phase='install', policy_version=1, battle_available=False,
          original_update_preserved=True, audited_source=v.FIGHT_SOURCE, audited_pyc_sha256=v.FIGHT_SHA,
          original_method_code_sha256=v.BATTLE_METHOD_HASHES.copy(),
          bindings=['fightClick', '_FightButton__disableFightButton'])
    event('hangar_bootstrap_step', stage='module_capabilities', phase='return')
    call('update', v.FIGHT_SOURCE, 103, 1, 'call', -1)
    call('__disableFightButton', v.FIGHT_SOURCE, 204, 2, 'call', -1, isDisabled=True, toolTip=v.BATTLE_TOOLTIP)
    call('as_disableFightButtonS', v.FIGHT_META, 30, 3, 'call', -1, isDisabled=True, toolTip=v.BATTLE_TOOLTIP)
    call('as_disableFightButtonS', v.FIGHT_META, 30, 3, 'return', 30, isDisabled=True, toolTip=v.BATTLE_TOOLTIP)
    call('__disableFightButton', v.FIGHT_SOURCE, 204, 2, 'return', 19, isDisabled=True, toolTip=v.BATTLE_TOOLTIP)
    event('battle_capability_disabled', policy_version=1, phase='return', disabled=True, tool_tip=v.BATTLE_TOOLTIP,
          original_disable_called=True, original_update_preserved=True)
    call('as_setFightButtonS', v.FIGHT_META, 42, 4, 'call', -1, isEnabled=True, label='В бой!')
    call('as_setFightButtonS', v.FIGHT_META, 42, 4, 'return', 36, isEnabled=True, label='В бой!')
    call('update', v.FIGHT_SOURCE, 103, 1, 'return', 519)
    event('battle_capability_denied', policy_version=1, capability='battle', action='fight',
          origin='project_test_service_policy', original_callback_called=False,
          dispatcher_called=False, original_mutation_called=False)
    event('battle_capability_notice', policy_version=1, phase='return', channel='original_SystemMessages_Warning')
    event('battle_capability_policy', policy_version=1, phase='restore', original_binding_restored=True,
          restored_bindings=['fightClick', '_FightButton__disableFightButton'])
    event('hangar_cleanup', stage='module_capabilities', outcome='PASS')
    return rows


class LimitsPolicyParserControls(unittest.TestCase):
    def test_synthetic_parser_vector_never_claims_readback(self):
        value = v.battle_policy(synthetic_policy_rows())
        self.assertEqual(value['status'], 'PASS')
        self.assertTrue(value['native_button_readback'].startswith('NOT_RUN'))

    def test_unbound_fallback_is_not_display_success(self):
        rows = synthetic_policy_rows()
        for row in rows:
            if row.get('method') == 'as_disableFightButtonS':
                row['flash_bound'] = False
                if row['phase'] == 'return':
                    row['offset'] = 34
        with self.assertRaises(ValueError):
            v.battle_policy(rows)

    def test_unchanged_original_update_is_mandatory(self):
        rows = synthetic_policy_rows()
        rows[1]['original_method_code_sha256']['update'] = '0' * 64
        with self.assertRaises(ValueError):
            v.battle_policy(rows)

    def test_non_nested_meta_does_not_prove_original_path(self):
        rows = synthetic_policy_rows()
        for row in rows:
            if row.get('method') == 'as_disableFightButtonS':
                row['owner_id'] = 99
        with self.assertRaises(ValueError):
            v.battle_policy(rows)

    def test_altered_tooltip_is_not_expected_policy(self):
        rows = synthetic_policy_rows()
        rows[5]['toolTip'] = 'Подмена'
        with self.assertRaises(ValueError):
            v.battle_policy(rows)

    def test_fake_denial_with_actual_dispatcher_is_rejected(self):
        rows = synthetic_policy_rows()
        rows[12]['dispatcher_called'] = True
        with self.assertRaises(ValueError):
            v.battle_policy(rows)

    def test_missing_original_warning_is_rejected(self):
        rows = [r for r in synthetic_policy_rows() if r['event'] != 'battle_capability_notice']
        with self.assertRaises(ValueError):
            v.battle_policy(rows)

    def test_unrestored_policy_is_rejected(self):
        rows = synthetic_policy_rows()
        rows[14]['original_binding_restored'] = False
        with self.assertRaises(ValueError):
            v.battle_policy(rows)

    def test_replacing_update_binding_is_outside_scope(self):
        rows = synthetic_policy_rows()
        rows[1]['bindings'].append('update')
        with self.assertRaises(ValueError):
            v.battle_policy(rows)


class LimitsReadbackParserControls(unittest.TestCase):
    """Synthetic structure tests. No rows here are native acceptance evidence."""
    def setUp(self):
        self.expected = {'native_id': 1, 'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
                         'profile': {'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}}}
        self.row = {'stable_seconds': 2.01, 'state': {'page': 'Hangar', 'alias': 'hangar',
                    'flash_bound': True, 'waiting_visible': False, 'selected_inventory_id': 1,
                    'fight_button_enabled': False, 'fight_owner': 51,
                    'identity': v.state_identity(self.expected),
                    'tooltip_readback': {'status': 'UNKNOWN', 'error_type': 'AttributeError'}}}

    def test_unknown_private_tooltip_remains_unknown(self):
        result = v.native_state(self.row, 0, self.expected)
        self.assertEqual(result['tooltip_readback']['status'], 'UNKNOWN')

    def test_policy_marker_cannot_replace_native_readback(self):
        self.row['state'].pop('fight_button_enabled')
        self.row['state']['disabled'] = True
        with self.assertRaises(ValueError):
            v.native_state(self.row, 0, self.expected)

    def test_enabled_button_rejected(self):
        self.row['state']['fight_button_enabled'] = True
        with self.assertRaises(ValueError):
            v.native_state(self.row, 0, self.expected)

    def test_integer_zero_is_not_boolean_false(self):
        self.row['state']['fight_button_enabled'] = 0
        with self.assertRaises(ValueError):
            v.native_state(self.row, 0, self.expected)

    def test_wrong_vehicle_or_page_rejected(self):
        for step in (1, 2):
            with self.subTest(step=step), self.assertRaises(ValueError):
                v.native_state(self.row, step, self.expected)

    def test_account_or_resources_cannot_change(self):
        for path in ('database_id', 'resources', 'statistics'):
            row = copy.deepcopy(self.row)
            if path == 'database_id':
                row['state']['identity'][path] = 2
            else:
                row['state']['identity'][path][0] += 1
            with self.subTest(path=path), self.assertRaises(ValueError):
                v.native_state(row, 0, self.expected)

    def test_invented_observed_tooltip_rejected(self):
        self.row['state']['tooltip_readback'] = {'status': 'OBSERVED', 'value': 'В бой!'}
        with self.assertRaises(ValueError):
            v.native_state(self.row, 0, self.expected)

    def test_unstable_or_nonfinite_observation_rejected(self):
        for value in (0, 1.99, float('nan'), float('inf'), True):
            row = copy.deepcopy(self.row)
            row['stable_seconds'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                v.native_state(row, 0, self.expected)

    def test_foreign_or_unbound_owner_rejected(self):
        for key, value in (('flash_bound', False), ('fight_owner', None), ('waiting_visible', True)):
            row = copy.deepcopy(self.row)
            row['state'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.native_state(row, 0, self.expected)

    def test_relogin_cannot_use_same_trace(self):
        case = {'status': 'PASS', 'install': 'same', 'checks': {'runtime_trace': {'sha256': 'abc'}}}
        with self.assertRaisesRegex(ValueError, 'reused same'):
            v.crew.relogin(case, copy.deepcopy(case))

    def test_partial_run_cannot_be_promoted_by_relogin(self):
        with self.assertRaisesRegex(ValueError, 'independently'):
            v.crew.relogin({'status': 'PASS'}, {'status': 'NOT_RUN'})

    def test_missing_scenario_never_accepts_lone_disable_state(self):
        with self.assertRaisesRegex(ValueError, 'event count'):
            v.limits_scenario([{'event': 'limits_scenario_state', **self.row}], {}, {}, self.expected,
                              ROOT / 'local', {'status': 'PASS'}, {'status': 'PASS'})


class LimitsNativeFailedRunControls(unittest.TestCase):
    """Closed real limits01 remains a failed scenario despite useful subproofs."""
    @classmethod
    def setUpClass(cls):
        cls.install = ROOT / 'local/evidence/20261005-p02-hangar-limits/limits01-prepare'
        if not (cls.install / 'native-outcome.json').is_file():
            raise unittest.SkipTest('Closed native limits01 corpus absent; NOT_RUN')
        cls.plan = v.crew.read_json(cls.install / 'install-plan.json', 1048576)
        cls.outcome = v.crew.read_json(cls.install / 'native-outcome.json')
        cls.rows, _ = v.entry.runtime_rows(cls.install, cls.plan, cls.outcome, ROOT / 'local')

    def test_actual_new_compiled_chain_and_greeting_are_subproofs(self):
        self.assertEqual(v.compiled_sources(self.install, self.plan, self.outcome)['status'], 'PASS')
        proof = v.greeting_resource(self.install, self.plan)
        self.assertEqual((proof['changed_key'], proof['unchanged_entries']), ('connected', 655))

    def test_actual_original_greeting_nested_returns(self):
        self.assertEqual(v.native_greeting(self.rows)['original_returns'], [31, 61])

    def test_successful_exit_does_not_erase_scenario_error(self):
        proof = v.crew.runtime_common(self.install, self.plan, self.outcome, self.rows)
        self.assertEqual(proof['checks']['process_restore']['status'], 'PASS')
        self.assertEqual(proof['checks']['engine_cleanup']['status'], 'PASS')
        self.assertEqual(proof['checks']['native_errors']['trace_error_count'], 2)
        self.assertEqual(proof['status'], 'FAIL')

    def test_original_disable_alone_does_not_prove_guarded_callback(self):
        with self.assertRaisesRegex(ValueError, 'denial/notice'):
            v.battle_policy(self.rows)

    def test_truncated_scenario_cannot_pass_complete_gate(self):
        expected = {'native_id': 1, 'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
                    'profile': {'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}}}
        with self.assertRaisesRegex(ValueError, 'event count'):
            v.limits_scenario(self.rows, self.outcome, self.plan, expected, ROOT / 'local',
                              {'status': 'PASS'}, {'status': 'PASS'})

    def test_greeting_replaced_after_native_call_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            if row['event'] == 'native_greeting_call' and row.get('method') == 'pushI18nMessage' and row.get('phase') == 'return':
                row['text'] = 'Подменённое приветствие'
        with self.assertRaisesRegex(ValueError, 'translation'):
            v.native_greeting(rows)


class LimitsNativePositiveRejectionControls(unittest.TestCase):
    """Tampering controls based on the closed native02 corpus, never new runs."""
    @classmethod
    def setUpClass(cls):
        base = ROOT / 'local/evidence/20261005-p02-hangar-limits'
        cls.install = base / 'limits02-prepare'
        report = base / 'wire/verify-limits02-01/hangar-limits-verification.json'
        if not report.is_file():
            raise unittest.SkipTest('Closed native limits02 independent report absent; NOT_RUN')
        cls.proof = v.crew.read_json(report, 4 * 1024 * 1024)
        cls.plan = v.crew.read_json(cls.install / 'install-plan.json', 1048576)
        cls.outcome = v.crew.read_json(cls.install / 'native-outcome.json')
        cls.rows, cls.trace = v.entry.runtime_rows(cls.install, cls.plan, cls.outcome, ROOT / 'local')
        cls.expected = {'native_id': 1, 'name': 'sr_ascii_f4d1e9',
                        'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
                        'profile': {'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}}}
        cls.checks = cls.proof['session']['checks']

    def scenario(self, rows):
        return v.limits_scenario(rows, self.outcome, self.plan, self.expected, ROOT / 'local',
                                 self.checks['crew_preservation'], self.checks['battle_policy'])

    def test_real_six_native_states_and_images_link_to_original_owner(self):
        result = self.scenario(self.rows)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual([x['selected_inventory_id'] for x in result['states']], [1, 2, 2, 1, 1, 1])
        self.assertTrue(all(x['fight_button_enabled'] is False for x in result['states']))

    def test_enabled_after_profile_is_not_hidden_by_previous_disabled_states(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['event'] == 'limits_scenario_state' and r['step'] == 3)['state']['fight_button_enabled'] = True
        with self.assertRaisesRegex(ValueError, 'readback'):
            self.scenario(rows)

    def test_borrowed_native_button_owner_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['event'] == 'limits_scenario_state' and r['step'] == 4)['state']['fight_owner'] += 1
        with self.assertRaisesRegex(ValueError, 'receiver'):
            self.scenario(rows)

    def test_changed_original_action_order_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['event'] == 'limits_scenario_action' and r['action'] == 'open_profile')['action'] = 'close_profile'
        with self.assertRaisesRegex(ValueError, 'action order'):
            self.scenario(rows)

    def test_native_profile_callbacks_are_identity_bound(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            if row['event'] == 'native_profile_call' and row['method'] == 'as_setUserDataS':
                row['owner_id'] += 1
        with self.assertRaisesRegex(ValueError, 'different native summary owners'):
            v.original_profile(rows, self.expected, *self.checks['limits_scenario']['profile_window'])

    def test_native_profile_invented_progress_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        for row in rows:
            if row['event'] == 'native_profile_call' and row['method'] == 'as_responseDossierS':
                row['data']['battlesCount'] = 1
        with self.assertRaisesRegex(ValueError, 'battle counts'):
            v.original_profile(rows, self.expected, *self.checks['limits_scenario']['profile_window'])

    def test_tooltip_outside_its_image_window_is_rejected(self):
        scenario = copy.deepcopy(self.checks['limits_scenario'])
        scenario['tooltip_window'][1] = scenario['tooltip_window'][0]
        with self.assertRaisesRegex(ValueError, 'screenshot window'):
            v.battle_tooltip(self.rows, scenario)

    def test_pixel_review_cannot_be_borrowed_from_another_trace(self):
        review = v.crew.read_json(self.install / 'visual-review-limits.json', 65536)
        review['trace_sha256'] = '0' * 64
        with patch.object(v, 'read_limited', return_value=json.dumps(review).encode()), self.assertRaisesRegex(ValueError, 'trace/source'):
            v.visual_review(self.install, self.trace['sha256'], self.checks['limits_scenario'])


    def test_native_warning_file_existence_is_not_pixel_success(self):
        review = v.crew.read_json(self.install / 'visual-review-limits.json', 65536)
        for row in review['images']:
            if row['file'].startswith('limits_denied_'):
                row['battle_warning_visible'] = False
        with patch.object(v, 'read_limited', return_value=json.dumps(review).encode()), self.assertRaisesRegex(ValueError, 'visually observed'):
            v.visual_review(self.install, self.trace['sha256'], self.checks['limits_scenario'])


class LimitsCachedReloginControls(unittest.TestCase):
    """Real02/03 pair with deliberate report-input mutations for rejection tests."""
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'local/evidence/20261005-p02-hangar-limits/wire/verify-limits03-strict-01/hangar-limits-verification.json'
        if not path.is_file():
            raise unittest.SkipTest('Closed real02/03 strict pair absent; NOT_RUN')
        proof = v.crew.read_json(path, 4 * 1024 * 1024)
        cls.current, cls.previous = proof['session'], proof['previous_session']

    def test_actual_cached_pair_is_accepted(self):
        proof = v.relogin(self.current, self.previous)
        self.assertTrue(proof['real_cached_relogin'])
        self.assertEqual(proof['current_cache_hints'], proof['previous_cache_hints'])

    def test_other_profile_directory_is_not_cached_relogin(self):
        current = copy.deepcopy(self.current)
        current['checks']['client_profile']['directory'] = str(ROOT / 'local/another-profile')
        with self.assertRaisesRegex(ValueError, 'another native client profile'):
            v.relogin(current, self.previous)

    def test_missing_profile_provenance_is_rejected(self):
        current = copy.deepcopy(self.current)
        current['checks'].pop('client_profile')
        with self.assertRaisesRegex(ValueError, 'provenance absent'):
            v.relogin(current, self.previous)

    def test_empty_account_hint_cannot_claim_cached_relogin(self):
        current = copy.deepcopy(self.current)
        for row in current['checks']['wire']['commands']:
            if row['command'] == 100:
                row['persistent_crc'] = 0
        with self.assertRaisesRegex(ValueError, 'nonzero native cache'):
            v.relogin(current, self.previous)

    def test_empty_shop_hint_cannot_claim_cached_relogin(self):
        current = copy.deepcopy(self.current)
        for row in current['checks']['wire']['commands']:
            if row['command'] == 300:
                row['cached_bytes'], row['cached_crc32_signed'] = 0, 0
        with self.assertRaisesRegex(ValueError, 'nonzero native cache'):
            v.relogin(current, self.previous)

    def test_fresh_dossier_cursor_is_not_persistent_cursor(self):
        current = copy.deepcopy(self.current)
        for row in current['checks']['wire']['commands']:
            if row['command'] == 600:
                row['revision'], row['last_change_time'] = 0, 0
        with self.assertRaisesRegex(ValueError, 'nonzero native cache'):
            v.relogin(current, self.previous)

    def test_consistent_but_changed_account_crc_is_rejected(self):
        current = copy.deepcopy(self.current)
        for row in current['checks']['wire']['commands']:
            if row['command'] == 100:
                row['persistent_crc'] += 1
        with self.assertRaisesRegex(ValueError, 'existing account cache descriptor changed'):
            v.relogin(current, self.previous)

    def test_changed_existing_shop_crc_is_rejected(self):
        current = copy.deepcopy(self.current)
        for row in current['checks']['wire']['commands']:
            if row['command'] == 300:
                row['cached_crc32_signed'] += 1
        with self.assertRaisesRegex(ValueError, 'existing shop cache descriptor changed'):
            v.relogin(current, self.previous)

    def test_refresh_must_reuse_initial_cached_descriptor(self):
        current = copy.deepcopy(self.current)
        for row in current['checks']['wire']['commands']:
            if row['kind'] == 'refresh':
                row['persistent_crc'] += 1
        with self.assertRaisesRegex(ValueError, 'changed from initial'):
            v.relogin(current, self.previous)

if __name__ == '__main__':
    unittest.main(verbosity=2)
