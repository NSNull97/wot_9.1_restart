"""Pure source/phase controls. Synthetic pose inputs do not prove native collision."""
import math
import sys
import types
import unittest

import map_drive_acceptance as A
import test_map_drive_acceptance as F
import test_map_drive_phase2 as P


def fixture_function(method):
    # Test fixture reuse across unrelated unittest classes must use the actual
    # Python function under2.7, not a foreign-class unbound method descriptor.
    return getattr(method, 'im_func', method)


class Policy(unittest.TestCase):
    def make(self):
        return A._BoundaryPlan([-15.0,12.0,10.0],0.0,0.0)

    def test_first_spawn_and_first_nonzero_renewal(self):
        p=self.make();r=p.sample([-15.0,12.0,10.0],0.0,0.0,0.0)
        self.assertEqual(r['renewed_flags'],1);self.assertFalse(r['stop_candidate'])

    def test_boundary_requires_five_seconds_after_first_valid_stall(self):
        p=self.make();p.sample([-15,12,10],0,0,0)
        for now in range(1,6):
            r=p.sample([-5,11,498.48],0,0,float(now));self.assertFalse(r['stop_candidate'])
        self.assertTrue(p.sample([-5,11,498.48],0,0,6.0)['stop_candidate'])

    def test_invalid_speed_resets_instead_of_counting_violating_start(self):
        p=self.make();p.sample([-15,12,10],0,0,0)
        for now in range(1,5):p.sample([-5,11,498.48],0,0,float(now))
        self.assertIsNone(p.sample([-5,11,498.48],1.0,0,5.0)['stable_since'])
        row=p.sample([-5,11,498.48],0.0,0,6.0)
        self.assertEqual(row['stable_since'],6.0);self.assertEqual(row['stable_seconds'],0.0)

    def test_nonfinite_speed_rejected(self):
        for speed in (float('nan'),float('inf'),True):
            with self.assertRaises((ValueError,RuntimeError)):self.make().sample([-15,12,10],speed,0,0)

    def test_thirty_degree_guard_is_not_relaxed(self):
        with self.assertRaises(RuntimeError):self.make().sample([-15,12,10],0,math.pi/6+0.001,0)

    def test_wrong_spawn_and_yaw_rejected(self):
        for position,yaw in (([-5,12,498.48],0),([-15,12,10],0.2)):
            with self.assertRaises(RuntimeError):A._BoundaryPlan(position,yaw,0)

    def test_repeated_stall_far_from_wall_never_completes(self):
        p=self.make()
        for now in range(12):self.assertFalse(p.sample([-15,12,10],0,0,float(now))['stop_candidate'])

    def test_endpoint_only_large_interval_rejected(self):
        p=self.make();p.sample([-15,12,10],0,0,0)
        with self.assertRaises(RuntimeError):p.sample([-5,11,498.48],0,0,5.0)

    def test_position_drift_resets_stall(self):
        p=self.make();p.sample([-15,12,10],0,0,0)
        p.sample([-5,11,498.48],0,0,1.0)
        row=p.sample([-5.1,11,498.48],0,0,2.0)
        self.assertEqual(row['stable_since'],2.0)

    def test_forward_renewals_cannot_extend_total110seconds(self):
        p=self.make()
        for now in range(110):p.sample([-15,12,10],0,0,float(now))
        with self.assertRaises(RuntimeError):p.sample([-15,12,10],0,0,110.0)

    def test_two_exact_modes_and_rejection(self):
        for mode in A.MODES:self.assertEqual(A.checked_mode(mode),mode)
        for mode in (None,True,1,'combined','boundary',{},[]):
            with self.assertRaises(ValueError):A.checked_mode(mode)


class Boundary(unittest.TestCase):
    setUp=fixture_function(P.Phases.setUp)
    tearDown=fixture_function(P.Phases.tearDown)
    tick=fixture_function(P.Phases.tick)
    binding=fixture_function(P.Phases.binding)
    entity=fixture_function(P.Phases.entity)
    enter=fixture_function(P.Phases.enter)
    returned=fixture_function(P.Phases.returned)

    def arm(self):
        A.arm(self.record,{},'boundary_only');A._run.clock=lambda:self.at

    def begin(self,map_id=4):
        if A._run is None:self.arm()
        if A._run.phase=='between_rides':self.tick()
        self.tick();self.enter(map_id)
        for _ in range(6):self.tick()
        self.assertEqual(A._run.phase,'boundary_active' if map_id==4 else 'leg_end_png')

    def reach_stall(self):
        self.assertEqual(A._run.phase,'boundary_active')
        self.native.speed=0.0
        self.native.position=[-5.0,11.0,498.48]
        for _ in range(6):self.tick()
        self.assertEqual(A._run.phase,'boundary_hold')

    def finish(self):
        self.reach_stall()
        for _ in range(4):self.tick()
        self.assertEqual(A._run.phase,'boundary_backoff')
        self.native.position[2]-=5.1
        self.tick()
        self.assertEqual(A._run.phase,'boundary_backoff_hold')
        for _ in range(5):self.tick()
        self.assertEqual(A._run.phase,'waiting_return')
        return self.returned()

    def test_single_random_proho_scope_with_actual_original_proofs(self):
        self.begin(4);self.assertTrue(self.finish())
        final=[r for e,r in self.events if e=='map_drive_acceptance_complete'][0]
        self.assertEqual(final['diagnostic_mode'],'boundary_only')
        self.assertEqual(final['native_rides'],1)
        self.assertTrue(final['boundary_observed'])
        self.assertEqual(final['basic_drive_acceptance'],
                         'NOT_RUN_IN_BOUNDARY_MODE_REQUIRES_SEPARATE_PHASE2_DRIVE')
        self.assertNotIn('two_maps_observed',final)
        self.assertEqual(final['sampler_count'],0)
        self.assertFalse(any(e=='map_drive_acceptance_sample' for e,r in self.events))
        actions=[r for e,r in self.events if e=='map_drive_acceptance_action' and r['moment']=='begin']
        self.assertGreaterEqual(sum(r['arguments']==[1,True] for r in actions),5)
        self.assertEqual(self.native.actions[-3:],[(2,True),(0,False),'leave'])

    def test_random_other_map_return_then_fresh_proho(self):
        self.begin(1);self.tick();self.assertEqual(A._run.phase,'waiting_return')
        self.assertFalse(self.returned());seen=set(A._run.seen)
        self.assertEqual(self.native.actions,['fight','leave'])
        self.begin(4);self.assertTrue(self.finish())
        self.assertTrue(seen.issubset(A._run.seen))
        self.assertEqual([x['space_id'] for x in A._run.completed_rides],[1,2])
        self.assertEqual([x['map_id'] for x in A._run.completed_rides],[1,4])

    def test_eight_wrong_random_maps_fail_without_forced_selection(self):
        for _ in range(7):
            self.begin(1);self.tick();self.assertFalse(self.returned())
        self.begin(1);self.tick()
        with self.assertRaises(RuntimeError):self.returned()
        self.assertEqual(self.native.actions.count('fight'),8)
        self.assertTrue(all(x in ('fight','leave') for x in self.native.actions))

    def test_actual_forward_commands_renew_instead_of_only_markers(self):
        self.begin(4)
        for _ in range(6):self.tick()
        issued=[r for e,r in self.events if e=='map_drive_acceptance_action' and r['moment']=='return' and r['action'].startswith('boundary_')]
        self.assertEqual(len(issued),7)
        self.assertTrue(all(r['action'] in A._run.proofs for r in issued))

    def test_missing_native_renewal_callback_fails(self):
        self.begin(4);self.native.omit_action=True
        with self.assertRaises(RuntimeError):self.tick()
        self.assertFalse(A._run.complete)

    def test_boundary_forward_beyond30_uses_independent110_budget(self):
        self.begin(4)
        for _ in range(35):self.tick()
        self.assertEqual(A._run.phase,'boundary_active')
        self.assertFalse(A._run.complete)

    def test_readiness_gap_cannot_keep_renewal_alive(self):
        self.begin(4);self.at+=0.6
        with self.assertRaises(RuntimeError):self.tick()
        self.assertEqual(self.native.actions[-1],(0,False))

    def test_zero_world_readiness_retry_emits_no_forward(self):
        self.begin(4);before=len(self.native.actions)
        self.native.target=False;self.tick()
        self.assertEqual(A.next_observation_delay(),0.1)
        self.assertEqual(len(self.native.actions),before)

    def test_three_second_stop_starts_with_valid_not_violating_sample(self):
        self.begin(4);self.reach_stall()
        self.native.speed=1.0
        for _ in range(4):self.tick()
        self.assertEqual(A._run.phase,'boundary_hold');self.assertIsNone(A._run.stable_since)
        self.native.speed=0.0
        for _ in range(3):self.tick()
        self.assertEqual(A._run.phase,'boundary_hold')
        self.tick();self.assertEqual(A._run.phase,'boundary_backoff')

    def test_backoff_insufficient_distance_cannot_complete(self):
        self.begin(4);self.reach_stall()
        for _ in range(4):self.tick()
        self.native.position[2]-=4.9;self.tick()
        self.assertEqual(A._run.phase,'boundary_backoff')

    def test_backoff_preserves_other_action30second_limit(self):
        self.begin(4);self.reach_stall()
        for _ in range(4):self.tick()
        for _ in range(29):self.tick()
        with self.assertRaises(RuntimeError):self.tick()

    def test_hold_requires_three_valid_seconds_for_both_stops(self):
        self.begin(4);self.assertTrue(self.finish())
        holds=[r for e,r in self.events if e=='map_drive_acceptance_hold']
        self.assertEqual([r['kind'] for r in holds],['boundary_stop','boundary_backoff_stop'])
        self.assertGreaterEqual(holds[0]['observed_at']-holds[0]['began_at'],3.0)
        self.assertGreaterEqual(holds[1]['observed_at']-holds[1]['began_at'],3.0)
        self.assertTrue(all(r['interval_start']=='FIRST_VALID_LOW_SPEED_SAMPLE' for r in holds))

    def test_physics_airborne_and_wall_causality_not_faked(self):
        self.begin(4);self.assertTrue(self.finish())
        final=[r for e,r in self.events if e=='map_drive_acceptance_complete'][0]
        self.assertIn('INDEPENDENT_SERVER_BOUNDARY_AND_ALL_WORKER_CONTACTS',final['collision_acceptance'])

    def test_no_global_frozen_scenario_mutation_or_sampler(self):
        self.begin(4);self.assertTrue(self.finish())
        self.assertEqual(self.native.scheduled,{})
        self.assertEqual(self.frozen,(A.binding._run,A.movement._run,A.vehicle._run))


class CorrectedBasicHold(unittest.TestCase):
    def test_first_valid_observation_starts_basic_hold(self):
        native=P.Native();run=A._Scenario(lambda *a,**k:None,{},native=native,clock=lambda:0)
        run.phase='hold_reverse';native.speed=1.0
        self.assertFalse(run._hold(native.motion(),1.0));self.assertIsNone(run.stable_since)
        native.speed=0.0
        self.assertFalse(run._hold(native.motion(),2.0))
        self.assertFalse(run._hold(native.motion(),3.99))
        self.assertFalse(run._hold(native.motion(),4.0))
        self.assertFalse(run._hold(native.motion(),4.99))
        self.assertTrue(run._hold(native.motion(),5.0))

    def test_violating_speed_resets_entire_basic_hold(self):
        native=P.Native();run=A._Scenario(lambda *a,**k:None,{},native=native,clock=lambda:0)
        run.phase='hold_turn'
        self.assertFalse(run._hold(native.motion(),1.0))
        native.speed=0.2;self.assertFalse(run._hold(native.motion(),3.0))
        native.speed=0;self.assertFalse(run._hold(native.motion(),4.0))
        self.assertFalse(run._hold(native.motion(),5.0));self.assertFalse(run._hold(native.motion(),6.0))
        self.assertTrue(run._hold(native.motion(),7.0))

    def test_default_mode_preserves_full_phase2_requirements(self):
        saved=A._run,A._attempted,A._Native
        try:
            A._run,A._attempted=None,False
            A._Native=lambda settings:P.Native()
            A.arm(lambda *a,**k:None,{})
            self.assertIs(type(A._run),A._Scenario)
            self.assertEqual(A._run.diagnostic_mode,'phase2_drive')
            self.assertFalse(A._run.complete)
        finally:A._run,A._attempted,A._Native=saved

    def test_invalid_mode_has_no_native_initialize_side_effect(self):
        saved=A._run,A._attempted,A._Native
        called=[]
        try:
            A._run,A._attempted=None,False
            A._Native=lambda settings:called.append(settings)
            with self.assertRaises(ValueError):A.arm(lambda *a,**k:None,{},'combined')
            self.assertEqual(called,[]);self.assertIsNone(A._run)
        finally:A._run,A._attempted,A._Native=saved


class NativePixelNames(unittest.TestCase):
    def setUp(self):
        self.previous=sys.modules.get('BigWorld')
        self.calls=[]
        module=types.ModuleType('BigWorld')
        module.screenShot=lambda kind,name:self.calls.append((kind,name))
        sys.modules['BigWorld']=module

        class Pixels(A._Pixels):
            def __init__(self):
                self.requested=set()
                self.entries=[]

            def _entries(self):
                return list(self.entries)

        self.pixels=Pixels()

    def tearDown(self):
        if self.previous is None:sys.modules.pop('BigWorld',None)
        else:sys.modules['BigWorld']=self.previous

    def test_actual_request_accepts_both_production_name_sets(self):
        expected=tuple('map_drive_r%02d_%s'%(ride,moment) for ride in range(1,9)
                       for moment in ('entry','driven','return'))
        expected+=tuple('map_boundary_r%02d_%s'%(ride,moment) for ride in range(1,9)
                        for moment in ('entry','end','return'))
        self.assertEqual(A.SCREENSHOTS+A.BOUNDARY_SCREENSHOTS,expected)
        for name in expected:self.pixels.request(name)
        self.assertEqual(self.calls,[('png',name) for name in expected])

    def test_actual_request_rejects_unknown_names_before_writer(self):
        for name in ('map_boundary_r00_entry','map_boundary_r09_entry',
                     'map_boundary_r01_driven','map_drive_r01_end','../foreign',None):
            with self.assertRaises(ValueError):self.pixels.request(name)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.pixels.requested,set())

    def test_actual_request_rejects_repeated_boundary_basename(self):
        self.pixels.request('map_boundary_r01_entry')
        with self.assertRaises(ValueError):self.pixels.request('map_boundary_r01_entry')
        self.assertEqual(self.calls,[('png','map_boundary_r01_entry')])

    def test_actual_request_keeps_unowned_directory_guard(self):
        self.pixels.entries=['foreign.png']
        with self.assertRaises(ValueError):self.pixels.request('map_boundary_r01_entry')
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
