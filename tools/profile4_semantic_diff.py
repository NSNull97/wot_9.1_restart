"""Prove the offline semantic delta from profile4-r3 to profile4.

This verifier is bundle-rooted and data-only.  It re-runs the accepted profile4
chain check, then proves the exact crew-preserving/ammunition-adding delta in
JSON payload descriptors and raw payload bytes.  It does not open SQLite, an
installed client, a live service, or a native trace, and it does not authorize
battle loadouts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

if __package__:
    from .content_bundle import Bundle, BundleError
    from .profile4_chain import verify_profile4_chain
else:  # Direct script execution from tools/.
    from content_bundle import Bundle, BundleError
    from profile4_chain import verify_profile4_chain


R3 = "profile4-r3"
R4 = "profile4"
EXPECTED_AMMO_SHELL = "shell:ms1-stock-ap"
EXPECTED_NATIVE_AMMO = {
    "shell_definition_id": EXPECTED_AMMO_SHELL,
    "native_shell_compact_descr": 2570,
    "native_turret_compact_descr": 5891,
    "native_gun_compact_descr": 5892,
    "native_vehicle_inventory_id": 1,
}
EXPECTED_CHANGED_PATHS = [
    "profile.profile_version",
    "profile.snapshot_revision",
    "profile.inventory[vehicle:ms1].ammunition_count",
    "profile.ammunition",
    "profile.ammo_grant",
    "fixture.fixture_version",
    "fixture.profile_version",
    "fixture.snapshot_revision",
    "fixture.inventory[vehicle:ms1].ammunition_count",
    "fixture.ammunition",
    "fixture.ammo_grant",
    "compatibility.snapshot_revision",
    "compatibility.ammo_mapping",
    "payloads.state.bin.inventory[1].shells[1]",
    "payloads.state.bin.inventory[1].shellsLayout[1]",
]


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fail(message: str) -> None:
    raise BundleError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _pair_value(pairs: Any, key: Any, label: str) -> Any:
    _require(isinstance(pairs, list), f"{label}: expected pairs list")
    found = [row[1] for row in pairs if isinstance(row, list) and len(row) == 2 and row[0] == key]
    _require(len(found) == 1, f"{label}: expected exactly one pair for {key!r}")
    return found[0]


def _ms1_state_fields(state: dict[str, Any], label: str) -> tuple[dict[str, Any], dict[str, Any]]:
    top = _pair_value(state.get("pairs"), "inventory", f"{label}.state")
    inventory = _pair_value(top.get("pairs"), 1, f"{label}.state.inventory")
    fields = inventory.get("pairs")
    return (
        _pair_value(fields, "shells", f"{label}.state.inventory[1]"),
        _pair_value(fields, "shellsLayout", f"{label}.state.inventory[1]"),
    )


def _inventory_item(profile: dict[str, Any], definition: str, label: str) -> dict[str, Any]:
    rows = [row for row in profile.get("inventory", [])
            if isinstance(row, dict) and row.get("vehicle_definition_id") == definition]
    _require(len(rows) == 1, f"{label}: expected one {definition} inventory row")
    return rows[0]


def _normalize_revision(value: dict[str, Any], *, fixture: bool = False) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    normalized["profile_version"] = 3
    normalized["snapshot_revision"] = 3
    if fixture:
        normalized["fixture_version"] = 3
    inventory = normalized.get("inventory")
    _require(isinstance(inventory, list), "revision value inventory is not a list")
    ms1 = _inventory_item(normalized, "vehicle:ms1", "revision normalization")
    ms1["ammunition_count"] = 0
    normalized.pop("ammunition", None)
    normalized.pop("ammo_grant", None)
    return normalized


def _normalize_compatibility(value: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(value)
    normalized["snapshot_revision"] = 3
    normalized.pop("ammo_mapping", None)
    return normalized


def _normalize_state(state: dict[str, Any], label: str, reference: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(state)
    shells, shells_layout = _ms1_state_fields(reference, f"{label}.reference")
    fields = _pair_value(normalized.get("pairs"), "inventory", f"{label}.state")
    vehicle = _pair_value(fields.get("pairs"), 1, f"{label}.state.inventory")
    vehicle_fields = vehicle.get("pairs")
    for key, expected in (("shells", shells), ("shellsLayout", shells_layout)):
        pairs = vehicle_fields
        for row in pairs:
            if isinstance(row, list) and len(row) == 2 and row[0] == key:
                row[1] = copy.deepcopy(expected)
                break
        else:
            _fail(f"{label}.state.inventory[1]: missing {key}")
    return normalized


def compare_profile4_semantic_values(
    profile_r3: dict[str, Any],
    profile_r4: dict[str, Any],
    fixture_r3: dict[str, Any],
    fixture_r4: dict[str, Any],
    compatibility_r3: dict[str, Any],
    compatibility_r4: dict[str, Any],
    payloads_r3: dict[str, Any],
    payloads_r4: dict[str, Any],
    raw_payloads_r3: dict[str, bytes],
    raw_payloads_r4: dict[str, bytes],
    native_crew: bytes,
    native_ammo: bytes,
) -> dict[str, Any]:
    """Validate one r3→r4 pair; raises BundleError on any unexpected mutation."""
    _require("ammunition" not in profile_r3 and "ammo_grant" not in profile_r3,
             "r3 profile already contains ammunition delta")
    _require("ammunition" not in fixture_r3 and "ammo_grant" not in fixture_r3,
             "r3 fixture already contains ammunition delta")
    _require("ammo_mapping" not in compatibility_r3, "r3 compatibility already contains ammo mapping")

    _require(profile_r3.get("crew") == profile_r4.get("crew"), "crew changed between r3 and r4")
    _require(fixture_r3.get("crew") == fixture_r4.get("crew"), "fixture crew changed between r3 and r4")
    _require(profile_r3.get("crew"), "r3 crew is empty")
    _require(_inventory_item(profile_r3, "vehicle:ms1", "r3").get("ammunition_count") == 0,
             "r3 MS-1 ammunition count is not zero")
    _require(_inventory_item(profile_r4, "vehicle:ms1", "r4").get("ammunition_count") == 20,
             "r4 MS-1 ammunition count is not twenty")
    _require(_inventory_item(profile_r3, "vehicle:is7", "r3") ==
             _inventory_item(profile_r4, "vehicle:is7", "r4"), "IS-7 inventory changed")

    ammo_row = {"vehicle_inventory_id": _inventory_item(profile_r4, "vehicle:ms1", "r4")["inventory_id"],
                "shell_definition_id": EXPECTED_AMMO_SHELL, "count": 20}
    _require(profile_r4.get("ammunition") == [ammo_row], "r4 ammunition row is not exact")
    _require(fixture_r4.get("ammunition") == [ammo_row], "r4 fixture ammunition row is not exact")

    ammo_grant = profile_r4.get("ammo_grant")
    _require(isinstance(ammo_grant, dict), "r4 ammo grant is missing")
    _require(ammo_grant.get("grant_id") == "test-ms1-ammo-v1", "r4 ammo grant ID changed")
    _require(ammo_grant.get("base_profile_sha256") == "5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888",
             "r4 ammo grant parent hash changed")
    _require(ammo_grant.get("native_export_sha256") == _digest(native_ammo), "r4 ammo native anchor changed")
    _require(fixture_r4.get("ammo_grant") == ammo_grant, "fixture/profile ammo grant diverged")
    _require(profile_r4.get("crew_grant") == profile_r3.get("crew_grant"), "crew grant changed")
    _require(fixture_r4.get("crew_grant") == fixture_r3.get("crew_grant"), "fixture crew grant changed")
    _require(profile_r3.get("crew_grant", {}).get("native_export_sha256") == _digest(native_crew),
             "r3 crew native anchor changed")

    _require(_normalize_revision(profile_r3) == _normalize_revision(profile_r4),
             "profile changed outside version/ammunition delta")
    _require(_normalize_revision(fixture_r3, fixture=True) == _normalize_revision(fixture_r4, fixture=True),
             "fixture changed outside version/ammunition delta")
    _require(_normalize_compatibility(compatibility_r3) == _normalize_compatibility(compatibility_r4),
             "compatibility changed outside snapshot/ammo mapping delta")

    expected_ammo_mapping = dict(EXPECTED_NATIVE_AMMO)
    expected_ammo_mapping["vehicle_inventory_id"] = ammo_row["vehicle_inventory_id"]
    _require(compatibility_r4.get("ammo_mapping") == [expected_ammo_mapping],
             "r4 ammo mapping does not match measured native IDs")
    _require(compatibility_r3.get("vehicle_mapping") == compatibility_r4.get("vehicle_mapping"),
             "vehicle mapping changed")
    _require(compatibility_r3.get("crew_mapping") == compatibility_r4.get("crew_mapping"),
             "crew mapping changed")

    _require(payloads_r3.get("shop.bin") == payloads_r4.get("shop.bin"), "shop descriptor changed")
    _require(payloads_r3.get("dossier.bin") == payloads_r4.get("dossier.bin"), "dossier descriptor changed")
    state_r3 = payloads_r3.get("state.bin")
    state_r4 = payloads_r4.get("state.bin")
    _require(isinstance(state_r3, dict) and isinstance(state_r4, dict), "state descriptor is not an object")
    shells_r3, layout_r3 = _ms1_state_fields(state_r3, "r3")
    shells_r4, layout_r4 = _ms1_state_fields(state_r4, "r4")
    _require(shells_r3 == {"pairs": [[1, []], [2, []]]}, "r3 shells descriptor is not empty")
    _require(shells_r4 == {"pairs": [[1, [2570, 20, 2826, 0, 3082, 0]], [2, []]]},
             "r4 shells descriptor is not exact")
    _require(layout_r3 == {"pairs": [[1, {"pairs": []}], [2, {"pairs": []}]]},
             "r3 shellsLayout descriptor is not empty")
    _require(layout_r4 == {"pairs": [[1, {"pairs": [[{"tuple": [5891, 5892]}, [2570, 20, 2826, 0, 3082, 0]]]}], [2, {"pairs": []}]]},
             "r4 shellsLayout descriptor is not exact")
    _require(_normalize_state(state_r4, "r4", state_r3) == state_r3,
             "state descriptor changed outside shells delta")

    for name in ("shop.bin", "dossier.bin"):
        _require(raw_payloads_r3[name] == raw_payloads_r4[name], f"{name} bytes changed")
    _require(raw_payloads_r3["state.bin"] != raw_payloads_r4["state.bin"], "state.bin did not change")
    return {
        "status": "PASS_PORTABLE_PROFILE4_SEMANTIC_DIFF",
        "from": R3,
        "to": R4,
        "changed_paths": EXPECTED_CHANGED_PATHS,
        "stable_checks": {
            "identity": "PASS",
            "crew": "PASS_EXACT",
            "is7_inventory": "PASS_EXACT",
            "vehicle_mapping": "PASS_EXACT",
            "crew_mapping": "PASS_EXACT",
            "shop.bin": "PASS_BYTE_IDENTICAL",
            "dossier.bin": "PASS_BYTE_IDENTICAL",
            "state.bin": "PASS_EXPECTED_SHELL_DELTA",
        },
        "ammunition": {"shell_definition_id": EXPECTED_AMMO_SHELL, "count": 20,
                       "native_shell_compact_descr": 2570,
                       "native_turret_compact_descr": 5891,
                       "native_gun_compact_descr": 5892},
        "payloads": {
            name: {"r3_bytes": len(raw_payloads_r3[name]), "r4_bytes": len(raw_payloads_r4[name]),
                   "r3_sha256": _digest(raw_payloads_r3[name]), "r4_sha256": _digest(raw_payloads_r4[name]),
                   "byte_identical": raw_payloads_r3[name] == raw_payloads_r4[name]}
            for name in ("state.bin", "shop.bin", "dossier.bin")
        },
        "native_exports": {"crew_sha256": _digest(native_crew), "ammo_sha256": _digest(native_ammo)},
        "native_compatibility": "NOT_RUN",
        "battle_authorization": "NOT_RUN",
    }


def verify_profile4_semantic_diff(bundle_root: str | Path) -> dict[str, Any]:
    chain = verify_profile4_chain(bundle_root)
    bundle = Bundle(bundle_root)
    r3_profile_raw = bundle.read(f"fixtures/{R3}/profile-input.json")
    r4_base_profile_raw = bundle.read(f"fixtures/{R4}/base-profile-input.json")
    _require(r4_base_profile_raw == r3_profile_raw,
             "r4 base-profile-input is not byte-identical to r3 profile-input")
    values: dict[str, dict[str, Any]] = {}
    for fixture in (R3, R4):
        values[fixture] = {
            "profile": bundle.read_json(f"fixtures/{fixture}/profile-input.json"),
            "fixture": bundle.read_json(f"fixtures/{fixture}/fixture.json"),
            "compatibility": bundle.read_json(f"fixtures/{fixture}/compatibility.json"),
            "payloads": bundle.read_json(f"fixtures/{fixture}/payloads.json"),
        }
    raw = {fixture: {name: bundle.read(f"fixtures/{fixture}/{name}") for name in ("state.bin", "shop.bin", "dossier.bin")}
           for fixture in (R3, R4)}
    result = compare_profile4_semantic_values(
        values[R3]["profile"], values[R4]["profile"], values[R3]["fixture"], values[R4]["fixture"],
        values[R3]["compatibility"], values[R4]["compatibility"], values[R3]["payloads"], values[R4]["payloads"],
        raw[R3], raw[R4], bundle.read("inputs/native-ms1-crew"), bundle.read("inputs/native-ms1-ammo"),
    )
    result["bundle_manifest_sha256"] = _digest((bundle.root / "manifest.json").read_bytes())
    result["chain_status"] = chain["status"]
    result["chain_receipt_status"] = "PASS_PORTABLE_PROFILE4_CHAIN"
    result["base_profile"] = {
        "r4_base_content_id": f"fixtures/{R4}/base-profile-input.json",
        "r3_profile_content_id": f"fixtures/{R3}/profile-input.json",
        "bytes": len(r3_profile_raw),
        "sha256": _digest(r3_profile_raw),
        "byte_identical": True,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_profile4_semantic_diff(args.bundle), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
