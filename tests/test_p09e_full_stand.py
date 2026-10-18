"""Focused source-bound P09E full-stand preparation checks.

The tests prove the purchased garage projection and its fail-closed service
guards.  They intentionally do not claim a native client, battle admission or
an optional-device contract for a newly purchased inventory id.
"""
from copy import deepcopy
from types import SimpleNamespace
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from game_profile_tx import TransactionError
from p09e_full_stand import prepare, report_digest


VEHICLE = "vehicle:test:SU-18"
MODULES = {
    "module:test:chassis": {"kind": "chassis", "mass_grams": 100,
        "max_load_grams": 1000, "native_compact_id": 2},
    "module:test:engine": {"kind": "engine", "mass_grams": 100,
        "native_compact_id": 5},
    "module:test:fuel": {"kind": "fuelTank", "mass_grams": 1,
        "native_compact_id": 6},
    "module:test:radio": {"kind": "radio", "mass_grams": 10,
        "native_compact_id": 7},
    "module:test:turret": {"kind": "turret", "mass_grams": 100,
        "native_compact_id": 3},
    "module:test:gun": {"kind": "gun", "mass_grams": 100,
        "native_compact_id": 4},
}
DEFAULTS = {
    "chassis": "module:test:chassis", "engine": "module:test:engine",
    "fuelTank": "module:test:fuel", "radio": "module:test:radio",
    "turret": "module:test:turret", "gun": "module:test:gun",
}


class FullStandPreparationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = SimpleNamespace(
            modules=MODULES,
            vehicles={VEHICLE: {
                "native_compact_id": 4609,
                "historical_price": {"amount": 0, "currency": "credits"},
                "acquisition_allowed": True,
                "unsupported_reason": None,
                "defaults": DEFAULTS,
                "compatible": {role: [item] for role, item in DEFAULTS.items()},
                "gun_turrets": {DEFAULTS["gun"]: [DEFAULTS["turret"]]},
                "hull_mass_grams": 100,
                "module_mass_grams": {},
                "module_max_load_grams": {},
                "default_unlocks": [],
                "crew_roles": ["commander", "driver"],
                "hull_max_hp": 90,
                "turret_max_hp": {DEFAULTS["turret"]: 0},
            }},
        )
        self.vehicle = {
            "vehicle_inventory_id": "account:test:p09e-vehicle:3",
            "native_id": 3,
            "vehicle_id": VEHICLE,
            "modules": deepcopy(DEFAULTS),
            "runtime_supported": False,
        }

    def test_prepares_source_loadout_but_keeps_service_boundaries_explicit(self):
        before = deepcopy(self.vehicle)
        report = prepare(self.catalog, self.vehicle)
        self.assertEqual(report["status"], "PREPARED_GARAGE_ONLY_NOT_NATIVE")
        self.assertEqual(report["vehicle"]["vehicle_inventory_id"], self.vehicle["vehicle_inventory_id"])
        self.assertEqual(report["loadout"]["mass_grams"], 511)
        self.assertEqual(report["loadout"]["max_load_grams"], 1000)
        self.assertEqual(report["crew"]["status"], "NOT_RUN")
        self.assertEqual(report["crew"]["slots"], [None, None])
        self.assertEqual(report["ammunition"]["status"], "NOT_RUN")
        self.assertEqual(report["equipment"]["status"], "NOT_RUN")
        self.assertFalse(report["battle"]["battle_admission"])
        self.assertEqual(self.vehicle, before)
        self.assertEqual(report["report_sha256"], report_digest(report))

    def test_nonempty_service_inputs_fail_closed_instead_of_fabricating_state(self):
        cases = (
            ({"crew_ids": ["account:test:crew:1"]}, "UNSUPPORTED_NEW_VEHICLE_CREW"),
            ({"ammo": [{"shell": "source-unknown", "count": 1}]}, "UNSUPPORTED_NEW_VEHICLE_AMMO"),
            ({"equipment": [123]}, "UNSUPPORTED_NEW_VEHICLE_EQUIPMENT"),
        )
        for change, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(TransactionError) as caught:
                    prepare(self.catalog, self.vehicle, **change)
                self.assertEqual(caught.exception.code, code)

    def test_battle_promotion_is_an_explicit_guard(self):
        with self.assertRaises(TransactionError) as caught:
            prepare(self.catalog, self.vehicle, request_battle=True)
        self.assertEqual(caught.exception.code, "UNVERIFIED_RUNTIME_PROFILE")

    def test_invalid_or_base_vehicle_rows_are_rejected(self):
        for change, code in (
            ({"native_id": 2}, "BASE_VEHICLE_NOT_A_PURCHASE"),
            ({"runtime_supported": True}, "RUNTIME_PROFILE_ALREADY_QUALIFIED"),
            ({"modules": {**DEFAULTS, "gun": "module:test:missing"}}, "INCOMPATIBLE_MODULE"),
        ):
            value = dict(self.vehicle)
            value.update(change)
            with self.subTest(code=code):
                with self.assertRaises(TransactionError) as caught:
                    prepare(self.catalog, value)
                self.assertEqual(caught.exception.code, code)


if __name__ == "__main__":
    unittest.main()

