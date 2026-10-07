# -*- coding: utf-8 -*-
"""Bounded diagnostic controls only; synthetic values are not native acceptance."""
import copy
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import arena_vehicle_scenario as scenario


def account():
    return dict(player_is_original_account=True, player_is_original_avatar=False,
        player_present=True, player_owner_id=200, entity_id=0x09100001,
        name=u'Тестовый_танкист', native_connected=True, repository_present=True,
        repository_owner_id=100, observation_index=1)


def avatar():
    value = account()
    value.update(player_is_original_account=False, player_is_original_avatar=True,
        player_owner_id=300, entity_id=scenario.AVATAR_ID, space_id=1,
        player_vehicle_id=scenario.VEHICLE_ID, arena_present=True, arena_type_id=1,
        arena_unique_id=1, geometry_path='spaces/01_karelia', arena_vehicle_count=1,
        space_load_progress=1.0, in_world=True, steps_till_init=0,
        user_sees_world=True, world_draw_enabled=True, vehicle_present=True)
    return value


def vehicle():
    return dict(vehicle_present=True, owner_id=400, entity_id=scenario.VEHICLE_ID,
        in_world=True, is_player=True, is_started=True, health=90, crew_active=True,
        position=[1.0, 30.0, 2.0], descriptor_sha256='a'*64,
        public_descriptor_sha256='a'*64, avatar_descriptor_same=True,
        type_compact_descr=3329, type_name='ussr:MS-1', public_name=account()['name'], team=1,
        appearance_original=True, model_count=4,
        models=[dict(part=p, present=True, visible=True) for p in scenario.PARTS],
        entity_model_is_chassis=True, roster=dict(vehicle_id=scenario.VEHICLE_ID,
            database_id=1, name=account()['name'], team=1, alive=True,
            avatar_ready=False, descriptor_sha256='a'*64),
        battle_present=True, battle_original=True, battle_component_present=True,
        battle_component_visible=True, battle_movie_present=True, turret_sound_initialized=True)


class NativeControl(object):
    def __init__(self):
        self.initial, self.value, self.vehicle_value = account(), account(), vehicle()
        self.identity = dict(database_id=1, entity_id=self.initial['entity_id'], name=self.initial['name'])
        self.expected = dict(inventory_id=1, type_compact_descr=3329, compact_descr_sha256='a'*64,
                             type_name='ussr:MS-1', health=90)
        self.sources = []
        self.initialized = self.reads = self.requests = self.polls = 0
        self.init_fail = self.capture_fail = False
        self.png = dict(basename=scenario.BASENAME, png_container_valid=True,
                        path='synthetic-only.png', sha256='b'*64, bytes=100,
                        dimensions=[800,600], native_pixels_review='NOT_RUN')

    def account(self):
        return copy.deepcopy(self.initial), dict(self.identity)

    def expected_vehicle(self):
        return dict(self.expected)

    def initialize(self):
        self.initialized += 1
        if self.init_fail:
            raise ValueError('synthetic original initialization error')

    def observe(self):
        self.reads += 1
        value = copy.deepcopy(self.value)
        value['observation_index'] = self.reads + 1
        return value

    def vehicle(self):
        return copy.deepcopy(self.vehicle_value)

    def request(self):
        self.requests += 1
        if self.capture_fail:
            raise ValueError('synthetic native screenshot error')

    def screenshot(self):
        self.polls += 1
        return copy.deepcopy(self.png)


class VehicleScenarioTests(unittest.TestCase):
    def setUp(self):
        self.saved = dict((key,getattr(scenario,key)) for key in
            ('_run','_arm_attempted','_closing','_finished_cleanup','_cleanup_errors','_Native'))
        scenario._run = None
        scenario._arm_attempted = scenario._closing = scenario._finished_cleanup = False
        scenario._cleanup_errors = []
        self.native, self.events, self.time = NativeControl(), [], 1.0
        self.record = lambda event, **row: self.events.append((event,row))
        scenario._Native = lambda record, settings: self.native
        self.cleanup = []
        self.cleanup_fail = set()
        self.old_cleanup = (scenario.arena_bootstrap.fini_before_entities, scenario.arena_bootstrap.fini_after_entities)

        def stage(name):
            def run():
                self.cleanup.append(name)
                if name in self.cleanup_fail:
                    raise ValueError(name)
            return run
        scenario.arena_bootstrap.fini_before_entities = stage('before')
        scenario.arena_bootstrap.fini_after_entities = stage('after')
        self.native_cleanup = stage('native')

    def tearDown(self):
        for key,value in self.saved.items():
            setattr(scenario,key,value)
        scenario.arena_bootstrap.fini_before_entities, scenario.arena_bootstrap.fini_after_entities = self.old_cleanup

    def arm(self):
        scenario.arm(self.record,{})
        scenario._run.clock = lambda: self.time
        self.native.value = avatar()

    def pair(self, kind, name, identity, owner=None, result=None, entry_space=1, return_space=1):
        source_line, returns = scenario.CALLBACKS[kind][name]
        owner = owner if owner is not None else (300 if kind == 'avatar' else 400)
        entity = scenario.AVATAR_ID if kind == 'avatar' else scenario.VEHICLE_ID
        function = scenario.note_avatar_call if kind == 'avatar' else scenario.note_vehicle_call
        function('call', name, source_line, -1, identity, owner, entity, entry_space)
        function('return', name, source_line, returns[-1] if result is None else result,
                 identity, owner, entity, return_space)

    def all_notes(self):
        self.pair('avatar','onEnterWorld',1)
        self.pair('avatar','__onInitStepCompleted',2,result=101)
        self.pair('avatar','__onInitStepCompleted',3,result=101)
        scenario.note_geometry_mapped(1,'spaces/01_karelia')
        self.pair('avatar','onSpaceLoaded',4)
        self.pair('avatar','__onInitStepCompleted',5,result=101)
        self.pair('vehicle','__init__',6)
        self.pair('vehicle','prerequisites',7)
        self.pair('vehicle','onEnterWorld',8)
        self.pair('vehicle','startVisual',9)
        self.pair('avatar','__onInitStepCompleted',10,result=640)

    def tick(self, step=1):
        result = scenario.advance(self.record)
        self.time += step
        return result

    def ready_until_requested(self):
        self.arm(); self.all_notes()
        self.assertFalse(self.tick()); self.assertFalse(self.tick()); self.assertFalse(self.tick())
        self.assertEqual(self.native.requests,1)

    def test_normal_unarmed_calls_are_passive(self):
        self.assertFalse(scenario.note_avatar_call(None,[],None,None,None,None,None,None))
        self.assertFalse(scenario.note_vehicle_call(None,[],None,None,None,None,None,None))
        self.assertFalse(scenario.note_geometry_mapped(None,object()))
        self.assertFalse(scenario.advance(self.record))
        self.assertEqual(self.events,[])
        self.assertEqual(self.native.initialized,0)

    def test_arm_requires_actual_primary_account_and_connected_repository(self):
        for key,wrong in [('native_connected',False),('player_is_original_account',False),
                          ('repository_present',False),('repository_owner_id',None),('name','foreign')]:
            native=NativeControl(); native.initial[key]=wrong
            self.assertRaises(RuntimeError,scenario._Scenario,self.record,native)
            self.assertEqual(native.initialized,0)
        native=NativeControl();native.identity['database_id']=2
        self.assertRaises(RuntimeError,scenario._Scenario,self.record,native)

    def test_one_arm_and_publication_only_after_real_initialization(self):
        self.arm()
        self.assertEqual(self.native.initialized,1)
        self.assertEqual([e for e,_ in self.events],['arena_vehicle_armed'])
        self.assertFalse(self.events[0][1]['native_entity_created_by_scenario'])
        self.assertRaises(RuntimeError,scenario.arm,self.record,{})

    def test_partial_initialization_error_still_attempts_three_cleanup_stages(self):
        self.native.init_fail=True
        self.assertRaises(ValueError,scenario.arm,self.record,{})
        self.assertEqual(self.events,[])
        scenario.fini(self.record,self.native_cleanup)
        self.assertEqual(self.cleanup,['before','native','after'])

    def test_exact_callbacks_plus_real_state_hold_and_png_container_complete(self):
        self.ready_until_requested()
        self.assertTrue(self.tick())
        proof=self.events[-1][1]
        self.assertEqual(self.events[-1][0],'arena_vehicle_complete')
        self.assertTrue(proof['world_loaded_observed'])
        self.assertFalse(proof['compatibility_acceptance'])
        self.assertEqual(proof['native_pixel_acceptance'],'NOT_RUN')
        self.assertEqual(proof['gameplay_acceptance'],'NOT_RUN')
        self.assertEqual(proof['clean_teardown_acceptance'],'NOT_RUN')
        count=len(self.events)
        self.assertTrue(self.tick())
        self.assertEqual(len(self.events),count)

    def test_fullflags_without_any_original_callbacks_never_complete(self):
        self.arm()
        for _ in range(5): self.assertFalse(self.tick())
        self.assertEqual(self.native.requests,0)

    def test_fourth_original_init_step_is_required(self):
        self.arm(); self.all_notes()
        scenario._run.notes=[x for x in scenario._run.notes if x.get('call_id')!=10]
        self.assertFalse(self.tick());self.assertEqual(self.native.requests,0)

    def test_abnormal_original_return_deferred_outside_profiler(self):
        self.arm();self.pair('vehicle','startVisual',1,result=406)
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.events[-1][0],'arena_vehicle_error')

    def test_exact_entry_offset_is_required(self):
        self.arm();self.all_notes();scenario._run.notes[0]['offset']=0
        self.assertRaises(RuntimeError,self.tick)

    def test_wrong_original_source_line_rejected(self):
        self.arm();self.all_notes();scenario._run.notes[0]['source_line']+=1
        self.assertRaises(RuntimeError,self.tick)

    def test_foreign_entity_and_owner_are_rejected(self):
        self.arm();self.all_notes();scenario._run.notes[0]['entity_id']+=1
        self.assertRaises(RuntimeError,self.tick)

    def test_return_without_same_entry_is_rejected(self):
        self.arm();self.pair('vehicle','prerequisites',1,return_space=2)
        self.assertRaises(RuntimeError,self.tick)

    def test_same_named_foreign_owner_does_not_satisfy_callback(self):
        self.arm();self.all_notes()
        for row in scenario._run.notes:
            if row.get('kind')=='vehicle':row['owner_id']=401
        self.assertRaises(RuntimeError,self.tick)

    def test_duplicate_call_identity_is_rejected(self):
        self.arm();self.pair('vehicle','__init__',1);self.pair('vehicle','__init__',1)
        self.assertRaises(RuntimeError,self.tick)

    def test_duplicate_distinct_creation_is_rejected(self):
        self.arm();self.all_notes();self.pair('vehicle','__init__',11)
        self.assertRaises(RuntimeError,self.tick)

    def test_prerequisites_cached_shortcut_is_not_first_entity_proof(self):
        self.arm();self.all_notes()
        for row in scenario._run.notes:
            if row.get('method')=='prerequisites' and row.get('phase')=='return':row['offset']=18
        self.assertRaises(RuntimeError,self.tick)

    def test_load_before_geometry_does_not_prove_mapping(self):
        self.arm();self.all_notes()
        for row in scenario._run.notes:
            if row['kind']=='geometry':row['sequence']=200
        self.assertFalse(self.tick())

    def test_original_world_leave_before_completion_is_failure(self):
        self.arm();self.pair('avatar','onLeaveWorld',1)
        self.assertRaises(RuntimeError,self.tick)

    def test_note_bound_and_malformed_input_never_raise_in_callback(self):
        self.arm()
        self.assertFalse(scenario.note_vehicle_call('call','startVisual',True,-1,1,400,scenario.VEHICLE_ID,1))
        self.assertRaises(RuntimeError,self.tick)

    def test_note_queue_is_bounded(self):
        self.arm()
        for i in range(scenario.MAX_PENDING_NOTES):
            self.assertTrue(scenario.note_geometry_mapped(1,'spaces/01_karelia'))
        self.assertFalse(scenario.note_geometry_mapped(1,'spaces/01_karelia'))
        self.assertRaises(RuntimeError,self.tick)

    def test_avatar_identity_cannot_change(self):
        self.arm();self.native.value['name']='foreign'
        self.assertRaises(RuntimeError,self.tick)

    def test_repository_cannot_change(self):
        self.arm();self.native.value['repository_owner_id']=101
        self.assertRaises(RuntimeError,self.tick)

    def test_roster_uses_account_identity_and_compact_bytes(self):
        self.arm();self.all_notes();self.native.vehicle_value['roster']['descriptor_sha256']='f'*64
        self.assertRaises(RuntimeError,self.tick)

    def test_public_vehicle_descriptor_must_match_inventory(self):
        self.arm();self.native.vehicle_value['public_descriptor_sha256']='f'*64
        self.assertRaises(RuntimeError,self.tick)

    def test_native_hp_or_team_are_not_client_defaults(self):
        self.arm();self.native.vehicle_value['health']=0
        self.assertRaises(RuntimeError,self.tick)

    def test_model_creation_alone_does_not_prove_visible_world(self):
        self.arm();self.all_notes();self.native.vehicle_value['models'][3]['visible']=False
        for _ in range(4):self.assertFalse(self.tick())
        self.assertEqual(self.native.requests,0)

    def test_hud_or_sound_not_ready_cannot_complete(self):
        self.arm();self.all_notes();self.native.vehicle_value['battle_component_visible']=False
        self.assertFalse(self.tick())
        self.native.vehicle_value['battle_component_visible']=True
        self.native.vehicle_value['turret_sound_initialized']=False
        self.assertFalse(self.tick());self.assertEqual(self.native.requests,0)

    def test_actual_readiness_loss_resets_hold_before_capture(self):
        self.arm();self.all_notes();self.assertFalse(self.tick())
        self.native.value['world_draw_enabled']=False
        self.assertFalse(self.tick());self.assertIsNone(scenario._run.ready_since)
        self.native.value['world_draw_enabled']=True
        self.assertFalse(self.tick());self.assertEqual(self.native.requests,0)

    def test_readiness_loss_after_capture_is_explicit_failure(self):
        self.ready_until_requested();self.native.value['world_draw_enabled']=False
        self.assertRaises(RuntimeError,self.tick)

    def test_gap_and_backwards_clock_cannot_count_ready(self):
        self.arm();self.all_notes();self.assertFalse(self.tick())
        self.time+=4
        self.assertRaises(RuntimeError,self.tick)

    def test_missing_png_remains_pending_then_fails_without_external_quit(self):
        self.ready_until_requested();self.native.png=None
        for _ in range(scenario.MAX_PNG_ADVANCES-1):self.assertFalse(self.tick())
        self.assertRaises(RuntimeError,self.tick)
        self.assertFalse(any(e=='arena_vehicle_complete' for e,_ in self.events))

    def test_invalid_png_proof_is_not_completion(self):
        self.ready_until_requested();self.native.png['png_container_valid']=False
        self.assertRaises(ValueError,self.tick)

    def test_native_screenshot_exception_is_not_suppressed(self):
        self.arm();self.all_notes();self.native.capture_fail=True
        self.assertFalse(self.tick());self.assertFalse(self.tick())
        self.assertRaises(ValueError,self.tick)

    def test_observation_exhaustion_is_failure_not_fake_complete(self):
        self.arm();scenario._run.advances=scenario.MAX_ADVANCES
        self.assertRaises(RuntimeError,self.tick)
        self.assertEqual(self.native.reads,0)

    def test_cleanup_attempts_every_stage_and_preserves_failure(self):
        self.arm();self.cleanup_fail.update(['before','native'])
        self.assertRaises(RuntimeError,scenario.fini,self.record,self.native_cleanup)
        self.assertEqual(self.cleanup,['before','native','after'])
        self.assertRaises(RuntimeError,scenario.fini,self.record,self.native_cleanup)
        self.assertEqual(len(self.cleanup),3)
        self.assertFalse(scenario.note_geometry_mapped(1,'spaces/01_karelia'))

    def test_successful_cleanup_is_idempotent(self):
        self.arm();scenario.fini(self.record,self.native_cleanup);scenario.fini(self.record,self.native_cleanup)
        self.assertEqual(self.cleanup,['before','native','after'])
        self.assertEqual([d['outcome'] for e,d in self.events if e=='arena_vehicle_cleanup'],['PASS']*3)

    def test_compact_bytes_do_not_allow_unicode_or_unbounded_data(self):
        self.assertRaises(ValueError,scenario._bytes_sha,u'not-bytes')
        self.assertRaises(ValueError,scenario._bytes_sha,b'x'*513)
        self.assertEqual(scenario._bytes_sha(b'x'),'2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881')

    def test_original_class_checks_reject_same_name_subclass_and_spoof(self):
        class Original:
            pass
        first = Original
        class Original:
            pass
        class Derived(first):
            pass
        class Spoof(object):
            @property
            def __class__(self):
                return first
        check = scenario.arena_bootstrap._exact_instance
        self.assertTrue(check(first(), first))
        self.assertFalse(check(Original(), first))
        self.assertFalse(check(Derived(), first))
        self.assertFalse(check(Spoof(), first))

    def test_bool_alias_preserves_actual_integer_and_boolean_types(self):
        for value in (0, 1, False, True):
            result = scenario._native_flag(value)
            self.assertIs(type(result), type(value))
            self.assertEqual(result, value)
        for value in (1.0, '1', [], object(), -1, 2, None):
            self.assertRaises(ValueError, scenario._native_flag, value)

    def test_exact_uint8_crew_flag_completes_without_forced_boolean(self):
        self.arm(); self.all_notes(); self.native.vehicle_value['crew_active'] = 1
        self.assertFalse(self.tick()); self.assertFalse(self.tick()); self.assertFalse(self.tick())
        self.assertTrue(self.tick())
        rows = [row for event,row in self.events if event == 'arena_vehicle_state']
        self.assertIs(type(rows[-1]['vehicle']['crew_active']), int)

    def test_zero_or_invalid_native_crew_flag_does_not_close_acceptance(self):
        self.arm(); self.native.vehicle_value['crew_active'] = 0
        self.assertRaises(RuntimeError, self.tick)


if __name__ == '__main__':
    unittest.main()
