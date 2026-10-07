"""Synthetic unit boundary checks only; never native descriptor compatibility."""
import copy
import importlib.util
import json
from pathlib import Path
import random
import tempfile
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'client_patch/ms1_crew_probe.py'
SPEC = importlib.util.spec_from_file_location('ms1_crew_probe_unit', SOURCE)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def synthetic_config():
    """IDs deliberately differ from the client; this is not a native fixture."""
    return {'normalGroups': [{'isFemales': False, 'firstNamesList': [12, 10, 11],
                             'lastNamesList': [22, 20, 21], 'iconsList': [32, 30, 31]}],
            'firstNames': {10: None, 11: None, 12: None},
            'lastNames': {20: None, 21: None, 22: None},
            'icons': {30: None, 31: None, 32: None}}


class PassportBoundsUnitTests(unittest.TestCase):
    def test_sorted_actual_ids_without_random_or_config_mutation(self):
        config = synthetic_config()
        before, rng = copy.deepcopy(config), random.getstate()
        self.assertEqual([(0, False, False, 10, 20, 30), (0, False, False, 11, 21, 31)],
                         PROBE.choose_passports(config))
        self.assertEqual(before, config)
        self.assertEqual(rng, random.getstate())

    def test_extra_rich_values_are_never_walked_or_stringified(self):
        class NeverTraverse:
            def __iter__(self):
                raise AssertionError('rich original value traversed')

            def __repr__(self):
                raise AssertionError('rich original value formatted')

        config = synthetic_config()
        config['ranks'] = NeverTraverse()
        config['firstNames'][10] = NeverTraverse()
        self.assertEqual(10, PROBE.choose_passports(config)[0][3])

    def test_rejects_ambiguous_group_and_wrong_sex_shape(self):
        for groups in ([], [synthetic_config()['normalGroups'][0]] * 2, None):
            config = synthetic_config()
            config['normalGroups'] = groups
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                PROBE.choose_passports(config)
        for value in (True, 0, None):
            config = synthetic_config()
            config['normalGroups'][0]['isFemales'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                PROBE.choose_passports(config)

    def test_invalid_missing_duplicate_and_oversized_passport_ids(self):
        for values in ([True, 11], [-1, 11], [11, 65536], [10, 10], [10],
                       list(range(2049)), [10, 11.0], [10, '11'], [10, 99]):
            config = synthetic_config()
            config['normalGroups'][0]['firstNamesList'] = values
            with self.subTest(count=len(values)), self.assertRaises(ValueError):
                PROBE.choose_passports(config)

    def test_container_limits_fail_before_rich_value_read(self):
        for config in (None, [], {str(i): None for i in range(33)}):
            with self.subTest(type=type(config).__name__), self.assertRaises(ValueError):
                PROBE.choose_passports(config)
        config = synthetic_config()
        config['icons'] = dict.fromkeys(range(4097))
        with self.assertRaises(ValueError):
            PROBE.choose_passports(config)


class InventoryShapeRegressionUnitTests(unittest.TestCase):
    def test_raw_column_keys_are_inventory_ids_not_type_compact_descriptors(self):
        # Shape-only UNIT labels. No synthetic native bytes or native API claim.
        fields = {'compDescr': {2: 'UNIT_IS7', 1: 'UNIT_MS1'},
                  'crew': {1: [None, None], 2: [None] * 5}, 'repair': {}}
        before = copy.deepcopy(fields)
        self.assertEqual((1, 2), PROBE._vehicle_inventory_ids(fields))
        self.assertEqual(before, fields)
        for wrong in ({3329: 'UNIT_VEH_DATA', 7169: 'UNIT_VEH_DATA'},
                      {1: 'UNIT_VEH_DATA', 2: 'UNIT_VEH_DATA'}):
            with self.subTest(keys=list(wrong)), self.assertRaises(ValueError):
                PROBE._vehicle_inventory_ids(wrong)

    def test_compact_values_and_other_native_fields_are_not_walked(self):
        class NeverRead:
            def __repr__(self):
                raise AssertionError('rich native value formatted')

            def __iter__(self):
                raise AssertionError('rich native value traversed')

        fields = {'compDescr': {1: NeverRead(), 2: NeverRead()}, 'crew': NeverRead()}
        self.assertEqual((1, 2), PROBE._vehicle_inventory_ids(fields))

    def test_missing_extra_foreign_and_noninteger_vehicle_ids_are_rejected(self):
        for compacts in ({}, {1: None}, {1: None, 2: None, 3: None},
                         {3329: None, 7169: None}, {True: None, 2: None},
                         {1.0: None, 2: None}, {'1': None, 2: None}):
            with self.subTest(keys=list(compacts)), self.assertRaises(ValueError):
                PROBE._vehicle_inventory_ids({'compDescr': compacts})

    def test_field_map_and_column_bounds_are_checked_before_use(self):
        for fields in (None, [], {}, {'crew': {}}, {'compDescr': None},
                       {'compDescr': []}, dict((str(i), None) for i in range(33))):
            with self.subTest(type=type(fields).__name__), self.assertRaises(ValueError):
                PROBE._vehicle_inventory_ids(fields)


class ObservationBoundsUnitTests(unittest.TestCase):
    def test_synthetic_scalar_observation_preserves_native_derived_training_xp(self):
        fields = SimpleNamespace(nationID=0, vehicleTypeID=13, role='commander', roleLevel=100,
                                 freeXP=0, lastSkillLevel=0, firstNameID=10, lastNameID=20,
                                 iconID=30, rankID=7, numLevelsToNextRank=50, skills=[],
                                 isPremium=False, isFemale=False, totalXP=lambda: 12345)
        values = PROBE._decoded_values(fields, (0, False, False, 10, 20, 30), 'commander')
        self.assertEqual((12345, 0, 7), (values['total_xp'], values['free_xp'], values['rank_id']))
        for field, value in (('roleLevel', 99), ('vehicleTypeID', 28), ('freeXP', 1),
                             ('role', 'driver'), ('firstNameID', 11), ('skills', ['repair']),
                             ('lastSkillLevel', 1), ('isPremium', True), ('rankID', True)):
            invalid = copy.copy(fields)
            setattr(invalid, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                PROBE._decoded_values(invalid, (0, False, False, 10, 20, 30), 'commander')

    def test_integer_bounds_reject_booleans_and_nonfinite_numbers(self):
        for value in (True, False, None, 1.0, float('nan'), float('inf'), -1, 65536):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PROBE._integer(value, 0, 65535, 'unit ID')

    def test_binary_type_and_size_checks_are_not_a_descriptor_parser(self):
        self.assertEqual(b'unit', PROBE._raw(b'unit', 1, 4, 'unit-only arbitrary bytes'))
        for value in ('unit', bytearray(b'unit'), b'', b'unit-overflow'):
            with self.subTest(type=type(value).__name__), self.assertRaises(ValueError):
                PROBE._raw(value, 1, 4, 'unit-only arbitrary bytes')

    def test_record_output_is_bounded_before_recorder(self):
        self.assertEqual(len(json.dumps({'x': 'unit'}, separators=(',', ':')).encode('ascii')),
                         PROBE._record_size({'x': 'unit'}))
        with self.assertRaises(ValueError):
            PROBE._record_size({'x': 'u' * (PROBE.MAX_JSON_BYTES + 1)})

    def test_source_reader_refuses_missing_or_mismatched_resource(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                PROBE._source_hashes(temporary)
            target = Path(temporary) / PROBE.SOURCE_HASHES[0][0]
            target.parent.mkdir(parents=True)
            target.write_bytes(b'explicit unit-only non-client file')
            with self.assertRaisesRegex(ValueError, 'differs from audited'):
                PROBE._source_hashes(temporary)


def synthetic_assignment():
    """Only domain observation scalars; no native descriptor or fake game API."""
    tankmen = []
    slots = []
    for index, role in enumerate(('commander', 'driver')):
        identity = 101 + index
        digest_label = 'synthetic-unit-label-%d-not-a-native-hash' % index
        tankmen.append({'inventory_id': identity, 'vehicle_inventory_id': 1,
                        'vehicle_slot_index': index, 'is_in_tank': True,
                        'combined_roles': list(PROBE.CREW_ROLES[index]),
                        'compact_descr_sha256': digest_label,
                        'effective_role_level': 100 if index == 0 else 110,
                        'decoded': {'nation_id': 0, 'vehicle_type_id': 13, 'role': role,
                                    'role_level': 100, 'free_xp': 0, 'skills': [],
                                    'last_skill_level': 0, 'is_premium': False, 'is_female': False}})
        slots.append({'slot_index': index, 'role': role, 'tankman_inventory_id': identity,
                      'tankman_compact_descr_sha256': digest_label})
    vehicles = [{'inventory_id': 1, 'type_compact_descr': 3329, 'crew': slots},
                {'inventory_id': 2, 'type_compact_descr': 7169,
                 'crew': [{'slot_index': index, 'tankman_inventory_id': None,
                           'tankman_compact_descr_sha256': None} for index in range(5)]}]
    return tankmen, vehicles


class AssignmentGateUnitTests(unittest.TestCase):
    def test_primitive_assignment_gate_does_not_normalize_effective_role_levels(self):
        tankmen, vehicles = synthetic_assignment()
        before = copy.deepcopy((tankmen, vehicles))
        status = PROBE.crew_status(tankmen, vehicles)
        self.assertTrue(status['ready'])
        self.assertEqual([101, 102], status['ms1_assigned_ids'])
        self.assertEqual(before, (tankmen, vehicles))
        self.assertEqual(110, tankmen[1]['effective_role_level'])

    def test_pregrant_empty_inventory_never_reports_ready(self):
        _, vehicles = synthetic_assignment()
        for slot in vehicles[0]['crew']:
            slot['tankman_inventory_id'] = None
            slot['tankman_compact_descr_sha256'] = None
        status = PROBE.crew_status([], vehicles)
        self.assertFalse(status['ready'])
        self.assertIn('crew_not_granted', status['issues'])

    def test_wrong_owner_slot_role_and_descriptor_binding_reject_readiness(self):
        for field, value in (('vehicle_inventory_id', 2), ('vehicle_slot_index', 1),
                             ('is_in_tank', False), ('combined_roles', ['driver']),
                             ('compact_descr_sha256', 'different-unit-label')):
            tankmen, vehicles = synthetic_assignment()
            tankmen[0][field] = value
            with self.subTest(field=field):
                self.assertFalse(PROBE.crew_status(tankmen, vehicles)['ready'])

    def test_partial_duplicate_foreign_and_is7_assignments_reject_readiness(self):
        for mode in ('partial', 'duplicate', 'foreign', 'is7'):
            tankmen, vehicles = synthetic_assignment()
            if mode == 'partial':
                tankmen.pop()
            elif mode == 'duplicate':
                vehicles[0]['crew'][1]['tankman_inventory_id'] = 101
            elif mode == 'foreign':
                vehicles[0]['crew'][1]['tankman_inventory_id'] = 909
            else:
                vehicles[1]['crew'][0]['tankman_inventory_id'] = 101
            with self.subTest(mode=mode):
                self.assertFalse(PROBE.crew_status(tankmen, vehicles)['ready'])

    def test_duplicate_identity_and_missing_native_slot_are_rejected(self):
        tankmen, vehicles = synthetic_assignment()
        tankmen[1]['inventory_id'] = tankmen[0]['inventory_id']
        with self.assertRaises(ValueError):
            PROBE.crew_status(tankmen, vehicles)
        tankmen, vehicles = synthetic_assignment()
        vehicles[0]['crew'][1]['slot_index'] = 0
        with self.assertRaises(ValueError):
            PROBE.crew_status(tankmen, vehicles)

    def test_changed_progress_or_training_policy_never_reports_ready(self):
        for field, value in (('nation_id', 1), ('vehicle_type_id', 28), ('role_level', 99),
                             ('free_xp', 10), ('skills', ['repair']), ('last_skill_level', 1),
                             ('is_premium', True), ('is_female', True)):
            tankmen, vehicles = synthetic_assignment()
            tankmen[0]['decoded'][field] = value
            with self.subTest(field=field):
                self.assertFalse(PROBE.crew_status(tankmen, vehicles)['ready'])

    def test_effective_role_numbers_reject_nonfinite_or_excessive_values(self):
        for value in (True, None, float('nan'), float('inf'), -1001, 1001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PROBE._number(value, -1000, 1000, 'unit-only bonus')
        self.assertEqual(110.0, PROBE._number(110.0, 0, 1000, 'unit-only effective level'))


if __name__ == '__main__':
    unittest.main()
