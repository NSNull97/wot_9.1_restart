"""Bounded, read-only recheck of the #717 P06E collision-source boundary.

This verifier hashes the already accepted bytecode receipt and its summary.  It
does not execute client bytecode and it deliberately measures only the eight
collision/flight methods listed below.  The eighth method,
``collideDynamicAndStatic``, is the missing wrapper that joins the dynamic and
static paths; measuring it closes the static call-chain shape without claiming
that either path is a server-authoritative solver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

SCHEMA = "p06e-client-collision-static-audit.v1"
SUMMARY_SCHEMA = "p06e-client-collision-source.v1"
EXPECTED_BYTECODE_SHA256 = "502581a94b4be46d4db885e5922038287b38ff155138cc37ebc24e2216ce7625"
EXPECTED_SUMMARY_SHA256 = "61ddf923d1b276176fe8b346590228cd00ab51acefc5f1bce94eb968ec364839"
MAX_BYTES = 32 * 1024 * 1024
MAX_DEPTH = 12
MAX_ITEMS = 500000
MAX_KEY = 256

EXPECTED_METHODS = {
    "<module>._readShell": "5f837cbeb6fb4a8893defc925702ad11f3149f9fcb3f53925c092288e461ee94",
    "<module>._readShot": "f237ee10ca5ca47d30ed4a2a226420c5eb526f9220feb6db3e5110c851dfdecf",
    "<module>.ProjectileMover.__notifyProjectileHit": "3421f31defe71c3a808815dfbaa0bb69cbe89fa90c5c8f52f4366b268c79f2e7",
    "<module>.VehicleDescr.getHitTesters": "a2d7e6bf439e5dbfa84859631e723323f47ed423055334badfbd138ec062aaac",
    "<module>.collideEntities": "eb774b0d2bf19fe2ecf1d1dbba0c9a36e187803fddcb71b5ca201238aa9432f7",
    "<module>.collideVehiclesAndStaticScene": "d2c1272f84da96caf36fde70a1743bda94762de9fab1c0f05aed154e910e8446",
    "<module>.getCollidableEntities": "8323a0c1f479f67a97fbbce4de8d2030740d6229370eff14e6fc7c6d70b19f38",
    "<module>.collideDynamicAndStatic": "09d3f74a4e55ecec0dddd7366929e13fcbbf0cb6bee32654ef490b762514c915",
}
SUMMARY_METHODS = set(EXPECTED_METHODS) - {"<module>.collideDynamicAndStatic"}


class AuditError(ValueError):
    """Malformed, unsafe or non-pinned evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def _reject_constant(value: str) -> Any:
    raise AuditError(f"non-finite JSON constant: {value}")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _walk(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    count = [0] if count is None else count
    _require(depth <= MAX_DEPTH, "JSON depth exceeds bound")
    count[0] += 1
    _require(count[0] <= MAX_ITEMS, "JSON item count exceeds bound")
    if isinstance(value, dict):
        for key, child in value.items():
            _require(isinstance(key, str) and len(key) <= MAX_KEY, "JSON key too long")
            _walk(child, depth + 1, count)
    elif isinstance(value, list):
        for child in value:
            _walk(child, depth + 1, count)


def parse_json(data: bytes) -> Any:
    _require(0 < len(data) <= MAX_BYTES, "JSON bytes outside bound")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise AuditError("bounded UTF-8 JSON required") from error
    _walk(value)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside_repo(path: Path, root: Path) -> None:
    try:
        path.relative_to(root)
    except ValueError as error:
        raise AuditError("evidence path escapes repository") from error


def _regular(path: Path, root: Path, label: str) -> None:
    raw = path.absolute()
    _require(not any(parent.is_symlink() for parent in (raw, *raw.parents)),
             "symlink evidence path is not allowed")
    canonical = raw.resolve(strict=False)
    _inside_repo(canonical, root)
    _require(canonical.is_file() and not canonical.is_symlink(),
             f"{label} must be a regular file")


def _method_hash(entry: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(entry, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def audit(bytecode_path: str | Path, summary_path: str | Path,
          *, root: str | Path | None = None) -> dict[str, Any]:
    repo = Path(root or Path(__file__).resolve().parents[1]).resolve()
    bytecode = Path(bytecode_path)
    summary = Path(summary_path)
    _regular(bytecode, repo, "bytecode")
    _regular(summary, repo, "summary")
    bytecode_bytes = bytecode.read_bytes()
    summary_bytes = summary.read_bytes()
    _require(hashlib.sha256(bytecode_bytes).hexdigest() == EXPECTED_BYTECODE_SHA256,
             "bytecode SHA-256 does not match #717 pin")
    _require(hashlib.sha256(summary_bytes).hexdigest() == EXPECTED_SUMMARY_SHA256,
             "summary SHA-256 does not match accepted P06E pin")
    source = parse_json(bytecode_bytes)
    pinned = parse_json(summary_bytes)
    _require(isinstance(source, list), "bytecode receipt list required")
    _require(isinstance(pinned, dict), "summary object required")
    _require(pinned.get("schema") == SUMMARY_SCHEMA, "summary schema mismatch")
    _require(pinned.get("bytecode_sha256") == EXPECTED_BYTECODE_SHA256,
             "summary bytecode SHA mismatch")
    methods = pinned.get("methods")
    _require(isinstance(methods, dict) and set(methods) == SUMMARY_METHODS,
             "summary must contain the seven original method pins")
    _require(all(methods[name] == EXPECTED_METHODS[name] for name in SUMMARY_METHODS),
             "summary method pin mismatch")
    entries = {}
    for entry in source:
        _require(isinstance(entry, dict), "bytecode entry must be an object")
        name = entry.get("qualified_name")
        if name in EXPECTED_METHODS:
            _require(name not in entries, "duplicate measured method entry")
            entries[name] = entry
    _require(set(entries) == set(EXPECTED_METHODS), "exactly eight measured methods required")
    measured = {name: _method_hash(entries[name]) for name in EXPECTED_METHODS}
    _require(measured == EXPECTED_METHODS, "measured method hash mismatch")
    _require(entries["<module>.collideDynamicAndStatic"].get("source_filename")
             == "scripts/client/ProjectileMover.py", "dynamic/static wrapper source mismatch")
    return {
        "schema": SCHEMA,
        "status": "PASS_STATIC_CLIENT_COLLISION_BOUNDARY_RECHECK",
        "native_server_hit_status": "NOT_RUN",
        "bytecode_sha256": EXPECTED_BYTECODE_SHA256,
        "summary_sha256": EXPECTED_SUMMARY_SHA256,
        "summary_method_count": len(SUMMARY_METHODS),
        "measured_method_count": len(measured),
        "measured_methods": measured,
        "dynamic_static_wrapper": "<module>.collideDynamicAndStatic",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bytecode", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit(args.bytecode, args.summary, root=args.root)
        if args.out:
            repository = Path(args.root or Path(__file__).resolve().parents[1]).resolve()
            target = Path(args.out)
            _regular(target, repository, "output") if target.exists() else _inside_repo(
                target.absolute().resolve(strict=False), repository)
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(result, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
            _require(len(raw) <= 512 * 1024, "audit receipt exceeds bound")
            target.write_bytes(raw + b"\n")
    except (OSError, AuditError) as error:
        print(json.dumps({"status": "FAIL_INVALID_EVIDENCE", "reason": str(error)},
                         ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
