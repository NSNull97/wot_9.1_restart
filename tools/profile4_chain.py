"""Verify the accepted MS-1 profile4 parent chain from server-content.v1.

This verifier is deliberately provenance-only.  It checks the immutable
profile4-r4 -> r3 -> r2 -> r1-catalog2 chain, payload digests, native export
anchors, and relative path rules.  It does not open SQLite, consult project
configuration, read an installed client, or generate a new profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

if __package__:
    from .content_bundle import Bundle, BundleError
else:  # Direct script execution from tools/.
    from content_bundle import Bundle, BundleError


EXPECTED_CHAIN = ["profile4", "profile4-r3", "profile4-r2", "profile4-r1"]
EXPECTED_PAYLOADS = ["state.bin", "shop.bin", "dossier.bin"]
EXPECTED_NATIVE_EXPORTS = {"inputs/native-ms1-crew", "inputs/native-ms1-ammo"}
EXPECTED_PROFILE_VERSIONS = {"profile4": 4, "profile4-r3": 3, "profile4-r2": 2, "profile4-r1": 1}
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise BundleError(f"{label}: expected lowercase SHA256")
    return value


def _relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise BundleError(f"{label}: invalid relative path")
    path = Path(value)
    if path.is_absolute() or value.startswith("/") or any(part in ("", ".", "..") for part in path.parts):
        raise BundleError(f"{label}: absolute or escaping path")
    return value


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def verify_profile4_chain(bundle_root: str | Path) -> dict[str, Any]:
    bundle = Bundle(bundle_root)
    manifest = bundle.manifest
    if manifest.get("ruleset") != "test_lab":
        raise BundleError("profile4 verifier only accepts test_lab bundle")
    if manifest.get("catalog", {}).get("revision") != 2:
        raise BundleError("profile4 verifier requires catalog revision 2")
    metadata = bundle.read_json("metadata/profile-chain")
    if metadata.get("version") != 1 or metadata.get("status") != "PASS_LEGACY_HASH_ANCHORS":
        raise BundleError("unsupported profile-chain metadata")
    if any(re.search(r"(?:[A-Za-z]:[\\/]|\\\\|^/)", value) for value in _strings(metadata)):
        raise BundleError("profile-chain metadata contains an absolute path")
    chain = metadata.get("chain")
    if not isinstance(chain, list) or [row.get("fixture") for row in chain] != EXPECTED_CHAIN:
        raise BundleError("profile4 chain order is not r4 -> r3 -> r2 -> r1")

    checks = []
    profile_hashes = []
    profile_json = []
    compatibility_json = []
    for index, row in enumerate(chain):
        if not isinstance(row, dict):
            raise BundleError(f"chain[{index}] is not an object")
        fixture = row["fixture"]
        profile_id = row.get("profile_content_id")
        _relative(row.get("legacy_manifest"), f"chain[{index}].legacy_manifest")
        _hex(row.get("legacy_manifest_sha256"), f"chain[{index}].legacy_manifest_sha256")
        if not isinstance(profile_id, str):
            raise BundleError(f"chain[{index}] profile content ID is missing")
        profile = bundle.read(profile_id)
        profile_hash = _hex(row.get("profile_sha256"), f"chain[{index}].profile_sha256")
        if _digest(profile) != profile_hash:
            raise BundleError(f"chain[{index}] profile digest mismatch")
        profile_hashes.append(profile_hash)
        profile_value = bundle.read_json(profile_id)
        expected_version = EXPECTED_PROFILE_VERSIONS[fixture]
        if ((fixture != "profile4-r1" and profile_value.get("profile_version") != expected_version)
                or profile_value.get("snapshot_revision") != expected_version):
            raise BundleError(f"chain[{index}] profile/snapshot revision mismatch")
        if not isinstance(profile_value.get("account_id"), str):
            raise BundleError(f"chain[{index}] account ID is missing")
        profile_json.append(profile_value)
        fixture_json = bundle.read_json(f"fixtures/{fixture}/fixture.json")
        compatibility = bundle.read_json(f"fixtures/{fixture}/compatibility.json")
        if (fixture_json.get("fixture_version") != expected_version
                or fixture_json.get("snapshot_revision") != expected_version
                or fixture_json.get("account_id") != profile_value["account_id"]):
            raise BundleError(f"chain[{index}] fixture/profile revision mismatch")
        if (compatibility.get("client_build") != "v.0.9.1 #717"
                or compatibility.get("account_id") != profile_value["account_id"]
                or compatibility.get("native_database_id") != profile_value.get("native_database_id")):
            raise BundleError(f"chain[{index}] compatibility identity mismatch")
        expected_catalog = 2 if fixture == "profile4-r1" else 3
        if compatibility.get("compatibility_catalog_revision") != expected_catalog:
            raise BundleError(f"chain[{index}] compatibility catalog revision mismatch")
        if fixture != "profile4-r1" and compatibility.get("wire_sync_revision") != 1:
            raise BundleError(f"chain[{index}] wire sync revision mismatch")
        mapping = compatibility.get("vehicle_mapping")
        if not isinstance(mapping, list) or not mapping:
            raise BundleError(f"chain[{index}] vehicle mapping is missing")
        mapping_by_inventory = {item.get("native_inventory_id"): item for item in mapping}
        if mapping_by_inventory.get(1, {}).get("type_compact_descr") != 3329:
            raise BundleError(f"chain[{index}] MS-1 native mapping mismatch")
        if fixture != "profile4-r1" and mapping_by_inventory.get(2, {}).get("type_compact_descr") != 7169:
            raise BundleError(f"chain[{index}] IS-7 native mapping mismatch")
        compatibility_json.append(compatibility)
        payload_rows = row.get("payloads")
        if not isinstance(payload_rows, list) or [item.get("file") for item in payload_rows] != EXPECTED_PAYLOADS:
            raise BundleError(f"chain[{index}] payload order/shape mismatch")
        payload_checks = []
        for payload in payload_rows:
            payload_id = payload.get("content_id")
            if not isinstance(payload_id, str):
                raise BundleError(f"chain[{index}] payload ID is missing")
            raw = bundle.read(payload_id)
            expected_bytes = payload.get("bytes")
            expected_hash = _hex(payload.get("sha256"), f"chain[{index}] {payload['file']} sha256")
            if expected_bytes != len(raw) or expected_hash != _digest(raw):
                raise BundleError(f"chain[{index}] {payload['file']} digest mismatch")
            payload_checks.append({"file": payload["file"], "content_id": payload_id,
                                   "bytes": len(raw), "sha256": expected_hash})
        if index < len(chain) - 1:
            base_id = row.get("base_profile_content_id")
            base_hash = _hex(row.get("base_profile_sha256"), f"chain[{index}].base_profile_sha256")
            parent_profile_hash = _digest(bundle.read(chain[index + 1]["profile_content_id"]))
            if not isinstance(base_id, str) or _digest(bundle.read(base_id)) != base_hash or base_hash != parent_profile_hash:
                raise BundleError(f"chain[{index}] base profile does not point to the next parent")
        elif "base_profile_content_id" in row or "base_profile_sha256" in row:
            raise BundleError("r1-catalog2 must not have a base profile")
        checks.append({"fixture": fixture, "profile_content_id": profile_id,
                       "profile_sha256": profile_hash, "payloads": payload_checks,
                       "legacy_manifest_sha256": row["legacy_manifest_sha256"]})

    account_ids = {value["account_id"] for value in profile_json}
    native_db_ids = {value["native_database_id"] for value in profile_json}
    if len(account_ids) != 1 or native_db_ids != {1}:
        raise BundleError("profile4 chain identity/native database changed between revisions")
    for left, right in zip(checks[:2], checks[1:3]):
        left_payloads = {item["file"]: item["sha256"] for item in left["payloads"]}
        right_payloads = {item["file"]: item["sha256"] for item in right["payloads"]}
        if left_payloads["shop.bin"] != right_payloads["shop.bin"] or left_payloads["dossier.bin"] != right_payloads["dossier.bin"]:
            raise BundleError(f"{left['fixture']} -> {right['fixture']} changed preserved shop/dossier payload")

    preservation = bundle.read_json("fixtures/profile4-r2/preservation.json")
    r1_payloads = {item["file"]: item["sha256"] for item in checks[3]["payloads"]}
    r2_payloads = {item["file"]: item["sha256"] for item in checks[2]["payloads"]}
    expected_preservation = {
        "status": "PASS_LOCAL_INVARIANTS_ONLY",
        "account_and_ms1_restored_state_sha256": r1_payloads["state.bin"],
        "base_state_sha256": r1_payloads["state.bin"],
        "account_dossier_sha256": "11243d5fc88998314035c78cc9f6f442f32f3289072ac5e5df80ab017469ab36",
        "base_dossier_payload_sha256": r1_payloads["dossier.bin"],
        "base_shop_sha256": r1_payloads["shop.bin"],
        "restored_shop_sha256": r1_payloads["shop.bin"],
        "dossier_cache_payload_sha256": r2_payloads["dossier.bin"],
    }
    if (preservation.get("status") != expected_preservation["status"]
            or any(preservation.get(key) != value for key, value in expected_preservation.items()
                   if key != "dossier_cache_payload_sha256")
            or preservation.get("dossier_cache", {}).get("payload_sha256") != expected_preservation["dossier_cache_payload_sha256"]):
        raise BundleError("profile4-r2 preservation receipt does not match chain payloads")

    native_rows = metadata.get("native_exports")
    if not isinstance(native_rows, list) or {row.get("content_id") for row in native_rows} != EXPECTED_NATIVE_EXPORTS:
        raise BundleError("native export anchor set mismatch")

    grants = [
        ("profile4-r2", "test-is7-v1", profile_json[2].get("test_grant"), profile_hashes[3], None),
        ("profile4-r3", "test-ms1-crew-v1", profile_json[1].get("crew_grant"), profile_hashes[2], "inputs/native-ms1-crew"),
        ("profile4", "test-ms1-ammo-v1", profile_json[0].get("ammo_grant"), profile_hashes[1], "inputs/native-ms1-ammo"),
    ]
    previous_time = None
    grant_checks = []
    for fixture, grant_id, grant, parent_hash, native_export_id in grants:
        if not isinstance(grant, dict) or grant.get("grant_id") != grant_id or grant.get("base_profile_sha256") != parent_hash:
            raise BundleError(f"{fixture} grant does not point to its parent profile")
        granted_at = grant.get("granted_at_ms")
        if not isinstance(granted_at, int) or (previous_time is not None and granted_at <= previous_time):
            raise BundleError(f"{fixture} grant timestamp is not strictly monotonic")
        previous_time = granted_at
        if native_export_id:
            expected_native = next(item["sha256"] for item in native_rows if item["content_id"] == native_export_id)
            if grant.get("native_export_sha256") != expected_native:
                raise BundleError(f"{fixture} grant native export anchor mismatch")
        grant_checks.append({"fixture": fixture, "grant_id": grant_id, "granted_at_ms": granted_at,
                             "base_profile_sha256": parent_hash, "native_export": native_export_id})
    if compatibility_json[1].get("crew_mapping") is None or len(compatibility_json[1]["crew_mapping"]) != 2:
        raise BundleError("profile4-r3 crew mapping is missing")
    ammo_mapping = compatibility_json[0].get("ammo_mapping")
    expected_ammo = {"shell_definition_id": "shell:ms1-stock-ap", "native_shell_compact_descr": 2570,
                     "vehicle_inventory_id": f"{next(iter(account_ids))}:starter-vehicle-v1",
                     "native_vehicle_inventory_id": 1, "native_turret_compact_descr": 5891,
                     "native_gun_compact_descr": 5892}
    if not isinstance(ammo_mapping, list) or expected_ammo not in ammo_mapping:
        raise BundleError("profile4 ammo mapping is missing or differs from measured native IDs")

    native_checks = []
    for row in native_rows:
        content_id = row["content_id"]
        expected = _hex(row.get("sha256"), f"native export {content_id} sha256")
        raw = bundle.read(content_id)
        if expected != _digest(raw):
            raise BundleError(f"native export digest mismatch: {content_id}")
        native_checks.append({"content_id": content_id, "bytes": len(raw), "sha256": expected})
    return {"status": "PASS_PORTABLE_PROFILE4_CHAIN", "chain": checks,
            "grants": grant_checks, "native_exports": native_checks,
            "semantic_checks": {"profile_versions": [EXPECTED_PROFILE_VERSIONS[name] for name in EXPECTED_CHAIN],
                                 "preserved_shop_dossier_edges": 2,
                                 "profile4_r2_preservation": "PASS_LOCAL_INVARIANTS_ONLY",
                                 "profile4_r3_r4_preservation": "NOT_BUNDLED_ABSOLUTE_PATHS",
                                 "ammo_mapping": "PASS"},
            "native_compatibility": "NOT_RUN",
            "bundle_manifest_sha256": _digest((bundle.root / "manifest.json").read_bytes())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_profile4_chain(args.bundle), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
