"""Audit the bounded P08A battle-lifecycle source boundary.

The inputs are the already exported P00/P01 evidence files for the verified
World of Tanks 0.9.1 #717 build.  This module checks exact evidence hashes,
the four lifecycle groups (Account, Avatar, Arena and Vehicle), and a small
set of measured method/property type shapes.  It never imports client code,
executes bytecode, decodes packets, or starts a client/server process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 64
MAX_ITEMS = 100_000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

LIFECYCLE_SHA256 = "f4b8e847513258fff543f46b3efa5c41d3b191df91863a30e04a54fd8220fbcf"
CONTRACTS_SHA256 = "c9bd0893dfdb1ec6c09de9af200b04eb19b6dd08f71b97f40b32bb831a70a6e5"
RESOURCE_FACTS_SHA256 = "817a9c01dd7b367c8d2b54be517f44c08720b3a508bddca0d8f0436f069c5d71"
SOURCES_SHA256 = "67a4d82108d821a3a39614ba9b3a278cbf8330b4329d6c6e5e9b5cc8ef53eb9a"
EXPECTED_BYTES = {"lifecycle": 17049, "contracts": 156154, "resource_facts": 9712, "sources": 3268}


class LifecycleAuditError(ValueError):
    """Input escaped the bound or differs from the pinned source boundary."""


def _reject_constant(value: str) -> Any:
    raise LifecycleAuditError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LifecycleAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _check_bounds(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    if count is None:
        count = [0]
    count[0] += 1
    if depth > MAX_DEPTH or count[0] > MAX_ITEMS:
        raise LifecycleAuditError("JSON depth or item bound exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise LifecycleAuditError("JSON object key must be text")
            _check_bounds(child, depth + 1, count)
    elif isinstance(value, list):
        for child in value:
            _check_bounds(child, depth + 1, count)


def _bounded(root: Path, path: str | Path, *, must_exist: bool = True) -> Path:
    root = root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    probe = candidate
    while probe != probe.parent:
        if probe.exists() and (probe.is_symlink() or getattr(probe, "is_junction", lambda: False)()):
            raise LifecycleAuditError(f"path link is forbidden: {probe}")
        probe = probe.parent
    try:
        candidate = candidate.resolve(strict=must_exist)
        candidate.relative_to(root)
    except (OSError, ValueError) as error:
        raise LifecycleAuditError(f"path escapes bound: {candidate}") from error
    if must_exist and not candidate.is_file():
        raise LifecycleAuditError(f"file required: {candidate}")
    return candidate


def _read_json(root: Path, path: str | Path, label: str) -> tuple[Any, Path, str, int]:
    candidate = _bounded(root, path)
    info = candidate.stat()
    if not 0 < info.st_size <= MAX_BYTES:
        raise LifecycleAuditError(f"{label} size outside bounds")
    raw = candidate.read_bytes()
    if len(raw) != info.st_size:
        raise LifecycleAuditError(f"{label} changed while reading")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except LifecycleAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise LifecycleAuditError(f"{label} is not bounded UTF-8 JSON") from error
    _check_bounds(value)
    return value, candidate, hashlib.sha256(raw).hexdigest(), len(raw)


def _type_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        raise LifecycleAuditError("type node is malformed")
    if set(value) == {"base64"} and isinstance(value["base64"], str):
        return value["base64"]
    kind = value.get("value")
    children = value.get("children")
    if kind in {"ARRAY", "TUPLE"} and isinstance(children, list):
        if kind == "ARRAY" and len(children) == 1 and children[0].get("name") == "of":
            return f"ARRAY<{_type_name(children[0].get('data'))}>"
        if kind == "TUPLE" and len(children) == 2 and children[0].get("name") == "of":
            return f"TUPLE<{_type_name(children[0].get('data'))},{children[1].get('name')}={children[1].get('data')}>"
    raise LifecycleAuditError("unsupported type shape")


def _method_map(definition: dict[str, Any], section: str) -> dict[str, dict[str, Any]]:
    rows = definition.get(section)
    if not isinstance(rows, list):
        raise LifecycleAuditError(f"missing contract section: {section}")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise LifecycleAuditError(f"malformed {section} method")
        if row["name"] in result:
            raise LifecycleAuditError(f"duplicate {section} method: {row['name']}")
        args = row.get("args")
        if not isinstance(args, list) or not all(isinstance(item, (str, dict)) for item in args):
            raise LifecycleAuditError(f"malformed args: {section}.{row['name']}")
        result[row["name"]] = row
    return result


def _check_methods(definition: dict[str, Any], section: str,
                   expected: dict[str, tuple[list[str], bool]]) -> dict[str, Any]:
    rows = _method_map(definition, section)
    result: dict[str, Any] = {}
    for name, (types, exposed) in expected.items():
        row = rows.get(name)
        if row is None:
            raise LifecycleAuditError(f"missing method: {section}.{name}")
        actual = [_type_name(item) for item in row["args"]]
        if actual != types or row.get("exposed") is not exposed or row.get("wire_id") != "UNKNOWN":
            raise LifecycleAuditError(f"method shape differs: {section}.{name}")
        result[name] = {"args": actual, "exposed": exposed, "wire_id": "UNKNOWN"}
    return result


def _check_properties(definition: dict[str, Any], expected: dict[str, tuple[str, str]]) -> dict[str, Any]:
    rows = definition.get("properties")
    if not isinstance(rows, list):
        raise LifecycleAuditError("missing properties section")
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise LifecycleAuditError("malformed property")
        if row["name"] in by_name:
            raise LifecycleAuditError(f"duplicate property: {row['name']}")
        by_name[row["name"]] = row
    result: dict[str, Any] = {}
    for name, (kind, flags) in expected.items():
        row = by_name.get(name)
        if row is None or _type_name(row.get("type")) != kind or row.get("flags") != flags:
            raise LifecycleAuditError(f"property shape differs: {name}")
        result[name] = {"type": kind, "flags": flags}
    return result


LIFECYCLE_GROUPS = {
    "account": {
        "source": "scripts/client/Account.py",
        "names": ["<module>.PlayerAccount.onBecomePlayer", "<module>.PlayerAccount.onBecomeNonPlayer", "<module>.PlayerAccount.showGUI"],
    },
    "avatar": {
        "source": "scripts/client/Avatar.py",
        "names": ["<module>.PlayerAvatar.onBecomePlayer", "<module>.PlayerAvatar.onBecomeNonPlayer", "<module>.PlayerAvatar.onEnterWorld", "<module>.PlayerAvatar.onLeaveWorld", "<module>.PlayerAvatar.onSpaceLoaded", "<module>.PlayerAvatar.vehicle_onEnterWorld", "<module>.PlayerAvatar.vehicle_onLeaveWorld", "<module>.PlayerAvatar.updateArena", "<module>.PlayerAvatar.moveVehicleByCurrentKeys", "<module>.PlayerAvatar.moveVehicle", "<module>.PlayerAvatar.shoot"],
    },
    "vehicle": {
        "source": "scripts/client/Vehicle.py",
        "names": ["<module>.Vehicle.onEnterWorld", "<module>.Vehicle.onLeaveWorld", "<module>.Vehicle.set_health", "<module>.Vehicle.onHealthChanged"],
    },
}

EXPECTED_SOURCE_ROWS = {
    "res/scripts/entities.xml": (860, "5613d3affa600b80a2c04418cc5bc8549dd7e0ecf77c04efee11fb42e4061004"),
    "res/scripts/entity_defs/alias.xml": (5987, "14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746"),
    "res/scripts/entity_defs/account.def": (10588, "883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674"),
    "res/scripts/entity_defs/avatar.def": (7450, "38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d"),
    "res/scripts/entity_defs/vehicle.def": (5588, "08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297"),
    "res/scripts/entity_defs/arena.def": (3036, "e50906f11e0fcbf1f5b41e105353689ca4b9e3cdb1768b7ac41edab7f3c2f4fc"),
    "res/scripts/entity_defs/login.def": (468, "9cc2fa3a962cce89c10e964b317e93143845f2d8b812e17018bd5e174faccf98"),
    "res/scripts/client/account.pyc": (45998, "bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef"),
    "res/scripts/client/avatar.pyc": (83656, "c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e"),
    "res/scripts/client/vehicle.pyc": (24119, "b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c"),
    "res/scripts/client/connectionmanager.pyc": (10408, "84deb9fbacb295991ae332df520c54a48fad62dcfee5d854eb7637bf402c0d20"),
    "res/scripts/client/avatarpositioncontrol.pyc": (3056, "7101af94b5f075bb3eed8dd27fbac65b62b2841cd01302a5e9e6daebf5d69882"),
    "res/scripts/client/clientarena.pyc": (12823, "30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455"),
    "res/scripts/client/battlereplay.pyc": (31905, "9d6d311a7bbe26e0c6cbc64b5fe0d5d9997b2a070667811ffe40ca116f4c0f02"),
    "res/scripts/item_defs/vehicles/germany/waffentrager_e100.xml": (7551, "6d8de10ed31cb908738ca9b32935aacfe01fec78d47239dadbd86713cba052e2"),
    "res/scripts/item_defs/vehicles/uk/gb48_fv215b_183.xml": (6264, "ffbe8c9bbffbddf61d9197ce0cd4d4d79b6e0a6bfcbf2846c10fc31dd38f6712"),
    "res/scripts/item_defs/vehicles/uk/components/guns.xml": (30258, "4214df566a69b23e92f339f0a157bb89145a41a90ea7ce1db7762496342028cd"),
    "res/scripts/item_defs/vehicles/uk/components/shells.xml": (13955, "3dee7c0961b050bf78d3954f85813ad62beb57d1d3e33b4d0738ab3dbf62cbac"),
    "res/scripts/item_defs/vehicles/ussr/t-34-85.xml": (18759, "3b69621a659e3369eddaefd078e7a6d3dbc52f8271c2c3318839956d3021cb92"),
    "WorldOfTanks.exe": (29131632, "86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed"),
}


def _audit_lifecycle(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LifecycleAuditError("lifecycle manifest must be an object")
    result: dict[str, Any] = {}
    for group, expected in LIFECYCLE_GROUPS.items():
        rows = value.get(group)
        if not isinstance(rows, list):
            raise LifecycleAuditError(f"missing lifecycle group: {group}")
        by_name: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("qualified_name"), str):
                raise LifecycleAuditError(f"malformed lifecycle row: {group}")
            name = row["qualified_name"]
            if name in by_name:
                raise LifecycleAuditError(f"duplicate lifecycle row: {name}")
            by_name[name] = row
        if set(by_name) != set(expected["names"]):
            raise LifecycleAuditError(f"lifecycle names differ: {group}")
        if any(row.get("source_filename") != expected["source"] for row in by_name.values()):
            raise LifecycleAuditError(f"lifecycle source differs: {group}")
        result[group] = {"source": expected["source"], "methods": expected["names"]}
    # The exporter includes these intentionally empty buckets; preserving that
    # fact prevents a silent move of Arena declarations into an unpinned group.
    for empty in ("avatarpositioncontrol", "clientarena", "battlereplay"):
        if value.get(empty) != []:
            raise LifecycleAuditError(f"unexpected lifecycle rows: {empty}")
    return result


def _audit_sources(value: Any) -> dict[str, Any]:
    if not isinstance(value, list):
        raise LifecycleAuditError("source manifest must be a list")
    seen: set[str] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "bytes"}:
            raise LifecycleAuditError("source manifest row is malformed")
        path = row["path"]
        if not isinstance(path, str) or not path or Path(path).is_absolute() or "\\" in path or ".." in Path(path).parts:
            raise LifecycleAuditError("source path is not bounded")
        if path in seen:
            raise LifecycleAuditError(f"duplicate source path: {path}")
        seen.add(path)
        if type(row["bytes"]) is not int or row["bytes"] < 0:
            raise LifecycleAuditError("source byte count is malformed")
        if not isinstance(row["sha256"], str) or not SHA256.fullmatch(row["sha256"]):
            raise LifecycleAuditError("source hash is malformed")
    actual = {row["path"]: (row["bytes"], row["sha256"]) for row in value}
    if actual != EXPECTED_SOURCE_ROWS:
        raise LifecycleAuditError("source manifest differs from pinned P00/P01 boundary")
    return {"count": len(actual), "paths": sorted(actual)}


def _audit_contracts(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("definitions"), dict):
        raise LifecycleAuditError("contracts root/definitions malformed")
    definitions = value["definitions"]
    for group in ("account", "avatar", "arena", "vehicle"):
        if not isinstance(definitions.get(group), dict):
            raise LifecycleAuditError(f"missing contract group: {group}")
    account = definitions["account"]
    avatar = definitions["avatar"]
    arena = definitions["arena"]
    vehicle = definitions["vehicle"]
    methods = {
        "account": {
            "BaseMethods": _check_methods(account, "BaseMethods", {
                "onArenaCreated": (["MAILBOX", "UINT64", "OBJECT_ID", "UINT8", "INT32", "UINT8"], False),
                "onArenaJoinFailure": (["UINT64", "UINT8", "STRING"], False),
            }),
            "ClientMethods": _check_methods(account, "ClientMethods", {
                "onArenaCreated": ([], False),
                "onArenaJoinFailure": (["UINT8", "STRING"], False),
                "showGUI": (["STRING"], False),
            }),
        },
        "avatar": {
            "BaseMethods": _check_methods(avatar, "BaseMethods", {
                "updateArena": (["UINT8", "STRING", "ARRAY<DISCLOSE_EVENT>"], False),
            }),
            "ClientMethods": _check_methods(avatar, "ClientMethods", {
                "updateArena": (["UINT8", "STRING"], False),
            }),
            "properties": _check_properties(avatar, {
                "state": ("UINT16", "BASE"), "arena": ("MAILBOX", "BASE"),
                "playerVehicle": ("MAILBOX", "BASE"), "playerVehicleID": ("OBJECT_ID", "OWN_CLIENT"),
                "arenaUniqueID": ("UINT64", "BASE_AND_CLIENT"), "arenaTypeID": ("INT32", "BASE_AND_CLIENT"),
                "arenaBonusType": ("UINT8", "BASE_AND_CLIENT"), "arenaGuiType": ("UINT8", "BASE_AND_CLIENT"),
                "arenaExtraData": ("PYTHON", "BASE_AND_CLIENT"),
            }),
        },
        "arena": {
            "BaseMethods": _check_methods(arena, "BaseMethods", {
                "onVehicleCreated": (["OBJECT_ID"], False), "onCreateVehicleFailure": (["OBJECT_ID"], False),
                "stopByFailure": (["UINT8"], False), "reuse": (["UINT8", "UINT8", "UINT8", "PYTHON", "INT32", "MAILBOX", "PYTHON", "BOOL", "UINT8", "UINT8", "PYTHON", "UINT64", "INT8"], False),
                "setAvatarReady": (["OBJECT_ID", "OBJECT_ID"], False), "removeAvatar": (["OBJECT_ID"], False),
                "sendArenaStateTo": (["MAILBOX", "UINT8"], False),
            }),
            "CellMethods": _check_methods(arena, "CellMethods", {
                "onVehicleCreated": (["UINT8", "OBJECT_ID", "BOOL"], False), "reuse": (["UINT8", "UINT8"], False),
            }),
            "properties": _check_properties(arena, {
                "state": ("UINT16", "BASE"), "typeID": ("INT32", "BASE"), "roundLength": ("INT32", "BASE"),
                "roster": ("PYTHON", "BASE"), "geometry_cell": ("STRING", "CELL_PUBLIC"), "gameplayID": ("UINT16", "CELL_PUBLIC"),
            }),
        },
        "vehicle": {
            "CellMethods": _check_methods(vehicle, "CellMethods", {"shoot": (["FLOAT32"], False)}),
            "ClientMethods": _check_methods(vehicle, "ClientMethods", {"onHealthChanged": (["INT16", "OBJECT_ID", "UINT8"], False)}),
            "properties": _check_properties(vehicle, {
                "state": ("UINT8", "BASE"), "health": ("INT16", "ALL_CLIENTS"),
                "ammo": ("ARRAY<INT32>", "CELL_PRIVATE"), "arena": ("MAILBOX", "BASE"),
                "arenaTypeID": ("INT32", "CELL_PRIVATE"), "arenaBonusType": ("INT32", "CELL_PRIVATE"),
                "arenaUniqueID": ("UINT64", "CELL_PRIVATE"), "accountDBID": ("DB_ID", "CELL_PRIVATE"),
            }),
        },
    }
    return methods


def audit(*, root: str | Path, lifecycle: str | Path, contracts: str | Path,
          resource_facts: str | Path, sources: str | Path) -> dict[str, Any]:
    repository = Path(root).resolve()
    specs = [
        ("lifecycle", lifecycle, LIFECYCLE_SHA256), ("contracts", contracts, CONTRACTS_SHA256),
        ("resource_facts", resource_facts, RESOURCE_FACTS_SHA256), ("sources", sources, SOURCES_SHA256),
    ]
    values: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    for label, path, expected_sha in specs:
        value, candidate, digest, size = _read_json(repository, path, label)
        if size != EXPECTED_BYTES[label] or digest != expected_sha:
            raise LifecycleAuditError(f"{label} hash/size differs from pinned evidence")
        values[label] = value
        inputs[label] = {"path": candidate.relative_to(repository).as_posix(), "bytes": size, "sha256": digest}
    lifecycle_report = _audit_lifecycle(values["lifecycle"])
    contract_report = _audit_contracts(values["contracts"])
    source_report = _audit_sources(values["sources"])
    resource = values["resource_facts"]
    if not isinstance(resource, dict) or set(resource) != {"wte_magazines", "fv183_module", "fv183_hesh_shot", "fv183_hesh_shell", "t34_hull", "embedded_python_version_strings", "active_runtime_version"}:
        raise LifecycleAuditError("resource-facts keys differ from pinned boundary")
    return {
        "status": "PASS_STATIC_SOURCE_BOUNDARY_ONLY",
        "schema": "p08a-lifecycle-static-audit.v1",
        "build": "v.0.9.1 #717",
        "inputs": inputs,
        "lifecycle_groups": lifecycle_report,
        "contracts": contract_report,
        "source_manifest": source_report,
        "resource_facts": {"keys": sorted(resource), "active_runtime_version": resource["active_runtime_version"]},
        "wire_ids": "UNKNOWN",
        "native_lifecycle": "NOT_RUN",
        "native_ui_audio_timer": "NOT_RUN",
        "server_handoff": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    base = "local/evidence/20261002-p00-p01/summary"
    parser.add_argument("--lifecycle", default=f"{base}/lifecycle-static.json")
    parser.add_argument("--contracts", default=f"{base}/contracts.json")
    parser.add_argument("--resource-facts", dest="resource_facts", default=f"{base}/resource-facts.json")
    parser.add_argument("--sources", default=f"{base}/sources.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        report = audit(root=args.root, lifecycle=args.lifecycle, contracts=args.contracts,
                       resource_facts=args.resource_facts, sources=args.sources)
        if args.out:
            output = _bounded(Path(args.root).resolve(), args.out, must_exist=False)
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 64 * 1024:
                raise LifecycleAuditError("receipt exceeds bounds")
            output.write_bytes(raw + b"\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (LifecycleAuditError, OSError) as error:
        raise SystemExit(f"p08a lifecycle audit rejected: {error}")


if __name__ == "__main__":
    main()
