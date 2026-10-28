"""CAT-NATIONS: one nation numbering (the 0.9.1 client's) in every catalogue.

The research catalogue used france=3, uk=4, china=5 until 2026-10-28; the
client's res/scripts/common/nations.pyc NAMES tuple says china=3, france=4,
uk=5. These tests pin the client order for all seven nations across the
research catalogue, the BATTLE-ANY table, the CAT-01 catalogue and its
bindings, and keep the mandatory historical special cases on catalogue rows.
"""
import json
import os
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "tools"), str(ROOT / "client_patch")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import battle_any_profiles
import catalog_v1_data
import catalog_v1_hints
import p06t_native_encoding_v3
import p06t_shell_catalog
import tankman_passports
from tools import p09e_research_catalog

CLIENT_NATIONS = ("ussr", "germany", "usa", "china", "france", "uk", "japan")
ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_ROOT", "C:/WoT_0.9.1_RU_0717_original"))
TABLE = ROOT / "config/catalog/battle_profiles.v1.json"
CATALOG = ROOT / "config/catalog/catalog.v1.json"
OLD_RESEARCH_SHA256 = "b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460"
RESEARCH_SHA256 = "1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80"


def table():
    return json.loads(TABLE.read_bytes())


class OneNationOrder(unittest.TestCase):
    def test_every_python_order_is_the_client_order(self):
        for module in (p09e_research_catalog, battle_any_profiles, p06t_native_encoding_v3,
                       p06t_shell_catalog, tankman_passports):
            self.assertEqual(tuple(module.NATIONS), CLIENT_NATIONS, module.__name__)

    def test_web_portal_lists_the_same_seven_nations(self):
        # The portal's display list is a label map, not a numbering; it must not invent a nation.
        text = (ROOT / "web/scripts/build-catalog.py").read_text(encoding="utf-8")
        listed = re.search(r"NATIONS = \[([^\]]*)\]", text).group(1)
        self.assertEqual(sorted(re.findall(r"'([a-z]+)'", listed)), sorted(CLIENT_NATIONS))

    def test_battle_any_table_nations_and_compact_nibbles(self):
        doc = table()
        self.assertEqual(doc["research_catalog_sha256"], RESEARCH_SHA256)
        seen = set()
        for row in doc["vehicles"]:
            nid = CLIENT_NATIONS.index(row["nation"])
            seen.add(row["nation"])
            self.assertEqual((row["native_nation_id"], row["research_catalog_nation_id"]), (nid, nid), row["vehicle_id"])
            self.assertFalse(row["catalog_nation_correction_required"], row["vehicle_id"])
            identity = row["identity"]
            self.assertEqual(identity["type_compact_id"] >> 4 & 15, nid, row["vehicle_id"])
            self.assertEqual(int(identity["descriptor_hex"][:2], 16), (nid << 4) | 1, row["vehicle_id"])
            self.assertTrue(all(cd >> 4 & 15 == nid for cd in identity["module_compact_ids"].values()), row["vehicle_id"])
            self.assertTrue(all(s["compact_descr"] >> 4 & 15 == nid for s in row.get("shots") or ()), row["vehicle_id"])
        self.assertEqual(seen, set(CLIENT_NATIONS))

    def test_cat01_catalog_and_bindings_use_the_client_nation(self):
        doc = json.loads(CATALOG.read_bytes())
        self.assertEqual(doc["sources"]["research_catalog_sha256"], RESEARCH_SHA256)
        nations = set()
        for row in doc["vehicles"]:
            nid = CLIENT_NATIONS.index(row["nation"])
            nations.add(row["nation"])
            self.assertEqual(row["nation_id"], nid, row["kind"])
            self.assertEqual(row["native_compact_id"] >> 4 & 15, nid, row["kind"])
            self.assertEqual(int(row["descriptor_hex"][:2], 16), (nid << 4) | 1, row["kind"])
            self.assertTrue(all(m["native_compact_id"] >> 4 & 15 == nid for m in row["modules"].values()), row["kind"])
            self.assertTrue(all(s["native_compact_id"] >> 4 & 15 == nid for s in row["shells"]), row["kind"])
        self.assertTrue({"uk", "china", "france"} <= nations)
        for binding in (catalog_v1_data, catalog_v1_hints):
            self.assertEqual({(v["kind"], v["native_compact_id"]) for v in binding.VEHICLES},
                             {(v["kind"], v["native_compact_id"]) for v in doc["vehicles"]})

    def test_fv215b_183_compact_id_is_the_client_one(self):
        # VERIFIED: research catalogue before CAT-NATIONS said 9281 (nation 4 = france).
        row = next(v for v in catalog_v1_data.VEHICLES if v["kind"] == "uk-GB48_FV215b_183")
        self.assertEqual((row["nation_id"], row["native_compact_id"], row["type_id"]), (5, 9297, 36))

    def test_old_research_hash_survives_only_as_frozen_p04m_provenance(self):
        import p04m_battle_profiles
        self.assertEqual(p04m_battle_profiles.CATALOG_SHA256, RESEARCH_SHA256)
        self.assertEqual(p04m_battle_profiles.SPEC_CATALOG_SHA256, OLD_RESEARCH_SHA256)
        # Frozen provenance is sound only while every P04M spec is a USSR row (nation 0).
        self.assertTrue(all(int(spec["type_cd"]) >> 4 & 15 == 0 and int(spec["descriptor"][:2], 16) == 1
                            for spec in p04m_battle_profiles.SPECS.values()))


class GeneratorReport(unittest.TestCase):
    """The generator report after the nation fix (stock assembly of all 374 rows)."""

    def test_generated_and_refusal_counts(self):
        counts = {}
        for row in table()["vehicles"]:
            key = row["status"] if row["refusal"] is None else row["refusal"]
            counts[key] = counts.get(key, 0) + 1
        self.assertEqual(counts, {
            "generated": 232, "SPG_INDIRECT_FIRE_OUT_OF_SCOPE": 52, "SUPPORT_SOURCE_UNRESOLVED": 35,
            "AUTOMATIC_GUN_UNSUPPORTED": 21, "SHELL_SOURCE_UNSUPPORTED": 13, "PHYSICS_ENVELOPE_EXCEEDED": 9,
            "COLLISION_SOURCE_UNSUPPORTED": 7, "AIM_ENVELOPE_UNSUPPORTED": 3, "COLLISION_SOURCE_UNRESOLVED": 1,
            "MOUNTED_SHOT_OVERRIDE_UNSUPPORTED": 1})

    def test_no_refusal_is_about_nations(self):
        for row in table()["vehicles"]:
            if row["refusal"] is not None:
                self.assertNotIn("nation", (row["refusal"] + " " + str(row.get("detail"))).lower(), row["vehicle_id"])


class HistoricalSpecialCasesInCatalog(unittest.TestCase):
    def setUp(self):
        self.rows = {v["kind"]: v for v in catalog_v1_data.VEHICLES}
        self.table = {r["vehicle_id"]: r for r in table()["vehicles"]}

    def test_fv215b_183_premium_hesh_275_on_its_183mm_gun(self):
        row = self.rows["uk-GB48_FV215b_183"]
        source = self.table[row["vehicle_id"]]
        self.assertEqual(source["gun"]["resource"], "_183mm_AT_Gun")
        self.assertTrue(row["modules"]["gun"]["module_id"].endswith(":_183mm_AT_Gun"))
        hesh = next(s for s in source["shots"] if s["resource"] == "_183mm_HESH")
        self.assertEqual((hesh["penetration_mm"], hesh["premium_gold_flag"], hesh["family"]),
                         ([275.0, 275.0], True, "HIGH_EXPLOSIVE"))
        shell = next(s for s in row["shells"] if s["resource_name"] == "_183mm_HESH")
        self.assertEqual(shell["native_compact_id"], hesh["compact_descr"])
        self.assertEqual(shell["native_compact_id"], (hesh["item_id"] << 8) + (5 << 4) + 10)

    def test_waffentrager_128_drum_six_and_not_on_150mm(self):
        row = self.rows["germany-Waffentrager_E100"]
        source = self.table[row["vehicle_id"]]
        self.assertTrue(row["modules"]["gun"]["module_id"].endswith(":_128mm_K44_2_L61"))
        self.assertEqual((source["gun"]["resource"], source["gun"]["clip_count"]), ("_128mm_K44_2_L61", 6))
        self.assertFalse(any(r.get("gun", {}).get("resource") == "_150mm_Rohr_L38" for r in self.table.values()))
        fixture = json.loads((ROOT / "tests/fixtures/p06t-shell-catalog.json").read_bytes())
        mount = next(m for m in fixture["mounts"] if m["id"] == "wt-e100-150")
        self.assertEqual((mount["gun_resource"], mount["clip_count"]), ("_150mm_Rohr_L38", 4))


@unittest.skipUnless((ORIGINAL / "WorldOfTanks.exe").is_file(), "original #717 client absent")
class AgainstTheClient(unittest.TestCase):
    def test_nations_pyc_names_tuple_is_the_client_order(self):
        from py27_static import parse_pyc
        raw = (ORIGINAL / "res/scripts/common/nations.pyc").read_bytes()
        code = parse_pyc(raw)
        self.assertIn([n.encode() for n in CLIENT_NATIONS], code["consts"])
        self.assertIn(b"NAMES", code["names"])

    def test_research_catalogue_rebuild_has_client_nibbles_for_all_nations(self):
        catalog = p09e_research_catalog.load_catalog(ORIGINAL, cache_dir=None)
        self.assertEqual(catalog.sha256, RESEARCH_SHA256)
        for row in catalog.vehicles.values():
            self.assertEqual(row["nation_id"], CLIENT_NATIONS.index(row["nation"]), row["vehicle_id"])
            self.assertEqual(row["native_compact_id"] >> 4 & 15, row["nation_id"], row["vehicle_id"])
        for key, row in catalog.modules.items():
            nation = key.split(":")[1]
            self.assertEqual(row["native_compact_id"] >> 4 & 15, CLIENT_NATIONS.index(nation), key)
        self.assertEqual({row["nation"] for row in catalog.vehicles.values()}, set(CLIENT_NATIONS))


if __name__ == "__main__":
    unittest.main()
