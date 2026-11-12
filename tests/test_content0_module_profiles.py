"""CONTENT-0 3.2: battle profiles of every mountable build from per-module tables.

The stock table stays byte-identical (`test_battle_any.RebuildFromClient`); here every build of every catalogue
vehicle is assembled from one shared set of module tables and pinned by one digest of its row and bundle hashes,
which equals the pre-refactor generator run build by build (2026-11-12, `vehicle_row(modules=...)`).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import battle_any_profiles as generator  # noqa: E402

ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_ROOT", "C:/WoT_0.9.1_RU_0717_original"))
BUILDS = 12617
COUNTS = {"AIM_ENVELOPE_UNSUPPORTED": 92, "COLLISION_SOURCE_UNRESOLVED": 3, "MOUNTED_SHOT_OVERRIDE_UNSUPPORTED": 1,
          "SUPPORT_SOURCE_UNRESOLVED": 1, "generated": 12520}
DIGEST = "3502824d77eac52c335cabe0e805691394083fde5d967870cc18316608995ea6"
_CONTEXT = None


def context():
    global _CONTEXT
    if _CONTEXT is None:
        _CONTEXT = generator.context(ORIGINAL)
    return _CONTEXT


class Configurations(unittest.TestCase):
    """Mountable builds from the research catalogue alone (no client needed)."""

    @classmethod
    def setUpClass(cls):
        from p09e_research_catalog import load_catalog
        if not (ORIGINAL / "WorldOfTanks.exe").is_file():
            raise unittest.SkipTest("original #717 client absent")
        cls.catalog = load_catalog(ORIGINAL)

    def test_stock_first_then_sorted_unique_and_within_max_load(self):
        for vehicle_id, v in self.catalog.vehicles.items():
            builds = generator.configurations(v)
            self.assertEqual(builds[0], {k: v["defaults"][k] for k in generator.MODULE_KINDS}, vehicle_id)
            keys = [tuple(b[k] for k in generator.MODULE_KINDS) for b in builds]
            self.assertEqual(len(set(keys)), len(keys), vehicle_id)
            self.assertEqual(keys[1:], sorted(keys[1:]), vehicle_id)
            for b in builds:
                self.assertEqual(b["fuelTank"], v["defaults"]["fuelTank"])
                self.assertIn(b["gun"], v["turret_guns"][b["turret"]])
                grams = v["hull_mass_grams"] + sum(v["module_mass_grams"][b[k]] for k in generator.MODULE_KINDS)
                self.assertLessEqual(grams, v["module_max_load_grams"][b["chassis"]], vehicle_id)

    def test_kv1_builds(self):
        builds = generator.configurations(self.catalog.vehicles["vehicle:ussr:KV1"])
        # 2 chassis x 3 engines x radios x (turret, gun) pairs = 84; 30 exceed the maxLoad of their chassis.
        v = self.catalog.vehicles["vehicle:ussr:KV1"]
        pairs = sum(len(v["turret_guns"][t]) for t in v["compatible"]["turret"])
        self.assertEqual(2 * 3 * len(v["compatible"]["radio"]) * pairs, 84)
        self.assertEqual(len(builds), 54)


@unittest.skipUnless((ORIGINAL / "WorldOfTanks.exe").is_file(), "original #717 client absent")
@unittest.skipIf(generator.TEST_LAB, "main catalogue digest")
class EveryBuild(unittest.TestCase):
    def test_every_build_digest_and_counts(self):
        src, catalog, defaults, factor, effects = context()
        rows, counts = [], {}
        for vehicle_id in sorted(catalog.vehicles):
            builds = generator.configurations(catalog.vehicles[vehicle_id])
            tables = generator.module_tables(src, catalog, vehicle_id, defaults, factor, effects, builds)
            for m in builds:
                row, raw = generator.assemble(catalog, tables, m)
                key = row["refusal"] or row["status"]
                counts[key] = counts.get(key, 0) + 1
                rows.append([vehicle_id, m, row["status"], row["refusal"], generator.sha(generator.canonical(row)),
                             None if raw is None else generator.sha(raw)])
        self.assertEqual(len(rows), BUILDS)
        self.assertEqual(dict(sorted(counts.items())), COUNTS)
        raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), DIGEST)

    def test_shared_tables_equal_single_build_tables(self):
        # A table built for every build of the vehicle gives the same row as one built for that build alone.
        src, catalog, defaults, factor, effects = context()
        for vehicle_id in ("vehicle:ussr:KV1", "vehicle:ussr:KV-3", "vehicle:germany:VK3001H", "vehicle:usa:T1_Cunningham"):
            builds = generator.configurations(catalog.vehicles[vehicle_id])
            tables = generator.module_tables(src, catalog, vehicle_id, defaults, factor, effects, builds)
            for m in builds[:: max(1, len(builds) // 12)]:
                self.assertEqual(generator.assemble(catalog, tables, m),
                                 generator.vehicle_row(src, catalog, vehicle_id, defaults, factor, effects, modules=m))

    def test_non_stock_build_changes_only_its_modules(self):
        src, catalog, defaults, factor, effects = context()
        v = catalog.vehicles["vehicle:ussr:KV1"]
        builds = generator.configurations(v)
        tables = generator.module_tables(src, catalog, "vehicle:ussr:KV1", defaults, factor, effects, builds)
        stock, _ = generator.assemble(catalog, tables, builds[0])
        top = dict(builds[0], engine="module:ussr:engine:V-2K")
        row, _ = generator.assemble(catalog, tables, top)
        self.assertEqual(row["movement"]["engine_power_hp"], v["module_power_hp"]["module:ussr:engine:V-2K"])
        self.assertEqual(row["gun"], stock["gun"])
        self.assertEqual(row["pivots"], stock["pivots"])
        self.assertNotEqual(row["identity"]["descriptor_hex"], stock["identity"]["descriptor_hex"])
        self.assertEqual(row["identity"]["mass_kg"] - stock["identity"]["mass_kg"],
                         (v["module_mass_grams"]["module:ussr:engine:V-2K"] - v["module_mass_grams"]["module:ussr:engine:M-17T"]) / 1000)


@unittest.skipUnless((ORIGINAL / "WorldOfTanks.exe").is_file(), "original #717 client absent")
@unittest.skipIf(generator.TEST_LAB, "main catalogue build table")
class BuildTable(unittest.TestCase):
    """CONTENT-0 3.3: the embedded build table reproduces every generated build by copying alone."""

    @classmethod
    def setUpClass(cls):
        cls.raw, cls.parts, cls.rows = generator.build_table(ORIGINAL)
        cls.table = json.loads(cls.raw)

    def test_rebuild_equals_committed_table(self):
        self.assertEqual(self.raw, generator.BUILDS.read_bytes())
        self.assertEqual(self.table["profile_table_sha256"], generator.sha(generator.TABLE.read_bytes()))
        # 12 520 generated builds less the 319 non-stock builds of the five legacy kinds (stock-only until they move
        # to the generated path) = 12 201; 12 196 runtime entries (the 5 legacy stock builds keep their closed arms).
        self.assertEqual(self.table["builds"], 12201)
        refused = [e for v in self.table["vehicles"].values() for e in v["builds"] if e["refusal"] == "LEGACY_KIND_BUILD_UNSUPPORTED"]
        self.assertEqual(len(refused), 319)

    def test_every_generated_build_is_copied_from_the_table(self):
        by_label = {e["label"]: (v, e) for v in self.table["vehicles"].values() for e in v["builds"] if "label" in e}
        self.assertEqual(len(by_label), len(self.rows))
        for label, row in self.rows:
            vehicle, entry = by_label[label]
            self.assertEqual(generator.project(row), generator.project_build(vehicle, entry), label)
            self.assertLessEqual(len(label), generator.MAX_BUILD_LABEL)

    def test_stock_builds_are_the_stock_profile_rows(self):
        stock = {r["kind"]: r for r in json.loads(generator.TABLE.read_bytes())["vehicles"] if r["status"] == "generated"}
        rows = {label: row for label, row in self.rows}
        stock_labels = [e["label"] for v in self.table["vehicles"].values() for e in v["builds"] if e["stock"] and "label" in e]
        self.assertEqual(sorted(stock_labels), sorted(stock))
        for label in stock_labels:
            self.assertEqual(generator.canonical(rows[label]), generator.canonical(stock[label]), label)

    def test_parts_are_pinned_by_their_digest(self):
        refs = set()
        for v in self.table["vehicles"].values():
            refs.add(v["hull"]["part"]["sha256"])
            refs.update(t["part"]["sha256"] for t in v["turrets"].values())
            refs.update(m["part"]["sha256"] for m in v["mounts"].values())
        self.assertEqual(refs, set(self.parts))
        for key, raw in self.parts.items():
            self.assertEqual(generator.sha(raw), key)
            self.assertLessEqual(len(raw), generator.MAX_PART)


if __name__ == "__main__":
    unittest.main()
