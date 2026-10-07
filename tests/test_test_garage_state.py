"""Explicit-grant invariants using actual local #717 resources/evidence.

These are generator/provenance checks, never native two-vehicle acceptance.
Missing original inputs are marked NOT_RUN; client/server/DB are never started.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import test_garage_state as garage


class TestGarageState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ms1_file = ROOT / 'local/evidence/20261004-p02-hangar/native-descriptors.json'
        cls.is7_file = ROOT / 'local/evidence/20261004-p02-hangar-ui/ui06-catalog2-manual-runtime/original-vehicle-is7.json'
        cls.base_file = ROOT / 'local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1-catalog2/profile-input.json'
        if not all(p.is_file() for p in (cls.ms1_file, cls.is7_file, cls.base_file, ROOT / 'config/project.local.json')):
            raise unittest.SkipTest('NOT_RUN: actual native exports and primary baseline required')
        cls.ms1, cls.is7, cls.native_sources = garage.read_native_inputs(cls.ms1_file, cls.is7_file)
        cls.base, cls.base_source, cls.base_raw = garage.read_base_profile(cls.base_file)
        cls.granted_at_ms = max(cls.base['created_at_ms'],
                                struct.unpack_from('<I', cls.is7['vehicle_dossier'], 52)[0] * 1000)
        cls.profile = garage.promote_profile(cls.base, cls.base_source['sha256'], cls.granted_at_ms)
        cls.scratch = ROOT / 'local/evidence/20261004-p02-hangar-ui/is7-generator'
        cls.scratch.mkdir(exist_ok=True)

    def test_native_descriptor_and_reference_prices_match_real_resources(self):
        self.assertEqual(7169, self.is7['type_compact_descr'])
        self.assertEqual(2150, self.is7['max_health'])
        self.assertEqual([['commander'], ['gunner'], ['driver'], ['loader'], ['loader', 'radioman']], self.is7['crew_roles'])
        self.assertEqual({14850: (82500, 0), 12035: (66000, 0), 14852: (297000, 0),
                          9221: (132000, 0), 2823: (51600, 0)}, self.is7['mounted_module_prices'])
        self.assertNotIn(52486, self.is7['mounted_module_prices'])
        for row in self.native_sources['is7']['mounted_module_price_sources']:
            for kind in ('id_source', 'price_source'):
                source = row[kind]
                self.assertEqual(source['sha256'], garage.sha256(Path(source['file'])))

    def test_promotion_is_deterministic_and_preserves_input_identity_and_resources(self):
        before = deepcopy(self.base)
        result = garage.promote_profile(self.base, self.base_source['sha256'], self.granted_at_ms)
        self.assertEqual(self.profile, result)
        self.assertEqual(before, self.base)
        self.assertEqual(2, result['snapshot_revision'])
        for field in ('account_id', 'native_database_id', 'created_at_ms', 'username', 'resources', 'statistics'):
            self.assertEqual(before[field], result[field])

    def test_only_authorized_vehicle_changes_state_and_reversal_recovers_exact_baseline(self):
        model, compatibility, trees, preservation = garage.build_payloads(
            self.profile, self.base, self.base_source['sha256'], self.ms1, self.is7)
        old = garage.legacy.fixture(self.ms1, self.base, 2)[2]
        self.assertEqual((2, 1, 3), (model['snapshot_revision'], trees['state.bin']['rev'], trees['shop.bin']['rev']))
        self.assertEqual([1, 2], [x['native_inventory_id'] for x in compatibility['vehicle_mapping']])
        self.assertEqual(12, len(trees['shop.bin']['items']['itemPrices']))
        current = trees['state.bin']['inventory'][1]
        for field, previous in old['state.bin']['inventory'][1].items():
            self.assertEqual(previous[1], current[field][1], field)
        self.assertEqual((0, 2150), current['repair'][2])
        self.assertEqual([None] * 5, current['crew'][2])
        self.assertEqual([], current['shells'][2])
        self.assertEqual(bytes.fromhex(self.is7['compact_descr_hex']), current['compDescr'][2])
        self.assertEqual(old['state.bin']['stats']['dossier'], trees['state.bin']['stats']['dossier'])
        self.assertEqual(preservation['base_state_sha256'], preservation['account_and_ms1_restored_state_sha256'])
        # This verifies the actual old bytes, not just a model round trip.
        self.assertEqual((self.base_file.parent / 'state.bin').read_bytes(), garage.legacy.encode_data(old['state.bin']))
        self.assertEqual((self.base_file.parent / 'shop.bin').read_bytes(), garage.legacy.encode_data(old['shop.bin']))
        self.assertEqual((self.base_file.parent / 'dossier.bin').read_bytes(), garage.legacy.encode_data(old['dossier.bin']))

    def test_dossier_owner_is_vehicle_type_and_only_creation_time_changes(self):
        trees = garage.build_payloads(self.profile, self.base, self.base_source['sha256'], self.ms1, self.is7)[2]
        version, entries = trees['dossier.bin']
        self.assertEqual(1, version)
        self.assertEqual(1, len(entries))
        owner, stamp, raw = entries[0]
        self.assertEqual(7169, owner)
        self.assertNotEqual(2, owner)
        self.assertEqual(self.granted_at_ms // 1000, stamp)
        self.assertEqual(self.is7['vehicle_dossier'][:52], raw[:52])
        self.assertEqual(self.is7['vehicle_dossier'][56:], raw[56:])
        self.assertEqual(stamp, struct.unpack_from('<I', raw, 52)[0])
        _, compatibility, _, preservation = garage.build_payloads(
            self.profile, self.base, self.base_source['sha256'], self.ms1, self.is7)
        self.assertEqual({'version': 1, 'last_change_time': stamp, 'vehicle_type_compact_descr': 7169},
                         compatibility['dossier_cache'])
        self.assertEqual(garage.digest(garage.legacy.encode_data(trees['dossier.bin'])),
                         preservation['dossier_cache']['payload_sha256'])

    def test_delta_gate_refuses_hidden_account_shop_or_dossier_changes(self):
        old = garage.legacy.fixture(self.ms1, self.base, 2)[2]
        trees = garage.build_payloads(self.profile, self.base, self.base_source['sha256'], self.ms1, self.is7)[2]
        mutations = [lambda x: x['state.bin']['stats'].update(gold=1),
                     lambda x: x['state.bin']['inventory'][1]['repair'].update({1: (0, 89)}),
                     lambda x: x['state.bin']['stats']['unlocks'].append(9999),
                     lambda x: x['shop.bin'].update(dailyXPFactor=5),
                     lambda x: x['shop.bin']['items']['itemPrices'].update({14850: (1, 0)}),
                     lambda x: x.update({'dossier.bin': (0, [(2, 0, self.is7['vehicle_dossier'])])})]
        for index, mutation in enumerate(mutations):
            candidate = deepcopy(trees)
            mutation(candidate)
            with self.subTest(index=index), self.assertRaises(ValueError):
                garage.verify_delta(old, candidate, self.base, self.profile, self.is7)

    def test_cross_account_and_changed_resource_or_history_profiles_are_rejected(self):
        mutations = [lambda p: p.update(account_id='00000000-0000-4000-8000-000000000001'),
                     lambda p: p.update(native_database_id=p['native_database_id'] + 1),
                     lambda p: p.update(username='another_account'),
                     lambda p: p['resources'].update(credits=p['resources']['credits'] + 1),
                     lambda p: p['statistics'].update(battles=1),
                     lambda p: p.update(created_at_ms=p['created_at_ms'] + 1),
                     lambda p: p['inventory'][0].update(inventory_id=p['account_id'] + ':replaced'),
                     lambda p: p['inventory'][1].update(health=1),
                     lambda p: p['inventory'][1].update(crew_assigned=True),
                     lambda p: p['inventory'][1].update(ammunition_count=10),
                     lambda p: p['test_grant'].update(grant_id='another-grant')]
        for index, mutation in enumerate(mutations):
            candidate = deepcopy(self.profile)
            mutation(candidate)
            with self.subTest(index=index), self.assertRaises(ValueError):
                garage.validate_profile(candidate, self.base, self.base_source['sha256'])

    def test_second_account_has_its_own_uuid_mapping_and_preserved_nondefault_balances(self):
        base = deepcopy(self.base)
        base.update(account_id='00000000-0000-4000-8000-000000000002', native_database_id=77,
                    username='Танкист_Ёж', resources={'credits': 123456, 'gold': 7, 'free_xp': 8})
        source = garage.digest(json.dumps(base).encode('utf8'))
        profile = garage.promote_profile(base, source, self.granted_at_ms)
        model, compat, trees, _ = garage.build_payloads(profile, base, source, self.ms1, self.is7)
        self.assertEqual(base['resources'], model['resources'])
        self.assertEqual(base['username'], compat['client_name'])
        self.assertEqual(base['account_id'], compat['account_id'])
        self.assertEqual(77, compat['native_database_id'])
        self.assertEqual((123456, 7, 8), tuple(trees['state.bin']['stats'][key] for key in ('credits', 'gold', 'freeXP')))
        self.assertTrue(all(x['inventory_id'].startswith(base['account_id'] + ':') for x in compat['vehicle_mapping']))
        with self.assertRaises(ValueError):
            garage.validate_profile(profile, self.base, self.base_source['sha256'])

    def test_exact_raw_base_hash_is_required_even_when_json_values_are_equal(self):
        changed_whitespace = self.base_raw + b'\n'
        self.assertEqual(json.loads(self.base_raw), json.loads(changed_whitespace))
        with self.assertRaises(ValueError):
            garage.validate_profile(self.profile, self.base, garage.digest(changed_whitespace))

    def test_profile_type_bounds_and_extra_inventory_are_rejected(self):
        for field, value in [('profile_version', True), ('snapshot_revision', True), ('native_database_id', True),
                             ('created_at_ms', float(self.base['created_at_ms']))]:
            candidate = deepcopy(self.profile)
            candidate[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                garage.validate_profile(candidate, self.base, self.base_source['sha256'])
        for value in (None, [], self.profile['inventory'] * 2):
            candidate = deepcopy(self.profile)
            candidate['inventory'] = value
            with self.subTest(inventory=value), self.assertRaises(ValueError):
                garage.validate_profile(candidate, self.base, self.base_source['sha256'])
        for stamp in (True, self.base['created_at_ms'] - 1, 2147483648000):
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                garage.promote_profile(self.base, self.base_source['sha256'], stamp)

    def test_json_duplicate_depth_and_size_bounds(self):
        for raw in (b'{"a":1,"a":2}', b'[' * 10 + b'0' + b']' * 10,
                    b'"' + b'x' * 8192 + b'"', b'{"n":NaN}'):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                garage.bounded_json(raw)

    def test_fractional_or_ambiguous_reference_prices_are_refused(self):
        self.assertEqual(82500, garage.integral_reference_price('82500.0'))
        self.assertEqual(66000, garage.integral_reference_price('66000.0'))
        for price in (True, -1, 1 << 31, '01', '1.5', '1e3', '+1', '-1', 'nan', 0.5, '2147483648.0'):
            with self.subTest(price=price), self.assertRaises(ValueError):
                garage.integral_reference_price(price)

    def test_wrong_resource_component_and_descriptor_flags_are_rejected(self):
        _, paths = garage.config()
        for kind in ('engine', 'gun'):
            native = deepcopy(self.is7)
            native['components'][kind] += 256
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                garage.is7_reference_prices(native, paths['original_client_root'])
        native = deepcopy(self.is7)
        native['compact_descr_hex'] = native['compact_descr_hex'][:-2] + '01'
        with self.assertRaises(ValueError):
            garage.is7_reference_prices(native, paths['original_client_root'])

    def test_played_or_unrecognized_dossier_is_never_rewritten(self):
        for raw in (self.is7['vehicle_dossier'][:-1], self.is7['vehicle_dossier'] + b'\0',
                    self.is7['vehicle_dossier'][:56] + b'\1' + self.is7['vehicle_dossier'][57:],
                    b'\x50' + self.is7['vehicle_dossier'][1:]):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                garage.grant_vehicle_dossier(raw, self.granted_at_ms)

    def test_existing_output_and_foreign_paths_are_refused(self):
        with self.assertRaises(ValueError):
            garage.local_file(ROOT / 'README.md')
        with tempfile.TemporaryDirectory(dir=self.scratch) as directory:
            root = Path(directory).resolve()
            self.assertTrue(root.is_relative_to(ROOT / 'local'))
            profile = root / 'proposed.json'
            profile.write_text(json.dumps(self.profile), 'utf8')
            output = root / 'snapshot'
            first = garage.generate(profile, self.base_file, self.ms1_file, self.is7_file, output)
            manifest = json.loads((output / 'manifest.json').read_text('utf8'))
            self.assertEqual(16, len(manifest))
            self.assertLess((output / 'manifest.json').stat().st_size, 32768)
            self.assertEqual(self.base_raw, (output / 'base-profile-input.json').read_bytes())
            self.assertEqual(profile.read_bytes(), (output / 'profile-input.json').read_bytes())
            self.assertTrue(all(x['bytes'] <= 16384 for x in first['files']))
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
            with self.assertRaises(FileExistsError):
                garage.generate(profile, self.base_file, self.ms1_file, self.is7_file, output)
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
            self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()
