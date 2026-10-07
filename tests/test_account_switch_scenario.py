# -*- coding: utf-8 -*-
"""Synthetic sequencing controls and read-only contracts; not native acceptance."""
import copy
import hashlib
import json
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import account_switch_scenario as S
import hangar_relogin_scenario as R

PRIMARY = {'username': u'unit-primary@example.invalid', 'password': u'  UnitOnly_Primary_\u041f\u0430\u0440\u043e\u043b\u044c  '}
ALTERNATE = {'username': u'unit-alternate@example.invalid', 'password': u' UnitOnly_Alternate_\u0401  '}


def expected():
    """Deliberately synthetic account state; never described as a client run."""
    first = {'database_id': 1, 'name': u'UnitPrimary',
             'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
             'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0},
             'account_dossier_sha256': 'a' * 64,
             'vehicles': [{'inventory_id': 1, 'type_compact_descr': 3329,
                           'compact_descr_sha256': 'b' * 64, 'health': 90, 'crew_ids': [1, 2]},
                          {'inventory_id': 2, 'type_compact_descr': 7169,
                           'compact_descr_sha256': 'c' * 64, 'health': 2150, 'crew_ids': [None] * 5}],
             'tankmen': [{'inventory_id': i + 1, 'compact_descr_sha256': ('d', 'e')[i] * 64,
                          'vehicle_inventory_id': 1, 'vehicle_slot_index': i} for i in range(2)]}
    second = copy.deepcopy(first)
    second.update(database_id=2, name=u'\u0412\u0442\u043e\u0440\u043e\u0439', account_dossier_sha256='f' * 64, tankmen=[])
    second['vehicles'] = [copy.deepcopy(first['vehicles'][0])]
    second['vehicles'][0]['crew_ids'] = [None, None]
    return [first, second]


class FakeNative(object):
    """Unit boundary only: no engine, files, network, credentials log or input."""
    def __init__(self):
        self.accounts, self.index = expected(), 0
        self.selected, self.owner = 2, 10
        self.actions, self.requests = [], []
        self.auto_png, self.submit_error, self.logoff_error = True, False, False
        self.result_status, self.releases = 'LOGGED_ON', 0
        self.login = {'native_connected': False, 'exact_disconnected': True,
                      'repository_absent': True, 'player_absent': True,
                      'login_ready': True, 'class_name': 'LoginView', 'alias': 'login',
                      'flash_bound': True, 'owner_id': 20}
        self.submissions = []

    def state(self):
        return {'account': copy.deepcopy(self.accounts[self.index]), 'selected_inventory_id': self.selected,
                'hangar_owner': self.owner, 'crew_owner': self.owner + 1}

    def select_ms1(self):
        self.actions.append('select_ms1')
        self.selected = 1

    def request(self, basename):
        if basename in self.requests:
            raise ValueError('unit duplicate request')
        self.requests.append(basename)

    def screenshot(self, basename):
        if not self.auto_png:
            return None
        if basename not in self.requests:
            raise ValueError('unit request missing')
        return {'basename': basename, 'png_container_valid': True, 'native_pixels_review': 'NOT_RUN'}

    def logoff(self):
        self.actions.append('logoff')
        if self.logoff_error:
            raise RuntimeError('unit original logoff failure')

    def login_state(self):
        return copy.deepcopy(self.login)

    def submit(self, username, password):
        if (username, password) in S._credentials:
            raise AssertionError('submitted pair still retained in scenario queue')
        self.actions.append('login')
        self.submissions.append((username, password))
        if self.submit_error:
            raise RuntimeError('unit original submit failure')
        self.index = 1 - self.index
        self.selected = 1
        if self.result_status is not None:
            S.note_login_result(1, self.result_status)

    def release_context(self):
        self.releases += 1


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        S._scenario, S._armed, S._credentials, S._expected_accounts = None, False, None, None
        S.arm(PRIMARY, ALTERNATE, expected())
        self.native, self.events, self.now = FakeNative(), [], 0.0
        self.scenario = S._Scenario({}, self.record, self.native, lambda: self.now)
        S._scenario = self.scenario

    def tearDown(self):
        S.clear_credentials()
        S._scenario, S._armed, S._expected_accounts = None, False, None

    def record(self, event, **fields):
        self.events.append((event, fields))

    def observed(self):
        return {'selected_inventory_id': self.native.selected, 'vehicle_model_loaded': True,
                'vehicle': {'type_compact_descr': 3329 if self.native.selected == 1 else 7169}}

    def tick(self, ready=True, at=None, observed=None, public=True):
        self.now = self.now + 1.0 if at is None else at
        observed = self.observed() if observed is None else observed
        if public:
            return S.advance(self.record, {}, observed, ready)
        return self.scenario.advance(observed, ready)

    def reach(self, phase, session=1):
        for _ in range(150):
            if self.scenario.phase == phase and self.scenario.session_index == session:
                return
            self.assertFalse(self.tick())
        self.fail('unit phase not reached')

    def complete(self):
        for _ in range(160):
            if self.tick():
                return
        self.fail('unit switch did not complete')

    def test_three_exact_legs_two_original_actions_and_three_png(self):
        self.complete()
        self.assertEqual(self.native.actions, ['select_ms1', 'logoff', 'login', 'logoff', 'login'])
        self.assertEqual(self.native.requests, list(S.SCREENSHOTS))
        snapshots = [row for event, row in self.events if event == 'account_switch_snapshot']
        self.assertEqual([r['snapshot'] for r in snapshots], [expected()[0], expected()[1], expected()[0]])
        self.assertEqual([r['session_index'] for r in snapshots], [1, 2, 3])
        self.assertEqual(snapshots[0]['fingerprint'], snapshots[2]['fingerprint'])
        self.assertNotEqual(snapshots[0]['fingerprint'], snapshots[1]['fingerprint'])
        self.assertTrue(all(r['seconds'] >= 16 and r['samples'] >= 17 for r in self.scenario.intervals))
        self.assertIsNone(S._credentials)
        self.assertTrue(self.tick())
        self.assertEqual(len([1 for event, _ in self.events if event == 'account_switch_complete']), 1)

    def test_distinct_owner_addresses_and_reused_owner_addresses_both_work(self):
        self.reach('waiting_hangar', 2)
        self.native.owner = 30
        self.reach('waiting_hangar', 3)
        self.native.owner = 10
        self.complete()

    def test_utf8_name_is_observed_without_ascii_assumption(self):
        self.reach('stable_hangar', 2)
        self.native.accounts[1]['name'] = expected()[1]['name'].encode('utf8')
        self.complete()

    def test_credentials_queue_drops_consumed_pair_before_each_original_submit(self):
        self.reach('waiting_hangar', 2)
        self.assertEqual(S._credentials, [(PRIMARY['username'], PRIMARY['password'])])
        self.reach('waiting_hangar', 3)
        self.assertEqual(S._credentials, [])
        self.complete()
        self.assertEqual(self.native.submissions, [(ALTERNATE['username'], ALTERNATE['password']),
                                                  (PRIMARY['username'], PRIMARY['password'])])
        submits = [r for e, r in self.events if e == 'account_switch_action' and r['action'] == 'login' and r['moment'] == 'call']
        self.assertEqual([r['remaining_credential_pairs'] for r in submits], [1, 0])
        self.assertTrue(all(r['submitted_credential_references_cleared'] for r in submits))

    def test_no_credentials_or_secret_derivatives_in_records(self):
        self.complete()
        raw = json.dumps(self.events, ensure_ascii=True)
        for pair in (PRIMARY, ALTERNATE):
            for value in pair.values():
                self.assertNotIn(json.dumps(value, ensure_ascii=True)[1:-1], raw)
                self.assertNotIn(hashlib.sha256(value.encode('utf8')).hexdigest(), raw)

    def test_first_result_is_never_reused_as_second_result(self):
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))
        self.assertFalse(S.note_login_result(1, 'LOGIN_REJECTED_INVALID_PASSWORD'))
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        self.assertFalse(self.tick())
        self.assertEqual(self.scenario.phase, 'waiting_hangar')
        self.assertTrue(S.note_login_result(1, 'LOGGED_ON'))
        self.native.result_status = 'LOGGED_ON'
        self.complete()

    def test_second_success_cannot_supply_third_success(self):
        self.reach('waiting_disconnect', 2)
        self.native.result_status = None
        self.tick(ready=False)
        self.assertEqual(self.scenario.session_index, 3)
        self.assertFalse(self.scenario.login_accepted)
        self.assertFalse(self.tick())
        self.assertEqual(self.scenario.phase, 'waiting_hangar')
        self.assertTrue(S.note_login_result(1, 'LOGGED_ON'))
        self.complete()

    def test_rejection_leg_two_is_passive_then_fail_fast_with_credentials_cleared(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        count = len(self.events)
        self.assertTrue(S.note_login_result(1, 'LOGIN_REJECTED_SERVER_NOT_READY'))
        self.assertEqual(len(self.events), count)
        self.assertIsNotNone(S._credentials)
        with self.assertRaises(S.LoginRejected): self.tick(ready=False)
        self.assertIsNone(S._credentials)
        self.assertEqual(self.scenario.phase, 'error')
        self.assertFalse(self.scenario.completed)
        self.assertEqual(self.native.actions.count('login'), 1)

    def test_rejection_leg_three_does_not_retry_or_complete(self):
        self.reach('waiting_disconnect', 2)
        self.native.result_status = 'LOGIN_REJECTED_INVALID_PASSWORD'
        self.tick(ready=False)  # Synchronous callback never raises out of submit.
        with self.assertRaises(S.LoginRejected): self.tick()
        self.assertIsNone(S._credentials)
        self.assertEqual(self.native.actions.count('login'), 2)
        self.assertFalse(any(e == 'account_switch_complete' for e, _ in self.events))

    def test_duplicate_and_unexpected_callback_do_not_overwrite_outcome(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        self.assertFalse(S.note_login_result(6, 'NOT_SET'))
        self.assertTrue(S.note_login_result(1, 'LOGIN_REJECTED_INVALID_PASSWORD'))
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))
        with self.assertRaises(S.LoginRejected): self.tick()
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))

    def test_malformed_callback_cannot_raise_or_leak_message(self):
        self.native.result_status = None
        self.reach('waiting_hangar', 2)
        for stage, value in ((True, 'LOGGED_ON'), (1.0, 'LOGGED_ON'), (1, ''), (1, 'X' * 129),
                             (1, object()), (object(), 'LOGGED_ON'), (1, PRIMARY['password']),
                             (1, u'\u041e\u0448\u0438\u0431\u043a\u0430'), (1, 'status message')):
            self.assertFalse(S.note_login_result(stage, value))
        self.assertIsNone(self.scenario.pending_login_result)

    def test_unexpected_rejection_after_accept_is_not_reassigned(self):
        self.reach('stable_hangar', 2)
        self.assertFalse(S.note_login_result(1, 'LOGIN_REJECTED_INVALID_PASSWORD'))
        self.complete()

    def test_wait_for_real_disconnected_and_repository_release_each_transition(self):
        self.reach('waiting_disconnect')
        for field in ('exact_disconnected', 'repository_absent', 'player_absent', 'login_ready'):
            old = dict(self.native.login)
            self.native.login[field] = False
            if field == 'login_ready': self.native.login['flash_bound'] = False
            self.assertFalse(self.tick(ready=False))
            self.assertNotIn('login', self.native.actions)
            self.native.login = old
        self.complete()

    def test_original_submit_error_clears_remaining_primary_and_never_retries(self):
        self.reach('waiting_disconnect')
        self.native.submit_error = True
        with self.assertRaises(RuntimeError): self.tick(ready=False)
        self.assertIsNone(S._credentials)
        with self.assertRaises(RuntimeError): self.tick()
        self.assertEqual(self.native.actions.count('login'), 1)

    def test_original_logoff_error_clears_all_credentials(self):
        self.reach('waiting_png')
        self.native.logoff_error = True
        with self.assertRaises(RuntimeError): self.tick()
        self.assertIsNone(S._credentials)
        self.assertNotIn('login', self.native.actions)

    def test_secondary_cannot_keep_primary_fleet_even_with_secondary_id(self):
        self.reach('waiting_hangar', 2)
        self.native.accounts[1]['vehicles'] = copy.deepcopy(self.native.accounts[0]['vehicles'])
        self.native.accounts[1]['tankmen'] = copy.deepcopy(self.native.accounts[0]['tankmen'])
        with self.assertRaises(RuntimeError): self.tick()

    def test_secondary_cannot_keep_primary_dossier_with_same_zero_stats(self):
        self.reach('waiting_hangar', 2)
        self.native.accounts[1]['account_dossier_sha256'] = self.native.accounts[0]['account_dossier_sha256']
        with self.assertRaises(RuntimeError): self.tick()

    def test_secondary_wrong_name_rejected(self):
        self.reach('waiting_hangar', 2)
        self.native.accounts[1]['name'] = self.native.accounts[0]['name']
        with self.assertRaises(RuntimeError): self.tick()

    def test_return_primary_must_restore_both_owned_vehicles_and_crew(self):
        self.reach('waiting_hangar', 3)
        self.native.accounts[0]['vehicles'] = copy.deepcopy(self.native.accounts[1]['vehicles'])
        self.native.accounts[0]['tankmen'] = []
        with self.assertRaises(RuntimeError): self.tick()

    def test_changed_health_resources_and_statistics_fail(self):
        self.reach('stable_hangar')
        original = copy.deepcopy(self.native.accounts[0])
        for mutate in (lambda a: a['vehicles'][0].update(health=89),
                       lambda a: a['resources'].update(credits=99999),
                       lambda a: a['statistics'].update(battles=1)):
            self.native.accounts[0] = copy.deepcopy(original)
            mutate(self.native.accounts[0])
            with self.assertRaises(RuntimeError): self.tick(public=False)

    def test_interval_resets_after_not_ready(self):
        self.reach('stable_hangar')
        for _ in range(10): self.tick()
        self.tick(ready=False)
        self.assertIsNone(self.scenario.ready_since)
        for _ in range(16): self.tick()
        self.assertEqual(self.native.requests, [])
        self.complete()

    def test_sparse_samples_cannot_prove_stable_hangar(self):
        self.reach('stable_hangar')
        for _ in range(10): self.tick(at=self.now + 3.0)
        self.assertEqual(self.native.requests, [])
        self.assertEqual(self.scenario.ready_samples, 1)
        self.complete()

    def test_png_completion_is_required_before_logoff(self):
        self.native.auto_png = False
        self.reach('waiting_png')
        for _ in range(5): self.tick()
        self.assertNotIn('logoff', self.native.actions)
        self.native.auto_png = True
        self.complete()

    def test_lost_model_before_png_fails(self):
        self.reach('waiting_png')
        with self.assertRaises(RuntimeError): self.tick(ready=False)

    def test_selected_ms1_is_refetched_for_return_leg(self):
        self.reach('waiting_hangar', 3)
        self.native.selected = 2
        self.complete()
        self.assertEqual(self.native.actions.count('select_ms1'), 2)

    def test_observation_budget_is_failure_not_completion(self):
        self.scenario.advances = S.MAX_ADVANCES
        with self.assertRaises(RuntimeError): self.tick()
        self.assertIsNone(S._credentials)
        self.assertFalse(self.scenario.completed)

    def test_bad_clock_values_rejected(self):
        self.tick()
        for bad in (float('nan'), float('inf'), -1.0, True):
            with self.assertRaises(ValueError): self.tick(at=bad, public=False)

    def test_external_credential_clear_prevents_any_further_submit(self):
        self.reach('waiting_disconnect')
        S.clear_credentials()
        with self.assertRaises(RuntimeError): self.tick()
        self.assertNotIn('login', self.native.actions)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        S._scenario, S._armed, S._credentials, S._expected_accounts = None, False, None, None

    def tearDown(self):
        S.clear_credentials()
        S._scenario, S._armed, S._expected_accounts = None, False, None

    def test_normal_unarmed_is_fully_passive(self):
        events = []
        self.assertFalse(S.advance(lambda *a, **k: events.append((a, k)), {}, {}, False))
        self.assertFalse(S.note_login_result(1, 'LOGGED_ON'))
        self.assertEqual(events, [])
        self.assertIsNone(S._scenario)

    def test_expected_is_detached_copy(self):
        source = expected()
        result = S.checked_expected_accounts(source)
        source[0]['vehicles'][0]['crew_ids'][0] = None
        self.assertEqual(result, expected())

    def test_arm_detaches_public_expected_and_credential_dictionaries(self):
        pairs, source = [dict(PRIMARY), dict(ALTERNATE)], expected()
        S.arm(pairs[0], pairs[1], source)
        pairs[1]['password'] = 'mutated'
        source[0]['resources']['credits'] = 1
        self.assertEqual(S._credentials[0], (ALTERNATE['username'], ALTERNATE['password']))
        self.assertEqual(S._expected_accounts, expected())

    def test_double_arm_refuses_and_clears_queue(self):
        S.arm(PRIMARY, ALTERNATE, expected())
        with self.assertRaises(RuntimeError): S.arm(PRIMARY, ALTERNATE, expected())
        self.assertIsNone(S._credentials)

    def test_same_canonical_login_is_not_account_switch(self):
        alternate = dict(PRIMARY)
        alternate['username'] = u'  UNIT-PRIMARY@EXAMPLE.INVALID  '
        with self.assertRaises(ValueError): S.arm(PRIMARY, alternate, expected())
        self.assertIsNone(S._credentials)

    def test_bad_credentials_not_retained(self):
        for value in ({'username': PRIMARY['username'], 'password': 'short'},
                      {'username': True, 'password': PRIMARY['password']},
                      {'username': 'X' * 1025, 'password': PRIMARY['password']},
                      {'username': PRIMARY['username'], 'password': PRIMARY['password'], 'token': 'extra'}):
            with self.assertRaises(ValueError): S.arm(PRIMARY, value, expected())
            self.assertIsNone(S._credentials)

    def test_same_native_identity_or_name_refused(self):
        for key in ('database_id', 'name'):
            rows = expected()
            rows[1][key] = rows[0][key]
            with self.assertRaises(ValueError): S.checked_expected_accounts(rows)

    def test_boolean_ids_hash_and_wrong_scalar_types_refused(self):
        for key, bad in (('database_id', True), ('name', object()), ('account_dossier_sha256', 'g' * 64)):
            row = expected()[0]
            row[key] = bad
            with self.assertRaises(ValueError): S.checked_snapshot(row)

    def test_extra_nested_secret_or_unknown_keys_refused(self):
        for section in (None, 'resources', 'statistics'):
            row = expected()[0]
            (row if section is None else row[section])['password'] = 'untrusted'
            with self.assertRaises(ValueError): S.checked_snapshot(row)

    def test_missing_dossier_hash_is_not_filled(self):
        row = expected()[0]
        del row['account_dossier_sha256']
        with self.assertRaises(ValueError): S.checked_snapshot(row)

    def test_empty_secondary_is_not_fake_primary_crew(self):
        row = expected()[1]
        self.assertEqual(S.checked_snapshot(row), row)
        row['vehicles'][0]['crew_ids'] = [1, 2]
        with self.assertRaises(ValueError): S.checked_snapshot(row)

    def test_orphan_and_duplicate_assignment_rejected(self):
        for mutate in (lambda r: r['vehicles'][0].update(crew_ids=[1, 1]),
                       lambda r: r['tankmen'][0].update(vehicle_slot_index=1),
                       lambda r: r['tankmen'][0].update(vehicle_inventory_id=3)):
            row = expected()[0]
            mutate(row)
            with self.assertRaises(ValueError): S.checked_snapshot(row)

    def test_duplicate_or_unsorted_inventory_not_canonicalized_silently(self):
        for ids in ((2, 1), (1, 1)):
            row = expected()[0]
            for v, i in zip(row['vehicles'], ids): v['inventory_id'] = i
            with self.assertRaises(ValueError): S.checked_snapshot(row)

    def test_container_and_byte_budgets(self):
        row = expected()[1]
        row['vehicles'] = row['vehicles'] * 9
        with self.assertRaises(ValueError): S.checked_snapshot(row)
        row = expected()[0]
        row['tankmen'] *= 9
        with self.assertRaises(ValueError): S.checked_snapshot(row)
        previous = S.MAX_EXPECTED_BYTES
        S.MAX_EXPECTED_BYTES = 32
        try:
            with self.assertRaises(ValueError): S.checked_expected_accounts(expected())
        finally: S.MAX_EXPECTED_BYTES = previous

    def test_raw_inventory_allows_absent_empty_tankmen_not_absent_vehicles(self):
        self.assertEqual(S._inventory_compacts({}, 16), {})
        with self.assertRaises(ValueError): S._inventory_compacts({}, 8, True)
        with self.assertRaises(ValueError): S._inventory_compacts({'compDescr': {True: b'x'}}, 8)
        with self.assertRaises(ValueError): S._inventory_compacts({'compDescr': {1: b'x' * 4097}}, 8)

    def test_frozen_original_action_bindings_and_png_reader_reused_exactly(self):
        for name in ('logoff', 'login_state', 'submit', 'select_ms1', 'release_context', 'screenshot'):
            def function(value): return getattr(value, 'im_func', getattr(value, '__func__', value))
            self.assertIs(function(getattr(S._Native, name)), function(getattr(R._Native, name)))

    def test_import_does_not_load_engine_or_settings(self):
        self.assertNotIn('BigWorld', sys.modules)
        self.assertNotIn('Settings', sys.modules)

    @unittest.skipIf(sys.version_info[0] < 3, 'bounded historical disassembly requires Python3')
    def test_original_account_dossier_property_and_empty_crew_contract(self):
        cfg = os.path.join(ROOT, 'config/project.local.json')
        if not os.path.isfile(cfg): self.skipTest('local original path absent; NOT_RUN')
        with open(cfg, 'rb') as stream: original = json.load(stream)['paths']['original_client_root']
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        from py27_static import parse_pyc, records, text, inspect, opcode_table
        with open(os.path.join(ROOT, 'local/vendor/cpython-2.7.3/opcode.py'), 'r') as stream:
            table = opcode_table(stream.read())
        specs = (('client/gui/shared/utils/requesters/statsrequesterr.pyc',
                  '85c35d9320332c4ccc282ac17b0786fd08bcd4a9d59275fce0e61d4758a51b34'),
                 ('client/gui/scaleform/daapi/view/lobby/hangar/crew.pyc',
                  '8defb03050f4d903d40e466e11fed0b04c368f8fc0450263316e0b768edba136'),
                 ('client/gui/scaleform/daapi/view/meta/crewmeta.pyc',
                  'e3bbd2ef7ef897c7fb8d9f19f8f82f5c4c55a4ff3efe685fada0ba86aaeee22a'))
        all_rows = []
        for relative, sha in specs:
            with open(os.path.join(original, 'res/scripts', relative), 'rb') as stream: raw = stream.read(1048577)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
            all_rows.extend(inspect(raw, table))
        dossier = next(r for r in all_rows if r['qualified_name'].endswith('.accountDossier'))
        self.assertEqual(dossier['firstlineno'], 258)
        self.assertEqual(dossier['constants'][-2:], ['dossier', ''])
        self.assertEqual(dossier['instructions'][-1]['offset'], 15)
        crew = next(r for r in all_rows if r['qualified_name'].endswith('.Crew.updateTankmen'))
        ops = dict((r['offset'], r) for r in crew['instructions'])
        self.assertIsNone(ops[244]['value'])
        self.assertEqual(ops[247]['value'], 'tankmanID')
        self.assertEqual((ops[404]['opname'], ops[404]['arg']), ('BUILD_LIST', 0))
        self.assertEqual(ops[1066]['opname'], 'RETURN_VALUE')
        meta = next(r for r in all_rows if r['qualified_name'].endswith('.as_tankmenResponseS'))
        self.assertEqual(meta['varnames'], ['self', 'roles', 'tankmen'])
        self.assertEqual(meta['instructions'][-3]['offset'], 30)


if __name__ == '__main__':
    unittest.main()
