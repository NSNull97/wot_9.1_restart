# -*- coding: utf-8 -*-
"""Synthetic boundary tests plus a read-only original-code audit, not native proof."""
import copy
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import map_drive_scenario as drive
import test_arena_movement_scenario as prior
import test_arena_vehicle_scenario as world


class NativeControl(prior.NativeControl):
    def __init__(self):
        prior.NativeControl.__init__(self)
        self.map_drive_sources = []
        self.binding_overrides, self.physics_overrides = {}, {}
        self.physics_reads = 0

    def binding(self):
        row = dict(present=True, owner_id=300, vehicle_owner_id=400,
            attached_vehicle_id=drive.vehicle.VEHICLE_ID, attached_owner_id=400,
            attached_is_own_vehicle=True, filter_is_original_wg_vehicle=True,
            target_present=True, target_python_identity_equal=True, provider_owner_id=500,
            target_owner_id=600, body_owner_id=600, avatar_position=[0.0]*3,
            own_matrix_position=list(self.position), body_matrix_position=list(self.position),
            target_position=list(self.position), last_server_speeds=[0.0,0.0])
        row.update(self.binding_overrides)
        return row

    def physics(self):
        self.physics_reads += 1
        row = dict(vehicle_id=drive.vehicle.VEHICLE_ID, vehicle_owner_id=400,
            type_compact_descr=3329, compact_descr_sha256='a'*64,
            state_assigned=False, physics_created=False, historical_physics_acceptance='NOT_RUN')
        row.update(self.physics_overrides)
        return row

    def ground_samples(self):
        return dict(space_id=1,player_owner_id=300,samples=[],comparison_acceptance='NOT_RUN')

    def move(self, flags, is_key_down, owner):
        self.commands.append((flags, is_key_down, owner))
        if flags in self.move_fail:
            raise RuntimeError('synthetic original command failure')
        if not self.omit_notes:
            self.call_id += 1
            data = dict(flags=flags, is_key_down=is_key_down)
            drive.note_movement_call('call', 'moveVehicle', 2130, -1, self.call_id, owner, data)
            drive.note_movement_call('return', 'moveVehicle', 2130,
                                     12 if self.early_return else 345, self.call_id, owner, data)


class MapDriveTests(unittest.TestCase):
    def setUp(self):
        keys = ('_run','_native','_arm_attempted','_closing','_finished_cleanup','_cleanup_errors','_Native')
        self.saved = dict((key,getattr(drive,key)) for key in keys)
        drive._run = drive._native = None
        drive._arm_attempted = drive._closing = drive._finished_cleanup = False
        drive._cleanup_errors = []
        self.native, self.events, self.at = NativeControl(), [], 1.0
        self.record = lambda name, **row: self.events.append((name,row))
        drive._Native = lambda record, settings: self.native
        self.cleanup, self.cleanup_fail = [], set()
        self.old_cleanup = (drive.arena_bootstrap.fini_before_entities, drive.arena_bootstrap.fini_after_entities)
        drive.arena_bootstrap.fini_before_entities = self.stage('before')
        drive.arena_bootstrap.fini_after_entities = self.stage('after')
        self.q_globals = (drive.movement._run, drive.movement._native, drive.movement.SCREENSHOTS)

    def tearDown(self):
        for key,value in self.saved.items():
            setattr(drive,key,value)
        drive.arena_bootstrap.fini_before_entities, drive.arena_bootstrap.fini_after_entities = self.old_cleanup
        self.assertEqual(self.q_globals, (drive.movement._run, drive.movement._native, drive.movement.SCREENSHOTS))

    def stage(self, name):
        def run():
            self.cleanup.append(name)
            if name in self.cleanup_fail:
                raise ValueError('synthetic ' + name)
        return run

    def arm(self):
        drive.arm(self.record,{})
        drive._run.clock = lambda: self.at
        self.native.value = world.avatar()

    def entities(self):
        def pair(kind,method,identity,result=None):
            line,returns = drive.vehicle.CALLBACKS[kind][method]
            fun = drive.note_avatar_call if kind == 'avatar' else drive.note_vehicle_call
            owner = 300 if kind == 'avatar' else 400
            entity = drive.vehicle.AVATAR_ID if kind == 'avatar' else drive.vehicle.VEHICLE_ID
            fun('call',method,line,-1,identity,owner,entity,1)
            fun('return',method,line,returns[-1] if result is None else result,identity,owner,entity,1)
        pair('avatar','onEnterWorld',1)
        pair('avatar','__onInitStepCompleted',2,101)
        pair('avatar','__onInitStepCompleted',3,101)
        drive.note_geometry_mapped(1,'spaces/01_karelia')
        pair('avatar','onSpaceLoaded',4)
        pair('avatar','__onInitStepCompleted',5,101)
        pair('vehicle','__init__',6)
        pair('vehicle','prerequisites',7)
        pair('vehicle','onEnterWorld',8)
        pair('vehicle','startVisual',9)
        pair('avatar','__onInitStepCompleted',10,640)

    def pair(self, method='updateOwnVehiclePosition', cid=200, offset=None, owner=300, data=None):
        line,returns = drive.RETURNS[method]
        if data is None:
            data = {} if method.startswith('__') else dict(position=list(self.native.position),
                                                           direction=[0.0]*3,speed=0.0,rspeed=0.0)
        self.assertTrue(drive.note_map_drive_call('call',method,line,-1,cid,owner,data))
        self.assertTrue(drive.note_map_drive_call('return',method,line,returns[0] if offset is None else offset,cid,owner,data))

    def bind(self, cid=200):
        self.pair(cid=cid)
        self.pair('__setOwnVehicleMatrixCallback',cid+1)

    def tick(self):
        self.native.at = self.at
        result = drive.advance(self.record)
        self.at += 1.0
        return result

    def begin(self):
        self.arm(); self.entities(); self.bind()
        for _ in range(3):self.assertFalse(self.tick())
        self.assertEqual(self.native.requested,[drive.SCREENSHOTS[0]])
        self.assertFalse(self.tick())
        self.assertEqual(self.native.commands,[(1,True,300)])

    def target(self):
        self.native.position = list(drive.TARGET)
        self.bind(220)
        self.assertFalse(self.tick())
        self.assertEqual(self.native.commands,[(1,True,300),(0,False,300)])

    def finish(self):
        self.target(); self.assertFalse(self.tick()); self.assertFalse(self.tick()); self.assertTrue(self.tick())

    def test_unarmed_normal_passive(self):
        self.assertFalse(drive.advance(self.record))
        self.assertFalse(drive.note_map_drive_call(None,[],None,None,None,None,object()))
        self.assertFalse(drive.note_movement_call(None,[],None,None,None,None,object()))
        self.assertEqual(self.events,[])

    def test_three_native_links_commands_hold_and_png_required(self):
        self.begin(); self.finish()
        event,row = self.events[-1]
        self.assertEqual(event,'map_drive_complete')
        self.assertEqual(row['own_matrix_delta'],[0.0,0.0,2.0])
        self.assertEqual(row['body_matrix_delta'],[0.0,0.0,2.0])
        self.assertGreaterEqual(row['hold_seconds'],2.0)
        self.assertEqual(row['binding_call_id'],221)
        self.assertEqual(row['update_call_id'],220)
        self.assertEqual(row['full_drive_acceptance'],'NOT_RUN')
        self.assertFalse(row['compatibility_acceptance'])
        self.assertEqual(self.native.physics_reads,1)
        self.assertEqual(self.native.requested,list(drive.SCREENSHOTS))
        self.assertTrue(self.tick())
        self.assertEqual(len(self.native.commands),2)
        self.assertFalse(any(name.startswith('arena_movement_') for name,row in self.events))

    def test_foreign_account_before_initialization(self):
        self.native.identity['database_id'] = 2
        self.assertRaises(RuntimeError,self.arm)
        self.assertEqual(self.native.initialized,0)

    def test_arm_one_shot(self):
        self.arm(); self.assertRaises(RuntimeError,drive.arm,self.record,{})

    def test_native_attachments_without_original_callbacks_not_accepted(self):
        self.arm(); self.entities()
        for _ in range(5):self.assertFalse(self.tick())
        self.assertEqual(self.native.commands,[])
        self.assertEqual(self.native.requested,[])

    def test_deferred_retry_is_observation_not_binding_proof(self):
        self.arm(); self.entities(); self.pair(); self.pair('__setOwnVehicleMatrixCallback',201,179)
        self.assertFalse(self.tick())
        self.assertIsNone(drive._run.latest_bound)
        self.assertEqual(len(drive._run.binding_pairs),2)

    def test_success_without_original_update_rejected(self):
        self.arm(); self.entities(); self.pair('__setOwnVehicleMatrixCallback',201)
        self.assertRaises(RuntimeError,self.tick)

    def test_latest_update_requires_new_deferred_completion(self):
        self.arm(); self.entities(); self.bind(); self.pair(cid=202)
        self.assertFalse(self.tick())
        self.assertIsNone(drive._run.latest_bound)

    def test_attachment_fallback_not_equivalent_to_native_vehicle(self):
        self.arm(); self.entities(); self.bind()
        self.native.binding_overrides.update(attached_vehicle_id=None,attached_owner_id=None,attached_is_own_vehicle=False)
        for _ in range(3):self.assertFalse(self.tick())
        self.assertEqual(self.native.requested,[])

    def test_foreign_attachment_rejected(self):
        self.arm(); self.entities(); self.bind()
        self.native.binding_overrides['attached_vehicle_id'] = 42
        self.assertRaises(RuntimeError,self.tick)

    def test_distinct_native_wrappers_require_callbacks_and_dynamic_follow(self):
        self.native.binding_overrides.update(target_python_identity_equal=False,target_owner_id=601)
        self.begin(); self.finish()
        row=[r for n,r in self.events if n=='map_drive_complete'][-1]
        self.assertEqual(row['own_matrix_delta'],[0.0,0.0,2.0])
        self.assertEqual(row['body_matrix_delta'],[0.0,0.0,2.0])
        states=[r for n,r in self.events if n=='map_drive_state']
        self.assertTrue(all(r['binding']['target_python_identity_equal'] is False for r in states))

    def test_missing_target_wrapper_identity_rejected(self):
        self.arm(); self.entities(); self.bind()
        self.native.binding_overrides['target_owner_id'] = None
        self.assertRaises(RuntimeError,self.tick)

    def test_distinct_wrappers_without_success151_not_binding_proof(self):
        self.arm(); self.entities(); self.pair()
        self.native.binding_overrides.update(target_python_identity_equal=False,target_owner_id=601)
        for _ in range(3): self.assertFalse(self.tick())
        self.assertEqual(self.native.commands,[])
        self.assertEqual(self.native.requested,[])

    def test_semantic_target_mismatch_rejected_even_with_success151(self):
        self.arm(); self.entities(); self.bind()
        wrong=list(drive.ORIGIN);wrong[0]+=0.01
        self.native.binding_overrides.update(target_python_identity_equal=False,target_owner_id=601,
                                            target_position=wrong)
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands,[])

    def test_actual_world_exports_do_not_require_binding_or_forward(self):
        self.arm();self.entities()
        self.native.binding_overrides.update(target_python_identity_equal=False,target_owner_id=601)
        self.assertFalse(self.tick());self.assertFalse(self.tick())
        names=[n for n,r in self.events]
        for name in ('map_drive_export_context','map_drive_physics','map_drive_ground'):
            self.assertEqual(names.count(name),1)
        self.assertLess(names.index('map_drive_ground'),names.index('map_drive_state'))
        self.assertEqual(self.native.physics_reads,1)
        self.assertEqual(self.native.commands,[])

    def test_world_exports_preserved_before_bad_matrix_read(self):
        self.arm();self.entities();self.bind()
        def broken(): raise ValueError('synthetic invalid matrix getter')
        self.native.motion=broken
        self.assertRaises(ValueError,self.tick)
        self.assertEqual(self.native.physics_reads,1)
        self.assertTrue(any(n=='map_drive_ground' for n,r in self.events))
        self.assertFalse(any(n=='map_drive_complete' for n,r in self.events))

    def test_no_world_no_geometry_exports(self):
        self.arm()
        self.assertFalse(self.tick())
        self.assertEqual(self.native.physics_reads,0)
        self.assertFalse(any(n in ('map_drive_export_context','map_drive_ground') for n,r in self.events))

    def test_static_own_matrix_cannot_complete_entity_motion(self):
        self.begin(); self.native.position = list(drive.TARGET)
        self.native.binding_overrides['own_matrix_position'] = list(drive.ORIGIN)
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands[-1],(0,False,300))
        self.assertFalse(drive._run.complete)

    def test_vertical_provider_difference_remains_observed_not_physics_pass(self):
        self.arm(); self.entities(); self.bind()
        value=list(drive.ORIGIN);value[1]+=0.01
        self.native.binding_overrides['own_matrix_position']=value
        self.native.overrides['own_matrix_position']=value
        self.assertFalse(self.tick())
        row=[r for n,r in self.events if n=='map_drive_state'][-1]
        self.assertEqual(row['binding']['own_matrix_position'][1]-row['binding']['body_matrix_position'][1],
                         value[1]-drive.ORIGIN[1])

    def test_actual_output_y_not_required_equal_wire_seed(self):
        self.native.position[1]-=0.07084
        self.begin(); self.native.position=list(drive.TARGET);self.native.position[1]-=0.07084
        self.bind(220);self.assertFalse(self.tick());self.tick();self.tick();self.assertTrue(self.tick())

    def test_foreign_physics_export_rejected(self):
        self.arm();self.entities();self.bind();self.native.physics_overrides['compact_descr_sha256']='c'*64
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands,[])

    def test_only_model_reaches_target_no_stop(self):
        self.begin();self.native.overrides['model_matrix_position']=list(drive.TARGET)
        self.assertFalse(self.tick())
        self.assertFalse(drive._run.stop_attempted)

    def test_own_target_lags_entity_does_not_stop_prematurely(self):
        self.begin();self.native.position=list(drive.TARGET)
        lag=list(drive.TARGET);lag[2]-=0.1
        self.native.overrides['own_matrix_position']=lag
        self.native.binding_overrides.update(own_matrix_position=lag,body_matrix_position=lag,target_position=lag)
        self.assertFalse(self.tick());self.assertFalse(drive._run.stop_attempted)

    def test_stop_requires_passive_transport_return(self):
        self.begin();self.native.position=list(drive.TARGET);self.native.early_return=True
        self.assertRaises(RuntimeError,self.tick)
        self.assertIsNone(drive._run.stop_pair)

    def test_actual_startup_stop_12_is_only_observation(self):
        self.arm();self.entities();self.bind();data=dict(flags=0,is_key_down=False)
        drive.note_movement_call('call','moveVehicle',2130,-1,150,300,data)
        drive.note_movement_call('return','moveVehicle',2130,12,150,300,data)
        self.assertFalse(self.tick());self.assertIsNone(drive._run.stop_pair)

    def test_outside_path_triggers_one_original_stop(self):
        self.begin();self.native.position[0]+=0.1
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands[-1],(0,False,300))

    def test_binding_loss_after_forward_stops(self):
        self.begin();self.native.binding_overrides['attached_is_own_vehicle']=False
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands[-1],(0,False,300))

    def pending(self):
        self.pair(cid=240)
        self.native.binding_overrides.update(target_present=False,target_owner_id=None,
                                            target_python_identity_equal=False,target_position=None)

    def test_original_deferred_window_not_fabricated_ready(self):
        self.begin();self.pending()
        self.assertFalse(self.tick())
        row=[r for n,r in self.events if n=='map_drive_state'][-1]
        self.assertFalse(row['binding_ready'])
        self.assertTrue(row['original_binding_callback_pending'])
        self.assertFalse(drive._run.stop_attempted)
        self.pair('__setOwnVehicleMatrixCallback',241)
        self.native.binding_overrides.clear()
        self.assertFalse(self.tick())

    def test_deferred_window_not_unbounded(self):
        self.begin();self.pending()
        for _ in range(3):self.assertFalse(self.tick())
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands[-1],(0,False,300))

    def test_deferred_window_does_not_hide_outside_pose(self):
        self.begin();self.pending();self.native.position[0]+=1
        self.assertRaises(RuntimeError,self.tick)
        self.assertFalse(drive._run.complete)

    def test_deferred_window_does_not_hide_period_change(self):
        self.begin();self.pending();self.native.overrides['period']=4
        self.assertRaises(RuntimeError,self.tick)

    def test_deferred_window_does_not_erase_baseline_gap(self):
        self.arm();self.entities();self.bind();self.tick();self.pending()
        self.assertFalse(self.tick())
        self.assertIsNone(drive._run.ready_since)
        self.pair('__setOwnVehicleMatrixCallback',241);self.native.binding_overrides.clear()
        self.tick();self.tick()
        self.assertEqual(self.native.requested,[])
        self.tick();self.assertEqual(self.native.requested,[drive.SCREENSHOTS[0]])

    def test_hold_cannot_accept_a_stale_png_after_pose_reverts(self):
        self.begin();self.target();self.tick();self.tick();self.native.position=list(drive.ORIGIN)
        self.assertRaises(RuntimeError,self.tick);self.assertFalse(drive._run.complete)

    def test_latest_iteration_binds_both_png_events(self):
        self.begin();self.finish()
        for i,(event,row) in enumerate(self.events):
            if event in ('map_drive_screenshot_requested','map_drive_screenshot'):
                state=next(r for n,r in reversed(self.events[:i]) if n=='map_drive_state')
                self.assertEqual((row['advance'],row['observed_at']),(state['advance'],state['observed_at']))
                self.assertTrue(state['binding_ready'])

    def test_nan_argument_never_raises_in_profiler(self):
        self.arm();data=dict(position=[0,0,float('nan')],direction=[0]*3,speed=0,rspeed=0)
        self.assertFalse(drive.note_map_drive_call('call','updateOwnVehiclePosition',1445,-1,200,300,data))
        self.assertRaises(RuntimeError,self.tick)

    def test_note_copies_vectors_not_native_or_mutable_references(self):
        self.arm();data=dict(position=list(drive.ORIGIN),direction=[0]*3,speed=0,rspeed=0)
        self.assertTrue(drive.note_map_drive_call('call','updateOwnVehiclePosition',1445,-1,200,300,data))
        data['position'][0]=99
        self.assertEqual(drive._run.binding_notes[0]['data']['position'][0],drive.ORIGIN[0])

    def test_note_exact_integer_metadata(self):
        for index in (2,3,4,5):
            self.arm();args=['call','updateOwnVehiclePosition',1445,-1,200,300,
                            dict(position=[0]*3,direction=[0]*3,speed=0,rspeed=0)]
            args[index]=float(args[index])
            self.assertFalse(drive.note_map_drive_call(*args))
            self.assertRaises(RuntimeError,self.tick)
            drive._run=drive._native=None;drive._arm_attempted=False
            self.native.value=world.account()

    def test_binding_note_budget_is_hard_and_passive(self):
        self.arm()
        for cid in range(drive.MAX_BINDING_PENDING):
            self.assertTrue(drive.note_map_drive_call('call','__setOwnVehicleMatrixCallback',2951,-1,cid+1,300,{}))
        self.assertFalse(drive.note_map_drive_call('call','__setOwnVehicleMatrixCallback',2951,-1,999,300,{}))
        self.assertRaises(RuntimeError,self.tick)

    def test_return_without_call_rejected(self):
        self.arm();self.entities()
        drive.note_map_drive_call('return','__setOwnVehicleMatrixCallback',2951,151,201,300,{})
        self.assertRaises(RuntimeError,self.tick)

    def test_duplicate_call_id_rejected(self):
        self.arm();self.entities();self.bind();self.pair(cid=200)
        self.assertRaises(RuntimeError,self.tick)

    def test_wrong_original_return_offset_rejected(self):
        self.arm();self.entities();self.pair(offset=197)
        self.assertRaises(RuntimeError,self.tick)

    def test_foreign_original_callback_owner_rejected(self):
        self.arm();self.entities();self.pair(owner=999)
        self.assertRaises(RuntimeError,self.tick)

    def test_original_arguments_must_not_change_between_call_return(self):
        self.arm();self.entities()
        data=dict(position=list(drive.ORIGIN),direction=[0]*3,speed=0,rspeed=0)
        drive.note_map_drive_call('call','updateOwnVehiclePosition',1445,-1,200,300,data)
        data['speed']=1
        drive.note_map_drive_call('return','updateOwnVehiclePosition',1445,198,200,300,data)
        self.assertRaises(RuntimeError,self.tick)

    def test_deadline_and_gap_failures_cannot_complete(self):
        self.begin()
        for _ in range(7):self.assertFalse(self.tick())
        self.assertRaises(RuntimeError,self.tick)
        self.assertFalse(drive._run.complete)
        self.assertEqual(self.native.commands[-1],(0,False,300))

    def test_clock_backwards_stops(self):
        self.begin();self.at=1.0
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands[-1],(0,False,300))

    def test_missing_png_has_no_success_fallback(self):
        self.arm();self.entities();self.bind();self.native.png_missing=True
        self.tick();self.tick();self.tick()
        for _ in range(drive.MAX_PNG_ADVANCES-1):self.assertFalse(self.tick())
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.commands,[])

    def test_fini_tries_every_stage_and_reports_failure(self):
        self.arm();self.cleanup_fail.add('before')
        self.assertRaises(RuntimeError,drive.fini,self.record,self.stage('native'))
        self.assertEqual(self.cleanup,['before','native','after'])
        self.assertEqual(self.native.cleanup,['light'])

    def test_fini_after_complete_idempotent(self):
        self.begin();self.finish()
        drive.fini(self.record,self.stage('native'));drive.fini(self.record,self.stage('native'))
        self.assertEqual(self.cleanup,['before','native','after'])
        self.assertEqual(self.native.cleanup,['light'])
        self.assertFalse(drive.note_map_drive_call('call','__setOwnVehicleMatrixCallback',2951,-1,999,300,{}))

    def test_every_synthetic_event_fits_native_record_budget(self):
        self.begin();self.finish()
        for event,row in self.events:
            self.assertLessEqual(len(json.dumps(row,ensure_ascii=True,separators=(',',':')).encode('ascii')),8192)


class SourceContracts(unittest.TestCase):
    @unittest.skipIf(sys.version_info[0]<3,'host static bytecode audit is run by Python3')
    def test_original_code_arguments_offsets_and_source_pins(self):
        sys.path.insert(0,os.path.join(ROOT,'tools'))
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,text,opcode_table,disassemble
        original=config()[1]['original_client_root']
        table=opcode_table(read_limited(__import__('pathlib').Path(ROOT)/'local/vendor/cpython-2.7.3/opcode.py',32768).decode('utf8'))
        methods={}
        for relative,digest in drive.SOURCE_HASHES:
            raw=read_limited(original/relative,1048576)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            if relative.endswith('/Avatar.pyc'):
                methods=dict((q.rsplit('.',1)[-1],code) for q,code in records(parse_pyc(raw)))
        for attr,name,line,nargs,digest in drive.METHODS:
            code=methods[name]
            self.assertEqual(code['firstlineno'],line);self.assertEqual(code['argcount'],nargs)
            self.assertEqual(hashlib.sha256(code['code']).hexdigest(),digest)
            offsets=tuple(row['offset'] for row in disassemble(code,table) if row['opname']=='RETURN_VALUE')
            self.assertEqual(offsets,drive.RETURNS[name][1])
        self.assertEqual(text(methods['updateOwnVehiclePosition']['varnames'])[:5],
                         ['self','position','direction','speed','rspeed'])

    def test_frozen_movement_source_unchanged(self):
        path=os.path.join(ROOT,'client_patch','arena_movement_scenario.py')
        with open(path,'rb') as stream:raw=stream.read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         'f995f0e574c9a96dcee07beb4518beebb7c2e21bfbe2213a6e8d2d6127a182fb')

    def test_ground_query_plan_exact_and_no_expected_height_in_module(self):
        filename=os.path.join(ROOT,'local','evidence','20261005-p02-map-drive','data','native-rays-01','samples.json')
        with open(filename,'rb') as stream:raw=stream.read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),drive.RAY_PLAN_SHA256)
        plan=json.loads(raw.decode('utf8'))
        self.assertEqual(len(plan['samples']),len(drive.GROUND_RAYS))
        for row,(name,x,z) in zip(plan['samples'],drive.GROUND_RAYS):
            self.assertEqual(row['id'],name)
            self.assertEqual(row['start'],[x,200.0,z]);self.assertEqual(row['end'],[x,-50.0,z])
            self.assertEqual(row['flags'],18)


class CollisionControls(unittest.TestCase):
    def test_miss_recorded_without_fabricated_height(self):
        row=drive._ray_result(None)
        self.assertEqual(row['status'],'MISS');self.assertIsNone(row['point'])

    def test_original_six_fields_copied_with_opaque_labels(self):
        raw=([1.,2.,3.],[0.,1.,0.],4,[5.,6.,7.],-1,4294967295)
        row=drive._ray_result(raw)
        raw[0][1]=99
        self.assertEqual(row['point'],[1.,2.,3.]);self.assertEqual(row['material'],4)
        self.assertEqual(row['opaque_integers'],[-1,4294967295])

    def test_unknown_tuple_shape_rejected_not_suppressed(self):
        for value in ((),[0]*6,(0,)*5,(0,)*7):
            self.assertRaises(ValueError,drive._ray_result,value)

    def test_nonfinite_or_unbounded_collision_rejected(self):
        self.assertRaises(ValueError,drive._ray_result,([0,float('nan'),0],[0,1,0],0,[0,0,0],0,0))
        self.assertRaises(ValueError,drive._ray_result,([0,0,0],[0,1,0],0,[0,0,0],0,2**40))


if __name__=='__main__':
    unittest.main(verbosity=2)
