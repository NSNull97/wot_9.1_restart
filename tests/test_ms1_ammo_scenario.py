# -*- coding: utf-8 -*-
"""Bounds/order regression tests only; synthetic inputs do not prove native UI."""
import copy
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import ms1_ammo_scenario as A


def expected():
    account = {'database_id': 1, 'name': u'Unit_Ёж',
        'resources': {'credits': 100000, 'gold': 0, 'free_xp': 0},
        'statistics': {'battles': 0, 'wins': 0, 'losses': 0, 'draws': 0},
        'account_dossier_sha256': 'a' * 64,
        'vehicles': [{'inventory_id': 1, 'type_compact_descr': 3329,
                     'compact_descr_sha256': 'b' * 64, 'health': 90, 'crew_ids': [1, 2]},
                    {'inventory_id': 2, 'type_compact_descr': 7169,
                     'compact_descr_sha256': 'e' * 64, 'health': 2150, 'crew_ids': [None] * 5}],
        'tankmen': [{'inventory_id': i + 1, 'compact_descr_sha256': ('c', 'd')[i] * 64,
                    'vehicle_inventory_id': 1, 'vehicle_slot_index': i} for i in range(2)]}
    return {'version': 1, 'account': account, 'vehicle_inventory_id': 1,
            'vehicle_compact_descr_sha256': 'b' * 64, 'turret_compact_descr': 5891,
            'gun_compact_descr': 5892, 'max_ammo': 96,
            'shells': [{'compact_descr': cd, 'count': count}
                       for cd, count in zip(A.probe.SHELL_CDS, A.COUNTS)],
            'auto_load': False, 'storage_shells': []}


def actual(index=1):
    flat = [2570, 20, 2826, 0, 3082, 0]
    selection = {'database_id': 1, 'selected_inventory_id': 1,
                 'selected_descriptor_sha256': 'b' * 64}
    return {'version': 1, 'type_name': 'ussr:MS-1', 'type_id': [0, 13],
        'vehicle_inventory_id': 1, 'vehicle_type_compact_descr': 3329,
        'vehicle_compact_descr_sha256': 'b' * 64,
        'turret': {'resource_name': 'T-18_Standart', 'compact_descr': 5891},
        'gun': {'resource_name': '_37mm_Gochkins', 'compact_descr': 5892},
        'max_ammo': 96, 'shell_item_type': 10,
        'shells': [{'resource_name': name, 'item_id': [0, item_id], 'compact_descr': cd,
                    'kind': kind, 'compatible_with_mounted_gun': True}
                   for name, item_id, cd, kind in A.probe.SHELLS],
        'native_empty_ammo': [2570, 0, 2826, 0, 3082, 0],
        'native_default_ammo': [2570, 96, 2826, 0, 3082, 0],
        'observation': {'raw_shells': list(flat),
            'raw_layouts': [{'layout_index': [5891, 5892], 'shells': list(flat)}],
            'layout_index': [5891, 5892], 'mounted_layout_present': True,
            'storage_shells': [],
            'gui_shells': [{'compact_descr': cd, 'kind': kind, 'count': count,
                'default_count': count, 'is_bought_for_credits': False,
                'default_layout_value': [cd, count], 'inventory_count': 0,
                'buy_price': [0, 0], 'default_price': [0, 0]}
                for (_, _, cd, kind), count in zip(A.probe.SHELLS, A.COUNTS)],
            'native_loaded_pairs': [[2570, 20], [2826, 0], [3082, 0]],
            'native_layout_rows': [[2570, 20, False], [2826, 0, False], [3082, 0, False]],
            'ammo_sum': 20, 'default_ammo_sum': 20, 'ammo_max_size': 96,
            'is_ammo_full': True, 'is_auto_load': False},
        'selection_before': dict(selection), 'selection_after': dict(selection),
        'selection_unchanged': True, 'inventory_mutation_requested': False,
        'loaded_module_files': {'vehicles': 'synthetic-unit-only', 'account_shared': 'synthetic-unit-only'},
        'observation_index': index}


class FakeNative(object):
    def __init__(self):
        self.account, self.selected, self.owner = expected()['account'], 1, 100
        self.hangar, self.crew, self.panel, self.bound = 200, 201, 202, True
        self.ammo_value, self.observations = actual(), 0
        self.requests, self.actions, self.releases = [], [], 0
        self.png_ready, self.png_valid = True, True

    def state(self):
        return {'account_state': {'account': copy.deepcopy(self.account),
                'selected_inventory_id': self.selected, 'hangar_owner': self.hangar, 'crew_owner': self.crew},
                'account_owner': self.owner, 'ammunition_owner': self.panel, 'ammunition_flash_bound': self.bound}

    def select_ms1(self):
        self.actions.append('original_select_ms1')
        self.selected = 1

    def ammo(self, record):
        self.observations += 1
        result = copy.deepcopy(self.ammo_value)
        result['observation_index'] = self.observations
        record('ms1_ammo_observation', **result)
        return result

    def request(self, basename):
        if basename in self.requests:
            raise RuntimeError('unit duplicate request')
        self.requests.append(basename)

    def screenshot(self, basename):
        if not self.png_ready:
            return None
        return {'basename': basename, 'png_container_valid': self.png_valid,
                'native_pixels_review': 'NOT_RUN', 'unit_only': True}

    def release_context(self):
        self.releases += 1


class AmmoScenarioTests(unittest.TestCase):
    def setUp(self):
        A._armed, A._expected, A._scenario = False, None, None
        self.native, self.now, self.events = FakeNative(), 0.0, []
        A.arm(expected())
        self.scenario = A._Scenario({}, self.record, self.native, lambda: self.now)
        A._scenario = self.scenario

    def tearDown(self):
        A._armed, A._expected, A._scenario = False, None, None

    def record(self, event, **fields):
        self.events.append((event, fields))

    def tick(self, at=None, ready=True, observed=None):
        self.now = self.now + 1 if at is None else at
        if observed is None:
            observed = {'selected_inventory_id': self.native.selected, 'vehicle_model_loaded': True,
                        'vehicle': {'type_compact_descr': 3329}}
        return A.advance(self.record, {}, observed, ready)

    def until(self, target):
        while self.now < target:
            if self.tick():
                return True
        return False

    def test_positive_requires_hold_three_reads_and_two_complete_png(self):
        self.assertFalse(self.until(17))
        self.assertFalse(self.tick())  # end observation and PNG request at t18
        self.assertTrue(self.tick())   # native file has completed
        rows = [r for e, r in self.events if e == 'ms1_ammo_snapshot']
        self.assertEqual(['start', 'middle', 'end'], [r['moment'] for r in rows])
        self.assertEqual([2, 10, 18], [r['observed_at'] for r in rows])
        self.assertEqual([1, 2, 3], [r['ammo_observation_index'] for r in rows])
        self.assertEqual(1, len(set(r['fingerprint'] for r in rows)))
        self.assertEqual(3, self.native.observations)
        self.assertEqual(list(A.SCREENSHOTS), self.native.requests)
        self.assertEqual([], self.native.actions)
        complete = [r for e, r in self.events if e == 'ms1_ammo_complete'][0]
        self.assertGreaterEqual(complete['stable_seconds'], 16)
        self.assertFalse(complete['timed_exit'])
        self.assertFalse(complete['inventory_mutation_requested'])
        self.assertEqual('NOT_RUN', complete['native_pixels_review'])
        self.assertTrue(self.tick())
        self.assertEqual(1, len([e for e, r in self.events if e == 'ms1_ammo_complete']))

    def test_normal_unarmed_is_passive(self):
        A._armed, A._expected, A._scenario = False, None, None
        self.assertFalse(A.advance(None, None, None, None))
        self.assertIsNone(A._scenario)

    def test_arming_twice_is_rejected(self):
        self.assertRaises(RuntimeError, A.arm, expected())

    def test_public_expected_copy_and_no_secret_keys(self):
        source = expected()
        checked = A.checked_expected(source)
        checked['shells'][0]['count'] = 19
        self.assertEqual(20, source['shells'][0]['count'])
        source['password'] = 'unit-secret-must-not-be-accepted'
        self.assertRaises(ValueError, A.checked_expected, source)

    def test_expected_only_current20_policy_not_capacity_or_previous80(self):
        for value in (0, 19, 21, 80, 96, 97, True, 20.0, '20'):
            data = expected()
            data['shells'][0]['count'] = value
            self.assertRaises(ValueError, A.checked_expected, data)

    def test_reject_wrong_gun_capacity_identity_and_version(self):
        for key, value in (('version', True), ('version', 2), ('vehicle_inventory_id', 2),
                           ('turret_compact_descr', 5892), ('gun_compact_descr', 7169),
                           ('max_ammo', 92), ('vehicle_compact_descr_sha256', 'f' * 64)):
            data = expected()
            data[key] = value
            self.assertRaises(ValueError, A.checked_expected, data)

    def test_reject_foreign_or_misordered_expected_shell(self):
        data = expected()
        data['shells'].reverse()
        self.assertRaises(ValueError, A.checked_expected, data)
        data = expected()
        data['shells'][0]['compact_descr'] = -2570
        self.assertRaises(ValueError, A.checked_expected, data)

    def test_reject_autoload_and_spare_inventory_expectations(self):
        for key, value in (('auto_load', True), ('auto_load', 0),
                           ('storage_shells', [{'compact_descr': 2570, 'count': 20}])):
            data = expected()
            data[key] = value
            self.assertRaises(ValueError, A.checked_expected, data)

    def test_reject_missing_existing_is7_or_crew(self):
        data = expected()
        data['account']['vehicles'].pop()
        self.assertRaises(ValueError, A.checked_expected, data)
        data = expected()
        data['account']['tankmen'] = []
        data['account']['vehicles'][0]['crew_ids'] = [None, None]
        self.assertRaises(ValueError, A.checked_expected, data)

    def test_native_model_must_be_ready_before_first_snapshot(self):
        self.tick()
        self.tick(observed={'selected_inventory_id': 1, 'vehicle_model_loaded': False,
                            'vehicle': {'type_compact_descr': 3329}})
        self.assertEqual(0, self.native.observations)
        self.assertIsNone(self.scenario.began_at)

    def test_actual_original_selection_invoked_once_only_if_needed(self):
        self.native.selected = 2
        self.assertFalse(self.tick())
        self.assertEqual(['original_select_ms1'], self.native.actions)
        self.assertFalse(self.tick())
        self.assertEqual(1, len(self.native.actions))

    def test_ready_loss_after_snapshot_is_failure_not_reset_pass(self):
        self.until(3)
        self.assertRaises(RuntimeError, self.tick, ready=False)
        self.assertEqual('error', self.scenario.phase)
        self.assertEqual(1, self.native.releases)

    def test_sample_gap_greater_than2point5_rejected(self):
        self.until(3)
        self.assertRaises(RuntimeError, self.tick, at=5.6)

    def test_gap_boundary2point5_is_allowed(self):
        self.until(3)
        self.assertFalse(self.tick(at=5.5))
        self.assertEqual(2.5, self.scenario.max_gap)

    def test_clock_reversal_nan_inf_or_bool_rejected(self):
        for at in (-1, float('nan'), float('inf'), True):
            self.scenario.phase = 'waiting_hangar'
            self.now = at
            self.assertRaises(ValueError, self.scenario.advance, {}, False)

    def test_clock_reversal_after_actual_forward_sample_rejected(self):
        self.until(3)
        self.assertRaises(ValueError, self.tick, at=2.9)

    def test_actual_account_resources_changed_rejected(self):
        self.until(3)
        self.native.account['resources']['credits'] -= 1
        self.assertRaises(RuntimeError, self.tick)

    def test_native_owner_or_original_panel_changed_rejected(self):
        self.until(3)
        self.native.owner += 1
        self.assertRaises(RuntimeError, self.tick)

    def test_unbound_original_panel_rejected(self):
        self.native.bound = False
        self.assertRaises(ValueError, self.tick)

    def test_expected_data_does_not_override_actual_counts(self):
        self.native.ammo_value['observation']['raw_shells'][1] = 19
        self.tick()
        self.assertRaises(ValueError, self.tick)

    def test_raw_layout_not_count_only(self):
        data = actual()
        data['observation']['raw_layouts'][0]['shells'][1] = 96
        self.assertRaises(ValueError, A.checked_ammo, data, expected())

    def test_negative_currency_flag_not_silently_normalized(self):
        data = actual()
        data['observation']['raw_layouts'][0]['shells'][0] = -2570
        self.assertRaises(ValueError, A.checked_ammo, data, expected())

    def test_observed_bool_or_float_not_accepted_as_native_integer(self):
        for key, value in (('vehicle_inventory_id', True), ('shell_item_type', 10.0)):
            data = actual()
            data[key] = value
            self.assertRaises(ValueError, A.checked_ammo, data, expected())
        data = actual()
        data['observation']['raw_layouts'][0]['shells'][3] = False
        self.assertRaises(ValueError, A.checked_ammo, data, expected())
        data = actual()
        data['observation']['native_layout_rows'][0][2] = 0
        self.assertRaises(ValueError, A.checked_ammo, data, expected())

    def test_unknown_observation_field_rejected(self):
        data = actual()
        data['unexpected'] = 'not a native projection field'
        self.assertRaises(ValueError, A.checked_ammo, data, expected())

    def test_legacy_full_true_does_not_substitute_exact_quantity(self):
        data = actual()
        data['observation']['gui_shells'][0]['count'] = 96
        data['observation']['ammo_sum'] = 96
        self.assertTrue(data['observation']['is_ammo_full'])
        self.assertRaises(ValueError, A.checked_ammo, data, expected())

    def test_default_layout96_with_loaded20_rejected(self):
        data = actual()
        data['observation']['default_ammo_sum'] = 96
        data['observation']['gui_shells'][0]['default_count'] = 96
        self.assertRaises(ValueError, A.checked_ammo, data, expected())

    def test_gui_zero_or_missing_count_rejected(self):
        data = actual()
        data['observation']['gui_shells'][0]['count'] = 0
        self.assertRaises(ValueError, A.checked_ammo, data, expected())
        del data['observation']['gui_shells'][0]['count']
        self.assertRaises(ValueError, A.checked_ammo, data, expected())

    def test_midway_ammo_change_fails(self):
        self.until(9)
        self.native.ammo_value['observation']['gui_shells'][0]['count'] = 19
        self.assertRaises(ValueError, self.tick)
        self.assertFalse(self.scenario.completed)

    def test_second_png_required_and_invalid_png_rejected(self):
        self.until(18)
        self.native.png_ready = False
        self.assertFalse(self.tick())
        self.assertFalse(self.scenario.completed)
        self.native.png_ready, self.native.png_valid = True, False
        self.assertRaises(ValueError, self.tick)

    def test_missing_first_png_is_explicit_failure(self):
        self.native.png_ready = False
        self.until(17)
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual(['ammo_start'], self.native.requests)

    def test_startup_exhaustion_does_not_quit_or_complete(self):
        for _ in range(A.MAX_ADVANCES):
            self.assertFalse(self.tick(ready=False))
        self.assertRaises(RuntimeError, self.tick, ready=False)
        self.assertEqual([], self.native.requests)
        self.assertFalse(self.scenario.completed)

    def test_exhausted_second_png_never_claims_success(self):
        self.until(18)
        self.native.png_ready = False
        while self.scenario.advances < A.MAX_ADVANCES:
            self.assertFalse(self.tick())
        self.assertRaises(RuntimeError, self.tick)
        self.assertEqual('error', self.scenario.phase)
        self.assertEqual(3, self.native.observations)


if __name__ == '__main__':
    unittest.main()
