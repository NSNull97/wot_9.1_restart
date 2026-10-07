"""Read-only real-corpus contracts plus explicitly non-native mutation controls."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import account_switch_expectations as subject

LOCAL = ROOT / 'local'
EVIDENCE = LOCAL / 'evidence/20261005-p02-account-switch/data'
PRIMARY = LOCAL / 'server/fixtures' / subject.PRIMARY / 'r3-catalog3'
SECONDARY = LOCAL / 'server/fixtures' / subject.SECONDARY / 'r1-catalog2'
EXPORT = LOCAL / 'evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json'


class FrozenAccountCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(p.exists() for p in (PRIMARY, SECONDARY, EXPORT)):
            raise unittest.SkipTest('NOT_RUN: own immutable native corpus is unavailable')
        cls.pair = subject.load_pair(PRIMARY, SECONDARY, EXPORT, LOCAL)
        cls.compatibility = [subject.json_file(folder, 'compatibility.json')[0]
                             for folder in (PRIMARY, SECONDARY)]

    def mutated_snapshot(self, callback, account=0):
        expected = copy.deepcopy(self.pair['expected'][account])
        compatibility = copy.deepcopy(self.compatibility[account])
        callback(expected, compatibility)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            subject.snapshot(expected, compatibility)

    def clone_secondary(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(prefix='unit-only-', dir=EVIDENCE)
        root = Path(directory.name).resolve()
        self.assertTrue(root.is_relative_to(EVIDENCE.resolve()))
        self.addCleanup(directory.cleanup)
        for name in ('r1', 'r1-catalog2'):
            shutil.copytree(SECONDARY.parent / name, root / name)
        return root / 'r1-catalog2'

    def test_actual_frozen_pair_has_distinct_owned_data(self):
        accounts = self.pair['expected_accounts']
        self.assertEqual([r['database_id'] for r in accounts], [1, 2])
        self.assertEqual([len(r['vehicles']) for r in accounts], [2, 1])
        self.assertEqual([len(r['tankmen']) for r in accounts], [2, 0])
        self.assertEqual(accounts[0]['vehicles'][0]['crew_ids'], [1, 2])
        self.assertEqual(accounts[1]['vehicles'][0]['crew_ids'], [None, None])
        self.assertNotEqual(accounts[0]['account_dossier_sha256'], accounts[1]['account_dossier_sha256'])
        self.assertEqual(self.pair['expected'][1]['dossier_cache'], None)
        self.assertEqual(self.pair['expected'][0]['dossier_cache']['vehicle_type_compact_descr'], 7169)
        self.assertNotIn('inventory', self.pair['expected'][1]['profile'])
        self.assertFalse(self.pair['provenance']['credentials_read'])

    def test_actual_output_agrees_with_pure_client_validator(self):
        sys.path.insert(0, str(ROOT / 'client_patch'))
        import account_switch_scenario
        actual = account_switch_scenario.checked_expected_accounts(self.pair['expected_accounts'])
        self.assertEqual(actual, self.pair['expected_accounts'])
        self.assertLessEqual(len(account_switch_scenario._encoded(actual, 6144)), 6144)

    def test_manifest_self_rehash_cannot_replace_accepted_fixture(self):
        directory = self.clone_secondary()
        path = directory / 'manifest.json'
        value = json.loads(path.read_bytes())
        value['native_database_id'] = 1
        path.write_text(json.dumps(value), encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'accepted pre-card audit'):
            subject.load_secondary_fixture(directory, LOCAL)

    def test_changed_payload_is_rejected_before_projection(self):
        directory = self.clone_secondary()
        path = directory / 'state.bin'
        raw = bytearray(path.read_bytes())
        raw[-2] ^= 1
        path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'payload hash or size'):
            subject.load_secondary_fixture(directory, LOCAL)

    def test_changed_historical_payload_is_rejected(self):
        directory = self.clone_secondary()
        path = directory.parent / 'r1/dossier.bin'
        path.write_bytes(path.read_bytes() + b'.')
        with self.assertRaisesRegex(ValueError, 'payload hash or size'):
            subject.load_secondary_fixture(directory, LOCAL)

    def test_catalog_migration_path_escape_is_rejected(self):
        directory = self.clone_secondary()
        path = directory / 'catalog-migration.json'
        value = json.loads(path.read_bytes())
        value['previous']['directory'] = '../r1'
        path.write_text(json.dumps(value), encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'migration source'):
            subject.load_secondary_fixture(directory, LOCAL)

    def test_catalog_migration_profile_substitution_is_rejected(self):
        directory = self.clone_secondary()
        path = directory / 'catalog-migration.json'
        value = json.loads(path.read_bytes())
        value['previous']['profile_sha256'] = subject.PINS[subject.PRIMARY][1]
        path.write_text(json.dumps(value), encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'migration profile hash'):
            subject.load_secondary_fixture(directory, LOCAL)

    def test_duplicate_json_key_is_rejected(self):
        directory = self.clone_secondary()
        (directory / 'catalog-migration.json').write_bytes(b'{"version":1,"version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            subject.json_file(directory, 'catalog-migration.json')

    def test_nonfinite_json_and_deep_nesting_are_rejected(self):
        directory = self.clone_secondary()
        path = directory / 'catalog-migration.json'
        for raw in (b'{"value":NaN}', b'{"value":' + b'[' * 17 + b'0' + b']' * 17 + b'}'):
            with self.subTest(kind=raw[:16]):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    subject.json_file(directory, 'catalog-migration.json')

    def test_boolean_database_id_is_not_integer_one(self):
        self.mutated_snapshot(lambda e, c: e['profile'].__setitem__('native_database_id', True))

    def test_missing_native_balance_is_not_filled_from_profile(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'stats'].__delitem__(b'gold'))

    def test_changed_balance_is_not_hidden_by_same_domain_profile(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'stats'].__setitem__(b'credits', 99999))

    def test_boolean_statistic_is_not_zero(self):
        self.mutated_snapshot(lambda e, c: e['profile']['statistics'].__setitem__('battles', False))

    def test_dossier_text_or_truncated_bytes_are_rejected(self):
        for dossier in ('not-native-bytes', b'\0' * 87):
            with self.subTest(kind=type(dossier).__name__):
                self.mutated_snapshot(lambda e, c: e['state'][b'stats'].__setitem__(b'dossier', dossier))

    def test_unknown_inventory_category_is_rejected(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'inventory'].__setitem__(9, {}))

    def test_foreign_vehicle_compatibility_is_rejected(self):
        self.mutated_snapshot(lambda e, c: c['vehicle_mapping'][0].__setitem__('native_inventory_id', 9))

    def test_foreign_type_mapping_is_rejected(self):
        self.mutated_snapshot(lambda e, c: c['vehicle_mapping'][0].__setitem__('type_compact_descr', 7169))

    def test_truncated_native_vehicle_descriptor_is_rejected(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'inventory'][1][b'compDescr'].__setitem__(1, b'\x01\x0d'))

    def test_health_outside_native_descriptor_is_rejected(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'inventory'][1][b'repair'].__setitem__(1, (0, 91)))

    def test_secondary_cannot_reference_primary_tankman(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'inventory'][1][b'crew'].__setitem__(1, [1, None]), 1)

    def test_duplicate_or_boolean_tankman_assignment_is_rejected(self):
        for value in ([1, 1], [True, 2]):
            with self.subTest(value=value):
                self.mutated_snapshot(lambda e, c: e['state'][b'inventory'][1][b'crew'].__setitem__(1, value))

    def test_reverse_tankman_assignment_must_match_owned_vehicle(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'inventory'][8][b'vehicle'].__setitem__(1, 2))

    def test_missing_crew_column_does_not_become_empty(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'inventory'][1].__delitem__(b'crew'))

    def test_fleet_count_bound_precedes_iteration(self):
        self.mutated_snapshot(lambda e, c: e['state'][b'inventory'][1].__setitem__(b'compDescr',
            {i: b'\x01' * 15 for i in range(1, 10)}))


if __name__ == '__main__':
    unittest.main()
