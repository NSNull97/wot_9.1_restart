"""Executable P09E boundary: purchased garage entries are not battle-ready.

These tests deliberately prove the current contract and prevent a future merge
from silently granting crew/ammo/admission while the successor card is absent.
They do not claim native UI or battle compatibility.
"""
from types import SimpleNamespace
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from tools import p09e_research_projection as projection
from tools import p09e_research_store as store
from game_profile_tx import TransactionError

VEHICLE = "vehicle:test:MS-1"
MODULES = {
    "module:test:chassis": {"kind": "chassis", "mass_grams": 100, "max_load_grams": 1000, "native_compact_id": 2},
    "module:test:engine": {"kind": "engine", "mass_grams": 100, "native_compact_id": 5},
    "module:test:fuel": {"kind": "fuelTank", "mass_grams": 1, "native_compact_id": 6},
    "module:test:radio": {"kind": "radio", "mass_grams": 10, "native_compact_id": 7},
    "module:test:turret": {"kind": "turret", "mass_grams": 100, "native_compact_id": 3},
    "module:test:gun": {"kind": "gun", "mass_grams": 100, "native_compact_id": 4},
}
DEFAULTS = {
    "chassis": "module:test:chassis", "engine": "module:test:engine",
    "fuelTank": "module:test:fuel", "radio": "module:test:radio",
    "turret": "module:test:turret", "gun": "module:test:gun",
}


class FullStandBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.catalog = SimpleNamespace(
            modules=MODULES,
            vehicles={VEHICLE: {
                "native_compact_id": 257,
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
        self.state = {
            "unlocked": [VEHICLE], "depot": {},
            "vehicles": [],
            "next_native_id": 1, "garage_slots": 3,
        }

    def test_purchase_is_explicitly_garage_only(self):
        state, details = store.plan(self.catalog, self.state, "buy_vehicle",
                                    {"vehicle_id": VEHICLE}, account_id="account:test")
        purchased = state["vehicles"][-1]
        self.assertFalse(purchased["runtime_supported"])
        self.assertEqual(details["vehicle_inventory_id"], purchased["vehicle_inventory_id"])
        self.assertEqual(len(state["vehicles"]), 1)

    def test_new_garage_record_has_no_crew_or_loaded_shells(self):
        row = {"vehicle_id": VEHICLE, "modules": dict(DEFAULTS)}
        record = projection.garage_record(self.catalog, row)
        self.assertEqual(record["crew"], [None, None])
        self.assertEqual(record["shells"], [])
        self.assertEqual(record["shellsLayout"], {})
        self.assertEqual(record["eqs"], [0, 0, 0])
        self.assertEqual(record["eqsLayout"], [0, 0, 0])

    def test_research_writer_still_exposes_only_three_source_slots(self):
        self.assertEqual(self.state["garage_slots"], 3)
        self.assertEqual(projection.free_vehicle_purchases(self.state), 3)
        self.assertEqual(store.MAX_OWNED, 256)

    def test_full_stand_operations_are_rejected_until_successor_card(self):
        for operation, payload in (
            ("sell_vehicle", {"vehicle_inventory_id": "base:1"}),
            ("expand_garage", {"count": 100}),
            ("assign_crew", {"vehicle_inventory_id": "base:1", "crew": []}),
            ("service_ammo", {"vehicle_inventory_id": "base:1"}),
        ):
            with self.assertRaises(TransactionError) as caught:
                store.validate_request({"account_id": "account:test", "command_key": "k",
                    "expected_revision": 1, "operation": operation, "payload": payload},
                    "account:test")
            self.assertEqual(caught.exception.code, "UNSUPPORTED_OPERATION")

    def test_policy_keeps_battle_admission_closed_for_research_inventory(self):
        self.assertIs(store.POLICY["battle_admission"], False)
        self.assertIn("battle_admission", store.POLICY)


if __name__ == "__main__":
    unittest.main()
