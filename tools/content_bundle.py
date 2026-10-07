"""Validate and read a bounded, relative-path server-content.v1 bundle.

The bundle is an input artifact, not a client installation and not an account
backup.  This module deliberately has no project-config or SQLite dependency:
portable generators can point it at a copied bundle and prove that the client
tree is absent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


FORMAT = "server-content.v1"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_CONTENT_BYTES = 16 * 1024 * 1024


class BundleError(ValueError):
    """The bundle is malformed, unsafe, or does not match its manifest."""


def _relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise BundleError(f"{label}: expected slash-separated relative path")
    path = Path(value)
    if path.is_absolute() or value.startswith("/") or any(part in ("", ".", "..") for part in path.parts):
        raise BundleError(f"{label}: path is not relative")
    return value


def _read(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise BundleError(f"links are forbidden: {path}")
    if not path.is_file():
        raise BundleError(f"missing bundle file: {path}")
    size = path.stat().st_size
    if size > maximum:
        raise BundleError(f"bundle file exceeds limit: {path}")
    data = path.read_bytes()
    if len(data) != size:
        raise BundleError(f"bundle file changed while reading: {path}")
    return data


def load_manifest(bundle_root: str | Path) -> dict[str, Any]:
    root = Path(bundle_root).resolve(strict=True)
    raw = _read(root / "manifest.json", MAX_MANIFEST_BYTES)
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BundleError("manifest.json is not UTF-8 JSON") from error
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise BundleError("unsupported server content bundle format")
    if manifest.get("manifest_revision") != 1:
        raise BundleError("unsupported manifest revision")
    content = manifest.get("content")
    if not isinstance(content, list) or not content:
        raise BundleError("manifest content list is empty")
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for index, item in enumerate(content):
        if not isinstance(item, dict):
            raise BundleError(f"content[{index}] is not an object")
        content_id = _relative(item.get("content_id"), f"content[{index}].content_id")
        bundle_path = _relative(item.get("bundle_path"), f"content[{index}].bundle_path")
        if content_id in seen_ids or bundle_path in seen_paths:
            raise BundleError("duplicate content ID or bundle path")
        seen_ids.add(content_id)
        seen_paths.add(bundle_path)
        if not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
            raise BundleError(f"content[{index}] has invalid digest")
        if not isinstance(item.get("bytes"), int) or item["bytes"] < 0 or item["bytes"] > MAX_CONTENT_BYTES:
            raise BundleError(f"content[{index}] has invalid size")
        source = item.get("source")
        if not isinstance(source, dict):
            raise BundleError(f"content[{index}] has no source record")
        _relative(source.get("relative_path"), f"content[{index}].source.relative_path")
        if source.get("classification") not in {"VERIFIED", "OBSERVED", "INFERRED", "UNKNOWN"}:
            raise BundleError(f"content[{index}] has invalid classification")
        license_state = source.get("license")
        if not isinstance(license_state, str) or not license_state:
            raise BundleError(f"content[{index}] has no license decision")
        target = (root / bundle_path).resolve()
        if not target.is_relative_to(root):
            raise BundleError(f"content[{index}] escapes bundle root")
    if not isinstance(manifest.get("encoder"), dict) or not manifest["encoder"].get("revision"):
        raise BundleError("encoder revision is missing")
    provenance = manifest.get("provenance")
    if not isinstance(provenance, dict):
        raise BundleError("provenance is missing")
    for key in ("source_receipt", "legacy_profile_receipt"):
        receipt_path = _relative(provenance.get(key), f"provenance.{key}")
        if receipt_path not in seen_paths:
            raise BundleError(f"provenance receipt is not included: {receipt_path}")
    return manifest


def verify_bundle(bundle_root: str | Path) -> dict[str, Any]:
    root = Path(bundle_root).resolve(strict=True)
    manifest = load_manifest(root)
    checked = []
    expected_paths = {"manifest.json"}
    for item in manifest["content"]:
        path = _relative(item["bundle_path"], "bundle_path")
        expected_paths.add(path)
        target = (root / path).resolve(strict=True)
        if not target.is_relative_to(root):
            raise BundleError("bundle path escaped root")
        raw = _read(target, MAX_CONTENT_BYTES)
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) != item["bytes"] or digest != item["sha256"]:
            raise BundleError(f"digest/size mismatch for {path}")
        checked.append({"content_id": item["content_id"], "bytes": len(raw), "sha256": digest})
    actual_paths = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual_paths != expected_paths:
        extra = sorted(actual_paths - expected_paths)
        missing = sorted(expected_paths - actual_paths)
        raise BundleError(f"bundle file set differs; extra={extra}, missing={missing}")
    return {"status": "PASS_CONTENT_BUNDLE", "format": FORMAT,
            "content_count": len(checked), "content": checked,
            "ruleset": manifest.get("ruleset"), "encoder_revision": manifest["encoder"]["revision"]}


class Bundle:
    """Read-only access to validated content IDs."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=True)
        self.manifest = load_manifest(self.root)
        verify_bundle(self.root)
        self._by_id = {item["content_id"]: item for item in self.manifest["content"]}

    def path(self, content_id: str) -> Path:
        item = self._by_id.get(content_id)
        if item is None:
            raise BundleError(f"unknown content ID: {content_id}")
        return self.root / item["bundle_path"]

    def read(self, content_id: str) -> bytes:
        data = _read(self.path(content_id), MAX_CONTENT_BYTES)
        item = self._by_id[content_id]
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise BundleError(f"content changed: {content_id}")
        return data

    def read_json(self, content_id: str) -> Any:
        try:
            return json.loads(self.read(content_id).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BundleError(f"content is not UTF-8 JSON: {content_id}") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, help="validated server-content.v1 directory")
    args = parser.parse_args()
    print(json.dumps(verify_bundle(args.bundle), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
