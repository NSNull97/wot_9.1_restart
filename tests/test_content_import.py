from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.content_bundle import Bundle
from tools.content_import import ContentImportError, validate_import, validate_import_path


def write_bundle(root: Path) -> Path:
    payload = (json.dumps({"format": "triangle_mesh.v1", "version": 1,
                           "coordinates": {"unit": "metre", "up_axis": "Y", "order": "XYZ"},
                           "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                           "triangles": [[0, 1, 2]]}, separators=(",", ":")).encode("utf-8"))
    content_path = root / "content" / "example.blob"
    content_path.parent.mkdir(parents=True)
    content_path.write_bytes(payload)
    receipt = b"receipt\n"
    receipt_path = root / "receipts" / "source.blob"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes(receipt)
    manifest = {
        "format": "server-content.v1", "manifest_revision": 1,
        "ruleset": "test_lab", "target": {"client_build": "v.0.9.1 #717", "region": "RU"},
        "encoder": {"revision": "sha256:test"},
        "provenance": {"source_receipt": "receipts/source.blob",
                        "legacy_profile_receipt": "receipts/source.blob"},
        "content": [
            {"content_id": "inputs/example", "bundle_path": "content/example.blob",
             "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
             "source": {"relative_path": "local/source.json", "classification": "VERIFIED",
                        "license": "UNKNOWN; test"}},
            {"content_id": "receipts/source", "bundle_path": "receipts/source.blob",
             "bytes": len(receipt), "sha256": hashlib.sha256(receipt).hexdigest(),
             "source": {"relative_path": "local/source.json", "classification": "VERIFIED",
                        "license": "UNKNOWN; test"}},
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def fixture_manifest(bundle: Path) -> dict:
    source = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    return {
        "format": "content-import.v1", "manifest_revision": 1, "ruleset": "test_lab",
        "target": {"client_build": "v.0.9.1 #717", "region": "RU"},
        "source_bundle": {"format": "server-content.v1", "manifest_sha256": source},
        "provenance": {"source_receipts": ["receipts/source"],
                        "license": "UNKNOWN; local-only test"},
        "records": [
            {"record_id": "material/steel", "kind": "material", "classification": "VERIFIED",
             "source_content_ids": ["inputs/example"], "material_type": "rolled_homogeneous",
             "attributes": {"density_kg_m3": 7850}},
            {"record_id": "module/ms1/gun", "kind": "module", "classification": "VERIFIED",
             "source_content_ids": ["inputs/example"], "module_type": "gun",
             "compatible_vehicle_ids": ["vehicle/ussr:MS-1"], "attributes": {"reload_s": 2.5}},
            {"record_id": "shell/ms1/ap", "kind": "shell", "classification": "VERIFIED",
             "source_content_ids": ["inputs/example"], "shell_type": "AP", "caliber_mm": 37,
             "penetration_mm": 28, "damage": 30, "speed_mps": 800,
             "compatible_vehicle_ids": ["vehicle/ussr:MS-1"]},
            {"record_id": "vehicle/ussr:MS-1", "kind": "vehicle", "classification": "VERIFIED",
             "source_content_ids": ["inputs/example"], "type_compact_descr": 7169,
             "max_health": 90, "crew_slots": 2, "components": ["module/ms1/gun"],
             "shells": ["shell/ms1/ap"],
             "pivot": {"position": [0, 0, 0], "rotation": [0, 0, 0]}},
            {"record_id": "armor/vehicle/ussr:MS-1", "kind": "armor", "classification": "OBSERVED",
             "source_content_ids": ["inputs/example"], "vehicle_record_id": "vehicle/ussr:MS-1",
             "surfaces": [{"surface_id": "front", "material_record_id": "material/steel",
                           "thickness_mm": 16, "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                           "triangles": [[0, 1, 2]]}]},
            {"record_id": "map/test", "kind": "map", "classification": "INFERRED",
             "source_content_ids": ["inputs/example"],
             "bounds": {"min": [0, 0, 0], "max": [100, 20, 100]},
             "geometry": {"terrain": {"content_id": "inputs/example", "format": "triangle_mesh.v1"},
                          "obstacles": []},
             "spawns": [{"spawn_id": "a", "team": "allies", "position": [10, 0, 10], "rotation_y": 0},
                        {"spawn_id": "b", "team": "enemies", "position": [90, 0, 90], "rotation_y": 180}],
             "bases": [{"base_id": "base-a", "team": "allies", "position": [10, 0, 10], "radius": 20}],
             "instances": []},
        ],
        "missing": [],
    }


def write_import(root: Path, value: dict, name: str = "import.json") -> Path:
    path = root / name
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


class ContentImportTests(unittest.TestCase):
    def test_valid_import_is_typed_and_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            value = fixture_manifest(bundle)
            first = validate_import_path(write_import(root, value), bundle)
            reordered = copy.deepcopy(value)
            reordered["records"] = list(reversed(reordered["records"]))
            reordered["records"][0]["source_content_ids"] = ["inputs/example"]
            second = validate_import_path(write_import(root, reordered, "import-2.json"), bundle)
            self.assertEqual(first["status"], "PASS_TYPED_IMPORT_VALIDATOR")
            self.assertEqual(first["record_count"], 6)
            self.assertEqual(first["record_counts"]["vehicle"], 1)
            self.assertEqual(first["canonical_sha256"], second["canonical_sha256"])
            self.assertFalse(first["runtime_ready"])
            self.assertEqual(first["runtime_eligibility"], "NOT_RUN")
            self.assertTrue(first["data_complete"])

    def test_missing_data_is_explicit_and_not_runtime_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            value = fixture_manifest(bundle)
            value["missing"] = [{"record_id": "vehicle/ussr:IS-7", "field": "crew",
                                  "reason": "profile has no assigned crew", "status": "UNKNOWN"}]
            report = validate_import_path(write_import(root, value), bundle)
            self.assertEqual(report["missing_count"], 1)
            self.assertFalse(report["runtime_ready"])

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            path = root / "duplicate.json"
            path.write_text('{"format":"content-import.v1","format":"content-import.v1"}', encoding="utf-8")
            with self.assertRaises(ContentImportError):
                validate_import_path(path, bundle)

    def test_nonfinite_and_traversal_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            value = fixture_manifest(bundle)
            value["records"][0]["record_id"] = "../outside"
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value), bundle)
            value = fixture_manifest(bundle)
            value["records"][0]["attributes"]["bad"] = float("nan")
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "nonfinite.json"), bundle)

    def test_unknown_source_and_cross_kind_reference_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            value = fixture_manifest(bundle)
            value["records"][0]["source_content_ids"] = ["inputs/does-not-exist"]
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value), bundle)
            value = fixture_manifest(bundle)
            value["records"][3]["components"] = ["shell/ms1/ap"]
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "cross-kind.json"), bundle)

    def test_mesh_payload_and_target_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            value = fixture_manifest(bundle)
            (root / "bad-mesh.json").write_text(json.dumps(value), encoding="utf-8")
            payload = json.loads((bundle / "content/example.blob").read_text())
            payload["triangles"] = [[0, 0, 1]]
            (bundle / "content/example.blob").write_text(json.dumps(payload), encoding="utf-8")
            manifest = json.loads((bundle / "manifest.json").read_text())
            manifest["content"][0]["bytes"] = (bundle / "content/example.blob").stat().st_size
            manifest["content"][0]["sha256"] = hashlib.sha256((bundle / "content/example.blob").read_bytes()).hexdigest()
            (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            value["source_bundle"]["manifest_sha256"] = hashlib.sha256(
                (bundle / "manifest.json").read_bytes()).hexdigest()
            with self.assertRaises(ContentImportError):
                validate_import_path(root / "bad-mesh.json", bundle)

    def test_revision_target_ruleset_and_atgm_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            for field, bad in (("manifest_revision", True), ("ruleset", "other")):
                value = fixture_manifest(bundle)
                value[field] = bad
                with self.subTest(field=field), self.assertRaises(ContentImportError):
                    validate_import_path(write_import(root, value, field + ".json"), bundle)
            value = fixture_manifest(bundle)
            value["target"]["client_build"] = "v.0.9.2"
            altered_bundle = json.loads((bundle / "manifest.json").read_text())
            altered_bundle["target"]["client_build"] = "v.0.9.2"
            (bundle / "manifest.json").write_text(json.dumps(altered_bundle), encoding="utf-8")
            value["source_bundle"]["manifest_sha256"] = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "other-build.json"), bundle)
            altered_bundle["target"]["client_build"] = "v.0.9.1 #717"
            (bundle / "manifest.json").write_text(json.dumps(altered_bundle), encoding="utf-8")
            value = fixture_manifest(bundle)
            value["target"]["region"] = "EU"
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "target.json"), bundle)
            value = fixture_manifest(bundle)
            value["records"][2]["shell_type"] = "ATGM"
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "atgm.json"), bundle)

    def test_non_reciprocal_compatibility_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            value = fixture_manifest(bundle)
            value["records"][1]["compatible_vehicle_ids"] = []
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "reciprocal.json"), bundle)
            value = fixture_manifest(bundle)
            value["records"][3]["components"] = []
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "reciprocal-reverse.json"), bundle)

    def test_source_ids_are_cached_and_json_depth_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_root = write_bundle(root / "bundle")
            bundle = Bundle(bundle_root)
            value = fixture_manifest(bundle_root)
            with mock.patch.object(bundle, "read", wraps=bundle.read) as read:
                report = validate_import(value, bundle)
                self.assertTrue(report["data_complete"])
                # One receipt and one input blob, despite repeated references
                # from every record and geometry field.
                self.assertEqual(read.call_count, 2)
            value = fixture_manifest(bundle_root)
            cursor = value
            for _ in range(70):
                cursor["nested"] = {}
                cursor = cursor["nested"]
            with self.assertRaises(ContentImportError):
                validate_import(value, bundle)
            with self.assertRaises(ContentImportError):
                validate_import([], bundle)

    def test_bad_bounds_spawn_and_zero_area_armor_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = write_bundle(root / "bundle")
            value = fixture_manifest(bundle)
            value["records"][-1]["bounds"] = {"min": [10, 0, 0], "max": [0, 20, 100]}
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value), bundle)
            value = fixture_manifest(bundle)
            value["records"][-1]["spawns"][0]["position"] = [101, 0, 10]
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "spawn.json"), bundle)
            value = fixture_manifest(bundle)
            value["records"][4]["surfaces"][0]["triangles"] = [[0, 0, 1]]
            with self.assertRaises(ContentImportError):
                validate_import_path(write_import(root, value, "armor.json"), bundle)


if __name__ == "__main__":
    unittest.main()
