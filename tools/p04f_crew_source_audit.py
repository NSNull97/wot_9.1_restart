"""Bounded, read-only #717 crew transfer contract; never executes original code.

Static source facts do not prove CMD105 native transport or UI acceptance.
Receipts contain hashes and semantic anchors, not copied client resources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from . import p04d_crew_source_audit as baseline
    from .crew_equipment_source_audit import OPCODE_PIN, SOURCE_BUILD, SOURCE_MANIFEST, pinned_read, write_receipt, _scalar
    from .destructible_catalog import json_value, no_links, read
    from .packed_xml import decode, walk
    from .py27_static import inspect, opcode_table, parse_pyc, records
else:
    import p04d_crew_source_audit as baseline
    from crew_equipment_source_audit import OPCODE_PIN, SOURCE_BUILD, SOURCE_MANIFEST, pinned_read, write_receipt, _scalar
    from destructible_catalog import json_value, no_links, read
    from packed_xml import decode, walk
    from py27_static import inspect, opcode_table, parse_pyc, records


ROOT = Path(__file__).resolve().parents[1]
SOURCE_PINS = dict(baseline.SOURCE_PINS, **{
    "client/account_helpers/diff_utils.pyc": (1194, "46c1582f244c27ed72b1b38890f86a03ca5de339af36b3d2a77b39a3e9de7517"),
    "client/gui/shared/gui_items/vehicle.pyc": (25863, "ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8"),
    "client/gui/shared/gui_items/tankman.pyc": (15745, "07645906b7cac95bc482c0e9548b37c598d3ec440752f7f19058688f981fa364"),
    "client/gui/scaleform/daapi/view/lobby/barracks/barracks.pyc": (13142, "1c18c924c6bfb9e753dae3f637b8b8079807a25b2e08e421b895bbb83bab3f19"),
    "common/items/tankmen.pyc": (24558, "74f914b1e5e7e574086dd865d87e4cfbf8cace6e60b5e506757eba28ca8bc530"),
    "item_defs/vehicles/ussr/ms-1.xml": (11839, "a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535"),
    "item_defs/vehicles/ussr/list.xml": (18228, "167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138"),
})
AUDIT_OPCODES = dict(baseline.AUDIT_OPCODES)
AUDIT_OPCODES.update({86: "YIELD_VALUE", 102: "BUILD_TUPLE", 132: "MAKE_FUNCTION"})


class SourceAuditError(ValueError):
    """The admitted historical source or closed transfer contract differs."""


def require(condition, message):
    if not condition:
        raise SourceAuditError(message)


def verify_facts(raw_sources, table):
    require(type(raw_sources) is dict and set(raw_sources) == set(SOURCE_PINS), "exact source set required")
    for source, (size, digest) in SOURCE_PINS.items():
        raw = raw_sources[source]
        require(type(raw) is bytes and len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
                "source pin mismatch: " + source)
    try:
        prior = baseline.verify_facts({key: raw_sources[key] for key in baseline.SOURCE_PINS}, table)
    except baseline.SourceAuditError as error:
        raise SourceAuditError(str(error)) from error
    parsed, metadata, assertions = {}, {}, []

    def check(source, name, line, argument_names, expected):
        if source not in parsed:
            parsed[source] = inspect(raw_sources[source], table)
            metadata[source] = list(records(parse_pyc(raw_sources[source])))
        qualified = name if name == "<module>" else "<module>." + name
        matches = [r for r in parsed[source] if r["qualified_name"] == qualified]
        codes = [r for q, r in metadata[source] if q == qualified]
        require(len(matches) == len(codes) == 1, "ambiguous/missing record: " + qualified)
        row, code = matches[0], codes[0]
        require(row["firstlineno"] == line, "source line differs: " + name)
        require(code["argcount"] == len(argument_names) and row["varnames"][:len(argument_names)] == argument_names,
                "argument signature differs: " + name)
        instructions = {item["offset"]: item for item in row["instructions"]}
        for offset, (opname, operand) in expected.items():
            item = instructions.get(offset)
            require(item is not None and item["opname"] == opname and item.get("value", item.get("arg")) == operand,
                    "bytecode semantic anchor differs: " + name + ":" + str(offset))
        assertions.append({"source_id": "res/scripts/" + source, "record": qualified,
            "source_filename": row["source_filename"], "firstlineno": line,
            "marshal_offset_plus_pyc_header": code["marshal_offset"] + 8,
            "argument_names": argument_names, "local_names": row["varnames"],
            "code_bytes": len(code["code"]), "code_sha256": hashlib.sha256(code["code"]).hexdigest(),
            "verified_offsets": sorted(expected)})
        return row

    account = "client/account.pyc"
    check(account, "PlayerAccount._doCmdInt3", 1401, ["self", "cmd", "int1", "int2", "int3", "callback"], {
        6: ("LOAD_CONST", "doCmdInt3"), 9: ("LOAD_FAST", "cmd"), 12: ("LOAD_FAST", "callback"),
        15: ("LOAD_FAST", "int1"), 18: ("LOAD_FAST", "int2"), 21: ("LOAD_FAST", "int3"), 24: ("CALL_FUNCTION", 6)})
    check(account, "PlayerAccount.__doCmd", 1523, ["self", "doCmdMethod", "cmd", "callback"], {
        19: ("LOAD_ATTR", "_PlayerAccount__getRequestID"), 25: ("STORE_FAST", "requestID"),
        68: ("STORE_SUBSCR", None), 87: ("LOAD_FAST", "requestID"), 90: ("LOAD_FAST", "cmd"),
        93: ("LOAD_FAST", "args"), 96: ("CALL_FUNCTION_VAR", 2)})
    check(account, "PlayerAccount.onCmdResponse", 291, ["self", "requestID", "resultID", "errorStr"], {
        6: ("LOAD_ATTR", "pop"), 36: ("LOAD_FAST", "requestID"), 39: ("LOAD_FAST", "resultID"),
        42: ("LOAD_FAST", "errorStr"), 45: ("CALL_FUNCTION", 3)})
    check(account, "PlayerAccount.onCmdResponseExt", 302, ["self", "requestID", "resultID", "errorStr", "ext"], {
        67: ("LOAD_ATTR", "pop"), 97: ("LOAD_FAST", "requestID"), 100: ("LOAD_FAST", "resultID"),
        103: ("LOAD_FAST", "errorStr"), 106: ("LOAD_FAST", "ext"), 109: ("CALL_FUNCTION", 4)})
    check("common/accountcommands.pyc", "<module>", 1, [], {
        136: ("LOAD_CONST", 105), 139: ("STORE_NAME", "CMD_EQUIP_TMAN"),
        220: ("LOAD_CONST", 157), 223: ("STORE_NAME", "CMD_RETURN_CREW"),
        298: ("LOAD_CONST", 306), 301: ("STORE_NAME", "CMD_DISMISS_TMAN")})
    inventory = "client/account_helpers/inventory.pyc"
    check(inventory, "Inventory.equipTankman", 314, ["self", "vehInvID", "slot", "tmanInvID", "callback"], {
        44: ("LOAD_FAST", "tmanInvID"), 47: ("LOAD_CONST", None), 50: ("COMPARE_OP", 8),
        56: ("LOAD_CONST", -1), 59: ("STORE_FAST", "tmanInvID"), 110: ("LOAD_ATTR", "_doCmdInt3"),
        116: ("LOAD_ATTR", "CMD_EQUIP_TMAN"), 119: ("LOAD_FAST", "vehInvID"), 122: ("LOAD_FAST", "slot"),
        125: ("LOAD_FAST", "tmanInvID"), 131: ("CALL_FUNCTION", 5)})
    check(inventory, "Inventory.equipTankman.<lambda>", 323, ["requestID", "resultID", "errorStr", "ext"], {
        0: ("LOAD_DEREF", "callback"), 3: ("LOAD_FAST", "resultID"), 6: ("CALL_FUNCTION", 1)})
    check(inventory, "Inventory.returnCrew", 338, ["self", "vehInvID", "callback"], {
        89: ("LOAD_ATTR", "_doCmdInt3"), 95: ("LOAD_ATTR", "CMD_RETURN_CREW"),
        98: ("LOAD_FAST", "vehInvID"), 101: ("LOAD_CONST", 0), 104: ("LOAD_CONST", 0)})
    processors = "client/gui/shared/gui_items/processors/tankman.pyc"
    equip = check(processors, "TankmanEquip.__init__", 126, ["self", "tankman", "vehicle", "slot"], {
        67: ("LOAD_ATTR", "get"), 70: ("LOAD_FAST", "slot"), 106: ("LOAD_ATTR", "invID"),
        112: ("LOAD_ATTR", "invID"), 115: ("COMPARE_OP", 3), 127: ("STORE_ATTR", "isReequip"),
        142: ("LOAD_ATTR", "VehicleValidator"), 160: ("LOAD_CONST", "isLocked"),
        170: ("LOAD_ATTR", "ModuleValidator"), 182: ("LOAD_ATTR", "ModuleTypeValidator"),
        191: ("LOAD_ATTR", "TANKMAN")})
    require("BarracksSlotsValidator" not in equip["names"], "unexpected replacement barracks validator")
    check(processors, "TankmanEquip._request", 165, ["self", "callback"], {
        61: ("LOAD_ATTR", "invID"), 82: ("LOAD_ATTR", "equipTankman"), 91: ("LOAD_ATTR", "invID"),
        97: ("LOAD_ATTR", "slot"), 100: ("LOAD_FAST", "tmanInvID"), 118: ("CALL_FUNCTION", 4)})
    check(processors, "TankmanUnload", 264, [], {6: ("LOAD_CONST", -1), 12: ("MAKE_FUNCTION", 1)})
    unload = check(processors, "TankmanUnload.__init__", 267, ["self", "vehicle", "slot"], {
        37: ("LOAD_CONST", 1), 40: ("STORE_FAST", "berthsNeeded"), 46: ("LOAD_CONST", -1),
        49: ("COMPARE_OP", 2), 70: ("LOAD_ATTR", "crew"), 79: ("STORE_FAST", "berthsNeeded"),
        121: ("LOAD_ATTR", "VehicleValidator"), 139: ("LOAD_CONST", "isLocked"),
        149: ("LOAD_ATTR", "BarracksSlotsValidator"), 152: ("LOAD_FAST", "berthsNeeded")})
    require(not any("Confirm" in name for name in equip["names"] + unload["names"]), "unexpected transfer confirmation plugin")
    check(processors, "TankmanUnload.__init__.<lambda>", 282, [".0"], {
        12: ("LOAD_FAST", "t"), 15: ("LOAD_CONST", None), 18: ("COMPARE_OP", 9)})
    check(processors, "TankmanUnload._request", 307, ["self", "callback"], {
        34: ("LOAD_ATTR", "equipTankman"), 43: ("LOAD_ATTR", "invID"), 49: ("LOAD_ATTR", "slot"),
        52: ("LOAD_CONST", None), 70: ("CALL_FUNCTION", 4)})
    for name, line in [("TankmanEquip._request.<lambda>", 178), ("TankmanUnload._request.<lambda>", 315)]:
        check(processors, name, line, ["code"], {3: ("LOAD_ATTR", "_response"), 6: ("LOAD_FAST", "code"), 12: ("CALL_FUNCTION", 2)})
    plugins = "client/gui/shared/gui_items/processors/plugins.pyc"
    check(plugins, "BarracksSlotsValidator._validate", 380, ["self"], {
        15: ("LOAD_ATTR", "IN_TANK"), 18: ("UNARY_INVERT", None), 34: ("LOAD_ATTR", "tankmenBerthsCount"),
        58: ("LOAD_ATTR", "berthsNeeded"), 73: ("BINARY_SUBTRACT", None),
        74: ("COMPARE_OP", 4), 83: ("LOAD_CONST", "not_enough_space")})
    check(plugins, "VehicleValidator._validate", 112, ["self"], {
        12: ("LOAD_CONST", "invalid_vehicle"), 65: ("LOAD_ATTR", "isLocked"), 74: ("LOAD_CONST", "vehicle_locked")})
    crew = "client/gui/scaleform/daapi/view/lobby/hangar/crew.pyc"
    check(crew, "Crew.equipTankman", 152, ["self", "tmanInvID", "slot"], {
        6: ("LOAD_ATTR", "getTankman"), 24: ("LOAD_GLOBAL", "TankmanEquip"),
        30: ("LOAD_GLOBAL", "g_currentVehicle"), 39: ("LOAD_FAST", "slot"), 54: ("YIELD_VALUE", None)})
    check(crew, "Crew.unloadTankman", 164, ["self", "tmanInvID"], {
        6: ("LOAD_ATTR", "getTankman"), 24: ("LOAD_GLOBAL", "TankmanUnload"),
        36: ("LOAD_ATTR", "vehicleSlotIdx"), 48: ("YIELD_VALUE", None)})
    check(crew, "Crew.unloadAllTankman", 175, ["self"], {3: ("LOAD_ATTR", "unloadCrew"), 6: ("CALL_FUNCTION", 0)})
    check(crew, "Crew.unloadCrew", 179, [], {0: ("LOAD_GLOBAL", "TankmanUnload"),
        3: ("LOAD_GLOBAL", "g_currentVehicle"), 9: ("CALL_FUNCTION", 1), 18: ("YIELD_VALUE", None)})
    check(crew, "Crew.onInventoryUpdate", 37, ["self", "invDiff"], {
        3: ("LOAD_ATTR", "TANKMAN"), 9: ("COMPARE_OP", 6), 18: ("LOAD_ATTR", "updateTankmen")})
    check(crew, "Crew.updateTankmen", 42, ["self"], {
        200: ("LOAD_ATTR", "crewRoles"), 244: ("LOAD_CONST", None), 247: ("LOAD_CONST", "tankmanID"),
        336: ("LOAD_CONST", "slot"), 432: ("LOAD_ATTR", "isInTank"),
        441: ("LOAD_ATTR", "vehicleInvID"), 450: ("COMPARE_OP", 3),
        1034: ("LOAD_ATTR", "as_tankmenResponseS"), 1037: ("LOAD_FAST", "roles"), 1040: ("LOAD_FAST", "tankmenData")})
    barracks = "client/gui/scaleform/daapi/view/lobby/barracks/barracks.pyc"
    check(barracks, "Barracks.unloadTankman", 319, ["self", "invID"], {
        6: ("LOAD_ATTR", "getTankman"), 56: ("LOAD_ATTR", "getVehicle"), 62: ("LOAD_ATTR", "vehicleInvID"),
        106: ("LOAD_GLOBAL", "TankmanUnload"), 115: ("LOAD_ATTR", "vehicleSlotIdx"), 127: ("YIELD_VALUE", None)})
    check(barracks, "Barracks._populate", 39, ["self"], {
        48: ("LOAD_ATTR", "onSyncCompleted"), 54: ("LOAD_ATTR", "_Barracks__updateTankmen"),
        77: ("LOAD_CONST", "inventory.8"), 87: ("LOAD_CONST", "stats.berths")})
    check("client/gui/shared/gui_items/vehicle.pyc", "Vehicle._buildCrew", 265, ["self", "crew", "proxy"], {
        49: ("LOAD_CONST", None), 55: ("LOAD_FAST", "tankmanID"), 58: ("LOAD_CONST", None),
        61: ("COMPARE_OP", 9), 100: ("LOAD_CONST", "compDescr"),
        137: ("LOAD_FAST", "idx"), 140: ("LOAD_FAST", "tankman"), 143: ("BUILD_TUPLE", 2)})
    check("client/gui/shared/gui_items/tankman.pyc", "Tankman.__init__", 116,
        ["self", "strCompactDescr", "inventoryID", "vehicle", "proxy"], {
            147: ("LOAD_CONST", -1), 153: ("STORE_ATTR", "vehicleInvID"), 177: ("LOAD_CONST", -1),
            183: ("STORE_ATTR", "vehicleSlotIdx"), 243: ("LOAD_ATTR", "crewIndices"), 273: ("LOAD_ATTR", "crewRoles")})
    check("client/gui/shared/utils/requesters/itemsrequester.pyc", "ItemsRequester.__makeTankman", 677,
        ["self", "tmanInvID", "tmanInvData"], {36: ("LOAD_CONST", None), 45: ("LOAD_ATTR", "vehicle"),
            48: ("LOAD_CONST", 0), 51: ("COMPARE_OP", 4), 60: ("LOAD_ATTR", "getVehicle")})
    check("client/account_helpers/diff_utils.pyc", "synchronizeDicts", 7, ["diff", "cache"], {
        315: ("LOAD_CONST", None), 318: ("COMPARE_OP", 8), 327: ("LOAD_ATTR", "pop"),
        349: ("LOAD_GLOBAL", "dict"), 376: ("LOAD_GLOBAL", "synchronizeDicts"),
        397: ("CALL_FUNCTION", 2), 490: ("LOAD_FAST", "value"), 499: ("STORE_SUBSCR", None)})
    check("common/items/tankmen.pyc", "<module>", 1, [], {
        177: ("LOAD_CONST", "reserved"), 180: ("LOAD_CONST", "commander"), 183: ("LOAD_CONST", "radioman"),
        186: ("LOAD_CONST", "driver"), 189: ("LOAD_CONST", "gunner"), 192: ("LOAD_CONST", "loader"),
        360: ("BUILD_TUPLE", 61), 363: ("STORE_NAME", "SKILL_NAMES"), 375: ("LOAD_NAME", "enumerate"),
        378: ("LOAD_NAME", "SKILL_NAMES"), 391: ("STORE_NAME", "SKILL_INDICES")})

    tree = decode(raw_sources["item_defs/vehicles/ussr/ms-1.xml"], max_bytes=65536, max_depth=24, max_nodes=12000)
    crews = [row["data"] for row in tree["children"] if row["name"] == "crew"]
    require(len(crews) == 1, "MS-1 crew section differs")
    roster = [[row["name"], *_scalar(row["data"]).split()] for row in crews[0]["children"]]
    require(roster == [["commander", "gunner", "radioman", "loader"], ["driver"]], "MS-1 source roles differ")
    listed = dict(walk(decode(raw_sources["item_defs/vehicles/ussr/list.xml"], max_bytes=65536, max_depth=24, max_nodes=12000)))
    require(listed.get("/MS-1[1]/id[1]") == 13, "MS-1 source type differs")
    return {
        "commands": {"transfer": {"id": 105, "name": "CMD_EQUIP_TMAN", "method": "doCmdInt3",
            "arguments": ["request_id", "command", "vehicle_inventory_id", "seat", "tankman_inventory_id"],
            "argument_types": prior["methods"]["doCmdInt3"]["argument_types"], "payload_struct": "<hhqii", "payload_bytes": 20,
            "single_unload_tankman_id": -1, "whole_unload_seat": -1, "whole_unload_tankman_id": -1,
            "callback_arguments": ["result_id"], "response_extension_keys_required": []},
            "return_previous_crew": {"id": 157, "method": "doCmdInt3", "arguments_after_request_and_command": ["vehicle_inventory_id", 0, 0]},
            "dismiss": {"id": 306, "same_as_unload": False}},
        "method_table_candidate": {"classification": "INFERRED", **prior["method_table_candidate"]["selected"]["doCmdInt3"],
            "framing_candidate": "VAR2 length20", "native_cmd105_capture": "NOT_RUN"},
        "inventory": {"vehicle_category": 1, "tankman_category": 8, "vehicle_crew_column": "crew",
            "empty_seat": None, "unassigned_vehicle_id": -1, "assignment_column": "vehicle",
            "descriptor_column": "compDescr", "descriptor_mutation_required": False,
            "delta_columns": {"1": ["crew"], "8": ["vehicle"]},
            "minimal_delta_semantics": "merge nested maps; replace complete crew list; None inside list is an empty seat; None map value deletes a key",
            "dossier": "unchanged embedded descriptor.dossierCompactDescr"},
        "native_processors": {"occupied_replacement_admitted": True, "equip_has_barracks_validator": False,
            "unload_checks_barracks_capacity": True, "whole_unload_counts_present_members": True,
            "vehicle_locked_rejected": True, "confirmation_plugin_on_equip_or_unload": False,
            "role_and_ownership_validation": "client processors are not authoritative; server must validate"},
        "ui": {"Crew.equipTankman": ["self", "tmanInvID", "slot"], "Crew.unloadTankman": ["self", "tmanInvID"],
            "Crew.unloadAllTankman": ["self"], "Crew.unloadCrew": [], "Barracks.unloadTankman": ["self", "invID"],
            "crew_refresh_trigger": "inventory category8", "barracks_refresh_triggers": ["inventory.8", "stats.berths", "onSyncCompleted"],
            "crew_gui_rows": "(slot, Tankman_or_None)", "empty_flash_role_tankmanID": None},
        "ms1": {"nation_id": 0, "source_vehicle_type_id": 13, "type_compact_id": 3329, "roles_by_slot": roster,
            "native_role_ids": {"commander": 1, "radioman": 2, "driver": 3, "gunner": 4, "loader": 5}},
        "account_update_order": prior["account_update_order"],
        "response_order_requirement": "publish authoritative inventory delta before matching success callback",
        "bytecode_assertions": assertions,
    }


def audit_sources(original_root: Path) -> dict:
    """Stable path-independent facts for store activation; no native export required."""
    try:
        original_root = Path(original_root)
        require(original_root.is_absolute(), "explicit absolute original root required")
        original_root = no_links(original_root).resolve(strict=True)
        require(original_root.is_dir(), "original directory required")
        raw = {name: pinned_read(no_links(original_root / "res/scripts" / name), pin) for name, pin in SOURCE_PINS.items()}
    except (ValueError, OSError, TypeError) as error:
        raise SourceAuditError("original source audit failed: " + str(error)) from error
    return {"schema_version": 1, "status": "PASS_P04F_STATIC_SOURCE_AUDIT", "classification": "VERIFIED_STATIC",
        "build": SOURCE_BUILD, "client_manifest_sha256": SOURCE_MANIFEST,
        "manifest_validation": "target identity only; all selected resources independently pinned",
        "sources": [{"source_id": "res/scripts/" + name, "bytes": pin[0], "sha256": pin[1]} for name, pin in sorted(SOURCE_PINS.items())],
        "opcode_table": {"reference_bytes": OPCODE_PIN[0], "reference_sha256": OPCODE_PIN[1], "mode": "audited CPython2.7.3 opcode subset"},
        "facts": verify_facts(raw, AUDIT_OPCODES),
        "not_run": ["native CMD105 wire capture", "native transfer and whole unload", "relogin", "UI acceptance", "server transaction"],
        "unknown": ["cross-vehicle historical retraining penalties", "cross-session replay identity"],
        "no_client_code_executed": True, "no_database_or_service_access": True}


def audit(config_path):
    config = json_value(read(no_links(config_path), 65536).removeprefix(b"\xef\xbb\xbf"), depth=12, nodes=1024)
    require(type(config) is dict and type(config.get("target")) is dict, "configured target object required")
    target = config["target"]
    require(target.get("exact_build") == SOURCE_BUILD and target.get("region") == "RU", "unexpected client build/region")
    require(target.get("client_manifest_sha256") == SOURCE_MANIFEST, "unexpected client manifest")
    paths = config.get("paths")
    require(type(paths) is dict, "configured paths required")
    for key in ("original_client_root", "local_artifacts_root"):
        require(type(paths.get(key)) is str and Path(paths[key]).is_absolute(), "configured absolute root required")
    opcode = pinned_read(no_links(Path(paths["local_artifacts_root"]) / "vendor/cpython-2.7.3/opcode.py"), OPCODE_PIN)
    table = opcode_table(opcode.decode("utf-8"))
    require(all(table.get(key) == value for key, value in AUDIT_OPCODES.items()), "opcode subset differs from pinned reference")
    return audit_sources(Path(paths["original_client_root"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = write_receipt(audit(args.config), args.out, ROOT)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, "FAIL_P04F_STATIC_SOURCE_AUDIT: " + str(error) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
