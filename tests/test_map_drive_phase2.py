# -*- coding: utf-8 -*-
"""Phase2 state and boundary controls only: no native engine/server/OS input."""
import copy
import math
import sys
import unittest

import map_drive_acceptance as A
import test_map_drive_acceptance as F
from test_arena_vehicle_scenario import avatar, account


class Native(F.NativeControl):
    def binding(self):
        row=F.NativeControl.binding(self)
        row.setdefault('last_server_speeds',[self.speed,0.0])
        return row

    def motion(self):
        row=F.NativeControl.motion(self)
        row.update(body_up_axis=[0.0,1.0,0.0],tilt_radians=0.0)
        row.update(self.motion_changes)
        return row

    def ground(self,map_id,context):
        result=F.NativeControl.ground(self,map_id,context)
        result['space_id']=context['space_id']
        return result


class Phases(unittest.TestCase):
    def setUp(self):
        self.saved=dict((k,getattr(A,k)) for k in ('_run','_attempted','_closing','_Native'))
        A._run,A._attempted,A._closing=None,False,False
        self.native=Native()
        self.events,self.at=[],1.0
        self.record=lambda event,**row:self.events.append((event,row))
        A._Native=lambda settings:self.native
        self.frozen=(A.binding._run,A.movement._run,A.vehicle._run)
        self.space=1

    def tearDown(self):
        for key,value in self.saved.items():setattr(A,key,value)
        self.assertEqual(self.frozen,(A.binding._run,A.movement._run,A.vehicle._run))

    def arm(self):
        A.arm(self.record,{})
        A._run.clock=lambda:self.at

    def tick(self):
        result=A.advance(self.record)
        self.at+=1.0
        return result

    def binding(self):
        self.native.pair(A.note_map_drive_call,'updateOwnVehiclePosition',1445,300,
            dict(position=list(self.native.position),direction=[0.0]*3,speed=self.native.speed,rspeed=0.0),198)
        self.native.pair(A.note_map_drive_call,'__setOwnVehicleMatrixCallback',2951,300,{},151)

    def entity(self,kind,method,result=None,owner=None):
        self.native.cid+=1
        line,ends=A.ENTITY_METHODS[kind][method]
        fn=A.note_avatar_call if kind=='avatar' else A.note_vehicle_call
        owner=(300 if kind=='avatar' else 400) if owner is None else owner
        identity=A.vehicle.AVATAR_ID if kind=='avatar' else A.vehicle.VEHICLE_ID
        space=None if kind=='avatar' and method in ('__init__','onBecomePlayer') else self.space
        fn('call',method,line,-1,self.native.cid,owner,identity,space)
        fn('return',method,line,ends[-1] if result is None else result,self.native.cid,owner,identity,space)

    def enter(self,map_id=4):
        self.space=A._run.ride_index
        self.native.map_id=map_id
        self.native.value=avatar()
        self.native.value.update(arena_type_id=map_id,arena_unique_id=100+self.space,
            geometry_name=A.MAPS[map_id],geometry_path='spaces/'+A.MAPS[map_id],space_id=self.space)
        self.native.position=list(A.ROUTE_SPAWN) if map_id==1 else [-15.0,20.0,10.0]
        self.native.heading=0.0;self.native.speed=0.0
        self.native.target=True
        self.native.motion_changes={}
        self.native.item['roster']['avatar_ready']=True
        for name in ('__init__','onBecomePlayer','onEnterWorld'):
            self.entity('avatar',name)
        self.assertTrue(A.note_geometry_mapped(self.space,'spaces/'+A.MAPS[map_id]))
        self.entity('avatar','onSpaceLoaded')
        for _ in range(3):self.entity('avatar','__onInitStepCompleted',101)
        for name in ('__init__','prerequisites','onEnterWorld','startVisual'):self.entity('vehicle',name)
        self.entity('avatar','__onInitStepCompleted',640)
        self.binding()

    def begin(self,map_id=4):
        if A._run is None:self.arm()
        if A._run.phase=='between_rides':
            self.assertFalse(self.tick())
            self.assertEqual(A._run.phase,'initial')
        self.tick()
        self.assertEqual(A._run.phase,'waiting_world')
        self.enter(map_id)
        for _ in range(6):self.tick()
        self.assertEqual(A._run.phase,'route_active' if map_id==1 and not A._run.route_done else 'forward')

    def common_drive(self):
        self.assertEqual(A._run.phase,'forward')
        axis=self.native.motion()['forward_axis']
        self.native.position=[p+3.2*a for p,a in zip(self.native.position,axis)]
        self.binding();self.tick()
        self.native.heading+=0.2;self.tick();self.tick();self.tick();self.tick();self.tick()
        self.assertEqual(A._run.phase,'reverse')
        axis=self.native.motion()['forward_axis']
        self.native.position=[p-2.1*a for p,a in zip(self.native.position,axis)]
        self.binding();self.tick();self.tick();self.tick();self.tick();self.tick();self.tick()
        self.assertEqual(A._run.phase,'waiting_return')

    def returned(self):
        for kind,method in (('vehicle','stopVisual'),('vehicle','onLeaveWorld'),('avatar','onLeaveWorld'),('avatar','onBecomeNonPlayer')):
            self.entity(kind,method)
        self.native.value=account()
        self.assertTrue(A.note_geometry_mapped(2147483648+self.space,'spaces/hangar_v2'))
        for _ in range(5):result=self.tick()
        return result

    def route_success(self):
        self.assertEqual(A._run.phase,'route_active')
        # Supplied synthetic observations exercise policy, not physical success.
        destination=[A.ROUTE_TARGET[0],A.ROUTE_SPAWN[1],A.ROUTE_TARGET[2]-5.0]
        for index in range(1,28):
            self.native.position=[a+(b-a)*index/27.0 for a,b in zip(A.ROUTE_SPAWN,destination)]
            self.native.heading=math.atan2(A.ROUTE_TARGET[0]-self.native.position[0],A.ROUTE_TARGET[2]-self.native.position[2])
            self.native.speed=1.5
            self.binding();self.tick()
        self.native.speed=0.0
        self.binding()
        for _ in range(5):self.tick()
        self.assertEqual(A._run.phase,'route_hold')
        for _ in range(4):self.tick()
        self.assertEqual(A._run.phase,'route_backoff')
        axis=self.native.motion()['forward_axis']
        self.native.position=[p-5.1*a for p,a in zip(self.native.position,axis)]
        self.binding();self.tick()
        self.assertEqual(A._run.phase,'route_backoff')
        self.assertEqual(self.native.actions[-1],(2,True))
        self.native.position=[p-7.0*a for p,a in zip(self.native.position,axis)]
        self.binding();self.tick();self.tick();self.tick();self.tick();self.tick()
        self.assertEqual(A._run.phase,'forward')
        self.assertTrue(A._run.route_done)

    def test_two_random_maps_reenter_same_service_lifetime(self):
        self.begin(4);self.common_drive();self.assertFalse(self.returned())
        first=A._run.initial;seen=set(A._run.seen);sequence=A._run.sequence
        self.assertFalse(A._run.complete)
        self.begin(1);self.route_success();self.common_drive();self.assertTrue(self.returned())
        self.assertIs(A._run.initial,first)
        self.assertTrue(seen.issubset(A._run.seen));self.assertGreater(A._run.sequence,sequence)
        self.assertEqual(A._run.maps_seen,set((1,4)))
        self.assertEqual(A._run.spaces_seen,set((1,2)))
        self.assertEqual(len(self.native.requests),6)
        self.assertEqual(len(set(self.native.requests)),6)
        self.assertEqual([r['map_id'] for r in A._run.completed_rides],[4,1])
        self.assertEqual(len([e for e,r in self.events if e=='map_drive_acceptance_armed']),1)
        mapped=[r for e,r in self.events if e=='map_drive_acceptance_return_geometry']
        self.assertEqual([r['ride_index'] for r in mapped],[1,2])
        self.assertEqual([r['geometry']['space_id'] for r in mapped],[2147483649,2147483650])
        self.assertTrue(all(not r['hangar_ready_proven'] for r in mapped))

    def test_next_ride_resets_only_own_return_geometry(self):
        self.begin(4);self.common_drive();self.assertFalse(self.returned())
        self.assertIsNotNone(A._run.return_geometry)
        self.tick()
        self.assertIsNone(A._run.return_geometry)
        self.assertIsNone(A._run.pending_return_geometry)
        self.assertEqual(A._run.ride_index,2)

    def test_early_hangar_mapping_cannot_borrow_later_teardown(self):
        self.begin(4);self.common_drive()
        self.assertTrue(A.note_geometry_mapped(2147483649,'spaces/hangar_v2'))
        for kind,method in (('vehicle','stopVisual'),('vehicle','onLeaveWorld'),('avatar','onLeaveWorld'),('avatar','onBecomeNonPlayer')):
            self.entity(kind,method)
        self.native.value=account()
        with self.assertRaises(RuntimeError):self.tick()

    def test_hangar_mapping_cannot_cross_ride_epoch(self):
        self.begin(4);self.common_drive()
        for kind,method in (('vehicle','stopVisual'),('vehicle','onLeaveWorld'),('avatar','onLeaveWorld'),('avatar','onBecomeNonPlayer')):
            self.entity(kind,method)
        self.assertTrue(A.note_geometry_mapped(2147483649,'spaces/hangar_v2'))
        A._run.pending_return_geometry['ride_index']=2
        with self.assertRaises(RuntimeError):self.tick()

    def test_karelia_then_prohorovka_with_reused_python_owners(self):
        self.begin(1);self.route_success();self.common_drive();self.assertFalse(self.returned())
        self.begin(4);self.common_drive();self.assertTrue(self.returned())
        self.assertEqual(A._run.avatar_owner,300);self.assertEqual(A._run.vehicle_owner,400)
        self.assertEqual(len(self.native.grounds),2)

    def test_duplicate_map_requires_another_genuine_button_and_return(self):
        for _ in range(2):
            self.begin(4);self.common_drive();self.assertFalse(self.returned())
        self.assertEqual(self.native.actions.count('fight'),2)
        self.assertEqual(len(A._run.completed_rides),2)
        self.assertFalse(A._run.complete)
        self.begin(1);self.route_success();self.common_drive();self.assertTrue(self.returned())

    def test_eight_same_maps_never_force_missing_map_or_pass(self):
        for _ in range(7):
            self.begin(4);self.common_drive();self.assertFalse(self.returned())
        self.begin(4);self.common_drive()
        with self.assertRaises(RuntimeError):self.returned()
        self.assertEqual(self.native.actions.count('fight'),8)
        self.assertFalse(A._run.complete)

    def test_eighth_ride_can_supply_last_random_map_with_24_unique_pngs(self):
        for _ in range(7):
            self.begin(4);self.common_drive();self.assertFalse(self.returned())
        self.begin(1);self.route_success();self.common_drive();self.assertTrue(self.returned())
        self.assertEqual(A._run.ride_index,8)
        self.assertEqual(self.native.requests,list(A.SCREENSHOTS))
        final=[r for e,r in self.events if e=='map_drive_acceptance_complete']
        self.assertEqual(len(final),1)
        self.assertEqual(len(final[0]['rides']),8)
        self.assertEqual(final[0]['collision_acceptance'],'NOT_RUN_REQUIRES_INDEPENDENT_SERVER_GEOMETRY')

    def test_previous_call_id_cannot_satisfy_next_ride(self):
        self.begin(4);self.common_drive();self.returned();self.tick();self.tick()
        old=next(iter(A._run.seen))
        A.note_movement_call('call','moveVehicle',2130,-1,old,300,dict(flags=0,is_key_down=False))
        with self.assertRaises(RuntimeError):self.tick()

    def test_binding_callback_before_fresh_avatar_constructor_rejected(self):
        self.arm();self.tick();self.binding()
        with self.assertRaises(RuntimeError):self.tick()

    def test_avatar_constructor_before_original_fight_is_rejected(self):
        self.arm();self.entity('avatar','__init__')
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions,[])

    def test_late_previous_epoch_note_cannot_count_for_current_ride(self):
        self.arm();self.tick()
        self.native.cid+=1
        A.note_movement_call('call','moveVehicle',2130,-1,self.native.cid,300,dict(flags=0,is_key_down=False))
        A._run.notes[-1]['ride_index']=0
        with self.assertRaises(RuntimeError):self.tick()

    def test_old_space_cannot_be_reused_after_completed_ride(self):
        self.begin(4);self.common_drive();self.returned();self.tick();self.tick()
        self.assertFalse(A.note_geometry_mapped(1,'spaces/05_prohorovka'))
        with self.assertRaises(RuntimeError):self.tick()

    def test_world_space_change_inside_ride_rejected(self):
        self.begin(4);self.native.value['space_id']=99
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_original_lifecycle_space_must_equal_actual_mapping(self):
        self.arm();self.tick();self.enter(4)
        for row in A._run.notes:
            if row['kind']=='vehicle' and row['method']=='startVisual':row['data']['space_id']=99
        with self.assertRaises(RuntimeError):self.tick()

    def test_arena_unique_id_cannot_repeat_on_second_space(self):
        self.begin(4);self.common_drive();self.returned();self.tick();self.tick();self.enter(4)
        self.native.value['arena_unique_id']=101
        with self.assertRaises(RuntimeError):self.tick()

    def test_account_resources_cannot_drift_between_rides(self):
        self.begin(4);self.common_drive();self.returned()
        self.native.public['resources']['credits']-=1
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions.count('fight'),1)

    def test_between_rides_selection_is_not_silently_repaired(self):
        self.begin(4);self.common_drive();self.returned();self.tick()
        self.native.account_value['selected_inventory_id']=2
        with self.assertRaises(RuntimeError):self.tick()
        self.assertNotIn('select_ms1',self.native.actions)

    def test_no_new_button_same_iteration_as_return_png(self):
        self.begin(4);self.common_drive();self.returned()
        self.assertEqual(self.native.actions.count('fight'),1)
        self.tick()
        self.assertEqual(self.native.actions.count('fight'),1)
        self.tick()
        self.assertEqual(self.native.actions.count('fight'),2)

    def test_pending_old_callback_blocks_next_ride(self):
        self.begin(4);self.common_drive();self.returned()
        self.native.cid+=1
        A.note_movement_call('call','moveVehicle',2130,-1,self.native.cid,300,dict(flags=0,is_key_down=False))
        with self.assertRaises(RuntimeError):self.tick()

    def test_screenshots_use_latest_actual_iteration_and_unique_ride_names(self):
        self.begin(4);self.common_drive();self.returned()
        for event,row in self.events:
            if event not in ('map_drive_acceptance_screenshot','map_drive_acceptance_screenshot_request'):continue
            matching=[r for e,r in self.events if e in ('map_drive_acceptance_state','map_drive_acceptance_return_state')
                      and r['advance']==row['advance'] and r['ride_index']==row['ride_index']]
            self.assertEqual(len(matching),1)
            self.assertEqual(matching[0]['observed_at'],row['observed_at'])
        self.assertEqual(self.native.requests,list(A.SCREENSHOTS[:3]))

    def test_route_requires_measured_spawn(self):
        self.arm();self.tick();self.enter(1)
        self.native.position[0]+=10.0
        with self.assertRaises(RuntimeError):
            for _ in range(6):self.tick()
        self.assertNotIn((1,True),self.native.actions)

    def test_route_hysteresis_uses_current_filter_not_initial_server_speed(self):
        self.begin(1)
        self.native.speed=3.75627851
        self.native.motion_changes['speed_info']=[1.68183446,0.0,0.0,0.0]
        self.binding();self.tick()
        row=[r for e,r in self.events if e=='map_drive_acceptance_route_sample'][-1]
        self.assertNotEqual(row['flags'],0)
        self.assertEqual(row['speed_source'],'original_WGVehicleFilter.speedInfo[0]')
        self.assertEqual(row['filter_speed_info'][0],1.68183446)
        self.assertEqual(row['last_server_speeds'][0],3.75627851)
        self.assertFalse(row['last_server_speeds_used_for_control'])
        self.assertNotEqual(self.native.actions[-1],(0,False))
        self.native.speed=1.2
        self.native.motion_changes['speed_info']=[3.0,0.0,0.0,0.0]
        self.binding();self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_entity_only_route_accepts_stale_initial_callback_but_uses_current_filter(self):
        self.begin(1)
        self.native.binding_changes['last_server_speeds']=[0.0,0.0]
        cid=A._run.latest_update['returned']['call_id']
        for index in range(10):
            self.native.motion_changes['speed_info']=[2.1,0.0,0.0,0.0]
            self.tick()
        row=[r for e,r in self.events if e=='map_drive_acceptance_route_sample'][-1]
        self.assertEqual(row['own_update_call_id'],cid)
        self.assertGreater(row['own_update_age_seconds'],10.0)
        self.assertEqual(row['speed'],2.1)
        self.assertEqual(row['flags'],0)
        self.assertEqual(row['last_server_speeds'],[0.0,0.0])

    def test_filter_route_rejects_boolean_nonfinite_or_wrong_shape(self):
        self.begin(1)
        for speeds in ([True,0.0,0.0,0.0],[float('nan'),0.0,0.0,0.0],[0.0]*3):
            motion=self.native.motion();motion['speed_info']=speeds
            count=len(self.native.actions)
            with self.assertRaises((RuntimeError,ValueError)):
                A._run._route_step(motion,self.native.binding(),self.at)
            self.assertEqual(len(self.native.actions),count)

    def test_route_raw_speed_requires_latest_same_owner_callback(self):
        self.begin(1)
        self.native.binding_changes['last_server_speeds']=[3.0,0.0]
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_route_raw_speed_rejects_missing_or_nonfinite(self):
        self.begin(1)
        self.native.binding_changes['last_server_speeds']=[float('nan'),0.0]
        with self.assertRaises((RuntimeError,ValueError)):self.tick()

    def test_route_transient_provider_retries_without_stale_steering(self):
        self.begin(1);self.native.target=False
        count=len(self.native.actions)
        self.assertFalse(self.tick())
        self.assertEqual(A.next_observation_delay(),0.1)
        self.assertEqual(len(self.native.actions),count)
        self.at-=0.9;self.native.target=True;self.binding()
        self.assertFalse(self.tick())
        self.assertEqual(A.next_observation_delay(),1.0)
        self.assertEqual(len(self.native.actions),count+1)
        sample=[r for e,r in self.events if e=='map_drive_acceptance_route_sample'][-1]
        self.assertAlmostEqual(sample['interval_seconds'],1.1)

    def test_route_provider_retry_never_extends_actual_one_point_five_bound(self):
        self.begin(1);self.native.target=False
        last=A._run.route.last_at
        for delta in (1.0,1.1,1.2,1.3,1.4):
            self.at=last+delta;self.tick()
            self.assertEqual(A.next_observation_delay(),0.1)
        self.at=last+1.51
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_route_early_ready_does_not_issue_command_before_one_second(self):
        self.begin(1);count=len(self.native.actions)
        last=A._run.route.last_at;self.at=last+0.9
        self.assertFalse(self.tick())
        self.assertEqual(len(self.native.actions),count)
        self.assertEqual(A.next_observation_delay(),0.1)
        self.at=last+1.1;self.tick()
        self.assertEqual(len(self.native.actions),count+1)

    def test_route_retry_count_is_bounded_and_unarmed_delay_is_one(self):
        self.assertEqual(A.next_observation_delay(),1.0)
        self.begin(1);self.native.target=False
        A._run.route_retries=A.MAX_ROUTE_RETRIES
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_route_late_sample_stops_original_command(self):
        self.begin(1);self.at+=1.0
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_excessive_native_body_tilt_fails_and_stops(self):
        self.begin(1);self.native.motion_changes['tilt_radians']=A.ROUTE_MAX_TILT+0.01
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_route_backoff_needs_twelve_metres_not_only_reverse_command(self):
        self.begin(1);self.route_success()
        rows=[r for e,r in self.events if e=='map_drive_acceptance_progress' and r['kind']=='route_backoff']
        self.assertEqual(len(rows),1);self.assertGreaterEqual(rows[0]['metres'],12.0)
        route_stops=[r for e,r in self.events if e=='map_drive_acceptance_hold' and r['kind'].startswith('route_')]
        self.assertEqual(len(route_stops),2)
        self.assertGreaterEqual(route_stops[0]['observed_at']-route_stops[0]['began_at'],3.0)
        self.assertGreaterEqual(route_stops[1]['observed_at']-route_stops[1]['began_at'],3.0)

    def test_karelia_clearance_keeps_boundary_backoff_and_action_budget(self):
        self.assertEqual(A.ROUTE_BACKOFF_METRES,12.0)
        self.assertEqual(A.BOUNDARY_BACKOFF_METRES,5.0)
        self.assertEqual(A.MAX_ACTION_SECONDS,30.0)

    def test_original_pre_ready_false_still_waits_then_true_starts(self):
        self.arm();self.tick();self.enter(4)
        self.native.item['roster']['avatar_ready']=False
        self.native.motion_changes.update(period=1,is_on_arena=False)
        self.native.target=False
        self.assertFalse(self.tick());self.assertEqual(A._run.phase,'waiting_world')
        self.native.item['roster']['avatar_ready']=True
        self.native.motion_changes.update(period=3,is_on_arena=True);self.native.target=True
        self.binding();self.tick();self.assertEqual(A._run.phase,'baseline')

    def test_global_and_per_ride_budgets_fail_closed(self):
        self.arm();A._run.ride_advances=A.MAX_RIDE_ADVANCES
        with self.assertRaises(RuntimeError):self.tick()
        self.at+=1.0;A._run.ride_advances=0;A._run.advances=A.MAX_ADVANCES
        with self.assertRaises(RuntimeError):self.tick()

    def test_frozen_callback_maps_not_modified(self):
        self.assertIsNot(A.ENTITY_METHODS,A.vehicle.CALLBACKS)
        self.assertIsNot(A.ENTITY_METHODS['avatar'],A.vehicle.CALLBACKS['avatar'])

    def test_captured_late_stage_pair_cannot_skip_new_ride_world(self):
        self.begin(4);self.common_drive();self.returned();self.tick();self.tick()
        self.entity('avatar','onLeaveWorld')
        with self.assertRaises(RuntimeError):self.tick()

    def test_callback_budget_latches_without_raising_from_profiler(self):
        self.arm();A._run.sequence=A.MAX_NOTES
        self.assertFalse(A.note_movement_call('call','moveVehicle',2130,-1,1234,300,dict(flags=0,is_key_down=False)))
        with self.assertRaises(RuntimeError):self.tick()

    def test_service_initialization_exactly_once_after_three_rides(self):
        self.arm()
        self.native.initialize=lambda:(_ for _ in ()).throw(AssertionError('unexpected reinitialization'))
        for _ in range(2):
            self.begin(4);self.common_drive();self.returned()
        self.begin(1)
        self.assertEqual(len([r for e,r in self.events if e=='map_drive_acceptance_armed']),1)

    def fire_sample(self, delay=0.02):
        sampler=A._run.sampler
        requested,callback=self.native.scheduled.pop(sampler.callback_id)
        self.assertEqual(requested,A.SAMPLE_DELAY)
        self.at+=delay
        callback()

    def test_sampler_skips_entire_long_route_then_starts_before_basic_forward(self):
        self.begin(1)
        for _ in range(46):self.tick()
        self.assertIsNone(A._run.sampler)
        self.assertEqual(self.native.sample_reads,0)
        self.assertEqual(self.native.scheduled,{})
        self.route_success()
        self.assertGreater(A._run.sampler.started_at-A._run.route.started_at,45.0)
        self.assertEqual(A._run.sampler_count,1)
        self.assertEqual(A._run.sampler.count,1)
        sample=next(i for i,(e,r) in enumerate(self.events) if e=='map_drive_acceptance_sample')
        forward=next(i for i,(e,r) in enumerate(self.events)
                     if e=='map_drive_acceptance_action' and r['action']=='forward' and r['moment']=='begin')
        self.assertLess(sample,forward)

    def test_sampler_new_instance_each_ride_retains_global_count_and_old_callback_is_inert(self):
        self.begin(4);self.fire_sample()
        old=A._run.sampler;old_count=old.count
        self.common_drive();self.returned();self.tick()
        self.assertIsNone(A._run.sampler)
        self.assertIsNone(A._run.sample_last_update)
        self.assertIsNone(A._run.sample_last_deferred)
        self.assertEqual(A._run.total_samples,old_count)
        self.begin(4)
        current=A._run.sampler;reads=self.native.sample_reads;token=current.callback_id
        old._tick()
        self.assertEqual(self.native.sample_reads,reads)
        self.assertEqual(current.callback_id,token)
        self.assertIsNot(current,old)
        self.assertEqual(current.ride_index,2)
        self.assertEqual(A._run.total_samples,old_count+1)
        self.assertEqual(A._run.sampler_count,2)
        starts=[r for e,r in self.events if e=='map_drive_acceptance_sampler_start']
        self.assertEqual([r['ride_index'] for r in starts],[1,2])
        self.assertEqual([r['sampler_index'] for r in starts],[1,2])

    def test_sampler_active_cannot_follow_reused_owner_into_new_ride(self):
        self.begin(4);sampler=A._run.sampler;reads=self.native.sample_reads
        A._run.ride_index=2
        self.fire_sample()
        self.assertIn('outlived',sampler.error)
        self.assertEqual(self.native.sample_reads,reads)

    def test_per_ride_sample_budget_fails_before_new_native_read(self):
        self.begin(4);reads=self.native.sample_reads
        A._run.sampler.count=A.MAX_SAMPLES
        self.fire_sample()
        self.assertIn('budget exhausted',A._run.sampler.error)
        self.assertEqual(self.native.sample_reads,reads)
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_global_sample_budget_is_not_reset_per_ride(self):
        self.begin(4);reads=self.native.sample_reads
        A._run.total_samples=A.MAX_TOTAL_SAMPLES
        self.fire_sample()
        self.assertIn('budget exhausted',A._run.sampler.error)
        self.assertEqual(self.native.sample_reads,reads)

    def test_sampler_45_second_window_remains_strict(self):
        self.begin(4);reads=self.native.sample_reads
        self.at=A._run.sampler.started_at+45.0
        self.fire_sample()
        self.assertIn('budget exhausted',A._run.sampler.error)
        self.assertEqual(self.native.sample_reads,reads)

    def test_signed_callback_handles_pass_unchanged_and_stop_is_once(self):
        self.begin(4)
        original=self.native.schedule_sample
        def schedule(delay,callback):
            self.native.scheduled[-2147483647]=(delay,callback)
            return -2147483647
        self.native.schedule_sample=schedule
        self.fire_sample()
        self.assertEqual(A._run.sampler.callback_id,-2147483647)
        self.assertIsNone(A._run.sampler.error)
        sampler=A._run.sampler
        A.fini(self.record);A.fini(self.record)
        self.assertEqual(self.native.cancelled[-1],-2147483647)
        self.assertTrue(sampler.stop_recorded)
        self.assertEqual(len([r for e,r in self.events if e=='map_drive_acceptance_sampler_stop']),1)

    def test_cancel_failure_keeps_pending_handle_and_fini_retries(self):
        self.begin(4);sampler=A._run.sampler;token=sampler.callback_id
        original=self.native.cancel_sample
        self.native.cancel_sample=lambda handle:(_ for _ in ()).throw(RuntimeError('cancel failed'))
        with self.assertRaises(RuntimeError):sampler.stop('diagnostic_error')
        self.assertEqual(sampler.callback_id,token)
        self.assertFalse(sampler.stop_recorded)
        self.native.cancel_sample=original
        A.fini(self.record)
        self.assertTrue(sampler.stop_recorded)
        self.assertIsNone(sampler.callback_id)

    def test_bad_scheduled_handle_ownership_survives_validation_failure(self):
        self.begin(4)
        token=2147483648
        def schedule(delay,callback):
            self.native.scheduled[token]=(delay,callback)
            return token
        self.native.schedule_sample=schedule
        self.fire_sample()
        self.assertEqual(A._run.sampler.callback_id,token)
        self.assertIn('signed int32',A._run.sampler.error)
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.cancelled[-1],token)
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_no_sampler_can_be_started_twice_in_one_ride(self):
        self.begin(4);count=self.native.sample_reads
        with self.assertRaises(RuntimeError):
            A._run._start_basic_drive(self.native.position,[0.0,0.0,1.0],self.at)
        self.assertEqual(self.native.sample_reads,count)

    def test_live_sampler_blocks_epoch_reset(self):
        self.begin(4)
        A._run.moving=False
        with self.assertRaises(RuntimeError):A._run._next_ride()
        self.assertEqual(A._run.ride_index,1)


class RoutePolicy(unittest.TestCase):
    def make(self):return A._RoutePlan(list(A.ROUTE_SPAWN),0.0,1.0)
    def test_hysteresis_and_exact_original_turn_flags(self):
        route=self.make();p=list(A.ROUTE_SPAWN)
        self.assertEqual(route.sample(p,0.0,0.0,0.0,1.0)['flags'],5)
        self.assertEqual(route.sample(p,0.0,2.1,0.0,2.0)['flags'],0)
        self.assertEqual(route.sample(p,0.0,1.5,0.0,3.0)['flags'],0)
        self.assertEqual(route.sample(p,-0.5,1.2,0.0,4.0)['flags'],9)

    def test_stationary_at_spawn_is_not_collision(self):
        route=self.make()
        for i in range(10):self.assertFalse(route.sample(list(A.ROUTE_SPAWN),0.0,0.0,0.0,1.0+i)['stop_candidate'])

    def test_preceding_brake_is_not_collision_interval(self):
        route=self.make();position=[A.ROUTE_TARGET[0],22.0,A.ROUTE_TARGET[2]-5]
        route.sample(list(A.ROUTE_SPAWN),0.0,3.0,0.0,1.0)
        row=route.sample(position,0.0,0.0,0.0,2.0)
        self.assertEqual(row['previous_flags'],0);self.assertEqual(row['stalled_intervals'],0)

    def test_five_consecutive_nonzero_stalled_intervals_required(self):
        route=self.make();position=[A.ROUTE_TARGET[0],22.0,A.ROUTE_TARGET[2]-5]
        route.sample(position,0.0,0.0,0.0,1.0)
        for i in range(1,5):self.assertFalse(route.sample(position,0.0,0.0,0.0,1.0+i)['stop_candidate'])
        final=route.sample(position,0.0,0.0,0.0,6.0)
        self.assertTrue(final['stop_candidate']);self.assertEqual(final['flags'],0)

    def test_time_tilt_nonfinite_and_budget_rejected(self):
        for key,value in (('speed',float('nan')),('tilt',A.ROUTE_MAX_TILT+0.01)):
            route=self.make();args=dict(position=list(A.ROUTE_SPAWN),heading=0.0,speed=0.0,tilt=0.0,now=1.0);args[key]=value
            with self.assertRaises((ValueError,RuntimeError)):route.sample(**args)
        route=self.make();route.steps=A.MAX_ROUTE_STEPS
        with self.assertRaises(RuntimeError):route.sample(list(A.ROUTE_SPAWN),0.0,0.0,0.0,1.0)


# These exercise real unchanged Python getter bodies/source hashes under the
# candidate receiver, including the Python2 unbound-method boundary.
class OriginalSource(unittest.TestCase):
    @unittest.skipIf(sys.version_info[0]<3,'host Python3 original static reader only')
    def test_new_epoch_lifecycle_and_route_plan_are_source_bound(self):
        from pathlib import Path
        import hashlib
        sys.path.insert(0,str(Path(F.ROOT)/'tools'))
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,disassemble,opcode_table
        root=Path(F.ROOT)
        route=root/'local/evidence/20261005-p02-map-drive/data/current-spawn-route-1hz-review-01/ALGORITHM.md'
        self.assertEqual(hashlib.sha256(route.read_bytes()).hexdigest(),A.ROUTE_PLAN_SHA256)
        path=config()[1]['original_client_root']/'res/scripts/client/Avatar.pyc'
        raw=read_limited(path,1048576)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e')
        codes=dict(records(parse_pyc(raw)))
        table=opcode_table(read_limited(root/'local/vendor/cpython-2.7.3/opcode.py',32768).decode())
        for method,line,offset in (('__init__',110,212),('onBecomePlayer',147,882)):
            code=codes['<module>.PlayerAvatar.'+method]
            self.assertEqual(code['firstlineno'],line)
            self.assertEqual(A.ENTITY_METHODS['avatar'][method],(line,(offset,)))
            self.assertEqual(next(r for r in disassemble(code,table) if r['offset']==offset)['opname'],'RETURN_VALUE')


if __name__=='__main__':unittest.main()
