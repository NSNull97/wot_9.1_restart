"""Bounded incremental roster projection without a native-compatibility claim."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from tests.test_p04f_crew_projection import inventory as old_inventory
from p04h_crew_projection import RosterRecruitmentProjectionSource, POLICY_SHA256, native_crew, update_delta
from p04h_crew_store import plan_assignment
from p09d_ammo_projection import encode, MAX_UPDATE


class RosterProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = os.environ.get("P04H_TEST_BUNDLE") or os.environ.get("P04D_TEST_BUNDLE")
        if not bundle: raise unittest.SkipTest("NOT_RUN: verified bundle required")
        cls.source = RosterRecruitmentProjectionSource(bundle)

    def inventory(self):
        value = old_inventory(self.source)
        value.update(policy_sha256=POLICY_SHA256, free_recruitment_left=13)
        return value

    def hire(self, before, vehicle=2, slot=4):
        return plan_assignment(before, [3, vehicle, slot, 0], recruit=True, account_id=self.source.profile["account_id"])

    def test_new_descriptor_and_changed_assignments_only_with_complete_seat_arrays(self):
        before = self.inventory(); after = self.hire(before, 1, 1)
        inventory, seats = native_crew(after)
        expected = {"prevRev": 1, "rev": 2, "inventory": {8: {"vehicle": {3: -1, 4: 1},
            "compDescr": {4: inventory["compDescr"][4]}}, 1: {"crew": seats}}, "stats": {"freeTMenLeft": 12}}
        self.assertEqual(update_delta(after, 1, recruit=True, before_crew=before), encode(expected, MAX_UPDATE))

    def test_all_thirteen_recruitments_and_full_roster_whole_unload_fit_native_bound(self):
        current = self.inventory()
        for number in range(4, 17):
            before = current; current = self.hire(before, 2, (number - 4) % 5)
            for wire in (1, 65536, 2**31 - 2):
                self.assertLessEqual(len(update_delta(current, wire, recruit=True, before_crew=before)), 240)
        before = current; current = plan_assignment(before, [2, -1, -1])
        self.assertLessEqual(len(update_delta(current, 2**31 - 2, before_crew=before)), 240)
        self.assertEqual((len(current["members"]), current["free_recruitment_left"]), (16, 0))

    def test_repeated_loader_roles_have_distinct_compatible_seats(self):
        value = self.hire(self.inventory(), 2, 3)
        value = self.hire(value, 2, 4)
        self.assertEqual(native_crew(value)[1][2], [None, None, None, 4, 5])
        self.assertEqual([r["role"] for r in value["members"][-2:]], ["loader", "loader"])

    def test_quota_allocator_identity_descriptor_and_assignment_adversaries(self):
        original = self.hire(self.inventory())
        mutations = [lambda v: v.update(free_recruitment_left=13), lambda v: v.update(next_native_id=7),
            lambda v: v.update(configuration_revision=True), lambda v: v["members"][-1].update(role="gunner"),
            lambda v: v["members"][-1].update(descriptor_hex=v["members"][1]["descriptor_hex"]),
            lambda v: v["members"][-1].update(vehicle_native_id=2, seat=2),
            lambda v: v["members"][0].update(descriptor_hex="00" * 25),
            lambda v: v["members"][-1].update(crew_id=v["members"][0]["crew_id"])]
        for mutate in mutations:
            value = deepcopy(original); mutate(value)
            with self.assertRaises(ValueError): native_crew(value)

    def test_before_and_wire_revision_are_required_and_noop_is_not_success(self):
        before = self.inventory(); after = self.hire(before)
        with self.assertRaises(ValueError): update_delta(after, 1, recruit=True)
        with self.assertRaises(ValueError): update_delta(before, 1, before_crew=before)
        for wire in (True, 0, 2**31 - 1):
            with self.assertRaises(ValueError): update_delta(after, wire, recruit=True, before_crew=before)
