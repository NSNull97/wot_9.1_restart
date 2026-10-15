"""Real pinned #717 source import gates; not native/worker/battle acceptance."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import p04m_battle_profiles as profiles


class RealStockImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A missing real source is a failure of this explicit importer gate;
        # never turn a fabricated source or an implicit skip into acceptance.
        config = json.loads((ROOT / "config/project.local.json").read_text(encoding="utf-8-sig"))
        cls.original = Path(config["paths"]["original_client_root"])
        cls.payloads, cls.packages, cls.catalog = profiles.load_sources(cls.original)
        cls.result = profiles.build_profiles(cls.payloads, cls.packages, cls.catalog)

    def test_three_exact_stock_assemblies_keep_admission_closed(self):
        expected = {
            "t26-stock": (4609, 150, 160, 3, "011224001300c90001001e00100000"),
            "t34-stock": (1, 400, 77, 4, "010000000000cb0003000000000000"),
            "t3485-stock": (2561, 670, 68, 5, "010a14000100cb0003001100060000"),
        }
        self.assertEqual(set(self.result), set(expected))
        for key, (cd, hp, capacity, crew, descriptor) in expected.items():
            with self.subTest(key=key):
                row = self.result[key]
                self.assertEqual(row["schema"], "p04m-battle-source.v1")
                self.assertIs(row["battle_admission"], False)
                self.assertIsNone(row["runtime_physics"])
                self.assertEqual(row["identity"]["type_compact_id"], cd)
                self.assertEqual(row["identity"]["max_hp"], hp)
                self.assertEqual(row["identity"]["descriptor_hex"], descriptor)
                self.assertEqual(len(row["identity"]["crew_roles"]), crew)
                self.assertEqual(row["gun"]["capacity"], capacity)
                self.assertIn("physics_support_selection_and_radius", row["unknowns"])
        # #717 vehicle index0 is real T-34, not a missing/empty descriptor.
        self.assertEqual(self.result["t34-stock"]["identity"]["module_compact_ids"]["chassis"], 2)
        self.assertEqual(self.result["t26-stock"]["identity"]["crew_roles"],
                         [["commander", "radioman"], ["driver"], ["gunner", "loader"]])

    def test_mounted_gun_overrides_and_mount_specific_ap_are_preserved(self):
        expected = {
            "t26-stock": (2.3, 2.3, 160, 1034, 36, [40, 33], 536., 37),
            "t34-stock": (6, 2.9, 77, 7178, 110, [68, 62], 489.6, 76),
            "t3485-stock": (4.1, 2.9, 68, 7946, 115, [125, 115], 652.8, 76),
        }
        for key, values in expected.items():
            with self.subTest(key=key):
                gun = self.result[key]["gun"]
                reload, aim, capacity, shell, damage, penetration, speed, caliber = values
                self.assertEqual([gun[k] for k in ("reload_seconds", "aiming_seconds", "capacity", "shell_compact_id", "damage_hp", "penetration_mm")],
                                 [reload, aim, capacity, shell, damage, penetration])
                self.assertAlmostEqual(gun["speed_mps"], speed)
                self.assertEqual(gun["caliber_mm"], caliber)
                self.assertEqual(gun["gravity_mps2"], 9.81)
                self.assertEqual(gun["max_distance_m"], 720)
                self.assertEqual(gun["allowed_shell_kinds"], ["ARMOR_PIERCING"])
                self.assertIn("/shots[1]/" + gun["shell_resource"] + "[1]", gun["shot_source_path"])
        # Shared S-54 has52 rounds /4.5714s; actual mounted T-34-85 is68 /4.1s.
        self.assertNotEqual(self.result["t3485-stock"]["gun"]["capacity"], 52)
        self.assertGreater(self.result["t26-stock"]["gun"]["capacity"], 96)

    def test_real_mesh_groups_coverage_and_bounds_do_not_inherit_is7_exclusions(self):
        expected = {
            "t26-stock": [(211, 142), (228, 190), (217, 128)],
            "t34-stock": [(266, 172), (382, 264), (195, 181)],
            "t3485-stock": [(301, 198), (575, 429), (199, 160)],
        }
        for key, counts in expected.items():
            with self.subTest(key=key):
                components = self.result[key]["geometry"]["components"]
                self.assertEqual([(len(c["vertices"]), len(c["triangles"])) for c in components], counts)
                for i, component in enumerate(components):
                    self.assertEqual(component["excluded_degenerate_triangle_ids"], [])
                    self.assertEqual([t["triangle_id"] for t in component["triangles"]],
                                     list(range(i * 100000, i * 100000 + counts[i][1])))
                    names = {m["name"] for m in component["materials"]}
                    self.assertTrue(all(t["material"] in names for t in component["triangles"]))
                    self.assertTrue(all(not profiles.geometry.exact_zero_area(component["vertices"], t)
                                        for t in component["triangles"]))
                # Source visual bbox is kept separate even when it differs.
                turret = components[1]
                self.assertNotEqual(turret["visual_bounds"],
                                    [turret["mesh_bounds"]["min"], turret["mesh_bounds"]["max"]])
                self.assertEqual(self.result[key]["geometry"]["hull_aabb_candidate"]["classification"],
                                 "DERIVED_COLLISION_HULL_AABB_NOT_ADMITTED_PHYSICS")

    def test_actual_zero_armor_absent_device_and_gun_damage_factor_are_distinct(self):
        for key, row in self.result.items():
            with self.subTest(key=key):
                hull, turret, gun = row["geometry"]["components"]
                for component in (hull, turret):
                    by_name = {m["name"]: m for m in component["materials"]}
                    self.assertIsNone(by_name["surveyingDevice"]["effective"])
                    self.assertTrue(any(m["effective"] is not None and m["effective"]["armor"] == 0
                                        for m in component["materials"]))
                device = next(m["effective"] for m in gun["materials"] if m["name"] == "gun")
                self.assertEqual(device["damageKind"], 1)
                self.assertFalse(device["extra_is_none"])
                self.assertTrue(device["collideOnceOnly"])
                for material in gun["materials"]:
                    if material["name"].startswith("armor_"):
                        self.assertEqual(material["effective"]["vehicleDamageFactor"], 0.)
                self.assertTrue(all(m["effective"] is None or m["effective"]["vehicleDamageFactor"] == 1.
                                    for m in hull["materials"]))

    def test_movement_is_actual_source_without_fabricated_supports(self):
        for key, mass, power in (("t26-stock", 9302, 90), ("t34-stock", 27940, 480), ("t3485-stock", 32370, 500)):
            row = self.result[key]
            self.assertEqual(row["movement_source"]["mass_kg"], mass)
            self.assertEqual(row["movement_source"]["engine_power_hp"], power)
            self.assertNotIn("wheel_points", row["movement_source"])
            self.assertNotIn("engine_max_torque_nm", row["movement_source"])
        wheels = self.result["t26-stock"]["movement_source"]["wheel_source"]
        radii = {profiles.vector(v, 1, "radius")[0] if isinstance(v, list) else profiles.number(v, "radius")
                 for k, v in wheels.items() if k.endswith("/radius[1]")}
        self.assertEqual(len(radii), 4)

    def test_every_byte_source_is_pinned_before_any_xml_loader_or_primitive_parser(self):
        for name in self.payloads:
            with self.subTest(source=name):
                poisoned = dict(self.payloads)
                raw = bytearray(poisoned[name])
                raw[-1] ^= 1
                poisoned[name] = bytes(raw)
                with patch.object(profiles, "decode") as decoder, patch.object(profiles.materials, "_loader_defaults") as loader:
                    with self.assertRaisesRegex(ValueError, "source pin differs"):
                        profiles.build_profiles(poisoned, self.packages, self.catalog)
                    decoder.assert_not_called()
                    loader.assert_not_called()

    def test_missing_extra_and_changed_package_sources_fail_closed(self):
        for change in ("missing", "extra", "package"):
            poisoned, packages = dict(self.payloads), copy.deepcopy(self.packages)
            if change == "missing":
                del poisoned[profiles.materials.KINDS_KEY]
            elif change == "extra":
                poisoned["unexpected"] = b"x"
            else:
                packages[profiles.PACKAGE]["sha256"] = "0" * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                profiles.build_profiles(poisoned, packages, self.catalog)

    def test_modified_catalogue_owner_neutral_facts_are_not_accepted(self):
        catalog = copy.deepcopy(self.catalog)
        catalog.document["vehicles"]["vehicle:ussr:T-26"]["defaults"]["gun"] = "module:ussr:gun:_45mm_20K"
        with self.assertRaisesRegex(ValueError, "catalogue differs"):
            profiles.build_profiles(self.payloads, self.packages, catalog)
        with self.assertRaisesRegex(ValueError, "unknown curated"):
            profiles._build_profile("kv1-stock", self.payloads, self.catalog, {})

    def test_a_degenerate_real_primitive_is_rejected_instead_of_excluding_is7_ids(self):
        payloads = dict(self.payloads)
        prefix = "vehicles/russian/R09_T-26/collision/"
        name = profiles.PACKAGE + "!" + prefix + "Hull.primitives"
        raw = bytearray(payloads[name])
        mesh = profiles.collision_mesh(bytes(raw))
        start = mesh["sections"]["indices"]["offset"]
        width = 2 if raw[start:start + 64].split(b"\0", 1)[0] == b"list" else 4
        offset = start + 72
        raw[offset + width:offset + width * 2] = raw[offset:offset + width]
        payloads[name] = bytes(raw)
        # Internal parser negative test only; public importer rejects this byte
        # mutation even earlier at the source pin gate tested above.
        with self.assertRaisesRegex(ValueError, "zero-area triangle"):
            profiles._component("Hull", 0, prefix, payloads, {})

    def test_export_is_repeatable_and_source_spec_return_cannot_mutate_pins(self):
        rebuilt = profiles.build_profiles(self.payloads, self.packages, self.catalog)
        expected = {"t26-stock": "7b6c41b5d8678a6f935701547781090c517649f741c05621a0cbaf063670e55e",
                    "t34-stock": "6c64732e7421f139991df3cdb0d0d161a3d563a3312fcef040a089d26508c306",
                    "t3485-stock": "25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb"}
        for key, row in rebuilt.items():
            self.assertEqual(profiles.canonical(row), profiles.canonical(self.result[key]))
            self.assertEqual(hashlib.sha256(profiles.canonical(row) + b"\n").hexdigest(), expected[key])
        spec = profiles.source_spec()
        spec["assemblies"]["t26-stock"]["capacity"] = 1
        spec["members"].clear()
        self.assertEqual(profiles.SPECS["t26-stock"]["capacity"], 160)
        self.assertEqual(len(profiles.MEMBER_PINS), 28)

    def test_output_guard_rejects_existing_or_outside_directory_before_source_io(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local", prefix="p04m-test-") as existing:
            sentinel = Path(existing) / "untouched.txt"
            sentinel.write_bytes(b"existing proof")
            with patch.object(profiles, "load_sources") as source:
                with self.assertRaisesRegex(ValueError, "fresh output"):
                    profiles.export(self.original, existing)
                with self.assertRaisesRegex(ValueError, "outside owned"):
                    profiles.export(self.original, ROOT / "docs" / "must-not-write")
                source.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b"existing proof")


if __name__ == "__main__":
    unittest.main()
