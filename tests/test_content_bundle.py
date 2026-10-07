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


if __name__ == "__main__":
    unittest.main()
