"""CONTENT-0 step 0: the committed inventory is internally consistent and, with the client present, reproducible."""
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "research" / "content0_inventory.v1.json"
CLIENT = Path(os.environ.get("WOT091_ORIGINAL_CLIENT", "C:/WoT_0.9.1_RU_0717_original"))
STATUSES = {"works", "partial", "closed", "absent", "unknown"}


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(INVENTORY.read_text(encoding="utf-8"))

    def test_schema_and_counts_agree_with_rows(self):
        d, s = self.doc, self.doc["summary"]
        self.assertEqual(d["schema"], "wot091-content0-inventory.v1")
        self.assertEqual(s["vehicles"], len(d["vehicles"]))
        self.assertEqual(s["vehicles"], 374, "#717 lists 374 vehicles")
        self.assertEqual(sum(s["vehicles_by_class"].values()), s["vehicles"])
        self.assertEqual(s["shells"], len(d["shells"]))
        self.assertEqual(s["equipment"], len(d["equipment"]))
        self.assertEqual(s["consumables"], len(d["consumables"]))
        self.assertEqual(s["maps"], len(d["maps"]))
        self.assertEqual(s["achievements"], len(d["achievements"]))
        self.assertEqual(s["crew_skills"], len(d["crew"]["skills"]))
        for variant in ("main", "test_lab"):
            self.assertEqual(s[variant]["in_catalog"], sum(v[variant]["in_catalog"] for v in d["vehicles"]))

    def test_every_refused_vehicle_names_a_reason(self):
        for v in self.doc["vehicles"]:
            for variant in ("main", "test_lab"):
                row = v[variant]
                self.assertEqual(row["profile"] == "refused", row["refusal"] is not None, (v["vehicle_id"], variant))

    def test_server_maps_are_client_maps(self):
        served = [m for m in self.doc["maps"] if m["server_battle"]]
        self.assertEqual(sorted(m["asset"] for m in served), ["01_karelia", "02_malinovka", "05_prohorovka"])
        self.assertTrue(all(m["package"] for m in served))

    def test_operation_table_is_well_formed(self):
        names = [o["operation"] for o in self.doc["operations"]]
        self.assertEqual(len(names), len(set(names)))
        for o in self.doc["operations"]:
            self.assertIn(o["status"], STATUSES)
            self.assertTrue(o["evidence"])
            self.assertTrue(o["content0_step"] is None or 1 <= o["content0_step"] <= 14)

    def test_client_shoot_through_constants_are_kept(self):
        st = self.doc["summary"]["shoot_through"]
        self.assertEqual(st["max_hp"], "19")
        self.assertEqual(set(st["piercing_power_reduction"]), {"ground", "stone", "wood", "metal", "snow", "sand", "water"})

    @unittest.skipUnless((CLIENT / "res" / "scripts" / "destructibles.xml").is_file(), "NOT_RUN: original #717 client absent")
    def test_inventory_reproduces_from_the_client(self):
        from tools import content0_inventory as inv
        self.assertEqual(inv.canonical(inv.build(CLIENT)), INVENTORY.read_bytes().replace(b"
", b"
"))


if __name__ == "__main__":
    unittest.main()
