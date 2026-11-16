"""Checks for top, compatible #717 bot modules and the committed catalog."""

import json
import os
from pathlib import Path
import unittest

from tools.bot_top_loadouts import LAB, OUTPUT, build_rank, generate, module_levels, preferred_build
from tools.destructible_catalog import read
from tools.p09e_research_catalog import load_catalog
from tools.packed_xml import decode


ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_ROOT", "C:/WoT_0.9.1_RU_0717_original"))
# Native levels in order gun, turret, chassis, engine, radio.
GOLDEN = {
    "vehicle:ussr:KV-1s": ("ussr-KV-1s--a468dc30", (7, 6, 6, 7, 7)),
    "vehicle:usa:M18_Hellcat": ("usa-M18_Hellcat--f74499a2", (7, 6, 6, 5, 10)),
    "vehicle:germany:Grille": ("germany-Grille--dbbcef5c", (5, 5, 5, 4, 9)),
    "vehicle:ussr:SU-152": ("ussr-SU-152--ddbd721b", (8, 7, 8, 7, 9)),
    "vehicle:ussr:Object_261": ("ussr-Object_261", (9, 10, 10, 10, 10)),
}


class BotTopLoadoutsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_vehicle = json.loads(OUTPUT.read_bytes())["by_vehicle"]
        cls.builds = json.loads((LAB / "battle_builds.v1.json").read_bytes())["vehicles"]
        cls.qualified = {row["kind"] for row in
                         json.loads((LAB / "battle_qualification.v1.json").read_bytes())["profiles"]}

    def test_known_upgrades_and_stock_top(self):
        for vehicle_id, (label, _) in GOLDEN.items():
            with self.subTest(vehicle=vehicle_id):
                self.assertEqual(self.by_vehicle[vehicle_id], label)
        self.assertNotIn("vehicle:ussr:T62A_T", self.by_vehicle)

    def test_all_selections_are_qualified_for_their_own_vehicle_and_need_no_optional_device(self):
        self.assertGreater(len(self.by_vehicle), 300)
        for vehicle_id, label in self.by_vehicle.items():
            with self.subTest(vehicle=vehicle_id):
                selected, = [row for row in self.builds[vehicle_id]["builds"] if row["label"] == label]
                self.assertEqual(selected["status"], "generated")
                self.assertIsNone(selected.get("required_suspension"))
                self.assertTrue(selected["stock"] or label in self.qualified)

    def test_unfitted_suspension_and_unqualified_build_are_excluded_before_ranking(self):
        vehicle = {"vehicle_id": "vehicle:test:kind", "turret_guns": {"t": ["stock", "upgrade"]},
                   "compatible": {"turret": ["t"], "chassis": ["c"], "engine": ["e"],
                                  "radio": ["r"], "fuelTank": ["f"]}}
        stock = {"status": "generated", "stock": True, "label": "stock",
                 "modules": {"gun": "stock", "turret": "t", "chassis": "c", "engine": "e",
                             "radio": "r", "fuelTank": "f"}}
        upgrade = dict(stock, stock=False, label="upgrade", modules=dict(stock["modules"], gun="upgrade"))
        ranks = ({"t": 1, "c": 1, "e": 1, "r": 1}, {("t", "stock"): 1, ("t", "upgrade"): 2})
        self.assertEqual(preferred_build(vehicle, [stock, upgrade], {"upgrade"}, "stock", *ranks), "upgrade")
        self.assertEqual(preferred_build(vehicle, [stock, upgrade], set(), "stock", *ranks), "stock")
        upgraded_suspension = dict(upgrade, required_suspension=3321)
        self.assertEqual(preferred_build(vehicle, [stock, upgraded_suspension], {"upgrade"}, "stock", *ranks), "stock")
        tied = (ranks[0], {("t", "stock"): 1, ("t", "upgrade"): 1})
        self.assertEqual(preferred_build(vehicle, [upgrade, stock], {"upgrade"}, "stock", *tied), "upgrade")

    @unittest.skipUnless(ORIGINAL.is_dir(), "pinned #717 client is not installed")
    def test_generation_reproduces_the_table_and_highest_compatible_levels(self):
        self.assertEqual(generate(ORIGINAL), OUTPUT.read_bytes())
        catalog = load_catalog(ORIGINAL, cache_dir=None)

        def source(relative):
            pin = catalog.document["sources"][relative]
            return decode(read(ORIGINAL / relative, pin["bytes"], pin["sha256"]))

        for vehicle_id, (label, expected_levels) in GOLDEN.items():
            with self.subTest(vehicle=vehicle_id):
                build, = [row for row in self.builds[vehicle_id]["builds"] if row["label"] == label]
                vehicle = catalog.vehicles[vehicle_id]
                native_rank, _ = build_rank(vehicle, build, *module_levels(source, vehicle))
                self.assertEqual(native_rank, expected_levels)
