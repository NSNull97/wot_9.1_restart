"""Generic trusted assignment rules; synthetic vehicles are not native evidence."""
from dataclasses import replace
import unittest
from server.domain.crew_transfer import Assignment, AssignmentError, transfer_assignments


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.rows = (Assignment(11, "leader", 101, 0), Assignment(12, "operator", 101, 1),
                     Assignment(25, "operator", -1, None), Assignment(31, "operator", 222, 3))
        self.roles = (frozenset({"leader"}), frozenset({"operator", "specialist"}))

    def plan(self, slot, tankman, **kw):
        return transfer_assignments(self.rows, 101, self.roles, slot, tankman, kw.get("berths", 16))

    def test_replace_preserves_identity_and_displaces_occupant(self):
        result = self.plan(1, 25)
        self.assertEqual(result[1], replace(self.rows[1], vehicle_id=-1, seat=None))
        self.assertEqual(result[2], replace(self.rows[2], vehicle_id=101, seat=1))
        self.assertEqual(tuple(r.tankman_id for r in result), (11, 12, 25, 31))
        self.assertEqual(self.rows[1].vehicle_id, 101)

    def test_second_vehicle_and_non_ms1_seat_map_use_same_transition(self):
        roles = tuple(frozenset({"operator"}) for _ in range(4))
        result = transfer_assignments(self.rows, 222, roles, 3, 25, 16)
        self.assertEqual(result[2], replace(self.rows[2], vehicle_id=222, seat=3))
        self.assertEqual(result[3], replace(self.rows[3], vehicle_id=-1, seat=None))
        self.assertEqual(result[:2], self.rows[:2])

    def test_cross_vehicle_transfer_vacates_original_assignment(self):
        result = self.plan(1, 31)
        self.assertEqual(result[3], replace(self.rows[3], vehicle_id=101, seat=1))
        self.assertFalse(any(r.vehicle_id == 222 for r in result))

    def test_empty_and_whole_vehicle_unload_preserve_other_vehicle(self):
        result = self.plan(-1, -1)
        self.assertEqual([r.vehicle_id for r in result], [-1, -1, -1, 222])
        result = transfer_assignments(result, 101, self.roles, 1, 12, 16)
        self.assertEqual(result[1].vehicle_id, 101)
        self.assertEqual(result[0].vehicle_id, -1)

    def test_allowed_role_set_can_have_multiple_roles(self):
        rows = (Assignment(7, "specialist", -1, None),)
        result = transfer_assignments(rows, 999, self.roles, 1, 7, 0)
        self.assertEqual(result[0].vehicle_id, 999)

    def test_capacity_is_checked_on_result_including_displacement(self):
        self.assertEqual(self.plan(1, 25, berths=1)[1].vehicle_id, -1)
        with self.assertRaisesRegex(AssignmentError, "BARRACKS_FULL"):
            self.plan(-1, -1, berths=2)

    def test_no_change_is_explicit_rejection(self):
        with self.assertRaisesRegex(AssignmentError, "NO_ASSIGNMENT_CHANGE"):
            self.plan(0, 11)
        empty = self.plan(-1, -1)
        with self.assertRaisesRegex(AssignmentError, "NO_ASSIGNMENT_CHANGE"):
            transfer_assignments(empty, 101, self.roles, -1, -1, 16)

    def test_unknown_foreign_role_and_invalid_selection_rejected(self):
        for slot, tankman in ((1, 77), (-1, 11), (2, -1), (True, -1), (1, False), (1, 11)):
            with self.subTest(slot=slot, tankman=tankman), self.assertRaises(AssignmentError):
                self.plan(slot, tankman)

    def test_duplicate_identity_or_seat_rejected(self):
        for extra in (self.rows[0], Assignment(77, "leader", 101, 0)):
            with self.assertRaises(AssignmentError):
                transfer_assignments(self.rows + (extra,), 101, self.roles, 1, -1, 16)

    def test_input_bounds_and_boolean_aliases_rejected(self):
        for rows, vehicle, roles, berths in ((iter(self.rows), 101, self.roles, 16),
            (self.rows * 257, 101, self.roles, 16), (self.rows, True, self.roles, 16),
            (self.rows, 101, ({"operator"},) * 33, 16), (self.rows, 101, self.roles, True)):
            with self.subTest(vehicle=vehicle, berths=berths), self.assertRaises(AssignmentError):
                transfer_assignments(rows, vehicle, roles, 1, -1, berths)
