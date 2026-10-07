# -*- coding: utf-8 -*-
"""Window diagnostic lifecycle controls; no client/server or native render runs.

FakeNative is an explicitly synthetic control boundary. The existing measured
crew02 corpus is used separately as read-only input to the reused validator.
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
sys.path.insert(0, str(ROOT / 'tests'))
import hangar_windows_scenario as S
from test_hangar_limits_scenario import unit_snapshot


class FakeNative:
    """Sequencing only. The real bridge uses original callbacks and PNG parsing."""
    def __init__(self, selected=2):
        self.state = {'database_id': 1, 'resources': [100000, 0, 0], 'statistics': [0, 0, 0, 0],
                      'selected_inventory_id': selected, 'hangar_owner': 10,
                      'crew_owner': 11, 'ammunition_owner': 12}
        self.state['view_scan'] = {
            'version': 1, 'scope': 'LOBBY_SUB_current_and_WINDOW_alias',
            'lobby_sub': {'class_name': 'Hangar', 'alias': 'hangar', 'flash_bound': True, 'owner_id': 10},
            'window': {'view_count': 0, 'queried_alias': 'technicalMaintenance', 'matched_view': None},
            'unsupported_present': False}
        self.actions, self.requests, self.snapshots = [], [], []
        self.crew_value, self.observations = unit_snapshot(), 0
        self.auto_files = True

    def context(self):
        return copy.deepcopy(self.state)

    def select_ms1(self):
        self.actions.append('select_ms1')
        self.state['selected_inventory_id'] = 1

    def deny(self, action):
        self.actions.append(action)

    def observe(self, record):
        self.observations += 1
        value = copy.deepcopy(self.crew_value)
        value['selected_inventory_id'] = self.state['selected_inventory_id']
        value['selected_ms1'] = value['selected_inventory_id'] == 1
        value['observation_index'] = self.observations
        self.snapshots.append(value)
        return value

    def request(self, basename):
        if basename in self.requests:
            raise ValueError('unit duplicate request')
        self.requests.append(basename)

    def screenshot(self, basename):
        if basename not in self.requests:
            raise ValueError('unit request absent')
        if not self.auto_files:
            return None
        return {'basename': basename, 'png_container_valid': True, 'native_pixels_review': 'NOT_RUN'}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.native, self.events, self.now = FakeNative(), [], 0.0
        self.scenario = S._Scenario({}, self.record, self.native, lambda: self.now)

    def record(self, event, **fields):
        self.events.append((event, fields))

    def observed(self):
        selected = self.native.state['selected_inventory_id']
        return {'selected_inventory_id': selected, 'vehicle_model_loaded': True,
                'vehicle': {'type_compact_descr': 3329 if selected == 1 else 7169}}

    def tick(self, ready=True, observed=None, at=None):
        self.now = self.now + 1.0 if at is None else at
        return self.scenario.advance(self.observed() if observed is None else observed, ready)

    def reach(self, phase, step):
        for _ in range(40):
            if self.scenario.phase == phase and self.scenario.step == step:
                return
            self.assertFalse(self.tick())
        self.fail('unit state not reached')

    def complete(self):
        for _ in range(40):
            if self.tick():
                return
        self.fail('unit diagnostic did not complete')

    def complete_events(self):
        return [fields for event, fields in self.events if event == 'windows_scenario_complete']

    def test_exact_two_denials_three_png_three_snapshots_and_idempotent_complete(self):
        self.complete()
        self.assertEqual(self.native.actions, ['select_ms1', 'appearance', 'maintenance'])
        self.assertEqual(self.native.requests, list(S.SCREENSHOTS))
        self.assertEqual(self.native.observations, 3)
        self.assertEqual(len(set(S.checked_snapshot(row) for row in self.native.snapshots)), 1)
        actions = [fields for event, fields in self.events if event == 'windows_scenario_action']
        self.assertEqual([(row['action'], row['moment']) for row in actions],
                         [(name, moment) for name in self.native.actions for moment in ('call', 'return')])
        self.assertEqual([row['step'] for row in actions], [0, 0, 1, 1, 2, 2])
        complete = self.complete_events()[0]
        self.assertEqual((complete['screenshots'], complete['observations']), (3, 3))
        self.assertEqual(complete['native_pixels_review'], 'NOT_RUN')
        self.assertEqual(complete['human_manual_acceptance'], 'NOT_RUN')
        self.assertFalse(complete['computer_input'])
        self.assertFalse(complete['automatic_quit'])
        self.assertTrue(self.tick())
        self.assertEqual(len(self.complete_events()), 1)
        self.assertEqual(self.native.observations, 3)

    def test_selected_ms1_does_not_emit_selection_or_repeat_original_carousel(self):
        self.native.state['selected_inventory_id'] = 1
        self.complete()
        self.assertEqual(self.native.actions, ['appearance', 'maintenance'])

    def test_not_ready_start_has_no_actions_or_crew_reads(self):
        for _ in range(5):
            self.assertFalse(self.tick(False))
        self.assertEqual((self.native.actions, self.native.requests, self.native.observations), ([], [], 0))

    def test_boolean_readiness_and_dict_observation_required(self):
        for observed, ready in (({}, 1), ([], True), ({}, None)):
            with self.subTest(observed=observed, ready=ready), self.assertRaises(TypeError):
                self.scenario.advance(observed, ready)

    def test_ready_model_selected_id_and_native_descriptor_must_agree(self):
        self.tick()
        bad = [dict(self.observed(), vehicle_model_loaded=False),
               dict(self.observed(), selected_inventory_id=2),
               dict(self.observed(), selected_inventory_id=True),
               dict(self.observed(), vehicle={'type_compact_descr': 7169}),
               dict(self.observed(), vehicle=[])]
        for value in bad:
            for _ in range(3):
                self.assertFalse(self.tick(True, value))
        self.assertEqual(self.native.requests, [])
        self.assertEqual(self.native.observations, 0)

    def test_initial_stability_loss_restarts_two_seconds(self):
        self.tick(at=0)
        self.tick(at=1)
        self.tick(False, at=2)
        self.tick(at=3)
        self.tick(at=4)
        self.assertEqual(self.native.requests, [])
        self.tick(at=5)
        self.assertEqual(self.native.requests, ['windows_ms1'])

    def test_identity_and_original_component_replacements_are_rejected(self):
        changes = {'database_id': 2, 'resources': [99999, 0, 0], 'statistics': [1, 0, 0, 0],
                   'hangar_owner': 20, 'crew_owner': 21, 'ammunition_owner': 22}
        for name, value in changes.items():
            with self.subTest(name=name):
                self.setUp()
                self.tick()
                self.native.state[name] = value
                with self.assertRaises(RuntimeError):
                    self.tick()
                self.assertEqual(self.native.requests, [])

    def test_malformed_context_cannot_become_trusted_initial_baseline(self):
        for key, value in (('database_id', True), ('resources', [True, 0, 0]),
                           ('statistics', [0, 0, -1, 0]), ('selected_inventory_id', True),
                           ('hangar_owner', 0), ('ammunition_owner', 2 ** 64)):
            with self.subTest(key=key):
                self.setUp()
                self.native.state[key] = value
                with self.assertRaises(ValueError):
                    self.tick()
                self.assertEqual(self.native.actions, [])
        with self.assertRaises(ValueError):
            S.checked_context(dict(self.native.state, unknown=1))

    def test_missing_png_blocks_next_denial(self):
        self.native.auto_files = False
        self.reach('waiting_png', 0)
        for _ in range(5):
            self.assertFalse(self.tick())
        self.assertEqual(self.native.actions, ['select_ms1'])
        self.assertEqual(self.native.observations, 1)

    def test_readiness_and_identity_are_rechecked_while_waiting_every_png(self):
        for step in range(3):
            for fault in ('ready', 'model', 'selected', 'identity', 'view'):
                with self.subTest(step=step, fault=fault):
                    self.setUp()
                    self.reach('waiting_png', step)
                    observed, ready = self.observed(), True
                    if fault == 'ready':
                        ready = False
                    elif fault == 'model':
                        observed['vehicle_model_loaded'] = False
                    elif fault == 'selected':
                        self.native.state['selected_inventory_id'] = 2
                    elif fault == 'identity':
                        self.native.state['resources'][0] += 1
                    else:
                        self.native.state['ammunition_owner'] += 1
                    with self.assertRaises(RuntimeError):
                        self.tick(ready, observed)
                    self.assertFalse(self.scenario.completed)

    def test_denial_must_leave_same_view_identity_and_selection(self):
        for name, value in (('selected_inventory_id', 2), ('database_id', 2), ('hangar_owner', 99)):
            with self.subTest(name=name):
                self.setUp()
                self.reach('waiting_png', 0)
                self.native.deny = lambda action: self.native.state.update({name: value})
                with self.assertRaises(RuntimeError):
                    self.tick()
                actions = [fields for event, fields in self.events
                           if event == 'windows_scenario_action' and fields['action'] == 'appearance']
                self.assertEqual([row['moment'] for row in actions], ['call'])

    def test_original_view_cannot_disappear_during_warning_delay(self):
        self.reach('waiting_view', 1)
        with self.assertRaises(RuntimeError):
            self.tick(False)
        self.assertNotIn('windows_appearance', self.native.requests)

    def test_crew_changes_after_each_warning_capture_are_rejected(self):
        for step in (1, 2):
            with self.subTest(step=step):
                self.setUp()
                self.reach('waiting_png', step)
                self.native.crew_value['tankmen'][0]['vehicle_slot_index'] = 1
                with self.assertRaises(ValueError):
                    self.tick()
                self.assertFalse(self.scenario.completed)

    def test_matching_maintenance_view_or_false_empty_query_is_rejected(self):
        for fault in ('matched_view', 'alias', 'unsupported', 'too_many', 'bool_count', 'false_hangar'):
            with self.subTest(fault=fault):
                self.setUp()
                self.reach('waiting_png', 1)
                scan = self.native.state['view_scan']
                if fault == 'matched_view':
                    scan['window']['matched_view'] = {'class_name': 'TechnicalMaintenance'}
                elif fault == 'alias':
                    scan['window']['queried_alias'] = 'unmeasured'
                elif fault == 'unsupported':
                    scan['unsupported_present'] = True
                elif fault == 'too_many':
                    scan['window']['view_count'] = 65
                elif fault == 'bool_count':
                    scan['window']['view_count'] = False
                else:
                    scan['lobby_sub']['class_name'] = 'VehicleCustomization'
                with self.assertRaises((ValueError, RuntimeError)):
                    self.tick()
                self.assertFalse(self.scenario.completed)

    def test_unrelated_native_popup_is_not_misreported_as_empty_container(self):
        self.native.state['view_scan']['window']['view_count'] = 1
        self.complete()
        states = [fields['state'] for event, fields in self.events if event == 'windows_scenario_state']
        self.assertTrue(all(row['view_scan']['window']['view_count'] == 1 for row in states))

    def test_foreign_account_snapshot_is_rejected_before_first_png(self):
        self.native.crew_value['database_id'] = 2
        self.reach('waiting_view', 0)
        self.tick()
        with self.assertRaises(RuntimeError):
            self.tick(at=5)
        self.assertEqual(self.native.requests, [])

    def test_final_crew_read_that_changes_context_cannot_complete(self):
        self.reach('waiting_png', 2)
        original = self.native.observe
        def changed(record):
            result = original(record)
            self.native.state['ammunition_owner'] += 1
            return result
        self.native.observe = changed
        with self.assertRaises(RuntimeError):
            self.tick()
        self.assertFalse(self.scenario.completed)
        self.assertEqual(self.complete_events(), [])

    def test_wrapper_propagates_policy_exception_and_prevents_resume(self):
        self.reach('waiting_png', 0)
        self.native.deny = Mock(side_effect=RuntimeError('unit missing policy'))
        with patch.object(S, '_scenario', self.scenario):
            with self.assertRaisesRegex(RuntimeError, 'missing policy'):
                S.advance(self.record, {}, self.observed(), True)
            self.assertEqual(self.scenario.phase, 'error')
            with self.assertRaisesRegex(RuntimeError, 'cannot resume'):
                S.advance(self.record, {}, self.observed(), True)
        self.assertEqual(self.complete_events(), [])

    def test_constructor_error_is_recorded_and_propagated(self):
        with patch.object(S, '_scenario', None), patch.object(S, '_Native', side_effect=ValueError('unit path')):
            with self.assertRaisesRegex(ValueError, 'unit path'):
                S.advance(self.record, {}, self.observed(), True)
        self.assertEqual(self.events[-1][0], 'windows_scenario_error')

    def test_observation_budget_fails_without_process_control(self):
        for _ in range(S.MAX_ADVANCES):
            self.assertFalse(self.tick(False))
        with self.assertRaisesRegex(RuntimeError, 'budget'):
            self.tick(False)
        self.assertEqual(self.native.actions, [])

    def test_clock_reversal_nonfinite_and_boolean_are_rejected(self):
        for value in (-1, float('nan'), float('inf'), True):
            with self.subTest(value=value):
                self.setUp()
                self.tick(False, at=0)
                with self.assertRaises(ValueError):
                    self.tick(False, at=value)


class NativeBoundaryControls(unittest.TestCase):
    """Exercise the production wrapper checks using isolated import boundaries."""
    def setUp(self):
        self.calls = []
        def original_appearance(panel):
            self.fail('original unavailable window entry must never execute')
        def original_maintenance(panel):
            self.fail('original unavailable window entry must never execute')
        def appearance(panel):
            self.calls.append(('appearance', panel))
        def maintenance(panel):
            self.calls.append(('maintenance', panel))
        self.panel_class = type('AmmunitionPanel', (), {'showCustomization': appearance,
                                                      'showTechnicalMaintenance': maintenance})
        self.guard = types.SimpleNamespace(active=True, panel_class=self.panel_class,
                     originals={'showCustomization': original_appearance,
                                'showTechnicalMaintenance': original_maintenance},
                     replacements=(('showCustomization', appearance), ('showTechnicalMaintenance', maintenance)))
        self.policy = types.SimpleNamespace(_window_guard=self.guard)
        self.native = S._Native.__new__(S._Native)
        self.native.panel = self.panel_class()

    def invoke(self, action):
        with patch.dict(sys.modules, {'hangar_capabilities': self.policy}):
            return self.native.deny(action)

    def test_only_verified_wrappers_bound_to_actual_panel_are_called(self):
        self.invoke('appearance')
        self.invoke('maintenance')
        self.assertEqual(self.calls, [('appearance', self.native.panel), ('maintenance', self.native.panel)])

    def test_absent_inactive_or_wrong_class_guard_rejected_without_callback(self):
        for fault in ('absent', 'inactive', 'truthy', 'subclass'):
            with self.subTest(fault=fault):
                self.setUp()
                if fault == 'absent':
                    self.policy._window_guard = None
                elif fault == 'inactive':
                    self.guard.active = False
                elif fault == 'truthy':
                    self.guard.active = 1
                else:
                    self.native.panel = type('ForeignPanel', (self.panel_class,), {})()
                with self.assertRaises(RuntimeError):
                    self.invoke('appearance')
                self.assertEqual(self.calls, [])

    def test_either_rebound_method_prevents_all_actions(self):
        for method in S.METHODS.values():
            with self.subTest(method=method):
                self.setUp()
                setattr(self.panel_class, method, lambda panel: self.fail('foreign binding'))
                with self.assertRaises(RuntimeError):
                    self.invoke('appearance')
                self.assertEqual(self.calls, [])

    def test_instance_shadow_and_original_binding_masquerade_rejected(self):
        self.native.panel.showCustomization = lambda: self.fail('instance shadow')
        with self.assertRaises(RuntimeError):
            self.invoke('appearance')
        self.setUp()
        self.guard.originals['showCustomization'] = self.guard.replacements[0][1]
        with self.assertRaises(RuntimeError):
            self.invoke('appearance')

    def test_unexpected_or_duplicate_replacement_methods_rejected(self):
        for bindings in ((), self.guard.replacements + (('extra', lambda panel: None),),
                         (self.guard.replacements[0], self.guard.replacements[0])):
            with self.subTest(bindings=len(bindings)):
                self.guard.replacements = bindings
                with self.assertRaises(RuntimeError):
                    self.invoke('appearance')
        self.assertEqual(self.calls, [])

    def test_unknown_action_and_callback_exception_propagate(self):
        with self.assertRaises(ValueError):
            self.invoke('open_anything')
        def broken(panel):
            raise LookupError('unit original Warning unavailable')
        self.panel_class.showCustomization = broken
        self.guard.replacements = (('showCustomization', broken), self.guard.replacements[1])
        with self.assertRaisesRegex(LookupError, 'Warning unavailable'):
            self.invoke('appearance')

    def test_screenshot_request_checks_fixed_names_collisions_and_does_not_retry_failure(self):
        self.native.requested = set()
        self.native._entries = lambda: []
        api = types.SimpleNamespace(screenShot=Mock())
        with patch.dict(sys.modules, {'BigWorld': api}):
            with self.assertRaises(ValueError):
                self.native.request('../foreign')
            self.native.request('windows_ms1')
            api.screenShot.assert_called_once_with('png', 'windows_ms1')
            with self.assertRaises(ValueError):
                self.native.request('windows_ms1')
            self.native._entries = lambda: ['windows_appearance_001.png']
            with self.assertRaises(ValueError):
                self.native.request('windows_appearance')
            self.native._entries = lambda: []
            api.screenShot.side_effect = OSError('unit native writer failure')
            with self.assertRaises(OSError):
                self.native.request('windows_maintenance')
            with self.assertRaises(ValueError):
                self.native.request('windows_maintenance')

    def test_actual_context_uses_same_hangar_ammunition_alias_and_class(self):
        panel = self.native.panel
        panel.flashObject = object()
        page = type('Hangar', (), {})()
        page.components, page.settings, page.flashObject = {'ammunitionPanel': panel}, types.SimpleNamespace(alias='hangar'), object()
        windows = types.SimpleNamespace(getViewCount=Mock(return_value=0), getView=Mock(return_value=None))
        manager = types.SimpleNamespace(getContainer=lambda kind: windows if kind == 4 else types.SimpleNamespace(getView=lambda: page))
        modules = {
            'gui.WindowsManager': types.SimpleNamespace(g_windowsManager=types.SimpleNamespace(
                window=types.SimpleNamespace(containerManager=manager))),
            'gui.Scaleform.framework': types.SimpleNamespace(ViewTypes=types.SimpleNamespace(LOBBY_SUB=2, WINDOW=4)),
            'gui.Scaleform.framework.managers.containers': types.SimpleNamespace(POP_UP_CRITERIA=types.SimpleNamespace(VIEW_ALIAS=1)),
            'gui.Scaleform.daapi.settings.views': types.SimpleNamespace(VIEW_ALIAS=types.SimpleNamespace(
                TECHNICAL_MAINTENANCE='technicalMaintenance', LOBBY_CUSTOMIZATION='customization')),
            'gui.Scaleform.daapi.view.lobby.hangar.AmmunitionPanel': types.SimpleNamespace(AmmunitionPanel=self.panel_class),
        }
        current = FakeNative(1).context()
        current.pop('ammunition_owner')
        current.pop('view_scan')
        current['hangar_owner'] = id(page)
        with patch.dict(sys.modules, modules), patch.object(S.CrewNative, 'context', return_value=current):
            actual = self.native.context()
            self.assertEqual(actual['ammunition_owner'], id(panel))
            windows.getView.assert_called_once_with(criteria={1: 'technicalMaintenance'})
            self.assertEqual(actual['view_scan']['window']['matched_view'], None)
            self.assertEqual(S.checked_context(actual)['hangar_owner'], id(page))
            windows.getViewCount.return_value = 65
            with self.assertRaises(ValueError):
                self.native.context()
            self.assertEqual(windows.getView.call_count, 1)
            windows.getViewCount.return_value = 1
            found = type('TechnicalMaintenance', (), {})()
            found.settings, found.flashObject = types.SimpleNamespace(alias='technicalMaintenance'), object()
            windows.getView.return_value = found
            actual = self.native.context()
            self.assertTrue(actual['view_scan']['unsupported_present'])
            self.assertEqual(actual['view_scan']['window']['matched_view']['class_name'], 'TechnicalMaintenance')
            with self.assertRaises(RuntimeError):
                S.checked_context(actual)
            windows.getView.return_value = None
            panel.flashObject = None
            with self.assertRaises(RuntimeError):
                self.native.context()
            panel.flashObject = object()
            current['hangar_owner'] += 1
            with self.assertRaises(RuntimeError):
                self.native.context()

    def test_native_view_metadata_bounds_do_not_swallow_unreadable_properties(self):
        view = types.SimpleNamespace(settings=types.SimpleNamespace(alias='x' * 65), flashObject=None)
        with self.assertRaises(ValueError):
            S.view_record(view)
        with self.assertRaises(AttributeError):
            S.view_record(object())
        self.assertIsNone(S.view_record(None))


class HistoricalSnapshotInputs(unittest.TestCase):
    """Historical native crew data tests parsing only, never new window acceptance."""
    def test_three_real_crew02_records_remain_equal_in_new_mocked_lifecycle(self):
        install = ROOT / 'local/evidence/20261005-p02-ms1-crew/crew02-prepare/install-plan.json'
        if not install.is_file():
            self.skipTest('Historical native corpus absent; no substitute generated')
        plan = json.loads(install.read_bytes())
        paths = list(Path(plan['settings']['trace_dir']).glob('native-*.jsonl'))
        self.assertEqual(len(paths), 1)
        raw = paths[0].read_bytes()
        self.assertLess(len(raw), 8 * 1024 * 1024)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'df55ed6b67f1a16cf96f3f13b07af7751f6860d8f7348e3db2319f931cd2f440')
        rows = [json.loads(line) for line in raw.splitlines()]
        snapshots = [{key: value for key, value in row.items() if key not in ('event', 'elapsed_seconds')}
                     for row in rows if row.get('event') == 'ms1_crew_observation']
        self.assertEqual(len(snapshots), 3)
        saved, consumed = copy.deepcopy(snapshots), []
        native, events, clock = FakeNative(1), [], [0.0]
        def observe(record):
            value = snapshots[len(consumed)]
            consumed.append(value)
            return value
        native.observe = observe
        native.state['database_id'] = snapshots[0]['database_id']
        scenario = S._Scenario({}, lambda name, **fields: events.append((name, fields)), native, lambda: clock[0])
        for _ in range(40):
            clock[0] += 1.0
            if scenario.advance({'selected_inventory_id': 1, 'vehicle_model_loaded': True,
                                 'vehicle': {'type_compact_descr': 3329}}, True):
                break
        self.assertTrue(scenario.completed)
        self.assertEqual(len(consumed), 3)
        self.assertEqual(snapshots, saved)
        self.assertEqual(len(set(S.checked_snapshot(row) for row in snapshots)), 1)


if __name__ == '__main__':
    unittest.main()
