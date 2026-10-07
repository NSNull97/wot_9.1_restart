"""Bounded static audit for the P03I tree/queue evidence boundary.

The audit reads only hash-bound local evidence and the two permitted #717
client copies.  It validates the Account.def envelope, static queue constants,
the tree predicate receipt and capture-tool audit.  It does not launch a
client/service and does not decode or execute bytecode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


MAX_BYTES = 1024 * 1024
MAX_DEPTH = 24
MAX_ITEMS = 4096

QUEUE_SOURCES = {
    "client/gui/scaleform/daapi/view/lobby/header/fightbutton.pyc":
        "10582b200f622c2bad8623a5c04cc1c90adb28e6af80605efc5401f5c15a2b95",
    "client/gui/scaleform/daapi/view/meta/fightbuttonmeta.pyc":
        "025a38d92700bf721f440347215e5d3b46c75db1d64feab27e42a1e39c79e4df",
    "client/gui/prb_control/functional/random_queue.pyc":
        "29fbe5ffce02bc6919a204471a57bd047db80f3e9efa30df9b7bd8b45c327137",
    "client/gui/prb_control/functional/decorators.pyc":
        "5a78a91a19f75b653219654ea93e507f1f5e2b1ced6760d1bfe8a8026f559840",
    # This is the corrected hash.  The historical queue README contains a
    # one-character transcription error (…d46e0f2…); the audit reports it as
    # stale evidence instead of silently adopting the typo.
    "client/gui/shared/utils/functions.pyc":
        "dc7e27aacd46f0e2a3fa8b341554b95c2ef78fddfeaf427bc9663761d3a27d33",
    "client/gui/shared/gui_items/vehicle.pyc":
        "ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8",
    "client/Account.pyc":
        "bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef",
    "common/AccountCommands.pyc":
        "ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe",
    "common/streamids.pyc":
        "737bd163fbba40822e6c8e3493b39a62c944c7af320692c75889679cb4ce3f29",
    "res/scripts/entity_defs/Account.def":
        "883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674",
}

PREDICATE_SOURCES = {
    "res/scripts/client/gui/scaleform/daapi/view/lobby/techtree/data.pyc":
        "18aa479d8ca1168e441616fb73fc7ea6cad2faa138fb69ba933b1ab5b79a55f2",
    "res/scripts/client/gui/shared/gui_items/vehicle.pyc":
        "ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8",
    "res/scripts/client/gui/shared/utils/requesters/shoprequester.pyc":
        "8680e4bb6255b7e58abaa323b9fca7b4244f5749b9e40d97e3205a0a0b948375",
    "res/scripts/client/gui/scaleform/daapi/view/lobby/techtree/TechTree.pyc":
        "d3fca045cb1fd478a6eb306adfda08ce019795e926574ed943b31946f0dcfb42",
}

CAPTURE_AUDIT_SOURCES = {
    "tools/verify_unified_entry.py": "f9a29803a24db02b5144695de3ed4a7655cbca9b73ce8d065b45edc7b44513de",
    "tools/verify_hangar.py": "30d043e426313dcc8e001723df1020e58b5944f4c3463668f755a1c0321d6e24",
    "tools/verify_account_ready.py": "4a72c2d82c47259e50c72b1f81b605adf6452fcbc42ad420638826c696beddcd",
    "tools/verify_channel_capture.py": "075fe88a4e77ff5b328b06a16ed8ea65eb004f194610acee4c4343b9076131dc",
    "server/gateway/src/protocol/capture.rs": "b7f19afe2197f2001bc1a66295d8217ffe8b81d119bbfce242f6d7039d670efe",
    "server/gateway/src/drive/world.rs": "59c1c3cecab7fd4d6b469876cba45b1400a1aa10088c06c546e706ce2da2bafd",
    "local/evidence/20261005-p02-ms1-crew/data/next-hangar-gates/static-05/account-def-queue.json": "613e3c968306b3c2fbb890ebd7ea06a917f94a0daec4f366a2ea3882777656fd",
}


class P03IStaticAuditError(ValueError):
    """An input escaped its bound or violated the static contract."""


def _reject_constant(value: str) -> Any:
    raise P03IStaticAuditError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise P03IStaticAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _depth(value: Any, level: int = 0) -> None:
    if level > MAX_DEPTH:
        raise P03IStaticAuditError("JSON nesting exceeds bounds")
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS:
            raise P03IStaticAuditError("JSON object exceeds bounds")
        for key, child in value.items():
            if not isinstance(key, str):
                raise P03IStaticAuditError("JSON object key must be text")
            _depth(child, level + 1)
    elif isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise P03IStaticAuditError("JSON list exceeds bounds")
        for child in value:
            _depth(child, level + 1)


def _bounded(root: Path, path: str | Path, *, directory: bool = False,
             must_exist: bool = True) -> Path:
    root = root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    probe = candidate
    while probe != probe.parent:
        if probe.exists() and (probe.is_symlink() or getattr(probe, "is_junction", lambda: False)()):
            raise P03IStaticAuditError(f"path link is forbidden: {probe}")
        probe = probe.parent
    try:
        candidate = candidate.resolve(strict=must_exist)
        candidate.relative_to(root)
    except (OSError, ValueError) as error:
        raise P03IStaticAuditError(f"path escapes bound: {candidate}") from error
    if must_exist and directory and not candidate.is_dir():
        raise P03IStaticAuditError(f"directory required: {candidate}")
    if must_exist and not directory and not candidate.is_file():
        raise P03IStaticAuditError(f"file required: {candidate}")
    return candidate


def _read(root: Path, path: str | Path, maximum: int = MAX_BYTES) -> tuple[bytes, Path]:
    candidate = _bounded(root, path)
    try:
        info = candidate.stat()
        if info.st_size <= 0 or info.st_size > maximum:
            raise P03IStaticAuditError(f"file size outside bounds: {candidate}")
        raw = candidate.read_bytes()
    except OSError as error:
        raise P03IStaticAuditError(f"cannot read: {candidate}") from error
    if len(raw) != info.st_size:
        raise P03IStaticAuditError(f"file changed while reading: {candidate}")
    return raw, candidate


def _json(root: Path, path: str | Path) -> tuple[dict[str, Any], Path, str]:
    raw, candidate = _read(root, path)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except P03IStaticAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise P03IStaticAuditError(f"bounded UTF-8 JSON required: {candidate}") from error
    if not isinstance(value, dict):
        raise P03IStaticAuditError(f"JSON object required: {candidate}")
    _depth(value)
    return value, candidate, hashlib.sha256(raw).hexdigest()


def _hash(root: Path, source_root: Path, relative: str, expected: str) -> str:
    raw, candidate = _read(source_root, relative, MAX_BYTES)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise P03IStaticAuditError(f"source hash mismatch: {candidate}")
    return actual


def _queue_rows(root: Path, receipt: str | Path) -> dict[str, Any]:
    value, _, receipt_sha = _json(root, receipt)
    if set(value) != {"source", "sha256", "rows"}:
        raise P03IStaticAuditError("Account.def receipt keys differ")
    source = value["source"]
    if not isinstance(source, str) or not source.endswith("res\\scripts\\entity_defs\\Account.def"):
        raise P03IStaticAuditError("Account.def receipt source path")
    if value["sha256"] != QUEUE_SOURCES["res/scripts/entity_defs/Account.def"]:
        raise P03IStaticAuditError("Account.def receipt SHA differs")
    rows = value["rows"]
    if not isinstance(rows, list) or len(rows) != 11:
        raise P03IStaticAuditError("Account.def row count")
    observed: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "value"}:
            raise P03IStaticAuditError("Account.def row shape")
        path, item = row["path"], row["value"]
        if not isinstance(path, str) or path in observed or not isinstance(item, str):
            raise P03IStaticAuditError("Account.def row path/value")
        observed[path] = item
    expected = {
        "/ClientMethods[1]/onEnqueueFailure[1]": "",
        "/ClientMethods[1]/onEnqueueFailure[1]/Arg[1]": "UINT8",
        "/ClientMethods[1]/onEnqueueFailure[1]/Arg[2]": "UINT8",
        "/ClientMethods[1]/onEnqueueFailure[1]/Arg[3]": "STRING",
        "/BaseMethods[1]/doCmdInt3[1]": "",
        "/BaseMethods[1]/doCmdInt3[1]/Arg[1]": "INT16",
        "/BaseMethods[1]/doCmdInt3[1]/Arg[2]": "INT16",
        "/BaseMethods[1]/doCmdInt3[1]/Arg[3]": "INT64",
        "/BaseMethods[1]/doCmdInt3[1]/Arg[4]": "INT32",
        "/BaseMethods[1]/doCmdInt3[1]/Arg[5]": "INT32",
        "/BaseMethods[1]/doCmdInt3[1]/Exposed[1]": "",
    }
    if observed != expected:
        raise P03IStaticAuditError("Account.def queue schema differs")
    return {"receipt_sha256": receipt_sha, "row_count": len(rows), "schema": list(expected.values())}


def _readme(root: Path, path: str | Path) -> dict[str, Any]:
    raw, candidate = _read(root, path)
    text = raw.decode("utf-8")
    required = (
        "request ID is 202", "CMD_ENQUEUE_RANDOM=700", "INT16, INT16, INT64, INT32, INT32",
        "onEnqueueFailure(queueType,errorCode,errorStr)",
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise P03IStaticAuditError(f"queue README missing static claims: {missing}")
    documented: dict[str, str] = {}
    for path_name, hash_value in re.findall(r"^- `([^`]+)`: `([0-9a-f]{64})`$", text, re.MULTILINE):
        documented[path_name] = hash_value
    mismatches = []
    for path_name, expected in QUEUE_SOURCES.items():
        if path_name not in documented:
            continue
        if documented[path_name] != expected:
            mismatches.append({"path": path_name, "documented": documented[path_name], "actual": expected})
    return {"sha256": hashlib.sha256(raw).hexdigest(), "documented_source_rows": len(documented),
            "stale_hash_rows": mismatches, "status": "STALE_DOCUMENTED_HASH" if mismatches else "MATCH"}


def audit(*, root: str | Path, original: str | Path, research: str | Path,
          predicate: str | Path, queue_receipt: str | Path, queue_readme: str | Path,
          capture_audit: str | Path) -> dict[str, Any]:
    repository = Path(root).resolve()
    _bounded(repository, repository, directory=True)
    original_root = _bounded(repository, original, directory=True)
    research_root = _bounded(repository, research, directory=True)
    queue = _queue_rows(repository, queue_receipt)
    predicate_value, _, predicate_sha = _json(repository, predicate)
    if predicate_value.get("status") != "PASS_STATIC_PREDICATE" or predicate_value.get("build") != "v.0.9.1 #717":
        raise P03IStaticAuditError("predicate receipt status/build")
    predicate_rows = predicate_value.get("sources")
    if not isinstance(predicate_rows, list) or len(predicate_rows) != len(PREDICATE_SOURCES):
        raise P03IStaticAuditError("predicate source row count")
    predicate_hashes: dict[str, str] = {}
    for row in predicate_rows:
        if not isinstance(row, dict) or row.get("path") in predicate_hashes:
            raise P03IStaticAuditError("duplicate predicate source row")
        predicate_hashes[row.get("path")] = row.get("sha256")
    if predicate_hashes != PREDICATE_SOURCES:
        raise P03IStaticAuditError("predicate source rows differ")
    for source_path, expected in PREDICATE_SOURCES.items():
        _hash(repository, original_root, source_path, expected)
        _hash(repository, research_root, source_path, expected)
    queue_hashes = {}
    for source_path, expected in QUEUE_SOURCES.items():
        queue_hashes[source_path] = _hash(repository, original_root,
                                          "res/scripts/" + source_path if not source_path.startswith("res/") else source_path,
                                          expected)
        _hash(repository, research_root,
              "res/scripts/" + source_path if not source_path.startswith("res/") else source_path,
              expected)
    capture_value, _, capture_sha = _json(repository, capture_audit)
    if capture_value.get("status") != "PASS_READ_ONLY_CAPTURE_FORMAT_AUDIT" or capture_value.get("native_queue_handoff") != "NOT_RUN":
        raise P03IStaticAuditError("capture audit status/queue boundary")
    if capture_value.get("source_sha256") != CAPTURE_AUDIT_SOURCES:
        raise P03IStaticAuditError("capture audit source hashes differ")
    readme = _readme(repository, queue_readme)
    return {
        "status": "PASS_P03I_STATIC_SOURCE_RECHECK",
        "schema": "p03i-static-audit.v1",
        "queue": {"request_id": 202, "command": 700, "envelope": ["INT16", "INT16", "INT64", "INT32", "INT32"],
                  "account_def": queue},
        "predicate": {"status": predicate_value["status"], "receipt_sha256": predicate_sha,
                       "source_count": len(predicate_hashes), "native_payload": "NOT_RUN"},
        "queue_source_count": len(queue_hashes),
        "capture_audit": {"status": capture_value["status"], "receipt_sha256": capture_sha,
                          "native_queue_handoff": "NOT_RUN"},
        "queue_readme": readme,
        "native_client": "NOT_RUN",
        "gateway": "NOT_RUN",
        "deployed_service": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--original", default="WoT_0.9.1_RU_0717_original")
    parser.add_argument("--research", default="WoT_0.9.1_RU_0717_research")
    parser.add_argument("--predicate", default="local/evidence/20261007-native-tree-filter-01/predicate-01.json")
    parser.add_argument("--queue-receipt", default="local/evidence/20261005-p02-ms1-crew/data/next-hangar-gates/static-05/account-def-queue.json")
    parser.add_argument("--queue-readme", default="local/evidence/20261007-p03i-queue-research-08/README.md")
    parser.add_argument("--capture-audit", default="local/evidence/20261007-p03i-queue-capture-audit-01/audit.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        report = audit(root=args.root, original=args.original, research=args.research,
                       predicate=args.predicate, queue_receipt=args.queue_receipt,
                       queue_readme=args.queue_readme, capture_audit=args.capture_audit)
        if args.out:
            root = Path(args.root).resolve()
            output = _bounded(root, args.out, must_exist=False)
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 64 * 1024:
                raise P03IStaticAuditError("receipt exceeds bounds")
            output.write_bytes(raw + b"\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (P03IStaticAuditError, OSError) as error:
        raise SystemExit(f"p03i static audit rejected: {error}")


if __name__ == "__main__":
    main()
