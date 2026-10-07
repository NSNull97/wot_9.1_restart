# -*- coding: utf-8 -*-
"""Bounded sequencing/rejection tests; synthetic boundaries are not native proof."""
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import hangar_relogin_scenario as S
import ms1_crew_scenario as Crew

EMAIL = u'fixture@example.invalid'
PASSWORD = u'  FixtureOnly_\u041f\u0430\u0440\u043e\u043b\u044c  '


def unit_snapshot():
    """Synthetic envelope, with measured original compact bytes for validation."""
    compacts = ('080d0164000000010001000100410600000000420000000000',
                '080d0364000000020002000200410600000000420000000000')
    return {
        'version': 1, 'ready': True, 'issues': [], 'selected_ms1': True,
        'selected_inventory_id': 1, 'tankmen_count': 2, 'ms1_assigned_ids': [1, 2],
        'is7_assigned_count': 0, 'inventory_mutation_requested': False,
        'selection_changed_by_observer': False, 'database_id': 1,
        'tankmen': [{'inventory_id': i + 1, 'vehicle_inventory_id': 1,
                     'vehicle_slot_index': i, 'is_in_tank': True,
                     'original_parse_repack_equal': True, 'compact_descr_hex': compacts[i],
                     'compact_descr_sha256': Crew.EXPECTED_COMPACTS[i]} for i in range(2)],
        'vehicles': [{'inventory_id': i + 1, 'type_compact_descr': (3329, 7169)[i],
                      'crew': [{'slot_index': j, 'tankman_inventory_id': j + 1 if i == 0 else None,
                                'tankman_compact_descr_sha256': Crew.EXPECTED_COMPACTS[j] if i == 0 else None}
                               for j in range((2, 5)[i])]} for i in range(2)],
    }


class FakeNative(object):
    """Unit-only boundary; no networking, engine imports, files or user input."""
    def __init__(self):
        self.state = {'database_id': 1, 'resources': [100000, 0, 0],
                      'statistics': [0, 0, 0, 0], 'selected_inventory_id': 2,
                      'hangar_owner': 10, 'crew_owner': 11}
        self.actions, self.requests, self.snapshots = [], [], []
        self.crew_value, self.observations = unit_snapshot(), 0
        self.auto_files, self.submit_error, self.logoff_error = True, False, False
        self.result_status = 'LOGGED_ON'
        self.login = {'native_connected': False, 'exact_disconnected': True,
                      'repository_absent': True, 'player_absent': True,
                      'login_ready': True, 'class_name': 'LoginView', 'alias': 'login',
                      'flash_bound': True, 'owner_id': 20}
        self.submitted = None

    def context(self):
        return copy.deepcopy(self.state)

    def select_ms1(self):
        self.actions.append('select_ms1')
        self.state['selected_inventory_id'] = 1

    def observe(self, record):
        self.observations += 1
        value = copy.deepcopy(self.crew_value)
        value['observation_index'] = self.observations
        self.snapshots.append(value)
        return value

    def request(self, basename):
        if basename in self.requests:
            raise ValueError('unit duplicate request')
        self.requests.append(basename)

    def screenshot(self, basename):
        if not self.auto_files:
            return None
        if basename not in self.requests:
            raise ValueError('unit request absent')
        return {'basename': basename, 'png_container_valid': True, 'native_pixels_review': 'NOT_RUN'}

    def logoff(self):
        self.actions.append('logoff')
        if self.logoff_error:
            raise RuntimeError('unit original logoff failure')

    def login_state(self):
        return copy.deepcopy(self.login)

    def submit(self, username, password):
        if S._credentials is not None:
            raise AssertionError('credentials retained while submitting')
        self.actions.append('login')
        self.submitted = (username, password)
        if self.submit_error:
            raise RuntimeError('unit original submit failure')
        if self.result_status is not None:
            S.note_login_result(1, self.result_status)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        S._scenario, S._armed, S._credentials = None, False, None
        S.arm(EMAIL, PASSWORD)
        self.native, self.events, self.now = FakeNative(), [], 0.0
        self.scenario = S._Scenario({}, self.record, self.native, lambda: self.now)
        S._scenario = self.scenario

    def tearDown(self):
        S.clear_credentials()
        S._scenario, S._armed = None, False

    def record(self, event, **fields):
        self.events.append((event, fields))

    def observed(self):
        selected = self.native.state['selected_inventory_id']
        return {'selected_inventory_id': selected, 'vehicle_model_loaded': True,
                'vehicle': {'type_compact_descr': 3329 if selected == 1 else 7169}}

    def tick(self, ready=True, at=None, observed=None, public=False):
        self.now = self.now + 1.0 if at is None else at
        observed = self.observed() if observed is None else observed
        if public:
            S._scenario = self.scenario
            return S.advance(self.record, {}, observed, ready)
        return self.scenario.advance(observed, ready)

    def reach(self, phase, session=1):
        for _ in range(100):
            if self.scenario.phase == phase and self.scenario.session_index == session:
                return
            self.assertFalse(self.tick())
        self.fail('unit phase not reached')

    def complete(self):
        for _ in range(100):
            if self.tick():
                return
        self.fail('unit sequence did not complete')

    def test_exact_two_legs_crew_png_and_same_owner_addresses_are_valid(self):
        self.complete()
        self.assertEqual(self.native.actions, ['select_ms1', 'logoff', 'login'])
        self.assertEqual(self.native.requests, list(S.SCREENSHOTS))
        self.assertEqual(self.native.observations, 2)
        self.assertEqual(len(set(S.checked_snapshot(x) for x in self.native.snapshots)), 1)
        self.assertEqual([x['session_index'] for x in self.scenario.intervals], [1, 2])
        self.assertTrue(all(x['seconds'] >= 16.0 and x['samples'] >= 17 for x in self.scenario.intervals))
        self.assertIsNone(S._credentials)
        self.assertTrue(self.tick())
        self.assertEqual(len([e for e, _ in self.events if e == 'relogin_scenario_complete']), 1)

    def test_new_gui_owner_addresses_are_also_valid(self):
        self.reach('waiting_hangar', 2)
        self.native.state['hangar_owner'], self.native.state['crew_owner'] = 90, 91
        self.complete()

    def test_exact_unicode_and_edge_whitespace_password_preserved(self):
        self.complete()
        self.assertEqual(self.native.submitted, (EMAIL, PASSWORD))
        log = json.dumps(self.events, ensure_ascii=True)
        self.assertNotIn('FixtureOnly', log)
        self.assertNotIn('fixture@example.invalid', log)
        self.assertNotIn(hashlib.sha256(PASSWORD.encode('utf8')).hexdigest(), log)

    def test_no_action_before_actual_hangar_ready(self):
        for _ in range(20):
            self.assertFalse(self.tick(ready=False))
        self.assertEqual(self.native.actions, [])
        self.assertEqual(self.native.requests, [])

    def test_fifteen_seconds_marker_does_not_finish_hold(self):
        self.reach('stable_hangar')
        self.tick()
        for _ in range(15):
            self.tick()
        self.assertEqual(self.native.requests, [])
        self.tick()
        self.assertEqual(self.native.requests, ['relogin_first'])

    def test_not_ready_resets_continuous_interval(self):
        self.reach('stable_hangar')
        for _ in range(12): self.tick()
        self.tick(ready=False)
        for _ in range(16): self.tick()
        self.assertEqual(self.native.requests, [])
        self.tick()
        self.assertEqual(self.native.requests, ['relogin_first'])
        self.assertTrue(any(e == 'relogin_scenario_interval_reset' and x['reason'] == 'not_ready'
                            for e, x in self.events))

    def test_sample_gap_resets_instead_of_accumulating_missing_time(self):
        self.reach('stable_hangar')
        self.tick()
        self.tick(at=self.now + 3.0)
        self.assertEqual(self.scenario.ready_samples, 1)
        self.assertEqual(self.native.requests, [])
        self.assertTrue(any(e == 'relogin_scenario_interval_reset' and x['reason'] == 'sample_gap'
                            for e, x in self.events))

    def test_boundary_gap_2_5_is_accepted(self):
        self.reach('stable_hangar')
        self.tick()
        self.tick(at=self.now + 2.5)
        self.assertEqual(self.scenario.ready_samples, 2)
        self.assertEqual(self.scenario.max_gap, 2.5)

    def test_wrong_vehicle_and_unloaded_model_do_not_count(self):
        self.reach('stable_hangar')
        self.tick(observed={'selected_inventory_id': 1, 'vehicle_model_loaded': False,
                            'vehicle': {'type_compact_descr': 3329}})
        self.assertIsNone(self.scenario.ready_since)
        self.tick(observed={'selected_inventory_id': 1, 'vehicle_model_loaded': True,
                            'vehicle': {'type_compact_descr': 7169}})
        self.assertIsNone(self.scenario.ready_since)

    def test_bool_inventory_id_is_not_native_integer(self):
        self.reach('stable_hangar')
        value = self.observed()
        value['selected_inventory_id'] = True
        self.tick(observed=value)
        self.assertIsNone(self.scenario.ready_since)

    def test_first_png_missing_never_logs_off(self):
        self.native.auto_files = False
        self.reach('waiting_png')
        for _ in range(10): self.tick()
        self.assertNotIn('logoff', self.native.actions)
        self.assertIsNotNone(S._credentials)

    def test_second_png_missing_never_completes(self):
        self.reach('stable_hangar', 2)
        self.native.auto_files = False
        self.reach('waiting_png', 2)
        for _ in range(10): self.assertFalse(self.tick())
        self.assertFalse(self.scenario.completed)

    def test_loss_of_readiness_during_capture_fails(self):
        self.reach('waiting_png')
        with self.assertRaises(RuntimeError): self.tick(ready=False, public=True)
        self.assertIsNone(S._credentials)

    def test_logoff_return_explicitly_does_not_prove_disconnect(self):
        self.reach('waiting_disconnect')
        rows = [x for e, x in self.events if e == 'relogin_scenario_action'
                and x['action'] == 'logoff' and x['moment'] == 'return']
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]['actual_disconnect_proven'], False)
        self.assertNotIn('login', self.native.actions)

    def test_transition_is_not_disconnected_and_cannot_submit(self):
        self.reach('waiting_disconnect')
        self.native.login['exact_disconnected'] = False
        for _ in range(5): self.tick(ready=False)
        self.assertNotIn('login', self.native.actions)
        self.assertIsNotNone(S._credentials)

    def test_retained_repository_prevents_second_submit(self):
        self.reach('waiting_disconnect')
        self.native.login['repository_absent'] = False
        self.tick(ready=False)
        self.assertNotIn('login', self.native.actions)

    def test_retained_player_prevents_second_submit(self):
        self.reach('waiting_disconnect')
        self.native.login['player_absent'] = False
        self.tick(ready=False)
        self.assertNotIn('login', self.native.actions)

    def test_login_view_not_flash_bound_prevents_second_submit(self):
        self.reach('waiting_disconnect')
        self.native.login.update(flash_bound=False, login_ready=False)
        self.tick(ready=False)
        self.assertNotIn('login', self.native.actions)

    def test_contradictory_login_state_is_error(self):
        self.reach('waiting_disconnect')
        self.native.login['native_connected'] = True
        with self.assertRaises(ValueError): self.tick(public=True)
        self.assertIsNone(S._credentials)

    def test_original_submit_error_clears_inputs_and_never_retries(self):
        self.reach('waiting_disconnect')
        self.native.submit_error = True
        with self.assertRaises(RuntimeError): self.tick(public=True)
        self.assertIsNone(S._credentials)
        with self.assertRaises(RuntimeError): self.tick(public=True)
        self.assertEqual(self.native.actions.count('login'), 1)

    def test_original_logoff_error_clears_inputs(self):
        self.reach('waiting_png')
        self.native.logoff_error = True
        with self.assertRaises(RuntimeError): self.tick(public=True)
        self.assertIsNone(S._credentials)
        self.assertNotIn('login', self.native.actions)

    def test_second_account_identity_change_fails(self):
        self.reach('waiting_hangar', 2)
        self.native.state['database_id'] = 2
        with self.assertRaises(RuntimeError): self.tick(public=True)

    def test_resource_mutation_fails(self):
        self.reach('stable_hangar')
        self.native.state['resources'][0] += 1
        with self.assertRaises(RuntimeError): self.tick(public=True)

    def test_statistic_mutation_fails(self):
        self.reach('waiting_hangar', 2)
        self.native.state['statistics'][0] = 1
        with self.assertRaises(RuntimeError): self.tick(public=True)

    def test_actual_crew_fingerprint_change_fails(self):
        self.reach('stable_hangar', 2)
        self.native.crew_value['tankmen'][0]['first_user_name'] = 'changed'
        with self.assertRaises(RuntimeError):
            for _ in range(20): self.tick(public=True)

    def test_altered_vehicle_or_compact_rejected(self):
        self.reach('stable_hangar')
        self.native.crew_value['vehicles'][1]['type_compact_descr'] = 999
        with self.assertRaises(ValueError):
            for _ in range(20): self.tick(public=True)

    def test_selected_vehicle_is_rechecked_for_leg_two(self):
        self.reach('waiting_hangar', 2)
        self.native.state['selected_inventory_id'] = 2
        self.complete()
        self.assertEqual(self.native.actions.count('select_ms1'), 2)

    def test_clock_rollback_nan_infinity_rejected(self):
        self.tick()
        for bad in (-1.0, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError): self.tick(at=bad)

    def test_observation_budget_is_failure_not_completion(self):
        self.scenario.advances = S.MAX_ADVANCES
        with self.assertRaises(RuntimeError): self.tick(public=True)
        self.assertFalse(self.scenario.completed)
        self.assertIsNone(S._credentials)

    def test_credential_clear_before_second_submit(self):
        self.reach('waiting_disconnect')
        self.assertIsNotNone(S._credentials)
        self.tick(ready=False)
        self.assertIsNone(S._credentials)
        self.assertEqual(self.native.submitted, (EMAIL, PASSWORD))

    def test_clear_credentials_cancels_pending_second_submit(self):
        self.reach('waiting_disconnect')
        S.clear_credentials()
        with self.assertRaises(RuntimeError): self.tick(public=True)
        self.assertNotIn('login', self.native.actions)

    def test_first_success_and_unexpected_first_rejection_are_not_second_result(self):
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))
        self.assertFalse(S.note_login_result(1, 'LOGIN_REJECTED_SERVER_NOT_READY'))
        self.assertIsNone(self.scenario.pending_login_result)
        self.assertFalse(self.scenario.second_login_accepted)
        self.complete()
        result = [x for event, x in self.events if event == 'relogin_scenario_login_result']
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['session_index'], 2)
        self.assertEqual(result[0]['status'], 'LOGGED_ON')

    def test_expected_logoff_stage_six_cannot_become_failed_login(self):
        self.reach('waiting_disconnect')
        self.assertFalse(S.note_login_result(6, 'NOT_SET'))
        self.assertFalse(S.note_login_result(1, 'LOGIN_REJECTED_SERVER_NOT_READY'))
        self.assertIsNone(self.scenario.pending_login_result)
        self.complete()

    def test_second_rejection_is_passive_then_fails_on_next_advance(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        before = len(self.events)
        self.assertTrue(S.note_login_result(1, 'LOGIN_REJECTED_SERVER_NOT_READY'))
        self.assertEqual(len(self.events), before)
        self.assertEqual(self.scenario.phase, 'waiting_hangar')
        self.assertIsNone(S._credentials)
        with self.assertRaises(S.SecondLoginRejected): self.tick(ready=False, public=True)
        self.assertEqual(self.scenario.phase, 'error')
        rows = [x for event, x in self.events if event == 'relogin_scenario_login_result']
        self.assertEqual(rows[-1]['status'], 'LOGIN_REJECTED_SERVER_NOT_READY')
        self.assertIs(rows[-1]['handled_outside_callback'], True)
        self.assertFalse(self.scenario.completed)
        self.assertEqual(self.native.actions.count('login'), 1)
        self.assertFalse(any(event == 'relogin_scenario_complete' for event, _ in self.events))
        error = [x for event, x in self.events if event == 'relogin_scenario_error'][-1]
        self.assertEqual(error['error_type'], 'SecondLoginRejected')
        self.assertIs(error['credential_references_cleared'], True)

    def test_synchronous_original_reject_callback_never_raises_from_submit(self):
        self.native.result_status = 'LOGIN_REJECTED_INVALID_PASSWORD'
        self.reach('waiting_disconnect')
        self.assertFalse(self.tick(ready=False))
        self.assertEqual(self.scenario.phase, 'waiting_hangar')
        self.assertEqual(self.native.actions[-1], 'login')
        with self.assertRaises(S.SecondLoginRejected): self.tick(public=True)

    def test_stage_one_success_is_required_but_cannot_prove_hangar(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        self.assertFalse(self.tick())
        self.assertEqual(self.scenario.phase, 'waiting_hangar')
        self.assertTrue(S.note_login_result(1, 'LOGGED_ON'))
        self.assertFalse(self.tick(ready=False))
        self.assertTrue(self.scenario.second_login_accepted)
        self.assertFalse(self.scenario.completed)
        self.assertEqual(len(self.native.requests), 1)
        self.complete()

    def test_duplicate_or_late_callback_cannot_overwrite_first_outcome(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        self.assertTrue(S.note_login_result(1, 'LOGIN_REJECTED_SERVER_NOT_READY'))
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))
        with self.assertRaises(S.SecondLoginRejected): self.tick(public=True)
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))
        self.assertFalse(S.note_login_result(1, 'LOGIN_REJECTED_INVALID_PASSWORD'))

    def test_rejection_after_accepted_second_result_is_unexpected_not_reassigned(self):
        self.reach('stable_hangar', 2)
        self.assertTrue(self.scenario.second_login_accepted)
        self.assertFalse(S.note_login_result(1, 'LOGIN_REJECTED_SERVER_NOT_READY'))
        self.assertIsNone(self.scenario.pending_login_result)

    def test_malformed_callback_values_never_raise_or_enter_record(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        values = [(True, 'LOGGED_ON'), (1.0, 'LOGGED_ON'), (6, 'NOT_SET'), (1, ''),
                  (1, 'X' * 129), (1, 'status with message'), (1, u'\u041e\u0428\u0418\u0411\u041a\u0410'),
                  (1, object()), (object(), 'LOGGED_ON'), (1, PASSWORD)]
        count = len(self.events)
        for stage, status in values:
            self.assertFalse(S.note_login_result(stage, status))
        self.assertEqual(len(self.events), count)
        self.assertIsNone(self.scenario.pending_login_result)
        self.assertTrue(self.scenario.awaiting_second_login)
        self.assertTrue(S.note_login_result(1, 'LOGGED_ON'))

    def test_callback_status_128_boundary_is_a_bounded_primitive(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        self.assertTrue(S.note_login_result(1, 'X' * 128))
        self.assertEqual(len(self.scenario.pending_login_result['status']), 128)
        with self.assertRaises(S.SecondLoginRejected): self.tick(public=True)


class InputAndContractTests(unittest.TestCase):
    def setUp(self):
        S._scenario, S._armed, S._credentials = None, False, None

    def tearDown(self):
        S.clear_credentials()
        S._scenario, S._armed = None, False

    def test_default_unarmed_has_no_original_actions(self):
        events = []
        with self.assertRaises(RuntimeError):
            S.advance(lambda event, **fields: events.append((event, fields)), {}, {}, False)
        self.assertIsNone(S._credentials)
        self.assertEqual(events[0][0], 'relogin_scenario_error')

    def test_normal_unarmed_callback_has_no_effects(self):
        for stage, status in ((1, 'LOGGED_ON'), (1, 'LOGIN_REJECTED_SERVER_NOT_READY'),
                              (6, 'NOT_SET'), (object(), object())):
            self.assertFalse(S.note_login_result(stage, status))
        self.assertIsNone(S._scenario)
        self.assertIsNone(S._credentials)
        self.assertFalse(S._armed)

    def test_armed_before_first_scenario_does_not_capture_first_outcome(self):
        S.arm(EMAIL, PASSWORD)
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))
        self.assertFalse(S.note_login_result(1, 'LOGIN_REJECTED_SERVER_NOT_READY'))
        self.assertIsNone(S._scenario)

    def test_double_arm_refused_and_clears_first_input(self):
        S.arm(EMAIL, PASSWORD)
        with self.assertRaises(RuntimeError): S.arm(EMAIL, PASSWORD)
        self.assertIsNone(S._credentials)

    def test_arm_invalid_or_oversize_inputs_never_retained(self):
        for user, password in ((u'not-an-email', PASSWORD), (EMAIL, u'short'),
                               (u'x' * 1025, PASSWORD), (EMAIL, u'X' * 1025),
                               (True, PASSWORD), (EMAIL, object())):
            with self.assertRaises(ValueError): S.arm(user, password)
            self.assertIsNone(S._credentials)

    def test_credential_clear_is_idempotent_and_not_rearm(self):
        S.arm(EMAIL, PASSWORD)
        S.clear_credentials()
        S.clear_credentials()
        with self.assertRaises(RuntimeError): S.arm(EMAIL, PASSWORD)

    def test_context_rejects_bool_and_unknown_fields(self):
        value = FakeNative().context()
        value['database_id'] = True
        with self.assertRaises(ValueError): S.checked_context(value)
        value = FakeNative().context()
        value['secret'] = 'untrusted'
        with self.assertRaises(ValueError): S.checked_context(value)

    def test_login_state_rejects_forged_ready_shape(self):
        value = FakeNative().login_state()
        value['class_name'] = 'LobbyView'
        with self.assertRaises(ValueError): S.checked_login_state(value)

    def test_login_state_metadata_length_bounded(self):
        value = FakeNative().login_state()
        value['class_name'] = 'X' * 65
        with self.assertRaises(ValueError): S.checked_login_state(value)

    def test_no_old_gui_references_are_retained(self):
        native = object.__new__(S._Native)
        native.carousel, native.crew, native.endpoint = object(), object(), '127.0.0.1:20014'
        native.release_context()
        native.release_context()
        self.assertNotIn('carousel', native.__dict__)
        self.assertNotIn('crew', native.__dict__)
        self.assertEqual(native.endpoint, '127.0.0.1:20014')

    def test_actual_context_wrapper_releases_refs_even_on_read_failure(self):
        native = object.__new__(S._Native)
        previous = Crew._Native.context
        def failed_read(owner):
            owner.carousel, owner.crew = object(), object()
            raise RuntimeError('unit original observation failure')
        Crew._Native.context = failed_read
        try:
            with self.assertRaises(RuntimeError): native.context()
            self.assertNotIn('carousel', native.__dict__)
            self.assertNotIn('crew', native.__dict__)
        finally:
            Crew._Native.context = previous

    def test_selection_refetches_current_context_and_releases_after_failure(self):
        native = object.__new__(S._Native)
        first, second, calls = object(), object(), []
        previous_context, previous_select = Crew._Native.context, Crew._Native.select_ms1
        def fresh_read(owner):
            owner.carousel, owner.crew = first, second
            calls.append('fresh_context')
        def select(owner):
            self.assertIs(owner.carousel, first)
            self.assertIs(owner.crew, second)
            calls.append('original_selection')
            raise RuntimeError('unit original selection failure')
        Crew._Native.context, Crew._Native.select_ms1 = fresh_read, select
        try:
            with self.assertRaises(RuntimeError): native.select_ms1()
            self.assertEqual(calls, ['fresh_context', 'original_selection'])
            self.assertNotIn('carousel', native.__dict__)
            self.assertNotIn('crew', native.__dict__)
        finally:
            Crew._Native.context, Crew._Native.select_ms1 = previous_context, previous_select

    def test_successful_context_returns_only_primitives_not_native_owners(self):
        native = object.__new__(S._Native)
        previous = Crew._Native.context
        expected = FakeNative().context()
        def read(owner):
            owner.carousel, owner.crew = object(), object()
            return copy.deepcopy(expected)
        Crew._Native.context = read
        try:
            self.assertEqual(native.context(), expected)
            self.assertNotIn('carousel', native.__dict__)
            self.assertNotIn('crew', native.__dict__)
        finally:
            Crew._Native.context = previous

    def test_unaudited_function_cannot_be_invoked(self):
        def wrong(*args): raise AssertionError('must never execute')
        for contract in S.AUDIT:
            with self.assertRaises(RuntimeError): S.audit_function(wrong, contract)

    def test_second_snapshot_parser_uses_complete_native_corpus_when_available(self):
        path = os.path.join(ROOT, 'local/evidence/20261005-p02-ms1-crew/crew02-runtime')
        if not os.path.isdir(path):
            self.skipTest('historical native corpus not installed')
        files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.jsonl')]
        self.assertEqual(len(files), 1)
        values = []
        with open(files[0], 'rb') as stream:
            for raw in stream:
                row = json.loads(raw.decode('utf8'))
                if row.get('event') == 'ms1_crew_observation':
                    for key in ('event', 'elapsed'):
                        row.pop(key, None)
                    values.append(row)
        if not values:
            self.skipTest('historical event name differs; not synthetic native proof')
        self.assertTrue(all(S.checked_snapshot(row) for row in values))

    @unittest.skipIf(sys.version_info[0] < 3, 'bounded original static decoder requires Python 3')
    def test_original_static_contracts_match_actual_readonly_client(self):
        config = os.path.join(ROOT, 'config/project.local.json')
        if not os.path.isfile(config):
            self.skipTest('local original client path not configured')
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        from py27_static import parse_pyc, records, text
        with open(config, 'rb') as stream:
            base = os.path.join(json.load(stream)['paths']['original_client_root'], 'res')
        for contract, expected in S.AUDIT.items():
            if contract == 'project_submit': continue
            filename, line, argc, variables, freevars, flags, sha = expected
            with open(os.path.join(base, filename + 'c'), 'rb') as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            rows = [code for _, code in records(parse_pyc(raw))
                    if code['firstlineno'] == line and text(code['filename']) == filename]
            self.assertEqual(len(rows), 1, contract)
            row = rows[0]
            self.assertEqual((row['argcount'], tuple(text(row['varnames'])),
                              tuple(text(row['freevars'])), row['flags'],
                              hashlib.sha256(row['code']).hexdigest()),
                             (argc, variables, freevars, flags, sha), contract)

    @unittest.skipUnless(sys.version_info[:2] == (2, 7), 'project bytecode must use Python 2.7')
    def test_project_input_boundary_compile_only_matches_pin(self):
        import types
        with open(os.path.join(ROOT, 'client_patch/project_auth.py'), 'rb') as stream:
            code = compile(stream.read(), 'project_auth.py', 'exec')
        pending, matches = [code], []
        while pending:
            node = pending.pop()
            if node.co_name == 'submit': matches.append(node)
            pending.extend(x for x in node.co_consts if isinstance(x, types.CodeType))
        self.assertEqual(len(matches), 1)
        node = matches[0]
        self.assertEqual((node.co_filename, node.co_firstlineno, node.co_argcount,
                          node.co_varnames, node.co_freevars, node.co_flags,
                          hashlib.sha256(node.co_code).hexdigest()), S.AUDIT['project_submit'])


if __name__ == '__main__':
    unittest.main()
