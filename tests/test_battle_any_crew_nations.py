"""BATTLE-ANY 3d: pool tankman passports carry the vehicle's nation (CAT-01 mode)."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import catalog_v1
import catalog_v1_data
import p04m_pool_crew as crew
from p04h_tankman_descriptor import CATALOG_BOUNDS


class CrewNations(unittest.TestCase):
    def setUp(self):
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.addCleanup(catalog_v1.deactivate_for_tests)

    def test_ussr_passports_are_byte_identical_to_the_v1_rule(self):
        for identity in range(4, 193):
            old = tuple((identity - 1) % CATALOG_BOUNDS[k] + 1 for k in ("first_name_id", "last_name_id", "icon_id"))
            self.assertEqual(crew.name_ids(identity), old)
            self.assertEqual(crew.name_ids(identity, 0), old)
        raw = crew.passport(5, 13, "commander", 192)  # MS-1, nation 0
        self.assertEqual(raw[0], 8)

    def test_pilot_nations_get_their_own_header_and_passport_sets(self):
        for kind in ("usa-M4_Sherman", "germany-Waffentrager_E100", "japan-Chi_Ri", "ussr-KV-3"):
            row = catalog_v1.by_kind(kind)
            nation, type_id = row["nation_id"], row["native_compact_id"] >> 8
            self.assertEqual((row["native_compact_id"] >> 4) & 15, nation)
            role = row["crew"][0]["roles"][0]
            for identity in (4, 50, 192):
                raw = crew.passport(identity, type_id, role, 192, nation)
                self.assertEqual(raw[0], 8 + (nation << 4), kind)
                decoded = crew.decode(raw)
                self.assertEqual((decoded["nation_id"], decoded["vehicle_type_id"], decoded["role"]), (nation, type_id, role))
                ids = crew.nation_passports(nation)
                self.assertIn(decoded["first_name_id"], ids["first_name_id"])
                self.assertIn(decoded["last_name_id"], ids["last_name_id"])
                self.assertEqual(crew.base_descriptor(decoded), raw)

    def test_type_ids_shared_across_nations_resolve_by_nation(self):
        sherman, chi_ri = catalog_v1.by_kind("usa-M4_Sherman"), catalog_v1.by_kind("japan-Chi_Ri")
        self.assertEqual(sherman["native_compact_id"] >> 8, chi_ri["native_compact_id"] >> 8)
        self.assertEqual(crew.profile_for_type(sherman["native_compact_id"] >> 8, 2)[0], "usa-M4_Sherman")
        self.assertEqual(crew.profile_for_type(chi_ri["native_compact_id"] >> 8, 6)[0], "japan-Chi_Ri")
        # A passport ID outside the nation's exact (non-contiguous) set is refused.
        japan = crew.nation_passports(6)
        missing = next(v for v in range(1, 300) if v not in japan["last_name_id"])
        with self.assertRaises(Exception):
            crew.unskilled(vehicle_type_id=4, role="commander", role_level=50, first_name_id=japan["first_name_id"][0],
                           last_name_id=missing, icon_id=1, nation_id=6)


if __name__ == "__main__":
    unittest.main()
