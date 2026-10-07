# -*- coding: utf-8 -*-
"""Pure negative/sequencing tests; fake boundaries never prove native acceptance."""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import long_hangar_scenario as L


def expected():
    return {'database_id': 1, 'name': u'Unit_Ёж',
        'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
        'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0},
        'account_dossier_sha256': 'a'*64,
        'vehicles': [{'inventory_id': 1, 'type_compact_descr': 3329,
            'compact_descr_sha256': 'b'*64, 'health': 90, 'crew_ids': [1, 2]}],
        'tankmen': [{'inventory_id': i+1, 'compact_descr_sha256': ('c', 'd')[i]*64,
            'vehicle_inventory_id': 1, 'vehicle_slot_index': i} for i in range(2)]}


class FakeNative(object):
    def __init__(self):
        self.account = expected()
        self.owner, self.selected, self.view, self.crew = 100, 1, 200, 201
        self.requests, self.actions, self.releases = [], [], 0
        self.png_ready, self.png_valid = True, True

    def account_owner(self):
        return self.owner

    def state(self):
        return {'account': copy.deepcopy(self.account), 'selected_inventory_id': self.selected,
                'hangar_owner': self.view, 'crew_owner': self.crew}

    def select_ms1(self):
        self.actions.append('original_select_ms1')
        self.selected = 1

    def request(self, basename):
        if basename in self.requests:
            raise ValueError('unit repeated request')
        self.requests.append(basename)

    def screenshot(self, basename):
        if not self.png_ready:
            return None
        return {'basename': basename, 'png_container_valid': self.png_valid,
                'native_pixels_review': 'NOT_RUN', 'unit_only': True}

    def release_context(self):
        self.releases += 1


class LongHangarTests(unittest.TestCase):
    def setUp(self):
        L._armed, L._expected, L._scenario = False, None, None
        L._closed, L._notes, L._note_error = False, [], None
        self.native, self.events, self.now, self.next_call = FakeNative(), [], 0.0, 1
        L.arm(expected())
        self.scenario = L._Scenario({}, self.record, self.native, lambda: self.now)
        L._scenario = self.scenario

    def tearDown(self):
        L._armed, L._expected, L._scenario = False, None, None
        L._closed, L._notes, L._note_error = False, [], None

    def record(self, event, **fields):
        self.events.append((event, fields))

    def observed(self):
        result = dict((key, True) for key in ('native_connected', 'items_cache_synced',
            'vehicle_model_loaded', 'app_initialized', 'gui_initialized', 'hangar_space_inited',
            'hangar_space_loaded', 'interactive_movie_started'))
        result.update(selected_inventory_id=self.native.selected, vehicle={'type_compact_descr': 3329},
            waiting_visible=False, hangar_space_loading=False, vehicle_model_count=4,
            vehicle_models_visible=[True]*4, resources=copy.deepcopy(self.native.account['resources']),
            statistics=copy.deepcopy(self.native.account['statistics']))
        return result

    def tick(self, ready=True, at=None, observed=None):
        self.now = self.now+1 if at is None else at
        return L.advance(self.record, {}, self.observed() if observed is None else observed, ready)

    def stats(self, at=None, owner=None, call_id=None, offset=16):
        at = self.now if at is None else at
        call_id = self.next_call if call_id is None else call_id
        self.next_call += 1
        return L.note_stats_return(self.native.owner if owner is None else owner,
                                   call_id, 679, offset, at)

    def run_until(self, end, cadence=5):
        while self.now < end:
            now = self.now+1
            if int(now) % cadence == 0:
                self.assertTrue(self.stats(at=now))
            done = self.tick(at=now)
            if done:
                return True
        return False

    def test_complete_requires181_original_notes_900span_three_snapshots_two_png(self):
        self.assertFalse(self.run_until(904))
        self.assertEqual(self.scenario.stats_count, 180)
        self.assertFalse(self.run_until(905))  # end PNG requested, not yet read
        self.assertTrue(self.tick())
        self.assertEqual(self.native.requests, list(L.SCREENSHOTS))
        self.assertEqual(self.native.actions, [])
        snapshots = [r for e, r in self.events if e == 'long_hangar_snapshot']
        self.assertEqual([r['moment'] for r in snapshots], ['start', 'middle', 'end'])
        self.assertTrue(all(r['snapshot'] == expected() for r in snapshots))
        self.assertEqual(len(set(r['fingerprint'] for r in snapshots)), 1)
        self.assertEqual(snapshots[1]['observed_at'], 451)
        complete = [r for e, r in self.events if e == 'long_hangar_complete']
        self.assertEqual(len(complete), 1)
        self.assertEqual(complete[0]['stats_returns'], 181)
        self.assertEqual(complete[0]['stats_span'], 900)
        self.assertFalse(complete[0]['timed_exit'])
        self.assertEqual(complete[0]['native_pixels_review'], 'NOT_RUN')
        self.assertTrue(self.tick())
        self.assertEqual(len([1 for e, r in self.events if e == 'long_hangar_complete']), 1)
        self.assertFalse(self.stats())

    def test_more_than181_fast_answers_do_not_replace900_seconds(self):
        self.assertFalse(self.run_until(500, cadence=2))
        self.assertGreater(self.scenario.stats_count, 181)
        self.assertLess(self.scenario.stats_span(), 900)
        self.assertEqual(len(self.scenario.snapshots), 2)
        self.assertFalse(self.scenario.completed)

    def test_nothing_ready_is_bounded_without_external_timer(self):
        for _ in range(L.MAX_STARTUP_ADVANCES):
            self.assertFalse(self.tick(ready=False))
        with self.assertRaises(RuntimeError):
            self.tick(ready=False)
        self.assertEqual(self.scenario.phase, 'error')

    def test_startup_returns_are_observed_but_excluded(self):
        self.assertTrue(self.stats(at=.5))
        self.tick(at=1)
        event = [r for e, r in self.events if e == 'long_hangar_stats_return'][0]
        self.assertFalse(event['eligible'])
        self.assertEqual(event['observed_at'], .5)
        self.assertEqual(self.scenario.stats_count, 0)
        self.assertTrue(self.stats(at=5))
        with self.assertRaises(RuntimeError):
            self.tick(at=3)  # future notes cannot inflate the interval

    def test_native_callback_time_is_not_later_observer_time(self):
        self.tick(at=1)
        self.assertTrue(self.stats(at=2.5))
        self.tick(at=3)
        event = [r for e, r in self.events if e == 'long_hangar_stats_return'][0]
        self.assertEqual(event['observed_at'], 2.5)
        self.assertEqual(event['native_call_id'], 1)
        self.assertEqual(self.scenario.first_stats, 2.5)

    def test_abnormal_return_is_passive_then_error_outside_callback(self):
        self.tick()
        count = len(self.events)
        self.assertFalse(self.stats(offset=15))
        self.assertEqual(len(self.events), count)
        with self.assertRaises(RuntimeError):
            self.tick()
        self.assertTrue(L._closed)
        self.assertEqual(L._notes, [])
        self.assertFalse(self.stats())

    def test_bad_primitive_note_never_raises_in_profiler(self):
        for value in (None, [], {}, True, float('inf'), float('nan'), 10**500):
            L._note_error = None
            self.assertFalse(L.note_stats_return(100, 1, 679, 16, value))
        self.assertEqual(L._notes, [])

    def test_duplicate_and_backward_call_ids_are_failures(self):
        self.tick()
        self.stats(at=2, call_id=10)
        self.tick(at=2)
        self.stats(at=3, call_id=10)
        with self.assertRaises(RuntimeError):
            self.tick(at=3)

    def test_foreign_original_stats_owner_fails(self):
        self.tick()
        self.stats(at=2, owner=101)
        with self.assertRaises(RuntimeError):
            self.tick(at=2)

    def test_missing_first_or_later_statistics_progress_fails(self):
        for _ in range(16):
            self.tick()
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_later_stats_gap_fails_without_resetting_ready_interval(self):
        self.run_until(15)
        for _ in range(15):
            self.tick()
        with self.assertRaises(RuntimeError):
            self.tick()
        self.assertEqual(self.scenario.ready_since, 1)

    def test_pending_note_budget_fails_explicitly_not_callback(self):
        for n in range(L.MAX_PENDING_NOTES):
            self.assertTrue(self.stats(at=n+1))
        self.assertFalse(self.stats(at=9))
        self.assertEqual(len(L._notes), L.MAX_PENDING_NOTES)
        with self.assertRaises(RuntimeError):
            self.tick(at=10)

    def test_lost_ready_does_not_restart_successful_interval(self):
        self.run_until(10)
        with self.assertRaises(RuntimeError):
            self.tick(ready=False)
        self.assertEqual(self.scenario.phase, 'error')
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_sample_gap_exact3_allowed_over3_rejected(self):
        self.tick(at=1)
        self.tick(at=4)
        self.assertEqual(self.scenario.max_gap, 3)
        with self.assertRaises(RuntimeError):
            self.tick(at=7.001)

    def test_changed_account_pointer_is_not_same_native_session(self):
        self.tick()
        self.native.owner += 1
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_changed_full_dossier_fails(self):
        self.tick()
        self.native.account['account_dossier_sha256'] = 'e'*64
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_changed_resources_fails(self):
        self.tick()
        self.native.account['resources']['credits'] -= 1
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_changed_crew_compact_fails(self):
        self.tick()
        self.native.account['tankmen'][0]['compact_descr_sha256'] = 'e'*64
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_changed_original_view_owner_fails(self):
        self.tick()
        self.native.view += 1
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_ready_flag_loss_fails_even_if_caller_boolean_true(self):
        self.tick()
        observed = self.observed()
        observed['native_connected'] = False
        with self.assertRaises(RuntimeError):
            self.tick(observed=observed)

    def test_expected_snapshot_is_detached_from_callers_mutable_object(self):
        value = expected()
        result = L.checked_expected_primary(value)
        value['resources']['credits'] = 0
        self.assertEqual(result['resources']['credits'], 100000)
        self.assertEqual(result['name'], u'Unit_Ёж')

    def test_unknown_expected_field_cannot_carry_credentials(self):
        value = expected()
        value['password'] = 'UNIT_NOT_A_REAL_SECRET'
        with self.assertRaises(ValueError):
            L.checked_expected_primary(value)

    def test_missing_or_invalid_screenshot_never_passes(self):
        self.native.png_valid = False
        with self.assertRaises(ValueError):
            self.tick()

    def test_missing_png_exhaustion_is_observed_failure(self):
        self.native.png_ready = False
        with self.assertRaises(RuntimeError):
            self.run_until(20)
        self.assertEqual(self.scenario.phase, 'error')

    def test_counter_bound_stops_infinite_diagnostic(self):
        self.scenario.advances = L.MAX_ADVANCES
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_stats_count_bound_is_not_an_unbounded_history(self):
        with self.assertRaises(RuntimeError):
            self.run_until(650, cadence=2)
        self.assertEqual(self.scenario.note_count, L.MAX_STATS_RETURNS)
        self.assertEqual(self.scenario.phase, 'error')

    def test_measured_original_selection_is_used_once_for_owned_other_vehicle(self):
        second = {'inventory_id': 2, 'type_compact_descr': 7169,
                  'compact_descr_sha256': 'e'*64, 'health': 2150, 'crew_ids': [None]*5}
        self.native.account['vehicles'].append(second)
        self.scenario.expected = copy.deepcopy(self.native.account)
        self.native.selected = 2
        self.assertFalse(self.tick())
        self.assertEqual(self.native.actions, ['original_select_ms1'])
        self.assertFalse(self.tick())
        self.assertEqual(self.scenario.phase, 'holding')
        self.assertEqual(self.native.actions, ['original_select_ms1'])

    def test_bad_source_line_is_pending_failure_and_no_callback_exception(self):
        self.assertFalse(L.note_stats_return(100, 1, 678, 16, 1.0))
        with self.assertRaises(RuntimeError):
            self.tick()

    def test_source_contains_no_process_control_or_original_callback_replacement(self):
        path = os.path.join(ROOT, 'client_patch', 'long_hangar_scenario.py')
        with open(path, 'rb') as stream:
            source = stream.read().decode('utf8')
        for forbidden in ('subprocess', 'terminate(', '.kill(', 'BigWorld.quit(', 'BigWorld.callback(',
                          'requestServerStats(', '.receiveServerStats(', 'setattr('):
            self.assertNotIn(forbidden, source)

    def test_unarmed_normal_usage_has_no_events_or_imported_engine(self):
        L._armed, L._scenario = False, None
        count = len(self.events)
        self.assertFalse(L.note_stats_return(None, None, None, None, None))
        self.assertFalse(L.advance(self.record, {}, {}, False))
        self.assertEqual(len(self.events), count)
        self.assertNotIn('BigWorld', sys.modules)


if __name__ == '__main__':
    unittest.main(verbosity=2)
