"""Audit the bounded #717 training-room contract without running the client.

This verifier reads only the already exported P00/P01 entity-definition JSON
and the hash-bound source manifest.  It checks names and primitive shapes for
the small P10A preparation boundary, plus source presence and exact hashes for
the documented training-room modules.  It deliberately does not assign wire
IDs, infer call order, decode ``PYTHON`` payloads, or start a native client or
server.
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

ACCOUNT_BASE = {
    "createTraining": (["INT32", "INT32", "BOOL", "STRING"], True),
    "createDevPrebattle": (["INT8", "INT32", "INT32", "STRING"], True),
    "sendPrebattleInvites": (["ARRAY<INT64>", "STRING"], True),
    "receivePrebattleRoster": (["OBJECT_ID", "PYTHON"], False),
    "updatePrebattle": (["OBJECT_ID", "UINT8", "STRING"], False),
    "onPrebattleResponse": (["OBJECT_ID", "INT16", "BOOL", "STRING", "INT32"], False),
    "onPrebattleVehicleChanged": (["OBJECT_ID", "INT32", "INT32"], False),
}

ACCOUNT_CLIENT = {
    "onPrebattleJoined": (["OBJECT_ID"], False),
    "onPrebattleJoinFailure": (["UINT8"], False),
    "onPrebattleLeft": ([], False),
    "onKickedFromPrebattle": (["UINT8"], False),
    "updatePrebattle": (["UINT8", "STRING"], False),
}

PREBATTLE_BASE = {
    "onArenaCreated": (["MAILBOX", "UINT64", "OBJECT_ID", "UINT8", "INT32", "UINT8"], False),
    "onArenaFinished": (["OBJECT_ID", "UINT64", "PREBATTLE_RESULTS"], False),
    "addPlayer": (["MAILBOX", "STRING", "DB_ID", "UINT8", "STRING", "DB_ID", "STRING", "UINT32"], False),
    "removePlayer": (["INT32", "OBJECT_ID"], False),
    "setPlayerNotReady": (["INT32", "OBJECT_ID", "UINT16", "BOOL"], False),
    "setPlayerReady": (["INT32", "OBJECT_ID", "INT32", "STRING", "ARRAY<INT32>", "ARRAY<INT32>"], False),
    "setPlayerOnline": (["OBJECT_ID", "BOOL"], False),
    "updatePlayerInfo": (["OBJECT_ID", "UINT8", "DB_ID", "STRING"], False),
    "kickPlayer": (["MAILBOX", "INT32", "OBJECT_ID"], False),
    "changePlayerRoster": (["MAILBOX", "INT32", "OBJECT_ID", "UINT8"], False),
    "swapTeams": (["MAILBOX", "INT32"], False),
    "changeArenaType": (["MAILBOX", "INT32", "INT32"], False),
    "changeRoundLength": (["MAILBOX", "INT32", "INT32"], False),
    "changeOpenStatus": (["MAILBOX", "INT32", "BOOL"], False),
    "changeComment": (["MAILBOX", "INT32", "STRING"], False),
    "changeArenaVoip": (["MAILBOX", "INT32", "UINT8"], False),
    "changeCompanyDivision": (["MAILBOX", "INT32", "INT8"], False),
    "changeGameplaysMask": (["MAILBOX", "INT32", "INT32"], False),
    "setTeamReady": (["MAILBOX", "INT32", "UINT8", "BOOL"], False),
    "setTeamNotReady": (["MAILBOX", "INT32", "UINT8"], False),
    "smartDestroy": (["UINT8"], False),
}

# P10A's source-presence claims are taken from the pinned P00/P01 manifest.
MANIFEST_ENTRIES = {
    "res/scripts/client/clientprebattle.pyc": (6155, "c74fc3070d15fb7099e2fba95f955483b09df174596d9f6d118db0956ab9decb"),
    "res/scripts/client/clientunitmgr.pyc": (15046, "c4c50ee6a462f7988ad1f8d5d9ae2a6f9238feb08994b0d0b00119d19cdd7edc"),
    "res/scripts/client/gui/scaleform/daapi/view/lobby/trainings/trainingroom.pyc": (18298, "a0647da875489f330281d614d24cddc9d8c08b79245e0064c47fd2b4a57f3970"),
    "res/scripts/client/gui/scaleform/daapi/view/lobby/prb_windows/prebattlewindow.pyc": (14517, "9586fa2ff766436b9699f9700ab330b538ae2113a8937a7d5ce3df6625d1bfc1"),
    "res/scripts/client/gui/scaleform/daapi/view/lobby/prb_windows/prbsendinviteswindow.pyc": (6136, "8d88a4f44444eac982ca59464dfa61ded1fb36007d7a5e078d0aa4e0fc3407dc"),
    "res/scripts/client/gui/scaleform/daapi/view/meta/receivedinvitewindowmeta.pyc": (1648, "371115c2d59d2aaf9c4165599904abd6416e9df6138e6fe93863547391320558"),
    "res/scripts/entity_defs/account.def": (10588, "883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674"),
    "res/scripts/entity_defs/prebattle.def": (1920, "115d555f1d13aa720c8ed4ee2240ef704788695614f1bd51671ae11c4e8a9dd8"),
    "res/scripts/entity_defs/unitmgr.def": (1581, "cb3b15a69f940981bf8676d914eb34a747ed46322659a0fcb91c219c3979ddc1"),
}


class TrainingRoomAuditError(ValueError):
    """Input escaped a bound or differs from the pinned static contract."""


def _reject_constant(value: str) -> Any:
    raise TrainingRoomAuditError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrainingRoomAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _check_bounds(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    if count is None:
        count = [0]
    count[0] += 1
    if depth > MAX_DEPTH or count[0] > MAX_ITEMS:
        raise TrainingRoomAuditError("JSON depth or item bound exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TrainingRoomAuditError("JSON object key must be text")
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
            raise TrainingRoomAuditError(f"path link is forbidden: {probe}")
        probe = probe.parent
    try:
        candidate = candidate.resolve(strict=must_exist)
        candidate.relative_to(root)
    except (OSError, ValueError) as error:
        raise TrainingRoomAuditError(f"path escapes bound: {candidate}") from error
    if must_exist and not candidate.is_file():
        raise TrainingRoomAuditError(f"file required: {candidate}")
    return candidate


def _read_json(root: Path, path: str | Path) -> tuple[Any, Path, str]:
    candidate = _bounded(root, path)
    info = candidate.stat()
    if not 0 < info.st_size <= MAX_BYTES:
        raise TrainingRoomAuditError("JSON size outside bounds")
    raw = candidate.read_bytes()
    if len(raw) != info.st_size:
        raise TrainingRoomAuditError("JSON changed while reading")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except TrainingRoomAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise TrainingRoomAuditError("bounded UTF-8 JSON required") from error
    _check_bounds(value)
    return value, candidate, hashlib.sha256(raw).hexdigest()


def _children(node: dict[str, Any], *, allow_empty: bool = False) -> list[dict[str, Any]]:
    data = node.get("data")
    if allow_empty and data == "":
        return []
    if not isinstance(data, dict) or not isinstance(data.get("children"), list):
        raise TrainingRoomAuditError("definition node children are malformed")
    children = data["children"]
    if not all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in children):
        raise TrainingRoomAuditError("definition child is malformed")
    return children


def _find_named(root: Any, name: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    pending = [root]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if item.get("name") == name:
                found.append(item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return found


def _type_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        raise TrainingRoomAuditError("type node is malformed")
    if set(value) == {"base64"} and isinstance(value["base64"], str):
        return value["base64"]
    if value.get("value") == "ARRAY" and isinstance(value.get("children"), list):
        children = value["children"]
        if len(children) != 1 or children[0].get("name") != "of":
            raise TrainingRoomAuditError("array type shape differs")
        return f"ARRAY<{_type_name(children[0].get('data'))}>"
    raise TrainingRoomAuditError("unsupported type shape")


def _section(definition: Any, name: str) -> dict[str, Any]:
    matches = _find_named(definition, name)
    if len(matches) != 1:
        raise TrainingRoomAuditError(f"missing or duplicate section: {name}")
    return matches[0]


def _method_shapes(definition: Any, section_name: str,
                   expected: dict[str, tuple[list[str], bool]]) -> dict[str, Any]:
    section = _section(definition, section_name)
    rows = _children(section)
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row["name"]
        if name in by_name:
            raise TrainingRoomAuditError(f"duplicate method in {section_name}: {name}")
        by_name[name] = row
    result: dict[str, Any] = {}
    for name, (types, exposed) in expected.items():
        row = by_name.get(name)
        if row is None:
            raise TrainingRoomAuditError(f"missing method in {section_name}: {name}")
        children = _children(row, allow_empty=True)
        actual_types = [_type_name(child.get("data")) for child in children if child.get("name") == "Arg"]
        actual_exposed = sum(child.get("name") == "Exposed" for child in children)
        if actual_types != types or actual_exposed != int(exposed):
            raise TrainingRoomAuditError(f"shape differs: {section_name}.{name}")
        result[name] = {"args": actual_types, "exposed": bool(actual_exposed), "wire_id": "UNKNOWN"}
    return result


def _manifest_entries(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise TrainingRoomAuditError("source manifest must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in value:
        if (not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}
                or not isinstance(row["path"], str) or not isinstance(row["bytes"], int)
                or isinstance(row["bytes"], bool) or row["bytes"] < 0
                or not isinstance(row["sha256"], str) or not SHA256.fullmatch(row["sha256"])):
            raise TrainingRoomAuditError("source manifest row is malformed")
        if row["path"] in result:
            raise TrainingRoomAuditError(f"duplicate source manifest path: {row['path']}")
        result[row["path"]] = row
    return result


def audit(*, root: str | Path, account_def: str | Path,
          prebattle_def: str | Path, manifest: str | Path) -> dict[str, Any]:
    repository = Path(root).resolve()
    account, account_path, account_sha = _read_json(repository, account_def)
    prebattle, prebattle_path, prebattle_sha = _read_json(repository, prebattle_def)
    manifest_value, manifest_path, manifest_sha = _read_json(repository, manifest)
    entries = _manifest_entries(manifest_value)
    selected: dict[str, dict[str, Any]] = {}
    for path, (size, digest) in MANIFEST_ENTRIES.items():
        row = entries.get(path)
        if row is None or row["bytes"] != size or row["sha256"] != digest:
            raise TrainingRoomAuditError(f"manifest entry differs: {path}")
        selected[path] = row
    return {
        "status": "PASS_STATIC_TRAINING_ROOM_CONTRACT",
        "schema": "p10a-training-room-static-audit.v1",
        "build": "v.0.9.1 #717",
        "inputs": {
            "account_def": {"path": account_path.relative_to(repository).as_posix(), "sha256": account_sha},
            "prebattle_def": {"path": prebattle_path.relative_to(repository).as_posix(), "sha256": prebattle_sha},
            "manifest": {"path": manifest_path.relative_to(repository).as_posix(), "sha256": manifest_sha},
        },
        "account": {
            "base_methods": _method_shapes(account, "BaseMethods", ACCOUNT_BASE),
            "client_methods": _method_shapes(account, "ClientMethods", ACCOUNT_CLIENT),
        },
        "prebattle": {"base_methods": _method_shapes(prebattle, "BaseMethods", PREBATTLE_BASE)},
        "source_presence": selected,
        "native_wire_ids": "UNKNOWN",
        "native_request_bytes": "NOT_RUN",
        "native_callback_order": "NOT_RUN",
        "room_isolation": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--account-def", default="local/evidence/20261002-p00-p01/decoded/res__scripts__entity_defs__account.def.json")
    parser.add_argument("--prebattle-def", default="local/evidence/20261002-p00-p01/decoded/res__scripts__entity_defs__prebattle.def.json")
    parser.add_argument("--manifest", default="local/evidence/20261002-p00-p01/baseline/original-content-manifest.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        report = audit(root=args.root, account_def=args.account_def,
                       prebattle_def=args.prebattle_def, manifest=args.manifest)
        if args.out:
            output = _bounded(Path(args.root).resolve(), args.out, must_exist=False)
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 256 * 1024:
                raise TrainingRoomAuditError("receipt exceeds bounds")
            output.write_bytes(raw + b"\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (TrainingRoomAuditError, OSError) as error:
        raise SystemExit(f"training-room static audit rejected: {error}")


if __name__ == "__main__":
    main()
