from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.content_bundle import Bundle, BundleError, verify_bundle


def write_bundle(root: Path, content_id: str = "inputs/example") -> None:
    payload = b"portable-content\n"
    target = root / "content" / "example.blob"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    receipt = b"receipt\n"
    receipt_path = root / "receipts" / "source.blob"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_bytes(receipt)
    manifest = {
        "format": "server-content.v1", "manifest_revision": 1,
        "ruleset": "test_lab",
        "encoder": {"revision": "sha256:test"},
        "provenance": {"source_receipt": "receipts/source.blob",
                        "legacy_profile_receipt": "receipts/source.blob"},
        "content": [{"content_id": content_id, "bundle_path": "content/example.blob",
                      "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
                      "source": {"relative_path": "local/source.json", "classification": "VERIFIED",
                                 "license": "UNKNOWN; test"}},
                     {"content_id": "receipts/source", "bundle_path": "receipts/source.blob",
                      "bytes": len(receipt), "sha256": hashlib.sha256(receipt).hexdigest(),
                      "source": {"relative_path": "local/source.json", "classification": "VERIFIED",
                                 "license": "UNKNOWN; test"}}],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class ContentBundleTests(unittest.TestCase):
    def test_valid_bundle_is_read_only_by_content_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_bundle(root)
            # Synthetic manifest references a receipt ID but does not need to
            # include it in content for this focused reader test.
            bundle = Bundle(root)
            self.assertEqual(bundle.read("inputs/example"), b"portable-content\n")
            self.assertEqual(verify_bundle(root)["status"], "PASS_CONTENT_BUNDLE")

    def test_absolute_content_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_bundle(root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["content"][0]["bundle_path"] = "D:/outside.blob"
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(BundleError):
                verify_bundle(root)

    def test_manifest_duplicate_and_nonfinite_json_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            duplicate_root = root / "duplicate"
            write_bundle(duplicate_root)
            (duplicate_root / "manifest.json").write_text(
                '{"format":"server-content.v1","format":"server-content.v1"}',
                encoding="utf-8")
            with self.assertRaises(BundleError):
                verify_bundle(duplicate_root)

            nonfinite_root = root / "nonfinite"
            write_bundle(nonfinite_root)
            raw = (nonfinite_root / "manifest.json").read_text(encoding="utf-8")
            (nonfinite_root / "manifest.json").write_text(raw[:-1] + ',"nonfinite":NaN}', encoding="utf-8")
            with self.assertRaises(BundleError):
                verify_bundle(nonfinite_root)

    def test_manifest_rejects_boolean_integer_fields_and_bad_digest_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revision_root = root / "revision"
            write_bundle(revision_root)
            manifest = json.loads((revision_root / "manifest.json").read_text(encoding="utf-8"))
            manifest["manifest_revision"] = True
            (revision_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(BundleError):
                verify_bundle(revision_root)

            bytes_root = root / "bytes"
            write_bundle(bytes_root)
            manifest = json.loads((bytes_root / "manifest.json").read_text(encoding="utf-8"))
            manifest["content"][0]["bytes"] = True
            (bytes_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(BundleError):
                verify_bundle(bytes_root)

            digest_root = root / "digest"
            write_bundle(digest_root)
            manifest = json.loads((digest_root / "manifest.json").read_text(encoding="utf-8"))
            manifest["content"][0]["sha256"] = "A" * 64
            (digest_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(BundleError):
                verify_bundle(digest_root)

    def test_read_json_uses_the_same_strict_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_bundle(root)
            payload = b'{"value":1,"value":2}'
            content = root / "content" / "example.blob"
            content.write_bytes(payload)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            manifest["content"][0]["bytes"] = len(payload)
            manifest["content"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            bundle = Bundle(root)
            with self.assertRaises(BundleError):
                bundle.read_json("inputs/example")

            nonfinite_root = Path(directory) / "nonfinite-content"
            write_bundle(nonfinite_root)
            payload = b'{"value":NaN}'
            content = nonfinite_root / "content" / "example.blob"
            content.write_bytes(payload)
            manifest = json.loads((nonfinite_root / "manifest.json").read_text(encoding="utf-8"))
            manifest["content"][0]["bytes"] = len(payload)
            manifest["content"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
            (nonfinite_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            bundle = Bundle(nonfinite_root)
            with self.assertRaises(BundleError):
                bundle.read_json("inputs/example")

    def test_manifest_json_depth_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_bundle(root)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            cursor = manifest
            for _ in range(70):
                cursor["nested"] = {}
                cursor = cursor["nested"]
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(BundleError):
                verify_bundle(root)


if __name__ == "__main__":
    unittest.main()
