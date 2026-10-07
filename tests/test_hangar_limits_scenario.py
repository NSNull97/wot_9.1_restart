# -*- coding: utf-8 -*-
"""Lifecycle rejection controls, not native navigation or render acceptance.

FakeNative below has no client, server or input APIs. Historical native snapshots
are separate read-only parser inputs, never a substitute for a new native run.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
import hangar_limits_scenario as S
import ms1_crew_scenario as crew


def unit_snapshot():
    """Synthetic envelope around already measured crew bytes; unit data only."""
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
                     'compact_descr_sha256': crew.EXPECTED_COMPACTS[i]} for i in range(2)],
        'vehicles': [{'inventory_id': i + 1, 'type_compact_descr': (3329, 7169)[i],
                      'crew': [{'slot_index': j, 'tankman_inventory_id': j + 1 if i == 0 else None,
                                'tankman_compact_descr_sha256': crew.EXPECTED_COMPACTS[j] if i == 0 else None}
                               for j in range((2, 5)[i])]} for i in range(2)],
    }


class FakeNative:
    def __init__(self):
        self.selected, self.page = 2, 'Hangar'
        self.waiting, self.flash_bound, self.enabled = False, True, False
        self.profile_ready_flag = True
        self.subject = {'database_id': 1, 'resources': [100000, 0, 0], 'statistics': [0, 0, 0, 0]}
        self.actions, self.requests, self.snapshots = [], [], []
        self.crew_value, self.observations = unit_snapshot(), 0
        self.auto_files, self.files = True, {}
        self.state_reads = 0

    def views(self):
        return self.page, self.waiting

    def identity(self):
        return copy.deepcopy(self.subject)

    def state(self):
        self.state_reads += 1
        return {'page': self.page, 'alias': 'hangar' if self.page == 'Hangar' else 'profile',
                'flash_bound': self.flash_bound, 'waiting_visible': self.waiting,
                'selected_inventory_id': self.selected, 'fight_button_enabled': self.enabled,
                'tooltip_readback': {'status': 'UNKNOWN', 'error_type': 'UnitBoundary'},
                'fight_owner': 10, 'identity': self.identity()}

    def select(self, identity):
        self.actions.append(('select', identity))
        self.selected = identity

    def open_profile(self):
        self.actions.append(('open_profile',))
        self.page = 'ProfilePage'

    def close_profile(self):
        self.actions.append(('close_profile',))
        self.page = 'Hangar'

    def profile_ready(self):
        return self.page == 'ProfilePage' and self.profile_ready_flag

    def show_tooltip(self):
        self.actions.append(('show_tooltip',))

    def hide_tooltip(self):
        self.actions.append(('hide_tooltip',))

    def deny_battle(self):
        self.actions.append(('deny_battle',))

    def observe(self, record):
        self.observations += 1
        value = copy.deepcopy(self.crew_value)
        value['selected_inventory_id'] = self.selected
        value['selected_ms1'] = self.selected == 1
        value['observation_index'] = self.observations
        self.snapshots.append(value)
        return value

    def request(self, basename):
        if basename in self.requests:
            raise ValueError('unit duplicate screenshot')
        self.requests.append(basename)

    def screenshot(self, basename):
        if basename not in self.requests:
            raise ValueError('unit screenshot was not requested')
        # Stub only for sequencing. Production uses the inherited PNG validator.
        if self.auto_files:
            return {'basename': basename, 'png_container_valid': True, 'native_pixels_review': 'NOT_RUN'}
        return self.files.get(basename)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.native, self.events, self.now = FakeNative(), [], 0.0
        self.scenario = S._Scenario({}, self.record, self.native, lambda: self.now)

    def record(self, name, **fields):
        self.events.append((name, fields))

    def observed(self):
        return {'selected_inventory_id': self.native.selected, 'vehicle_model_loaded': True,
                'vehicle': {'type_compact_descr': 3329 if self.native.selected == 1 else 7169}}

    def tick(self, ready=None, observed=None, at=None):
        self.now = self.now + 1.0 if at is None else at
        if ready is None:
            ready = self.native.page == 'Hangar'
        return self.scenario.advance(self.observed() if observed is None else observed, ready)

    def reach(self, phase, step):
        for _ in range(80):
            if self.scenario.phase == phase and self.scenario.step == step:
                return
            self.assertFalse(self.tick())
        self.fail('unit scenario never reached requested state')

    def complete_events(self):
        return [fields for event, fields in self.events if event == 'limits_scenario_complete']

    def test_exact_navigation_three_snapshots_six_images_and_idempotent_completion(self):
        for _ in range(80):
            if self.tick():
                break
        else:
            self.fail('unit scenario did not complete')
        self.assertEqual(self.native.actions, [('select', 1), ('select', 2), ('open_profile',),
                                              ('close_profile',), ('select', 1), ('show_tooltip',),
                                              ('hide_tooltip',), ('deny_battle',)])
        self.assertEqual(self.native.requests, list(S.SCREENSHOTS))
        self.assertEqual(self.native.observations, 3)
        self.assertEqual(len(set(crew.checked_snapshot(value) for value in self.native.snapshots)), 1)
        self.assertEqual(len(self.complete_events()), 1)
        complete = self.complete_events()[0]
        self.assertEqual((complete['screenshots'], complete['observations']), (6, 3))
        self.assertEqual(complete['human_manual_acceptance'], 'NOT_RUN')
        self.assertEqual(complete['native_pixels_review'], 'NOT_RUN')
        self.assertFalse(complete['automatic_quit'])
        self.assertFalse(complete['computer_input'])
        actions = list(self.native.actions)
        self.assertTrue(self.tick())
        self.assertEqual(self.native.actions, actions)
        self.assertEqual(len(self.complete_events()), 1)

    def test_not_ready_start_does_not_navigate_or_capture(self):
        for _ in range(4):
            self.assertFalse(self.tick(False))
        self.assertEqual(self.native.actions, [])
        self.assertEqual(self.native.requests, [])
        self.assertEqual(self.native.observations, 0)

    def test_boolean_readiness_and_observation_type_required(self):
        for observed, ready in (({}, 1), ([], True), ({}, None)):
            with self.assertRaises(TypeError):
                self.scenario.advance(observed, ready)

    def test_model_and_ready_flags_are_both_required(self):
        self.tick()
        value = self.observed()
        value['vehicle_model_loaded'] = False
        for _ in range(4):
            self.assertFalse(self.tick(True, value))
        for _ in range(4):
            self.assertFalse(self.tick(False))
        self.assertEqual(self.native.requests, [])
        self.assertEqual(self.native.observations, 0)

    def test_old_ms1_model_sample_cannot_prove_is7_readiness(self):
        self.reach('waiting_view', 1)
        self.assertEqual(self.native.selected, 2)
        stale = {'selected_inventory_id': 1, 'vehicle_model_loaded': True,
                 'vehicle': {'type_compact_descr': 3329}}
        for _ in range(5):
            self.assertFalse(self.tick(True, stale))
        self.assertNotIn('limits_is7', self.native.requests)
        self.assertNotIn(('open_profile',), self.native.actions)

    def test_wrong_native_descriptor_sample_cannot_prove_ready_model(self):
        self.tick()
        invalid = self.observed()
        invalid['vehicle']['type_compact_descr'] = 7169
        for _ in range(4):
            self.assertFalse(self.tick(True, invalid))
        self.assertEqual(self.native.requests, [])

    def test_loss_of_stability_restarts_two_second_window(self):
        self.tick(at=0)
        self.tick(at=1)
        self.tick(False, at=2)
        self.tick(at=3)
        self.tick(at=4)
        self.assertEqual(self.native.requests, [])
        self.tick(at=5)
        self.assertEqual(self.native.requests, ['limits_ms1'])

    def test_profile_uses_its_own_readiness_not_hangar_flag(self):
        self.reach('waiting_view', 2)
        self.native.profile_ready_flag = False
        for _ in range(3):
            self.assertFalse(self.tick(False))
        self.assertNotIn('limits_profile', self.native.requests)
        self.native.profile_ready_flag = True
        for _ in range(3):
            self.assertFalse(self.tick(False))
        self.assertIn('limits_profile', self.native.requests)

    def test_profile_return_waits_before_second_ms1_selection(self):
        self.reach('waiting_return', 3)
        selected = self.native.actions.count(('select', 1))
        self.tick(False)
        bad = self.observed()
        bad['vehicle_model_loaded'] = False
        self.tick(True, bad)
        self.assertEqual(self.native.actions.count(('select', 1)), selected)
        self.tick(True)
        self.assertEqual(self.native.actions.count(('select', 1)), selected + 1)

    def test_disabled_button_required_before_any_success_capture(self):
        self.tick()
        self.native.enabled = True
        with self.assertRaises(RuntimeError):
            self.tick()
        self.assertEqual(self.native.requests, [])

    def test_account_resource_or_statistics_change_fails_before_capture(self):
        for key, changed in (('database_id', 2), ('resources', [100001, 0, 0]), ('statistics', [1, 0, 0, 0])):
            with self.subTest(key=key):
                self.setUp()
                self.tick()
                self.native.subject[key] = changed
                with self.assertRaises(RuntimeError):
                    self.tick()
                self.assertFalse(self.scenario.completed)

    def test_malformed_initial_identity_is_not_a_trusted_baseline(self):
        edits = (('database_id', True), ('database_id', 0), ('resources', [True, 0, 0]),
                 ('resources', [100000, 0]), ('resources', [-1, 0, 0]),
                 ('statistics', [0, 0, float('nan'), 0]), ('statistics', [0, 0, 0, 0, 0]))
        for key, changed in edits:
            with self.subTest(key=key, changed=changed):
                self.setUp()
                self.native.subject[key] = changed
                with self.assertRaises((TypeError, ValueError)):
                    self.tick()
                self.assertEqual(self.native.actions, [])

    def test_missing_png_blocks_next_action(self):
        self.native.auto_files = False
        self.reach('waiting_png', 0)
        for _ in range(6):
            self.assertFalse(self.tick())
        self.assertEqual(self.native.actions, [('select', 1)])
        self.assertEqual(self.native.requests, ['limits_ms1'])

    def test_readiness_loss_while_waiting_png_cannot_complete_or_navigate(self):
        self.reach('waiting_png', 0)
        with self.assertRaises(RuntimeError):
            self.tick(False)
        self.assertEqual(self.native.actions, [('select', 1)])

    def test_identity_change_while_waiting_final_png_is_rejected(self):
        self.reach('waiting_png', 5)
        self.native.subject['resources'][0] += 1
        with self.assertRaises(RuntimeError):
            self.tick()
        self.assertFalse(self.scenario.completed)
        self.assertEqual(self.complete_events(), [])

    def test_crew_change_after_final_png_request_is_rejected(self):
        self.reach('waiting_png', 5)
        self.native.crew_value['tankmen'][0]['vehicle_slot_index'] = 1
        with self.assertRaises((RuntimeError, ValueError)):
            self.tick()
        self.assertFalse(self.scenario.completed)

    def test_foreign_account_crew_rejected(self):
        self.native.crew_value['database_id'] = 2
        self.tick()
        self.tick()
        with self.assertRaises(RuntimeError):
            self.tick(at=4)
        self.assertEqual(self.native.requests, [])

    def test_disabled_policy_error_propagates_without_complete(self):
        self.reach('waiting_png', 4)
        def unavailable():
            raise RuntimeError('unit policy absent')
        self.native.deny_battle = unavailable
        with self.assertRaisesRegex(RuntimeError, 'unit policy absent'):
            self.tick()
        self.assertEqual(self.complete_events(), [])
        pairs = [x for event, x in self.events if event == 'limits_scenario_action' and x['action'] == 'deny_battle']
        self.assertEqual([x['moment'] for x in pairs], ['call'])

    def test_600_advances_is_budget_error_not_a_process_kill(self):
        for _ in range(S.MAX_ADVANCES):
            self.assertFalse(self.tick(False))
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            self.tick(False)
        self.assertEqual(self.native.actions, [])
        self.assertFalse(self.scenario.completed)

    def test_clock_reversal_nonfinite_and_boolean_fail(self):
        for invalid in (-1, float('nan'), float('inf'), True):
            with self.subTest(invalid=invalid):
                self.setUp()
                self.tick(False, at=0)
                with self.assertRaises(ValueError):
                    self.tick(False, at=invalid)

    def test_global_wrapper_marks_error_and_refuses_resume(self):
        self.scenario.phase = 'unsupported-unit-state'
        with patch.object(S, '_scenario', self.scenario):
            with self.assertRaises(RuntimeError):
                S.advance(self.record, {}, self.observed(), True)
            self.assertEqual(self.scenario.phase, 'error')
            with self.assertRaisesRegex(RuntimeError, 'cannot resume'):
                S.advance(self.record, {}, self.observed(), True)
        failures = [x for event, x in self.events if event == 'limits_scenario_error']
        self.assertEqual(len(failures), 2)
        self.assertEqual(self.complete_events(), [])


class HistoricalNativeSnapshotInputs(unittest.TestCase):
    """Real crew02 records test only the reused shape/hash validator."""
    @classmethod
    def setUpClass(cls):
        install = ROOT / 'local/evidence/20261005-p02-ms1-crew/crew02-prepare'
        if not (install / 'install-plan.json').is_file():
            raise unittest.SkipTest('Historical native crew02 snapshot corpus absent; no data fabricated')
        plan = json.loads((install / 'install-plan.json').read_bytes())
        paths = list(Path(plan['settings']['trace_dir']).glob('native-*.jsonl'))
        if len(paths) != 1:
            raise ValueError('Historical trace count differs')
        raw = paths[0].read_bytes()
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('Historical trace outside bound')
        if hashlib.sha256(raw).hexdigest() != 'df55ed6b67f1a16cf96f3f13b07af7751f6860d8f7348e3db2319f931cd2f440':
            raise ValueError('Historical native crew02 trace changed')
        records = [json.loads(row) for row in raw.splitlines()]
        cls.snapshots = []
        for row in records:
            if row.get('event') == 'ms1_crew_observation':
                value = dict(row)
                value.pop('event')
                value.pop('elapsed_seconds')
                cls.snapshots.append(value)
        if len(cls.snapshots) != 3:
            raise ValueError('Expected exactly three historical native observations')

    def test_three_actual_snapshots_validate_without_mutation(self):
        saved = copy.deepcopy(self.snapshots)
        fingerprints = [S.checked_snapshot(value) for value in self.snapshots]
        self.assertEqual(len(set(fingerprints)), 1)
        self.assertEqual(self.snapshots, saved)

    def test_mutated_actual_crew_snapshot_is_rejected(self):
        value = copy.deepcopy(self.snapshots[1])
        value['vehicles'][1]['crew'][0]['tankman_inventory_id'] = 1
        with self.assertRaises(ValueError):
            S.checked_snapshot(value)

    def test_fake_navigation_can_reuse_actual_snapshot_shape_only(self):
        native = FakeNative()
        native.crew_value = copy.deepcopy(self.snapshots[0])
        native.subject['database_id'] = native.crew_value['database_id']
        events, clock = [], [0]
        scenario = S._Scenario({}, lambda event, **fields: events.append((event, fields)), native, lambda: clock[0])
        for _ in range(80):
            clock[0] += 1
            observed = {'selected_inventory_id': native.selected, 'vehicle_model_loaded': True,
                        'vehicle': {'type_compact_descr': 3329 if native.selected == 1 else 7169}}
            if scenario.advance(observed, native.page == 'Hangar'):
                break
        self.assertTrue(scenario.completed)
        self.assertEqual(native.observations, 3)
        self.assertEqual(len([1 for event, _ in events if event == 'limits_scenario_complete']), 1)


class NativeProfileBridgeControls(unittest.TestCase):
    """Injected import boundaries exercise production bridge, not FakeNative."""
    def setUp(self):
        self.player = types.SimpleNamespace(databaseID=1)
        self.big_world = types.ModuleType('BigWorld')
        self.big_world.player = lambda: self.player
        self.shared = types.ModuleType('hangar_ui_probe')
        self.shared._observe = Mock(return_value={'observed_ready': True})
        self.legacy = types.ModuleType('hangar_bootstrap')
        self.legacy._started = False
        self.legacy.observe_profile = Mock(side_effect=AssertionError('legacy bootstrap gate must not be used'))
        self.modules = {'BigWorld': self.big_world, 'hangar_ui_probe': self.shared,
                        'hangar_bootstrap': self.legacy}
        # No constructor: these methods need neither real paths nor client APIs.
        self.native = object.__new__(S._Native)

    def test_live_profile_section_bypasses_unstarted_legacy_bootstrap(self):
        with patch.dict(sys.modules, self.modules):
            self.assertTrue(self.native.profile_ready())
            self.player.databaseID = 2
            self.shared._observe.return_value = {'observed_ready': False}
            self.assertFalse(self.native.profile_ready())
        self.assertEqual(self.shared._observe.call_args_list,
                         [(('profileSummaryPage', 1), {}), (('profileSummaryPage', 2), {})])
        self.legacy.observe_profile.assert_not_called()
        self.assertFalse(self.legacy._started)

    def test_only_exact_shared_observed_ready_true_can_release_gate(self):
        cases = (({'observed_ready': True}, True), ({'observed_ready': False}, False),
                 ({'ready': True}, False), ({'observed_ready': 1}, False),
                 ({'observed_ready': 'True'}, False), ({}, False))
        with patch.dict(sys.modules, self.modules):
            for returned, expected in cases:
                with self.subTest(returned=returned):
                    self.shared._observe.return_value = returned
                    self.assertIs(self.native.profile_ready(), expected)
        self.legacy.observe_profile.assert_not_called()

    def test_shared_observer_exception_propagates_instead_of_waiting_forever(self):
        error = RuntimeError('unit original Profile owner mismatch')
        self.shared._observe.side_effect = error
        with patch.dict(sys.modules, self.modules):
            with self.assertRaises(RuntimeError) as caught:
                self.native.profile_ready()
        self.assertIs(caught.exception, error)
        self.shared._observe.assert_called_once_with('profileSummaryPage', 1)
        self.legacy.observe_profile.assert_not_called()

    def test_original_close_callback_waits_for_shared_profile_ready(self):
        page = type('ProfilePage', (), {})()
        page.onCloseProfile = Mock()
        self.native.views = lambda: (page, False)
        with patch.dict(sys.modules, self.modules):
            self.shared._observe.return_value = {'observed_ready': False}
            with self.assertRaisesRegex(RuntimeError, 'ready ProfilePage'):
                self.native.close_profile()
            page.onCloseProfile.assert_not_called()
            self.shared._observe.return_value = {'observed_ready': True}
            self.native.close_profile()
        page.onCloseProfile.assert_called_once_with()
        self.legacy.observe_profile.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
