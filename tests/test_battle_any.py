"""BATTLE-ANY stage 1: generated battle profile table for any #717 catalogue vehicle.

Regression: the generic generator must reproduce every hand-closed profile that
already exists (P04M SPECS/bundles, physics definitions, P06T shells, Rust
VehicleKind constants) and keep the mandatory historical special cases.
"""
import json
import os
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "tools")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import battle_any
import battle_any_data
import battle_any_profiles as generator
from p04m_battle_profiles import SPECS

TABLE = ROOT / "config/catalog/battle_profiles.v1.json"
ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_ROOT", "C:/WoT_0.9.1_RU_0717_original"))
P04M_IMPORT = Path(os.environ.get("P04M_SOURCE_IMPORT", ROOT / "local/evidence/20261016-p04m-source-import01"))
RUST_KINDS = {"Ms1": "ms1", "Is7": "is7", "T26": "t26", "T34": "t34", "T3485": "t3485",
              "Wt128": "wt-e100-128", "Fv183": "fv215b-183"}
_BUILT = None


def rows():
    return {row["vehicle_id"]: row for row in json.loads(TABLE.read_bytes())["vehicles"]}


def existing():
    return {row["existing_kind"]: row for row in rows().values() if row["existing_kind"]}


def rust_match(name):
    """`Self::Kind => literal` arms of one single-line `pub fn name` in vehicle_profile.rs."""
    source = (ROOT / "server/gateway/src/shared/vehicle_profile.rs").read_text(encoding="utf-8")
    line = next(l for l in source.splitlines() if re.search(r"pub fn %s\(self\)" % name, l))
    return {RUST_KINDS[k]: float(v) for k, v in re.findall(r"Self::(\w+)\s*=>\s*(-?[0-9.]+)", line)}


def rust_block(name):
    source = (ROOT / "server/gateway/src/shared/vehicle_profile.rs").read_text(encoding="utf-8")
    start = source.index("pub fn %s(self)" % name)
    end = source.find("pub fn ", start + 10)
    return source[start:end if end > 0 else source.index("#[cfg(test)]", start)]


def built():
    global _BUILT
    if _BUILT is None:
        _BUILT = generator.build(ORIGINAL)
    return _BUILT


class TableContract(unittest.TestCase):
    def test_check_binding_and_accessor(self):
        result = generator.check()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["table_sha256"], battle_any_data.TABLE_SHA256)
        self.assertEqual(len(battle_any.table()), result["vehicles"])
        self.assertEqual(result["vehicles"], 374)

    def test_no_row_grants_admission_stage1(self):
        for vehicle_id, row in rows().items():
            self.assertIs(row["battle_admission"], False, vehicle_id)
            self.assertEqual(row["readiness_code"], "BATTLE_PROFILE_UNSUPPORTED", vehicle_id)
            self.assertEqual(battle_any.readiness(vehicle_id), (False, "BATTLE_PROFILE_UNSUPPORTED", row["refusal"]))
        self.assertEqual(battle_any.readiness("vehicle:ussr:NOPE"), (False, "BATTLE_PROFILE_UNSUPPORTED", "UNKNOWN_VEHICLE_PROFILE"))

    def test_tampered_table_refuses(self):
        raw = TABLE.read_bytes()
        bad = ROOT / "local" / "battle-any-tamper-test.json"
        if not bad.parent.is_dir():
            self.skipTest("no project local directory")
        bad.write_bytes(raw.replace(b'"battle_admission":false', b'"battle_admission":true ', 1))
        try:
            with self.assertRaises(ValueError):
                generator.check(bad)
        finally:
            bad.unlink()

    def test_spg_refused_explicitly(self):
        spg = [row for row in rows().values() if row["vehicle_class"] == "SPG"]
        self.assertEqual(len(spg), 52)
        for row in spg:
            self.assertEqual((row["status"], row["refusal"]), ("refused", "SPG_INDIRECT_FIRE_OUT_OF_SCOPE"))
        self.assertEqual(rows()["vehicle:ussr:Object_261"]["refusal"], "SPG_INDIRECT_FIRE_OUT_OF_SCOPE")

    def test_automatic_guns_refused_not_truncated(self):
        for row in rows().values():
            if row["vehicle_class"] != "SPG" and (row["gun"]["burst"] or row["gun"]["clip_count"] > generator.MAX_CLIP):
                self.assertEqual(row["refusal"], "AUTOMATIC_GUN_UNSUPPORTED", row["vehicle_id"])
            if row["status"] == "generated":
                self.assertTrue(1 <= row["gun"]["clip_count"] <= generator.MAX_CLIP and not row["gun"]["burst"])

    def test_generated_rows_inside_physics_envelope(self):
        for row in rows().values():
            if row["status"] != "generated":
                continue
            for field, (low, high) in generator.ENVELOPE.items():
                value = row["handling"][field] if field in row["handling"] else row["physics"][field]
                self.assertTrue(low <= value <= high, (row["vehicle_id"], field))

    def test_nation_ids_are_original_and_equal_to_research_catalogue(self):
        # CAT-NATIONS: the research catalogue now uses the client order too.
        fv = rows()["vehicle:uk:GB48_FV215b_183"]
        self.assertEqual((fv["native_nation_id"], fv["research_catalog_nation_id"]), (5, 5))
        self.assertFalse(any(row["catalog_nation_correction_required"] for row in rows().values()))


class SpecialCases(unittest.TestCase):
    def test_waffentrager_128_keeps_six_shell_drum(self):
        wt = rows()["vehicle:germany:Waffentrager_E100"]
        self.assertEqual(wt["status"], "generated")
        gun = wt["gun"]
        self.assertEqual(gun["resource"], "_128mm_K44_2_L61")
        self.assertIn("/guns[1]/_128mm_K44_2_L61[1]", gun["mount_source_path"])
        self.assertEqual((gun["clip_count"], gun["clip_rate_per_minute"], gun["clip_interval_seconds"]), (6, 30.0, 2.0))
        self.assertEqual((gun["max_ammo"], gun["reload_seconds"]), (60, 60.0))

    def test_drum_does_not_leak_to_150mm(self):
        # The 150 mm is not the stock gun: no row profiles it, and its own
        # source clip (P06T fixture, original XML) is 4, not 6.
        fixture = json.loads((ROOT / "tests/fixtures/p06t-shell-catalog.json").read_bytes())
        mount = next(m for m in fixture["mounts"] if m["id"] == "wt-e100-150")
        self.assertEqual((mount["gun_resource"], mount["clip_count"]), ("_150mm_Rohr_L38", 4))
        self.assertFalse(any(row.get("gun", {}).get("resource") == "_150mm_Rohr_L38" for row in rows().values()))

    def test_fv215b_183_premium_hesh_275_bound_to_its_gun(self):
        fv = rows()["vehicle:uk:GB48_FV215b_183"]
        self.assertEqual(fv["status"], "generated")
        self.assertEqual(fv["gun"]["resource"], "_183mm_AT_Gun")
        hesh = [s for s in fv["shots"] if s["resource"] == "_183mm_HESH"]
        self.assertEqual(len(hesh), 1)
        self.assertEqual((hesh[0]["penetration_mm"], hesh[0]["premium_gold_flag"], hesh[0]["family"]),
                         ([275.0, 275.0], True, "HIGH_EXPLOSIVE"))
        self.assertEqual(hesh[0]["compact_descr"], 21082)
        others = [s for r in rows().values() if r["vehicle_id"] != fv["vehicle_id"] for s in r.get("shots", ())
                  if s["resource"] == "_183mm_HESH"]
        self.assertEqual(others, [])


class ExistingProfilesReproduced(unittest.TestCase):
    def test_physics_definitions_equal(self):
        by = existing()
        for name in ("stock-definitions.json", "extended-definitions.json"):
            for p in json.loads((ROOT / "server/physics/Profiles" / name).read_bytes())["profiles"]:
                row = by[p["kind"]]
                self.assertEqual(row["physics"], p["physics"], p["kind"])
                self.assertEqual(row["handling"], p["handling"], p["kind"])
                self.assertEqual(row["hull_aabb"], p["source"]["hull_aabb"], p["kind"])
                if name == "extended-definitions.json":
                    self.assertEqual(generator.MAPPING, p["mapping"])

    def test_p04m_specs_equal(self):
        by = existing()
        for key, s in SPECS.items():
            r = by[key.split("-")[0]]
            g, shot, m, i = r["gun"], r["shots"][0], r["movement"], r["identity"]
            got = dict(type_cd=i["type_compact_id"], descriptor=i["descriptor_hex"], capacity=g["max_ammo"],
                reload=g["reload_seconds"], aiming=g["aiming_seconds"], dispersion=g["shot_dispersion_radius"],
                pitch=tuple(g["pitch_limits"]), shell=shot["resource"], shell_cd=shot["compact_descr"],
                caliber=shot["caliber_mm"], damage=shot["damage_hp"], device_damage=shot["device_damage"],
                penetration=tuple(shot["penetration_mm"]), speed=shot["raw_speed_mps"], max_hp=i["max_hp"],
                mass_kg=i["mass_kg"], power_hp=m["engine_power_hp"], forward=m["speed_limits_kmh"][0],
                reverse=m["speed_limits_kmh"][1], chassis_yaw=m["chassis_rotation_deg_s"],
                turret_yaw=g["turret_rotation_deg_s"], gun_yaw=g["gun_rotation_deg_s"],
                module_cds=tuple(i["module_compact_ids"][k] for k in generator.MODULE_KINDS),
                crew=tuple(tuple(x) for x in i["crew_roles"]))
            self.assertEqual(got, {k: s[k] for k in got}, key)

    def test_p06t_shell_mounts_equal(self):
        table = {(r["nation"], r["resource"]): r for r in rows().values()}
        fixture = json.loads((ROOT / "tests/fixtures/p06t-shell-catalog.json").read_bytes())
        checked = 0
        for m in fixture["mounts"]:
            r = table[(m["nation"], m["vehicle_resource"])]
            if r["gun"]["resource"] != m["gun_resource"]:
                continue
            strip = lambda s: {k: v for k, v in s.items() if k not in ("shell_source_path", "shot_source_path", "effects_index")}
            self.assertEqual([strip(s) for s in m["shots"]], [strip(s) for s in r["shots"]], m["id"])
            self.assertEqual((m["max_ammo"], m["reload_seconds"], m["clip_count"], m["clip_interval_seconds"]),
                (r["gun"]["max_ammo"], r["gun"]["reload_seconds"], r["gun"]["clip_count"], r["gun"]["clip_interval_seconds"]))
            self.assertEqual(m["vehicle_type_compact_descr"], r["identity"]["type_compact_id"], m["id"])
            self.assertEqual(m["gun_compact_descr"], r["identity"]["module_compact_ids"]["gun"], m["id"])
            checked += 1
        self.assertEqual(checked, 7)

    def test_rust_vehicle_kind_constants_equal(self):
        by = existing()
        for fn, get in (("vehicle_compact_id", lambda r: r["identity"]["type_compact_id"]),
                        ("gun_compact_id", lambda r: r["identity"]["module_compact_ids"]["gun"]),
                        ("shell_compact_id", lambda r: r["shots"][0]["compact_descr"]),
                        ("max_health", lambda r: r["identity"]["max_hp"]),
                        ("mass_kg", lambda r: r["identity"]["mass_kg"]),
                        ("view_range", lambda r: r["view_range_m"]),
                        ("ammo_limit", lambda r: r["gun"]["max_ammo"]),
                        ("reload_seconds", lambda r: r["gun"]["reload_seconds"])):
            arms = rust_match(fn)
            self.assertEqual(set(arms), set(by), fn)
            for kind, value in arms.items():
                self.assertEqual(get(by[kind]), value, (fn, kind))
        shells = {RUST_KINDS[k]: [float(x) for x in v.split(",")]
                  for k, v in re.findall(r"Self::(\w+)\s*=>\s*\(([^)]*)\)", rust_block("shell"))}
        self.assertEqual(set(shells), set(by))
        for kind, (caliber, damage, p100, p500, speed, _effects) in shells.items():
            s = by[kind]["shots"][0]
            self.assertEqual((s["caliber_mm"], s["damage_hp"], s["penetration_mm"], s["raw_speed_mps"]),
                             (caliber, damage, [p100, p500], speed), kind)
        descriptors = {RUST_KINDS[k]: bytes(int(x, 16) for x in v.split(","))
                       for k, v in re.findall(r"Self::(\w+)\s*=>\s*&\[([^\]]*)\]", rust_block("descriptor"))}
        self.assertEqual(set(descriptors), set(by) - {"ms1"})
        for kind, raw in descriptors.items():
            self.assertEqual(by[kind]["identity"]["descriptor_hex"], raw.hex(), kind)

    def test_device_caps_and_crew_equal_p06t(self):
        by = existing()
        src = (ROOT / "server/gateway/src/shared/p06t_device_caps.rs").read_text(encoding="utf-8")
        order = ["ms1", "is7", "t26", "t34", "t3485", "wt-e100-128", "fv215b-183"]
        caps = re.search(r"pub const CAPS:\[\[Cap;9\];7\]=\[(.*?)\n\];", src, re.S).group(1).strip().splitlines()
        crew = re.search(r"pub const CREW:\[&\[Seat\];7\]=\[(.*?)\n\];", src, re.S).group(1).strip().splitlines()
        fire = [float(x) for x in re.search(r"ENGINE_FIRE_CHANCE:\[f64;7\]=\[([^\]]*)\]", src).group(1).split(",")]
        for i, kind in enumerate(order):
            r = by[kind]
            self.assertEqual([(int(a), int(b)) for a, b in re.findall(r"max:(\d+),regen:(\d+)", caps[i])],
                             [(d["max_health"], d["max_regen_health"]) for d in r["devices"]], kind)
            self.assertEqual([(int(a), int(b)) for a, b in re.findall(r"extra:(\d+),roles:(\d+)", crew[i])],
                             [(x["extra_index"], x["role_bits"]) for x in r["crew_seats"]], kind)
            self.assertEqual(fire[i], r["engine_fire_starting_chance"], kind)

    def test_aim_and_effects_equal_rust(self):
        by = existing()
        block = rust_block("aim")
        arms = re.split(r"Self::(\w+)\s*=>\s*AimSpec", block)[1:]
        aims = {RUST_KINDS[arms[i]]: arms[i + 1] for i in range(0, len(arms), 2)}
        self.assertEqual(set(aims), set(by))
        for kind, text in aims.items():
            g = by[kind]["gun"]
            field = lambda name: float(re.search(name + r":\s*(-?[0-9.]+)", text).group(1))
            self.assertEqual(field("yaw_rate"), g["turret_rotation_deg_s"], kind)
            self.assertEqual(field("pitch_rate"), g["gun_rotation_deg_s"], kind)
            self.assertEqual((field("min_pitch"), field("max_pitch_degrees")), tuple(g["pitch_envelope"]["basic"]), kind)
            self.assertEqual(field("turret_dispersion"), g["dispersion_turret_rotation"], kind)
            self.assertEqual(field("hull_dispersion"), g["dispersion_vehicle_rotation"], kind)
            self.assertEqual(field("aiming_time"), g["aiming_seconds"], kind)
        effects = {RUST_KINDS[k]: int(v.split(",")[-1]) for k, v in re.findall(r"Self::(\w+)\s*=>\s*\(([^)]*)\)", rust_block("shell"))}
        for kind, index in effects.items():
            self.assertEqual(by[kind]["shots"][0]["effects_index"], index, kind)

    def test_catalog_v1_rows_match_table(self):
        # Legacy five keep their closed kind; stage 3 pilot rows carry the generated label.
        catalog = json.loads((ROOT / "config/catalog/catalog.v1.json").read_bytes())
        by = {row["vehicle_id"]: row for row in rows().values()}
        for vehicle in catalog["vehicles"]:
            row = by[vehicle["vehicle_id"]]
            if vehicle["kind"] not in ("ms1", "is7", "t26", "t34", "t3485"):
                # WT keeps existing_kind wt-e100-128 (closed P06T kind); its catalog row
                # uses the generated label, equal to the closed kind by the gateway test.
                self.assertEqual((row["status"], row["kind"]), ("generated", vehicle["kind"]))
                self.assertFalse(row["catalog_nation_correction_required"], vehicle["kind"])
            else:
                self.assertEqual(row["existing_kind"], vehicle["kind"])
            self.assertEqual(row["identity"]["descriptor_hex"], vehicle["descriptor_hex"])
            self.assertEqual(row["gun"]["max_ammo"], vehicle["ammo_capacity"])


@unittest.skipUnless((ORIGINAL / "WorldOfTanks.exe").is_file(), "original #717 client absent")
class RebuildFromClient(unittest.TestCase):
    def test_rebuild_equals_committed_table(self):
        raw, bundles = built()
        self.assertEqual(raw, TABLE.read_bytes())
        table = json.loads(raw)
        for row in table["vehicles"]:
            if row["status"] == "generated":
                data = bundles[row["geometry"]["bundle"]]
                self.assertEqual(generator.pin(data), dict(bytes=row["geometry"]["bytes"], sha256=row["geometry"]["sha256"]))
        self.assertEqual(len(bundles), sum(r["status"] == "generated" for r in table["vehicles"]))

    def test_is7_degenerate_exclusions_equal_rust_geometry(self):
        _raw, bundles = built()
        source = (ROOT / "server/gateway/src/shared/geometry.rs").read_text(encoding="utf-8")
        rust = [int(x) for x in re.search(r"IS7_EXCLUDED_IDS: \[u32; 2\] = \[([^\]]*)\]", source).group(1).split(",")]
        hull = json.loads(bundles[existing()["is7"]["geometry"]["bundle"]])["geometry"]["components"][0]
        self.assertEqual(hull["excluded_degenerate_triangle_ids"], rust)

    @unittest.skipUnless(P04M_IMPORT.is_dir(), "P04M source import evidence absent")
    def test_bundles_equal_p04m_source_import(self):
        _raw, bundles = built()
        by = existing()
        for key in SPECS:
            prior = json.loads((P04M_IMPORT / (key + ".json")).read_bytes())["geometry"]
            mine = json.loads(bundles[by[key.split("-")[0]]["geometry"]["bundle"]])["geometry"]
            for field in ("hull_position", "turret_position", "gun_position"):
                self.assertEqual(prior[field], mine[field], (key, field))
            for a, b in zip(prior["components"], mine["components"], strict=True):
                b = dict(b)
                self.assertIn(b.pop("vertex_format"), ("xyznuv", "xyznuvtb"))
                self.assertEqual(a, b, (key, a["name"]))


if __name__ == "__main__":
    unittest.main()
