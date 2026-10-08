"""Bound the static #717 NationObjDumper UI output without executing bytecode.

The receipt describes instruction facts, not an account wire serializer, native
payload, type schema or rendered research tree. Only existing local evidence and
the two permitted client source copies are read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 24
MAX_ITEMS = 100000
MAX_RECORDS = 256
MAX_INSTRUCTIONS = 8192
SOURCE_SHA256 = "09d86ed36847190f41719e95651b43852bdeba10ffeb1430917669ac3e20c8fc"
DISASSEMBLY_SHA256 = "313253c1004396567c2c79cf3cfd8fe5e431683b881a31fa694d3b8c59782a7d"
SOURCE_RELATIVE = "res/scripts/client/gui/scaleform/daapi/view/lobby/techtree/dumpers.pyc"
EXPECTED_SOURCE = "scripts/client/gui/Scaleform/daapi/view/lobby/techtree/dumpers.py"
DEFAULT_DISASSEMBLY = (
    "local/evidence/20261007-native-tree-filter-01/bytecode/"
    "client__gui__scaleform__daapi__view__lobby__techtree__dumpers.json"
)
PREFIX = "<module>.NationObjDumper."
XML_PREFIX = "<module>.NationXMLDumper."
ARG_OPS = {"BUILD_MAP", "BUILD_LIST", "BUILD_TUPLE", "CALL_FUNCTION",
           "UNPACK_SEQUENCE", "COMPARE_OP", "MAKE_CLOSURE"}

NATION_XML_CONSTANTS = (
    '<?xml version="1.0" encoding="utf-8"?><tree><nodes>{0:>s}</nodes><scrollIndex>{1:d}</scrollIndex></tree>',
    '<node><id>{id:d}</id><nameString>{nameString:>s}</nameString><class><name>{primaryClass[name]:>s}</name><userString>{primaryClass[userString]:>s}</userString></class><level>{level:d}</level><earnedXP>{earnedXP:d}</earnedXP><state>{state:d}</state><unlockProps><parentID>{unlockProps[0]:d}</parentID><unlockIdx>{unlockProps[1]:d}</unlockIdx><xpCost>{unlockProps[2]:n}</xpCost><topIDs>{unlockProps[3]:>s}</topIDs></unlockProps><iconPath>{iconPath:>s}</iconPath><smallIconPath><![CDATA[{smallIconPath:>s}]]></smallIconPath><longName>{longName:>s}</longName><shopPrice><credits>{shopPrice[0]:n}</credits><gold>{shopPrice[1]:n}</gold></shopPrice><display>{displayInfo:>s}</display></node>',
    '<row>{row:d}</row><column>{column:d}</column><position><x>{position[0]:n}</x><y>{position[1]:n}</y></position><lines>{lines:>s}</lines>',
    '<set><outLiteral>{0:>s}</outLiteral><outPin><x>{1[0]:n}</x><y>{1[1]:n}</y></outPin><inPins>{2:>s}</inPins></set>',
    '<item><childID>{childID:d}</childID><inPin><x>{inPin[0]:n}</x><y>{inPin[1]:n}</y></inPin><viaPins>{dump:>s}</viaPins></item>',
    '<pin><x>{0[0]:n}</x><y>{0[1]:n}</y></pin>',
    '<id>{0:d}</id>',
)
NATION_XML_NAMES = (
    "_NationXMLDumper__xmlBody", "_NationXMLDumper__nodeFormat",
    "_NationXMLDumper__displayInfoFormat", "_NationXMLDumper__setFormat",
    "_NationXMLDumper__inPinFormat", "_NationXMLDumper__viaPinFormat",
    "_NationXMLDumper__topIDFormat",
)


class NationDumperAuditError(ValueError):
    """Evidence escaped a bound or differs from the measured static shape."""


def _reject_constant(value: str) -> Any:
    raise NationDumperAuditError(f"non-finite JSON constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NationDumperAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(raw: bytes) -> list[dict[str, Any]]:
    """Read bounded disassembly data; never marshal/import/execute client code."""
    if not raw or len(raw) > MAX_BYTES:
        raise NationDumperAuditError("JSON size outside bounds")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
    except NationDumperAuditError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise NationDumperAuditError("bounded UTF-8 JSON required") from error
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_ITEMS:
            raise NationDumperAuditError("JSON depth or total item bound exceeded")
        if isinstance(item, float) and not math.isfinite(item):
            raise NationDumperAuditError("non-finite JSON number")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_RECORDS:
        raise NationDumperAuditError("disassembly record count outside bounds")
    if not all(isinstance(item, dict) for item in value):
        raise NationDumperAuditError("disassembly records must be objects")
    return value


def _bounded(root: Path, path: str | Path, *, must_exist: bool = True) -> Path:
    root = root.resolve(strict=True)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    probe = candidate
    while probe != probe.parent:
        if probe.exists() and (probe.is_symlink() or getattr(probe, "is_junction", lambda: False)()):
            raise NationDumperAuditError(f"path link is forbidden: {probe}")
        probe = probe.parent
    try:
        candidate = candidate.resolve(strict=must_exist)
        candidate.relative_to(root)
    except (OSError, ValueError) as error:
        raise NationDumperAuditError(f"path escapes bound: {candidate}") from error
    if must_exist and not candidate.is_file():
        raise NationDumperAuditError("input must be a file")
    return candidate


def _read(root: Path, path: str | Path, limit: int = MAX_BYTES) -> tuple[Path, bytes]:
    candidate = _bounded(root, path)
    size = candidate.stat().st_size
    if not 0 < size <= limit:
        raise NationDumperAuditError("input size outside bounds")
    raw = candidate.read_bytes()
    if len(raw) != size:
        raise NationDumperAuditError("input changed while reading")
    return candidate, raw


def _method(records: list[dict[str, Any]], suffix: str,
            varnames: list[str], *, prefix: str = PREFIX) -> list[tuple[str, Any]]:
    matches = [row for row in records if row.get("qualified_name") == prefix + suffix]
    if len(matches) != 1:
        raise NationDumperAuditError(f"missing or duplicate method: {suffix}")
    row = matches[0]
    if row.get("source_filename") != EXPECTED_SOURCE or row.get("varnames") != varnames:
        raise NationDumperAuditError(f"source/signature differs: {suffix}")
    instructions = row.get("instructions")
    constants, names = row.get("constants"), row.get("names")
    if (not isinstance(instructions, list) or not 1 <= len(instructions) <= MAX_INSTRUCTIONS
            or not isinstance(constants, list) or not isinstance(names, list)):
        raise NationDumperAuditError("instruction/constants/name list required")
    result = []
    previous = -1
    for item in instructions:
        if (not isinstance(item, dict) or not {"offset", "opcode", "opname"} <= item.keys()
                or item.keys() - {"offset", "opcode", "opname", "arg", "value"}):
            raise NationDumperAuditError("instruction record is malformed")
        offset, opcode, opname = item["offset"], item["opcode"], item["opname"]
        if (type(offset) is not int or not previous < offset <= MAX_BYTES
                or type(opcode) is not int or not 0 <= opcode <= 255
                or not isinstance(opname, str) or re.fullmatch(r"[A-Z_]+(?:\+[0-9])?", opname) is None):
            raise NationDumperAuditError("instruction offset/opcode/name outside bounds")
        if previous < 0 and offset != 0:
            raise NationDumperAuditError("first instruction must start at zero")
        previous = offset
        arg = item.get("arg")
        if "arg" in item and (type(arg) is not int or not 0 <= arg <= 65535):
            raise NationDumperAuditError("instruction argument outside bounds")
        pool = constants if opname == "LOAD_CONST" else (
            varnames if opname in {"LOAD_FAST", "STORE_FAST"} else (
                names if opname in {"LOAD_ATTR", "LOAD_GLOBAL"} else None))
        if pool is not None and (type(arg) is not int or arg >= len(pool)
                                 or item.get("value") != pool[arg]):
            raise NationDumperAuditError("instruction value disagrees with its pool")
        result.append((opname, arg if opname in ARG_OPS else item.get("value")))
    return result


def parse_map_segments(instructions: list[tuple[str, Any]], start: int,
                       count: int) -> tuple[dict[str, list[tuple[str, Any]]], int]:
    """Extract literal keys/value instruction spans, without evaluating them."""
    if type(start) is not int or type(count) is not int or not 0 <= start < len(instructions) or not 1 <= count <= 32:
        raise NationDumperAuditError("map segment bound differs")
    if instructions[start] != ("BUILD_MAP", count):
        raise NationDumperAuditError("map field count differs")
    result: dict[str, list[tuple[str, Any]]] = {}
    cursor = start + 1
    for _ in range(count):
        end = cursor
        while end < len(instructions) and instructions[end][0] != "STORE_MAP":
            if instructions[end][0] in {"RETURN_VALUE", "STORE_SUBSCR", "STORE_FAST"}:
                raise NationDumperAuditError("map field instruction span differs")
            end += 1
        if end >= len(instructions) or end - cursor < 2:
            raise NationDumperAuditError("map field terminator missing")
        opname, key = instructions[end - 1]
        if opname != "LOAD_CONST" or not isinstance(key, str) or not key or key in result:
            raise NationDumperAuditError("map key is missing or duplicate")
        result[key] = instructions[cursor:end - 1]
        cursor = end + 1
    return result, cursor


def inspect_shape(records: list[dict[str, Any]]) -> dict[str, Any]:
    init = _method(records, "__init__", ["self", "cache"])
    if init[:4] != [("LOAD_FAST", "cache"), ("LOAD_CONST", None),
                    ("COMPARE_OP", 8), ("POP_JUMP_IF_FALSE", None)]:
        raise NationDumperAuditError("constructor default-cache guard differs")
    envelope, after_init = parse_map_segments(init, 4, 3)
    if envelope != {"nodes": [("BUILD_LIST", 0)],
                    "displaySettings": [("BUILD_MAP", 0)],
                    "scrollIndex": [("LOAD_CONST", -1)]} or init[after_init] != ("STORE_FAST", "cache"):
        raise NationDumperAuditError("constructor envelope differs")

    dump = _method(records, "dump", ["self", "data", "nodes"])
    expected_dump = [
        ("LOAD_DEREF", "self"), ("LOAD_ATTR", "clear"), ("CALL_FUNCTION", 0), ("POP_TOP", None),
        ("LOAD_FAST", "data"), ("LOAD_ATTR", "_nodes"), ("STORE_FAST", "nodes"),
        ("LOAD_FAST", "data"), ("LOAD_ATTR", "getItem"), ("STORE_DEREF", "itemGetter"),
        ("LOAD_GLOBAL", "map"), ("LOAD_CLOSURE", "itemGetter"), ("LOAD_CLOSURE", "self"),
        ("BUILD_TUPLE", 2), ("LOAD_CONST", "<code <lambda>>"), ("MAKE_CLOSURE", 0),
        ("LOAD_FAST", "nodes"), ("CALL_FUNCTION", 2), ("LOAD_DEREF", "self"),
        ("LOAD_ATTR", "_cache"), ("LOAD_CONST", "nodes"), ("STORE_SUBSCR", None),
        ("LOAD_FAST", "data"), ("LOAD_ATTR", "_scrollIndex"), ("LOAD_DEREF", "self"),
        ("LOAD_ATTR", "_cache"), ("LOAD_CONST", "scrollIndex"), ("STORE_SUBSCR", None),
        ("LOAD_DEREF", "self"), ("LOAD_ATTR", "_cache"), ("LOAD_CONST", "displaySettings"),
        ("BINARY_SUBSCR", None), ("LOAD_ATTR", "update"), ("LOAD_GLOBAL", "g_techTreeDP"),
        ("LOAD_ATTR", "getDisplaySettings"), ("LOAD_GLOBAL", "SelectedNation"),
        ("LOAD_ATTR", "getIndex"), ("CALL_FUNCTION", 0), ("CALL_FUNCTION", 1),
        ("CALL_FUNCTION", 1), ("POP_TOP", None), ("LOAD_DEREF", "self"),
        ("LOAD_ATTR", "_cache"), ("RETURN_VALUE", None),
    ]
    if dump != expected_dump:
        raise NationDumperAuditError("dump field population/return differs")
    mapper = _method(records, "dump.<lambda>", ["node"])
    if mapper != [
        ("LOAD_DEREF", "self"), ("LOAD_ATTR", "_getVehicleData"), ("LOAD_FAST", "node"),
        ("LOAD_DEREF", "itemGetter"), ("LOAD_FAST", "node"), ("LOAD_CONST", "id"),
        ("BINARY_SUBSCR", None), ("CALL_FUNCTION", 1), ("CALL_FUNCTION", 2), ("RETURN_VALUE", None),
    ]:
        raise NationDumperAuditError("dump node/item lookup differs")

    node = _method(records, "_getVehicleData", ["self", "node", "item", "nodeCD", "tags",
                    "credits", "gold", "defCredits", "defGold", "action"])
    prefix = [
        ("LOAD_FAST", "node"), ("LOAD_CONST", "id"), ("BINARY_SUBSCR", None), ("STORE_FAST", "nodeCD"),
        ("LOAD_FAST", "item"), ("LOAD_ATTR", "tags"), ("STORE_FAST", "tags"),
        ("LOAD_FAST", "item"), ("LOAD_ATTR", "buyPrice"), ("LOAD_FAST", "item"),
        ("LOAD_ATTR", "defaultPrice"), ("ROT_TWO", None), ("UNPACK_SEQUENCE", 2),
        ("STORE_FAST", "credits"), ("STORE_FAST", "gold"), ("UNPACK_SEQUENCE", 2),
        ("STORE_FAST", "defCredits"), ("STORE_FAST", "defGold"), ("LOAD_CONST", None),
        ("STORE_FAST", "action"), ("LOAD_FAST", "item"), ("LOAD_ATTR", "buyPrice"),
        ("LOAD_FAST", "item"), ("LOAD_ATTR", "defaultPrice"), ("COMPARE_OP", 3),
        ("POP_JUMP_IF_FALSE", None), ("LOAD_GLOBAL", "getItemActionTooltipData"),
        ("LOAD_FAST", "item"), ("CALL_FUNCTION", 1), ("STORE_FAST", "action"), ("JUMP_FORWARD", None),
    ]
    if node[:len(prefix)] != prefix:
        raise NationDumperAuditError("node ID/tags/price/action source differs")
    fields, after_node = parse_map_segments(node, len(prefix), 13)
    passthrough = lambda key: [("LOAD_FAST", "node"), ("LOAD_CONST", key), ("BINARY_SUBSCR", None)]
    item_attr = lambda attr: [("LOAD_FAST", "item"), ("LOAD_ATTR", attr)]
    expected_fields = {
        "id": [("LOAD_FAST", "nodeCD")], "state": passthrough("state"),
        "type": item_attr("itemTypeName"), "nameString": item_attr("shortUserName"),
        "primaryClass": [("LOAD_FAST", "self"), ("LOAD_ATTR", "_vClassInfo"),
                         ("LOAD_ATTR", "getInfoByTags"), ("LOAD_FAST", "tags"), ("CALL_FUNCTION", 1)],
        "level": item_attr("level"), "longName": item_attr("longUserName"),
        "iconPath": item_attr("icon"), "smallIconPath": item_attr("iconSmall"),
        "earnedXP": passthrough("earnedXP"),
        "shopPrice": [("LOAD_FAST", "credits"), ("LOAD_FAST", "gold"),
                      ("LOAD_FAST", "action"), ("BUILD_TUPLE", 3)],
        "displayInfo": passthrough("displayInfo"),
        "unlockProps": passthrough("unlockProps") + [("LOAD_ATTR", "_makeTuple"), ("CALL_FUNCTION", 0)],
    }
    if fields != expected_fields or node[after_node:] != [("RETURN_VALUE", None)]:
        raise NationDumperAuditError("vehicle field names/sources/return differ")
    return {
        "envelope_fields": list(envelope),
        "constructor_defaults": {"nodes": "empty list", "displaySettings": "empty dict", "scrollIndex": -1},
        "dump_sources": {"nodes": "map(_getVehicleData(node, data.getItem(node['id'])), data._nodes)",
                         "scrollIndex": "data._scrollIndex",
                         "displaySettings": "g_techTreeDP.getDisplaySettings(SelectedNation.getIndex())"},
        "vehicle_fields": list(fields),
        "vehicle_sources": {
            "id": "node['id']", "state": "node['state']", "type": "item.itemTypeName",
            "nameString": "item.shortUserName", "primaryClass": "_vClassInfo.getInfoByTags(item.tags)",
            "level": "item.level", "longName": "item.longUserName", "iconPath": "item.icon",
            "smallIconPath": "item.iconSmall", "earnedXP": "node['earnedXP']",
            "shopPrice": "(item.buyPrice credits, item.buyPrice gold, action tooltip or None)",
            "displayInfo": "node['displayInfo']", "unlockProps": "node['unlockProps']._makeTuple()",
        },
        "field_value_types": "UNKNOWN_NOT_ESTABLISHED_BY_STATIC_DUMPER",
        "nested_display_info_unlock_props": "STATIC_FORMAT_SHAPE_ONLY_VALUE_TYPES_UNKNOWN",
    }


def inspect_nested_shape(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure only the nested keys/indexes consumed by NationXMLDumper.

    This is still an instruction/format audit.  It intentionally reports
    format conversions and access paths rather than assigning Python or wire
    types to the values supplied by the vehicle data provider.
    """
    class_rows = [row for row in records
                  if row.get("qualified_name") == "<module>.NationXMLDumper"]
    if len(class_rows) != 1:
        raise NationDumperAuditError("missing or duplicate NationXMLDumper class")
    class_row = class_rows[0]
    constants = class_row.get("constants")
    names = class_row.get("names")
    if (not isinstance(constants, list) or len(constants) < len(NATION_XML_CONSTANTS)
            or tuple(constants[:len(NATION_XML_CONSTANTS)]) != NATION_XML_CONSTANTS
            or not isinstance(names, list)
            or tuple(names[2:2 + len(NATION_XML_NAMES)]) != NATION_XML_NAMES):
        raise NationDumperAuditError("NationXMLDumper format constants differ")

    nodes = _method(records, "__buildNodesData",
                    ["self", "data", "nodesDump", "itemGetter", "node"],
                    prefix=XML_PREFIX)
    expected_nodes = [
        ("BUILD_LIST", 0), ("STORE_FAST", "nodesDump"),
        ("LOAD_FAST", "data"), ("LOAD_ATTR", "getItem"),
        ("STORE_FAST", "itemGetter"), ("SETUP_LOOP", None),
        ("LOAD_FAST", "data"), ("LOAD_ATTR", "_nodes"), ("GET_ITER", None),
        ("FOR_ITER", None), ("STORE_FAST", "node"), ("LOAD_FAST", "self"),
        ("LOAD_ATTR", "_getVehicleData"), ("LOAD_FAST", "node"),
        ("LOAD_FAST", "itemGetter"), ("LOAD_FAST", "node"),
        ("LOAD_CONST", "id"), ("BINARY_SUBSCR", None),
        ("CALL_FUNCTION", 1), ("CALL_FUNCTION", 2), ("STORE_FAST", "data"),
        ("LOAD_FAST", "self"),
        ("LOAD_ATTR", "_NationXMLDumper__buildUnlockProps"),
        ("LOAD_FAST", "data"), ("LOAD_CONST", "unlockProps"),
        ("BINARY_SUBSCR", None), ("CALL_FUNCTION", 1), ("LOAD_FAST", "data"),
        ("LOAD_CONST", "unlockProps"), ("STORE_SUBSCR", None),
        ("LOAD_FAST", "self"),
        ("LOAD_ATTR", "_NationXMLDumper__buildDisplayInfo"),
        ("LOAD_FAST", "data"), ("LOAD_CONST", "displayInfo"),
        ("BINARY_SUBSCR", None), ("CALL_FUNCTION", 1), ("LOAD_FAST", "data"),
        ("LOAD_CONST", "displayInfo"), ("STORE_SUBSCR", None),
        ("LOAD_FAST", "nodesDump"), ("LOAD_ATTR", "append"), ("LOAD_FAST", "self"),
        ("LOAD_ATTR", "_NationXMLDumper__nodeFormat"), ("LOAD_ATTR", "format"),
        ("LOAD_FAST", "data"), ("CALL_FUNCTION_KW", None),
        ("CALL_FUNCTION", 1), ("POP_TOP", None), ("JUMP_ABSOLUTE", None),
        ("POP_BLOCK", None), ("LOAD_CONST", ""), ("LOAD_ATTR", "join"),
        ("LOAD_FAST", "nodesDump"), ("CALL_FUNCTION", 1), ("RETURN_VALUE", None),
    ]
    if nodes != expected_nodes:
        raise NationDumperAuditError("NationXMLDumper node builder differs")

    unlock = _method(records, "__buildUnlockProps",
                     ["self", "unlockProps", "dump"], prefix=XML_PREFIX)
    if unlock != [
        ("LOAD_GLOBAL", "map"), ("LOAD_CLOSURE", "self"), ("BUILD_TUPLE", 1),
        ("LOAD_CONST", "<code <lambda>>"), ("MAKE_CLOSURE", 0),
        ("LOAD_FAST", "unlockProps"), ("LOAD_CONST", -1), ("BINARY_SUBSCR", None),
        ("CALL_FUNCTION", 2), ("STORE_FAST", "dump"),
        ("LOAD_FAST", "unlockProps"), ("LOAD_CONST", -1), ("SLICE+2", None),
        ("LOAD_CONST", ""), ("LOAD_ATTR", "join"), ("LOAD_FAST", "dump"),
        ("CALL_FUNCTION", 1), ("BUILD_TUPLE", 1), ("BINARY_ADD", None),
        ("RETURN_VALUE", None),
    ]:
        raise NationDumperAuditError("NationXMLDumper unlockProps builder differs")
    unlock_lambda = _method(records, "__buildUnlockProps.<lambda>",
                            ["item"], prefix=XML_PREFIX)
    if unlock_lambda != [
        ("LOAD_DEREF", "self"), ("LOAD_ATTR", "_NationXMLDumper__topIDFormat"),
        ("LOAD_ATTR", "format"), ("LOAD_FAST", "item"), ("CALL_FUNCTION", 1),
        ("RETURN_VALUE", None),
    ]:
        raise NationDumperAuditError("NationXMLDumper top-ID mapper differs")

    display = _method(records, "__buildDisplayInfo",
                      ["self", "displayInfo", "info", "lines", "dump", "data",
                       "inPins", "inPin", "viaPins"], prefix=XML_PREFIX)
    expected_display = [
        ("LOAD_FAST", "displayInfo"), ("LOAD_ATTR", "copy"), ("CALL_FUNCTION", 0),
        ("STORE_FAST", "info"), ("LOAD_FAST", "info"), ("LOAD_CONST", "lines"),
        ("BINARY_SUBSCR", None), ("STORE_FAST", "lines"), ("BUILD_LIST", 0),
        ("STORE_FAST", "dump"), ("SETUP_LOOP", None), ("LOAD_FAST", "lines"),
        ("GET_ITER", None), ("FOR_ITER", None), ("STORE_FAST", "data"),
        ("BUILD_LIST", 0), ("STORE_FAST", "inPins"), ("SETUP_LOOP", None),
        ("LOAD_FAST", "data"), ("LOAD_CONST", "inPins"), ("BINARY_SUBSCR", None),
        ("GET_ITER", None), ("FOR_ITER", None), ("STORE_FAST", "inPin"),
        ("LOAD_GLOBAL", "map"), ("LOAD_CLOSURE", "self"), ("BUILD_TUPLE", 1),
        ("LOAD_CONST", "<code <lambda>>"), ("MAKE_CLOSURE", 0),
        ("LOAD_FAST", "inPin"), ("LOAD_CONST", "viaPins"), ("BINARY_SUBSCR", None),
        ("CALL_FUNCTION", 2), ("STORE_FAST", "viaPins"), ("LOAD_FAST", "inPins"),
        ("LOAD_ATTR", "append"), ("LOAD_DEREF", "self"),
        ("LOAD_ATTR", "_NationXMLDumper__inPinFormat"), ("LOAD_ATTR", "format"),
        ("LOAD_CONST", "dump"), ("LOAD_CONST", ""), ("LOAD_ATTR", "join"),
        ("LOAD_FAST", "viaPins"), ("CALL_FUNCTION", 1), ("LOAD_FAST", "inPin"),
        ("CALL_FUNCTION_KW", None), ("CALL_FUNCTION", 1), ("POP_TOP", None),
        ("JUMP_ABSOLUTE", None), ("POP_BLOCK", None), ("LOAD_FAST", "dump"),
        ("LOAD_ATTR", "append"), ("LOAD_DEREF", "self"),
        ("LOAD_ATTR", "_NationXMLDumper__setFormat"), ("LOAD_ATTR", "format"),
        ("LOAD_FAST", "data"), ("LOAD_CONST", "outLiteral"),
        ("BINARY_SUBSCR", None), ("LOAD_FAST", "data"), ("LOAD_CONST", "outPin"),
        ("BINARY_SUBSCR", None), ("LOAD_CONST", ""), ("LOAD_ATTR", "join"),
        ("LOAD_FAST", "inPins"), ("CALL_FUNCTION", 1), ("CALL_FUNCTION", 3),
        ("CALL_FUNCTION", 1), ("POP_TOP", None), ("JUMP_ABSOLUTE", None),
        ("POP_BLOCK", None), ("LOAD_CONST", ""), ("LOAD_ATTR", "join"),
        ("LOAD_FAST", "dump"), ("CALL_FUNCTION", 1), ("LOAD_FAST", "info"),
        ("LOAD_CONST", "lines"), ("STORE_SUBSCR", None), ("LOAD_DEREF", "self"),
        ("LOAD_ATTR", "_NationXMLDumper__displayInfoFormat"), ("LOAD_ATTR", "format"),
        ("LOAD_FAST", "info"), ("CALL_FUNCTION_KW", None), ("RETURN_VALUE", None),
    ]
    if display != expected_display:
        raise NationDumperAuditError("NationXMLDumper displayInfo builder differs")
    display_lambda = _method(records, "__buildDisplayInfo.<lambda>",
                             ["item"], prefix=XML_PREFIX)
    if display_lambda != [
        ("LOAD_DEREF", "self"), ("LOAD_ATTR", "_NationXMLDumper__viaPinFormat"),
        ("LOAD_ATTR", "format"), ("LOAD_FAST", "item"), ("CALL_FUNCTION", 1),
        ("RETURN_VALUE", None),
    ]:
        raise NationDumperAuditError("NationXMLDumper via-pin mapper differs")

    return {
        "format_constants": list(NATION_XML_CONSTANTS),
        "unlockProps": {
            "input": "node['unlockProps']._makeTuple()",
            "iterated_index": -1,
            "preserved_prefix": "unlockProps[:-1]",
            "output_arity": 4,
            "format_fields": [
                {"index": 0, "name": "parentID", "conversion": "d"},
                {"index": 1, "name": "unlockIdx", "conversion": "d"},
                {"index": 2, "name": "xpCost", "conversion": "n"},
                {"index": 3, "name": "topIDs", "conversion": ">s"},
            ],
            "value_types": "UNKNOWN_NOT_ESTABLISHED_BY_STATIC_DUMPER",
        },
        "displayInfo": {
            "input": "node['displayInfo']",
            "copy_method": "copy()",
            "line_key": "lines",
            "line_fields": ["row", "column", "position", "inPins", "outLiteral", "outPin"],
            "in_pin_fields": ["inPin", "viaPins"],
            "via_pin_format": "<pin><x>{0[0]:n}</x><y>{0[1]:n}</y></pin>",
            "value_types": "UNKNOWN_NOT_ESTABLISHED_BY_STATIC_DUMPER",
        },
        "serializer_or_wire": "NOT_RUN",
    }


def audit(*, root: str | Path, disassembly: str | Path = DEFAULT_DISASSEMBLY) -> dict[str, Any]:
    repository = Path(root).resolve(strict=True)
    source, raw = _read(repository, disassembly)
    records = parse_json(raw)
    shape = inspect_shape(records)
    nested_shape = inspect_nested_shape(records)
    disassembly_sha = hashlib.sha256(raw).hexdigest()
    if disassembly_sha != DISASSEMBLY_SHA256:
        raise NationDumperAuditError("disassembly SHA differs from measured evidence")
    copies = {}
    for name in ("original", "research"):
        _, client_raw = _read(repository, f"WoT_0.9.1_RU_0717_{name}/{SOURCE_RELATIVE}")
        copies[name] = hashlib.sha256(client_raw).hexdigest()
        if copies[name] != SOURCE_SHA256:
            raise NationDumperAuditError(f"{name} dumpers.pyc SHA differs")
    return {
        "status": "PASS_STATIC_NATION_DUMPER_OUTPUT", "schema": "p09a-nation-dumper-static.v1",
        "build": "v.0.9.1 #717", "disassembly": source.relative_to(repository).as_posix(),
        "disassembly_sha256": disassembly_sha, "source_relative": SOURCE_RELATIVE,
        "source_sha256": SOURCE_SHA256, "source_copies": copies, "shape": shape,
        "nested_shape": nested_shape,
        "native_account_shop_payload": "NOT_RUN", "native_callback_bytes": "NOT_RUN",
        "native_tree_screenshot": "NOT_RUN", "native_visibility": "UNKNOWN",
        "server_handoff": "NOT_RUN", "battle_admission": "NOT_RUN",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--disassembly", default=DEFAULT_DISASSEMBLY)
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        report = audit(root=args.root, disassembly=args.disassembly)
        if args.out:
            output = _bounded(Path(args.root), args.out, must_exist=False)
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(raw) > 64 * 1024:
                raise NationDumperAuditError("receipt exceeds bounds")
            output.write_bytes(raw + b"\n")
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    except (NationDumperAuditError, OSError) as error:
        raise SystemExit(f"nation dumper static audit rejected: {error}")


if __name__ == "__main__":
    main()
