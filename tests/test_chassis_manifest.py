"""SHELL-02 helpers: chassis refs in a derived profile13 manifest; collision device census.

Manifest inputs are synthetic; bundle bytes come from the SHELL-01 evidence export
when it exists (otherwise those cases skip, reported as such, never as a pass).
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import chassis_manifest as manifest  # noqa: E402

BUNDLES = Path("D:/WoT_9.1_Server/local/evidence/shell-01-chassis-20261104-02/bundles")
ORIGINAL = Path("C:/WoT_0.9.1_RU_0717_original")


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def row(kind):
    ref = {"path": "C:/x/" + kind + ".json", "sha256": "a" * 64}
    return {"kind": kind, "pool": ref, "geometry": ref}


class ChassisManifestTests(unittest.TestCase):
    def test_curated_and_generated_labels_name_table_bundles(self):
        table = manifest.pins()
        for name in manifest.CURATED.values():
            self.assertIn(name + ".json", table)
        self.assertIn("usa-M4_Sherman.json", table)

    def test_old_shape_is_required_and_input_is_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = write(tmp / "m.json", {"version": 5, "profiles": [dict(row("ms1"), chassis={})]})
            before = source.read_bytes()
            with self.assertRaises(manifest.ManifestError):
                manifest.derive(source, tmp)
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaises(manifest.ManifestError):
                manifest.derive(Path("relative.json"), tmp)

    def test_unknown_kind_is_kept_without_chassis(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = write(tmp / "m.json", {"version": 5, "profiles": [row("not-a-vehicle")]})
            derived, bound, kept = manifest.derive(source, tmp)
            self.assertEqual((bound, kept), ([], ["not-a-vehicle"]))
            self.assertNotIn("chassis", derived["profiles"][0])

    @unittest.skipUnless((BUNDLES / "ussr-MS-1.json").is_file(), "SHELL-01 chassis bundles absent")
    def test_pinned_bundle_is_bound_and_altered_bytes_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = write(tmp / "m.json", {"version": 5, "profiles": [row("ms1"), row("is7")]})
            derived, bound, kept = manifest.derive(source, BUNDLES)
            self.assertEqual([b["vehicle_id"] for b in bound], ["vehicle:ussr:MS-1", "vehicle:ussr:IS-7"])
            raw = (BUNDLES / "ussr-MS-1.json").read_bytes()
            self.assertEqual(derived["profiles"][0]["chassis"]["sha256"], hashlib.sha256(raw).hexdigest())
            (tmp / "b").mkdir()
            (tmp / "b" / "ussr-MS-1.json").write_bytes(raw + b" ")
            with self.assertRaises(manifest.ManifestError):
                manifest.derive(write(tmp / "m2.json", {"version": 5, "profiles": [row("ms1")]}), tmp / "b")


class CollisionDeviceCensusTests(unittest.TestCase):
    @unittest.skipUnless(ORIGINAL.is_dir(), "original #717 client absent")
    def test_no_battle_registry_vehicle_carries_internal_device_groups(self):
        import collision_device_census as census
        result = census.census(ORIGINAL)
        self.assertEqual(result["collision_visuals"], 2522)
        self.assertEqual(result["battle_registry_vehicles_with_device_groups"], [])
        self.assertEqual(sorted(v["battle_profiles"][0]["vehicle_id"] for v in result["visuals_with_device_groups"]),
                         ["vehicle:france:Bat_Chatillon155_55", "vehicle:germany:E50_Ausf_M", "vehicle:germany:E50_Ausf_M",
                          "vehicle:usa:M41", "vehicle:ussr:A44"])


if __name__ == "__main__":
    unittest.main()
