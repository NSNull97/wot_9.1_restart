"""Export the measured MS-1 server-content closure into server-content.v1.

The source client is read only at export time.  The resulting bundle has no
absolute paths and is intentionally local-only until the resource licence is
resolved.  Existing fixtures, validators, the live service, and SQLite are not
opened or rewritten by this exporter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 16 * 1024 * 1024
FORMAT = "server-content.v1"
ENCODERS = [
    "web/src/game-adapter.mjs", "web/src/store.mjs", "web/src/security.mjs",
    "web/src/test-garage.mjs", "web/src/ms1-crew.mjs", "web/src/ms1-ammo.mjs",
    "tools/hangar_state.py", "tools/test_garage_state.py", "tools/ms1_crew_state.py",
    "tools/ms1_ammo_state.py", "tools/client_audit.py", "tools/packed_xml.py",
    "tools/verify_hangar.py",
]
FIXTURE_ROOTS = {
    "profile1": "local/server/fixtures/271022a3-41e0-406e-b6fa-59930c320442/r1-catalog2",
    "profile4-r1": "local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1-catalog2",
    "profile4-r2": "local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r2-catalog3",
    "profile4-r3": "local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3",
    "profile4": "local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r4-catalog3",
}
DESCRIPTORS = {
    "native-ms1": "local/server/native-descriptors.json",
    "native-is7": "local/server/native-is7-descriptors.json",
}
NATIVE_EXPORTS = {
    "native-ms1-crew": "local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json",
    "native-ms1-ammo": "local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json",
}
RECEIPT = "local/evidence/20261006-server-layout/profile-preservation-01/result.json"
CLIENT_RESOURCES = [
    "res/scripts/item_defs/vehicles/ussr/list.xml",
    "res/scripts/item_defs/vehicles/ussr/components/chassis.xml",
    "res/scripts/item_defs/vehicles/ussr/components/turrets.xml",
    "res/scripts/item_defs/vehicles/ussr/components/guns.xml",
    "res/scripts/item_defs/vehicles/ussr/components/engines.xml",
    "res/scripts/item_defs/vehicles/ussr/components/radios.xml",
    "res/scripts/item_defs/vehicles/ussr/ms-1.xml",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source(path: Path) -> bytes:
    path = path.resolve(strict=True)
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError(f"links are not accepted as export input: {path}")
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError(f"invalid or oversized export input: {path}")
    data = path.read_bytes()
    if len(data) != path.stat().st_size:
        raise ValueError(f"source changed while reading: {path}")
    return data


def relative_source(path: Path, root: Path | None = None) -> str:
    if root is not None:
        path = path.resolve(strict=True)
        root = root.resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError(f"source escaped configured root: {path}")
        return path.relative_to(root).as_posix()
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT):
        raise ValueError(f"project source outside repository: {path}")
    return path.relative_to(ROOT).as_posix()


def add_bytes(out: Path, rows: list[dict[str, Any]], content_id: str, data: bytes,
              source_path: str, classification: str, license_state: str,
              source_sha256: str | None = None) -> None:
    if not content_id or "\\" in content_id or content_id.startswith("/") or ".." in Path(content_id).parts:
        raise ValueError(f"invalid content ID: {content_id}")
    bundle_path = Path("content") / (content_id + ".blob")
    target = out / bundle_path
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    target.write_bytes(data)
    rows.append({"content_id": content_id, "bundle_path": bundle_path.as_posix(),
                 "bytes": len(data), "sha256": digest(data),
                 "source": {"relative_path": source_path, "sha256": source_sha256 or digest(data),
                             "classification": classification, "license": license_state}})


def add_file(out: Path, rows: list[dict[str, Any]], content_id: str, source: Path,
             source_root: Path | None, classification: str = "VERIFIED") -> None:
    data = read_source(source)
    add_bytes(out, rows, content_id, data, relative_source(source, source_root), classification,
              "UNKNOWN; local-only non-redistribution", digest(data))


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def export(args: argparse.Namespace) -> dict[str, Any]:
    client_root = Path(args.client_root).resolve(strict=True)
    if not client_root.is_dir():
        raise ValueError("--client-root must be a directory")
    out = Path(args.out).resolve()
    local_root = (ROOT / "local").resolve(strict=True)
    if not out.is_relative_to(local_root):
        raise ValueError("bundle output must remain inside local/")
    if out.exists():
        raise FileExistsError(f"append-only export output already exists: {out}")
    out.mkdir(parents=True)
    rows: list[dict[str, Any]] = []
    for key, rel in DESCRIPTORS.items():
        path = ROOT / rel
        if path.is_file():
            add_file(out, rows, f"inputs/{key}", path, None)
    for key, rel in NATIVE_EXPORTS.items():
        path = ROOT / rel
        if path.is_file():
            add_file(out, rows, f"inputs/{key}", path, None)
    for key, rel in FIXTURE_ROOTS.items():
        base = ROOT / rel
        if not base.is_dir():
            raise ValueError(f"accepted fixture root is missing: {base}")
        for path in sorted(base.iterdir()):
            if not path.is_file() or path.name == "manifest.json":
                continue
            # Raw historical manifests include absolute client/evidence paths;
            # their hashes remain pinned in metadata/profile-chain.json instead.
            if path.suffix == ".json" and re.search(r"(?:[A-Za-z]:[\\/]|\\\\)", read_source(path).decode("utf-8", errors="ignore")):
                continue
            add_file(out, rows, f"fixtures/{key}/{path.name}", path, None)
    receipt = ROOT / RECEIPT
    add_file(out, rows, "receipts/profile-preservation", receipt, None)
    for rel in CLIENT_RESOURCES:
        path = client_root / rel
        add_file(out, rows, f"client/{rel}", path, client_root)

    # Preserve the old manifest/payload anchors as hashes without importing
    # their absolute-path JSON into the portable closure.
    chain = []
    independent_profiles = []
    ordered_fixture_keys = ["profile4", "profile4-r3", "profile4-r2", "profile4-r1", "profile1"]
    for key in ordered_fixture_keys:
        rel = FIXTURE_ROOTS[key]
        base = ROOT / rel
        manifest = base / "manifest.json"
        raw = read_source(manifest)
        profile = base / "profile-input.json"
        profile_raw = read_source(profile)
        item = {"fixture": key, "legacy_manifest": relative_source(manifest),
                "legacy_manifest_sha256": digest(raw),
                "profile_content_id": f"fixtures/{key}/profile-input.json",
                "profile_sha256": digest(profile_raw)}
        if (base / "base-profile-input.json").is_file():
            base_raw = read_source(base / "base-profile-input.json")
            item.update({"base_profile_content_id": f"fixtures/{key}/base-profile-input.json",
                         "base_profile_sha256": digest(base_raw)})
        payloads = []
        for name in ("state.bin", "shop.bin", "dossier.bin"):
            path = base / name
            raw_payload = read_source(path)
            payloads.append({"file": name, "content_id": f"fixtures/{key}/{name}",
                             "bytes": len(raw_payload), "sha256": digest(raw_payload)})
        item["payloads"] = payloads
        (independent_profiles if key == "profile1" else chain).append(item)
    chain_data = {"version": 1, "status": "PASS_LEGACY_HASH_ANCHORS", "chain": chain,
                  "independent_profiles": independent_profiles,
                  "native_exports": [{"content_id": f"inputs/{key}", "sha256": digest(read_source(ROOT / rel))}
                                     for key, rel in sorted(NATIVE_EXPORTS.items())]}
    add_bytes(out, rows, "metadata/profile-chain", json_bytes(chain_data), RECEIPT, "VERIFIED",
              "UNKNOWN; generated local provenance", digest(read_source(receipt)))

    dependency_rows = []
    for rel in ENCODERS:
        path = ROOT / rel
        raw = read_source(path)
        dependency_rows.append({"path": rel, "bytes": len(raw), "sha256": digest(raw), "status": "FROZEN"})
    revision = digest(json_bytes(dependency_rows))
    manifest = {
        "format": FORMAT, "manifest_revision": 1,
        "ruleset": "test_lab", "target": {"client_build": "v.0.9.1 #717", "region": "RU",
        "client_manifest_sha256": args.client_manifest_sha256},
        "catalog": {"revision": 2, "scope": "verified MS-1 display catalogue; trades unavailable"},
        "encoder": {"api": "portable-hangar.v1", "serialization": "python2-protocol2-bounded.v1",
                     "revision": "sha256:" + revision, "dependencies": dependency_rows},
        "provenance": {"source_receipt": "content/receipts/profile-preservation.blob",
                        "legacy_profile_receipt": "content/receipts/profile-preservation.blob",
                        "source_receipt_sha256": digest(read_source(receipt)),
                        "license": "UNKNOWN; local-only non-redistribution",
                        "absolute_paths_in_legacy_receipts": True},
        "content": sorted(rows, key=lambda item: item["content_id"]),
        "scope": {"profiles": sorted(FIXTURE_ROOTS), "client_resources": CLIENT_RESOURCES,
                  "native_exports": sorted(NATIVE_EXPORTS), "live_state_included": False},
        "native_compatibility": "NOT_RUN; requires real original-client exchange",
    }
    (out / "manifest.json").write_bytes(json_bytes(manifest))
    return {"status": "PASS_CONTENT_BUNDLE_EXPORTED", "output": str(out),
            "content_count": len(rows), "encoder_revision": "sha256:" + revision,
            "client_manifest_sha256": args.client_manifest_sha256}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-root", required=True, help="explicit read-only original #717 client copy")
    parser.add_argument("--out", required=True, help="fresh ignored output under local/")
    parser.add_argument("--client-manifest-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(export(args), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
