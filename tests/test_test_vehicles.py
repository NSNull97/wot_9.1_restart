"""Stand-only test vehicle overlay of the research catalogue (config/test_vehicles.json)."""
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

    def test_activation_is_shared_by_both_import_paths(self):
        import tools.test_vehicles as other
        try:
            tv.activate()
            self.assertTrue(other.active())
        finally:
            tv.deactivate_for_tests()
        self.assertFalse(other.active())


@unittest.skipUnless((ORIGINAL / 'res').is_dir(), 'original client absent')
class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from p09e_research_catalog import load_catalog, Catalog
        cls.Catalog = Catalog
        tv.deactivate_for_tests()
        cls.base = load_catalog(str(ORIGINAL))
        try:
            tv.activate()
            cls.test = load_catalog(str(ORIGINAL))
        finally:
            tv.deactivate_for_tests()

    def test_default_catalogue_is_unchanged_without_activation(self):
        from p09e_research_catalog import load_catalog
        self.assertEqual(load_catalog(str(ORIGINAL)).sha256, self.base.sha256)
        self.assertEqual(len(self.base.vehicles), 374)

    def test_overlay_adds_one_derived_vehicle_with_own_modules(self):
        self.assertEqual(len(self.test.vehicles), 375)
        self.assertNotEqual(self.test.sha256, self.base.sha256)
        v, base = self.test.vehicles['vehicle:ussr:T62A_T'], self.base.vehicles['vehicle:ussr:T62A']
        self.assertEqual((v['native_compact_id'], v['tier'], v['resource_name']), ((50 << 8) + 1, 11, 'T62A_T'))
        self.assertEqual(v['defaults']['chassis'], 'module:ussr:chassis:Chassis_T62A_T')
        self.assertEqual(v['defaults']['gun'], base['defaults']['gun'])
        self.assertEqual(v['hull_max_hp'], base['hull_max_hp'])
        self.assertEqual(self.test.modules['module:ussr:chassis:Chassis_T62A_T']['native_compact_id'], (62 << 8) + 2)
        self.assertEqual(self.test.modules['module:ussr:turret:Turret_1_T62A_T']['native_compact_id'], (50 << 8) + 3)
        self.assertIn('vehicle:ussr:T62A_T', self.test.initial_unlocked)
        self.assertEqual(self.test.document['sources']['test_vehicles_sha256'], tv.load()[1])

    def test_collisions_are_refused(self):
        spec, digest = tv.load()
        for key, value in (('native_type_id', 54), ('resource_name', 'T62A')):
            bad = copy.deepcopy(spec)
            bad['vehicles'][0][key] = value
            if key == 'resource_name':
                bad['vehicles'][0]['vehicle_id'] = 'vehicle:ussr:T62A'
            with self.assertRaises(tv.TestVehicleError):
                tv.research_overlay(self.base.document, bad, digest)
        bad = copy.deepcopy(spec)
        bad['vehicles'][0]['chassis']['id'] = 123
        with self.assertRaises(tv.TestVehicleError):
            tv.research_overlay(self.base.document, bad, digest)


if __name__ == '__main__':
    unittest.main()
