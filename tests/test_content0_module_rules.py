"""CONTENT-0 3.1: pure mounting rules (no SQLite, no client launch).

The synthetic cases need nothing; the catalogue case reads the original #717
client as bounded data (NOT_RUN without it). Never native UI evidence.
"""
from copy import deepcopy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from game_profile_tx import TransactionError
from p09e_native_commands import EQUIP, NativeRequest, domain_request
from p09e_research_store import assembly, plan

ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_CLIENT", r"C:\WoT_0.9.1_RU_0717_original"))


def module(kind, cd, mass, max_load=None):
    row = {"kind": kind, "native_compact_id": cd, "mass_grams": mass, "historical_price": {"amount": 1, "currency": "credits"}}
    if max_load is not None: row["max_load_grams"] = max_load
    return row


def synthetic(max_load):
    """One vehicle: hull 10 t, stock parts 4 t, chassis maxLoad as given."""
    modules = {"c": module("chassis", 0x102, 1000000, max_load), "e": module("engine", 0x105, 500000),
               "e2": module("engine", 0x205, 1500000), "f": module("fuelTank", 0x106, 100000),
               "r": module("radio", 0x107, 100000), "t": module("turret", 0x103, 1800000),
               "t2": module("turret", 0x203, 1700000), "g": module("gun", 0x104, 500000), "g2": module("gun", 0x204, 400000)}
    defaults = {"chassis": "c", "engine": "e", "fuelTank": "f", "radio": "r", "turret": "t", "gun": "g"}
    vehicle = {"native_compact_id": 0x101, "hull_mass_grams": 10000000, "defaults": defaults,
               "compatible": {"chassis": ["c"], "engine": ["e", "e2"], "fuelTank": ["f"], "radio": ["r"],
                              "turret": ["t", "t2"], "gun": ["g", "g2"]},
               "gun_turrets": {"g": ["t", "t2"], "g2": ["t2"]}}
    return SimpleNamespace(vehicles={"v": vehicle}, modules=modules, unlocks=[])


def state(catalog, depot):
    return {"unlocked": sorted(catalog.modules), "depot": dict(depot), "garage_slots": 5, "next_native_id": 4,
            "vehicles": [{"vehicle_inventory_id": "acct:p09e-vehicle:3", "native_id": 3, "vehicle_id": "v",
                          "modules": dict(catalog.vehicles["v"]["defaults"]), "runtime_supported": False}]}


class MountRuleTests(unittest.TestCase):
    def install(self, catalog, depot, *items, reserved=(), loaded=()):
        return plan(catalog, state(catalog, depot), "install",
                    {"vehicle_inventory_id": "acct:p09e-vehicle:3", "modules": list(items)},
                    account_id="acct", reserved=reserved, loaded=loaded)

    def code(self, action):
        with self.assertRaises(TransactionError) as caught: action()
        return caught.exception.code

    def test_mass_equal_to_max_load_mounts_and_one_gram_more_is_too_heavy(self):
        # Stock 14 t; the heavier engine makes it exactly 15 t.
        exact = synthetic(15000000)
        after, details = self.install(exact, {"e2": 1}, "e2")
        self.assertEqual((details["mass_grams"], details["max_load_grams"]), (15000000, 15000000))
        self.assertEqual(after["depot"], {"e": 1})
        self.assertEqual(self.code(lambda: self.install(synthetic(14999999), {"e2": 1}, "e2")), "CHASSIS_OVERLOAD")
        # 0.9.1 _isWeightAllowedToChange also admits a change that does not worsen an
        # overloaded reserve; the store never stores an overloaded assembly, so the
        # strict check is the same rule here (stock fits: see the catalogue test).
        self.assertEqual(self.code(lambda: assembly(synthetic(13999999), "v", synthetic(1).vehicles["v"]["defaults"])),
                         "CHASSIS_OVERLOAD")

    def test_turret_gun_pairs_follow_the_source_turret_gun_table(self):
        catalog = synthetic(20000000)
        self.assertEqual(self.code(lambda: self.install(catalog, {"g2": 1}, "g2")), "INCOMPATIBLE_TURRET_GUN")
        after, details = self.install(catalog, {"t2": 1, "g2": 1}, "t2", "g2")
        self.assertEqual(details["modules"], {"turret": "t2", "gun": "g2"})
        self.assertEqual(after["depot"], {"t": 1, "g": 1})
        self.assertEqual(after["vehicles"][0]["modules"]["gun"], "g2")
        # equipTurret(turret, 0): the mounted gun stays when the new turret carries it.
        after, details = self.install(catalog, {"t2": 1}, "t2")
        self.assertEqual((details["modules"], after["depot"]), ({"turret": "t2"}, {"t": 1}))

    def test_every_refusal_leaves_the_input_state_untouched(self):
        catalog = synthetic(20000000)
        cases = [("MODULE_NOT_OWNED", ({}, "e2"), {}), ("NO_CONFIGURATION_CHANGE", ({"e": 1}, "e"), {}),
                 ("UNKNOWN_MODULE", ({}, "nope"), {}), ("INTERNAL_COMPONENT_UNSUPPORTED", ({"f": 1}, "f"), {}),
                 ("DUPLICATE_MODULE_SLOT", ({"e2": 1}, "e2", "e"), {}),
                 ("VEHICLE_RESERVED", ({"e2": 1}, "e2"), {"reserved": ["acct:p09e-vehicle:3"]}),
                 ("UNLOAD_AMMUNITION_REQUIRED", ({"t2": 1}, "t2"), {"loaded": ["acct:p09e-vehicle:3"]})]
        for expected, (depot, *items), extra in cases:
            before = state(catalog, depot); frozen = deepcopy(before)
            with self.assertRaises(TransactionError) as caught:
                plan(catalog, before, "install", {"vehicle_inventory_id": "acct:p09e-vehicle:3", "modules": items},
                     account_id="acct", **extra)
            self.assertEqual(caught.exception.code, expected)
            self.assertEqual(before, frozen)
        # Loaded shells do not block a non-gun change (0.9.1 keeps the shells).
        after, _ = self.install(catalog, {"e2": 1}, "e2", loaded=["acct:p09e-vehicle:3"])
        self.assertEqual(after["vehicles"][0]["modules"]["engine"], "e2")

    def test_native_101_shapes_map_once_to_owned_inventory_and_module_ids(self):
        catalog = synthetic(20000000)
        aggregate = {"research": state(catalog, {})}
        def request(arguments):
            return domain_request(NativeRequest(7, EQUIP, arguments), catalog=catalog, aggregate=aggregate,
                account_id="acct", command_key="k", expected_revision=20, shop_revision=5)
        self.assertEqual(request((3, 0x205, 0))["payload"], {"vehicle_inventory_id": "acct:p09e-vehicle:3", "modules": ["e2"]})
        self.assertEqual(request((3, 0x203, 0x204))["payload"]["modules"], ["t2", "g2"])
        for arguments, expected in (((4, 0x205, 0), "UNOWNED_VEHICLE"), ((3, 0x305, 0), "UNKNOWN_MODULE"),
                                    ((3, 0x205, 0x204), "UNEXPECTED_GUN_SELECTION"), ((3, 0x203, 0x205), "INVALID_GUN_SELECTION"),
                                    ((3, 0x203, 0x304), "UNKNOWN_MODULE"), ((0, 0x205, 0), "INVALID_NATIVE_REQUEST"),
                                    ((3, 0x205, -1), "INVALID_NATIVE_REQUEST")):
            self.assertEqual(self.code(lambda: request(arguments)), expected, arguments)


@unittest.skipUnless(ORIGINAL.is_dir(), "NOT_RUN: original #717 client required")
class CatalogueMassTests(unittest.TestCase):
    def test_every_stock_assembly_fits_its_stock_chassis(self):
        from p09e_research_catalog import load_catalog
        catalog = load_catalog(str(ORIGINAL))
        self.assertEqual(len(catalog.vehicles), 374)
        for key, vehicle in catalog.vehicles.items():
            metrics = assembly(catalog, key, dict(vehicle["defaults"]))
            self.assertLessEqual(metrics["mass_grams"], metrics["max_load_grams"], key)

    def test_every_turret_gun_swap_delta_fits_the_account_update_bound(self):
        """compDescr + repair + shells + four depot counts, at the largest IDs and counts."""
        from p09e_research_catalog import load_catalog
        from p09e_research_projection import MAX_UPDATE, update_delta
        catalog = load_catalog(str(ORIGINAL))
        worst = 0
        for key, vehicle in catalog.vehicles.items():
            stock = vehicle["defaults"]
            for gun, turrets in vehicle["gun_turrets"].items():
                for turret in turrets:
                    mounted = dict(stock, turret=turret, gun=gun)
                    if mounted == stock: continue
                    old, new = {stock["turret"], stock["gun"]}, {turret, gun}
                    before = {"unlocked": [], "depot": {item: 999999 for item in new},
                              "vehicles": [{"native_id": 2**31 - 2, "vehicle_id": key, "modules": stock}]}
                    after = {"unlocked": [], "depot": {**{item: 999999 for item in old - new}, **{item: 999998 for item in new - old}},
                             "vehicles": [{"native_id": 2**31 - 2, "vehicle_id": key, "modules": mounted}]}
                    worst = max(worst, len(update_delta(catalog, before, after, 2**31 - 2)))
        self.assertLessEqual(worst, MAX_UPDATE)


if __name__ == "__main__":
    unittest.main()
