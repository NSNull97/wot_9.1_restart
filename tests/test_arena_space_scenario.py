# -*- coding: utf-8 -*-
"""Synthetic control/lifecycle tests; no native Entity, geometry or UI proof."""
import copy
import json
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import arena_space_scenario as scenario


def account_observation():
    return {'version': 1, 'native_connected': True, 'repository_present': True,
        'repository_owner_id': 100, 'player_present': True, 'player_owner_id': 200,
        'player_is_original_account': True, 'player_is_original_avatar': False,
        'entity_id': 0x09100001, 'name': u'Тестовый_танкист', 'observation_index': 1}


def avatar_observation():
    result = account_observation()
    result.update(player_is_original_account=False, player_is_original_avatar=True,
        entity_id=scenario.AVATAR_ID, player_owner_id=300, space_id=1,
        player_vehicle_id=scenario.VEHICLE_ID, vehicle_present=False,
        user_sees_world=False, steps_till_init=1, in_world=True,
        arena_present=True, arena_type_id=1, arena_unique_id=1,
        geometry_name='01_karelia', geometry_path='spaces/01_karelia',
        space_load_progress=1.0, position=[0.0, 30.0, 0.0], space_initialized=False,
        acceptance='OBSERVATION_ONLY')
    return result


class NativeControl(object):
    def __init__(self):
        self.initial = account_observation()
        self.identity = {'database_id': 1, 'entity_id': self.initial['entity_id'], 'name': self.initial['name']}
        self.value = account_observation()
        self.initializations, self.observations = 0, 0
        self.init_error = False
        self.observe_error = False

    def account(self):
        return copy.deepcopy(self.initial), dict(self.identity)

    def initialize(self):
        self.initializations += 1
        if self.init_error:
            raise RuntimeError('synthetic initialization failure')

    def observe(self):
        self.observations += 1
        if self.observe_error:
            raise RuntimeError('synthetic native reader failure')
        value = copy.deepcopy(self.value)
        value['observation_index'] = self.observations + 1
        return value


class ArenaSpaceTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict((name, getattr(scenario, name)) for name in
            ('_run', '_arm_attempted', '_closing', '_finished_cleanup', '_cleanup_errors', '_Native'))
        scenario._run = None
        scenario._arm_attempted = scenario._closing = scenario._finished_cleanup = False
        scenario._cleanup_errors = []
        self.native = NativeControl()
        scenario._Native = lambda record: self.native
        self.events = []
        self.record = lambda event, **data: self.events.append((event, data))
        self.cleanup_calls, self.cleanup_fails = [], set()
        self.saved_cleanup = (scenario.arena_bootstrap.fini_before_entities, scenario.arena_bootstrap.fini_after_entities)

        def stage(name):
            def run():
                self.cleanup_calls.append(name)
                if name in self.cleanup_fails:
                    raise ValueError('synthetic phase failure')
            return run
        scenario.arena_bootstrap.fini_before_entities = stage('before')
        scenario.arena_bootstrap.fini_after_entities = stage('after')
        self.native_cleanup = stage('native')

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(scenario, name, value)
        scenario.arena_bootstrap.fini_before_entities, scenario.arena_bootstrap.fini_after_entities = self.saved_cleanup

    def arm(self, avatar=True):
        scenario.arm(self.record)
        if avatar:
            self.native.value = avatar_observation()

    def pair(self, method, call_id, owner=300, space=1, line=None, return_offset=None):
        source_line, normal_return = scenario.CALLBACKS[method]
        if line is not None:
            source_line = line
        if return_offset is not None:
            normal_return = return_offset
        self.assertTrue(scenario.note_avatar_call('call', method, source_line, -1, call_id, owner, scenario.AVATAR_ID, space))
        self.assertTrue(scenario.note_avatar_call('return', method, source_line, normal_return, call_id, owner, scenario.AVATAR_ID, space))

    def notes(self):
        self.assertTrue(scenario.note_geometry_mapped(1, 'spaces/01_karelia'))
        self.pair('onEnterWorld', 11)
        self.pair('onSpaceLoaded', 12)

    def test_normal_unarmed_is_passive_even_with_malformed_notes(self):
        self.assertFalse(scenario.note_avatar_call(None, [], None, None, None, None, None, None))
        self.assertFalse(scenario.note_geometry_mapped(None, object()))
        self.assertFalse(scenario.advance(self.record))
        self.assertEqual((self.native.initializations, self.native.observations, self.events), (0, 0, []))

    def test_arm_initializes_once_before_publishing_ready_for_trigger(self):
        self.arm()
        self.assertEqual(self.native.initializations, 1)
        self.assertEqual([event for event, _ in self.events], ['arena_space_armed'])
        self.assertFalse(self.events[0][1]['native_entity_created_by_scenario'])
        self.assertRaises(RuntimeError, scenario.arm, self.record)

    def test_arm_requires_actual_connected_account_repository_and_identity(self):
        for key, wrong in (('player_is_original_account', False), ('native_connected', False),
                           ('repository_present', False), ('repository_owner_id', None), ('name', 'other')):
            native = NativeControl()
            native.initial[key] = wrong
            self.assertRaises(RuntimeError, scenario._Scenario, self.record, native)
            self.assertEqual(native.initializations, 0)
        self.assertEqual(self.events, [])

    def test_initialization_failure_never_publishes_armed_and_all_cleanup_runs(self):
        self.native.init_error = True
        self.assertRaises(RuntimeError, scenario.arm, self.record)
        self.assertEqual(self.events, [])
        self.assertIsNone(scenario._run)
        scenario.fini(self.record, self.native_cleanup)
        self.assertEqual(self.cleanup_calls, ['before', 'native', 'after'])
        self.assertRaises(RuntimeError, scenario.arm, self.record)

    def test_exact_native_contract_completes_without_claiming_full_world(self):
        self.arm()
        self.notes()
        self.assertTrue(scenario.advance(self.record))
        complete = [row for event, row in self.events if event == 'arena_space_complete']
        self.assertEqual(len(complete), 1)
        self.assertTrue(complete[0]['geometry_loaded'])
        self.assertFalse(complete[0]['full_world_ready'])
        self.assertFalse(complete[0]['battle_ready'])
        self.assertFalse(complete[0]['compatibility_acceptance'])
        self.assertFalse(complete[0]['space_initialized_observed'])
        self.assertEqual(complete[0]['original_callback_ids'], {'onEnterWorld': 11, 'onSpaceLoaded': 12})
        before = (len(self.events), self.native.observations)
        self.assertTrue(scenario.advance(self.record))
        self.assertEqual(before, (len(self.events), self.native.observations))
        self.assertFalse(scenario.note_geometry_mapped(1, 'spaces/01_karelia'))

    def test_space_initialized_is_observed_not_assigned_or_required(self):
        self.arm()
        self.native.value['space_initialized'] = True
        before = copy.deepcopy(self.native.value)
        self.notes()
        self.assertTrue(scenario.advance(self.record))
        self.assertEqual(before, self.native.value)
        self.assertTrue(self.events[-1][1]['space_initialized_observed'])

    def test_load_status_without_original_callbacks_is_insufficient(self):
        self.arm()
        self.assertFalse(scenario.advance(self.record))
        self.assertTrue(scenario.note_geometry_mapped(1, 'spaces/01_karelia'))
        self.pair('onEnterWorld', 11)
        self.assertFalse(scenario.advance(self.record))
        self.pair('onSpaceLoaded', 12)
        self.assertTrue(scenario.advance(self.record))

    def test_space_loaded_callback_before_actual_mapping_does_not_prove_map(self):
        self.arm()
        self.pair('onEnterWorld', 11)
        self.pair('onSpaceLoaded', 12)
        scenario.note_geometry_mapped(1, 'spaces/01_karelia')
        self.assertFalse(scenario.advance(self.record))

    def test_callbacks_from_no_space_do_not_prove_target_space(self):
        self.arm()
        scenario.note_geometry_mapped(1, 'spaces/01_karelia')
        self.pair('onEnterWorld', 11)
        self.pair('onSpaceLoaded', 12, space=None)
        self.assertFalse(scenario.advance(self.record))

    def test_matching_return_requires_entry_and_exact_owner(self):
        self.arm()
        scenario.note_geometry_mapped(1, 'spaces/01_karelia')
        scenario.note_avatar_call('return', 'onEnterWorld', 388, 316, 11, 300, scenario.AVATAR_ID, 1)
        self.assertRaises(RuntimeError, scenario.advance, self.record)
        self.assertEqual(self.events[-1][0], 'arena_space_error')

    def test_callback_owner_must_equal_real_avatar_owner(self):
        self.arm()
        scenario.note_geometry_mapped(1, 'spaces/01_karelia')
        self.pair('onEnterWorld', 11, owner=301)
        self.pair('onSpaceLoaded', 12)
        self.assertRaises(RuntimeError, scenario.advance, self.record)

    def test_abnormal_return_is_queued_without_callback_raise_then_fails(self):
        self.arm()
        self.pair('onEnterWorld', 11, return_offset=309)
        self.assertRaises(RuntimeError, scenario.advance, self.record)
        self.assertFalse(any(event == 'arena_space_complete' for event, _ in self.events))

    def test_wrong_source_line_and_duplicate_call_ids_are_rejected(self):
        self.arm()
        self.pair('onEnterWorld', 11, line=387)
        self.assertRaises(RuntimeError, scenario.advance, self.record)
        other = scenario._Scenario(self.record, NativeControl())
        other.note_avatar('call', 'onEnterWorld', 388, -1, 11, 300, scenario.AVATAR_ID, 1)
        other.note_avatar('call', 'onEnterWorld', 388, -1, 11, 300, scenario.AVATAR_ID, 1)
        self.assertRaises(RuntimeError, other.advance)

    def test_invalid_note_primitives_fail_on_advance_only(self):
        self.arm()
        self.assertFalse(scenario.note_avatar_call('call', 'onEnterWorld', 388, -1, True, 300, scenario.AVATAR_ID, 1))
        self.assertFalse(scenario.note_geometry_mapped(1, 'x' * 129))
        self.assertRaises(RuntimeError, scenario.advance, self.record)

    def test_queue_bound_is_fail_fast_without_raising_into_callback(self):
        self.arm()
        for i in range(scenario.MAX_PENDING_NOTES):
            self.assertTrue(scenario.note_avatar_call('call', 'onEnterWorld', 388, -1, i + 1, 300, scenario.AVATAR_ID, 1))
        self.assertFalse(scenario.note_avatar_call('call', 'onEnterWorld', 388, -1, 1000, 300, scenario.AVATAR_ID, 1))
        self.assertEqual(len(scenario._run.notes), scenario.MAX_PENDING_NOTES)
        self.assertRaises(RuntimeError, scenario.advance, self.record)

    def test_lifetime_note_bound_survives_draining_pending_batches(self):
        self.arm(avatar=False)
        for start in (1, 17):
            for call_id in range(start, start + 16):
                self.pair('onEnterWorld', call_id)
            self.assertFalse(scenario.advance(self.record))
            self.assertEqual(scenario._run.notes, [])
        self.assertEqual(scenario._run.sequence, scenario.MAX_TOTAL_NOTES)
        self.assertFalse(scenario.note_avatar_call('call', 'onEnterWorld', 388, -1,
                                                  33, 300, scenario.AVATAR_ID, 1))
        self.assertEqual(scenario._run.notes, [])
        self.assertRaises(RuntimeError, scenario.advance, self.record)

    def test_wrong_or_duplicate_geometry_mapping_is_rejected(self):
        self.arm()
        scenario.note_geometry_mapped(1, 'spaces/foreign_map')
        self.assertRaises(RuntimeError, scenario.advance, self.record)
        other = scenario._Scenario(self.record, NativeControl())
        other.note_geometry(1, 'spaces/01_karelia')
        other.note_geometry(1, 'spaces/01_karelia')
        self.assertRaises(RuntimeError, other.advance)

    def test_repository_or_connection_change_cannot_complete(self):
        for key, wrong in (('repository_owner_id', 101), ('repository_present', False), ('native_connected', False)):
            native = NativeControl()
            obj = scenario._Scenario(self.record, native)
            native.value = avatar_observation()
            native.value[key] = wrong
            self.assertRaises(RuntimeError, obj.advance)

    def test_unexpected_vehicle_full_ready_or_map_is_explicit_failure(self):
        for key, wrong in (('vehicle_present', True), ('steps_till_init', 0), ('user_sees_world', True),
                           ('entity_id', scenario.AVATAR_ID + 1), ('name', 'other'),
                           ('space_id', 2), ('player_vehicle_id', scenario.VEHICLE_ID + 1),
                           ('arena_type_id', 2), ('geometry_path', 'spaces/other')):
            native = NativeControl()
            obj = scenario._Scenario(self.record, native)
            native.value = avatar_observation()
            native.value[key] = wrong
            self.assertRaises(RuntimeError, obj.advance)

    def test_each_real_space_readiness_field_is_required(self):
        for key, wrong in (('space_id', None), ('in_world', False), ('arena_present', False),
                           ('space_load_progress', 0.999), ('position', None),
                           ('player_vehicle_id', 0), ('steps_till_init', None), ('user_sees_world', None)):
            native = NativeControl()
            obj = scenario._Scenario(self.record, native)
            native.value = avatar_observation()
            native.value[key] = wrong
            obj.note_geometry(1, 'spaces/01_karelia')
            for method, number in (('onEnterWorld', 11), ('onSpaceLoaded', 12)):
                line, offset = scenario.CALLBACKS[method]
                obj.note_avatar('call', method, line, -1, number, 300, scenario.AVATAR_ID, 1)
                obj.note_avatar('return', method, line, offset, number, 300, scenario.AVATAR_ID, 1)
            self.assertFalse(obj.advance())

    def test_observation_budget_is_total240_and_never_becomes_success(self):
        self.arm(avatar=False)
        for unused in range(scenario.MAX_ADVANCES):
            self.assertFalse(scenario.advance(self.record))
        self.assertEqual(self.native.observations, 239)
        self.assertRaises(RuntimeError, scenario.advance, self.record)
        self.assertEqual(self.native.observations, 239)
        self.assertFalse(any(event == 'arena_space_complete' for event, _ in self.events))

    def test_native_reader_exception_is_recorded_and_propagated(self):
        self.arm()
        self.native.observe_error = True
        self.assertRaises(RuntimeError, scenario.advance, self.record)
        self.assertFalse(scenario._run.active)
        self.assertEqual(self.events[-1][0], 'arena_space_error')

    def test_cleanup_attempts_all_phases_even_when_two_fail(self):
        self.arm()
        self.cleanup_fails.update(('before', 'native'))
        self.assertRaises(RuntimeError, scenario.fini, self.record, self.native_cleanup)
        self.assertEqual(self.cleanup_calls, ['before', 'native', 'after'])
        self.assertEqual([r['outcome'] for e, r in self.events if e == 'arena_space_cleanup'], ['FAIL', 'FAIL', 'PASS'])
        self.assertFalse(scenario.note_geometry_mapped(1, 'spaces/01_karelia'))
        self.assertRaises(RuntimeError, scenario.fini, self.record, self.native_cleanup)
        self.assertEqual(self.cleanup_calls, ['before', 'native', 'after'])

    def test_cleanup_recording_failure_does_not_skip_native_cleanup(self):
        def failing_record(event, **data):
            if event == 'arena_space_cleanup' and data['stage'] == 'before_entities':
                raise IOError('synthetic recording failure')
            self.record(event, **data)
        self.assertRaises(RuntimeError, scenario.fini, failing_record, self.native_cleanup)
        self.assertEqual(self.cleanup_calls, ['before', 'native', 'after'])
        self.assertTrue(any('record:OSError' in s or 'record:IOError' in s for s in scenario._cleanup_errors))

    def test_cleanup_is_idempotent_and_works_before_arm(self):
        scenario.fini(self.record, self.native_cleanup)
        scenario.fini(self.record, self.native_cleanup)
        self.assertEqual(self.cleanup_calls, ['before', 'native', 'after'])
        self.assertFalse(scenario.advance(self.record))

    def test_original_game_binding_gate_rejects_synthetic_functions_before_init(self):
        old = sys.modules.get('game')
        module = types.ModuleType('game')
        module.onGeometryMapped = lambda space_id, path: None
        module.onChangeEnvironments = lambda inside: None
        sys.modules['game'] = module
        try:
            native = self.saved['_Native'](self.record)
            self.assertRaises(ValueError, native.initialize)
        finally:
            if old is None:
                sys.modules.pop('game', None)
            else:
                sys.modules['game'] = old

    def test_all_success_records_are_bounded_primitive_data(self):
        self.arm()
        self.notes()
        self.assertTrue(scenario.advance(self.record))
        scenario.fini(self.record, self.native_cleanup)
        for unused, row in self.events:
            self.assertLessEqual(len(json.dumps(row, ensure_ascii=True).encode('ascii')), 8192)
            self.assertNotIn('password', row)


if __name__ == '__main__':
    unittest.main()
