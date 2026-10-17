"""Guards for the source-bound P05C/P04M follow-up matrix."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import p05c_followup_matrix as matrix


class MatrixDefinitionTests(unittest.TestCase):
    def test_pairwise_and_bounded_rosters_cover_requested_kinds(self):
        pairs = matrix.cases_for("pairwise")
        self.assertEqual(len(pairs), 25)
        self.assertEqual(set(pairs), {(left, right) for left in matrix.KINDS for right in matrix.KINDS})
        six = matrix.cases_for("max-6")
        self.assertEqual(len(six), 1)
        self.assertEqual(len(six[0]), 6)
        self.assertTrue(set(six[0]) == set(matrix.KINDS))

    def test_every_case_has_explicit_actor_slots_and_native_not_run(self):
        cases = matrix.build_cases("all", ("slope_push_stop", "ram_stationary_target"))
        self.assertEqual(len(cases), 27 * 2)
        for case in cases:
            slots = [actor["slot"] for actor in case["actors"]]
            self.assertEqual(slots, list(range(len(slots))))
            self.assertTrue(2 <= len(slots) <= 6)
            self.assertEqual(case["native"], "NOT_RUN")
            self.assertEqual(case["worker_result"], "NOT_RUN")

    def test_unknown_filter_and_scenario_are_rejected(self):
        with self.assertRaises(matrix.MatrixError):
            matrix.cases_for("everything")
        with self.assertRaises(matrix.MatrixError):
            matrix.build_cases("pairwise", ("invented",))


class ProfileGuardTests(unittest.TestCase):
    def test_current_five_profiles_are_source_bound(self):
        for kind, relative in matrix.PROFILE_PATHS.items():
            with self.subTest(kind=kind):
                profile = matrix.validate_profile(ROOT / relative, kind)
                self.assertEqual(profile["kind"], kind)
                self.assertRegex(profile["sha256"], r"^[0-9a-f]{64}$")
                if kind in ("t26", "t34", "t3485"):
                    self.assertFalse(profile["battle_admission"])

    def test_qualified_admission_or_kind_tamper_is_rejected(self):
        source = ROOT / matrix.PROFILE_PATHS["t26"]
        value = json.loads(source.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            for field, replacement in (("battle_admission", True), ("kind", "t34")):
                altered = copy.deepcopy(value)
                altered[field] = replacement
                path.write_text(json.dumps(altered), encoding="utf-8")
                with self.subTest(field=field), self.assertRaises(matrix.MatrixError):
                    matrix.validate_profile(path, "t26")

    def test_missing_profile_is_reported_as_not_run_and_output_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "matrix.json"
            result = matrix.run(root, output, "pairwise", ("flat_straight",))
            self.assertEqual(result["status"], "NOT_RUN_MISSING_PROFILES")
            self.assertEqual(result["native_gate"], "NOT_RUN")
            self.assertEqual(len(result["missing_profiles"]), 5)
            self.assertTrue(output.is_file())


class ReceiptGuardTests(unittest.TestCase):
    def test_empty_handling_receipt_stays_not_run(self):
        receipt = matrix.validate_handling_receipt({"scenario": "uphill_powered_turn_left",
                                                     "samples": [], "profile_sha256": "a" * 64})
        self.assertEqual(receipt["status"], "NOT_RUN")

    def test_handling_receipt_checks_sequence_and_contact_bounds(self):
        sample = {"seq": 0, "forward_mps": 1.0, "lateral_mps": 0.0,
                  "yaw_rate_dps": 2.0, "slope_grade": 0.12, "contacts": 6}
        checked = matrix.validate_handling_receipt({"scenario": "uphill_powered_turn_left",
                                                    "samples": [sample], "profile_sha256": "a" * 64})
        self.assertEqual(checked["status"], "CHECKED_TELEMETRY")
        bad = copy.deepcopy(sample)
        bad["contacts"] = 7
        with self.assertRaises(matrix.MatrixError):
            matrix.validate_handling_receipt({"scenario": "x", "samples": [bad],
                                              "profile_sha256": "a" * 64})

    def test_handling_quality_guard_catches_observed_reverse_drift(self):
        samples = [
            {"seq": 0, "forward_mps": 0.0, "lateral_mps": 0.0, "yaw_rate_dps": 0.0,
             "slope_grade": 0.12, "contacts": 6,
             "control": {"throttle": 1, "steer": 1, "brake": False}},
            {"seq": 1, "forward_mps": -1.0, "lateral_mps": 0.0, "yaw_rate_dps": 0.0,
             "slope_grade": 0.12, "contacts": 6,
             "control": {"throttle": 1, "steer": 1, "brake": False}},
        ]
        checks = matrix.handling_quality_checks({"scenario": "uphill_powered_turn_left",
                                                 "samples": samples,
                                                 "profile_sha256": "a" * 64})
        statuses = {check["gate"]: check["status"] for check in checks}
        self.assertEqual(statuses["forward_command_no_reverse_drift"], "FAIL")
        self.assertEqual(statuses["steer_channel_has_response"], "FAIL")

    def test_handling_quality_guard_does_not_claim_without_controls(self):
        sample = {"seq": 0, "forward_mps": 1.0, "lateral_mps": 0.0,
                  "yaw_rate_dps": 2.0, "slope_grade": 0.12, "contacts": 6}
        checks = matrix.handling_quality_checks({"scenario": "uphill_powered_turn_left",
                                                 "samples": [sample],
                                                 "profile_sha256": "a" * 64})
        self.assertEqual(checks[0]["status"], "NOT_RUN")

    def test_resting_contact_has_no_ram_damage_and_duplicate_is_rejected(self):
        event = {"impact_id": "contact-1", "attacker_slot": 0, "victim_slot": 1,
                 "relative_speed_mps": 0.0, "normal_speed_mps": 0.0, "impulse_ns": 10.0,
                 "damage": 0.0, "damage_status": "NO_DAMAGE"}
        self.assertEqual(matrix.validate_ram_receipts([event])["events"], 1)
        duplicate = [event, dict(event)]
        with self.assertRaisesRegex(matrix.MatrixError, "duplicate"):
            matrix.validate_ram_receipts(duplicate)
        harmful_rest = dict(event, damage=1.0, damage_status="APPLIED")
        with self.assertRaisesRegex(matrix.MatrixError, "resting"):
            matrix.validate_ram_receipts([harmful_rest])


if __name__ == "__main__":
    unittest.main()
