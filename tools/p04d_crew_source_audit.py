"""Bounded read-only #717 recruitment contract audit; never runs client code.

Receipts contain source pins, protocol facts and offsets, not proprietary
resources or reconstructed source code. A static PASS is not native acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from .crew_equipment_source_audit import OPCODE_PIN, SOURCE_BUILD, SOURCE_MANIFEST, pinned_read, write_receipt
    from .destructible_catalog import CatalogError, json_value, no_links, read
    from .packed_xml import decode, walk
    from .py27_static import inspect, opcode_table
else:
    from crew_equipment_source_audit import OPCODE_PIN, SOURCE_BUILD, SOURCE_MANIFEST, pinned_read, write_receipt
    from destructible_catalog import CatalogError, json_value, no_links, read
    from packed_xml import decode, walk
    from py27_static import inspect, opcode_table


ROOT = Path(__file__).resolve().parents[1]
# Language metadata, independently checked against the pinned CPython 2.7.3
# opcode table. Only opcodes needed to resolve operands/verify this audit are
# named; the bounded inspector retains unrelated operations as UNKNOWN_n.
AUDIT_OPCODES = {
    15: "UNARY_INVERT", 24: "BINARY_SUBTRACT", 25: "BINARY_SUBSCR", 60: "STORE_SUBSCR",
    83: "RETURN_VALUE", 90: "STORE_NAME", 91: "DELETE_NAME", 95: "STORE_ATTR",
    96: "DELETE_ATTR", 97: "STORE_GLOBAL", 98: "DELETE_GLOBAL", 100: "LOAD_CONST",
    101: "LOAD_NAME", 103: "BUILD_LIST", 106: "LOAD_ATTR", 107: "COMPARE_OP",
    108: "IMPORT_NAME", 109: "IMPORT_FROM", 116: "LOAD_GLOBAL", 124: "LOAD_FAST",
    125: "STORE_FAST", 126: "DELETE_FAST", 131: "CALL_FUNCTION", 135: "LOAD_CLOSURE",
    136: "LOAD_DEREF", 137: "STORE_DEREF", 140: "CALL_FUNCTION_VAR", 145: "EXTENDED_ARG",
}
SOURCE_PINS = {
    "client/account.pyc": (45998, "bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef"),
    "client/account_helpers/shop.pyc": (25626, "84aa30eb5b1862ac4fbb08557b67ad36dabc9b90cc1d083a29e0e12040127b6d"),
    "client/account_helpers/inventory.pyc": (22611, "3d17842cc6fa9af05d53cc6d22dc286e6b0434356e58c6f74d5822c2dd3cbf19"),
    "client/account_helpers/accountsyncdata.pyc": (6770, "8032c14629301d79056e4b5a0bf24c60f86023199bc762b3845860c6ca16dffd"),
    "common/accountcommands.pyc": (5534, "ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe"),
    "common/items/__init__.pyc": (4303, "587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176"),
    "client/gui/shared/gui_items/processors/tankman.pyc": (25844, "ef86bdc26577dc1d34dcc0c2f97ce230c185e5ae5b5ec41aaef5766224274d21"),
    "client/gui/shared/gui_items/processors/__init__.pyc": (9288, "a889281242e3ad47b57fcb739d9f5a3f52278b646092edf7caf30a8fc77e531b"),
    "client/gui/shared/gui_items/processors/plugins.pyc": (25426, "5d19c2f421b9f4f324bebd5a66ab31e4c990ec6b9298863c07c323c61749abdd"),
    "client/gui/scaleform/daapi/view/lobby/recruitwindow/recruitwindow.pyc": (11904, "ac81a6a0a009fbc856505395f87f76d2a6df303291a7569eb2054f01f802fc41"),
    "client/gui/scaleform/daapi/view/lobby/hangar/crew.pyc": (7329, "8defb03050f4d903d40e466e11fed0b04c368f8fc0450263316e0b768edba136"),
    "client/gui/shared/utils/requesters/inventoryrequester.pyc": (12868, "4e2c79a4f826740b3363b14b00dba7aeaa9a539dc3c1b32671eb5256f4103e84"),
    "client/gui/shared/utils/requesters/itemsrequester.pyc": (28259, "41e5e9bacbb68e89202116bd267c6cd9fceeda4edb0ed605c7b87cc9315c0c44"),
    "entity_defs/account.def": (10588, "883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674"),
    "entity_defs/alias.xml": (5987, "14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746"),
    "entity_defs/interfaces/chat.def": (876, "3f8f0f6d14e21ece8db54af467235110eaf495b04ab404434fd69eaf66270f3d"),
    "entity_defs/interfaces/accounteditor.def": (180, "9d91f1d0b1f60df9e8159f966240e8e023268ad1b7fb619868f746badba74e67"),
    "entity_defs/interfaces/transactionuser.def": (109, "7cad5cf0cd1f1bc8b0661af6cbeffb2566c26a378b0a5cc22626241600714a7e"),
}


class SourceAuditError(ValueError):
    """The configured source or closed protocol facts did not match."""


def require(condition, message):
    if not condition:
        raise SourceAuditError(message)


def verify_definition(raw):
    tree = decode(raw, max_bytes=64 * 1024, max_nodes=10000, max_depth=16)
    facts = {}
    for group, name, expected in [
        ("BaseMethods", "doCmdInt3", ["INT16", "INT16", "INT64", "INT32", "INT32"]),
        ("BaseMethods", "doCmdInt4", ["INT16", "INT16", "INT64", "INT32", "INT32", "INT32"]),
        ("ClientMethods", "onCmdResponse", ["INT16", "INT16", "STRING"]),
        ("ClientMethods", "onCmdResponseExt", ["INT16", "INT16", "STRING", "STRING"]),
        ("ClientMethods", "update", ["STRING"]),
    ]:
        groups = [row["data"] for row in tree["children"] if row["name"] == group]
        require(len(groups) == 1, "definition group mismatch")
        methods = [row["data"] for row in groups[0]["children"] if row["name"] == name]
        require(len(methods) == 1, "definition method count mismatch: " + name)
        arguments = [value for path, value in walk(methods[0]) if path.startswith("/Arg[") and path.count("/") == 1]
        require(arguments == expected, "definition argument order/types mismatch: " + name)
        if group == "BaseMethods":
            require(sum(row["name"] == "Exposed" for row in methods[0]["children"]) == 1,
                    "base method must be exposed")
        facts[name] = {"argument_types": arguments, "definition_group": group}
    return facts


def verify_method_table_candidate(raw_sources):
    """Bounded stable stream-size hypothesis, deliberately not native proof."""
    def children(node):
        return node.get("children", []) if isinstance(node, dict) else []
    def scalar(node):
        if isinstance(node, dict) and "value" in node:
            return scalar(node["value"])
        if isinstance(node, dict) and "base64" in node:
            return node["base64"]
        return str(node)
    def tree(name):
        require(name in SOURCE_PINS and name.startswith("entity_defs/"), "unlisted method-table source")
        return decode(raw_sources[name], max_bytes=65536, max_depth=24, max_nodes=12000)
    aliases = {row["name"]: row["data"] for row in children(tree("entity_defs/alias.xml"))}
    fixed = {"UINT8": 1, "INT8": 1, "BOOL": 1, "UINT16": 2, "INT16": 2, "UINT32": 4,
             "INT32": 4, "FLOAT32": 4, "UINT64": 8, "INT64": 8, "FLOAT64": 8, "VECTOR3": 12}
    def size(node, depth=0):
        require(depth <= 12, "method-table alias recursion bound")
        name = scalar(node)
        if name in fixed:
            return fixed[name]
        if name in aliases:
            return size(aliases[name], depth + 1)
        if name == "FIXED_DICT":
            attrs = {row["name"]: row["data"] for row in children(node)}
            if attrs.get("AllowNone"):
                return None
            sizes = [size(next(row["data"] for row in children(prop["data"]) if row["name"] == "Type"), depth + 1)
                     for prop in children(attrs.get("Properties"))]
            return None if None in sizes else sum(sizes)
        return None
    groups, seen = {"BaseMethods": [], "ClientMethods": []}, set()
    def visit(name):
        require(name not in seen and len(seen) < 8, "method-table interface cycle/bound")
        seen.add(name)
        node = tree(name)
        for group in children(node):
            if group["name"] == "Implements":
                for row in children(group["data"]):
                    part = scalar(row["data"])
                    require(part in ("Chat", "AccountEditor", "TransactionUser"), "unexpected inherited interface")
                    visit("entity_defs/interfaces/" + part.lower() + ".def")
        for group in children(node):
            if group["name"] not in groups:
                continue
            for method in children(group["data"]):
                attrs = children(method["data"])
                if group["name"] == "BaseMethods" and not any(row["name"] == "Exposed" for row in attrs):
                    continue
                sizes = [size(row["data"]) for row in attrs if row["name"] == "Arg"]
                groups[group["name"]].append((method["name"], None if None in sizes else sum(sizes)))
    visit("entity_defs/account.def")
    selected = {}
    for group, rows in groups.items():
        require(len(rows) <= 120, "method-table row bound")
        rows.sort(key=lambda row: (row[1] is None, row[1] or 0))
        for index, (name, width) in enumerate(rows):
            if name in ("doCmdInt3", "doCmdInt4", "onCmdResponseExt", "update"):
                selected[name] = {"exposed_index": index, "candidate_wire_id": (0x86 if group == "BaseMethods" else 0x3B) + index,
                                  "payload_bytes": width}
    require(selected == {"doCmdInt3": {"exposed_index": 8, "candidate_wire_id": 142, "payload_bytes": 20},
        "doCmdInt4": {"exposed_index": 10, "candidate_wire_id": 144, "payload_bytes": 24},
        "onCmdResponseExt": {"exposed_index": 18, "candidate_wire_id": 77, "payload_bytes": None},
        "update": {"exposed_index": 28, "candidate_wire_id": 87, "payload_bytes": None}}, "method-table hypothesis differs")
    return {"classification": "INFERRED", "ordering": "implements first; stable fixed-size ascending; variable last",
            "selected": selected, "native_doCmdInt4_acceptance": "NOT_RUN"}


def verify_facts(raw_sources, table):
    require(type(raw_sources) is dict and set(raw_sources) == set(SOURCE_PINS), "exact source set required")
    for source, (size, digest) in SOURCE_PINS.items():
        raw = raw_sources[source]
        require(type(raw) is bytes and len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
                "source pin mismatch: " + source)
    methods = verify_definition(raw_sources["entity_defs/account.def"])
    parsed, assertions = {}, []

    def record(source, name):
        if source not in parsed:
            parsed[source] = inspect(raw_sources[source], table)
        qualified = name if name == "<module>" else "<module>." + name
        # Unrelated property getter/setter records can share a name. The
        # specific records used by this protocol audit must be unambiguous.
        matches = [row for row in parsed[source] if row["qualified_name"] == qualified]
        require(len(matches) == 1, "missing/ambiguous bytecode record: " + qualified)
        return matches[0]

    def check(source, name, line, expected):
        row = record(source, name)
        require(row["firstlineno"] == line, "source line mismatch: " + name)
        instructions = {item["offset"]: item for item in row["instructions"]}
        for offset, (opname, operand) in expected.items():
            item = instructions.get(offset)
            require(item is not None and item["opname"] == opname
                    and item.get("value", item.get("arg")) == operand,
                    "bytecode semantic anchor mismatch: " + name + ":" + str(offset))
        assertions.append({"source_id": "res/scripts/" + source, "record": row["qualified_name"],
                           "firstlineno": line, "verified_offsets": sorted(expected)})
        return row

    commands = "common/accountcommands.pyc"
    check(commands, "<module>", 1, {
        82: ("LOAD_CONST", 0), 85: ("STORE_NAME", "RES_SUCCESS"),
        136: ("LOAD_CONST", 105), 139: ("STORE_NAME", "CMD_EQUIP_TMAN"),
        280: ("LOAD_CONST", 303), 283: ("STORE_NAME", "CMD_BUY_TMAN"),
        316: ("LOAD_CONST", 309), 319: ("STORE_NAME", "CMD_BUY_AND_EQUIP_TMAN"),
    })
    shop = "client/account_helpers/shop.pyc"
    check(shop, "Shop.buyAndEquipTankman", 741, {
        92: ("LOAD_ATTR", "_doCmdInt4"), 98: ("LOAD_ATTR", "CMD_BUY_AND_EQUIP_TMAN"),
        104: ("LOAD_ATTR", "_Shop__getCacheRevision"), 110: ("LOAD_FAST", "vehInvID"),
        113: ("LOAD_FAST", "slot"), 116: ("LOAD_FAST", "tmanCostTypeIdx"),
        119: ("LOAD_FAST", "proxy"), 122: ("CALL_FUNCTION", 6),
    })
    combined_callback = check(shop, "Shop.buyAndEquipTankman.<lambda>", 747, {
        0: ("LOAD_DEREF", "callback"), 3: ("LOAD_FAST", "resultID"),
        6: ("LOAD_FAST", "errorStr"), 9: ("LOAD_FAST", "ext"),
        12: ("CALL_FUNCTION", 3), 15: ("RETURN_VALUE", None),
    })
    require(combined_callback["names"] == [], "unexpected combined response extension access")
    check(shop, "Shop.buyTankman", 795, {
        3: ("LOAD_ATTR", "makeIntCompactDescrByID"), 24: ("LOAD_ATTR", "SKILL_INDICES"),
        79: ("LOAD_ATTR", "_doCmdInt4"), 85: ("LOAD_ATTR", "CMD_BUY_TMAN"),
        91: ("LOAD_ATTR", "_Shop__getCacheRevision"), 97: ("LOAD_FAST", "vehTypeCompDescr"),
        100: ("LOAD_FAST", "roleIdx"), 103: ("LOAD_FAST", "tmanCostTypeIdx"),
        106: ("LOAD_FAST", "proxy"), 109: ("CALL_FUNCTION", 6),
    })
    check(shop, "Shop.buyTankman.<lambda>", 800, {
        3: ("LOAD_FAST", "resultID"), 6: ("LOAD_FAST", "ext"),
        12: ("LOAD_CONST", "tmanInvID"), 21: ("LOAD_FAST", "ext"),
        27: ("LOAD_CONST", "tmanCompDescr"), 36: ("CALL_FUNCTION", 3),
    })
    check(shop, "Shop.__getCacheRevision", 1043, {9: ("LOAD_CONST", "rev"), 12: ("LOAD_CONST", 0)})
    inventory = "client/account_helpers/inventory.pyc"
    check(inventory, "Inventory.equipTankman", 314, {
        44: ("LOAD_FAST", "tmanInvID"), 47: ("LOAD_CONST", None), 56: ("LOAD_CONST", -1),
        110: ("LOAD_ATTR", "_doCmdInt3"), 116: ("LOAD_ATTR", "CMD_EQUIP_TMAN"),
        119: ("LOAD_FAST", "vehInvID"), 122: ("LOAD_FAST", "slot"),
        125: ("LOAD_FAST", "tmanInvID"), 131: ("CALL_FUNCTION", 5),
    })
    check(inventory, "Inventory.equipTankman.<lambda>", 323, {
        0: ("LOAD_DEREF", "callback"), 3: ("LOAD_FAST", "resultID"), 6: ("CALL_FUNCTION", 1),
    })
    account = "client/account.pyc"
    check(account, "PlayerAccount.__doCmd", 1523, {
        19: ("LOAD_ATTR", "_PlayerAccount__getRequestID"),
        62: ("LOAD_ATTR", "_PlayerAccount__onCmdResponse"), 68: ("STORE_SUBSCR", None),
        78: ("LOAD_ATTR", "base"), 81: ("LOAD_FAST", "doCmdMethod"),
        87: ("LOAD_FAST", "requestID"), 90: ("LOAD_FAST", "cmd"),
        93: ("LOAD_FAST", "args"), 96: ("CALL_FUNCTION_VAR", 2),
    })
    check(account, "PlayerAccount._doCmdInt4", 1407, {
        6: ("LOAD_CONST", "doCmdInt4"), 15: ("LOAD_FAST", "int1"),
        18: ("LOAD_FAST", "int2"), 21: ("LOAD_FAST", "int3"), 24: ("LOAD_FAST", "int4"),
    })
    check(account, "PlayerAccount.onCmdResponseExt", 302, {
        0: ("LOAD_GLOBAL", "cPickle"), 3: ("LOAD_ATTR", "loads"),
        64: ("LOAD_ATTR", "_PlayerAccount__onCmdResponse"), 67: ("LOAD_ATTR", "pop"),
        97: ("LOAD_FAST", "requestID"), 100: ("LOAD_FAST", "resultID"),
        103: ("LOAD_FAST", "errorStr"), 106: ("LOAD_FAST", "ext"), 109: ("CALL_FUNCTION", 4),
    })
    processor = "client/gui/shared/gui_items/processors/tankman.pyc"
    check(processor, "TankmanRecruitAndEquip.__init__", 190, {
        46: ("LOAD_GLOBAL", "dict"), 52: ("LOAD_ATTR", "crew"), 61: ("LOAD_FAST", "slot"),
        67: ("LOAD_CONST", None), 70: ("COMPARE_OP", 9), 76: ("STORE_ATTR", "isReplace"),
        137: ("LOAD_ATTR", "FreeTankmanValidator"), 146: ("LOAD_CONST", 0), 149: ("COMPARE_OP", 2),
        158: ("LOAD_ATTR", "BarracksSlotsValidator"), 161: ("LOAD_CONST", "isEnabled"),
        167: ("LOAD_ATTR", "isReplace"), 170: ("CALL_FUNCTION", 256),
    })
    check(processor, "TankmanRecruitAndEquip.__getSysMsgPrefix", 260, {
        3: ("LOAD_ATTR", "isReplace"), 9: ("LOAD_CONST", "buy_and_equip_tankman"),
        13: ("LOAD_CONST", "buy_and_reequip_tankman"),
    })
    response = check(processor, "TankmanRecruitAndEquip._request.<lambda>", 213, {
        3: ("LOAD_ATTR", "_response"), 6: ("LOAD_FAST", "code"),
        12: ("LOAD_CONST", "ctx"), 15: ("LOAD_FAST", "tmanInvID"), 18: ("CALL_FUNCTION", 258),
    })
    require(response["names"] == ["_response"], "unexpected processor extension access")
    require(not any(row.get("value") == "tmanCompDescr" for row in response["instructions"]),
            "combined processor unexpectedly consumes extension")
    check(processor, "TankmanRecruitAndEquip.__getRecruitPrice", 236, {
        9: ("LOAD_ATTR", "tankmanCost"), 12: ("LOAD_FAST", "tmanCostTypeIdx"), 15: ("BINARY_SUBSCR", None),
        22: ("LOAD_CONST", 1), 34: ("LOAD_CONST", "credits"),
        48: ("LOAD_CONST", 2), 63: ("LOAD_CONST", "gold"),
        71: ("LOAD_CONST", [0, 0]), 74: ("RETURN_VALUE", None),
    })
    plugins = "client/gui/shared/gui_items/processors/plugins.pyc"
    check(plugins, "FreeTankmanValidator._validate", 397, {
        9: ("LOAD_ATTR", "freeTankmenLeft"), 18: ("LOAD_CONST", "free_tankmen_limit"),
    })
    check(plugins, "BarracksSlotsValidator._validate", 380, {
        15: ("LOAD_ATTR", "IN_TANK"), 18: ("UNARY_INVERT", None),
        34: ("LOAD_ATTR", "tankmenBerthsCount"), 58: ("LOAD_ATTR", "berthsNeeded"),
        73: ("BINARY_SUBTRACT", None), 74: ("COMPARE_OP", 4), 83: ("LOAD_CONST", "not_enough_space"),
    })
    recruit = "client/gui/scaleform/daapi/view/lobby/recruitwindow/recruitwindow.pyc"
    check(recruit, "RecruitWindow.buyTankman", 294, {
        0: ("LOAD_FAST", "slot"), 3: ("LOAD_CONST", None), 6: ("COMPARE_OP", 9),
        15: ("LOAD_CONST", -1), 18: ("COMPARE_OP", 3),
        48: ("LOAD_ATTR", "_RecruitWindow__buyAndEquipTankman"),
        83: ("LOAD_ATTR", "_RecruitWindow__buyTankman"),
    })
    check(recruit, "RecruitWindow.__buyTankman", 244, {
        104: ("LOAD_FAST", "success"), 116: ("LOAD_ATTR", "getTankman"),
        119: ("LOAD_FAST", "tmanInvID"), 122: ("CALL_FUNCTION", 1),
    })
    check(account, "PlayerAccount._update", 1451, {
        31: ("LOAD_CONST", "prevRev"), 55: ("LOAD_ATTR", "updatePersistentCache"),
        80: ("LOAD_CONST", "rev"), 95: ("STORE_ATTR", "revision"),
        101: ("LOAD_ATTR", "inventory"), 104: ("LOAD_ATTR", "synchronize"),
    })
    check(inventory, "Inventory.synchronize", 68, {
        28: ("LOAD_CONST", "inventory"), 77: ("LOAD_GLOBAL", "synchronizeDicts"),
        92: ("LOAD_FAST", "itemTypeIdx"), 101: ("CALL_FUNCTION", 2),
    })
    check("client/account_helpers/accountsyncdata.pyc", "AccountSyncData.updatePersistentCache", 103, {
        321: ("LOAD_GLOBAL", "synchronizeDicts"), 324: ("LOAD_GLOBAL", "accountDataGetDiffForPersistent"),
        346: ("LOAD_GLOBAL", "True"), 355: ("STORE_ATTR", "isDirty"),
    })
    requester = "client/gui/shared/utils/requesters/inventoryrequester.pyc"
    check(requester, "InventoryRequester.__makeTankman", 182, {
        45: ("LOAD_ATTR", "TANKMAN"), 81: ("LOAD_CONST", "compDescr"),
        118: ("LOAD_ATTR", "TankmanDescr"), 130: ("LOAD_CONST", "vehicle"),
        133: ("LOAD_CONST", -1), 139: ("CALL_FUNCTION", 3),
    })
    check(requester, "InventoryRequester.__makeVehicle", 138, {
        225: ("LOAD_CONST", "crew"), 228: ("BUILD_LIST", 0), 231: ("CALL_FUNCTION", 2),
    })
    check("client/gui/shared/utils/requesters/itemsrequester.pyc", "ItemsRequester.__getTankmanDossierDescr", 620, {
        33: ("LOAD_ATTR", "getTankmanDossierDescr"), 39: ("LOAD_ATTR", "descriptor"),
        42: ("LOAD_ATTR", "dossierCompactDescr"), 45: ("CALL_FUNCTION", 1),
    })
    item_names = record("common/items/__init__.pyc", "<module>")
    item_row = next((row for row in item_names["instructions"] if row["offset"] == 91), {})
    require(item_row.get("opname") == "LOAD_CONST" and type(item_row.get("value")) is list
            and item_row["value"][1] == "vehicle" and item_row["value"][8] == "tankman",
            "native inventory category mismatch")
    return {
        "methods": methods,
        "method_table_candidate": verify_method_table_candidate(raw_sources),
        "commands": {
            "recruit_and_equip": {"id": 309, "method": "doCmdInt4",
                "arguments": ["request_id", "command", "shop_revision", "vehicle_inventory_id", "seat", "cost_index"],
                "callback_arguments": ["result_id", "error_string", "extension"],
                "extension_keys_required_by_inspected_callbacks": []},
            "recruit": {"id": 303, "method": "doCmdInt4",
                "arguments": ["request_id", "command", "shop_revision", "vehicle_type_compact_descr", "role_index", "cost_index"],
                "callback_arguments": ["result_id", "tankman_inventory_id", "tankman_compact_descr"],
                "extension_keys": ["tmanInvID", "tmanCompDescr"]},
            "equip": {"id": 105, "method": "doCmdInt3",
                "arguments": ["request_id", "command", "vehicle_inventory_id", "seat", "tankman_inventory_id"],
                "callback_arguments": ["result_id"], "unload_sentinel": -1},
        },
        "occupied_seat": {"native_ui_admitted": True, "is_replace_from_existing_seat": True,
            "barracks_validator_enabled_when_replace": True, "old_tankman_moved_by_client": False,
            "server_requirement": "retain old descriptor; move old owner to barracks; commit new seat atomically"},
        "free_tier": {"cost_index": 0, "client_display_price": {"credits": 0, "gold": 0},
            "tariff_row_zero_must_exist": True, "quota_field": "freeTankmenLeft",
            "historical_role_level": "UNKNOWN"},
        "inventory": {"vehicle_category": 1, "tankman_category": 8,
            "tankman_columns": ["compDescr", "vehicle"], "unassigned_vehicle_id": -1,
            "vehicle_crew_column": "crew", "tankman_dossier": "embedded descriptor.dossierCompactDescr",
            "separate_tankman_dossier_stream_row_required": False},
        "account_update_order": ["persistent_cache", "revision", "inventory", "other_state_and_events"],
        "response_extension": "bounded outgoing literal pickle; no incoming object deserialization",
        "update_before_success": {"classification": "INFERRED", "native_order_acceptance": "NOT_RUN"},
        "bytecode_assertions": assertions,
    }


def audit_sources(original_root: Path) -> dict:
    """Audit exact original resources; no config, native export, client or DB.

    The caller supplies an already authorized original directory. The complete
    client manifest is not recomputed; every source used here is independently
    bound to its release size and SHA256 before static parsing.
    """
    original_root = Path(original_root)
    require(original_root.is_absolute(), "explicit absolute original root required")
    try:
        original_root = no_links(original_root).resolve(strict=True)
        require(original_root.is_dir(), "original directory required")
        raw_sources = {name: pinned_read(original_root / "res/scripts" / name, pin)
                       for name, pin in SOURCE_PINS.items()}
    except (ValueError, OSError) as error:
        raise SourceAuditError("original source audit failed: " + str(error)) from error
    return {"schema_version": 1, "status": "PASS_P04D_STATIC_SOURCE_AUDIT", "classification": "VERIFIED_STATIC",
        "build": SOURCE_BUILD, "client_manifest_sha256": SOURCE_MANIFEST,
        "manifest_validation": "target identity only; selected source files independently pinned",
        "sources": [{"source_id": "res/scripts/" + name, "bytes": pin[0], "sha256": pin[1]}
                    for name, pin in sorted(SOURCE_PINS.items())],
        "opcode_table": {"reference_bytes": OPCODE_PIN[0], "reference_sha256": OPCODE_PIN[1],
                         "mode": "audited CPython2.7.3 opcode subset"},
        "facts": verify_facts(raw_sources, dict(AUDIT_OPCODES)),
        "not_run": ["native recruitment", "native occupied-seat replacement", "native doCmdInt4 wire index",
                    "native cache update and response order", "server transaction", "relogin", "UI acceptance"],
        "unknown": ["historical paid tariffs", "historical tier-to-training mapping", "cross-session replay identity"],
        "no_client_code_executed": True, "no_database_or_service_access": True}


def audit(config_path):
    config = json_value(read(no_links(config_path), 65536).removeprefix(b"\xef\xbb\xbf"), depth=12, nodes=1024)
    require(type(config) is dict and type(config.get("target")) is dict, "configured target object required")
    target = config["target"]
    require(target.get("exact_build") == SOURCE_BUILD and target.get("region") == "RU", "unexpected client build/region")
    require(target.get("client_manifest_sha256") == SOURCE_MANIFEST, "unexpected client manifest")
    paths = config.get("paths")
    require(type(paths) is dict, "configured paths required")
    roots = {}
    for key in ("original_client_root", "local_artifacts_root"):
        require(type(paths.get(key)) is str and Path(paths[key]).is_absolute(), "configured absolute root required")
        roots[key] = no_links(paths[key]).resolve(strict=True)
        require(roots[key].is_dir(), "configured directory required")
    opcode = pinned_read(roots["local_artifacts_root"] / "vendor/cpython-2.7.3/opcode.py", OPCODE_PIN)
    reference = opcode_table(opcode.decode("utf-8"))
    require(all(reference.get(number) == name for number, name in AUDIT_OPCODES.items()),
            "opcode subset differs from pinned CPython2.7.3 table")
    return audit_sources(roots["original_client_root"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="fresh directory under this worktree local/")
    args = parser.parse_args()
    try:
        result = write_receipt(audit(args.config), args.out)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, "FAIL_P04D_STATIC_SOURCE_AUDIT: " + str(error) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
