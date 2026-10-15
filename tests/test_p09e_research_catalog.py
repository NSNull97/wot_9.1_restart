"""Source catalogue regression checks; original resources are read only.

Source tests skip explicitly on machines without the owner-authorized original.
No test writes/copies client resources or launches the client.
"""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from tools import p09e_research_catalog as catalog


class ScalarBoundaryTests(unittest.TestCase):
    def test_numeric_input_rejects_bools_nan_negative_and_fractional_ids(self):
        for value in (True, False, None, "nan", "inf", "-1", "1.5", {}, "1e100"):
            with self.subTest(value=value), self.assertRaises(catalog.ResearchCatalogError):
                catalog.number(value, "test")
        self.assertEqual(40, catalog.number("40.0", "source decimal integer"))
        self.assertEqual(1, catalog.number("01", "native decimal ID"))

    def test_packed_xml_kind5_text_spelling_and_zero(self):
        self.assertEqual("SU-18", catalog.scalar({"value": {"base64": "SU-18"}, "children": []}))
        self.assertEqual(0, catalog.scalar({"value": 0, "children": []}))

    def test_duplicate_scalar_field_and_unsafe_ids_rejected(self):
        node = {"value": "", "children": [{"name": "id", "data": 1}, {"name": "id", "data": 2}]}
        with self.assertRaises(catalog.ResearchCatalogError): catalog.child(node, "id")
        for value in ("../evil", "", "a/b", "a\\b", "a:evil", "x" * 97):
            with self.subTest(value=value), self.assertRaises(catalog.ResearchCatalogError):
                catalog.identifier("vehicle", "ussr", value)


class OriginalSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(os.environ.get("WOT_P09E_ORIGINAL", r"C:\WoT_0.9.1_RU_0717_original"))
        if not cls.original.is_dir():
            raise unittest.SkipTest("NOT_RUN: pinned original #717 source root unavailable")
        cls.catalog = catalog.load_catalog(cls.original)

    def test_complete_pinned_source_coverage_and_native_ids(self):
        c = self.catalog
        self.assertEqual((374, 2120, 2062, 426),
                         (len(c.vehicles), len(c.modules), len(c.unlocks), len(c.document["sources"])))
        self.assertEqual(402, sum(pin["historical_catalog_baseline_match"] for pin in c.document["sources"].values()))
        native_ids = [row["native_compact_id"] for row in [*c.vehicles.values(), *c.modules.values()]]
        self.assertEqual(len(native_ids), len(set(native_ids)))

    def test_ms1_native_unlock_indices_differ_from_web_display_order(self):
        rows = [row for row in self.catalog.unlocks if row["vehicle_id"] == "vehicle:ussr:MS-1"]
        self.assertEqual(list(range(14)), [row["native_index"] for row in rows])
        self.assertEqual("module:ussr:gun:_37mm_B-3", rows[7]["item_id"])
        self.assertEqual("module:ussr:turret:T-18_mod", rows[8]["item_id"])
        self.assertEqual("vehicle:ussr:AT-1", rows[11]["item_id"])
        self.assertEqual("vehicle:ussr:T-26", rows[12]["item_id"])
        self.assertEqual(135, rows[12]["historical_xp"])
        self.assertEqual("module:ussr:gun:_45mm_mod_1932", rows[13]["item_id"])
        self.assertEqual({"module:ussr:gun:_37mm_Gochkins", "module:ussr:gun:_37mm_B-3",
                          "module:ussr:turret:T-18_Standart", "module:ussr:turret:T-18_mod"},
                         set(rows[13]["prerequisite_ids"]))

    def test_exact_stock_ms1_is7_descriptors_and_masses(self):
        for key, expected_mass, expected_hex in (
                ("vehicle:ussr:MS-1", 4691000, "010d1a000e00c90000001700170000"),
                ("vehicle:ussr:IS-7", 68190000, "011c3a002400cd000b002f003a0000")):
            vehicle = self.catalog.vehicles[key]
            defaults = vehicle["defaults"]
            mass = vehicle["hull_mass_grams"] + sum(vehicle["module_mass_grams"][mid] for mid in defaults.values())
            self.assertEqual(expected_mass, mass)
            ids = [self.catalog.modules[defaults[role]]["native_compact_id"] >> 8
                   for role in ("chassis", "engine", "fuelTank", "radio", "turret", "gun")]
            cd = vehicle["native_compact_id"]
            self.assertEqual(expected_hex, struct.pack("<2B6HB", cd & 255, cd >> 8, *ids, 0).hex())
            self.assertEqual("UNSUPPORTED_UNTIL_EXACT_RUNTIME_PROFILE", vehicle["battle_eligibility"])

    def test_all_stock_assemblies_compatible_complete_and_within_load(self):
        for key, vehicle in self.catalog.vehicles.items():
            with self.subTest(vehicle=key):
                self.assertEqual(set(catalog.KINDS), set(vehicle["defaults"]))
                for role, module_id in vehicle["defaults"].items():
                    self.assertIn(module_id, vehicle["compatible"][role])
                    self.assertIn(module_id, vehicle["default_unlocks"])
                self.assertIn(vehicle["defaults"]["turret"], vehicle["gun_turrets"][vehicle["defaults"]["gun"]])
                mass = vehicle["hull_mass_grams"] + sum(vehicle["module_mass_grams"][mid] for mid in vehicle["defaults"].values())
                self.assertLessEqual(mass, vehicle["module_max_load_grams"][vehicle["defaults"]["chassis"]])

    def test_t34_incompatible_gun_turret_and_shared_engine_identity(self):
        t34 = self.catalog.vehicles["vehicle:ussr:T-34"]
        su85 = self.catalog.vehicles["vehicle:ussr:SU-85"]
        self.assertEqual(t34["defaults"]["engine"], su85["defaults"]["engine"])
        self.assertNotIn(t34["defaults"]["turret"], t34["gun_turrets"]["module:ussr:gun:_76mm_S-54"])
        self.assertIn("module:ussr:turret:T-34_mod_1942", t34["gun_turrets"]["module:ussr:gun:_76mm_S-54"])

    def test_native_health_and_crew_seat_order_preserved(self):
        ms1 = self.catalog.vehicles["vehicle:ussr:MS-1"]
        is7 = self.catalog.vehicles["vehicle:ussr:IS-7"]
        self.assertEqual(90, ms1["hull_max_hp"] + ms1["turret_max_hp"][ms1["defaults"]["turret"]])
        self.assertEqual(2150, is7["hull_max_hp"] + is7["turret_max_hp"][is7["defaults"]["turret"]])
        self.assertEqual([["commander", "gunner", "radioman", "loader"], ["driver"]], ms1["crew_roles"])
        self.assertEqual(["commander", "gunner", "driver", "loader", "loader"], [row[0] for row in is7["crew_roles"]])

    def test_fake_turret_zero_index_is_a_real_default_unlock(self):
        fv304 = self.catalog.vehicles["vehicle:uk:GB77_FV304"]
        self.assertIn("module:uk:turret:Turret_2_GB77_FV304", fv304["default_unlocks"])
        crusader = next(row for row in self.catalog.unlocks if row["item_id"] == "vehicle:uk:GB29_Crusader_5inch")
        self.assertIn("module:uk:turret:Turret_2_GB77_FV304", crusader["prerequisite_ids"])

    def test_all_290_ordinary_credit_vehicles_reachable_without_unlock_all(self):
        c = self.catalog
        unlocked = set(c.initial_unlocked)
        self.assertEqual(7, len([key for key in unlocked if key.startswith("vehicle:")]))
        self.assertNotIn("vehicle:ussr:IS-7", unlocked)
        for _ in range(128):
            before = len(unlocked)
            for row in c.unlocks:
                if row["vehicle_id"] in unlocked and set(row["prerequisite_ids"]) <= unlocked:
                    unlocked.add(row["item_id"])
                    if row["item_id"] in c.vehicles:
                        unlocked.update(c.vehicles[row["item_id"]]["default_unlocks"])
            if len(unlocked) == before: break
        else: self.fail("graph did not converge")
        allowed = {key for key, row in c.vehicles.items() if row["acquisition_allowed"]}
        self.assertEqual(290, len(allowed))
        self.assertEqual(set(), allowed - unlocked)

    def test_hidden_gold_special_are_not_free_credit_purchases(self):
        self.assertFalse(self.catalog.vehicles["vehicle:ussr:Observer"]["acquisition_allowed"])
        gold = [row for row in self.catalog.vehicles.values() if row["historical_price"]["currency"] == "gold"]
        self.assertTrue(gold)
        self.assertTrue(all(not row["acquisition_allowed"] for row in gold))
        self.assertEqual({"amount": 6100000, "currency": "credits"},
                         self.catalog.vehicles["vehicle:ussr:IS-7"]["historical_price"])
        edge = next(row for row in self.catalog.unlocks if row["item_id"] == "vehicle:ussr:IS-7")
        self.assertEqual(189200, edge["historical_xp"])

    def test_wt_e100_source_magazines_keep_128_and_150_separate(self):
        row = self.catalog.vehicles["vehicle:germany:Waffentrager_E100"]
        counts = {key.split("/")[-1]: int(value["clip"]["count"]) for key, value in row["gun_parameters"].items()}
        self.assertEqual(6, counts["module:germany:gun:_128mm_K44_2_L61"])
        self.assertEqual(4, counts["module:germany:gun:_150mm_Rohr_L38"])

    def test_pinned_source_mismatch_and_oversized_pin_rejected(self):
        for update in ({"sha256": "0" * 64}, {"bytes": catalog.MAX_SOURCE_BYTES + 1}):
            pins = json.loads(catalog.PIN_PATH.read_text())
            pins["sources"]["res/scripts/common/items/vehicles.pyc"].update(update)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "pins.json"
                path.write_text(json.dumps(pins))
                with self.assertRaises(catalog.ResearchCatalogError):
                    catalog.load_catalog(self.original, path)


if __name__ == "__main__": unittest.main()
