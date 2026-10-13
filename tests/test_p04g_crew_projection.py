"""Exact two-vehicle wire projection and source-bound descriptor validation."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from tests.test_p04f_crew_projection import inventory as old_inventory
from p04g_crew_projection import CrossVehicleCrewProjectionSource, POLICY_SHA256, native_crew, update_delta
from p09d_ammo_projection import encode,MAX_UPDATE


class CrossVehicleProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle=os.environ.get("P04G_TEST_BUNDLE") or os.environ.get("P04F_TEST_BUNDLE") or os.environ.get("P04D_TEST_BUNDLE")
        if not bundle:raise unittest.SkipTest("NOT_RUN: verified source bundle required")
        cls.source=CrossVehicleCrewProjectionSource(bundle)

    def inventory(self):
        value=old_inventory(self.source);value["policy_sha256"]=POLICY_SHA256
        return value

    def test_both_rosters_exact_initial_source_retained_descriptors(self):
        inventory,seats=native_crew(self.inventory())
        self.assertEqual(seats,{1:[1,3],2:[None]*5})
        self.assertEqual(inventory["compDescr"][1],self.source.trees["state.bin"]["inventory"][8]["compDescr"][1])
        self.assertEqual(inventory["compDescr"][2],inventory["compDescr"][3])

    def test_cross_delta_contains_both_complete_arrays_and_no_passport_mutation(self):
        crew=self.inventory();crew["members"][2].update(vehicle_native_id=2,seat=2)
        for revision in (1,65536,2**31-2):
            expected={"prevRev":revision,"rev":revision+1,"inventory":{8:{"vehicle":{1:1,2:-1,3:2}},1:{"crew":{1:[1,None],2:[None,None,3,None,None]}}}}
            actual=update_delta(crew,revision)
            self.assertEqual(actual,encode(expected,MAX_UPDATE));self.assertLessEqual(len(actual),MAX_UPDATE)

    def test_whole_unload_preserves_none_in_all_seven_seats(self):
        crew=self.inventory()
        for row in crew["members"]:row.update(vehicle_native_id=-1,seat=None)
        inventory,seats=native_crew(crew)
        self.assertEqual(seats,{1:[None,None],2:[None]*5})
        self.assertEqual(inventory["vehicle"],{1:-1,2:-1,3:-1})

    def test_roles_duplicate_seats_nation_descriptor_and_unknown_vehicle_fail_closed(self):
        original=self.inventory()
        mutations=[lambda v:v["members"][0].update(vehicle_native_id=2,seat=1),
            lambda v:v["members"][2].update(vehicle_native_id=2,seat=1),
            lambda v:v["members"][2].update(vehicle_native_id=2,seat=4),
            lambda v:v["members"][2].update(vehicle_native_id=3,seat=2),
            lambda v:v["members"][2].update(vehicle_native_id=2,seat=True),
            lambda v:v["members"][1].update(vehicle_native_id=1,seat=1),
            lambda v:v["members"][2].update(descriptor_hex="00"*25),
            lambda v:v.update(free_recruitment_left=1),lambda v:v.update(configuration_revision=True)]
        for mutate in mutations:
            value=deepcopy(original);mutate(value)
            with self.assertRaises(ValueError):native_crew(value)

    def test_G_cannot_project_new_recruitment_or_invalid_wire_revision(self):
        with self.assertRaises(ValueError):update_delta(self.inventory(),1,recruit=True)
        for revision in (0,True,2**31-1):
            with self.assertRaises(ValueError):update_delta(self.inventory(),revision)
