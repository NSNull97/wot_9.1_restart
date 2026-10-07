"""Negative acceptance logic, not synthetic proof of native GUI compatibility.

Historical controls use already-frozen real traces when locally available; no
client is launched and no credentials are read by this test module.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import verify_hangar_ui as ui


def event(event_name, elapsed, **fields):
    return {'event': event_name, 'elapsed_seconds': elapsed, **fields}


def normal_input():
    plan = {'mode': 'interactive', 'normal_auto_login': False, 'normal_auto_quit': False,
            'settings': {'test_control': None}}
    rows = [event('init', 0, control_configured=False),
            event('project_login_submit', 2, source='original_LoginView.onLogin')]
    return plan, rows


def clean_lifecycle():
    rows = [event('connection_callback', 1, stage=1, status='LOGGED_ON', native_connected=True,
                  after_fini=False, original_callback='ConnectionManager.connectionWatcher'),
            event('fini_enter', 80)]
    rows.extend(event('hangar_cleanup', 80.1 + i / 100, stage=stage, outcome='PASS')
                for i, stage in enumerate(ui.STAGES))
    rows.extend((event('account_repository_closed', 81), event('fini', 81.1)))
    outcome = {'client_started': True, 'exit_code': 0, 'timed_out': False, 'exe_sha256': ui.EXE_SHA}
    return rows, outcome


class EntryModeTests(unittest.TestCase):
    def test_normal_has_no_diagnostic_quit_requirement(self):
        plan, rows = normal_input()
        self.assertEqual('PASS', ui.entry_mode(plan, rows, 'normal')['status'])

    def test_normal_rejects_diagnostic_credentials_or_autologin(self):
        for field in ('normal_auto_login', 'normal_auto_quit'):
            plan, rows = normal_input()
            plan[field] = True
            self.assertEqual('FAIL', ui.entry_mode(plan, rows, 'normal')['status'])
        plan, rows = normal_input()
        plan['settings']['test_control'] = 'local/private.json'
        self.assertEqual('FAIL', ui.entry_mode(plan, rows, 'normal')['status'])

    def test_normal_rejects_any_hidden_control_event(self):
        for name in ('diagnostic_login_submit', 'test_control_consumed', 'quit_requested'):
            plan, rows = normal_input()
            rows.append(event(name, 3))
            self.assertEqual('FAIL', ui.entry_mode(plan, rows, 'normal')['status'])

    def test_normal_rejects_missing_explicit_no_control_setting(self):
        plan, rows = normal_input()
        del plan['settings']['test_control']
        self.assertEqual('FAIL', ui.entry_mode(plan, rows, 'normal')['status'])

    def test_controlled_entry_allows_original_ui_exit_without_timer(self):
        plan, rows = normal_input()
        plan['settings']['test_control'] = 'local/private.json'
        rows[0]['control_configured'] = True
        rows.extend((event('test_control_consumed', 1, input_removed=True, credentials_present=True),
                     event('diagnostic_login_submit', 2, source='original_LoginPageMeta.as_doAutoLoginS', phase='begin', submit_via='flash'),
                     event('diagnostic_login_submit', 3, source='original_LoginPageMeta.as_doAutoLoginS', phase='return', submit_via='flash')))
        self.assertEqual('PASS', ui.entry_mode(plan, rows, 'controlled')['status'])
        self.assertEqual('FAIL', ui.entry_mode(plan, rows, 'normal')['status'])

    def test_matching_nickname_is_not_a_submission(self):
        plan, rows = normal_input()
        rows[1] = event('native_player', 2, name='test')
        self.assertEqual('FAIL', ui.entry_mode(plan, rows, 'normal')['status'])


class LifecycleTests(unittest.TestCase):
    def test_complete_engine_exit_does_not_require_quit_requested(self):
        rows, outcome = clean_lifecycle()
        self.assertEqual('PASS', ui.lifecycle(rows, outcome)['status'])

    def test_ten_cleanup_markers_do_not_hide_late_exception(self):
        rows, outcome = clean_lifecycle()
        rows.insert(7, event('python_exception', 80.145, traceback='redacted test failure'))
        report = ui.lifecycle(rows, outcome)
        self.assertEqual('PASS', report['checks']['engine_cleanup_order']['status'])
        self.assertEqual('FAIL', report['checks']['no_trace_errors_during_or_after_fini']['status'])
        self.assertEqual('FAIL', report['status'])

    def test_error_even_after_final_marker_is_rejected(self):
        rows, outcome = clean_lifecycle()
        rows.append(event('python_exception', 81.2, traceback='redacted test failure'))
        self.assertEqual('FAIL', ui.lifecycle(rows, outcome)['status'])

    def test_force_stop_exit_zero_is_not_native_exit(self):
        rows, outcome = clean_lifecycle()
        outcome['forced_stop'] = True
        self.assertEqual('FAIL', ui.lifecycle(rows, outcome)['status'])

    def test_timeout_or_boolean_exit_code_is_not_accepted(self):
        rows, outcome = clean_lifecycle()
        for changes in ({'timed_out': True}, {'exit_code': False}):
            altered = {**outcome, **changes}
            self.assertEqual('FAIL', ui.lifecycle(rows, altered)['status'])

    def test_missing_or_reordered_cleanup_is_rejected(self):
        rows, outcome = clean_lifecycle()
        self.assertEqual('FAIL', ui.lifecycle(rows[:2] + rows[3:], outcome)['status'])
        rows[2], rows[3] = rows[3], rows[2]
        self.assertEqual('FAIL', ui.lifecycle(rows, outcome)['status'])

    def test_native_disconnect_before_fini_is_not_clean_session(self):
        rows, outcome = clean_lifecycle()
        rows.insert(1, event('connection_callback', 70, stage=0, status='NOT_SET', native_connected=False,
                             after_fini=False, original_callback='ConnectionManager.connectionWatcher'))
        self.assertEqual('FAIL', ui.lifecycle(rows, outcome)['status'])

    def test_new_policy_requires_its_cleanup_in_original_order(self):
        rows, outcome = clean_lifecycle()
        self.assertEqual('FAIL', ui.lifecycle(rows, outcome, True)['status'])
        position = next(i for i, row in enumerate(rows) if row.get('stage') == 'area_destructibles')
        rows.insert(position, event('hangar_cleanup', 80.155, stage='module_capabilities', outcome='PASS'))
        self.assertEqual('PASS', ui.lifecycle(rows, outcome, True)['status'])
        self.assertEqual('FAIL', ui.lifecycle(rows, outcome, False)['status'])
        rows[position], rows[position + 1] = rows[position + 1], rows[position]
        self.assertEqual('FAIL', ui.lifecycle(rows, outcome, True)['status'])

    def test_error_report_does_not_copy_traceback_contents(self):
        rows = [event('python_exception', 2, traceback='secret must not be copied')]
        encoded = json.dumps(ui.native_error_events(rows))
        self.assertNotIn('secret', encoded)
        self.assertNotIn('traceback', encoded)


class ModulePolicyTests(unittest.TestCase):
    def rows(self):
        return [event('hangar_bootstrap_step', 1, stage='module_capabilities', phase='begin'),
                event('capability_policy', 2, phase='install', module_changes_available=False,
                      module_details_available=True, audited_source=ui.AMMUNITION_SOURCE, audited_pyc_sha256=ui.AMMUNITION_SHA),
                event('hangar_bootstrap_step', 3, stage='module_capabilities', phase='return'),
                event('capability_denied', 5, capability='module_changes', action='install_or_purchase',
                      origin='project_test_service_policy', original_mutation_called=False),
                event('capability_notice', 6, capability='module_changes', phase='return', channel='original_SystemMessages_Warning'),
                event('capability_policy', 8, phase='restore', original_binding_restored=True),
                event('hangar_cleanup', 9, stage='module_capabilities', outcome='PASS')]

    def test_missing_restore_or_mutation_available_cannot_pass_policy(self):
        rows = self.rows()
        with self.assertRaisesRegex(ValueError, 'lifecycle incomplete'):
            ui.module_policy_evidence(rows[:5] + rows[6:])
        rows[1]['module_changes_available'] = True
        with self.assertRaisesRegex(ValueError, 'audit or binding'):
            ui.module_policy_evidence(rows)

    def require_original(self):
        try:
            original = ui.config()[1]['original_client_root'] / 'res' / (ui.AMMUNITION_SOURCE + 'c')
        except (OSError, ValueError, KeyError):
            self.skipTest('NOT_RUN: local original source/config absent')
        if not original.exists():
            self.skipTest('NOT_RUN: local original source absent')

    def test_denial_is_only_a_warning_invocation_not_economic_success(self):
        self.require_original()
        report = ui.module_policy_evidence(self.rows())
        self.assertEqual('PASS', report['status'])
        self.assertEqual('PASS', report['invocation']['status'])
        self.assertIn('not a purchase', report['invocation']['scope'])
        rows = self.rows()
        report = ui.module_policy_evidence(rows[:3] + rows[5:])
        self.assertEqual('PASS', report['status'])
        self.assertEqual('NOT_RUN', report['invocation']['status'])

    def test_a_deny_without_original_warning_return_is_rejected(self):
        self.require_original()
        rows = self.rows()
        rows.pop(4)
        with self.assertRaisesRegex(ValueError, 'missing return'):
            ui.module_policy_evidence(rows)
        rows = self.rows()
        rows[3]['original_mutation_called'] = True
        with self.assertRaisesRegex(ValueError, 'original warning return'):
            ui.module_policy_evidence(rows)


def gui_contracts():
    return {(source, method, line): {offset} for source, method, line, offset in ui.UI_RETURNS}


def call_row(source, method, line, call_id, phase, offset, **fields):
    return event('native_tooltip_call', call_id + (0.1 if phase == 'return' else 0),
                 source=source, method=method, source_line=line, call_id=call_id,
                 phase=phase, offset=offset, owner_id=100, owner_class='ToolTip',
                 flash_bound=True, fini_started=False, **fields)


def tooltip_trace():
    outer = {'tooltipId': '#tooltips:test', 'stateType': None}
    generator = {**outer, 'tooltipType': 'tooltip'}
    rendered = {'tooltipData': 'original rendered contents', 'linkage': 'tooltip'}
    rows = [call_row(ui.TOOLTIP, 'onCreateComplexTooltip', 65, 1, 'call', -1, arguments=outer),
            call_row(ui.TOOLTIP, '__genComplexToolTip', 73, 2, 'call', -1, arguments=generator),
            call_row(ui.TOOLTIP_META, 'as_showS', 33, 3, 'call', -1, arguments=rendered),
            call_row(ui.TOOLTIP_META, 'as_showS', 33, 3, 'return', 30, arguments=rendered),
            call_row(ui.TOOLTIP, '__genComplexToolTip', 73, 2, 'return', 117, arguments=generator),
            call_row(ui.TOOLTIP, 'onCreateComplexTooltip', 65, 1, 'return', 28, arguments=outer)]
    for i, row in enumerate(rows):
        row['elapsed_seconds'] = i + 10
    return rows


class TooltipParserTests(unittest.TestCase):
    def test_nested_original_display_has_three_correlated_calls(self):
        report = ui.tooltip_evidence(tooltip_trace(), gui_contracts())
        self.assertEqual('PASS', report['status'])
        self.assertEqual(3, report['displays'][0]['show_call_id'])

    def test_an_exception_return_offset_is_not_a_normal_return(self):
        rows = tooltip_trace()
        rows[-1]['offset'] = 21
        with self.assertRaisesRegex(ValueError, 'normal RETURN_VALUE'):
            ui.tooltip_evidence(rows, gui_contracts())

    def test_none_never_becomes_empty_success(self):
        rows = tooltip_trace()
        for row in rows:
            if 'tooltipId' in row['arguments']:
                row['arguments']['tooltipId'] = None
        with self.assertRaisesRegex(ValueError, 'None ID'):
            ui.tooltip_evidence(rows, gui_contracts())

    def test_empty_input_is_not_a_display(self):
        rows = tooltip_trace()
        rows = [row for row in rows if row['method'] != 'as_showS']
        for row in rows:
            row['arguments']['tooltipId'] = ''
        rows[-2]['offset'] = 15
        contracts = gui_contracts()
        contracts[(ui.TOOLTIP, '__genComplexToolTip', 73)].add(15)
        self.assertEqual('NOT_RUN', ui.tooltip_evidence(rows, contracts)['status'])

    def test_unbound_flash_return_is_not_rendered(self):
        rows = tooltip_trace()
        rows[3]['offset'] = 34
        rows[2]['flash_bound'] = rows[3]['flash_bound'] = False
        contracts = gui_contracts()
        contracts[(ui.TOOLTIP_META, 'as_showS', 33)].add(34)
        self.assertEqual('NOT_RUN', ui.tooltip_evidence(rows, contracts)['status'])

    def test_wrong_receiver_or_crossing_call_stack_is_rejected(self):
        rows = tooltip_trace()
        rows[3]['owner_id'] = 101
        with self.assertRaisesRegex(ValueError, 'another call/receiver'):
            ui.tooltip_evidence(rows, gui_contracts())
        rows = tooltip_trace()
        rows[3], rows[4] = rows[4], rows[3]
        with self.assertRaisesRegex(ValueError, 'another call/receiver'):
            ui.tooltip_evidence(rows, gui_contracts())

    def test_omitted_render_callback_is_not_proof_of_pixels(self):
        rows = [row for row in tooltip_trace() if row['method'] != 'as_showS']
        self.assertEqual('NOT_RUN', ui.tooltip_evidence(rows, gui_contracts())['status'])

    def test_duplicate_call_identity_is_rejected(self):
        rows = tooltip_trace()
        rows[1]['call_id'] = 1
        with self.assertRaisesRegex(ValueError, 'duplicate/out-of-order'):
            ui.tooltip_evidence(rows, gui_contracts())

    def test_late_render_after_fini_is_not_positive(self):
        rows = tooltip_trace()
        rows[3]['fini_started'] = True
        with self.assertRaisesRegex(ValueError, 'live bound'):
            ui.tooltip_evidence(rows, gui_contracts())


class AwardsPayloadTests(unittest.TestCase):
    def native_shape(self):
        # Deliberately synthetic schema input. No native empty catalogue claim.
        return {'achievementsList': [[{'name': 'catalogueEntry', 'value': 0, 'isInDossier': False,
                                      'isDone': False, 'isRare': False}]] + [[] for _ in range(6)],
                'totalItemsList': [1, 0, 0, 0, 0, 0, 0], 'battlesCount': 0}

    def test_zero_battles_do_not_require_empty_original_catalogue(self):
        value = self.native_shape()
        original = copy.deepcopy(value)
        report = ui.awards_data(value)
        self.assertEqual('PASS', report['status'])
        self.assertEqual([1, 0, 0, 0, 0, 0, 0], report['block_lengths'])
        self.assertEqual(original, value)

    def test_truncated_observation_cannot_prove_awards_data(self):
        self.assertEqual('NOT_RUN', ui.awards_data({'truncated': True})['status'])
        value = self.native_shape()
        value['achievementsList'][0] = [{'description': {'truncated': True}}]
        self.assertEqual('NOT_RUN', ui.awards_data(value)['status'])

    def test_catalogue_totals_must_cover_displayed_items(self):
        value = self.native_shape()
        value['totalItemsList'][0] = 0
        with self.assertRaisesRegex(ValueError, 'exceeds native total'):
            ui.awards_data(value)

    def test_changed_battles_or_boolean_count_is_rejected(self):
        for count in (1, False):
            value = self.native_shape()
            value['battlesCount'] = count
            with self.assertRaisesRegex(ValueError, 'zero-battle'):
                ui.awards_data(value)

    def test_primitive_bounds_and_nonfinite_values_are_not_evidence(self):
        self.assertFalse(ui.bounded_plain(float('nan')))
        self.assertFalse(ui.bounded_plain('x' * 4097))
        self.assertFalse(ui.bounded_plain(list(range(257))))
        self.assertFalse(ui.bounded_plain({'unsupported_type': 'list'}))

    def summary(self):
        sections = [{**{key: 0 for key in ui.AWARDS_COUNTERS}, 'index': index} for index in range(7)]
        sections[0].update(packed_items=2, catalog_items=3, nonzero_value_items=1)
        return {'version': 1, 'battles_count': 0, 'section_count': 7, 'sections': sections,
                **{key: sum(row[key] for row in sections) for key in ui.AWARDS_COUNTERS}}

    def test_compact_summary_preserves_unearned_level_sentinel(self):
        value = self.summary()
        self.assertEqual('PASS', ui.awards_summary(value)['status'])
        self.assertEqual(1, value['nonzero_value_items'])
        self.assertEqual(0, value['done_items'])

    def test_compact_summary_requires_exact_aggregate_counts(self):
        value = self.summary()
        value['packed_items'] += 1
        with self.assertRaisesRegex(ValueError, 'aggregate count'):
            ui.awards_summary(value)

    def test_fresh_profile_cannot_silently_receive_earned_award(self):
        value = self.summary()
        value['sections'][0]['done_items'] = value['done_items'] = 1
        with self.assertRaisesRegex(ValueError, 'earned/done'):
            ui.awards_summary(value)

    def test_compact_summary_checks_section_bound_and_identity(self):
        value = self.summary()
        value['sections'][0]['index'] = 1
        with self.assertRaisesRegex(ValueError, 'section identity'):
            ui.awards_summary(value)
        value = self.summary()
        value['sections'][0]['catalog_items'] = 257
        with self.assertRaisesRegex(ValueError, 'section bounds'):
            ui.awards_summary(value)


def awards_trace():
    state = {'isActive': True, '_userID': None, '_databaseID': 7, '_userName': 'Player'}
    data = {'achievementsList': [[] for _ in range(7)], 'totalItemsList': [0] * 7, 'battlesCount': 0}
    rows = []
    for i, (source, method, line, call_id, phase, offset) in enumerate((
            (ui.AWARDS, '_sendAccountData', 16, 1, 'call', -1),
            (ui.SECTION_META, 'as_responseDossierS', 55, 2, 'call', -1),
            (ui.SECTION_META, 'as_responseDossierS', 55, 2, 'return', 30),
            (ui.AWARDS, '_sendAccountData', 16, 1, 'return', 266))):
        rows.append(event('native_profile_call', i + 10, source=source, method=method,
                          source_line=line, call_id=call_id, owner_id=100, phase=phase, offset=offset,
                          owner_class='ProfileAwards', owner_state=copy.deepcopy(state), flash_bound=True,
                          type='#profile:profile/dropdown/labels/all', data=copy.deepcopy(data)))
    return rows


class AwardsCallbackTests(unittest.TestCase):
    def test_nested_flash_data_belongs_to_original_awards(self):
        result = ui.awards_evidence(awards_trace(), gui_contracts(), {'native_id': 7, 'name': 'Player'})
        self.assertEqual('PASS', result['status'])
        self.assertEqual(2, result['renders'][0]['response_call_id'])

    def test_shared_summary_meta_does_not_prove_awards(self):
        rows = awards_trace()[1:3]
        for row in rows:
            row['owner_class'] = 'ProfileSummaryPage'
        self.assertEqual('NOT_RUN', ui.awards_evidence(rows, gui_contracts(), {'native_id': 7, 'name': 'Player'})['status'])

    def test_same_name_with_wrong_native_id_is_rejected(self):
        rows = awards_trace()
        rows[1]['owner_state']['_databaseID'] = 8
        with self.assertRaisesRegex(ValueError, 'different native player'):
            ui.awards_evidence(rows, gui_contracts(), {'native_id': 7, 'name': 'Player'})

    def test_awards_unbound_fallback_cannot_be_called_rendered(self):
        rows = awards_trace()
        rows[2]['offset'] = 34
        contracts = gui_contracts()
        contracts[(ui.SECTION_META, 'as_responseDossierS', 55)].add(34)
        with self.assertRaisesRegex(ValueError, 'render return offset'):
            ui.awards_evidence(rows, contracts, {'native_id': 7, 'name': 'Player'})

    def test_complete_compact_projection_can_cover_omitted_rich_strings(self):
        rows = awards_trace()
        value = AwardsPayloadTests().summary()
        for row in rows[1:3]:
            row['data'] = {'truncated': True}
            row['awards_summary'] = copy.deepcopy(value)
        self.assertEqual('PASS', ui.awards_evidence(rows, gui_contracts(), {'native_id': 7, 'name': 'Player'})['status'])

    def test_compact_data_change_during_callback_is_rejected(self):
        rows = awards_trace()
        for row in rows[1:3]:
            row['awards_summary'] = AwardsPayloadTests().summary()
        rows[2]['awards_summary']['catalog_items'] += 1
        with self.assertRaisesRegex(ValueError, 'projection changed'):
            ui.awards_evidence(rows, gui_contracts(), {'native_id': 7, 'name': 'Player'})


class ScenarioNegativeTests(unittest.TestCase):
    def test_same_receiver_can_reuse_its_actual_original_delivery(self):
        awards = {'renders': [{'owner_id': 9, 'call_id': 12, 'call_seconds': 20,
                               'return_seconds': 21, 'data': {'status': 'PASS'}}]}
        observed = {'owner_id': 9}
        self.assertEqual(([12], 'new_original_callback'), ui.scenario_awards_delivery(awards, observed, 19, 22, []))
        prior = [{'alias': 'profileAwards', 'owner_id': 9, 'awards_call_ids': [12]}]
        self.assertEqual(([12], 'same_original_receiver_cache'), ui.scenario_awards_delivery(awards, observed, 30, 32, prior))
        for owner, previous in ((10, prior), (9, [])):
            with self.assertRaisesRegex(ValueError, 'original data delivery'):
                ui.scenario_awards_delivery(awards, {'owner_id': owner}, 30, 32, previous)

    def test_truncated_payload_cannot_become_success_through_cache(self):
        awards = {'renders': [{'owner_id': 9, 'call_id': 12, 'call_seconds': 20,
                               'return_seconds': 21, 'data': {'status': 'NOT_RUN'}}]}
        prior = [{'alias': 'profileAwards', 'owner_id': 9, 'awards_call_ids': [12]}]
        with self.assertRaisesRegex(ValueError, 'original data delivery'):
            ui.scenario_awards_delivery(awards, {'owner_id': 9}, 30, 32, prior)

    def test_native_windows_path_casing_preserves_hash_and_size_binding(self):
        image = {'path': r'D:\Project\local\Screenshots\profile_001.png', 'sha256': 'a' * 64, 'bytes': 100}
        shot = {**image, 'path': r'd:\project\local\screenshots\profile_001.png'}
        self.assertEqual([image], ui.native_image_match([image], shot))
        for changes in ({'sha256': 'b' * 64}, {'bytes': 99}, {'path': r'd:\other\profile_001.png'}):
            self.assertEqual([], ui.native_image_match([image], {**shot, **changes}))

    def test_native_screenshot_path_cannot_use_parent_traversal(self):
        with self.assertRaisesRegex(ValueError, 'path scope'):
            ui.native_image_match([], {'path': r'D:\Project\local\..\profile_001.png'})

    def test_no_marker_is_not_six_step_gui_acceptance(self):
        self.assertEqual('NOT_RUN', ui.profile_scenario([], [], {'native_id': 7}, {})['status'])

    def test_cancelled_scenario_never_equals_complete(self):
        rows = [event('profile_scenario_cancelled', 20, version=1, step_index=2, database_id=7, scenario_elapsed=20)]
        with self.assertRaisesRegex(ValueError, 'failed/cancelled'):
            ui.profile_scenario(rows, [], {'native_id': 7}, {})

    def test_faked_complete_without_six_actual_steps_is_rejected(self):
        rows = [event('profile_scenario_complete', 20, version=1, step_index=6, database_id=7, scenario_elapsed=20)]
        with self.assertRaisesRegex(ValueError, 'incomplete/duplicate'):
            ui.profile_scenario(rows, [], {'native_id': 7}, {})

    def test_scenario_ready_flag_does_not_replace_native_player_fields(self):
        row = {'observation': {'observed_ready': True, 'alias': 'profileAwards', 'database_id': 8,
                               'waiting_visible': False, 'owner_class': 'ProfileAwards', 'flash_bound': True, 'owner_id': 10}}
        with self.assertRaisesRegex(ValueError, 'view/identity/binding'):
            ui.scenario_observation(row, {'native_id': 7}, ui.PROFILE_STEPS[1])


class VisualBindingTests(unittest.TestCase):
    def make_review(self):
        shot = {'file': 'screenshots/test.png', 'sha256': 'a' * 64}
        return {'schema_version': 1, 'reviewer': 'root_visual_inspection', 'status': 'PASS',
                'trace_sha256': 'b' * 64,
                'tooltip_reviews': [{'call_id': 1, 'screenshot': shot, 'trigger_source': 'root_computer_input',
                                     'findings': {'tooltip_visible': True, 'matches_target': True, 'text_readable': True}}],
                'awards_reviews': [{'call_id': 2, 'screenshot': shot, 'trigger_source': 'original_flash_scenario',
                                    'findings': {'awards_tab_visible': True, 'native_catalog_visible': True, 'player_identity_visible': True}}]}

    def check(self, review, require_human_actions=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'visual-review-ui.json').write_text(json.dumps(review), encoding='utf8')
            return ui.gui_visual_review(path, [{'file': 'screenshots/test.png', 'sha256': 'a' * 64}],
                                        'b' * 64, {'displays': [{'call_id': 1}]}, {'renders': [{'call_id': 2}]},
                                        require_human_actions)

    def test_review_binds_native_call_trace_and_file_hash(self):
        # Header/hash-valid PNG pixels themselves are checked outside this unit.
        self.assertEqual('PASS', self.check(self.make_review())['status'])

    def test_existing_screenshot_without_semantic_review_is_not_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual('NOT_RUN', ui.gui_visual_review(Path(directory), [], 'b' * 64, {}, {})['status'])

    def test_wrong_trace_or_call_or_pixels_is_rejected(self):
        for mutate in (lambda value: value.update(trace_sha256='c' * 64),
                       lambda value: value['tooltip_reviews'][0].update(call_id=99),
                       lambda value: value['awards_reviews'][0]['findings'].update(awards_tab_visible=False),
                       lambda value: value['tooltip_reviews'][0]['screenshot'].update(sha256='c' * 64)):
            review = self.make_review()
            mutate(review)
            with self.assertRaises(ValueError):
                self.check(review)

    def test_current_failure_never_falls_back_to_previous_pass(self):
        report = {'gui': {'status': 'FAIL'}, 'relogin': {'status': 'PASS'}}
        self.assertEqual('FAIL', ui.card_gui(report, 'unread-previous.json', Path('.'))['status'])

    def test_manual_gui_requires_specific_human_attestation(self):
        review = self.make_review()
        with self.assertRaisesRegex(ValueError, 'human action attestation'):
            self.check(review, True)
        review['human_attestation'] = {'source': 'direct_user_message', 'trace_sha256': 'b' * 64,
                                       'statement': 'Synthetic unit statement, not actual human evidence.',
                                       'actions': ['hover_tooltip', 'open_awards', 'return_to_hangar']}
        with self.assertRaisesRegex(ValueError, 'automatic action origin'):
            self.check(review, True)
        for field in ('tooltip_reviews', 'awards_reviews'):
            review[field][0]['trigger_source'] = 'human_attested'
        self.assertEqual('PASS', self.check(review, True)['status'])
        review['human_attestation']['trace_sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'human action attestation'):
            self.check(review, True)


class ObservedProfileTests(unittest.TestCase):
    def input(self):
        expected = {'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
                    'manifest': {'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0}},
                    'vehicle': {'inventory_id': 1}}
        common = {'window_class': 'AppEntry', 'native_connected': True, 'items_cache_synced': True,
                  'waiting_visible': False, 'vehicle_model_loaded': True, 'selected_inventory_id': 1,
                  'resources': expected['resources'], 'statistics': expected['manifest']['statistics']}
        samples = []
        for seconds, name, alias in ((10, 'Hangar', 'hangar'), (22, 'ProfilePage', 'profile'), (30, 'Hangar', 'hangar')):
            samples.append(event('native_hangar', seconds, **common, views={
                'main': {'class_name': 'LobbyView', 'alias': 'lobby', 'flash_bound': True},
                'lobby_sub': {'class_name': name, 'alias': alias, 'flash_bound': True}}))
        samples.append(event('fini_enter', 40))
        awards = {'renders': [{'call_id': 4, 'owner_id': 123, 'call_seconds': 20, 'return_seconds': 21,
                              'data': {'status': 'PASS'}}]}
        return samples, expected, awards

    def test_actual_views_and_original_awards_do_not_need_scripted_six_steps(self):
        rows, expected, awards = self.input()
        report = ui.observed_profile_return(rows, expected, awards)
        self.assertEqual('PASS', report['status'])
        self.assertEqual(4, report['observations'][0]['awards_call_id'])

    def test_human_attestation_alone_cannot_replace_missing_native_view(self):
        rows, expected, awards = self.input()
        rows[1]['views']['lobby_sub']['flash_bound'] = False
        self.assertEqual('NOT_RUN', ui.observed_profile_return(rows, expected, awards)['status'])

    def test_view_after_fini_or_missing_return_does_not_prove_manual_route(self):
        rows, expected, awards = self.input()
        rows[-1], rows[-2] = rows[-2], rows[-1]
        self.assertEqual('NOT_RUN', ui.observed_profile_return(rows, expected, awards)['status'])
        rows, expected, awards = self.input()
        rows.pop(2)
        self.assertEqual('NOT_RUN', ui.observed_profile_return(rows, expected, awards)['status'])

    def test_automatic_navigation_is_not_reclassified_as_manual(self):
        rows, expected, awards = self.input()
        rows.insert(1, event('diagnostic_open_profile', 19, phase='begin'))
        with self.assertRaisesRegex(ValueError, 'automatic Profile transition'):
            ui.observed_profile_return(rows, expected, awards)

    def test_stale_profile_sample_or_changed_resources_cannot_correlate(self):
        rows, expected, awards = self.input()
        rows[1]['elapsed_seconds'] = 25
        self.assertEqual('NOT_RUN', ui.observed_profile_return(rows, expected, awards)['status'])
        rows, expected, awards = self.input()
        rows[1]['resources'] = {**expected['resources'], 'gold': 10}
        self.assertEqual('NOT_RUN', ui.observed_profile_return(rows, expected, awards)['status'])

    def test_truncated_awards_is_not_promoted_by_visible_profile(self):
        rows, expected, awards = self.input()
        awards['renders'][0]['data']['status'] = 'NOT_RUN'
        self.assertEqual('NOT_RUN', ui.observed_profile_return(rows, expected, awards)['status'])


class CatalogDeltaTests(unittest.TestCase):
    def inputs(self):
        before = {b'rev': 1, b'sellPriceFactor': 0.0,
                  b'items': {b'itemPrices': {3329: (0, 0)}, b'notInShopItems': [3329]},
                  b'isEnabledBuyingGoldShellsForCredits': False}
        prices = {6658: (0, 0), 5891: (0, 0), 5892: (0, 0), 3589: (0, 0), 7: (0, 0)}
        after = copy.deepcopy(before)
        after[b'rev'] = 2
        after[b'items'][b'itemPrices'].update(prices)
        after[b'items'][b'notInShopItems'].extend(sorted(prices))
        return before, after, prices

    def test_only_five_installed_unavailable_display_references_change(self):
        before, after, prices = self.inputs()
        saved = copy.deepcopy(before)
        ui.catalog_shop_delta(before, after, prices)
        self.assertEqual(saved, before)

    def test_display_catalogue_cannot_enable_purchase_or_change_other_fields(self):
        for change in (lambda after: after[b'items'][b'notInShopItems'].pop(),
                       lambda after: after.update({b'isEnabledBuyingGoldShellsForCredits': True}),
                       lambda after: after[b'items'][b'itemPrices'].update({999: (0, 0)}),
                       lambda after: after.update({b'sellPriceFactor': 1.0})):
            before, after, prices = self.inputs()
            change(after)
            with self.assertRaisesRegex(ValueError, 'beyond five mounted'):
                ui.catalog_shop_delta(before, after, prices)

    def test_unmeasured_revision_or_invented_price_is_rejected(self):
        before, after, prices = self.inputs()
        after[b'rev'] = 3
        with self.assertRaisesRegex(ValueError, 'revision1 to2'):
            ui.catalog_shop_delta(before, after, prices)
        before, after, prices = self.inputs()
        before[b'rev'] = True
        with self.assertRaisesRegex(ValueError, 'revision1 to2'):
            ui.catalog_shop_delta(before, after, prices)
        before, after, prices = self.inputs()
        prices[7] = (100, 0)
        with self.assertRaisesRegex(ValueError, 'unmeasured mounted'):
            ui.catalog_shop_delta(before, after, prices)


class PairedSessionTests(unittest.TestCase):
    """Synthetic report-parser controls only; never native compatibility proof."""
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        install = self.root / 'before'
        install.mkdir()
        (install / 'wire').mkdir()
        plan, capture, trace = b'{}\n', b'{"unit":"capture"}\n', b'{"unit":"trace"}\n'
        (install / 'install-plan.json').write_bytes(plan)
        (install / 'wire/capture.json').write_bytes(capture)
        tracepath = install / 'trace.jsonl'
        tracepath.write_bytes(trace)
        sources = [{'source': 'client_patch/' + name + '.py', 'source_sha256': 'a' * 64,
                    'pyc_sha256': 'b' * 64, 'installed_file': 'scripts/' + name + '.pyc'} for name in ui.SOURCE_NAMES]
        self.previous = {'schema_version': ui.SCHEMA, 'tool': ui.TOOL, 'install': str(install),
                         'status': 'NOT_RUN', 'session_status': 'PASS', 'gui': {'status': 'NOT_RUN'},
                         'checks': {'installation_plan': {'status': 'PASS', 'sha256': ui.digest(plan)}},
                         'wire': {'status': 'PASS', 'capture_sha256': ui.digest(capture)},
                         'backend': {'status': 'PASS', 'session_id': 1},
                         'native_common': {'status': 'PASS', 'trace': {'path': str(tracepath), 'sha256': ui.digest(trace)},
                                           'checks': {'compiled_sources': {'status': 'PASS', 'sources': sources}}},
                         'native_hangar': {'status': 'PASS'}, 'visual': {'status': 'PASS'},
                         'identity_snapshot': {'account_id': 'synthetic-unit-account', 'native_database_id': 7, 'resources': 100000},
                         'process': {'started_utc': '2026-10-04T00:00:00+00:00', 'finished_utc': '2026-10-04T00:02:00+00:00',
                                     'gateway_run': 'synthetic-unit-run'}}
        self.current = copy.deepcopy(self.previous)
        self.current.update(install=str(self.root / 'after'), gui={'status': 'PASS'})
        self.current['wire']['capture_sha256'] = 'c' * 64
        self.current['backend']['session_id'] = 2
        self.current['process'].update(started_utc='2026-10-04T00:03:00+00:00', finished_utc='2026-10-04T00:05:00+00:00')
        self.previous_path = self.root / 'previous-report.json'

    def run_pair(self):
        self.previous_path.write_text(json.dumps(self.previous), encoding='utf8')
        answer = ui.relogin(self.previous_path, self.current, self.root)
        self.current['relogin'] = answer
        return answer

    def test_previous_clean_session_with_gui_not_run_supports_current_complete_gui(self):
        report = self.run_pair()
        self.assertEqual('PASS', report['status'])
        self.assertEqual('NOT_RUN', report['previous_gui_status'])
        self.assertEqual('PASS', ui.card_gui(self.current, self.previous_path, self.root)['status'])

    def test_two_incomplete_guis_do_not_become_complete_through_relogin(self):
        self.current['gui']['status'] = 'NOT_RUN'
        self.assertEqual('PASS', self.run_pair()['status'])
        self.assertEqual('NOT_RUN', ui.card_gui(self.current, self.previous_path, self.root)['status'])

    def test_previous_review_not_run_or_errors_block_clean_session_claim(self):
        for component, status in (('visual', 'NOT_RUN'), ('native_common', 'FAIL')):
            original = self.previous[component]['status']
            self.previous[component]['status'] = status
            with self.assertRaisesRegex(ValueError, 'two complete clean sessions'):
                self.run_pair()
            self.previous[component]['status'] = original

    def test_source_or_compiled_bytecode_change_rejects_paired_run(self):
        row = self.current['native_common']['checks']['compiled_sources']['sources'][0]
        for key in ('source_sha256', 'pyc_sha256'):
            original = row[key]
            row[key] = 'e' * 64
            with self.assertRaisesRegex(ValueError, 'compiled source or bytecode'):
                self.run_pair()
            row[key] = original

    def test_changed_identity_or_snapshot_cannot_be_persisted_account(self):
        self.current['identity_snapshot']['resources'] = 999999
        with self.assertRaisesRegex(ValueError, 'identity or server profile changed'):
            self.run_pair()

    def test_same_live_session_cannot_be_relogin(self):
        self.current['backend']['session_id'] = 1
        with self.assertRaisesRegex(ValueError, 'same live gateway session'):
            self.run_pair()

    def test_current_gui_failure_is_not_hidden_by_successful_pair(self):
        self.current['gui']['status'] = 'FAIL'
        self.assertEqual('PASS', self.run_pair()['status'])
        self.assertEqual('FAIL', ui.card_gui(self.current, self.previous_path, self.root)['status'])


OLD = ROOT / 'local/evidence/20261004-p02-unified-account'
NORMAL20 = OLD / 'gui-agent/normal20-prepare/normal-idle/native-trace.jsonl'
EMAIL22 = OLD / 'wire-agent/verify-email22-final-observer-01/unified-entry-verification.json'


class HistoricalNegativeControls(unittest.TestCase):
    @unittest.skipUnless(NORMAL20.exists(), 'NOT_RUN: local original Normal20 trace absent')
    def test_real_normal20_errors_are_not_reclassified_by_manual_auth(self):
        raw = NORMAL20.read_bytes()
        self.assertEqual('89b60593fb1769d1907ff06161ad1c7fa2812201d4f194f442065943e65a7476', ui.digest(raw))
        rows = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual(8, len(ui.native_error_events(rows)))
        self.assertFalse(any(row['event'] == 'fini' for row in rows))

    @unittest.skipUnless(EMAIL22.exists(), 'NOT_RUN: local original Email22 report absent')
    def test_real_email22_late_tooltip_remains_failure(self):
        raw = EMAIL22.read_bytes()
        self.assertEqual('55d428c5fbffe6669e58cf7c9526cbef75a8a4da1d2a7e930b5866fae1c2ff66', ui.digest(raw))
        old = json.loads(raw)
        trace = Path(old['native_common']['trace']['path']).read_bytes()
        self.assertEqual(old['native_common']['trace']['sha256'], ui.digest(trace))
        rows = [json.loads(line) for line in trace.splitlines()]
        outcome = json.loads((OLD / 'gui-agent/email22-final-observer-prepare/native-outcome.json').read_bytes())
        report = ui.lifecycle(rows, outcome)
        self.assertEqual('FAIL', old['status'])
        self.assertEqual('PASS', report['checks']['engine_cleanup_order']['status'])
        self.assertEqual('FAIL', report['checks']['no_trace_errors_during_or_after_fini']['status'])


if __name__ == '__main__':
    unittest.main()
