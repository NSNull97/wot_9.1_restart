"""Actual pinned original reads; no client import/execute and no runtime claims."""
import copy
from pathlib import Path
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STAGE / "tools"))
import p06t_shell_catalog as source
import p06t_generate_rust as rust


class OriginalShellCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads = source.load_sources(Path("C:/WoT_0.9.1_RU_0717_original"))
        cls.catalog = source.build(cls.payloads)
        cls.mounts = {row["id"]: row for row in cls.catalog["mounts"]}

    def test_actual_closed_source_sets_have_24_shells_four_literal_families(self):
        self.assertEqual(len(self.payloads), 24)
        self.assertEqual(len(self.mounts), 8)
        shots = [s for p in self.mounts.values() for s in p["shots"]]
        self.assertEqual(len(shots), 24)
        self.assertEqual(len({s["compact_descr"] for s in shots}), 24)
        self.assertEqual({s["family"] for s in shots}, set(source.FAMILIES))
        self.assertFalse(self.catalog["runtime_registration"])
        self.assertFalse(self.catalog["audit"]["client_bytecode_executed"])

    def test_all_source_pins_gate_parsing_and_missing_extra_inputs_fail(self):
        for name in self.payloads:
            wrong = dict(self.payloads)
            wrong[name] += b" "
            with self.assertRaises(source.SourceError, msg=name):
                source.build(wrong)
        for mode in ("missing", "extra"):
            wrong = dict(self.payloads)
            if mode == "missing": wrong.pop(next(iter(wrong)))
            else: wrong["invented.xml"] = b""
            with self.assertRaises(source.SourceError): source.build(wrong)

    def test_original_mounted_clip_default_and_wt_128_six_150_four(self):
        for name in ("ms1-stock", "is7-stock", "t26-stock", "t34-stock", "t3485-stock", "fv215b-183"):
            p = self.mounts[name]
            self.assertEqual((p["clip_count"], p["clip_interval_seconds"], p["clip_source"]), (1, 0., "ORIGINAL_LOADER_DEFAULT"))
        a, b = self.mounts["wt-e100-128"], self.mounts["wt-e100-150"]
        self.assertEqual((a["clip_count"], a["clip_interval_seconds"], a["reload_seconds"]), (6, 2., 60.))
        self.assertEqual((b["clip_count"], b["clip_interval_seconds"], b["reload_seconds"]), (4, 3., 50.))
        self.assertFalse(a["future_vehicle_physics_admitted"])
        self.assertFalse(b["future_vehicle_physics_admitted"])

    def test_original_mounted_reload_does_not_leak_shared_generic_values(self):
        expected = {"ms1-stock": (96, 2.5), "is7-stock": (30, 13.7), "t26-stock": (160, 2.3),
                    "t34-stock": (77, 6.), "t3485-stock": (68, 4.1), "fv215b-183": (12, 30.)}
        for name, values in expected.items():
            self.assertEqual((self.mounts[name]["max_ammo"], self.mounts[name]["reload_seconds"]), values)

    def test_original_fv_premium_is_he275_caliber182_9_and_uk_native_id5(self):
        p = self.mounts["fv215b-183"]
        self.assertEqual(p["native_nation_id"], 5)
        h, ordinary = p["shots"][1:]
        self.assertEqual((h["resource"], h["family"], h["caliber_mm"]), ("_183mm_HESH", "HIGH_EXPLOSIVE", 182.9))
        self.assertEqual((h["damage_hp"], h["device_damage"], h["penetration_mm"], h["explosion_radius_m"]), (1750, 244, [275., 275.], 5.05))
        self.assertTrue(h["premium_gold_flag"])
        self.assertEqual(h["compact_descr"], (82 << 8) + (5 << 4) + 10)
        self.assertEqual(ordinary["penetration_mm"], [92., 92.])
        self.assertFalse(ordinary["premium_gold_flag"])

    def test_shell_family_parameters_are_not_copied_from_ap(self):
        t = self.mounts["t3485-stock"]["shots"]
        self.assertEqual((t[0]["damage_hp"], t[1]["damage_hp"], t[2]["damage_hp"]), (115, 110, 165))
        self.assertEqual(self.mounts["t26-stock"]["shots"][1]["raw_speed_mps"], 838.)
        self.assertEqual(self.mounts["t34-stock"]["shots"][1]["raw_speed_mps"], 490.)
        self.assertEqual(self.mounts["ms1-stock"]["shots"][1]["piercing_power_loss_factor_by_distance"], .05)
        for p in self.mounts.values():
            for s in p["shots"]:
                self.assertEqual(s["speed_mps"], s["raw_speed_mps"] * .8)
                self.assertEqual(s["gravity_mps2"], 9.81 * .8 ** 2)

    def test_numbers_are_finite_bounded_and_false_is_not_zero_source_id(self):
        for value in (True, False, None, float("nan"), float("inf"), "NaN", -1, 1001):
            with self.assertRaises(source.SourceError): source.integer(value, "test", 1000, zero=True)
        self.assertEqual(source.integer(0, "T34 gun index", 255, zero=True), 0)
        self.assertEqual(self.mounts["t34-stock"]["gun_compact_descr"], 4)

    def test_rust_candidate_is_bounded_data_only_and_deterministic(self):
        a = rust.generate(self.catalog)
        self.assertEqual(a, rust.generate(copy.deepcopy(self.catalog)))
        self.assertLess(len(a), 65536)
        self.assertIn(b"pub const PROFILES:[GunProfile;8]", a)
        self.assertNotIn(b"unsafe", a)
        self.assertNotIn(b"pub fn admit", a)


if __name__ == "__main__":
    unittest.main()
