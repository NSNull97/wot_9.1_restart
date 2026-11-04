"""Stand-only test vehicles (config/test_vehicles.json) in the server research catalogue."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import test_vehicles as tv  # noqa: E402

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')


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
        from p09e_research_catalog import load_catalog
        cls.catalog = load_catalog(str(ORIGINAL))

    def test_catalogue_is_the_374_client_vehicles_plus_the_test_vehicle(self):
        self.assertEqual(len(self.catalog.vehicles), 375)
        self.assertEqual(sum('test_lab' in v for v in self.catalog.vehicles.values()), 1)

    def test_test_vehicle_is_derived_with_own_modules(self):
        v, base = self.catalog.vehicles['vehicle:ussr:T62A_T'], self.catalog.vehicles['vehicle:ussr:T62A']
        self.assertEqual((v['native_compact_id'], v['tier'], v['resource_name']), ((50 << 8) + 1, 11, 'T62A_T'))
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
        document = copy.deepcopy(self.catalog.document)
        del document['vehicles']['vehicle:ussr:T62A_T']
        for key in ('module:ussr:chassis:Chassis_T62A_T', 'module:ussr:turret:Turret_1_T62A_T'):
            del document['modules'][key]
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
