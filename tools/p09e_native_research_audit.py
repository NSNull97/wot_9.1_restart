"""Read-only exact #717 research contract audit and plain descriptor codec.

Client bytecode is parsed as bounded data, never executed. This receipt proves
source facts, not native UI or transport acceptance. No resources are exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

if __package__:
    from .py27_static import inspect, parse_pyc, records
    from .p04d_crew_source_audit import AUDIT_OPCODES
    from .packed_xml import decode, walk
else:
    from py27_static import inspect, parse_pyc, records
    from p04d_crew_source_audit import AUDIT_OPCODES
    from packed_xml import decode, walk

SOURCE_BUILD = "World of Tanks 0.9.1 RU #717"
POLICY = "test_lab.research.free-credit-xp.v1"
CONVERTER_CODE_SHA256 = "89fb933bfc007c68d34a0871c88f85fbeabffba5f7f439641f1da48063207915"
SOURCE_PINS = {
    "common/accountcommands.pyc": (5534, "ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe"),
    "common/items/vehicles.pyc": (125668, "805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6"),
    "common/items/__init__.pyc": (4303, "587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176"),
    "client/account.pyc": (45998, "bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef"),
    "client/account_helpers/shop.pyc": (25626, "84aa30eb5b1862ac4fbb08557b67ad36dabc9b90cc1d083a29e0e12040127b6d"),
    "client/account_helpers/inventory.pyc": (22611, "3d17842cc6fa9af05d53cc6d22dc286e6b0434356e58c6f74d5822c2dd3cbf19"),
    "client/account_helpers/stats.pyc": (12318, "79960cd768250ce4b1e7188f6353c26e2b480b29dae0ea839168dec19f73a983"),
    "client/account_helpers/accountsyncdata.pyc": (6770, "8032c14629301d79056e4b5a0bf24c60f86023199bc762b3845860c6ca16dffd"),
    "client/gui/scaleform/daapi/view/lobby/techtree/unlock.pyc": (6365, "962bfb784932dd9fc39a31e3b1818dd7f7351033084323995d39f649c35f7850"),
    "client/gui/scaleform/daapi/view/lobby/techtree/data.pyc": (28913, "18aa479d8ca1168e441616fb73fc7ea6cad2faa138fb69ba933b1ab5b79a55f2"),
    "client/gui/scaleform/daapi/view/lobby/techtree/techtree_dp.pyc": (20805, "026ac745a717382cbb893cbb24326e46d9de4cb6cff62f52c2427ce99b8707b4"),
    "client/gui/shared/gui_items/processors/module.pyc": (21142, "9ed4b67e45be92c5ff525fc3cbd407f4b2c662c2b5eb9d82db47fb5070ed5bd9"),
    "client/gui/shared/gui_items/processors/vehicle.pyc": (21686, "c2e6e1896bd3f71ab41ae89de70528a74268c7e67fe677d8bb498dc8b9c7bff2"),
    "client/gui/shared/gui_items/vehicle.pyc": (25863, "ec78e36ab100e2c2274dd69476da99a26791037c6d79d707921168b1e95ae1e8"),
    "client/gui/shared/utils/requesters/statsrequesterr.pyc": (9934, "85c35d9320332c4ccc282ac17b0786fd08bcd4a9d59275fce0e61d4758a51b34"),
    "entity_defs/account.def": (10588, "883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674"),
}

COMMANDS = {
    101: {"name": "equip", "method": "doCmdInt3", "arguments": ["vehicle_inventory_id", "component_cd", "gun_cd_or_zero"]},
    201: {"name": "unlock", "method": "doCmdInt3", "arguments": ["parent_vehicle_type_cd", "unlock_index", "zero"]},
    301: {"name": "buy_vehicle", "method": "doCmdInt4", "arguments": ["shop_revision", "vehicle_type_cd", "flags", "crew_tariff_index"]},
    302: {"name": "buy_item", "method": "doCmdInt4", "arguments": ["shop_revision", "component_cd", "count", "gold_for_credits"]},
    308: {"name": "buy_and_equip", "method": "doCmdIntArr", "arguments": ["shop_revision", "component_cd", "vehicle_inventory_id", "slot_index", "is_paid_removal", "gun_cd"]},
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, "invalid " + name)
    return value


def make_int_cd(item_type, nation_id, item_id):
    """Exact historical bit layout; bounded server input, no truncation."""
    return (_integer(item_id, 0, 65535, "item ID") << 8
            | _integer(nation_id, 0, 15, "nation ID") << 4
            | _integer(item_type, 1, 11, "item type"))


def split_int_cd(compact):
    _integer(compact, 1, 0xFFFFFF, "compact descriptor")
    kind, nation, item = compact & 15, (compact >> 4) & 15, compact >> 8
    _integer(kind, 1, 11, "item type")
    return kind, nation, item


def plain_vehicle_descriptor(vehicle_cd, chassis_cd, engine_cd, fuel_tank_cd, radio_cd, turret_gun_pairs):
    """Encode stock/custom mounted components without equipment/customization.

    Inputs are full integer CDs. Validate compatibility/ownership/weight with
    the catalog before calling: this codec proves representation only.
    Multi-position representation is supported up to the explicit project
    bound8; the caller must verify the exact vehicle's number of positions.
    """
    kind, nation, vehicle_id = split_int_cd(vehicle_cd)
    require(kind == 1 and vehicle_id <= 255, "vehicle header type/byte ID")
    require(type(turret_gun_pairs) in (tuple, list) and 1 <= len(turret_gun_pairs) <= 8,
            "turret position count")
    def component(value, expected):
        actual, component_nation, item = split_int_cd(value)
        require(actual == expected and component_nation == nation, "component type/nation")
        return item
    ids = [component(chassis_cd, 2), component(engine_cd, 5), component(fuel_tank_cd, 6), component(radio_cd, 7)]
    for pair in turret_gun_pairs:
        require(type(pair) in (tuple, list) and len(pair) == 2, "turret/gun pair shape")
        ids.extend([component(pair[0], 3), component(pair[1], 4)])
    return bytes([1 | nation << 4, vehicle_id]) + struct.pack("<" + "H" * len(ids), *ids) + b"\0"


def verify_sources(source_root):
    root = Path(source_root).resolve(strict=True)
    scripts = root / "res" / "scripts"
    raw_sources, provenance = {}, []
    for relative, (size, digest) in SOURCE_PINS.items():
        path = scripts / relative
        require(not any(p.is_symlink() for p in [path, *path.parents] if p != root.parent),
                "source link forbidden: " + relative)
        require(path.resolve(strict=True).is_relative_to(root), "source escapes original root")
        require(path.is_file() and path.stat().st_size == size, "source size mismatch: " + relative)
        with path.open("rb") as stream:
            raw = stream.read(size + 1)
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
                "source hash mismatch: " + relative)
        raw_sources[relative] = raw
        provenance.append({"path": relative, "bytes": size, "sha256": digest})
    return raw_sources, provenance


def audit(source_root):
    raw, provenance = verify_sources(source_root)
    indexed = {name: {row["qualified_name"]: row for row in inspect(data, AUDIT_OPCODES)}
               for name, data in raw.items() if name.endswith(".pyc")}
    evidence = []
    def checks(module, function, assertions):
        row = indexed[module]["<module>." + function]
        ops = {r["offset"]: r for r in row["instructions"]}
        for offset, opname, value in assertions:
            require(ops.get(offset, {}).get("opname") == opname and ops[offset].get("value") == value,
                    "source instruction mismatch: %s %s %d" % (module, function, offset))
        evidence.append({"path": module, "function": function, "source_line": row["firstlineno"],
                         "checked_offsets": [r[0] for r in assertions]})
    module_ops = indexed["common/accountcommands.pyc"]["<module>"]["instructions"]
    values = {row["value"]: module_ops[i - 1].get("value") for i, row in enumerate(module_ops)
              if row["opname"] == "STORE_NAME"}
    for name, value in [("CMD_EQUIP",101),("CMD_UNLOCK",201),("CMD_BUY_VEHICLE",301),
                        ("CMD_BUY_ITEM",302),("CMD_BUY_AND_EQUIP_ITEM",308),("RES_SUCCESS",0),
                        ("RES_WRONG_ARGS",-2),("RES_SHOP_DESYNC",-4),("RES_NOT_AVAILABLE",-10)]:
        require(values.get(name) == value, "command constant mismatch: " + name)
    checks("common/accountcommands.pyc", "BUY_VEHICLE_FLAG", [(6,"LOAD_CONST",0),(12,"LOAD_CONST",1),(18,"LOAD_CONST",16)])
    checks("client/account_helpers/stats.pyc", "Stats.unlock", [(86,"LOAD_ATTR","_doCmdInt3"),(92,"LOAD_ATTR","CMD_UNLOCK"),
        (95,"LOAD_FAST","vehTypeCompDescr"),(98,"LOAD_FAST","unlockIdx"),(101,"LOAD_CONST",0)])
    checks("client/account_helpers/inventory.pyc", "Inventory.equip", [(144,"LOAD_ATTR","_doCmdInt3"),(150,"LOAD_ATTR","CMD_EQUIP"),
        (153,"LOAD_FAST","vehInvID"),(156,"LOAD_FAST","itemCompDescr"),(159,"LOAD_CONST",0)])
    checks("client/account_helpers/inventory.pyc", "Inventory.equipTurret", [(92,"LOAD_ATTR","_doCmdInt3"),(98,"LOAD_ATTR","CMD_EQUIP"),
        (101,"LOAD_FAST","vehInvID"),(104,"LOAD_FAST","turretCompDescr"),(107,"LOAD_FAST","gunCompDescr")])
    checks("client/account_helpers/shop.pyc", "Shop.buyVehicle", [(163,"LOAD_ATTR","_doCmdInt4"),(169,"LOAD_ATTR","CMD_BUY_VEHICLE"),
        (175,"LOAD_ATTR","_Shop__getCacheRevision"),(181,"LOAD_FAST","typeCompDescr"),(184,"LOAD_FAST","flags"),(187,"LOAD_FAST","tmanCostTypeIdx")])
    checks("client/account_helpers/shop.pyc", "Shop.buy", [(151,"LOAD_ATTR","_doCmdInt4"),(157,"LOAD_ATTR","CMD_BUY_ITEM"),
        (163,"LOAD_ATTR","_Shop__getCacheRevision"),(169,"LOAD_FAST","itemShopID"),(172,"LOAD_FAST","count"),(175,"LOAD_FAST","goldForCredits")])
    checks("client/account_helpers/shop.pyc", "Shop.buyAndEquipItem", [(89,"LOAD_ATTR","_Shop__getCacheRevision"),
        (95,"LOAD_FAST","compDescr"),(98,"LOAD_FAST","vehInvID"),(101,"LOAD_FAST","slotIdx"),(104,"LOAD_FAST","isPaidRemoval"),
        (107,"LOAD_FAST","gunCompDescr"),(122,"LOAD_ATTR","_doCmdIntArr"),(128,"LOAD_ATTR","CMD_BUY_AND_EQUIP_ITEM")])
    checks("common/items/vehicles.pyc", "VehicleDescr.makeCompactDescr", [(21,"LOAD_CONST","<4H"),(27,"LOAD_ATTR","chassis"),
        (41,"LOAD_ATTR","engine"),(55,"LOAD_ATTR","fuelTank"),(69,"LOAD_ATTR","radio"),(139,"LOAD_CONST","<2H")])
    checks("common/items/vehicles.pyc", "_combineVehicleCompactDescr", [(139,"LOAD_FAST","vehicleTypeID"),(146,"LOAD_FAST","components"),
        (153,"LOAD_FAST","flags"),(160,"LOAD_FAST","optionalDevices")])
    checks("common/items/vehicles.pyc", "VehicleType.__convertAndValidateUnlocksDescrs", [(481,"LOAD_CONST",0),(485,"LOAD_FAST","compactDescr"),
        (620,"LOAD_FAST","reqItems"),(646,"LOAD_FAST","destList")])
    checks("client/account_helpers/shop.pyc", "Shop.__getPriceFromCache", [(9,"LOAD_CONST","items"),(21,"LOAD_CONST","itemPrices")])
    checks("client/account_helpers/accountsyncdata.pyc", "AccountSyncData.__onSyncResponse", [(86,"LOAD_CONST","prevRev"),
        (147,"LOAD_CONST","rev"),(180,"LOAD_ATTR","_update")])
    checks("client/gui/scaleform/daapi/view/lobby/techtree/techtree_dp.pyc", "_TechTreeDataProvider.__readNation", [
        (654,"LOAD_ATTR","unlocksDescrs"),(685,"LOAD_CONST",0),(692,"LOAD_ATTR","_TechTreeDataProvider__unlockPrices")])
    checks("client/account_helpers/stats.pyc", "Stats.synchronize", [(215,"LOAD_GLOBAL","_GROWING_SET_STATS"),
        (281,"LOAD_ATTR","setdefault"),(287,"LOAD_GLOBAL","set"),(296,"LOAD_ATTR","update"),
        (432,"LOAD_CONST",["unlocks","eliteVehicles"]),(472,"LOAD_ATTR","update")])
    checks("client/gui/shared/gui_items/vehicle.pyc", "Vehicle.__init__", [(365,"LOAD_GLOBAL","len"),
        (374,"LOAD_ATTR","unlocksDescrs"),(380,"LOAD_CONST",0),(392,"LOAD_ATTR","intCD"),
        (401,"LOAD_ATTR","eliteVehicles"),(410,"STORE_ATTR","isElite")])
    checks("client/gui/shared/utils/requesters/statsrequesterr.pyc", "StatsRequesterr.eliteVehicles", [
        (3,"LOAD_ATTR","getCacheValue"),(6,"LOAD_CONST","eliteVehicles"),(9,"LOAD_GLOBAL","list")])
    converter = dict(records(parse_pyc(raw["common/items/vehicles.pyc"])))["<module>.VehicleType.__convertAndValidateUnlocksDescrs"]
    require(hashlib.sha256(converter["code"]).hexdigest() == CONVERTER_CODE_SHA256, "converter code pin")
    definitions = {}
    tree = decode(raw["entity_defs/account.def"], max_bytes=65536, max_nodes=12000, max_depth=24)
    for name, expected in {"doCmdInt3":["INT16","INT16","INT64","INT32","INT32"],
                           "doCmdInt4":["INT16","INT16","INT64","INT32","INT32","INT32"],
                           "doCmdIntArr":["INT16","INT16","ARRAY"],
                           "onCmdResponseExt":["INT16","INT16","STRING","STRING"],"update":["STRING"]}.items():
        group = "BaseMethods" if name.startswith("doCmd") else "ClientMethods"
        method = next(row["data"] for group_row in tree["children"] if group_row["name"] == group
                      for row in group_row["data"]["children"] if row["name"] == name)
        args = [value for path, value in walk(method) if path.startswith("/Arg[") and path.count("/") == 1]
        require(args == expected, "definition argument mismatch: " + name)
        if name == "doCmdIntArr":
            require(dict(walk(method)).get("/Arg[3]/of[1]") == "INT32", "array element contract")
        definitions[name] = args
    return {"classification":"VERIFIED_SOURCE_ONLY", "native_acceptance":"NOT_RUN", "source_build":SOURCE_BUILD,
            "sources":provenance, "commands":COMMANDS, "definition_arguments":definitions,
            "vehicle_buy_flags":{"crew":1,"shells":16}, "checks":evidence,
            "xp_overlay":{"policy":POLICY,"code_sha256":CONVERTER_CODE_SHA256,"field":"unlocksDescrs[index][0]"},
            "limits":["No client execution, wire capture, or native UI acceptance", "Plain descriptor excludes optional devices and customization",
                      "Codec does not establish catalog compatibility or combat readiness"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require(not args.out.resolve().is_relative_to(args.original.resolve()), "receipt cannot be inside original client")
    result = audit(args.original)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"result":"PASS_SOURCE_ONLY","source_files":len(result["sources"]),"receipt":str(args.out),"native":"NOT_RUN"}))


if __name__ == "__main__":
    main()
