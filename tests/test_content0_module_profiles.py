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
DIGEST = "327ca4eb35258ede4e36af9d7b9f60981815366c1a3ce767f5f853aa6f720ba5"
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

    def test_kv1_suspension_adds_only_source_compatible_overweight_assemblies(self):
        from content0_equipment_catalog import compatible_suspension
        v = self.catalog.vehicles["vehicle:ussr:KV1"]
        self.assertEqual(compatible_suspension(v), 3321)
        stock_load_builds = generator.configurations(v)
        enhanced = generator.configurations(v, enhanced=True)
        extra = [modules for modules in enhanced if modules not in stock_load_builds]
        self.assertEqual(len(extra), 30)
        for modules in extra:
            grams = v["hull_mass_grams"] + sum(v["module_mass_grams"][item] for item in modules.values())
            limit = v["module_max_load_grams"][modules["chassis"]]
            self.assertGreater(grams, limit)
            self.assertLessEqual(100 * grams, 110 * limit)


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
        entries = [entry for v in self.table["vehicles"].values() for entry in v["builds"]
                   if entry["status"] == "generated"]
        self.assertEqual(len(entries), self.table["builds"])
        self.assertEqual(sum("required_suspension" not in entry for entry in entries), 12520)
        self.assertEqual(sum("required_suspension" in entry for entry in entries), 1862)

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
            refs.update(c["armor"]["sha256"] for c in v["chassis"].values() if c["armor"]["sha256"] is not None)
        self.assertEqual(refs, set(self.parts))
        for key, raw in self.parts.items():
            self.assertEqual(generator.sha(raw), key)
            self.assertLessEqual(len(raw), generator.MAX_PART)

    def test_stock_chassis_armor_part_is_the_stock_chassis_bundle_component(self):
        # SHELL-02 per chassis: the stock chassis part carries exactly the stock chassis bundle's armour mesh.
        import chassis_armor_export
        stock = {r["vehicle_id"]: r for r in json.loads(chassis_armor_export.TABLE.read_bytes())["vehicles"]}
        _, bundles = chassis_armor_export.build(ORIGINAL)
        compared = refused = 0
        for vehicle_id, v in self.table["vehicles"].items():
            chassis = next(e["modules"]["chassis"] for e in v["builds"] if e["stock"])
            ref = v["chassis"].get(chassis, {}).get("armor")
            row = stock[vehicle_id]
            if ref is None:
                continue
            if row["status"] != "generated":
                self.assertIsNone(ref["sha256"], vehicle_id)
                self.assertEqual(ref["refusal"][0], row["refusal"], vehicle_id)
                refused += 1
                continue
            part = json.loads(self.parts[ref["sha256"]])
            whole = json.loads(bundles[row["bundle"]])
            self.assertEqual(part["component"], whole["component"], vehicle_id)
            self.assertEqual(part["hull_position"], whole["hull_position"], vehicle_id)
            compared += 1
        self.assertGreater(compared, 300)


class StoreBuilds(unittest.TestCase):
    """CONTENT-0 4: what the domain reads from the build table agrees with the stock rows it already trusts."""

    def test_legacy_non_stock_builds_have_exact_descriptors_and_mounts(self):
        import content0_builds

        table, builds, mounts = content0_builds._table(), content0_builds.load(), content0_builds.mounts()
        expected = {"MS-1": 86, "T-26": 95, "T-34": 55, "T-34-85": 83, "IS-7": 0}
        for resource, count in expected.items():
            vehicle_id = "vehicle:ussr:" + resource
            entries = [entry for entry in table["vehicles"][vehicle_id]["builds"] if not entry["stock"]]
            self.assertEqual(len(entries), count, vehicle_id)
            for entry in entries:
                self.assertEqual(entry["status"], "generated", entry)
                build = builds[entry["descriptor_hex"]]
                self.assertEqual((build["vehicle_id"], build["label"], build["modules"]),
                                 (vehicle_id, entry["label"], entry["modules"]))
                mount = mounts[(vehicle_id, build["modules"]["turret"], build["modules"]["gun"])]
                self.assertEqual([generator.FAMILY_SUFFIX[shell[2]] for shell in mount["shells"]],
                                 [shell[0].rstrip("0123456789") for shell in mount["shells"]])

    def test_stock_devices_and_mounts_equal_the_stock_profile_rows(self):
        import battle_any
        import content0_builds
        table, mounts, checked = content0_builds._table(), content0_builds.mounts(), 0
        for vehicle_id, v in table["vehicles"].items():
            stock = next(e for e in v["builds"] if e["stock"])
            row = battle_any.profile(vehicle_id)
            if stock["status"] != "generated" or row is None or row.get("status") != "generated":
                continue
            m = stock["modules"]
            self.assertEqual(content0_builds.devices_of(v, m), tuple((d["extra_index"], d["max_health"]) for d in row["devices"]), vehicle_id)
            mount = mounts[(vehicle_id, m["turret"], m["gun"])]
            self.assertEqual((mount["capacity"], [s[4] for s in mount["shells"]]),
                             (row["gun"]["max_ammo"], [s["compact_descr"] for s in row["shots"]]), vehicle_id)
            checked += 1
        self.assertGreater(checked, 300)


if __name__ == "__main__":
    unittest.main()
