# -*- coding: utf-8 -*-
"""Synthetic rejection controls only; no test here proves native movement."""
import copy
import hashlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import arena_movement_scenario as movement
import test_arena_vehicle_scenario as world


class NativeControl(world.NativeControl):
    def __init__(self):
        world.NativeControl.__init__(self)
        self.movement_sources, self.commands, self.requested, self.cleanup = [], [], [], []
        self.at, self.call_id = 1.0, 100
        self.position = list(movement.ORIGIN)
        self.overrides, self.move_fail = {}, set()
        self.omit_notes = self.early_return = self.png_missing = False
        self.vehicle_value['roster']['avatar_ready'] = True

    def motion(self):
        value = dict(present=True, owner_id=300, vehicle_owner_id=400, period=3,
            period_end_time=160.0, period_length=60.0, additional_info_is_none=True,
            server_time=100.0+self.at, native_time=self.at, is_on_arena=True,
            gun_rotator_started=False, cruise_mode=0, entity_position=list(self.position),
            entity_matrix_position=list(self.position), model_matrix_position=list(self.position),
            own_matrix_position=list(self.position), speed_info=[0.0]*4,
            left_contacts=0, right_contacts=0,
            native_received_filter_input='UNKNOWN', native_controlled_property='UNKNOWN')
        value.update(self.overrides)
        return value

    def move(self, flags, is_key_down, owner):
        self.commands.append((flags, is_key_down, owner))
        if flags in self.move_fail:
            raise RuntimeError('synthetic original command failure')
        if not self.omit_notes:
            self.call_id += 1
            data = dict(flags=flags, is_key_down=is_key_down)
            movement.note_movement_call('call', 'moveVehicle', 2130, -1, self.call_id, owner, data)
            movement.note_movement_call('return', 'moveVehicle', 2130,
                                       12 if self.early_return else 345, self.call_id, owner, data)

    def request(self, basename):
        if self.capture_fail:
            raise RuntimeError('synthetic screenshot writer failure')
        self.requested.append(basename)

    def screenshot(self, basename):
        if self.png_missing:
            return None
        data = dict(self.png)
        data['basename'] = basename
        return data

    def light_fini(self):
        self.cleanup.append('light')


class MovementTests(unittest.TestCase):
    def setUp(self):
        keys = ('_run', '_native', '_arm_attempted', '_closing', '_finished_cleanup', '_cleanup_errors', '_Native')
        self.saved = dict((key, getattr(movement, key)) for key in keys)
        movement._run = movement._native = None
        movement._arm_attempted = movement._closing = movement._finished_cleanup = False
        movement._cleanup_errors = []
        self.native, self.events, self.at = NativeControl(), [], 1.0
        self.record = lambda name, **data: self.events.append((name, data))
        movement._Native = lambda record, settings: self.native
        self.cleanup, self.cleanup_fail = [], set()
        self.old_cleanup = (movement.arena_bootstrap.fini_before_entities,
                            movement.arena_bootstrap.fini_after_entities)
        movement.arena_bootstrap.fini_before_entities = self.stage('before')
        movement.arena_bootstrap.fini_after_entities = self.stage('after')

    def tearDown(self):
        for key, value in self.saved.items():
            setattr(movement, key, value)
        movement.arena_bootstrap.fini_before_entities, movement.arena_bootstrap.fini_after_entities = self.old_cleanup

    def stage(self, name):
        def call():
            self.cleanup.append(name)
            if name in self.cleanup_fail:
                raise ValueError(name)
        return call

    def arm(self):
        movement.arm(self.record, {})
        movement._run.clock = lambda: self.at
        self.native.value = world.avatar()

    def entities(self):
        def pair(kind, method, identity, result=None):
            line, returns = movement.vehicle.CALLBACKS[kind][method]
            fun = movement.note_avatar_call if kind == 'avatar' else movement.note_vehicle_call
            owner = 300 if kind == 'avatar' else 400
            entity = movement.vehicle.AVATAR_ID if kind == 'avatar' else movement.vehicle.VEHICLE_ID
            fun('call', method, line, -1, identity, owner, entity, 1)
            fun('return', method, line, returns[-1] if result is None else result, identity, owner, entity, 1)
        pair('avatar', 'onEnterWorld', 1)
        pair('avatar', '__onInitStepCompleted', 2, 101)
        pair('avatar', '__onInitStepCompleted', 3, 101)
        movement.note_geometry_mapped(1, 'spaces/01_karelia')
        pair('avatar', 'onSpaceLoaded', 4)
        pair('avatar', '__onInitStepCompleted', 5, 101)
        pair('vehicle', '__init__', 6)
        pair('vehicle', 'prerequisites', 7)
        pair('vehicle', 'onEnterWorld', 8)
        pair('vehicle', 'startVisual', 9)
        pair('avatar', '__onInitStepCompleted', 10, 640)

    def tick(self):
        self.native.at = self.at
        result = movement.advance(self.record)
        self.at += 1.0
        return result

    def begin(self):
        self.arm(); self.entities()
        self.assertFalse(self.tick()); self.assertFalse(self.tick()); self.assertFalse(self.tick())
        self.assertEqual(self.native.requested, [movement.SCREENSHOTS[0]])
        self.assertFalse(self.tick())
        self.assertEqual(self.native.commands, [(1, True, 300)])

    def target(self):
        self.native.position = list(movement.TARGET)
        self.assertFalse(self.tick())
        self.assertEqual(self.native.commands, [(1, True, 300), (0, False, 300)])

    def test_normal_unarmed_is_passive(self):
        self.assertFalse(movement.advance(self.record))
        self.assertFalse(movement.note_movement_call(None, [], None, None, None, None, object()))
        self.assertFalse(movement.note_avatar_call(None, [], None, None, None, None, None, None))
        self.assertEqual(self.events, [])

    def test_complete_requires_both_commands_hold_and_actual_png_receipts(self):
        self.begin(); self.target()
        self.assertFalse(self.tick()); self.assertFalse(self.tick())
        self.assertTrue(self.tick())
        event, row = self.events[-1]
        self.assertEqual(event, 'arena_movement_complete')
        self.assertGreaterEqual(row['hold_seconds'], 2.0)
        self.assertEqual(row['screenshots'], 2)
        self.assertFalse(row['compatibility_acceptance'])
        self.assertEqual(row['server_authority_acceptance'], 'NOT_RUN')
        self.assertEqual(self.native.requested, list(movement.SCREENSHOTS))
        self.assertTrue(self.tick())
        self.assertEqual(len(self.native.commands), 2)

    def test_foreign_account_rejected_before_initialization(self):
        self.native.identity['database_id'] = 2
        self.assertRaises(RuntimeError, self.arm)
        self.assertEqual(self.native.initialized, 0)

    def test_arm_is_one_shot(self):
        self.arm()
        self.assertRaises(RuntimeError, movement.arm, self.record, {})

    def test_original_initial_zero_is_recorded_separately(self):
        self.arm(); self.entities()
        data = {'flags': 0, 'is_key_down': False}
        movement.note_movement_call('call', 'moveVehicle', 2130, -1, 99, 300, data)
        movement.note_movement_call('return', 'moveVehicle', 2130, 345, 99, 300, data)
        self.assertFalse(self.tick())
        self.assertIsNone(movement._run.movement_pairs[0]['entry']['intent'])
        self.assertEqual(self.native.commands, [])

    def test_actual_startup_early_zero_then_rpc_zero_are_only_observations(self):
        self.arm(); self.entities()
        data = {'flags': 0, 'is_key_down': False}
        for cid, offset in ((79, 12), (80, 345)):
            self.assertTrue(movement.note_movement_call('call', 'moveVehicle', 2130, -1, cid, 300, data))
            self.assertTrue(movement.note_movement_call('return', 'moveVehicle', 2130, offset, cid, 300, data))
        self.assertFalse(self.tick())
        pairs = movement._run.movement_pairs
        self.assertEqual([p['returned']['offset'] for p in pairs], [12, 345])
        self.assertTrue(all(p['entry']['intent'] is None for p in pairs))
        self.assertIsNone(movement._run.forward_pair)
        self.assertIsNone(movement._run.stop_pair)
        self.assertEqual(self.native.commands, [])
        self.assertFalse(movement._run.complete)

    def test_automatic_early_return_with_nonzero_input_is_still_rejected(self):
        self.arm(); self.entities()
        data = {'flags': 1, 'is_key_down': True}
        movement.note_movement_call('call', 'moveVehicle', 2130, -1, 79, 300, data)
        movement.note_movement_call('return', 'moveVehicle', 2130, 12, 79, 300, data)
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(self.native.commands, [])
        self.assertFalse(movement._run.complete)

    def test_prebattle_does_not_inherit_baseline_duration(self):
        self.arm(); self.entities(); self.native.overrides['period'] = 2
        for _ in range(5): self.assertFalse(self.tick())
        self.assertEqual(self.native.commands, [])
        self.native.overrides['period'] = 3
        self.assertFalse(self.tick()); self.assertFalse(self.tick())
        self.assertEqual(self.native.requested, [])
        self.assertFalse(self.tick())
        self.assertEqual(len(self.native.requested), 1)

    def test_lost_onarena_flag_rejected(self):
        self.arm(); self.entities(); self.native.overrides['is_on_arena'] = False
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(self.native.commands, [])

    def test_cruise_input_not_overridden(self):
        self.arm(); self.entities(); self.native.overrides['cruise_mode'] = 1
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(self.native.commands, [])

    def test_foreign_period_deadline_rejected(self):
        self.arm(); self.entities(); self.native.overrides['period_end_time'] = 161.0
        self.assertRaises(RuntimeError, self.tick)

    def test_lost_roster_ready_rejected(self):
        self.arm(); self.entities(); self.native.vehicle_value['roster']['avatar_ready'] = False
        self.assertRaises(RuntimeError, self.tick)

    def test_readiness_requires_four_original_steps(self):
        self.arm()
        self.assertFalse(self.tick())
        self.assertEqual(self.native.commands, [])

    def test_motion_before_explicit_command_fails(self):
        self.arm(); self.entities(); self.native.position[2] += 0.1
        self.assertRaises(RuntimeError, self.tick)

    def test_just_local_model_motion_does_not_satisfy_target(self):
        self.begin(); self.native.overrides['model_matrix_position'] = list(movement.TARGET)
        self.assertFalse(self.tick())
        self.assertEqual(len(self.native.commands), 1)

    def test_output_y_not_forged_or_required_equal_wire(self):
        self.begin(); self.native.position = list(movement.TARGET); self.native.position[1] -= 0.07084
        self.assertFalse(self.tick())
        self.assertTrue(movement._run.stop_attempted)
        row = [data for name,data in self.events if name == 'arena_movement_state'][-1]
        self.assertEqual(row['motion']['entity_position'][1], self.native.position[1])

    def test_nan_pose_rejected_and_stop_attempted(self):
        self.begin(); self.native.position[0] = float('nan')
        self.assertRaises(ValueError, self.tick)
        self.assertEqual(self.native.commands[-1], (0, False, 300))

    def test_outside_path_rejected_and_stop_attempted(self):
        self.begin(); self.native.position[0] += 0.1
        self.assertRaises(RuntimeError, self.tick)
        self.assertTrue(movement._run.stop_attempted)

    def test_pose_cannot_revert_while_final_png_arrives(self):
        self.begin(); self.target(); self.tick(); self.tick()
        self.native.position = list(movement.ORIGIN)
        self.assertRaises(RuntimeError, self.tick)
        self.assertFalse(movement._run.complete)

    def test_target_cap_does_not_replace_original_stop(self):
        self.begin(); self.native.move_fail.add(0); self.native.position = list(movement.TARGET)
        self.assertRaises(RuntimeError, self.tick)
        self.assertFalse(movement._run.complete)
        self.assertEqual(len(self.native.commands), 2)

    def test_deadline_failure_stops_without_completing(self):
        self.begin()
        for _ in range(7): self.assertFalse(self.tick())
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(self.native.commands[-1], (0, False, 300))
        self.assertFalse(movement._run.complete)

    def test_gap_failure_stops_without_hiding_initial_error(self):
        self.begin(); self.at += 4
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(self.native.commands[-1], (0, False, 300))

    def test_world_loss_after_press_requests_one_stop(self):
        self.begin(); self.native.value['user_sees_world'] = False
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(self.native.commands[-1], (0, False, 300))
        movement.fini(self.record, self.stage('native'))
        self.assertEqual(len(self.native.commands), 2)

    def test_missing_passive_callback_rejects_successful_wrapper_return(self):
        self.arm(); self.entities(); self.native.omit_notes = True
        self.tick(); self.tick(); self.tick()
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(len(self.native.commands), 2)
        self.assertFalse(movement._run.complete)

    def test_original_early_return_is_not_transport_proof(self):
        self.arm(); self.entities(); self.native.early_return = True
        self.tick(); self.tick(); self.tick()
        self.assertRaises(RuntimeError, self.tick)
        self.assertFalse(movement._run.complete)

    def test_explicit_stop_early_return_is_not_transport_proof(self):
        self.begin()
        self.native.position = list(movement.TARGET)
        self.native.early_return = True
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(self.native.commands, [(1, True, 300), (0, False, 300)])
        self.assertIsNotNone(movement._run.forward_pair)
        self.assertIsNone(movement._run.stop_pair)
        self.assertFalse(movement._run.complete)

    def test_invalid_note_never_raises_in_profiler(self):
        self.arm(); self.entities()
        self.assertFalse(movement.note_movement_call('call','moveVehicle',2130.0,-1,12,300,{'flags':1,'is_key_down':True}))
        self.assertRaises(RuntimeError, self.tick)

    def test_callback_argument_aliasing_does_not_change_copy(self):
        self.arm(); self.entities(); data={'flags':0,'is_key_down':False}
        self.assertTrue(movement.note_movement_call('call','moveVehicle',2130,-1,99,300,data))
        data['flags']=1
        self.assertEqual(movement._run.movement_notes[0]['data']['flags'], 0)

    def test_unexpected_manual_command_rejected(self):
        self.arm(); self.entities(); data={'flags':2,'is_key_down':True}
        movement.note_movement_call('call','moveVehicle',2130,-1,99,300,data)
        movement.note_movement_call('return','moveVehicle',2130,345,99,300,data)
        self.assertRaises(RuntimeError,self.tick)

    def test_note_budget_is_hard_and_passive(self):
        self.arm(); self.entities()
        for i in range(movement.MAX_MOVEMENT_PENDING):
            self.assertTrue(movement.note_movement_call('call','moveVehicle',2130,-1,100+i,300,{'flags':0,'is_key_down':False}))
        self.assertFalse(movement.note_movement_call('call','moveVehicle',2130,-1,900,300,{'flags':0,'is_key_down':False}))
        self.assertRaises(RuntimeError,self.tick)

    def test_png_failure_before_start_sends_nothing(self):
        self.arm(); self.entities(); self.native.capture_fail = True
        self.tick(); self.tick()
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands, [])

    def test_png_missing_never_becomes_success(self):
        self.arm(); self.entities(); self.native.png_missing = True
        self.tick(); self.tick(); self.tick()
        for _ in range(movement.MAX_PNG_ADVANCES-1):self.assertFalse(self.tick())
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands, [])

    def test_success_cleanup_order_and_idempotence(self):
        self.begin(); self.target(); self.tick(); self.tick(); self.tick()
        movement.fini(self.record,self.stage('native'))
        movement.fini(self.record,self.stage('native'))
        self.assertEqual(self.cleanup, ['before','native','after'])
        self.assertEqual(self.native.cleanup, ['light'])
        self.assertEqual(len(self.native.commands), 2)

    def test_cleanup_failure_still_tries_all_stages(self):
        self.arm(); self.cleanup_fail.add('before')
        self.assertRaises(RuntimeError,movement.fini,self.record,self.stage('native'))
        self.assertEqual(self.cleanup, ['before','native','after'])
        self.assertEqual(self.native.cleanup, ['light'])

    def test_external_native_close_sends_stop_but_does_not_claim_completion(self):
        self.begin(); movement.fini(self.record,self.stage('native'))
        self.assertEqual(self.native.commands[-1], (0,False,300))
        self.assertFalse(movement._run.complete)


class SourceContracts(unittest.TestCase):
    @unittest.skipIf(sys.version_info[0] < 3, 'host static decoder verified separately under Python3')
    def test_original_sources_and_real_method_are_pinned(self):
        sys.path.insert(0,os.path.join(ROOT,'tools'))
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,text
        original=config()[1]['original_client_root']
        found=None
        for relative,digest in movement.SOURCE_HASHES:
            raw=read_limited(original/relative,1048576)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            if relative.endswith('/Avatar.pyc'):
                found=next(code for name,code in records(parse_pyc(raw)) if name.endswith('.moveVehicle'))
        self.assertEqual(found['firstlineno'],2130)
        self.assertEqual(found['argcount'],3)
        self.assertEqual(text(found['varnames'])[:3],['self','flags','isKeyDown'])
        self.assertEqual(hashlib.sha256(found['code']).hexdigest(),movement.MOVE_METHOD[-1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
