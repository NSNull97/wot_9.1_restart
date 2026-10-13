"""Verified profile source and vacancy/delta projection, no native execution."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from p04f_crew_projection import CrewTransferProjectionSource, POLICY_SHA256, native_crew, update_delta
from p09d_ammo_projection import encode, MAX_UPDATE
from tests.test_p04d_crew_projection import roster


def inventory(source, recruited=True):
    value = roster(source, recruited)
    value["policy_sha256"] = POLICY_SHA256
    return value


class TransferProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle = os.environ.get("P04F_TEST_BUNDLE") or os.environ.get("P04D_TEST_BUNDLE")
        if not bundle:
            raise unittest.SkipTest("NOT_RUN: verified P04F_TEST_BUNDLE required")
        cls.source = CrewTransferProjectionSource(bundle)

    def test_original_and_recruited_assignments_keep_source_descriptors(self):
        for recruited, seats in ((False, [1, 2]), (True, [1, 3])):
            value, actual = native_crew(inventory(self.source, recruited))
            self.assertEqual(actual, seats)
            for key in (1, 2):
                self.assertEqual(value["compDescr"][key], self.source.trees["state.bin"]["inventory"][8]["compDescr"][key])

    def test_vacant_seats_are_none_and_barracks_vehicle_minus_one(self):
        value = inventory(self.source)
        for row in value["members"]:
            row.update(vehicle_native_id=-1, seat=None)
        value["configuration_revision"] = 100
        actual, seats = native_crew(value)
        self.assertEqual(seats, [None, None])
        self.assertEqual(actual["vehicle"], {1: -1, 2: -1, 3: -1})

    def test_assignment_delta_never_resends_or_changes_descriptor(self):
        crew = inventory(self.source)
        crew["members"][2].update(vehicle_native_id=-1, seat=None)
        crew["configuration_revision"] = 3
        for revision in (1, 65536, 2**31 - 2):
            expected = {"prevRev": revision, "rev": revision + 1,
                "inventory": {8: {"vehicle": {1: 1, 2: -1, 3: -1}}, 1: {"crew": {1: [1, None]}}}}
            self.assertEqual(update_delta(crew, revision), encode(expected, MAX_UPDATE))

    def test_recruit_delta_preserves_vacant_commander_and_fits_native_envelope(self):
        crew = inventory(self.source)
        crew["members"][0].update(vehicle_native_id=-1, seat=None)
        crew["configuration_revision"] = 25
        actual = update_delta(crew, 2**31 - 2, recruit=True)
        self.assertLessEqual(len(actual), MAX_UPDATE)
        self.assertIn(bytes.fromhex(self.source.descriptors["driver"]), actual)
        self.assertEqual(native_crew(crew)[1], [None, 3])

    def test_duplicate_seat_incompatible_role_and_false_integer_fail_closed(self):
        original = inventory(self.source)
        mutations = [lambda v:v["members"][1].update(vehicle_native_id=1, seat=1),
            lambda v:v["members"][0].update(seat=1), lambda v:v["members"][2].update(seat=True),
            lambda v:v.update(configuration_revision=True), lambda v:v.update(configuration_revision=2**31),
            lambda v:v["members"][2].update(descriptor_hex="00"*25), lambda v:v.update(free_recruitment_left=1)]
        for change in mutations:
            value = deepcopy(original); change(value)
            with self.assertRaises(ValueError):
                native_crew(value)

    def test_wire_revision_bounds_and_wrong_quota_reject(self):
        for revision in (True, 0, -1, 2**31 - 1):
            with self.assertRaises(ValueError):
                update_delta(inventory(self.source), revision)
        with self.assertRaises(ValueError):
            update_delta(inventory(self.source, False), 1, recruit=True)
