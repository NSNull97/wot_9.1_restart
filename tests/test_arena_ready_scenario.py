# -*- coding: utf-8 -*-
"""Synthetic negative controls for the diagnostic, not native compatibility."""
import copy
import hashlib
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import arena_ready_scenario as ready
import test_arena_vehicle_scenario as world


class NativeControl(world.NativeControl):
    def __init__(self):
        world.NativeControl.__init__(self)
        self.countdown_sources, self.cleanup, self.requested = [], [], []
        self.at, self.timer_overrides = 1.0, {}
        self.timer_present, self.png_available = True, True
        self.vehicle_value['roster']['avatar_ready'] = True

    def timer(self):
        if not self.timer_present:
            return {'present': False}
        data = dict(present=True, owner_id=500, arena_owner_id=600, period=2,
            period_end_time=130.0, period_length=30.0, period_additional_info_is_none=True,
            server_time=100.0+self.at, native_time=self.at, remaining_exact=30.0-self.at,
            remaining_seconds=max(0,int(30.0-self.at)), timer_visible=True,
            replay_playing=False, replay_recording=True, movie_present=True)
        data.update(self.timer_overrides)
        return data

    def request(self, basename):
        if self.capture_fail:
            raise ValueError('synthetic capture failure')
        self.requested.append(basename)

    def screenshot(self, basename):
        if not self.png_available:
            return None
        data = copy.deepcopy(self.png)
        data['basename'] = basename
        return data

    def light_fini(self):
        self.cleanup.append('light')


class CountdownTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict((key,getattr(ready,key)) for key in
            ('_run','_native','_arm_attempted','_closing','_finished_cleanup','_cleanup_errors','_Native'))
        ready._run = ready._native = None
        ready._arm_attempted = ready._closing = ready._finished_cleanup = False
        ready._cleanup_errors = []
        self.native, self.events, self.time, self.call = NativeControl(), [], 1.0, 100
        self.record = lambda event, **data: self.events.append((event,data))
        ready._Native = lambda record,settings: self.native
        self.cleanup, self.cleanup_fail = [], set()
        self.old_cleanup = (ready.arena_bootstrap.fini_before_entities,ready.arena_bootstrap.fini_after_entities)
        ready.arena_bootstrap.fini_before_entities = self.stage('before')
        ready.arena_bootstrap.fini_after_entities = self.stage('after')

    def tearDown(self):
        for key,value in self.saved.items(): setattr(ready,key,value)
        ready.arena_bootstrap.fini_before_entities,ready.arena_bootstrap.fini_after_entities=self.old_cleanup

    def stage(self,name):
        def run():
            self.cleanup.append(name)
            if name in self.cleanup_fail: raise ValueError(name)
        return run

    def arm(self):
        ready.arm(self.record,{})
        ready._run.clock=lambda:self.time
        self.native.value=world.avatar()

    def entities(self):
        def pair(kind,name,index,result=None):
            line,returns=ready.vehicle.CALLBACKS[kind][name]
            owner=300 if kind=='avatar' else 400
            entity=ready.vehicle.AVATAR_ID if kind=='avatar' else ready.vehicle.VEHICLE_ID
            fun=ready.note_avatar_call if kind=='avatar' else ready.note_vehicle_call
            fun('call',name,line,-1,index,owner,entity,1)
            fun('return',name,line,returns[-1] if result is None else result,index,owner,entity,1)
        pair('avatar','onEnterWorld',1)
        pair('avatar','__onInitStepCompleted',2,101)
        pair('avatar','__onInitStepCompleted',3,101)
        ready.note_geometry_mapped(1,'spaces/01_karelia')
        pair('avatar','onSpaceLoaded',4)
        pair('avatar','__onInitStepCompleted',5,101)
        pair('vehicle','__init__',6)
        pair('vehicle','prerequisites',7)
        pair('vehicle','onEnterWorld',8)
        pair('vehicle','startVisual',9)
        pair('avatar','__onInitStepCompleted',10,640)

    def note(self,method,phase,index,data,owner=500,offset=None):
        line,returns=ready.TIMER_METHODS[method]
        return ready.note_timer_call(phase,method,line,
            (-1 if phase=='call' else returns[-1]) if offset is None else offset,index,owner,data)

    def timer_tick(self,period_event=False,seconds=None):
        self.call+=10
        c=self.call
        if period_event:
            self.note('__onSetArenaTime','call',c-1,{'period_args':[2,130.0,30.0,None]})
        self.note('__setArenaTime','call',c,{})
        count=max(0,int(30-self.time)) if seconds is None else seconds
        for offset,name,args in [(1,'timerBar.setTotalTime',[count]),
                                 (3,'timerBig.setTimer',[u'До начала боя',count])]:
            parent=dict(method_name=name,args=list(args),parent_call_id=c,parent_owner_id=500)
            child=dict(method_name='battle.'+name,args=list(args),parent_call_id=c+offset,parent_owner_id=500)
            self.note('__callEx','call',c+offset,parent)
            self.note('call','call',c+offset+1,child)
            child['args']=['battle.'+name]+args
            parent['args']=['battle.'+name]+args
            self.note('call','return',c+offset+1,child)
            self.note('__callEx','return',c+offset,parent)
        self.note('__setArenaTime','return',c,dict(period=2,remaining_exact=30.0-self.time,
                                                  remaining_seconds=count))
        if period_event:
            self.note('__onSetArenaTime','return',c-1,{'period_args':[2,130.0,30.0,None]})

    def tick(self,timer=True,period_event=False):
        self.native.at=self.time
        if timer:self.timer_tick(period_event)
        value=ready.advance(self.record)
        self.time+=1.0
        return value

    def begin(self):
        self.arm();self.entities()
        self.assertFalse(self.tick(period_event=True))
        self.assertFalse(self.tick())
        self.assertFalse(self.tick())
        self.assertEqual(self.native.requested,[ready.SCREENSHOTS[0]])

    def finish(self):
        for _ in range(15):
            if self.tick():return
        self.fail('bounded synthetic countdown did not complete')

    def test_unarmed_is_passive(self):
        self.assertFalse(ready.note_timer_call(None,[],None,None,None,None,object()))
        self.assertFalse(ready.note_avatar_call(None,[],None,None,None,None,None,None))
        self.assertFalse(ready.advance(self.record));self.assertEqual(self.events,[])

    def test_foreign_or_disconnected_account_rejected_before_init(self):
        self.native.initial['native_connected']=False
        self.assertRaises(RuntimeError,self.arm)
        self.assertEqual(self.native.initialized,0)

    def test_one_arm_and_only_explicit_native_services(self):
        self.arm();self.assertEqual(self.native.initialized,1)
        self.assertEqual(self.events[-1][0],'arena_ready_armed')
        self.assertFalse(self.events[-1][1]['clock_modified'])
        self.assertFalse(self.events[-1][1]['gui_invoked'])
        self.assertRaises(RuntimeError,self.arm)

    def test_countdown_two_png_and_original_pairs_complete(self):
        self.begin();self.finish()
        self.assertEqual(self.native.requested,list(ready.SCREENSHOTS))
        self.assertEqual(self.events[-1][0],'arena_ready_complete')
        self.assertFalse(self.events[-1][1]['compatibility_acceptance'])
        self.assertEqual(self.events[-1][1]['native_pixel_acceptance'],'NOT_RUN')
        self.assertGreaterEqual(self.events[-1][1]['observed_at']-self.events[-1][1]['began_at'],6)

    def test_gui_flags_without_original_callbacks_do_not_complete(self):
        self.arm()
        for _ in range(4):self.assertFalse(self.tick(period_event=(_==0)))
        self.assertEqual(self.native.requested,[])

    def test_original_entity_abnormal_return_is_deferred_failure(self):
        self.arm();self.entities();ready._run.notes[-1]['offset']=639
        self.assertRaises(RuntimeError,self.tick)

    def test_fourth_native_init_step_required(self):
        self.arm();self.entities()
        ready._run.notes=[x for x in ready._run.notes if x.get('call_id')!=10]
        self.assertFalse(self.tick(period_event=True));self.assertEqual(self.native.requested,[])

    def test_missing_period_listener_does_not_accept_flags(self):
        self.arm();self.entities()
        for _ in range(5):self.assertFalse(self.tick())
        self.assertEqual(self.native.requested,[])

    def test_changed_period_listener_deadline_rejected(self):
        self.arm();self.entities();self.timer_tick(True)
        for n in ready._run.timer_notes:
            if n['method']=='__onSetArenaTime':n['data']['period_args'][1]=131.0
        self.assertRaises(RuntimeError,self.tick,False)

    def test_duplicate_period_event_rejected(self):
        self.begin();self.assertRaises(RuntimeError,self.tick,True,True)

    def test_exact_integer_entry_offset_required(self):
        self.arm();self.entities();self.timer_tick(True)
        ready._run.timer_notes[1]['offset']=0
        self.assertRaises(RuntimeError,self.tick,False)

    def test_bool_offset_rejected_without_raising_from_hook(self):
        self.arm()
        self.assertFalse(self.note('__setArenaTime','call',100,{},offset=True))
        self.assertRaises(RuntimeError,self.tick,False)

    def test_abnormal_timer_return_rejected(self):
        self.arm();self.entities();self.timer_tick(True)
        next(n for n in ready._run.timer_notes if n['method']=='call' and n['phase']=='return')['offset']=55
        self.assertRaises(RuntimeError,self.tick,False)

    def test_original_line_pin_rejected(self):
        self.arm();self.timer_tick()
        ready._run.timer_notes[0]['source_line']+=1
        self.assertRaises(RuntimeError,self.tick,False)

    def test_foreign_flash_owner_rejected(self):
        self.arm();self.timer_tick()
        next(n for n in ready._run.timer_notes if n['method']=='call')['owner_id']=501
        self.assertRaises(RuntimeError,self.tick,False)

    def test_orphan_flash_parent_rejected(self):
        self.arm();self.timer_tick()
        next(n for n in ready._run.timer_notes if n['method']=='call')['data']['parent_call_id']=999
        self.assertRaises(RuntimeError,self.tick,False)

    def test_return_without_entry_rejected(self):
        self.arm();self.note('__setArenaTime','return',100,dict(period=2,remaining_exact=20.0,remaining_seconds=20))
        self.assertRaises(RuntimeError,self.tick,False)

    def test_flash_args_are_copied_before_original_in_place_mutation(self):
        self.arm()
        data=dict(method_name='timerBig.setTimer',args=[u'Начало',20],parent_call_id=100,parent_owner_id=500)
        self.assertTrue(self.note('__callEx','call',101,data))
        data['args'].insert(0,'battle.timerBig.setTimer')
        self.assertEqual(ready._run.timer_notes[-1]['data']['args'],[u'Начало',20])

    def test_missing_flash_method_prefix_rejected(self):
        self.arm();self.timer_tick()
        next(n for n in ready._run.timer_notes if n['method']=='call' and n['phase']=='return')['data']['args'].pop(0)
        self.assertRaises(RuntimeError,self.tick,False)

    def test_wrong_flash_value_rejected_even_if_parent_is_consistent(self):
        self.arm();self.timer_tick()
        for n in ready._run.timer_notes:
            if n['method'] in ('__callEx','call') and 'timerBig' in n['data']['method_name']:
                n['data']['args'][-1]=25
        self.assertRaises(RuntimeError,self.tick,False)

    def test_missing_one_of_two_flash_paths_rejected(self):
        self.arm();self.timer_tick()
        ready._run.timer_notes=[n for n in ready._run.timer_notes if n['call_id'] not in (self.call+1,self.call+2)]
        self.assertRaises(RuntimeError,self.tick,False)

    def test_stale_tick_or_wrong_observed_value_rejected(self):
        self.begin();self.time+=4
        self.assertRaises(RuntimeError,self.tick,False)

    def test_native_clock_backwards_within_interval_rejected(self):
        self.begin();self.tick()
        self.native.timer_overrides['server_time']=102.5
        self.assertRaises(RuntimeError,self.tick)

    def test_changed_deadline_not_accepted_as_refresh(self):
        self.begin();self.native.timer_overrides['period_end_time']=131.0
        self.assertRaises(RuntimeError,self.tick)

    def test_native_replay_does_not_prove_live_countdown(self):
        self.begin();self.native.timer_overrides['replay_playing']=True
        self.assertRaises(RuntimeError,self.tick)

    def test_active_battle_and_zero_tail_rejected(self):
        self.begin();self.native.timer_overrides['period']=3
        self.assertRaises(RuntimeError,self.tick)

    def test_period_without_server_avatar_ready_roster_rejected(self):
        self.begin();self.native.vehicle_value['roster']['avatar_ready']=False
        self.assertRaises(RuntimeError,self.tick)

    def test_only_positive_remaining_greater_than_one_is_accepted(self):
        self.begin();self.native.timer_overrides.update(remaining_seconds=1,remaining_exact=1.0)
        self.assertRaises(RuntimeError,self.tick)

    def test_freezing_timer_does_not_complete_on_wall_time(self):
        self.begin()
        # Repeated identical calculation with advancing diagnostic clock is no proof.
        self.native.timer_overrides.update(server_time=103.0,remaining_exact=27.0,remaining_seconds=27)
        for _ in range(7):
            self.timer_tick(seconds=27)
            for n in ready._run.timer_notes:
                if n['method']=='__setArenaTime' and n['phase']=='return':n['data']['remaining_exact']=27.0
            self.assertFalse(self.tick(False))
        self.assertEqual(self.native.requested,[ready.SCREENSHOTS[0]])

    def test_original_countdown_increase_rejected(self):
        self.begin();self.tick();self.timer_tick(seconds=29)
        for n in ready._run.timer_notes:
            if n['method']=='__setArenaTime' and n['phase']=='return':n['data']['remaining_exact']=29.0
        self.assertRaises(RuntimeError,self.tick,False)

    def test_countdown_without_six_seconds_does_not_complete(self):
        self.begin()
        for _ in range(4):self.assertFalse(self.tick())
        self.assertEqual(self.native.requested,[ready.SCREENSHOTS[0]])

    def test_identity_and_world_readiness_preserved_through_png(self):
        self.begin();self.native.vehicle_value['health']=89
        self.assertRaises(RuntimeError,self.tick)

    def test_readiness_loss_rejected_after_first_png(self):
        self.begin();self.native.value['world_draw_enabled']=False
        self.assertRaises(RuntimeError,self.tick)

    def test_before_delete_is_not_countdown_completion(self):
        self.begin();self.note('beforeDelete','call',999,{})
        self.assertRaises(RuntimeError,self.tick)

    def test_png_failure_never_marks_completion(self):
        self.native.capture_fail=True
        self.arm();self.entities();self.tick(period_event=True);self.tick()
        self.assertRaises(ValueError,self.tick)
        self.assertEqual(self.events[-1][0],'arena_ready_error')

    def test_invalid_png_container_rejected(self):
        self.begin();self.native.png['png_container_valid']=False
        self.assertRaises(RuntimeError,self.tick)

    def test_timer_note_budget_fail_is_deferred(self):
        self.arm();ready._run.timer_count=ready.MAX_TIMER_NOTES
        self.assertFalse(self.note('__setArenaTime','call',100,{}))
        self.assertRaises(RuntimeError,self.tick,False)

    def test_note_accepts_no_rich_or_oversized_gui_values(self):
        self.arm()
        data=dict(method_name='timerBig.setTimer',args=['x'*257,20],parent_call_id=100,parent_owner_id=500)
        self.assertFalse(self.note('__callEx','call',101,data))
        self.assertRaises(RuntimeError,self.tick,False)

    def test_observation_exhaustion_does_not_quit_or_pass_itself(self):
        self.arm();ready._run.advances=ready.MAX_ADVANCES
        self.assertRaises(RuntimeError,self.tick,False)

    def test_fini_attempts_all_stages_before_reporting_error(self):
        self.arm();self.cleanup_fail.add('native')
        self.assertRaises(RuntimeError,ready.fini,self.record,self.stage('native'))
        self.assertEqual(self.cleanup,['before','native','after'])
        self.assertEqual(self.native.cleanup,['light'])
        self.assertEqual([r['stage']for e,r in self.events if e=='arena_ready_cleanup'],
                         ['before_entities','native_hangar_cleanup','after_entities','light_after_native'])

    def test_cleanup_idempotent_and_late_profiler_notes_passive(self):
        self.arm();ready.fini(self.record,self.stage('native'));ready.fini(self.record,self.stage('native'))
        self.assertEqual(self.cleanup,['before','native','after'])
        self.assertFalse(self.note('__setArenaTime','call',100,{}))

    def test_partial_arm_still_cleans_native_and_light(self):
        self.native.init_fail=True
        self.assertRaises(ValueError,self.arm)
        ready.fini(self.record,self.stage('native'))
        self.assertEqual(self.cleanup,['before','native','after'])
        self.assertEqual(self.native.cleanup,['light'])


class LightLifecycle(unittest.TestCase):
    def setUp(self):
        self.saved=(ready._audit_sources,ready._bindings,ready.vehicle._Native.initialize)
        self.old_module=sys.modules.get('LightFx')
        self.module=types.ModuleType('LightFx')
        self.events=[]
        self.record=lambda event,**data:self.events.append((event,data))
        class Lights:
            def __init__(self):self.enabled=False;self.calls=[]
            def start(self):self.calls.append('start')
            def isEnabled(self):return self.enabled
            def destroy(self):self.calls.append('destroy')
        manager=types.ModuleType('LightManager')
        manager.LightManager=Lights;manager.g_instance=None
        self.module.LightManager=manager
        sys.modules['LightFx']=self.module
        ready._audit_sources=lambda:[]
        ready._bindings=lambda:None
        ready.vehicle._Native.initialize=lambda owner:setattr(owner,'sources',[])
        self.native=object.__new__(ready._Native)
        self.native.record=self.record
        self.native.light=self.native.light_module=None

    def tearDown(self):
        ready._audit_sources,ready._bindings,ready.vehicle._Native.initialize=self.saved
        if self.old_module is None:sys.modules.pop('LightFx',None)
        else:sys.modules['LightFx']=self.old_module

    def test_disabled_original_device_legitimate_without_assigning_true(self):
        self.native.initialize()
        self.assertFalse(self.native.light.enabled)
        self.assertEqual(self.native.light.calls,['start'])
        self.assertIs(self.module.LightManager.g_instance,self.native.light)
        self.assertFalse(self.events[-1][1]['enabled_assigned_by_diagnostic'])

    def test_existing_singleton_not_overwritten(self):
        foreign=object();self.module.LightManager.g_instance=foreign
        self.assertRaises(RuntimeError,self.native.initialize)
        self.assertIs(self.module.LightManager.g_instance,foreign)

    def test_original_destroy_then_clear_owned_binding(self):
        self.native.initialize();light=self.native.light
        self.native.light_fini()
        self.assertEqual(light.calls,['start','destroy'])
        self.assertIsNone(self.module.LightManager.g_instance)
        self.native.light_fini();self.assertEqual(light.calls,['start','destroy'])

    def test_replaced_singleton_refused_without_destroying_foreign(self):
        self.native.initialize();light=self.native.light
        foreign=object();self.module.LightManager.g_instance=foreign
        self.assertRaises(RuntimeError,self.native.light_fini)
        self.assertEqual(light.calls,['start'])
        self.assertIs(self.module.LightManager.g_instance,foreign)


class SourceContracts(unittest.TestCase):
    @unittest.skipIf(sys.version_info[0]<3,'bounded host static decoder requires Python3; separately executed there')
    def test_exact_original_source_hashes_and_method_code(self):
        sys.path.insert(0,os.path.join(ROOT,'tools'))
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,text
        original=config()[1]['original_client_root']
        methods={}
        for relative,digest in ready.SOURCE_HASHES:
            raw=read_limited(original/relative,1048576)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            for qualified,code in records(parse_pyc(raw)):
                methods[(text(code['filename']),text(code['name']),code['firstlineno'])]=code
        for path,rows in [('scripts/client/gui/Scaleform/Battle.py',ready.GUI_METHODS),
                          ('scripts/client/LightFx/LightManager.py',ready.LIGHT_METHODS)]:
            for attr,name,line,count,digest in rows:
                code=methods[(path,name,line)]
                self.assertEqual(code['argcount'],count)
                self.assertEqual(hashlib.sha256(code['code']).hexdigest(),digest)


if __name__=='__main__':
    unittest.main(verbosity=2)
