# -*- coding: utf-8 -*-
"""Synthetic phase/boundary controls and original-source reads, not a native run."""
import copy
import hashlib
import json
import math
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import map_drive_acceptance as A
import test_arena_vehicle_scenario as V
from test_account_switch_scenario import expected


class NativeControl(object):
    def __init__(self):
        self.value, self.item = V.account(), V.vehicle()
        self.item['roster']['avatar_ready'] = True
        self.public = expected()[0]
        self.public['name'] = self.value['name']
        self.public['vehicles'][0]['compact_descr_sha256'] = 'a' * 64
        self.account_value = dict(account=self.public, selected_inventory_id=1,
                                 ammo={'raw_shells': [2570, 20, 2826, 0, 3082, 0]},
                                 repository_owner_id=100, player_owner_id=200,
                                 entity_id=1, hangar_owner_id=900, crew_owner_id=901)
        self.position, self.heading, self.speed = [0.0, 20.0, 0.0], 0.0, 0.0
        self.actions, self.requests, self.grounds = [], [], []
        self.cid, self.map_id = 1000, 1
        self.auto_png, self.omit_action, self.early = True, False, False
        self.ready, self.target, self.foreign_binding = True, True, False
        self.motion_changes, self.binding_changes = {}, {}
        self.fail_action = None
        self.scheduled, self.cancelled, self.sample_reads = {}, [], 0
        self.captcha = dict(battles_till_captcha=1, captcha_required=False,
                            controller_owner_id=600, stats_owner_id=601, guard_blocked_calls=0)

    def initialize(self):
        return []

    def context(self):
        return copy.deepcopy(self.value)

    def hangar_ready(self):
        return self.ready and self.value['player_is_original_account']

    def account(self):
        return copy.deepcopy(self.account_value)

    def select_ms1(self):
        self.actions.append('select_ms1')
        self.account_value['selected_inventory_id'] = 1

    def button_state(self):
        return dict(owner_id=500, enabled=True, flash_bound=True, map_id=0, action_name='')

    def captcha_state(self):
        return dict(self.captcha)

    def pair(self, fun, method, line, owner, data, result):
        self.cid += 1
        fun('call', method, line, -1, self.cid, owner, copy.deepcopy(data))
        fun('return', method, line, result, self.cid, owner, copy.deepcopy(data))

    def fight(self, owner):
        self.actions.append('fight')
        if not self.omit_action:
            self.pair(A.note_action_call, 'fightClick', 196, owner, {'mapID': 0, 'actionName': ''}, 65)

    def world(self):
        return copy.deepcopy(self.item)

    def motion(self):
        row = dict(present=True, owner_id=300, vehicle_owner_id=400, period=3,
                   period_end_time=160.0, period_length=60.0, server_time=110.0,
                   is_on_arena=True, own_matrix_position=list(self.position),
                   entity_position=list(self.position), entity_matrix_position=list(self.position),
                   model_matrix_position=list(self.position), speed_info=[self.speed, 0.0, 0.0, 0.0],
                   forward_axis=[math.sin(self.heading), 0.0, math.cos(self.heading)], heading=self.heading)
        row.update(self.motion_changes)
        return row

    def binding(self):
        row = dict(present=True, owner_id=300, vehicle_owner_id=400,
                   attached_is_own_vehicle=True, attached_vehicle_id=A.vehicle.VEHICLE_ID,
                   attached_owner_id=400, filter_is_original_wg_vehicle=True,
                   target_present=self.target, target_python_identity_equal=False,
                   own_matrix_position=list(self.position), body_matrix_position=list(self.position),
                   target_position=list(self.position))
        row.update(self.binding_changes)
        return row

    def ground(self, map_id, context):
        self.grounds.append(map_id)
        return dict(map_id=map_id, geometry=A.MAPS[map_id], space_id=1,
                    player_owner_id=300, samples=[], source_sample_plan_sha256=A.RAY_PLANS[map_id][0])

    def sample(self, owner, vehicle_owner, space_id):
        self.sample_reads += 1
        pose = dict(position=list(self.position), forward=[0.0, 0.0, 1.0])
        return dict(player_owner_id=owner, vehicle_owner_id=vehicle_owner, space_id=space_id,
                    target_present=self.target, own=copy.deepcopy(pose), body=copy.deepcopy(pose),
                    camera=copy.deepcopy(pose), speed_info=[self.speed, 0.0, 0.0, 0.0],
                    last_server_speeds=[0.0, 0.0])

    def schedule_sample(self, delay, callback):
        self.cid += 1
        self.scheduled[self.cid] = (delay, callback)
        return self.cid

    def cancel_sample(self, callback_id):
        self.cancelled.append(callback_id)
        del self.scheduled[callback_id]

    def move(self, flags, down, owner):
        self.actions.append((flags, down))
        if self.fail_action == flags:
            raise RuntimeError('synthetic original movement failure')
        if not self.omit_action:
            self.pair(A.note_movement_call, 'moveVehicle', 2130, owner,
                      dict(flags=flags, is_key_down=down), 12 if self.early else 345)

    def leave(self, owner):
        self.actions.append('leave')
        if not self.omit_action:
            self.pair(A.note_action_call, 'leaveArena', 2310, owner, {}, 178)

    def request(self, name):
        if name in self.requests:
            raise RuntimeError('synthetic duplicate screenshot')
        self.requests.append(name)

    def screenshot(self, name):
        if not self.auto_png:
            return None
        return dict(basename=name, path='synthetic-only-' + name + '.png', sha256='f' * 64,
                    png_container_valid=True, native_pixels_review='NOT_RUN')


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict((k, getattr(A, k)) for k in ('_run', '_attempted', '_closing', '_Native'))
        A._run, A._attempted, A._closing = None, False, False
        self.native, self.events, self.at = NativeControl(), [], 1.0
        self.record = lambda event, **row: self.events.append((event, row))
        A._Native = lambda settings: self.native
        self.frozen = (A.binding._run, A.movement._run, A.vehicle._run)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(A, k, v)
        self.assertEqual(self.frozen, (A.binding._run, A.movement._run, A.vehicle._run))

    def arm(self):
        A.arm(self.record, {})
        A._run.clock = lambda: self.at

    def tick(self):
        result = A.advance(self.record)
        self.at += 1.0
        return result

    def entity(self, kind, method, result=None, owner=None):
        self.native.cid += 1
        line, returns = A.ENTITY_METHODS[kind][method]
        fun = A.note_avatar_call if kind == 'avatar' else A.note_vehicle_call
        owner = (300 if kind == 'avatar' else 400) if owner is None else owner
        eid = A.vehicle.AVATAR_ID if kind == 'avatar' else A.vehicle.VEHICLE_ID
        fun('call', method, line, -1, self.native.cid, owner, eid, 1)
        fun('return', method, line, returns[-1] if result is None else result, self.native.cid, owner, eid, 1)

    def binding(self):
        self.native.pair(A.note_map_drive_call, 'updateOwnVehiclePosition', 1445, 300,
                         dict(position=list(self.native.position), direction=[0.0] * 3, speed=0.0, rspeed=0.0), 198)
        self.native.pair(A.note_map_drive_call, '__setOwnVehicleMatrixCallback', 2951, 300, {}, 151)

    def enter_world(self, map_id=4):
        self.native.value = V.avatar()
        self.native.value.update(arena_type_id=map_id, geometry_name=A.MAPS[map_id], geometry_path='spaces/' + A.MAPS[map_id])
        self.entity('avatar', '__init__')
        self.entity('avatar', 'onBecomePlayer')
        self.entity('avatar', 'onEnterWorld')
        A.note_geometry_mapped(1, 'spaces/' + A.MAPS[map_id])
        self.entity('avatar', 'onSpaceLoaded')
        self.entity('avatar', '__onInitStepCompleted', 101)
        self.entity('avatar', '__onInitStepCompleted', 101)
        self.entity('avatar', '__onInitStepCompleted', 101)
        self.entity('vehicle', '__init__')
        self.entity('vehicle', 'prerequisites')
        self.entity('vehicle', 'onEnterWorld')
        self.entity('vehicle', 'startVisual')
        self.entity('avatar', '__onInitStepCompleted', 640)
        self.binding()

    def to_forward(self, map_id=4):
        self.arm()
        self.tick()
        self.enter_world(map_id)
        for _ in range(6):
            self.tick()
        self.assertEqual(A._run.phase, 'forward')

    def to_leave(self):
        self.to_forward()
        self.native.position[2] = 3.1
        self.binding(); self.tick()
        self.native.heading = 0.2
        for _ in range(5): self.tick()
        self.assertEqual(A._run.phase, 'reverse')
        self.native.position[0] -= math.sin(0.2) * 2.1
        self.native.position[2] -= math.cos(0.2) * 2.1
        self.binding()
        for _ in range(6): self.tick()
        self.assertEqual(A._run.phase, 'waiting_return')

    def return_account(self):
        for kind, method in (('vehicle', 'stopVisual'), ('vehicle', 'onLeaveWorld'),
                             ('avatar', 'onLeaveWorld'), ('avatar', 'onBecomeNonPlayer')):
            self.entity(kind, method)
        self.native.value = V.account()
        # Address reuse is legitimate; no pointer-inequality assertion.
        self.native.account_value['player_owner_id'] = 200

    def test_complete_original_actions_and_exact_warm_return(self):
        self.to_leave()
        self.return_account()
        for _ in range(5):
            complete = self.tick()
        self.assertFalse(complete)  # One ride cannot close both-map phase2.
        self.assertEqual(A._run.phase, 'between_rides')
        self.assertEqual(self.native.actions, ['fight', (1, True), (9, True), (0, False), (2, True), (0, False), 'leave'])
        self.assertEqual(self.native.requests, list(A.SCREENSHOTS[:3]))
        self.assertEqual(self.native.grounds, [4])
        rows = [r for e, r in self.events if e == 'map_drive_acceptance_callback']
        self.assertIn('call', [r['phase'] for r in rows])
        self.assertIn('return', [r['phase'] for r in rows])
        end = self.events[-1][1]
        self.assertEqual(end['completed_rides'], 1)
        self.assertEqual(end['random_maps_seen'], [4])
        self.assertTrue(end['account_invariant'])
        self.assertFalse(A._run.complete)

    def test_original_return_hangar_geometry_after_pending_teardown(self):
        self.to_leave()
        arena_geometry = copy.deepcopy(A._run.geometry)
        self.return_account()
        self.assertTrue(A.note_geometry_mapped(2147483649, 'spaces/hangar_v2'))
        self.assertIsNone(A._run.return_geometry)  # No callback-side acceptance.
        self.assertEqual(A._run.geometry, arena_geometry)
        for _ in range(5):
            complete = self.tick()
        self.assertFalse(complete)  # One ride cannot close both-map phase2.
        self.assertEqual(A._run.phase, 'between_rides')
        rows = [r for e, r in self.events if e == 'map_drive_acceptance_return_geometry']
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['hangar_ready_proven'])
        self.assertEqual(len(rows[0]['teardown_call_ids']), 4)
        self.assertEqual(A._run.geometry, arena_geometry)

    def test_hangar_geometry_rejects_before_leave_and_unknown_path(self):
        self.to_forward()
        self.assertFalse(A.note_geometry_mapped(2147483649, 'spaces/hangar_v2'))
        with self.assertRaises(RuntimeError): self.tick()

    def test_return_hangar_geometry_requires_preceding_teardown(self):
        self.to_leave()
        self.assertTrue(A.note_geometry_mapped(2147483649, 'spaces/hangar_v2'))
        self.return_account()  # Later callbacks cannot repair an early mapping.
        with self.assertRaises(RuntimeError): self.tick()

    def test_return_hangar_geometry_requires_same_owner_teardown(self):
        self.to_leave()
        self.return_account()
        for row in A._run.notes:
            if row['kind'] == 'avatar' and row['method'] == 'onLeaveWorld':
                row['owner_id'] = 999
        self.assertTrue(A.note_geometry_mapped(2147483649, 'spaces/hangar_v2'))
        with self.assertRaises(RuntimeError): self.tick()

    def test_return_hangar_geometry_rejects_duplicate_and_preserves_first_error(self):
        self.to_leave(); self.return_account()
        self.assertTrue(A.note_geometry_mapped(2147483649, 'spaces/hangar_v2'))
        self.assertFalse(A.note_geometry_mapped(2147483650, 'spaces/hangar_v2'))
        error = A._run.note_error
        self.assertFalse(A.note_geometry_mapped(1, 'spaces/01_karelia'))
        self.assertEqual(A._run.note_error, error)
        with self.assertRaises(RuntimeError): self.tick()

    def test_return_hangar_geometry_rejects_unknown_or_arena_space_reuse(self):
        self.to_leave(); self.return_account()
        for space, path in ((1, 'spaces/hangar_v2'), (2147483649, 'spaces/hangar_premium'),
                            (2147483649, 'spaces/other'), (True, 'spaces/hangar_v2')):
            A._run.note_error = None
            self.assertFalse(A.note_geometry_mapped(space, path))
            self.assertIsNotNone(A._run.note_error)

    def test_return_geometry_is_not_hangar_readiness_or_account_invariant(self):
        self.to_leave(); self.return_account()
        self.native.ready = False
        self.assertTrue(A.note_geometry_mapped(2147483649, 'spaces/hangar_v2'))
        self.assertFalse(self.tick())
        self.assertEqual(A._run.phase, 'waiting_return')
        self.native.ready = True
        self.native.account_value['ammo']['raw_shells'][1] = 19
        with self.assertRaises(RuntimeError): self.tick()

    def test_prohorovka_chosen_by_server_not_client(self):
        self.to_forward(4)
        self.assertEqual(self.native.grounds, [4])
        self.assertEqual(A._run.map_id, 4)

    def test_initial_is7_selects_once_through_original_carousel(self):
        self.native.account_value['selected_inventory_id'] = 2
        self.arm()
        self.tick()
        self.assertEqual(self.native.actions, ['select_ms1'])
        self.tick()
        self.assertEqual(self.native.actions, ['select_ms1', 'fight'])

    def test_normal_unarmed_passive(self):
        self.assertFalse(A.advance(self.record))
        self.assertFalse(A.note_geometry_mapped(1, 'spaces/01_karelia'))
        self.assertFalse(A.note_movement_call('call', 'moveVehicle', 2130, -1, 1, 1, {}))
        self.assertEqual(self.events, [])

    def test_missing_original_button_callback_rejects(self):
        self.native.omit_action = True
        self.arm()
        with self.assertRaises(RuntimeError): self.tick()

    def test_random_button_proof_requires_exact_integer_zero(self):
        self.arm(); self.tick()
        proof = A._run.proofs['fight']
        self.assertEqual(proof['entry']['data'], {'mapID': 0, 'actionName': ''})
        self.assertEqual(proof['returned']['data'], proof['entry']['data'])
        self.assertEqual(type(proof['entry']['data']['mapID']), int)
        for value in (None, False, 0.0, '', '0', 1, -1):
            A._run.note_error = None
            self.assertFalse(A.note_action_call('call', 'fightClick', 196, -1,
                                               10000, 500, {'mapID': value, 'actionName': ''}))
            self.assertIsNotNone(A._run.note_error)

    def test_account_stall_fails_at_thirty_seconds_without_repeat_button(self):
        self.arm(); self.tick()
        returned_at = A._run.fight_at
        self.at = returned_at + A.MAX_PREQUEUE_ACCOUNT_SECONDS - 0.01
        self.assertFalse(self.tick())
        self.at = returned_at + A.MAX_PREQUEUE_ACCOUNT_SECONDS
        with self.assertRaises(RuntimeError): self.tick()
        self.assertEqual(self.native.actions, ['fight'])
        self.assertFalse(A._run.complete)
        self.assertIn('thirty seconds', self.events[-1][1]['detail'])

    def test_avatar_loading_is_not_subject_to_account_stall_deadline(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.value['space_load_progress'] = 0.5
        self.at = A._run.fight_at + A.MAX_PREQUEUE_ACCOUNT_SECONDS + 10.0
        self.assertFalse(self.tick())
        self.assertEqual(A._run.phase, 'waiting_world')
        self.assertEqual(self.native.actions, ['fight'])

    def test_reset_gap_has_no_account_stall_claim(self):
        self.arm(); self.tick()
        self.native.value.update(player_is_original_account=False, player_present=False)
        self.at = A._run.fight_at + A.MAX_PREQUEUE_ACCOUNT_SECONDS + 10.0
        self.assertFalse(self.tick())
        self.assertFalse(A._run.complete)

    def test_waiting_account_never_calls_avatar_only_getters(self):
        self.arm(); self.tick()
        def forbidden():
            raise AssertionError('Avatar-only getter called while Account remains native player')
        self.native.world = self.native.motion = self.native.binding = forbidden
        for _ in range(3): self.assertFalse(self.tick())
        self.assertEqual(A._run.phase, 'waiting_world')
        self.assertTrue(any(e == 'map_drive_acceptance_waiting_world' and r['avatar_getters'] == 'NOT_RUN'
                            for e, r in self.events))

    def test_waiting_reset_without_player_never_calls_avatar_only_getters(self):
        self.arm(); self.tick()
        self.native.value.update(player_is_original_account=False, player_present=False)
        def forbidden():
            raise AssertionError('Avatar-only getter called during actual reset gap')
        self.native.world = self.native.motion = self.native.binding = forbidden
        self.assertFalse(self.tick())

    def test_unexpected_player_while_waiting_is_failure(self):
        self.arm(); self.tick()
        self.native.value.update(player_is_original_account=False, player_present=True)
        with self.assertRaises(RuntimeError): self.tick()

    def test_explicit_move_early_return_is_failure(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.early = True
        with self.assertRaises(RuntimeError):
            for _ in range(6): self.tick()
        self.assertNotIn('forward', A._run.proofs)

    def test_automatic_zero_early_observation_is_allowed_not_proof(self):
        self.arm(); self.tick()
        self.native.pair(A.note_movement_call, 'moveVehicle', 2130, 300, dict(flags=0, is_key_down=False), 12)
        A._run.drain()
        self.assertNotIn('stop_turn', A._run.proofs)

    def test_nested_automatic_stop_during_leave_is_not_leave_action_proof(self):
        self.arm(); self.tick()
        A._run.intent = 'leave'
        self.native.pair(A.note_movement_call, 'moveVehicle', 2130, 300, dict(flags=0, is_key_down=False), 12)
        A._run.intent = None
        A._run.drain()
        self.assertNotIn('leave', A._run.proofs)
        notes = [row for event, row in self.events if event == 'map_drive_acceptance_callback' and row['kind'] == 'movement']
        self.assertTrue(all(row['intent'] is None for row in notes))

    def test_unexpected_manual_motion_is_rejected(self):
        self.arm(); self.tick()
        self.native.pair(A.note_movement_call, 'moveVehicle', 2130, 300, dict(flags=1, is_key_down=True), 345)
        with self.assertRaises(RuntimeError): A._run.drain()

    def test_passive_invalid_callback_does_not_raise_inside_profiler(self):
        self.arm()
        self.assertFalse(A.note_movement_call('call', 'moveVehicle', True, -1, 1, 300, dict(flags=1, is_key_down=True)))
        with self.assertRaises(RuntimeError): self.tick()

    def test_call_id_none_rejected(self):
        self.arm()
        self.assertFalse(A.note_map_drive_call('return', '__setOwnVehicleMatrixCallback', 2951, 151, None, 300, {}))

    def test_mismatched_entry_data_rejected(self):
        self.arm()
        data = dict(flags=0, is_key_down=False)
        A.note_movement_call('call', 'moveVehicle', 2130, -1, 10, 300, data)
        A.note_movement_call('return', 'moveVehicle', 2130, 345, 10, 300, dict(flags=1, is_key_down=True))
        with self.assertRaises(RuntimeError): A._run.drain()

    def test_wrong_source_line_rejected(self):
        self.arm()
        self.native.pair(A.note_movement_call, 'moveVehicle', 2131, 300, dict(flags=0, is_key_down=False), 345)
        with self.assertRaises(RuntimeError): A._run.drain()

    def test_duplicate_call_id_rejected(self):
        self.arm()
        data = dict(flags=0, is_key_down=False)
        for _ in range(2):
            A.note_movement_call('call', 'moveVehicle', 2130, -1, 10, 300, data)
        with self.assertRaises(RuntimeError): A._run.drain()

    def test_pending_note_budget_is_failure_not_success(self):
        self.arm()
        for i in range(A.MAX_PENDING):
            self.assertTrue(A.note_movement_call('call', 'moveVehicle', 2130, -1, i + 1, 300, dict(flags=0, is_key_down=False)))
        self.assertFalse(A.note_movement_call('call', 'moveVehicle', 2130, -1, 10000, 300, dict(flags=0, is_key_down=False)))
        with self.assertRaises(RuntimeError): A._run.drain()

    def test_total_note_budget_rejects(self):
        self.arm(); A._run.sequence = A.MAX_NOTES
        self.assertFalse(A.note_action_call('call', 'leaveArena', 2310, -1, 1, 300, {}))

    def test_bound_provider_python_identity_not_required(self):
        self.to_forward()
        self.assertFalse(self.native.binding()['target_python_identity_equal'])
        self.assertIn('forward', A._run.proofs)

    def test_unbound_provider_cannot_start_motion(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.target = False
        for _ in range(8): self.tick()
        self.assertNotIn((1, True), self.native.actions)

    def test_provider_mismatch_rejects_and_attempts_original_stop(self):
        self.to_forward()
        self.native.binding_changes['own_matrix_position'] = [100.0, 20.0, 0.0]
        with self.assertRaises(RuntimeError): self.tick()
        self.assertEqual(self.native.actions[-1], (0, False))

    def test_wrong_avatar_callback_owner_rejects(self):
        self.arm(); self.tick(); self.enter_world()
        for p in A._run.notes:
            if p['kind'] == 'avatar' and p['method'] == 'onSpaceLoaded': p['owner_id'] = 999
        with self.assertRaises(RuntimeError): self.tick()

    def test_unsupported_map_rejects(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.value['arena_type_id'] = 99
        with self.assertRaises(RuntimeError): self.tick()

    def test_foreign_geometry_rejected_without_callback_raise(self):
        self.arm()
        self.assertFalse(A.note_geometry_mapped(1, 'spaces/other'))
        with self.assertRaises(RuntimeError): self.tick()

    def test_not_battle_never_emits_forward(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.motion_changes['period'] = 2
        for _ in range(8): self.tick()
        self.assertNotIn((1, True), self.native.actions)

    def test_models_must_be_actual_visible_original_models(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.item['models'][0]['visible'] = False
        with self.assertRaises(RuntimeError): self.tick()

    def test_health_mutation_rejected(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.item['health'] = 1
        with self.assertRaises(RuntimeError): self.tick()

    def test_original_uint8_crew_one_preserves_native_type(self):
        self.arm(); self.tick(); self.enter_world()
        for value in [True] + [kind(1) for kind in A.probe.integer_types]:
            self.native.item['crew_active'] = value
            self.native.item['crew_active_python_type'] = type(value).__name__
            self.assertFalse(self.tick())
            states = [row for event, row in self.events if event == 'map_drive_acceptance_state']
            self.assertTrue(states[-1]['world_ready'])
            self.assertIs(type(states[-1]['vehicle']['crew_active']), type(value))
            self.assertEqual(states[-1]['vehicle']['crew_active_python_type'], type(value).__name__)

    def test_crew_zero_false_and_foreign_one_cannot_make_world_ready(self):
        class ForeignInteger(int):
            pass
        self.arm(); self.tick(); self.enter_world()
        for value in (0, False, 1.0, '1', ForeignInteger(1)):
            self.native.item['crew_active'] = value
            self.native.item['crew_active_python_type'] = type(value).__name__
            with self.assertRaises((RuntimeError, ValueError)):
                self.tick()
            self.at += 1.0  # tick's successful-return clock step did not run.
            rejected = [row for event, row in self.events if event == 'map_drive_acceptance_state_rejected']
            self.assertFalse(rejected[-1]['world_ready'])
            self.assertIs(type(rejected[-1]['vehicle']['crew_active']), type(value))
            self.assertFalse(A._run.complete)
        self.assertNotIn((1, True), self.native.actions)

    def test_rejected_iteration_retains_current_fields_before_error(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.item['is_started'] = False
        self.assertFalse(self.tick())
        self.native.item.update(is_started=True, health=89, crew_active=1,
                                crew_active_python_type='int')
        failed_at = self.at
        with self.assertRaises(RuntimeError):
            self.tick()
        rejected_index = next(i for i, pair in enumerate(self.events)
                              if pair[0] == 'map_drive_acceptance_state_rejected')
        rejected = self.events[rejected_index][1]
        self.assertEqual(rejected['vehicle']['health'], 89)
        self.assertTrue(rejected['vehicle']['is_started'])
        self.assertIs(type(rejected['vehicle']['crew_active']), int)
        self.assertEqual(rejected['observed_at'], failed_at)
        self.assertEqual(rejected['advance'], A._run.advances)
        self.assertEqual(rejected['context'], self.native.context())
        self.assertEqual(rejected['motion'], self.native.motion())
        self.assertEqual(rejected['binding'], self.native.binding())
        self.assertEqual(self.events[rejected_index + 1][0], 'map_drive_acceptance_error')
        self.assertNotIn((1, True), self.native.actions)

    def test_no_progress_stops_original_command_and_fails(self):
        self.to_forward()
        self.at += A.MAX_ACTION_SECONDS
        with self.assertRaises(RuntimeError): self.tick()
        self.assertEqual(self.native.actions[-1], (0, False))

    def test_loaded_world_waits_for_separate_server_ready_then_continues(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.item['roster']['avatar_ready'] = False
        self.native.motion_changes.update(period=1, is_on_arena=False)
        self.native.target = False
        self.assertFalse(self.tick())
        self.assertEqual(A._run.phase, 'waiting_world')
        self.assertIsNone(A._run.last_world)
        self.assertEqual(self.native.actions, ['fight'])
        observed = [r for e, r in self.events if e == 'map_drive_acceptance_state'][-1]
        self.assertFalse(observed['world_ready'])
        self.native.item['roster']['avatar_ready'] = True
        self.native.motion_changes.update(period=3, is_on_arena=True)
        self.native.target = True
        self.binding()
        self.tick()
        self.assertEqual(A._run.phase, 'baseline')

    def test_pre_ready_death_and_wrong_identity_still_fail(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.item['roster']['avatar_ready'] = False
        self.native.motion_changes.update(period=1, is_on_arena=False)
        for field, value in (('alive', False), ('database_id', 2), ('name', 'foreign')):
            old = self.native.item['roster'][field]
            self.native.item['roster'][field] = value
            with self.assertRaises(RuntimeError): self.tick()
            self.at += 1.0
            self.native.item['roster'][field] = old
        self.assertEqual(self.native.actions, ['fight'])

    def test_pre_ready_wait_is_exact_false_period_one_only(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.motion_changes.update(period=1, is_on_arena=False)
        for value in (None, 0, '', True):
            self.native.item['roster']['avatar_ready'] = value
            if value is True:
                self.native.motion_changes.update(period=3, is_on_arena=True)
                continue
            with self.assertRaises(RuntimeError): self.tick()
            self.at += 1.0
        self.native.item['roster']['avatar_ready'] = False
        with self.assertRaises(RuntimeError): self.tick()

    def test_roster_readiness_lost_after_ready_cannot_return_to_wait(self):
        self.to_forward()
        self.native.item['roster']['avatar_ready'] = False
        self.native.motion_changes.update(period=1, is_on_arena=False)
        with self.assertRaises(RuntimeError): self.tick()
        self.assertEqual(self.native.actions[-1], (0, False))

    def test_world_ready_sample_gap_rejects(self):
        self.to_forward(); self.at += 4.0
        with self.assertRaises(RuntimeError): self.tick()

    def test_transient_missing_target_requests_fast_read_without_acceptance(self):
        self.to_forward()
        self.assertEqual(A.next_observation_delay(),1.0)
        self.native.target=False
        self.assertFalse(self.tick())
        self.assertEqual(A.next_observation_delay(),0.1)
        self.assertEqual(A._run.phase,'forward')
        last=[r for e,r in self.events if e=='map_drive_acceptance_state'][-1]
        self.assertFalse(last['world_ready'])
        self.native.target=True
        self.at-=0.9
        self.binding();self.tick()
        self.assertEqual(A.next_observation_delay(),1.0)

    def test_fast_retry_keeps_elapsed_three_second_and_advance_bounds(self):
        self.to_forward();self.native.target=False
        self.tick()
        self.at=A._run.last_world+3.01
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))
        self.assertFalse(A._run.complete)

    def test_fast_retry_unarmed_initial_and_closed_remain_passive(self):
        self.assertEqual(A.next_observation_delay(),1.0)
        self.arm();self.tick();self.enter_world();self.native.target=False
        self.assertFalse(self.tick())
        self.assertEqual(A.next_observation_delay(),1.0)
        A.fini(self.record)
        self.assertEqual(A.next_observation_delay(),1.0)

    def test_reverse_in_wrong_direction_does_not_finish(self):
        self.to_forward()
        self.native.position[2] = 3.1; self.tick()
        self.native.heading = 0.2; self.tick(); self.tick(); self.tick(); self.tick(); self.tick()
        self.native.position[2] += 3.0; self.tick()
        self.assertEqual(A._run.phase, 'reverse')

    def test_turn_without_heading_change_does_not_finish(self):
        self.to_forward()
        self.native.position[2] = 3.1; self.tick(); self.tick()
        self.assertEqual(A._run.phase, 'turn')

    def test_stop_requires_actual_stable_hold(self):
        self.to_forward()
        self.native.position[2] = 3.1; self.tick()
        self.native.heading = 0.2; self.tick()
        for _ in range(5):
            self.native.position[2] += 0.2
            self.tick()
        self.assertEqual(A._run.phase, 'hold_turn')

    def test_nonfinite_world_cannot_create_valid_evidence(self):
        self.to_forward(); self.native.position[0] = float('nan')
        with self.assertRaises((RuntimeError, ValueError)): self.tick()

    def test_png_timeout_is_failure(self):
        self.arm(); self.tick(); self.enter_world()
        self.native.auto_png = False
        with self.assertRaises(RuntimeError):
            for _ in range(25): self.tick()
        self.assertNotIn((1, True), self.native.actions)

    def test_receipt_bound_to_current_observation_iteration(self):
        self.to_forward()
        for event, row in self.events:
            if event == 'map_drive_acceptance_screenshot':
                prior = [r for e, r in self.events if e == 'map_drive_acceptance_state' and r['advance'] == row['advance']]
                self.assertEqual(len(prior), 1)
                self.assertEqual(prior[0]['observed_at'], row['observed_at'])

    def test_resource_mutation_after_return_rejected(self):
        self.to_leave(); self.return_account()
        self.native.public['resources']['credits'] -= 1
        with self.assertRaises(RuntimeError): self.tick()

    def test_ammo_mutation_after_return_rejected(self):
        self.to_leave(); self.return_account()
        self.native.account_value['ammo']['raw_shells'][1] = 19
        with self.assertRaises(RuntimeError): self.tick()

    def test_repository_replacement_after_return_rejected(self):
        self.to_leave(); self.return_account()
        self.native.account_value['repository_owner_id'] = 555
        with self.assertRaises(RuntimeError): self.tick()

    def test_return_without_original_teardown_rejected(self):
        self.to_leave(); self.native.value = V.account()
        with self.assertRaises(RuntimeError): self.tick()

    def test_world_teardown_before_explicit_leave_rejected(self):
        self.to_forward(); self.entity('avatar', 'onLeaveWorld')
        with self.assertRaises(RuntimeError): self.tick()

    def test_disconnect_is_not_a_warm_return(self):
        self.to_leave(); self.native.value['native_connected'] = False
        with self.assertRaises(RuntimeError): self.tick()

    def test_return_ready_gap_cannot_fake_hold(self):
        self.to_leave(); self.return_account(); self.tick(); self.at += 10
        with self.assertRaises(RuntimeError): self.tick()

    def test_advance_budget_never_reports_completion(self):
        self.arm(); A._run.advances = A.MAX_ADVANCES
        with self.assertRaises(RuntimeError): self.tick()

    def test_fini_stops_only_owned_motion_without_service_cleanup(self):
        self.to_forward()
        A.fini(self.record)
        self.assertEqual(self.native.actions[-1], (0, False))
        self.assertFalse(A._run.active)
        count = len(self.native.actions)
        A.fini(self.record)
        self.assertEqual(len(self.native.actions), count)

    def test_emergency_stop_does_not_command_replaced_player(self):
        self.to_forward(); self.native.value = V.account()
        before = len(self.native.actions)
        A.fini(self.record)
        self.assertEqual(len(self.native.actions), before)
        self.assertTrue(any(e == 'map_drive_acceptance_emergency_stop' and r['outcome'] == 'NOT_RUN' for e, r in self.events))

    def test_record_failure_cannot_prevent_original_stop_attempt(self):
        self.to_forward()
        def broken(event, **fields):
            raise IOError('synthetic evidence disk failure')
        self.record = broken
        A._run.record = broken
        with self.assertRaises(RuntimeError): self.tick()
        self.assertEqual(self.native.actions[-1], (0, False))

    def test_fini_does_not_hide_queued_invalid_callbacks(self):
        self.arm()
        A.note_movement_call('call', 'moveVehicle', 2130, -1, None, 300, dict(flags=0, is_key_down=False))
        with self.assertRaises(RuntimeError): A.fini(self.record)
        self.assertFalse(A._run.active)

    def test_positive_server_counter_observed_before_original_button(self):
        self.arm();self.tick()
        proof=next(i for i,(e,r) in enumerate(self.events) if e=='map_drive_acceptance_captcha')
        button=next(i for i,(e,r) in enumerate(self.events) if e=='map_drive_acceptance_action' and r['moment']=='begin')
        self.assertLess(proof,button)
        self.assertEqual(self.events[proof][1]['snapshot'],self.native.captcha)
        self.assertEqual(self.native.actions,['fight'])
        self.assertFalse(self.events[proof][1]['original_counter_assigned'])
        self.assertFalse(self.events[proof][1]['original_result_overridden'])

    def test_required_captcha_fails_before_button_without_synthetic_answer(self):
        self.native.captcha['captcha_required']=True
        self.arm()
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions,[])
        self.assertFalse(any(e=='map_drive_acceptance_action' for e,r in self.events))

    def test_wrong_positive_policy_counter_is_not_the_expected_counter_one(self):
        self.native.captcha['battles_till_captcha']=2
        self.arm()
        with self.assertRaises(ValueError):self.tick()
        self.assertEqual(self.native.actions,[])

    def test_external_guard_call_is_fatal_even_when_native_captcha_not_required(self):
        self.native.captcha['guard_blocked_calls']=1
        self.arm()
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions,[])

    def fire_sample(self, delay=0.02):
        sampler=A._run.sampler
        requested,callback=self.native.scheduled.pop(sampler.callback_id)
        self.assertEqual(requested,A.SAMPLE_DELAY)
        self.at+=delay
        callback()

    def test_sampler_starts_once_only_after_actual_ready_and_records_real_cadence(self):
        self.arm();self.tick()
        self.assertIsNone(A._run.sampler)
        self.enter_world();self.native.target=False;self.tick()
        self.assertIsNone(A._run.sampler)
        self.native.target=True;self.tick()
        self.assertIsNone(A._run.sampler)  # Ready baseline is outside the basic drive window.
        for _ in range(5):self.tick()
        sampler=A._run.sampler
        first=sampler.last_sampled_at
        self.fire_sample(0.037)
        rows=[r for e,r in self.events if e=='map_drive_acceptance_sample']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[-1]['sample_index'],2)
        self.assertEqual(rows[-1]['previous_sampled_at'],first)
        self.assertGreater(rows[-1]['sampled_at']-first,0.037)
        self.assertEqual(rows[-1]['requested_delay'],0.02)
        self.assertEqual(len([e for e,r in self.events if e=='map_drive_acceptance_sampler_start']),1)
        self.assertIs(sampler,A._run.sampler)

    def test_sampler_keeps_target_none_and_pending_original_return_anchors(self):
        self.to_forward()
        self.native.target=False
        self.native.pair(A.note_map_drive_call,'updateOwnVehiclePosition',1445,300,
                        dict(position=[1.,2.,3.],direction=[0.]*3,speed=-1.,rspeed=0.),198)
        cid=self.native.cid
        self.fire_sample()
        row=[r for e,r in self.events if e=='map_drive_acceptance_sample'][-1]
        self.assertFalse(row['snapshot']['target_present'])
        self.assertEqual(row['last_update']['call_id'],cid)
        self.assertEqual(row['last_update']['offset'],198)
        self.assertEqual(row['last_update']['noted_at'],self.at-0.02)
        self.assertEqual(row['last_deferred']['offset'],151)
        self.assertIsNone(A._run.sampler.error)
        self.assertFalse(self.tick())  # Sampling missing target does not accept readiness.
        self.assertEqual(A.next_observation_delay(),0.1)

    def test_sampler_read_failure_is_queued_outside_callback_and_stops_motion(self):
        self.to_forward()
        def broken(*args):raise AttributeError('synthetic actual camera getter failure')
        self.native.sample=broken
        self.fire_sample()  # Must not throw from a BigWorld-style callback.
        self.assertIn('AttributeError',A._run.sampler.error)
        self.assertFalse(A._run.sampler.active)
        self.assertFalse(self.native.scheduled)
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_sampler_signed_native_handles_reschedule_and_cancel_unchanged(self):
        self.to_forward()
        handles=iter((-2147483647,-1,2147483647))
        def schedule(delay,callback):
            token=next(handles)
            self.native.scheduled[token]=(delay,callback)
            return token
        self.native.schedule_sample=schedule
        self.fire_sample()
        self.assertEqual(A._run.sampler.callback_id,-2147483647)
        self.fire_sample()
        self.assertEqual(A._run.sampler.callback_id,-1)
        self.assertIsNone(A._run.sampler.error)
        handles=[r for e,r in self.events if e=='map_drive_acceptance_sampler_callback_handle']
        self.assertEqual(len(handles),1)
        self.assertEqual(handles[0]['callback_handle'],-2147483647)
        self.assertIs(handles[0]['first_negative'],True)
        self.assertEqual(handles[0]['native_type'],'int')
        A.fini(self.record)
        self.assertIn(-1,self.native.cancelled)
        self.assertFalse(self.native.scheduled)
        stop=[r for e,r in self.events if e=='map_drive_acceptance_sampler_stop']
        self.assertEqual(len(stop),1)
        self.assertEqual(stop[0]['callback_handle'],-1)
        self.assertTrue(stop[0]['pending_callback_cancelled'])

    def test_sampler_bad_handle_is_owned_before_validation_and_stop_is_once(self):
        self.to_forward()
        # A deliberately invalid native return proves failure ownership;
        # this fake scheduler/canceller is not native ABI acceptance.
        token=2147483648
        def schedule(delay,callback):
            self.native.scheduled[token]=(delay,callback)
            return token
        self.native.schedule_sample=schedule
        self.fire_sample()
        self.assertEqual(A._run.sampler.callback_id,token)
        self.assertIn('nonzero signed int32',A._run.sampler.error)
        self.assertFalse(A._run.sampler.active)
        with self.assertRaises(RuntimeError):self.tick()
        self.assertIn(token,self.native.cancelled)
        self.assertFalse(self.native.scheduled)
        A.fini(self.record)
        self.assertEqual(len([r for e,r in self.events if e=='map_drive_acceptance_sampler_stop']),1)

    def test_sampler_cancel_failure_keeps_owned_token_for_fini_retry(self):
        self.to_forward()
        sampler=A._run.sampler;token=sampler.callback_id
        original=self.native.cancel_sample
        def broken(value):raise RuntimeError('synthetic cancel failed before removal')
        self.native.cancel_sample=broken
        with self.assertRaises(RuntimeError):sampler.stop('diagnostic_error')
        self.assertEqual(sampler.callback_id,token)
        self.assertIn(token,self.native.scheduled)
        self.assertFalse(sampler.stop_recorded)
        self.native.cancel_sample=original
        A.fini(self.record)
        self.assertEqual(self.native.cancelled.count(token),1)
        self.assertIsNone(sampler.callback_id)
        self.assertTrue(sampler.stop_recorded)

    def test_sampler_nonfinite_read_is_failure_not_a_written_sample(self):
        self.to_forward()
        before=len([r for e,r in self.events if e=='map_drive_acceptance_sample'])
        self.native.position[0]=float('nan')
        self.fire_sample()
        self.assertIsNotNone(A._run.sampler.error)
        self.assertEqual(len([r for e,r in self.events if e=='map_drive_acceptance_sample']),before)

    def test_sampler_timestamps_precede_record_overhead_and_clock_reversal_fails(self):
        self.to_forward()
        old=A._run.record
        def delayed(event,**fields):
            if event=='map_drive_acceptance_sample':self.at+=0.25
            old(event,**fields)
        A._run.record=delayed
        self.fire_sample()
        row=[r for e,r in self.events if e=='map_drive_acceptance_sample'][-1]
        self.assertEqual(row['sample_started_at'],row['sampled_at'])
        self.assertAlmostEqual(self.at-row['sampled_at'],0.25)
        self.at=row['sampled_at']-0.1
        self.fire_sample()
        self.assertIn('strictly increasing',A._run.sampler.error)

    def test_sampler_sample_and_elapsed_budgets_fail_without_another_native_read(self):
        self.to_forward();reads=self.native.sample_reads
        A._run.sampler.count=A.MAX_SAMPLES
        self.fire_sample()
        self.assertIn('budget exhausted',A._run.sampler.error)
        self.assertEqual(self.native.sample_reads,reads)
        # Independently exercise the finite time bound, not the count bound.
        A._run.sampler=A._Sampler(A._run,1)
        self.at+=A.MAX_SAMPLE_SECONDS
        A._run.sampler._tick()
        self.assertIn('budget exhausted',A._run.sampler.error)
        self.assertEqual(self.native.sample_reads,reads)

    def test_sampler_stops_before_original_leave_and_cannot_read_after_fini(self):
        self.to_leave()
        events=[(e,r) for e,r in self.events]
        stop=next(i for i,(e,r) in enumerate(events) if e=='map_drive_acceptance_sampler_stop')
        leave=next(i for i,(e,r) in enumerate(events) if e=='map_drive_acceptance_action' and r['action']=='leave')
        self.assertLess(stop,leave)
        self.assertEqual(events[stop][1]['reason'],'before_original_leave')
        self.assertFalse(self.native.scheduled)
        before=self.native.sample_reads
        A.fini(self.record);A._run.sampler._tick()
        self.assertEqual(self.native.sample_reads,before)

    def test_sampler_fini_cancels_callback_before_emergency_stop(self):
        self.to_forward();sampler=A._run.sampler;token=sampler.callback_id
        old=self.native.move
        def checked_move(*args):
            self.assertFalse(self.native.scheduled)
            return old(*args)
        self.native.move=checked_move
        A.fini(self.record)
        self.assertIn(token,self.native.cancelled)
        self.assertFalse(sampler.active)

    def test_sampler_cancel_failure_does_not_prevent_emergency_stop_or_hide_failure(self):
        self.to_forward()
        def broken(token):raise RuntimeError('synthetic cancel failure')
        self.native.cancel_sample=broken
        with self.assertRaises(RuntimeError):A.fini(self.record)
        self.assertEqual(self.native.actions[-1],(0,False))
        self.assertFalse(A._run.active)


class StaticContractTests(unittest.TestCase):
    def test_native_callback_handle_exact_signed_type_and_bounds(self):
        for value in (-2147483648,-2147483647,-1,1,2147483647):
            self.assertEqual(A._callback_handle(value),value)
        class ForeignInt(int):pass
        class Opaque(object):
            def __str__(self):raise AssertionError('foreign callback token stringified')
        bad=(None,False,True,0,2147483648,4294967295,-2147483649,1.0,'1',ForeignInt(1),Opaque())
        if sys.version_info[0]==2:bad=bad+(long(1),long(-1))
        for value in bad:
            with self.assertRaises(ValueError):A._callback_handle(value)

    @unittest.skipIf(sys.version_info[0] < 3, 'host Python3 PE reader only')
    def test_original_callback_signed_pyint_return_cancel_format_and_generation(self):
        import struct,pefile
        from pathlib import Path
        sys.path.insert(0,os.path.join(ROOT,'tools'))
        from client_audit import config,read_limited
        raw=read_limited(config()[1]['original_client_root']/'WorldOfTanks.exe',64*1048576)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed')
        pe=pefile.PE(data=raw,fast_load=True)
        def read(va,n):
            start=pe.get_offset_from_rva(va-pe.OPTIONAL_HEADER.ImageBase)
            return raw[start:start+n]
        code=read(0xf4f66f,5)
        self.assertEqual(code[:1],b'\xe8')
        self.assertEqual(0xf4f674+struct.unpack('<i',code[1:])[0],0x486ee0)
        self.assertEqual(read(0x17071ac,2),b'i\0')
        self.assertEqual(read(0xf4f4e3,3),b'\xc1\xe0\x18')  # counter << 24
        self.assertEqual(read(0xf4f4ec,4),b'\x0b\xc2\xfe\xc1')  # OR slot; increment byte

    @unittest.skipIf(sys.version_info[0] < 3, 'host Python3 static decoder only')
    def test_original_camera_inverse_view_read_is_pinned_not_guessed(self):
        from pathlib import Path
        sys.path.insert(0,os.path.join(ROOT,'tools'))
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,opcode_table,disassemble
        path='res/scripts/client/AvatarInputHandler/cameras.pyc'
        raw=read_limited(config()[1]['original_client_root']/path,1048576)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),dict(A.EXTRA_SOURCES)[path])
        code=dict(records(parse_pyc(raw)))['<module>.getWorldRayAndPoint']
        self.assertEqual(code['firstlineno'],208)
        self.assertEqual(hashlib.sha256(code['code']).hexdigest(),'96c660caff3ba4460ac1b76cefe5519cc6e6c4a018823e0fd860899faa893f3f')
        table=opcode_table(read_limited(Path(ROOT)/'local/vendor/cpython-2.7.3/opcode.py',32768).decode())
        ins=dict((r['offset'],r) for r in disassemble(code,table))
        self.assertEqual([ins[o].get('value') for o in (104,107,110,116)],['Matrix','BigWorld','camera','invViewMatrix'])
        self.assertEqual(ins[113]['arg'],0)
        self.assertEqual(ins[119]['arg'],1)
    @unittest.skipIf(sys.version_info[0] < 3, 'host Python3 static decoder only')
    def test_passive_captcha_getters_pinned_without_executing_original(self):
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,text
        original=config()[1]['original_client_root']
        for filename,expected,qualified,args in (
                (A.CAPTCHA_REQUIRED_SOURCE,A.CAPTCHA_REQUIRED_METHOD,'<module>.CaptchaController.isCaptchaRequired',('self',)),
                (A.CACHE_GETTER_SOURCE,A.CACHE_GETTER_METHOD,'<module>.RequesterAbstract.getCacheValue',('self','key','defaultValue'))):
            path='res/'+filename[:-3]+'.pyc'
            raw=read_limited(original/path,1048576)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),dict(A.EXTRA_SOURCES)[path])
            code=dict(records(parse_pyc(raw)))[qualified]
            self.assertEqual((code['firstlineno'],code['argcount']),(expected[2],expected[3]))
            self.assertEqual(hashlib.sha256(code['code']).hexdigest(),expected[-1])
            self.assertEqual(tuple(text(v) for v in code['varnames'][:len(args)]),args)
    @unittest.skipIf(sys.version_info[0] < 3, 'host Python3 static decoder only')
    def test_original_action_code_hashes_and_ray_plans(self):
        from pathlib import Path
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        from client_audit import config, read_limited
        from py27_static import parse_pyc, records, text, opcode_table, disassemble
        original = config()[1]['original_client_root']
        table = opcode_table(read_limited(Path(ROOT) / 'local/vendor/cpython-2.7.3/opcode.py', 32768).decode('utf8'))
        specs = [('client/Avatar', '<module>.PlayerAvatar.leaveArena', A.LEAVE_METHOD[4], 2310, ('self',), 178),
                 ('client/gui/Scaleform/daapi/view/lobby/header/FightButton', '<module>.FightButton.fightClick',
                  '075a47213a9beee880cf1abc17bc24a25b88fbfed245f9ff1b2f068dfa3cb00c', 196, ('self', 'mapID', 'actionName'), 65)]
        for name, qual, digest, line, args, offset in specs:
            raw = read_limited(original / ('res/scripts/' + name + '.pyc'), 1048576)
            code = dict(records(parse_pyc(raw)))[qual]
            self.assertEqual(hashlib.sha256(code['code']).hexdigest(), digest)
            self.assertEqual(code['firstlineno'], line)
            self.assertEqual(tuple(text(n) for n in code['varnames'][:code['argcount']]), args)
            instructions = dict((i['offset'], i) for i in disassemble(code, table))
            self.assertEqual(instructions[offset]['opname'], 'RETURN_VALUE')
        base = Path(ROOT) / 'local/evidence/20261005-p02-map-drive/data'
        for map_id, dirname in ((1, 'native-rays-01'), (4, 'native-rays-prohorovka-01')):
            raw = (base / dirname / 'samples.json').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), A.RAY_PLANS[map_id][0])
        inputs = json.loads((base / 'native-rays-prohorovka-01/native-input.json').read_text())
        projected = [(r['sample_id'], r['start'][0], r['start'][2]) for r in inputs['samples']]
        self.assertEqual(projected, list(A.RAY_PLANS[4][1]))
        for r in inputs['samples']:
            self.assertEqual(r['start'][1], 200.0); self.assertEqual(r['end'][1], -50.0)
            self.assertEqual(r['flags'], 18)


class NativeHangarReadinessTests(unittest.TestCase):
    def setUp(self):
        self.missing=object()
        names=('Account','BigWorld','ConnectionManager','gui','gui.shared','gui.WindowsManager',
               'gui.Scaleform','gui.Scaleform.framework','gui.Scaleform.Waiting',
               'gui.Scaleform.daapi','gui.Scaleform.daapi.view','gui.Scaleform.daapi.view.lobby',
               'gui.Scaleform.daapi.view.lobby.hangar','gui.Scaleform.daapi.view.lobby.hangar.Hangar')
        self.saved=dict((n,sys.modules.get(n,self.missing)) for n in names)
        modules=dict((n,types.ModuleType(n)) for n in names)
        for name,module in modules.items():module.__path__=[]
        class Box(object):
            def __init__(self,**fields):self.__dict__.update(fields)
        self.Box=Box
        self.account=type('PlayerAccount',(object,),{'databaseID':1})
        self.hangar=type('Hangar',(object,),{})
        self.page=self.hangar();self.page.flashObject=object()
        self.container=Box(getView=lambda:self.page)
        self.manager=Box(getContainer=lambda view:self.container)
        self.app=Box(containerManager=self.manager)
        self.windows=Box(window=self.app)
        self.waiting=False
        modules['Account'].PlayerAccount=self.account
        modules['BigWorld'].player=lambda:self.account()
        modules['ConnectionManager'].connectionManager=Box(isConnected=lambda:True)
        modules['gui.shared'].g_itemsCache=Box(isSynced=lambda:True)
        modules['gui.WindowsManager'].g_windowsManager=self.windows
        modules['gui.Scaleform.framework'].ViewTypes=Box(LOBBY_SUB=3)
        modules['gui.Scaleform.Waiting'].Waiting=Box(isVisible=lambda:self.waiting)
        modules['gui.Scaleform.daapi.view.lobby.hangar.Hangar'].Hangar=self.hangar
        sys.modules.update(modules)
        self.receiver=object.__new__(A._Native)

    def tearDown(self):
        for name,value in self.saved.items():
            if value is self.missing:sys.modules.pop(name,None)
            else:sys.modules[name]=value

    def test_real_getter_waits_for_original_missing_container_then_ready(self):
        self.container=None
        self.assertFalse(self.receiver.hangar_ready())
        self.container=self.Box(getView=lambda:self.page)
        self.assertTrue(self.receiver.hangar_ready())

    def test_none_app_manager_view_and_unbound_hangar_remain_not_ready(self):
        self.windows.window=None;self.assertFalse(self.receiver.hangar_ready())
        self.windows.window=self.app;self.app.containerManager=None
        self.assertFalse(self.receiver.hangar_ready())
        self.app.containerManager=self.manager;self.page=None
        self.assertFalse(self.receiver.hangar_ready())
        self.page=self.hangar();self.page.flashObject=None
        self.assertFalse(self.receiver.hangar_ready())
        self.page.flashObject=object();self.waiting=True
        self.assertFalse(self.receiver.hangar_ready())

    def test_malformed_container_and_native_getter_exception_are_not_hidden(self):
        self.container=object()
        with self.assertRaises(AttributeError):self.receiver.hangar_ready()
        def broken():raise AttributeError('synthetic underlying getter error')
        self.container=self.Box(getView=broken)
        with self.assertRaises(AttributeError):self.receiver.hangar_ready()

    def test_foreign_view_is_not_accepted_as_native_hangar(self):
        self.page=self.Box(flashObject=object())
        self.assertFalse(self.receiver.hangar_ready())


class NativeSamplerReadTests(unittest.TestCase):
    def setUp(self):
        self.missing=object()
        self.saved=dict((n,sys.modules.get(n,self.missing)) for n in ('Avatar','Vehicle','BigWorld','Math'))
        self.modules=dict((n,types.ModuleType(n)) for n in self.saved)
        class Box(object):
            def __init__(self,**fields):self.__dict__.update(fields)
        class Vec(object):
            def __init__(self,x,y,z):self.x,self.y,self.z=x,y,z
        class Matrix(object):
            def __init__(self,source):
                self.translation=source.translation
                self.forward=source.forward
            def applyToAxis(self,index):
                if index!=2:raise ValueError('only measured forward axis')
                return self.forward
        self.Box,self.Vec=Box,Vec
        self.pose=lambda x:Box(translation=Vec(x,2.,3.),forward=Vec(0.,0.,1.))
        playerclass=type('PlayerAvatar',(object,),{})
        vehicleclass=type('Vehicle',(object,),{})
        filterclass=type('WGVehicleFilter',(object,),{})
        player,current,filt=playerclass(),vehicleclass(),filterclass()
        self.player,self.current,self.filt=player,current,filt
        player.id=A.vehicle.AVATAR_ID;player.spaceID=1;player.inWorld=True
        player.playerVehicleID=A.vehicle.VEHICLE_ID;player.vehicle=current
        player._PlayerAvatar__lastVehicleSpeeds=(-3.,.1)
        self.provider=self.pose(10.);self.provider.target=self.pose(20.)
        player.getOwnVehicleMatrix=lambda:self.provider
        current.id=A.vehicle.VEHICLE_ID;current.spaceID=1
        current.inWorld=current.isStarted=True
        current.filter=filt;current.model=Box(matrix=self.pose(30.))
        current.position=Vec(40.,2.,3.);current.matrix=self.pose(41.)
        filt.bodyMatrix=self.pose(20.);filt.speedInfo=Box(value=(-2.,0.,-2.5,0.))
        self.camera=Box(invViewMatrix=self.pose(50.))
        self.modules['Avatar'].PlayerAvatar=playerclass
        self.modules['Vehicle'].Vehicle=vehicleclass
        self.modules['BigWorld'].WGVehicleFilter=filterclass
        self.modules['BigWorld'].player=lambda:self.player
        self.modules['BigWorld'].entity=lambda eid:self.current
        self.modules['BigWorld'].camera=lambda:self.camera
        self.modules['Math'].Matrix=Matrix
        sys.modules.update(self.modules)
        self.receiver=object.__new__(A._Native)

    def tearDown(self):
        for name,value in self.saved.items():
            if value is self.missing:sys.modules.pop(name,None)
            else:sys.modules[name]=value

    def read(self):
        return self.receiver.sample(id(self.player),id(self.current),1)

    def test_actual_getter_body_reads_distinct_poses_and_camera_inverse_without_assignment(self):
        before=[dict(x.__dict__) for x in (self.player,self.current,self.filt,self.provider,self.camera)]
        row=self.read()
        self.assertEqual([row[k]['position'][0] for k in ('entity_matrix','model','body','own','camera')],[41.,30.,20.,10.,50.])
        self.assertEqual(row['entity_position'][0],40.)
        self.assertEqual(row['speed_info'],[-2.,0.,-2.5,0.])
        self.assertEqual(row['last_server_speeds'],[-3.,.1])
        self.assertEqual(row['camera']['forward'],[0.,0.,1.])
        self.assertEqual(before,[dict(x.__dict__) for x in (self.player,self.current,self.filt,self.provider,self.camera)])
        self.provider.target=None
        row=self.read()
        self.assertFalse(row['target_present']);self.assertIsNone(row['target'])
        self.assertEqual(row['own']['position'][0],10.)
        self.assertEqual(row['body']['position'][0],20.)

    def test_actual_getter_rejects_owner_space_class_camera_or_nonfinite_reads(self):
        with self.assertRaises(RuntimeError):self.receiver.sample(id(self.player)+1,id(self.current),1)
        self.current.spaceID=2
        with self.assertRaises(RuntimeError):self.read()
        self.current.spaceID=1
        self.player.vehicle=object()
        with self.assertRaises(RuntimeError):self.read()
        self.player.vehicle=self.current
        self.camera=None
        with self.assertRaises(RuntimeError):self.read()
        self.camera=self.Box(invViewMatrix=self.pose(float('nan')))
        with self.assertRaises(ValueError):self.read()

    def test_native_scheduler_only_owns_its_callback_and_never_changes_camera(self):
        calls=[]
        self.modules['BigWorld'].callback=lambda delay,callback:calls.append((delay,callback)) or 73
        self.modules['BigWorld'].cancelCallback=lambda cid:calls.append(cid)
        fn=lambda:None
        self.assertEqual(self.receiver.schedule_sample(0.02,fn),73)
        self.receiver.cancel_sample(73)
        self.assertEqual(calls,[(0.02,fn),73])


class CaptchaPreconditionTests(unittest.TestCase):
    def test_exact_integer_and_false_types_not_truthiness(self):
        good=dict(battles_till_captcha=1,captcha_required=False,
                  controller_owner_id=10,stats_owner_id=11,guard_blocked_calls=0)
        self.assertEqual(A._checked_captcha(good),good)
        self.assertIsNot(A._checked_captcha(good),good)
        for field,values in (
                ('battles_till_captcha',(None,False,True,0,-1,2,1.0,'1')),
                ('captcha_required',(None,0,True,'')),
                ('controller_owner_id',(None,False,0,1.0)),
                ('stats_owner_id',(None,False,0,1.0)),
                ('guard_blocked_calls',(None,False,0.0,1,-1))):
            for value in values:
                bad=dict(good);bad[field]=value
                with self.assertRaises((ValueError,RuntimeError)):A._checked_captcha(bad)
        bad=dict(good);bad['extra']='not permitted'
        with self.assertRaises(ValueError):A._checked_captcha(bad)
        for field in good:
            bad=dict(good);del bad[field]
            with self.assertRaises(ValueError):A._checked_captcha(bad)

    def test_real_getter_body_reads_cache_and_controller_without_mutation(self):
        missing=object();calls=[];owner=self
        names=('gui','gui.shared','gui.game_control','gui.game_control.captcha_control','map_drive_client')
        saved={name:sys.modules.get(name,missing) for name in names}
        modules={name:types.ModuleType(name) for name in names}
        modules['gui'].__path__=[];modules['gui.game_control'].__path__=[]
        modules['gui'].game_control=modules['gui.game_control']
        state=dict(counter=1,required=False,synced=True,blocked=0)
        class CaptchaController(object):
            def isCaptchaRequired(self):calls.append('required');return state['required']
        class Stats(object):
            def getCacheValue(self,key,defaultValue):
                calls.append((key,defaultValue));return state['counter']
        class Box(object):
            def __init__(self,**fields):self.__dict__.update(fields)
        captcha,stats=CaptchaController(),Stats()
        modules['gui.game_control.captcha_control'].CaptchaController=CaptchaController
        modules['gui.game_control'].g_instance=Box(captcha=captcha)
        modules['gui.shared'].g_itemsCache=Box(isSynced=lambda:state['synced'],items=Box(stats=stats))
        def guard_ready():calls.append('guard')
        guard=Box(require_ready=guard_ready,blocked_calls=0)
        modules['map_drive_client']._captcha_guard=guard
        audit=A.probe._code_contract
        def isolated_audit(fn,expected,filename):
            calls.append(('audit',expected[0],filename))
            owner.assertIn(expected,(A.CAPTCHA_REQUIRED_METHOD,A.CACHE_GETTER_METHOD))
        A.probe._code_contract=isolated_audit
        try:
            sys.modules.update(modules)
            receiver=object.__new__(A._Native);receiver.hangar_ready=lambda:True
            before=dict(state)
            result=receiver.captcha_state()
            self.assertEqual(state,before)
            self.assertEqual(result,dict(battles_till_captcha=1,captcha_required=False,
                controller_owner_id=id(captcha),stats_owner_id=id(stats),guard_blocked_calls=0))
            self.assertEqual(calls[-2:],[('battlesTillCaptcha',None),'required'])
            # The real fight wrapper rechecks immediately before native entry.
            button=Box(fightClick=lambda *args:calls.append(('fight',args)))
            receiver._button=lambda:button
            state['required']=True
            with self.assertRaises(RuntimeError):receiver.fight(id(button))
            self.assertFalse(any(type(c) is tuple and c[0]=='fight' for c in calls))
            state['required']=False;receiver.fight(id(button))
            self.assertEqual(calls[-3:],[('battlesTillCaptcha',None),'required',('fight',(0,''))])
            state['synced']=False
            with self.assertRaises(RuntimeError):receiver.captcha_state()
        finally:
            A.probe._code_contract=audit
            for name,value in saved.items():
                if value is missing:sys.modules.pop(name,None)
                else:sys.modules[name]=value


class PythonReceiverTests(unittest.TestCase):
    def test_real_parent_getter_bodies_accept_only_valid_python2_receiver(self):
        # Exercise the actual unchanged getter functions. Only engine imports
        # are inert test modules; no function or parent method is substituted.
        # On Python2 the old unrelated receiver fails BEFORE any native read.
        missing = object()
        names = ('Avatar', 'BigWorld', 'Math', 'Vehicle', 'VehicleAppearance', 'VehicleGunRotator',
                 'gui', 'gui.WindowsManager', 'gui.Scaleform', 'gui.Scaleform.Battle', 'items', 'items.vehicles')
        saved = dict((name, sys.modules.get(name, missing)) for name in names)
        modules = dict((name, types.ModuleType(name)) for name in names)
        for name in ('gui', 'gui.Scaleform', 'items'):
            modules[name].__path__ = []
        modules['gui'].WindowsManager = modules['gui.WindowsManager']
        modules['gui'].Scaleform = modules['gui.Scaleform']
        modules['gui.Scaleform'].Battle = modules['gui.Scaleform.Battle']
        modules['items'].vehicles = modules['items.vehicles']
        modules['Avatar'].PlayerAvatar = type('PlayerAvatar', (object,), {})
        modules['Vehicle'].Vehicle = type('Vehicle', (object,), {})
        modules['BigWorld'].player = lambda: None
        modules['BigWorld'].entity = lambda identity: None
        modules['gui.WindowsManager'].g_windowsManager = object()
        modules['gui.Scaleform.Battle'].Battle = type('Battle', (object,), {})
        try:
            sys.modules.update(modules)
            receiver = object.__new__(A._Native)
            self.assertIsInstance(receiver, A.binding._Native)
            self.assertIsInstance(receiver, A.movement._Native)
            self.assertIsInstance(receiver, A.vehicle._Native)
            self.assertFalse(receiver.world()['vehicle_present'])
            self.assertEqual(receiver.motion(), {'present': False})
            self.assertEqual(receiver.binding(), {'present': False})
            if sys.version_info[0] == 2:
                foreign = object()
                for getter in (A.vehicle._Native.vehicle, A.movement._Native.motion, A.binding._Native.binding):
                    with self.assertRaises(TypeError): getter(foreign)
        finally:
            for name, prior in saved.items():
                if prior is missing:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = prior


if __name__ == '__main__':
    unittest.main()
