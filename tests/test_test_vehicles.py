"""Stand-only test vehicles (config/test_vehicles.json): the stand flag and the research overlay."""
import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import test_vehicles as tv  # noqa: E402

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')


class FlagTests(unittest.TestCase):
    def test_flag_values(self):
        self.assertFalse(tv.enabled({}))
        self.assertFalse(tv.enabled({tv.ENV: '0'}))
        self.assertTrue(tv.enabled({tv.ENV: '1'}))
        for bad in ('', 'yes', 'true', '2', ' 1'):
            with self.assertRaises(tv.TestVehicleError):
                tv.enabled({tv.ENV: bad})

    def test_research_identity_per_mode(self):
        self.assertEqual(tv.research_sha256({}), tv.BASE_RESEARCH_SHA256)
        self.assertEqual(tv.research_sha256({tv.ENV: '1'}), tv.TEST_LAB_RESEARCH_SHA256)
        self.assertNotEqual(tv.BASE_RESEARCH_SHA256, tv.TEST_LAB_RESEARCH_SHA256)


class SpecTests(unittest.TestCase):
    def test_spec_is_test_lab_and_bounded(self):
        spec, digest = tv.load()
        self.assertEqual(len(digest), 64)
        v = spec['vehicles'][0]
        self.assertEqual((v['vehicle_id'], v['native_type_id'], v['tier'], v['armor_mm']), ('vehicle:ussr:T62A_T', 50, 11, 1000))
        self.assertTrue(spec['classification'].startswith('TEST_LAB_STAND_ONLY'))


@unittest.skipUnless((ORIGINAL / 'res').is_dir(), 'original client absent')
class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from p09e_research_catalog import Catalog, load_catalog
        with mock.patch.dict('os.environ', {tv.ENV: '0'}):
            cls.base = load_catalog(str(ORIGINAL))
        with mock.patch.dict('os.environ', {tv.ENV: '1'}):
            cls.catalog = load_catalog(str(ORIGINAL))
        cls.Catalog = Catalog

    def test_main_mode_is_the_374_client_vehicles(self):
        self.assertEqual((len(self.base.vehicles), self.base.sha256), (374, tv.BASE_RESEARCH_SHA256))
        self.assertNotIn('vehicle:ussr:T62A_T', self.base.vehicles)

    def test_test_lab_mode_adds_exactly_the_test_vehicle(self):
        self.assertEqual((len(self.catalog.vehicles), self.catalog.sha256), (375, tv.TEST_LAB_RESEARCH_SHA256))
        self.assertEqual(sum('test_lab' in v for v in self.catalog.vehicles.values()), 1)
        self.assertEqual(self.Catalog(tv.research_overlay(self.base.document)).sha256, tv.TEST_LAB_RESEARCH_SHA256)

    def test_test_vehicle_is_derived_with_own_modules_and_base_tier(self):
        v, base = self.catalog.vehicles['vehicle:ussr:T62A_T'], self.catalog.vehicles['vehicle:ussr:T62A']
        self.assertEqual((v['native_compact_id'], v['tier'], v['resource_name']), ((50 << 8) + 1, 10, 'T62A_T'))
        self.assertEqual(v['defaults']['chassis'], 'module:ussr:chassis:Chassis_T62A_T')
        self.assertEqual(v['defaults']['gun'], base['defaults']['gun'])
        self.assertEqual(v['hull_max_hp'], base['hull_max_hp'])
        self.assertEqual(self.catalog.modules['module:ussr:chassis:Chassis_T62A_T']['native_compact_id'], (62 << 8) + 2)
        self.assertEqual(self.catalog.modules['module:ussr:turret:Turret_1_T62A_T']['native_compact_id'], (50 << 8) + 3)
        self.assertIn('vehicle:ussr:T62A_T', self.catalog.initial_unlocked)
        self.assertEqual(self.catalog.document['sources']['test_vehicles_sha256'], tv.load()[1])
        self.assertEqual(base['tier'], 10)

    def test_collisions_are_refused(self):
        spec, digest = tv.load()
        document = copy.deepcopy(self.base.document)
        self.assertEqual(len(tv.research_overlay(document, spec, digest)['vehicles']), 375)
        for key, value in (('native_type_id', 54), ('resource_name', 'T62A')):
            bad = copy.deepcopy(spec)
            bad['vehicles'][0][key] = value
            if key == 'resource_name':
                bad['vehicles'][0]['vehicle_id'] = 'vehicle:ussr:T62A'
            with self.assertRaises(tv.TestVehicleError):
                tv.research_overlay(document, bad, digest)
        bad = copy.deepcopy(spec)
        bad['vehicles'][0]['chassis']['id'] = 123
        with self.assertRaises(tv.TestVehicleError):
            tv.research_overlay(document, bad, digest)


if __name__ == '__main__':
    unittest.main()
