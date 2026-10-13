"""Real pinned profile4 crew projection; no client execution is implied."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    from p04d_crew_projection import CrewProjectionSource, native_crew, update_delta, shop_policy, POLICY_SHA256
    from p09d_ammo_projection import encode, MAX_UPDATE
except ModuleNotFoundError as error:
    if error.name not in ("p09d_ammo_projection", "p09d_ammo_store"):
        raise
    CrewProjectionSource = None

BUNDLE = Path(os.environ["P04D_TEST_BUNDLE"]) if os.environ.get("P04D_TEST_BUNDLE") else None


def roster(source, recruited=False):
    account = source.profile["account_id"]
    rows = [{"native_id": index, "crew_id": row["crew_id"], "role": row["role"],
             "descriptor_hex": source.descriptors[row["role"]], "vehicle_native_id": 1, "seat": index - 1}
            for index, row in enumerate(source.profile["crew"], 1)]
    if recruited:
        rows[1].update(vehicle_native_id=-1, seat=None)
        rows.append({"native_id": 3, "crew_id": account + ":recruit-ms1-driver:3", "role": "driver",
                     "descriptor_hex": source.descriptors["driver"], "vehicle_native_id": 1, "seat": 1})
    return {"policy_sha256": POLICY_SHA256, "free_recruitment_left": 0 if recruited else 1,
            "configuration_revision": 2 if recruited else 1, "next_native_id": 4 if recruited else 3,
            "members": rows}


class CrewProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if CrewProjectionSource is None or BUNDLE is None or not BUNDLE.is_dir():
            raise unittest.SkipTest("NOT_RUN: frozen P09D dependency and P04D_TEST_BUNDLE required")
        cls.source = CrewProjectionSource(BUNDLE)

    def test_initial_projection_retains_exact_two_source_descriptors_and_assignments(self):
        inventory, seats = native_crew(roster(self.source))
        self.assertEqual(inventory, self.source.trees["state.bin"]["inventory"][8])
        self.assertEqual(seats, [1, 2])

    def test_recruited_identity_is_separate_while_old_driver_stays_in_barracks(self):
        value = roster(self.source, True)
        inventory, seats = native_crew(value)
        self.assertEqual(seats, [1, 3])
        self.assertEqual(inventory["vehicle"], {1: 1, 2: -1, 3: 1})
        self.assertEqual(inventory["compDescr"][2], inventory["compDescr"][3])
        self.assertNotEqual(value["members"][1]["crew_id"], value["members"][2]["crew_id"])

    def test_delta_is_bounded_even_at_maximum_native_wire_revision(self):
        value = roster(self.source, True)
        inventory, seats = native_crew(value)
        for revision in (1, 127, 65536, 2**31 - 2):
            with self.subTest(revision=revision):
                actual = update_delta(value, revision)
                expected = {"prevRev": revision, "rev": revision + 1,
                    "inventory": {8: {"compDescr": {3: inventory["compDescr"][3]}, "vehicle": {2: -1, 3: 1}},
                                  1: {"crew": {1: [1, 3]}}}, "stats": {"freeTMenLeft": 0}}
                self.assertEqual(actual, encode(expected, MAX_UPDATE))
                self.assertLessEqual(len(actual), MAX_UPDATE)

    def test_invalid_policy_quota_allocation_seats_and_descriptors_fail_closed(self):
        original = roster(self.source, True)
        cases = []
        for key, value in (("free_recruitment_left", True), ("next_native_id", 3),
                           ("configuration_revision", 1), ("policy_sha256", "0" * 64)):
            changed = deepcopy(original); changed[key] = value; cases.append(changed)
        for index, key, value in ((2, "native_id", True), (2, "native_id", 4),
                                  (2, "descriptor_hex", "00" * 25), (2, "role", "commander"),
                                  (1, "vehicle_native_id", 1), (1, "seat", 1), (2, "seat", False)):
            changed = deepcopy(original); changed["members"][index][key] = value; cases.append(changed)
        changed = deepcopy(original); changed["members"][2]["crew_id"] = changed["members"][1]["crew_id"]; cases.append(changed)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    native_crew(value)

    def test_delta_rejects_unconsumed_quota_and_invalid_revision(self):
        with self.assertRaises(ValueError):
            update_delta(roster(self.source), 1)
        for revision in (True, -1, 0, 1.0, 2**31 - 1):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                update_delta(roster(self.source, True), revision)

    def test_shop_free_row_is_explicit_policy_without_invented_paid_prices(self):
        before = deepcopy(self.source.trees["shop.bin"])
        actual = shop_policy(before)
        self.assertEqual(actual["tankmanCost"], [{}])
        expected = deepcopy(before); expected["tankmanCost"] = [{}]
        self.assertEqual(actual, expected)
        self.assertEqual(before, self.source.trees["shop.bin"])


if __name__ == "__main__":
    unittest.main()
