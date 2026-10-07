"""Original local resource/legacy-payload checks; never a native UI PASS.

Requires the configured readonly #717 original and existing local descriptor
evidence. Missing local inputs are an explicit NOT_RUN skip, never a mock.
No client, service or database is started or modified.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import hangar_state as state


class MountedModuleCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.descriptor_file = ROOT / 'local/evidence/20261004-p02-hangar/native-descriptors.json'
        if not (ROOT / 'config/project.local.json').is_file() or not cls.descriptor_file.is_file():
            raise unittest.SkipTest('NOT_RUN: configured original/native descriptor evidence missing')
        _, cls.paths = state.config()
        if not cls.paths['original_client_root'].is_dir():
            raise unittest.SkipTest('NOT_RUN: readonly original client missing')
        cls.native1, cls.source1 = state.descriptors(cls.descriptor_file, catalog_version=1)
        cls.native2, cls.source2 = state.descriptors(cls.descriptor_file, catalog_version=2)

    def test_prices_come_from_five_original_mounted_resources(self):
        prices = self.native2['mounted_module_prices']
        expected = {self.native1['components'][key] for key in ('chassis', 'turret', 'gun', 'engine', 'radio')}
        self.assertEqual(expected, set(prices))
        self.assertEqual(5, len(prices))
        self.assertEqual({(0, 0)}, set(prices.values()))
        self.assertNotIn(self.native1['components']['fuelTank'], prices)
        sources = self.source2['mounted_module_price_sources']
        self.assertEqual(expected, {item['compact_descr'] for item in sources})
        for item in sources:
            for key in ('id_source', 'price_source'):
                path = Path(item[key]['file']).resolve()
                self.assertTrue(path.is_relative_to(self.paths['original_client_root']))
                self.assertEqual(state.sha256(path), item[key]['sha256'])
            self.assertEqual(0, item['price_source']['source_value'])
            self.assertIs(False, item['price_source']['gold_child_present'])

    def test_declared_component_cannot_disagree_with_descriptor_bytes(self):
        native = deepcopy(self.native1)
        native['components']['engine'] += 256
        with self.assertRaisesRegex(ValueError, 'descriptor bytes'):
            state.mounted_module_reference_prices(native, self.paths['original_client_root'])

    def test_missing_extra_and_noninteger_component_ids_are_rejected(self):
        for mutation in ('missing', 'extra', 'boolean', 'negative', 'oversized'):
            native = deepcopy(self.native1)
            if mutation == 'missing':
                del native['components']['turret']
            elif mutation == 'extra':
                native['components']['invented'] = 1
            else:
                native['components']['radio'] = {'boolean': True, 'negative': -1, 'oversized': 0x1000000}[mutation]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                state.mounted_module_reference_prices(native, self.paths['original_client_root'])

    def test_unmeasured_customization_layout_or_vehicle_is_rejected(self):
        for field, value in (('compact_descr_hex', self.native1['compact_descr_hex'][:-2] + '01'),
                             ('compact_descr_hex', self.native1['compact_descr_hex'] + '00'),
                             ('type_name', 'ussr:another_vehicle'), ('type_compact_descr', 1)):
            native = deepcopy(self.native1)
            native[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                state.mounted_module_reference_prices(native, self.paths['original_client_root'])

    def test_only_shop_revision_and_exact_mounted_catalogue_change(self):
        before = deepcopy(self.native2)
        model1, compatibility1, payloads1 = state.fixture(self.native1, catalog_version=1)
        model2, compatibility2, payloads2 = state.fixture(self.native2, catalog_version=2)
        self.assertEqual(model1, model2)
        self.assertEqual(before, self.native2)
        self.assertEqual(1, compatibility1.pop('compatibility_catalog_revision'))
        self.assertEqual(2, compatibility2.pop('compatibility_catalog_revision'))
        self.assertEqual(compatibility1, compatibility2)
        for name in ('state.bin', 'dossier.bin'):
            self.assertEqual(state.encode_data(payloads1[name]), state.encode_data(payloads2[name]))
        shop = payloads2['shop.bin']
        self.assertEqual(2, shop['rev'])
        self.assertEqual(6, len(shop['items']['itemPrices']))
        for cd in self.native2['mounted_module_prices']:
            self.assertEqual((0, 0), shop['items']['itemPrices'].pop(cd))
            shop['items']['notInShopItems'].remove(cd)
        shop['rev'] = 1
        self.assertEqual(payloads1['shop.bin'], shop)

    def test_catalogue_cannot_include_an_uninstalled_fuel_or_other_item(self):
        for cd in (self.native2['components']['fuelTank'], 1):
            native = deepcopy(self.native2)
            native['mounted_module_prices'][cd] = (0, 0)
            with self.subTest(cd=cd), self.assertRaises(ValueError):
                state.fixture(native, catalog_version=2)

    def test_reference_price_schema_enforces_amount_bounds(self):
        cd = next(iter(self.native2['mounted_module_prices']))
        for value in (None, [0, 0], (0,), (True, 0), (-1, 0), (1 << 31, 0)):
            native = deepcopy(self.native2)
            native['mounted_module_prices'][cd] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                state.fixture(native, catalog_version=2)

    def test_catalogue_revision_and_native_input_are_explicit(self):
        for version in (True, 0, 3, '2'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                state.descriptors(self.descriptor_file, version)
        with self.assertRaisesRegex(ValueError, 'actual native'):
            state.fixture(catalog_version=2)

    def test_existing_primary_r1_account_payloads_are_preserved(self):
        # Inspect only this project's already-owned per-account fixture folder.
        candidates = sorted((ROOT / 'local/server/fixtures').glob('*/r1'))
        if not candidates:
            self.skipTest('NOT_RUN: no local primary r1 baseline to compare')
        self.assertLessEqual(len(candidates), 32, 'bounded diagnostic baseline inventory')
        for directory in candidates:
            self.assertTrue(directory.resolve().is_relative_to(ROOT / 'local/server/fixtures'))
            profile, _ = state.read_profile(directory / 'profile-input.json')
            model1, _, old = state.fixture(self.native1, profile, 1)
            model2, compatibility2, new = state.fixture(self.native2, profile, 2)
            self.assertEqual(model1, model2)
            self.assertEqual(profile['account_id'], compatibility2['account_id'])
            self.assertEqual(profile['native_database_id'], compatibility2['native_database_id'])
            for name in ('state.bin', 'shop.bin', 'dossier.bin'):
                baseline = state.read_limited(directory / name, state.MAX_BYTES)
                self.assertEqual(baseline, state.encode_data(old[name]), name + ' legacy bytes differ')
                if name != 'shop.bin':
                    self.assertEqual(baseline, state.encode_data(new[name]), name + ' account state changed')


if __name__ == '__main__':
    unittest.main()
