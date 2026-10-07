"""Strict parser controls; synthetic vectors never stand for native acceptance."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_hangar_windows as v


def policy_vector():
    """Unit-only structure, no client execution or pixel claim."""
    bindings = [r[1] for r in v.METHODS]
    rows = [{'event': 'hangar_bootstrap_step', 'stage': 'module_capabilities', 'phase': 'begin'},
            {'event': 'window_capability_policy', 'policy_version': 1, 'phase': 'install',
             'unavailable_windows': ['appearance', 'maintenance'], 'original_module_details_preserved': True,
             'audited_source': v.PANEL_SOURCE, 'audited_pyc_sha256': v.PANEL_SHA,
             'original_method_code_sha256': {r[1]: r[4] for r in v.METHODS}, 'bindings': bindings},
            {'event': 'hangar_bootstrap_step', 'stage': 'module_capabilities', 'phase': 'return'}]
    for action, callback, _, _, _ in v.METHODS:
        rows.extend([{'event': 'window_capability_denied', 'policy_version': 1, 'action': action,
                      'callback': callback, 'origin': 'project_test_service_policy', 'original_callback_called': False,
                      'native_event_called': False, 'original_mutation_called': False},
                     {'event': 'window_capability_notice', 'policy_version': 1, 'phase': 'return',
                      'action': action, 'callback': callback, 'channel': 'original_SystemMessages_Warning'}])
    rows.extend([{'event': 'window_capability_policy', 'policy_version': 1, 'phase': 'restore',
                  'original_binding_restored': True, 'restored_bindings': bindings},
                 {'event': 'hangar_cleanup', 'stage': 'module_capabilities', 'outcome': 'PASS'}])
    return rows


class WindowPolicyControls(unittest.TestCase):
    def test_unit_vector_has_explicitly_limited_scope(self):
        proof = v.window_policy(policy_vector())
        self.assertEqual([r['action'] for r in proof['denials']], ['appearance', 'maintenance'])
        self.assertIn('no claim', proof['scope'])

    def test_original_callback_or_event_or_mutation_cannot_run(self):
        for key in ('original_callback_called', 'native_event_called', 'original_mutation_called'):
            rows = policy_vector()
            rows[3][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.window_policy(rows)

    def test_marker_without_native_warning_return_is_rejected(self):
        rows = [r for r in policy_vector() if not (r['event'] == 'window_capability_notice' and r['action'] == 'appearance')]
        with self.assertRaisesRegex(ValueError, 'two explicit'):
            v.window_policy(rows)

    def test_maintenance_cannot_be_substituted_for_appearance(self):
        rows = policy_vector()
        rows[3]['callback'] = 'showTechnicalMaintenance'
        with self.assertRaises(ValueError):
            v.window_policy(rows)

    def test_global_dispatcher_guard_is_outside_approved_scope(self):
        rows = policy_vector()
        rows[1]['bindings'].append('showLobbyView')
        with self.assertRaises(ValueError):
            v.window_policy(rows)

    def test_source_signature_cannot_be_borrowed(self):
        rows = policy_vector()
        rows[1]['original_method_code_sha256']['showCustomization'] = '0' * 64
        with self.assertRaises(ValueError):
            v.window_policy(rows)

    def test_nonrestored_binding_fails(self):
        rows = policy_vector()
        rows[-2]['original_binding_restored'] = False
        with self.assertRaises(ValueError):
            v.window_policy(rows)

    def test_restore_after_cleanup_is_rejected(self):
        rows = policy_vector()
        rows[-2], rows[-1] = rows[-1], rows[-2]
        with self.assertRaisesRegex(ValueError, 'lifecycle'):
            v.window_policy(rows)

    def test_other_capability_attempt_is_not_this_card(self):
        for event in ('battle_capability_denied', 'crew_capability_denied', 'capability_denied'):
            rows = policy_vector() + [{'event': event}]
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, 'another unsupported'):
                v.window_policy(rows)

    def test_details_preservation_is_required(self):
        rows = policy_vector()
        rows[1]['original_module_details_preserved'] = False
        with self.assertRaises(ValueError):
            v.window_policy(rows)


class WindowOriginalContracts(unittest.TestCase):
    def test_original_void_entry_code_and_event_returns(self):
        proof = v.original_contracts()
        self.assertEqual(proof['status'], 'PASS')
        self.assertEqual([r['normal_return'] for r in proof['entry_contracts']], [31, 25])
        self.assertEqual([r['source_line'] for r in proof['unsupported_populate']], [62, 43])

    def test_previous_verifiers_are_unchanged(self):
        self.assertEqual(v.frozen_dependencies()['status'], 'PASS')

    def test_old_ten_modules_do_not_prove_two_window_guards(self):
        install = ROOT / 'local/evidence/20261005-p02-hangar-limits/limits03-prepare'
        if not (install / 'native-outcome.json').is_file():
            self.skipTest('Frozen native limits03 absent; NOT_RUN')
        plan = v.crew.read_json(install / 'install-plan.json', 1048576)
        outcome = v.crew.read_json(install / 'native-outcome.json')
        with self.assertRaisesRegex(ValueError, 'eleven'):
            v.compiled_sources(install, plan, outcome)

    def test_layout_command_cannot_pass_even_if_refused_by_server(self):
        path = ROOT / 'local/evidence/20261005-p02-hangar-limits/wire/verify-limits03-strict-01/hangar-limits-verification.json'
        if not path.is_file():
            self.skipTest('Frozen native limits03 wire absent; NOT_RUN')
        wire = copy.deepcopy(json.loads(path.read_text(encoding='utf8'))['session']['checks']['wire'])
        self.assertEqual(v.limits.no_gameplay_commands(wire)['status'], 'PASS')
        wire['commands'].append({'kind': 'unavailable', 'command': 108, 'request': 300})
        with self.assertRaisesRegex(ValueError, 'mutation command'):
            v.limits.no_gameplay_commands(wire)


class WindowAbsentCallControls(unittest.TestCase):
    """Zero recorded calls is not proof unless the installed observer stayed live."""
    def vector(self):
        rows = policy_vector()
        proof = v.window_policy(rows)
        for phase, offset in (('call', -1), ('return', 366)):
            rows.append({'event': 'native_account_call', 'method': 'onBecomeNonPlayer',
                         'source': 'scripts/client/Account.py', 'source_line': 246,
                         'phase': phase, 'offset': offset, 'call_id': 100, 'owner_id': 77})
        return rows, proof

    def test_unit_absence_requires_live_original_callback_after_actions(self):
        rows, proof = self.vector()
        value = v.unsupported_absence(rows, {'status': 'PASS'}, proof)
        self.assertEqual(value['unsupported_entry_and_populate_calls'], 0)
        self.assertEqual(value['profiler_active_after_both_actions']['return_offset'], 366)

    def test_unknown_observer_coverage_cannot_prove_absence(self):
        rows, proof = self.vector()
        with self.assertRaisesRegex(ValueError, 'prerequisite'):
            v.unsupported_absence(rows, {'status': 'NOT_RUN'}, proof)

    def test_original_entry_call_fails_even_when_policy_claimed_denial(self):
        rows, proof = self.vector()
        rows.append({'event': 'native_unsupported_window_call', 'method': 'showCustomization'})
        with self.assertRaisesRegex(ValueError, 'executed'):
            v.unsupported_absence(rows, {'status': 'PASS'}, proof)

    def test_original_window_population_fails(self):
        rows, proof = self.vector()
        rows.append({'event': 'native_unsupported_window_call', 'method': '_populate'})
        with self.assertRaisesRegex(ValueError, 'executed'):
            v.unsupported_absence(rows, {'status': 'PASS'}, proof)

    def test_absence_after_profiler_limit_is_not_success(self):
        rows, proof = self.vector()
        rows.append({'event': 'observation_limit'})
        with self.assertRaisesRegex(ValueError, 'budget'):
            v.unsupported_absence(rows, {'status': 'PASS'}, proof)

    def test_stopped_profiler_cannot_prove_absence(self):
        rows, proof = self.vector()
        with self.assertRaisesRegex(ValueError, 'completion'):
            v.unsupported_absence(rows[:-2], {'status': 'PASS'}, proof)


def expected_vector():
    return {'native_id': 1, 'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
            'profile': {'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}}}


def state_vector():
    """Unit-only structure; no input here is an actual native observation."""
    return {**v.limits.state_identity(expected_vector()), 'selected_inventory_id': 1,
            'hangar_owner': 11, 'crew_owner': 12, 'ammunition_owner': 13,
            'view_scan': {'version': 1, 'scope': 'LOBBY_SUB_current_and_WINDOW_alias',
                          'lobby_sub': {'class_name': 'Hangar', 'alias': 'hangar', 'flash_bound': True, 'owner_id': 11},
                          'window': {'view_count': 0, 'queried_alias': 'technicalMaintenance', 'matched_view': None},
                          'unsupported_present': False}}


class WindowTargetedScanControls(unittest.TestCase):
    def setUp(self):
        self.state, self.expected = state_vector(), expected_vector()

    def test_targeted_clear_scan_accepts_unrelated_popup_count(self):
        self.state['view_scan']['window']['view_count'] = 2
        self.assertEqual(v.window_state(self.state, self.expected)['view_scan']['window']['view_count'], 2)

    def test_plain_getview_none_is_not_absence_proof(self):
        self.state['view_scan']['window'].pop('queried_alias')
        with self.assertRaisesRegex(ValueError, 'alias query'):
            v.window_state(self.state, self.expected)

    def test_unrelated_alias_query_is_rejected(self):
        self.state['view_scan']['window']['queried_alias'] = 'settings'
        with self.assertRaisesRegex(ValueError, 'alias query'):
            v.window_state(self.state, self.expected)

    def test_matching_maintenance_even_unbound_is_rejected(self):
        self.state['view_scan']['window']['matched_view'] = {'class_name': 'TechnicalMaintenance', 'flash_bound': False}
        with self.assertRaisesRegex(ValueError, 'alias query'):
            v.window_state(self.state, self.expected)

    def test_visible_appearance_cannot_be_hidden_by_false_flag(self):
        self.state['view_scan']['lobby_sub'].update(class_name='VehicleCustomization', alias='customization')
        with self.assertRaisesRegex(ValueError, 'Hangar differs'):
            v.window_state(self.state, self.expected)

    def test_boolean_or_unbounded_popup_count_rejected(self):
        for value in (True, -1, 65, 1.0):
            self.state['view_scan']['window']['view_count'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                v.window_state(self.state, self.expected)

    def test_unbound_hangar_rejected(self):
        self.state['view_scan']['lobby_sub']['flash_bound'] = False
        with self.assertRaisesRegex(ValueError, 'unbound'):
            v.window_state(self.state, self.expected)

    def test_another_hangar_owner_rejected(self):
        self.state['view_scan']['lobby_sub']['owner_id'] = 14
        with self.assertRaisesRegex(ValueError, 'Hangar differs'):
            v.window_state(self.state, self.expected)

    def test_boolean_owner_or_identity_not_equal_integer(self):
        for key in ('hangar_owner', 'database_id', 'selected_inventory_id'):
            state = state_vector()
            state[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                v.window_state(state, self.expected)

    def test_resources_changed_rejected(self):
        self.state['resources'][0] -= 1
        with self.assertRaisesRegex(ValueError, 'resources'):
            v.window_state(self.state, self.expected)

    def test_unknown_scan_scope_rejected(self):
        self.state['view_scan']['scope'] = 'all_windows_are_empty'
        with self.assertRaisesRegex(ValueError, 'targeted'):
            v.window_state(self.state, self.expected)


def action_vector():
    rows = [{'event': 'unit_only'} for _ in range(32)]
    states = [(2, {'state': state_vector()}), (14, {'state': state_vector()}), (25, {'state': state_vector()})]
    shots = [(5, {}), (17, {}), (28, {})]
    policy = {'denials': []}
    for step, (action, callback, _, _, _) in enumerate(v.METHODS, 1):
        base = 6 if step == 1 else 18
        for position, moment in ((base, 'call'), (base + 3, 'return')):
            rows[position] = {'event': 'windows_scenario_action', 'action': action, 'moment': moment,
                              'version': 1, 'step': step, 'phase': 'waiting_png', 'callback': 'AmmunitionPanel.' + callback,
                              'owner_id': 13, 'state': state_vector()}
        rows[base]['origin'] = 'explicit_diagnostic_of_installed_UI_policy'
        policy['denials'].append({'denied_line': base + 2, 'notice_line': base + 3})
    return rows, states, shots, policy


class WindowActionControls(unittest.TestCase):
    def test_denial_nested_in_two_installed_callbacks(self):
        args = action_vector()
        proof = v.window_actions(*args, expected_vector(), 0)
        self.assertEqual(proof, {'appearance': [6, 9], 'maintenance': [18, 21]})

    def test_warning_before_callback_does_not_count(self):
        rows, states, shots, policy = action_vector()
        policy['denials'][0]['notice_line'] = 2
        with self.assertRaisesRegex(ValueError, 'inside'):
            v.window_actions(rows, states, shots, policy, expected_vector(), 0)

    def test_wrong_callback_owner_rejected(self):
        rows, states, shots, policy = action_vector()
        rows[6]['owner_id'] = 14
        with self.assertRaisesRegex(ValueError, 'owner'):
            v.window_actions(rows, states, shots, policy, expected_vector(), 0)

    def test_omitted_after_scan_rejected(self):
        rows, states, shots, policy = action_vector()
        rows[9].pop('state')
        with self.assertRaisesRegex(ValueError, 'state'):
            v.window_actions(rows, states, shots, policy, expected_vector(), 0)

    def test_window_appearing_after_callback_rejected(self):
        rows, states, shots, policy = action_vector()
        rows[9]['state']['view_scan']['window']['matched_view'] = {'alias': 'technicalMaintenance'}
        with self.assertRaisesRegex(ValueError, 'alias query'):
            v.window_actions(rows, states, shots, policy, expected_vector(), 0)

    def test_unexpected_extra_callback_rejected(self):
        rows, states, shots, policy = action_vector()
        rows[23] = copy.deepcopy(rows[6])
        with self.assertRaisesRegex(ValueError, 'order/count'):
            v.window_actions(rows, states, shots, policy, expected_vector(), 0)

    def test_unchanged_identity_with_replaced_panel_is_rejected(self):
        rows, states, shots, policy = action_vector()
        for position in (18, 21):
            rows[position]['state']['crew_owner'] = 99
        with self.assertRaisesRegex(ValueError, 'stable native owner'):
            v.window_actions(rows, states, shots, policy, expected_vector(), 0)

    def test_bounded_harmless_window_change_inside_callback_is_not_identical_view(self):
        rows, states, shots, policy = action_vector()
        rows[9]['state']['view_scan']['window']['view_count'] = 1
        with self.assertRaisesRegex(ValueError, 'changed native window'):
            v.window_actions(rows, states, shots, policy, expected_vector(), 0)


class WindowRealCaptureControls(unittest.TestCase):
    """Mutated copies of a closed native run; never replace its saved evidence."""
    @classmethod
    def setUpClass(cls):
        cls.install = ROOT / 'local/evidence/20261005-p02-hangar-windows/windows01-prepare'
        report = ROOT / 'local/evidence/20261005-p02-hangar-windows/wire/verify-windows01-02/hangar-windows-verification.json'
        if not report.is_file():
            raise unittest.SkipTest('Closed native windows01 absent; NOT_RUN')
        cls.proof = v.crew.read_json(report, 16 * 1024 * 1024)
        cls.plan = v.crew.read_json(cls.install / 'install-plan.json', 1024 * 1024)
        cls.outcome = v.crew.read_json(cls.install / 'native-outcome.json', 262144)
        cls.local_root = v.config()[1]['local_artifacts_root']
        cls.rows, cls.info = v.entry.runtime_rows(cls.install, cls.plan, cls.outcome, cls.local_root)
        cls.preservation = cls.proof['session']['checks']['crew_preservation']
        cls.policy = v.window_policy(cls.rows)
        cls.scenario = cls.proof['session']['checks']['windows_scenario']
        cls.review = v.crew.read_json(cls.install / 'visual-review-windows.json', 65536)

    def run_scenario(self, rows=None, outcome=None):
        return v.windows_scenario(self.rows if rows is None else rows, self.outcome if outcome is None else outcome,
                                  self.plan, expected_vector(), self.local_root, self.preservation, self.policy)

    def review_copy(self, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf8')
        with patch.object(v, 'read_limited', return_value=raw):
            return v.visual_review(self.install, self.info['sha256'], self.scenario)

    def test_actual_complete_window_run_has_three_observed_images(self):
        self.assertEqual(len(self.run_scenario()['images']), 3)

    def test_actual_installed_profiler_covers_all_four_original_targets(self):
        result = v.observer_coverage(self.install, self.plan)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['original_entry_methods'], ['showCustomization', 'showTechnicalMaintenance'])

    def test_actual_eleven_source_chain_is_valid(self):
        result = v.compiled_sources(self.install, self.plan, self.outcome)
        self.assertEqual(len(result['modules']), 11)

    def test_real_run_with_added_scenario_error_fails(self):
        rows = copy.deepcopy(self.rows)
        rows.append({'event': 'windows_scenario_error'})
        with self.assertRaisesRegex(ValueError, 'failed or mixed'):
            self.run_scenario(rows)

    def test_timer_cannot_replace_condition_exit(self):
        outcome = copy.deepcopy(self.outcome)
        outcome['diagnostic_control']['quit_after_seconds'] = 30
        with self.assertRaisesRegex(ValueError, 'control scope'):
            self.run_scenario(outcome=outcome)

    def test_unsupported_window_after_screenshot_request_rejected(self):
        rows = copy.deepcopy(self.rows)
        shot = next(r for r in rows if r['event'] == 'windows_scenario_screenshot' and r['step'] == 1)
        shot['state']['view_scan']['window']['matched_view'] = {'alias': 'technicalMaintenance'}
        with self.assertRaisesRegex(ValueError, 'alias query'):
            self.run_scenario(rows)

    def test_final_native_state_must_remain_same_after_third_crew_read(self):
        rows = copy.deepcopy(self.rows)
        complete = next(r for r in rows if r['event'] == 'windows_scenario_complete')
        complete['state']['view_scan']['window']['view_count'] = 1
        with self.assertRaisesRegex(ValueError, 'final window'):
            self.run_scenario(rows)

    def test_native_png_hash_tampering_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['event'] == 'windows_scenario_screenshot')['screenshot']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'PNG hash'):
            self.run_scenario(rows)

    def test_native_state_without_stable_hold_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['event'] == 'windows_scenario_state')['stable_seconds'] = 0.25
        with self.assertRaisesRegex(ValueError, 'two seconds'):
            self.run_scenario(rows)

    def test_extra_unversioned_state_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['event'] == 'windows_scenario_state')['state']['unknown'] = None
        with self.assertRaisesRegex(ValueError, 'exact bounded'):
            self.run_scenario(rows)

    def test_missing_conditional_completion_not_saved_by_exit_zero(self):
        rows = [r for r in self.rows if r['event'] != 'diagnostic_condition_complete']
        with self.assertRaisesRegex(ValueError, 'event count'):
            self.run_scenario(rows)

    def test_actual_review_absolute_paths_and_exact_basenames_supported(self):
        self.assertEqual(self.review_copy(self.review)['status'], 'PASS')
        review = copy.deepcopy(self.review)
        for row in review['images']:
            row['file'] = Path(row['file']).name
        self.assertEqual(self.review_copy(review)['status'], 'PASS')

    def test_review_cannot_borrow_same_basename_from_another_directory(self):
        review = copy.deepcopy(self.review)
        review['images'][0]['file'] = str(ROOT / 'local/unrelated' / Path(review['images'][0]['file']).name)
        with self.assertRaisesRegex(ValueError, 'image hash mismatch'):
            self.review_copy(review)

    def test_warning_review_is_required_and_trace_bound(self):
        for key in ('appearance_warning_visible', 'maintenance_warning_visible'):
            review = copy.deepcopy(self.review)
            next(r for r in review['images'] if key in r)[key] = False
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'warning'):
                self.review_copy(review)
        review = copy.deepcopy(self.review)
        review['trace_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'trace/source'):
            self.review_copy(review)


if __name__ == '__main__':
    unittest.main(verbosity=2)
