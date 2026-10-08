"""Bounded static audit for the P07A visibility source boundary.

The verifier reads the existing P00/P01 contract and source-manifest receipts
and checks the eight deliberately small visibility declarations used by the
P07A handoff.  It also re-hashes the two permitted #717 client copies.  The
audit never imports client bytecode, assigns wire IDs, decodes payloads or
starts a client, gateway, server or deployed service.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


MAX_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 32
MAX_ITEMS = 100_000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

CONTRACTS_SHA256 = "c9bd0893dfdb1ec6c09de9af200b04eb19b6dd08f71b97f40b32bb831a70a6e5"
SOURCES_SHA256 = "67a4d82108d821a3a39614ba9b3a278cbf8330b4329d6c6e5e9b5cc8ef53eb9a"

# The source rows are copied from the hash-bound P00/P01 inventory.  Keeping
# this table local makes a changed evidence manifest fail closed instead of
# silently expanding the static contract.
SELECTED_SOURCES = {
    "res/scripts/entity_defs/avatar.def": (7450, "38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d"),
    "res/scripts/entity_defs/vehicle.def": (5588, "08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297"),
    "res/scripts/entity_defs/arena.def": (3036, "e50906f11e0fcbf1f5b41e105353689ca4b9e3cdb1768b7ac41edab7f3c2f4fc"),
    "res/scripts/client/avatar.pyc": (83656, "c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e"),
    "res/scripts/client/vehicle.pyc": (24119, "b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c"),
    "res/scripts/client/clientarena.pyc": (12823, "30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455"),
}

EXPECTED = {
    ("avatar", "CellMethods", "freezeVisibilityState"): {
        "kind": "method", "args": [], "exposed": False, "wire_id": "UNKNOWN",
    },
    ("avatar", "CellMethods", "receiveVisibilityInfo"): {
        "kind": "method", "args": ["ARRAY<OBJECT_ID>", "ARRAY<FLOAT32>", "ARRAY<FLOAT32>"],
        "exposed": False, "wire_id": "UNKNOWN",
    },
    ("vehicle", "CellMethods", "sendVisibilityDevelopmentInfo"): {
        "kind": "method", "args": ["OBJECT_ID", "VECTOR3"], "exposed": True,
        "wire_id": "UNKNOWN",
    },
    ("vehicle", "properties", "invisibility"): {
        "kind": "property", "type": "FLOAT32", "flags": "CELL_PUBLIC",
    },
    ("vehicle", "properties", "detectedVehicles"): {
        "kind": "property", "type": "ARRAY<OBJECT_ID>", "flags": "CELL_PUBLIC",
    },
    ("arena", "CellMethods", "receiveVehicleVisibilityInfo"): {
        "kind": "method", "args": [
            "OBJECT_ID", "ARRAY<OBJECT_ID>", "ARRAY<FLOAT32>", "ARRAY<FLOAT32>",
            "FLOAT32", "ARRAY<OBJECT_ID>",
        ], "exposed": False, "wire_id": "UNKNOWN",
    },
    ("arena", "properties", "fogOfWar"): {
        "kind": "property", "type": "UINT8", "flags": "BASE",
    },
    ("arena", "properties", "fogOfWarCell"): {
        "kind": "property", "type": "UINT8", "flags": "CELL_PRIVATE",
    },
}


class P07AVisibilityAuditError(ValueError):
    """An input escaped its bound or differs from the pinned contract."""


def _reject_constant(value: str) -> Any:
    raise P07AVisibilityAuditError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise P07AVisibilityAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _check_bounds(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    if count is None:
        count = [0]
    if depth > MAX_DEPTH:
        raise P07AVisibilityAuditError("JSON nesting exceeds bounds")
    count[0] += 1
    if count[0] > MAX_ITEMS:
        raise P07AVisibilityAuditError("JSON item count exceeds bounds")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise P07AVisibilityAuditError("JSON object key must be text")
            _check_bounds(child, depth + 1, count)
    elif isinstance(value, list):
        for child in value:
            _check_bounds(child, depth + 1, count)


def _bounded(root: Path, path: str | Path, *, directory: bool = False,
             must_exist: bool = True) -> Path:
    root = root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    probe = candidate
    while probe != probe.parent:
        if probe.exists() and (probe.is_symlink() or getattr(probe, "is_junction", lambda: False)()):
            raise P07AVisibilityAuditError(f"path link is forbidden: {probe}")
        probe = probe.parent
    try:
        candidate = candidate.resolve(strict=must_exist)
        candidate.relative_to(root)
    except (OSError, ValueError) as error:
        raise P07AVisibilityAuditError(f"path escapes bound: {candidate}") from error
    if must_exist and directory and not candidate.is_dir():
        raise P07AVisibilityAuditError(f"directory required: {candidate}")
    if must_exist and not directory and not candidate.is_file():
        raise P07AVisibilityAuditError(f"file required: {candidate}")
    return candidate


def _read(root: Path, path: str | Path, maximum: int = MAX_BYTES) -> tuple[bytes, Path, str]:
    candidate = _bounded(root, path)
    try:
        info = candidate.stat()
        if not 0 < info.st_size <= maximum:
            raise P07AVisibilityAuditError(f"file size outside bounds: {candidate}")
        raw = candidate.read_bytes()
    except OSError as error:
        raise P07AVisibilityAuditError(f"cannot read: {candidate}") from error
    if len(raw) != info.st_size:
        raise P07AVisibilityAuditError(f"file changed while reading: {candidate}")
    return raw, candidate, hashlib.sha256(raw).hexdigest()


def _json(root: Path, path: str | Path) -> tuple[Any, Path, str]:
    raw, candidate, digest = _read(root, path)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except P07AVisibilityAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise P07AVisibilityAuditError(f"bounded UTF-8 JSON required: {candidate}") from error
    _check_bounds(value)
    return value, candidate, digest


def _type_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        raise P07AVisibilityAuditError("type node is malformed")
    if set(value) == {"base64"} and isinstance(value["base64"], str):
        return value["base64"]
    if value.get("value") == "ARRAY" and isinstance(value.get("children"), list):
        children = value["children"]
        if len(children) != 1 or not isinstance(children[0], dict) or children[0].get("name") != "of":
            raise P07AVisibilityAuditError("array type shape differs")
        return f"ARRAY<{_type_name(children[0].get('data'))}>"
    raise P07AVisibilityAuditError("unsupported type shape")


def _definitions(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("definitions"), dict):
        raise P07AVisibilityAuditError("contracts definitions object required")
    definitions = value["definitions"]
    for entity in ("avatar", "vehicle", "arena"):
        if not isinstance(definitions.get(entity), dict):
            raise P07AVisibilityAuditError(f"missing definition: {entity}")
    return definitions


def _rows(definition: dict[str, Any], section: str) -> list[dict[str, Any]]:
    rows = definition.get(section)
    if not isinstance(rows, list):
        raise P07AVisibilityAuditError(f"section is not a list: {section}")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise P07AVisibilityAuditError(f"malformed {section} row")
        name = row["name"]
        if name in seen:
            raise P07AVisibilityAuditError(f"duplicate {section} name: {name}")
        seen.add(name)
        result.append(row)
    return result


def _audit_contracts(value: Any) -> dict[str, Any]:
    definitions = _definitions(value)
    found: dict[tuple[str, str, str], dict[str, Any]] = {}
    for (entity, section, name), expected in EXPECTED.items():
        rows = _rows(definitions[entity], section)
        matches = [row for row in rows if row.get("name") == name]
        if len(matches) != 1:
            raise P07AVisibilityAuditError(f"missing or duplicate declaration: {entity}.{name}")
        row = matches[0]
        if expected["kind"] == "method":
            args = row.get("args")
            if not isinstance(args, list):
                raise P07AVisibilityAuditError(f"method args malformed: {entity}.{name}")
            actual_args = [_type_name(item) for item in args]
            actual = {"kind": "method", "args": actual_args,
                      "exposed": row.get("exposed"), "wire_id": row.get("wire_id")}
        else:
            actual = {"kind": "property", "type": _type_name(row.get("type")),
                      "flags": row.get("flags")}
        if actual != expected:
            raise P07AVisibilityAuditError(f"declaration shape differs: {entity}.{section}.{name}")
        found[(entity, section, name)] = actual
    if len(found) != 8:
        raise P07AVisibilityAuditError("visibility declaration count differs")
    return {f"{entity}.{section}.{name}": shape
            for (entity, section, name), shape in found.items()}


def _manifest(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise P07AVisibilityAuditError("source manifest must be a list")
    rows: dict[str, dict[str, Any]] = {}
    for row in value:
        if (not isinstance(row, dict) or set(row) != {"path", "sha256", "bytes"}
                or not isinstance(row["path"], str)
                or not isinstance(row["bytes"], int) or isinstance(row["bytes"], bool)
                or row["bytes"] < 0 or not isinstance(row["sha256"], str)
                or not SHA256.fullmatch(row["sha256"])):
            raise P07AVisibilityAuditError("source manifest row is malformed")
        if row["path"] in rows:
            raise P07AVisibilityAuditError(f"duplicate source manifest path: {row['path']}")
        rows[row["path"]] = row
    return rows


def _hash_copy(root: Path, copy_root: Path, relative: str,
               expected: tuple[int, str]) -> dict[str, Any]:
    raw, candidate, digest = _read(root, _bounded(root, copy_root, directory=True) / relative)
    if len(raw) != expected[0] or digest != expected[1]:
        raise P07AVisibilityAuditError(f"source hash mismatch: {candidate}")
    return {"path": relative, "bytes": len(raw), "sha256": digest}


def audit(*, root: str | Path, contracts: str | Path, sources: str | Path,
          original: str | Path, research: str | Path) -> dict[str, Any]:
    repository = Path(root).resolve()
    _bounded(repository, repository, directory=True)
    contracts_value, contracts_path, contracts_digest = _json(repository, contracts)
    sources_value, sources_path, sources_digest = _json(repository, sources)
    if contracts_digest != CONTRACTS_SHA256:
        raise P07AVisibilityAuditError("contracts receipt SHA differs")
    if sources_digest != SOURCES_SHA256:
        raise P07AVisibilityAuditError("sources receipt SHA differs")
    declarations = _audit_contracts(contracts_value)
    manifest = _manifest(sources_value)
    selected: dict[str, dict[str, Any]] = {}
    for relative, expected in SELECTED_SOURCES.items():
        row = manifest.get(relative)
        if row is None or row["bytes"] != expected[0] or row["sha256"] != expected[1]:
            raise P07AVisibilityAuditError(f"manifest entry differs: {relative}")
        selected[relative] = row
    original_root = _bounded(repository, original, directory=True)
    research_root = _bounded(repository, research, directory=True)
    copies = {"original": {}, "research": {}}
    for relative, expected in SELECTED_SOURCES.items():
        copies["original"][relative] = _hash_copy(repository, original_root, relative, expected)
        copies["research"][relative] = _hash_copy(repository, research_root, relative, expected)
    return {
        "status": "PASS_STATIC_VISIBILITY_SOURCE_AUDIT",
        "schema": "p07a-visibility-static-audit.v1",
        "build": "v.0.9.1 #717",
        "scope": "read-only P00/P01 contracts and source manifest; no runtime/client/service",
        "inputs": {
            "contracts": {"path": contracts_path.relative_to(repository).as_posix(), "sha256": contracts_digest},
            "sources": {"path": sources_path.relative_to(repository).as_posix(), "sha256": sources_digest},
        },
        "declaration_count": len(declarations),
        "declarations": declarations,
        "selected_manifest_rows": selected,
        "client_copies": copies,
        "wire_ids": "UNKNOWN",
        "serializer_order": "UNKNOWN",
        "native_visibility": "NOT_RUN",
        "interest_set_filtering": "NOT_RUN",
        "server_handoff": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--contracts", default="local/evidence/20261002-p00-p01/summary/contracts.json")
    parser.add_argument("--sources", default="local/evidence/20261002-p00-p01/summary/sources.json")
    parser.add_argument("--original", default="WoT_0.9.1_RU_0717_original")
    parser.add_argument("--research", default="WoT_0.9.1_RU_0717_research")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        report = audit(root=args.root, contracts=args.contracts, sources=args.sources,
                       original=args.original, research=args.research)
        if args.out:
            repository = Path(args.root).resolve()
            output = _bounded(repository, args.out, must_exist=False)
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 512 * 1024:
                raise P07AVisibilityAuditError("receipt exceeds bounds")
            output.write_bytes(raw + b"\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (P07AVisibilityAuditError, OSError) as error:
        raise SystemExit(f"P07A visibility static audit rejected: {error}")


if __name__ == "__main__":
    main()
