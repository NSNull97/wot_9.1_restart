"""Audit the bounded static TechTree handoff without starting the client.

The #717 ``TechTree.pyc`` disassembly is evidence, not a wire decoder.  This
audit checks only the small method boundary that is needed before a native
research-tree capture: the Scaleform request populates available/selected
nation fields, while the native callback validates a nation name, selects its
index, loads the ``NationTreeData`` object and returns its dump.  It does not
claim an account payload, serializer, callback bytes or rendered visibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 24
MAX_ITEMS = 8192
TECHTREE_SHA256 = "d3fca045cb1fd478a6eb306adfda08ce019795e926574ed943b31946f0dcfb42"
EXPECTED_SOURCE = "scripts/client/gui/Scaleform/daapi/view/lobby/techtree/TechTree.py"


class TechTreeHandoffError(ValueError):
    """Input escaped its bound or does not match the pinned static boundary."""


def _reject_constant(value: str) -> Any:
    raise TechTreeHandoffError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise TechTreeHandoffError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _depth(value: Any, level: int = 0) -> None:
    if level > MAX_DEPTH:
        raise TechTreeHandoffError("JSON nesting exceeds bounds")
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS:
            raise TechTreeHandoffError("JSON object exceeds bounds")
        for key, child in value.items():
            if not isinstance(key, str):
                raise TechTreeHandoffError("JSON object key must be text")
            _depth(child, level + 1)
    elif isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise TechTreeHandoffError("JSON list exceeds bounds")
        for child in value:
            _depth(child, level + 1)


def _bounded(root: Path, path: str | Path, *, must_exist: bool = True) -> Path:
    root = root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    probe = candidate
    while probe != probe.parent:
        if probe.exists() and (probe.is_symlink() or getattr(probe, "is_junction", lambda: False)()):
            raise TechTreeHandoffError(f"path link is forbidden: {probe}")
        probe = probe.parent
    try:
        candidate = candidate.resolve(strict=must_exist)
        candidate.relative_to(root)
    except (OSError, ValueError) as error:
        raise TechTreeHandoffError(f"path escapes bound: {candidate}") from error
    if must_exist and not candidate.is_file():
        raise TechTreeHandoffError(f"file required: {candidate}")
    return candidate


def _read_json(root: Path, path: str | Path) -> tuple[dict[str, Any], Path, str]:
    candidate = _bounded(root, path)
    info = candidate.stat()
    if info.st_size <= 0 or info.st_size > MAX_BYTES:
        raise TechTreeHandoffError("JSON size is outside bounds")
    raw = candidate.read_bytes()
    if len(raw) != info.st_size:
        raise TechTreeHandoffError("JSON changed while reading")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except TechTreeHandoffError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise TechTreeHandoffError("bounded UTF-8 JSON required") from error
    if not isinstance(value, list):
        raise TechTreeHandoffError("disassembly root must be a list")
    _depth(value)
    return {str(index): item for index, item in enumerate(value)}, candidate, hashlib.sha256(raw).hexdigest()


def _record(records: dict[str, Any], name: str) -> dict[str, Any]:
    for item in records.values():
        if isinstance(item, dict) and item.get("qualified_name") == name:
            return item
    raise TechTreeHandoffError(f"missing disassembly record: {name}")


def _pairs(record: dict[str, Any]) -> list[tuple[str, Any]]:
    result: list[tuple[str, Any]] = []
    for item in record.get("instructions", []):
        if not isinstance(item, dict) or not isinstance(item.get("opname"), str):
            raise TechTreeHandoffError("instruction record is malformed")
        result.append((item["opname"], item.get("value")))
    return result


def _contains(sequence: list[tuple[str, Any]], expected: list[tuple[str, Any]]) -> bool:
    cursor = 0
    for item in sequence:
        if cursor < len(expected) and item == expected[cursor]:
            cursor += 1
    return cursor == len(expected)


def _method_shape(records: dict[str, Any]) -> dict[str, Any]:
    request = _record(records, "<module>.TechTree.requestNationTreeData")
    get_data = _record(records, "<module>.TechTree.getNationTreeData")
    if request.get("source_filename") != EXPECTED_SOURCE or get_data.get("source_filename") != EXPECTED_SOURCE:
        raise TechTreeHandoffError("TechTree source filename differs")

    request_ins = _pairs(request)
    if request.get("varnames") != ["self"]:
        raise TechTreeHandoffError("requestNationTreeData signature differs")
    request_available = [
        ("LOAD_FAST", "self"), ("LOAD_ATTR", "as_setAvailableNationsS"),
        ("LOAD_GLOBAL", "g_techTreeDP"), ("LOAD_ATTR", "getAvailableNations"),
        ("CALL_FUNCTION", None), ("CALL_FUNCTION", None),
    ]
    request_selected = [
        ("LOAD_FAST", "self"), ("LOAD_ATTR", "as_setSelectedNationS"),
        ("LOAD_GLOBAL", "SelectedNation"), ("LOAD_ATTR", "getName"),
        ("CALL_FUNCTION", None), ("CALL_FUNCTION", None),
    ]
    if not _contains(request_ins, request_available) or not _contains(request_ins, request_selected):
        raise TechTreeHandoffError("requestNationTreeData field population shape differs")
    if ("LOAD_GLOBAL", "True") not in request_ins or ("RETURN_VALUE", None) not in request_ins:
        raise TechTreeHandoffError("requestNationTreeData success return is not pinned")

    get_ins = _pairs(get_data)
    if get_data.get("varnames") != ["self", "nationName", "nationIdx"]:
        raise TechTreeHandoffError("getNationTreeData signature differs")
    if "Nation not found" not in get_data.get("constants", []):
        raise TechTreeHandoffError("invalid-nation error string is missing")
    get_required = [
        ("LOAD_GLOBAL", "nations"), ("LOAD_ATTR", "INDICES"),
        ("COMPARE_OP", None), ("POP_JUMP_IF_FALSE", None),
        ("LOAD_GLOBAL", "LOG_ERROR"), ("LOAD_CONST", "Nation not found"),
        ("LOAD_FAST", "nationName"), ("CALL_FUNCTION", None),
        ("BUILD_MAP", None), ("RETURN_VALUE", None),
    ]
    if not _contains(get_ins, get_required):
        raise TechTreeHandoffError("invalid-nation guard shape differs")
    valid_flow = [
        ("LOAD_GLOBAL", "nations"), ("LOAD_ATTR", "INDICES"),
        ("LOAD_FAST", "nationName"), ("BINARY_SUBSCR", None),
        ("STORE_FAST", "nationIdx"), ("LOAD_GLOBAL", "SelectedNation"),
        ("LOAD_ATTR", "select"), ("LOAD_FAST", "nationIdx"),
        ("CALL_FUNCTION", None), ("LOAD_FAST", "self"), ("LOAD_ATTR", "_data"),
        ("LOAD_ATTR", "load"), ("LOAD_FAST", "nationIdx"), ("CALL_FUNCTION", None),
        ("LOAD_FAST", "self"), ("LOAD_ATTR", "_data"), ("LOAD_ATTR", "dump"),
        ("CALL_FUNCTION", None), ("RETURN_VALUE", None),
    ]
    if not _contains(get_ins, valid_flow):
        raise TechTreeHandoffError("valid nation load/dump flow differs")
    return {
        "requestNationTreeData": {
            "sets_available_nations": True,
            "sets_selected_nation": True,
            "returns_success": True,
        },
        "getNationTreeData": {
            "rejects_unknown_nation": True,
            "selects_nation_index": True,
            "loads_nation_data": True,
            "returns_data_dump": True,
        },
    }


def audit(*, root: str | Path, disassembly: str | Path) -> dict[str, Any]:
    repository = Path(root).resolve()
    data, source, receipt_sha256 = _read_json(repository, disassembly)
    records = list(data.values())
    if len(records) < 2:
        raise TechTreeHandoffError("disassembly contains too few records")
    actual_source_hash = None
    source_filename = None
    for item in records:
        if isinstance(item, dict) and item.get("qualified_name") == "<module>.TechTree.requestNationTreeData":
            source_filename = item.get("source_filename")
            break
    if source_filename != EXPECTED_SOURCE:
        raise TechTreeHandoffError("TechTree source filename differs")
    # The JSON is generated from the hash-pinned research copy.  Bind its
    # recorded source to the independently checked #717 SHA; no bytecode is
    # executed here.
    source_relative = "res/scripts/client/gui/scaleform/daapi/view/lobby/techtree/TechTree.pyc"
    copy_hashes: dict[str, str] = {}
    for copy_name in ("original", "research"):
        source_path = _bounded(repository, f"WoT_0.9.1_RU_0717_{copy_name}/{source_relative}")
        raw = source_path.read_bytes()
        copy_hashes[copy_name] = hashlib.sha256(raw).hexdigest()
        if copy_hashes[copy_name] != TECHTREE_SHA256:
            raise TechTreeHandoffError(f"{copy_name} TechTree.pyc SHA differs")
    actual_source_hash = copy_hashes["research"]
    shape = _method_shape(data)
    return {
        "status": "PASS_STATIC_TECHTREE_HANDOFF_SOURCE",
        "schema": "p09a-techtree-handoff-static.v1",
        "build": "v.0.9.1 #717",
        "source": str(source),
        "disassembly_sha256": receipt_sha256,
        "source_relative": source_relative,
        "source_copies": copy_hashes,
        "source_sha256": actual_source_hash,
        "methods": shape,
        "native_account_payload": "NOT_RUN",
        "native_callback_bytes": "NOT_RUN",
        "native_tree_screenshot": "NOT_RUN",
        "server_handoff": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--disassembly", default="local/evidence/20261007-native-tree-filter-01/bytecode/client__gui__scaleform__daapi__view__lobby__techtree__techtree.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        report = audit(root=args.root, disassembly=args.disassembly)
        if args.out:
            output = _bounded(Path(args.root).resolve(), args.out, must_exist=False)
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 64 * 1024:
                raise TechTreeHandoffError("receipt exceeds bounds")
            output.write_bytes(raw + b"\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (TechTreeHandoffError, OSError) as error:
        raise SystemExit(f"techtree handoff audit rejected: {error}")


if __name__ == "__main__":
    main()
