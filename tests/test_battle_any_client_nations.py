"""BATTLE-ANY 3d: the CREW-ANY client windows resolve tankmen by (nation, type)."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch')); sys.path.insert(0, str(ROOT / 'tools'))
import catalog_v1_hints
import crew_vehicles
import p04k_crew_ui as barracks

ROWS = dict((row['kind'], row) for row in catalog_v1_hints.VEHICLES)


def nation_without(type_id):
    """A nation whose catalogue has no vehicle of this type id (the full main catalogue since the CONTENT-0
    transfer shares many type ids across nations, so a fixed nation is no longer free)."""
    used = set((row['native_compact_id'] >> 4) & 15 for row in catalog_v1_hints.VEHICLES if row['type_id'] == type_id)
    return next((n for n in range(7) if n not in used), None)


class ClientCrewNations(unittest.TestCase):
    def setUp(self):
        crew_vehicles.disable(); crew_vehicles.enable(catalog_v1_hints)
        self.addCleanup(crew_vehicles.disable)

    def test_shared_type_ids_resolve_by_nation(self):
        sherman, chi_ri = ROWS['usa-M4_Sherman'], ROWS['japan-Chi_Ri']
        self.assertEqual(sherman['type_id'], chi_ri['type_id'])
        self.assertEqual(crew_vehicles.kind_by_type(sherman['type_id'], 2)['kind'], 'usa-M4_Sherman')
        self.assertEqual(crew_vehicles.kind_by_type(chi_ri['type_id'], 6)['kind'], 'japan-Chi_Ri')
        # A type id is resolved per nation: one used by only some nations is absent in the others.
        type_id = next(r['type_id'] for r in catalog_v1_hints.VEHICLES if nation_without(r['type_id']) is not None)
        self.assertIsNone(crew_vehicles.kind_by_type(type_id, nation_without(type_id)))
        self.assertEqual(crew_vehicles.kind_by_type(ROWS['ms1']['type_id'])['kind'], 'ms1')
        self.assertIn((1, ROWS['germany-Waffentrager_E100']['type_id']), crew_vehicles.trained_pairs())

    def test_barracks_selector_uses_the_vehicle_nation(self):
        wt = ROWS['germany-Waffentrager_E100']
        targets = dict(barracks.catalog_selector_target(wt['type_id'], wt['primary_roles'][0], 1))
        self.assertEqual((targets['nationDropdown'], targets['vehicleTypeDropdown']), (1, wt['type_id']))
        with self.assertRaises(ValueError):
            barracks.catalog_selector_target(wt['type_id'], wt['primary_roles'][0], nation_without(wt['type_id']))
        self.assertEqual(dict(barracks.catalog_selector_target(ROWS['t26']['type_id'], 'driver'))['nationDropdown'], 0)


if __name__ == '__main__':
    unittest.main()
