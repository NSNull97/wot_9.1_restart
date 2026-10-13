"""Isolated configuration tests; all account identities and mass audits are synthetic.

These fixtures exercise a trusted upstream contract. They do not demonstrate
native compatibility, real vehicle mass, account grants, or battle admission.
Source facts are independently checked by the separate source-audit tests.
"""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import unittest

from server.domain import crew_equipment as domain


COMPONENT_SHA = hashlib.sha256(b"synthetic component configuration, not native bytes").hexdigest()
MASS_EVIDENCE_SHA = hashlib.sha256(b"synthetic upstream mass authority fixture").hexdigest()
OTHER_SHA = "b" * 64
VENT1 = "optional_device:improvedVentilation_class1"
VENT3 = "optional_device:improvedVentilation_class3"
AIM = "optional_device:enhancedAimDrives"
OPTICS = "optional_device:coatedOptics"
ROSTERS = {
    "vehicle:ms1": [["commander", "gunner", "radioman", "loader"], ["driver"]],
    "vehicle:is7": [["commander"], ["gunner"], ["driver"], ["loader"], ["loader", "radioman"]],
}


def candidate(vehicle="vehicle:ms1", devices=None):
    return {
        "format": "crew-equipment-input.v1",
        "policy": "test_lab.crew-equipment.717.v1",
        "account_id": "synthetic-account:alice",
        "vehicle_inventory_id": "synthetic-vehicle:owned-1",
        "vehicle_definition_id": vehicle,
        "configuration_revision": 7,
        "component_configuration_sha256": COMPONENT_SHA,
        "crew": [{
            "crew_id": "synthetic-crew:seat-" + str(seat), "seat": seat,
            "role": roles[0], "role_level": 100,
            "trained_vehicle_definition_id": vehicle,
            "vehicle_inventory_id": "synthetic-vehicle:owned-1",
            "healthy": True, "skills": [],
        } for seat, roles in enumerate(ROSTERS[vehicle])],
        "optional_devices": [None, None, None] if devices is None else devices[:],
    }


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def trusted(raw, *, mass=None):
    # Deliberately independent from parsed candidate fields: this simulates
    # authenticated state supplying its own account, reservation and revision.
    return domain.TrustedBinding(
        account_id="synthetic-account:alice",
        vehicle_inventory_id="synthetic-vehicle:owned-1",
        configuration_revision=7,
        configuration_sha256=hashlib.sha256(raw).hexdigest(),
        component_configuration_sha256=COMPONENT_SHA,
        policy_sha256=domain.POLICY_SHA256,
        mass_budget=mass,
    )


def synthetic_mass(base=10_000_000, maximum=11_000_000):
    """Synthetic budget ONLY: these numbers are not historical vehicle masses."""
    return domain.MassBudget(COMPONENT_SHA, MASS_EVIDENCE_SHA, base, maximum)


class CrewEquipmentTests(unittest.TestCase):
    def build(self, value=None, *, mass=None):
        raw = encode(candidate() if value is None else value)
        return domain.build_snapshot(raw, binding=trusted(raw, mass=mass))

    def reject(self, value, pattern=None, *, mass=None):
        raw = encode(value)
        with self.assertRaisesRegex(domain.ConfigurationError, pattern or ".+"):
            domain.build_snapshot(raw, binding=trusted(raw, mass=mass))

    def reject_raw(self, raw, pattern=None):
        with self.assertRaisesRegex(domain.ConfigurationError, pattern or ".+"):
            domain.build_snapshot(raw, binding=trusted(raw))

    def test_baseline_ms1_has_native_roster_identity_modifiers_and_no_runtime_claim(self):
        result = self.build().as_dict()
        self.assertEqual(result["vehicle_type_compact_descr"], 3329)
        self.assertEqual([r["roles"] for r in result["crew"]], ROSTERS["vehicle:ms1"])
        self.assertEqual([r["base_role_level"] for r in result["crew"]], [100, 100])
        self.assertEqual(result["static_modifiers"], {
            "crewLevelIncrease": {"numerator": 0, "denominator": 1},
            "gunAimingTimeFactor": {"numerator": 1, "denominator": 1},
            "circularVisionRadiusFactor": {"numerator": 1, "denominator": 1},
        })
        self.assertEqual(result["optional_devices"], [None, None, None])
        self.assertEqual(result["operations_in_slot_order"], [])
        self.assertIsNone(result["mass_check"])
        self.assertIs(result["runtime_ready"], False)
        self.assertEqual(result["runtime_acceptance"], "NOT_RUN")
        self.assertIn("crew-to-battle-characteristic-formula", result["unknown"])
        self.assertIn("battle-admission", result["unsupported"])
        self.assertNotIn("reload_time", result)
        self.assertNotIn("display_role_level", result["crew"][0])

    def test_is7_baseline_preserves_two_distinct_loader_seats(self):
        result = self.build(candidate("vehicle:is7")).as_dict()
        self.assertEqual(result["vehicle_type_compact_descr"], 7169)
        self.assertEqual([r["roles"] for r in result["crew"]], ROSTERS["vehicle:is7"])
        self.assertEqual([r["seat"] for r in result["crew"]], list(range(5)))
        self.assertNotEqual(result["crew"][3]["crew_id"], result["crew"][4]["crew_id"])
        self.assertEqual(result["crew"][3]["roles"], ["loader"])
        self.assertEqual(result["crew"][4]["roles"], ["loader", "radioman"])

    def test_equipped_both_vehicles_apply_exact_source_rationals_in_slot_order(self):
        for vehicle, vent, compact, extra_mass in [
            ("vehicle:ms1", VENT1, 4601, 200_000),
            ("vehicle:is7", VENT3, 5113, 300_000),
        ]:
            with self.subTest(vehicle=vehicle):
                result = self.build(candidate(vehicle, [OPTICS, vent, AIM]), mass=synthetic_mass()).as_dict()
                self.assertEqual(result["static_modifiers"], {
                    "circularVisionRadiusFactor": {"numerator": 11, "denominator": 10},
                    "crewLevelIncrease": {"numerator": 5, "denominator": 1},
                    "gunAimingTimeFactor": {"numerator": 91, "denominator": 100},
                })
                self.assertEqual([d["compact_descr"] for d in result["optional_devices"]], [1529, compact, 6649])
                operations = result["operations_in_slot_order"]
                self.assertEqual([op["slot"] for op in operations], [0, 1, 2])
                self.assertEqual([op["operation"] for op in operations], ["multiply", "add", "multiply"])
                self.assertEqual([op["operand"] for op in operations], [
                    {"numerator": 11, "denominator": 10}, {"numerator": 5, "denominator": 1},
                    {"numerator": 91, "denominator": 100},
                ])
                self.assertEqual(result["mass_check"]["optional_device_mass_grams"], extra_mass)
                self.assertEqual(result["mass_check"]["total_mass_grams"], 10_000_000 + extra_mass)
                self.assertEqual(result["mass_check"]["evidence_sha256"], MASS_EVIDENCE_SHA)

    def test_empty_middle_slot_retains_installed_positions(self):
        result = self.build(candidate(devices=[AIM, None, OPTICS]), mass=synthetic_mass()).as_dict()
        self.assertIsNone(result["optional_devices"][1])
        self.assertEqual([op["slot"] for op in result["operations_in_slot_order"]], [0, 2])

    def test_reordered_crew_is_sorted_by_seat_without_losing_identity(self):
        value = candidate("vehicle:is7")
        first = self.build(value)
        value["crew"].reverse()
        reordered = self.build(value)
        result = reordered.as_dict()
        self.assertEqual([row["crew_id"] for row in result["crew"]],
                         ["synthetic-crew:seat-" + str(i) for i in range(5)])
        self.assertEqual(first.as_dict()["crew"], result["crew"])
        # Exact candidate bytes remain part of the authority binding, even
        # though the consumer-facing crew list is normalized by seat.
        self.assertNotEqual(first.as_dict()["configuration_sha256"], result["configuration_sha256"])
        self.assertNotEqual(first.sha256, reordered.sha256)

    def test_swapping_devices_preserves_aggregate_but_changes_slot_provenance(self):
        first = self.build(candidate(devices=[AIM, None, OPTICS]), mass=synthetic_mass()).as_dict()
        second = self.build(candidate(devices=[OPTICS, None, AIM]), mass=synthetic_mass()).as_dict()
        self.assertEqual(first["static_modifiers"], second["static_modifiers"])
        self.assertNotEqual(first["operations_in_slot_order"], second["operations_in_slot_order"])

    def test_duplicate_crew_identity_is_rejected(self):
        value = candidate()
        value["crew"][1]["crew_id"] = value["crew"][0]["crew_id"]
        self.reject(value, "duplicate crew/seat")

    def test_duplicate_seat_is_rejected_even_with_distinct_identity(self):
        value = candidate("vehicle:is7")
        value["crew"][4]["seat"] = 3
        self.reject(value, "duplicate crew/seat")

    def test_incomplete_or_extra_crew_is_rejected(self):
        for crew in [[], candidate()["crew"][:1], candidate()["crew"] + [candidate()["crew"][0]], {}]:
            value = candidate()
            value["crew"] = crew
            self.reject(value, "complete crew required")

    def test_wrong_primary_role_does_not_gain_access_through_combined_role(self):
        for vehicle, seat, role in [("vehicle:ms1", 0, "gunner"), ("vehicle:is7", 4, "radioman")]:
            value = candidate(vehicle)
            value["crew"][seat]["role"] = role
            self.reject(value, "primary role mismatch")

    def test_foreign_assignment_retraining_injury_and_skills_are_explicitly_unsupported(self):
        cases = [
            ("vehicle_inventory_id", "other-vehicle", "foreign crew assignment"),
            ("trained_vehicle_definition_id", "vehicle:is7", "retraining"),
            ("healthy", False, "injured"), ("healthy", 1, "injured"),
            ("skills", ["brotherhood"], "skills unsupported"),
            ("skills", {}, "skills unsupported"), ("role_level", 99, "role_level"),
        ]
        for key, replacement, reason in cases:
            with self.subTest(field=key, replacement=replacement):
                value = candidate()
                value["crew"][0][key] = replacement
                self.reject(value, reason)

    def test_exact_crew_and_top_level_schemas_reject_missing_extra_and_nonobject_rows(self):
        for location, key, remove in [("crew", "skills", True), ("crew", "perk", False),
                                      ("input", "policy", True), ("input", "consumables", False)]:
            value = candidate()
            target = value["crew"][0] if location == "crew" else value
            if remove:
                del target[key]
            else:
                target[key] = []
            self.reject(value, "exact fields")
        value = candidate()
        value["crew"][0] = []
        self.reject(value, "exact fields")

    def test_slots_must_be_three_element_list(self):
        for slots in [[], [None], [None] * 4, {}, "none"]:
            value = candidate()
            value["optional_devices"] = slots
            self.reject(value, "three optional-device slots")

    def test_duplicate_and_wrong_class_devices_rejected(self):
        self.reject(candidate(devices=[OPTICS, None, OPTICS]), "duplicate optional device", mass=synthetic_mass())
        self.reject(candidate(devices=[VENT3, None, None]), "incompatible", mass=synthetic_mass())
        self.reject(candidate("vehicle:is7", [VENT1, None, None]), "incompatible", mass=synthetic_mass())

    def test_unknown_vehicle_device_format_and_policy_are_rejected(self):
        for field, replacement, reason in [
            ("vehicle_definition_id", "vehicle:unknown", "unsupported vehicle"),
            ("optional_devices", ["optional_device:gunRammer", None, None], "unsupported optional device"),
            ("format", "crew-equipment-input.v2", "unsupported format/policy"),
            ("policy", "historical_091", "unsupported format/policy"),
        ]:
            value = candidate()
            value[field] = replacement
            self.reject(value, reason, mass=synthetic_mass())

    def test_bounded_identifiers_reject_empty_pathlike_nonascii_nonstring_and_too_long(self):
        for bad in ["", "../tankman", "crew\nother", "танкист", "x" * 129, 1, True, None]:
            with self.subTest(value=bad):
                value = candidate()
                value["crew"][0]["crew_id"] = bad
                self.reject(value, "bounded ID")

    def test_trusted_digest_rejects_replayed_or_modified_candidate(self):
        raw = encode(candidate())
        binding = trusted(raw)
        self.reject_binding(raw + b" ", binding, "digest mismatch")
        self.reject_binding(raw, replace(binding, configuration_sha256=OTHER_SHA), "digest mismatch")

    def reject_binding(self, raw, binding, pattern):
        with self.assertRaisesRegex(domain.ConfigurationError, pattern):
            domain.build_snapshot(raw, binding=binding)

    def test_candidate_cannot_override_account_vehicle_revision_or_component_authority(self):
        for field, replacement in [("account_id", "other-account"), ("vehicle_inventory_id", "other-vehicle"),
                                    ("configuration_revision", 8), ("component_configuration_sha256", OTHER_SHA)]:
            value = candidate()
            value[field] = replacement
            self.reject(value, "binding mismatch: " + field)

    def test_binding_itself_requires_exact_type_valid_ids_digests_revision_and_policy(self):
        raw = encode(candidate())
        self.reject_binding(raw, {}, "trusted server binding")
        for field, replacement, reason in [
            ("account_id", "", "bounded ID"), ("vehicle_inventory_id", "bad/id", "bounded ID"),
            ("configuration_revision", True, "integer outside bounds"),
            ("configuration_revision", 0, "integer outside bounds"),
            ("configuration_revision", 2**63, "integer outside bounds"),
            ("configuration_sha256", "A" * 64, "SHA256 required"),
            ("component_configuration_sha256", "short", "SHA256 required"),
            ("policy_sha256", OTHER_SHA, "unsupported policy digest"),
        ]:
            with self.subTest(field=field, replacement=replacement):
                self.reject_binding(raw, replace(trusted(raw), **{field: replacement}), reason)

    def test_integer_inputs_do_not_accept_boolean_float_negative_or_out_of_range(self):
        for field, bad in [("seat", True), ("seat", -1), ("seat", 2),
                           ("role_level", True), ("role_level", 101)]:
            value = candidate()
            value["crew"][0][field] = bad
            self.reject(value, field + ": integer")
        for bad in [True, 0, 2**63]:
            value = candidate()
            value["configuration_revision"] = bad
            self.reject(value, "configuration_revision: integer")
        raw = encode(candidate())
        for token in [b"100.0", b"1e2", b"NaN", b"Infinity", b"-Infinity"]:
            self.reject_raw(raw.replace(b'"role_level":100', b'"role_level":' + token, 1), "floating-point/non-finite")

    def test_installed_devices_require_mass_even_for_zero_mass_optics(self):
        for device in [OPTICS, AIM, VENT1]:
            self.reject(candidate(devices=[device, None, None]), "upstream verified mass budget")

    def test_mass_budget_binds_exact_component_and_audit_digest(self):
        raw = encode(candidate(devices=[OPTICS, None, None]))
        for mass, reason in [
            ({}, "typed mass budget"),
            (replace(synthetic_mass(), component_configuration_sha256=OTHER_SHA), "component binding mismatch"),
            (replace(synthetic_mass(), evidence_sha256="not-a-sha"), "SHA256 required"),
        ]:
            self.reject_binding(raw, trusted(raw, mass=mass), reason)

    def test_mass_budget_integral_positive_and_upper_bound_constraints(self):
        raw = encode(candidate(devices=[AIM, None, None]))
        for field in ["base_mass_grams", "max_load_grams"]:
            for bad in [0, -1, True, 1.0, 1_000_000_001]:
                mass = replace(synthetic_mass(), **{field: bad})
                self.reject_binding(raw, trusted(raw, mass=mass), field + ": integer")

    def test_exact_maximum_load_passes_and_one_gram_over_is_rejected(self):
        value = candidate("vehicle:is7", [VENT3, AIM, OPTICS])
        result = self.build(value, mass=synthetic_mass(10_000_000, 10_300_000)).as_dict()
        self.assertEqual(result["mass_check"]["total_mass_grams"], 10_300_000)
        self.reject(value, "exceeds maximum load", mass=synthetic_mass(10_000_001, 10_300_000))

    def test_no_integer_wraparound_at_upper_mass_boundary(self):
        value = candidate(devices=[AIM, None, None])
        self.reject(value, "exceeds maximum load", mass=synthetic_mass(1_000_000_000, 1_000_000_000))
        result = self.build(value, mass=synthetic_mass(999_900_000, 1_000_000_000)).as_dict()
        self.assertEqual(result["mass_check"]["total_mass_grams"], 1_000_000_000)

    def test_supplied_invalid_mass_is_not_ignored_for_empty_slots(self):
        self.reject(candidate(), "exceeds maximum load", mass=synthetic_mass(1001, 1000))

    def test_mass_cannot_be_injected_in_candidate_json(self):
        value = candidate(devices=[OPTICS, None, None])
        value["mass_budget"] = {"base_mass_grams": 1, "max_load_grams": 1_000_000_000}
        self.reject(value, "exact fields")

    def test_duplicate_json_keys_top_level_and_nested_are_rejected(self):
        raw = encode(candidate())
        self.reject_raw(raw[:-1] + b',"policy":"test_lab.crew-equipment.717.v1"}', "duplicate JSON key")
        self.reject_raw(raw.replace(b'"role_level":100', b'"role_level":100,"role_level":100', 1), "duplicate JSON key")

    def test_bad_json_utf8_root_type_and_empty_input_fail_closed(self):
        for raw in [b"", b"\xff", b"{", b"[]", b"null", b"true", b"{} trailing"]:
            with self.subTest(raw=raw):
                self.reject_raw(raw)
        raw = encode(candidate())
        self.reject_binding(bytearray(raw), trusted(raw), "bytes outside bounds")

    def test_byte_depth_and_node_budgets_reject_bounded_adversarial_inputs(self):
        self.reject_raw(b" " * (domain.MAX_BYTES + 1), "bytes outside bounds")
        value = candidate()
        value["padding"] = [[[[[[[[[0]]]]]]]]]
        self.reject(value, "depth/node bound")
        value["padding"] = [0] * 257
        self.reject(value, "depth/node bound")

    def test_canonical_determinism_and_own_hash_are_stable(self):
        value = candidate("vehicle:is7", [VENT3, AIM, OPTICS])
        raw = encode(value)
        binding = trusted(raw, mass=synthetic_mass())
        first = domain.build_snapshot(raw, binding=binding)
        for _ in range(3):
            self.assertEqual(domain.build_snapshot(raw, binding=binding).canonical_bytes, first.canonical_bytes)
        self.assertEqual(first.canonical_bytes, encode(first.as_dict()))
        self.assertEqual(first.sha256, hashlib.sha256(first.canonical_bytes).hexdigest())
        self.assertEqual(encode(dict(reversed(list(value.items())))), raw)
        self.assertEqual(first.as_dict()["configuration_sha256"], hashlib.sha256(raw).hexdigest())

    def test_snapshot_binding_and_mass_are_frozen_and_decoded_views_are_independent(self):
        raw = encode(candidate(devices=[VENT1, AIM, OPTICS]))
        mass = synthetic_mass()
        binding = trusted(raw, mass=mass)
        snapshot = domain.build_snapshot(raw, binding=binding)
        original = snapshot.canonical_bytes
        view = snapshot.as_dict()
        view["crew"][0]["roles"].append("forged-role")
        view["static_modifiers"]["gunAimingTimeFactor"]["numerator"] = 0
        view["sources"][0]["sha256"] = OTHER_SHA
        self.assertEqual(snapshot.canonical_bytes, original)
        self.assertNotEqual(snapshot.as_dict(), view)
        for instance, field, new in [(snapshot, "canonical_bytes", b"{}"),
                                     (binding, "account_id", "other"), (mass, "base_mass_grams", 1)]:
            with self.assertRaises(FrozenInstanceError):
                setattr(instance, field, new)
        with self.assertRaises(TypeError):
            snapshot.canonical_bytes[0] = 0

    def test_policy_document_is_fresh_and_its_hash_is_bound(self):
        original = domain.policy_document()
        changed = domain.policy_document()
        changed["sources"][0]["sha256"] = OTHER_SHA
        changed["devices"][0]["value"]["numerator"] = 900
        self.assertEqual(domain.policy_document(), original)
        self.assertEqual(domain.POLICY_SHA256, hashlib.sha256(encode(original)).hexdigest())

    def test_candidate_and_trusted_budget_remain_unchanged_on_success_and_rejection(self):
        value = candidate(devices=[VENT1, AIM, OPTICS])
        before = copy.deepcopy(value)
        mass = synthetic_mass()
        self.build(value, mass=mass)
        self.assertEqual(value, before)
        self.assertEqual(mass, synthetic_mass())
        value["crew"][0]["healthy"] = False
        before_failure = copy.deepcopy(value)
        self.reject(value, "injured", mass=mass)
        self.assertEqual(value, before_failure)


if __name__ == "__main__":
    unittest.main()
