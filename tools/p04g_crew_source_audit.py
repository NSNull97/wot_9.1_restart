"""Bounded static #717 cross-vehicle crew and GUI specialization audit.

Original bytecode is data, never executed. Static GUI factors are not battle
characteristics, original server validation, or native cross-vehicle acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from . import p04f_crew_source_audit as baseline
    from .crew_equipment_source_audit import ROSTERS, VEHICLE_IDS, VEHICLE_TAGS
else:
    import p04f_crew_source_audit as baseline
    from crew_equipment_source_audit import ROSTERS, VEHICLE_IDS, VEHICLE_TAGS

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD, SOURCE_MANIFEST = baseline.SOURCE_BUILD, baseline.SOURCE_MANIFEST
OPCODE_PIN = baseline.OPCODE_PIN
pinned_read, write_receipt = baseline.pinned_read, baseline.write_receipt
SOURCE_PINS = dict(baseline.SOURCE_PINS, **{
    "item_defs/vehicles/ussr/is-7.xml": (5809, "8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d"),
    "client/gui/scaleform/daapi/view/lobby/hangar/tankcarousel.pyc":
        (12529, "84e023be8befc58478600084811bc753ec670dee0fdf0f1982fa1bd66e596e8a"),
})
AUDIT_OPCODES = dict(baseline.AUDIT_OPCODES)
AUDIT_OPCODES.update({20:"BINARY_MULTIPLY",21:"BINARY_DIVIDE",23:"BINARY_ADD",24:"BINARY_SUBTRACT",64:"BINARY_AND",113:"JUMP_ABSOLUTE"})


class SourceAuditError(ValueError):
    """A source pin, static anchor or bounded input differs."""


def require(condition, message):
    if not condition:
        raise SourceAuditError(message)


def verify_facts(raw_sources, table):
    require(type(raw_sources) is dict and set(raw_sources) == set(SOURCE_PINS), "exact source set required")
    for name, (size, sha) in SOURCE_PINS.items():
        raw = raw_sources[name]
        require(type(raw) is bytes and len(raw) == size and hashlib.sha256(raw).hexdigest() == sha,
                "source pin mismatch: " + name)
    try:
        prior = baseline.verify_facts({name:raw_sources[name] for name in baseline.SOURCE_PINS}, table)
    except baseline.SourceAuditError as error:
        raise SourceAuditError(str(error)) from error
    parsed, codes, anchors = {}, {}, []

    def check(source, name, line, args, expected):
        if source not in parsed:
            parsed[source] = baseline.inspect(raw_sources[source], table)
            codes[source] = list(baseline.records(baseline.parse_pyc(raw_sources[source])))
        qualified = name if name == "<module>" else "<module>." + name
        rows = [r for r in parsed[source] if r["qualified_name"] == qualified]
        records = [r for q,r in codes[source] if q == qualified]
        require(len(rows) == len(records) == 1, "ambiguous/missing source record: " + name)
        row, code = rows[0], records[0]
        require(row["firstlineno"] == line and code["argcount"] == len(args)
                and row["varnames"][:len(args)] == args, "source signature differs: " + name)
        instructions = {r["offset"]:r for r in row["instructions"]}
        for offset,(op,value) in expected.items():
            ins = instructions.get(offset)
            require(ins is not None and ins["opname"] == op and ins.get("value",ins.get("arg")) == value,
                    "bytecode semantic anchor differs: " + name + ":" + str(offset))
        anchors.append({"source_id":"res/scripts/"+source,"record":qualified,
            "source_filename":row["source_filename"],"firstlineno":line,
            "marshal_offset_plus_pyc_header":code["marshal_offset"]+8,"argument_names":args,
            "local_names":row["varnames"],"code_bytes":len(code["code"]),
            "code_sha256":hashlib.sha256(code["code"]).hexdigest(),"verified_offsets":sorted(expected)})
        return row

    processor = "client/gui/shared/gui_items/processors/tankman.pyc"
    row = check(processor,"TankmanEquip.__init__",126,["self","tankman","vehicle","slot"],{
        142:("LOAD_ATTR","VehicleValidator"),148:("LOAD_GLOBAL","False"),160:("LOAD_CONST","isLocked"),
        170:("LOAD_ATTR","ModuleValidator"),182:("LOAD_ATTR","ModuleTypeValidator"),191:("LOAD_ATTR","TANKMAN"),
        200:("BUILD_LIST",3),203:("CALL_FUNCTION",1)})
    require(not any(n in row["names"] for n in ("FreeTankmanValidator","CompatibilityValidator","BarracksSlotsValidator"))
            and not any("Confirm" in n for n in row["names"]), "equip plugin contract differs")
    plugins = "client/gui/shared/gui_items/processors/plugins.pyc"
    check(plugins,"VehicleValidator.__init__",102,["self","vehicle","setAll","prop","isEnabled"],{
        49:("LOAD_CONST","isBroken"),52:("LOAD_GLOBAL","False"),61:("LOAD_FAST","setAll"),
        76:("LOAD_CONST","isLocked"),94:("STORE_ATTR","isLocked"),
        103:("LOAD_CONST","isInInventory"),115:("LOAD_FAST","setAll")})
    check(plugins,"ModuleValidator._validate",176,["self"],{3:("LOAD_ATTR","module"),12:("LOAD_CONST","invalid_module"),19:("LOAD_GLOBAL","makeSuccess")})
    check(plugins,"ModuleTypeValidator._validate",196,["self"],{
        6:("LOAD_ATTR","itemTypeID"),12:("LOAD_ATTR","allowableTypes"),15:("COMPARE_OP",7),24:("LOAD_CONST","invalid_module_type")})
    crew = "client/gui/scaleform/daapi/view/lobby/hangar/crew.pyc"
    check(crew,"Crew.updateTankmen",42,["self"],{
        200:("LOAD_ATTR","crewRoles"),203:("LOAD_FAST","slotIdx"),207:("LOAD_CONST",0),210:("BINARY_SUBSCR",None),
        382:("LOAD_ATTR","crewRoles"),392:("LOAD_CONST","roles"),432:("LOAD_ATTR","isInTank"),
        441:("LOAD_ATTR","vehicleInvID"),447:("LOAD_ATTR","invID"),450:("COMPARE_OP",3),456:("JUMP_ABSOLUTE",423),
        773:("LOAD_ATTR","realRoleLevel"),780:("LOAD_CONST","specializationLevel"),903:("LOAD_ATTR","role"),
        906:("LOAD_CONST","roleType"),923:("LOAD_ATTR","efficiencyRoleLevel"),926:("LOAD_CONST","efficiencyLevel")})
    check("client/gui/scaleform/daapi/view/lobby/hangar/tankcarousel.pyc","TankCarousel.vehicleChange",114,["self","vehInvID"],{
        0:("LOAD_GLOBAL","g_currentVehicle"),3:("LOAD_ATTR","selectVehicle"),6:("LOAD_GLOBAL","int"),9:("LOAD_FAST","vehInvID"),15:("CALL_FUNCTION",1)})
    tankman = "client/gui/shared/gui_items/tankman.pyc"
    check(tankman,"Tankman.__init__",116,["self","strCompactDescr","inventoryID","vehicle","proxy"],{
        99:("LOAD_ATTR","role"),108:("STORE_ATTR","combinedRoles"),132:("LOAD_ATTR","vehicleTypeID"),144:("STORE_ATTR","vehicleNativeDescr"),
        153:("STORE_ATTR","vehicleInvID"),207:("STORE_ATTR","vehicleInvID"),219:("STORE_ATTR","vehicleDescr"),
        273:("LOAD_ATTR","crewRoles"),322:("LOAD_ATTR","vehicleSlotIdx"),329:("STORE_ATTR","combinedRoles")})
    check(tankman,"Tankman.roleLevel",249,["self"],{3:("LOAD_ATTR","descriptor"),6:("LOAD_ATTR","roleLevel")})
    check(tankman,"Tankman.efficiencyRoleLevel",351,["self"],{
        0:("LOAD_CONST",[1,0]),15:("LOAD_ATTR","isInTank"),27:("LOAD_ATTR","efficiencyOnVehicle"),
        33:("LOAD_ATTR","vehicleDescr"),51:("LOAD_GLOBAL","round"),57:("LOAD_ATTR","roleLevel"),
        60:("LOAD_FAST","factor"),63:("BINARY_MULTIPLY",None),64:("CALL_FUNCTION",1)})
    check(tankman,"Tankman.realRoleLevel",185,["self"],{
        3:("LOAD_ATTR","efficiencyRoleLevel"),18:("BINARY_SUBTRACT",None),19:("STORE_FAST","penalty"),
        58:("LOAD_ATTR","COMMANDER"),67:("LOAD_CONST",0),70:("STORE_FAST","commBonus"),
        139:("LOAD_FAST","effRoleLevel"),142:("LOAD_FAST","commBonus"),145:("BINARY_ADD",None),
        158:("STORE_FAST","realRoleLevel"),176:("LOAD_FAST","penalty"),179:("BUILD_TUPLE",5),182:("BUILD_TUPLE",2)})
    source = "common/items/tankmen.pyc"
    check(source,"TankmanDescr.efficiencyOnVehicle",478,["self","vehicleDescr"],{
        24:("LOAD_ATTR","nationID"),27:("COMPARE_OP",2),33:("LOAD_GLOBAL","AssertionError"),39:("LOAD_CONST",1.0),
        51:("LOAD_ATTR","vehicleTypeID"),54:("COMPARE_OP",3),63:("LOAD_ATTR","_TankmanDescr__paramsOnVehicle"),
        84:("LOAD_FAST","isSameClass"),90:("LOAD_FAST","isPremium"),96:("LOAD_CONST",1.0),102:("LOAD_CONST",0.75),
        111:("LOAD_FAST","isPremium"),117:("LOAD_CONST",0.75),123:("LOAD_CONST",0.5),126:("STORE_FAST","factor"),
        138:("LOAD_CONST","crewLevelIncrease"),145:("LOAD_FAST","factor"),148:("LOAD_FAST","addition"),151:("BUILD_TUPLE",2)})
    check(source,"TankmanDescr.__paramsOnVehicle",882,["self","vehicleType"],{
        0:("LOAD_CONST","premium"),6:("LOAD_ATTR","tags"),9:("COMPARE_OP",6),
        18:("LOAD_GLOBAL","VEHICLE_CLASS_TAGS"),27:("BINARY_AND",None),31:("LOAD_ATTR","_TankmanDescr__vehicleTags"),34:("BINARY_AND",None)})
    check(source,"<module>",1,[],{709:("LOAD_CONST",10),712:("STORE_NAME","COMMANDER_ADDITION_RATIO")})
    check("client/gui/shared/gui_items/vehicle.pyc","Vehicle._calcCrewBonuses",217,["self","crew","proxy"],{
        339:("LOAD_ATTR","efficiencyOnVehicle"),360:("LOAD_GLOBAL","round"),366:("LOAD_ATTR","roleLevel"),
        369:("LOAD_FAST","factor"),372:("BINARY_MULTIPLY",None),373:("LOAD_FAST","addition"),376:("BINARY_ADD",None),
        425:("LOAD_ATTR","COMMANDER_ADDITION_RATIO"),428:("BINARY_DIVIDE",None),429:("CALL_FUNCTION",1)})

    listed = dict(baseline.walk(baseline.decode(raw_sources["item_defs/vehicles/ussr/list.xml"],max_bytes=65536,max_depth=24,max_nodes=12000)))
    vehicles = []
    for name, expected in ROSTERS.items():
        tree = baseline.decode(raw_sources["item_defs/vehicles/ussr/"+name.lower()+".xml"],max_bytes=65536,max_depth=24,max_nodes=12000)
        crews = [row["data"] for row in tree["children"] if row["name"] == "crew"]
        require(len(crews) == 1,"one crew roster required")
        roles = tuple((row["name"],*baseline._scalar(row["data"]).split()) for row in crews[0]["children"])
        tags = tuple(baseline._scalar(listed.get("/"+name+"[1]/tags[1]")).split())
        require(roles == expected and tags == VEHICLE_TAGS[name]
                and listed.get("/"+name+"[1]/id[1]") == VEHICLE_IDS[name],"vehicle roster/type/class source differs")
        vehicles.append({"source_name":"ussr:"+name,"nation_id":0,"source_vehicle_type_id":VEHICLE_IDS[name],
            "type_compact_id":VEHICLE_IDS[name]*256+1,"roles_by_slot":[list(r) for r in roles],
            "primary_roles_by_slot":[r[0] for r in roles],"tags":list(tags),"premium":"premium" in tags})
    return {"commands":prior["commands"],"inventory":prior["inventory"],"ui":prior["ui"],
        "vehicles":vehicles,"native_role_ids":prior["ms1"]["native_role_ids"],
        "selection":{"other_vehicle_seated_members_excluded":True,"barracks_members_in_candidate_data":True,
            "primary_role_field":"crewRoles[slot][0]","combined_roles_field":"crewRoles[slot]",
            "native_path":"unload source member; select target via TankCarousel.vehicleChange; equip member from barracks",
            "direct_seated_transfer_selectable_in_Crew":False,"original_server_direct_transfer":"UNKNOWN"},
        "processor":{"validators":["target vehicle existence and isLocked","tankman existence","itemTypeID=TANKMAN"],
            "checks_source_assignment":False,"checks_specialization":False,"checks_primary_role":False,
            "confirmation_plugin":False,"server_authority_required":True},
        "gui_specialization":{"same_nation_required":True,"same_trained_type_factor":"1",
            "different_type_factors":{"same_class_premium":"1","same_class_nonpremium":"0.75",
                "different_class_premium":"0.75","different_class_nonpremium":"0.5"},
            "efficiency_property":"Tankman.efficiencyRoleLevel","formula":"Python2 round(roleLevel * factor)",
            "unassigned_factor":"1","ms1_trained_level100":{"barracks":100,"MS-1":100,"IS-7":50},
            "descriptor_roleLevel_property":"Tankman.roleLevel","trained_type_property":"Tankman.descriptor.vehicleTypeID",
            "assigned_descriptor_property":"Tankman.vehicleDescr","combined_roles_property":"Tankman.combinedRoles",
            "combined_roles_in_barracks":"descriptor primary role only","display_includes_other_bonuses":True,
            "base_penalty_level100_on_IS7":-50,"commander_addition_ratio":10,
            "battle_characteristics":"UNKNOWN; GUI evidence is not combat acceptance"},
        "transfer_request_contains_new_descriptor":False,"baseline_assertions":prior["bytecode_assertions"],
        "bytecode_assertions":anchors}


def audit_sources(original_root: Path):
    try:
        require(isinstance(original_root,Path) and original_root.is_absolute(),"explicit absolute original root required")
        original_root = baseline.no_links(original_root).resolve(strict=True)
        require(original_root.is_dir(),"original directory required")
        raw = {name:pinned_read(baseline.no_links(original_root/"res/scripts"/name),pin) for name,pin in SOURCE_PINS.items()}
    except (ValueError,OSError,TypeError) as error:
        raise SourceAuditError("original source audit failed: "+str(error)) from error
    return {"schema_version":1,"status":"PASS_P04G_STATIC_SOURCE_AUDIT","classification":"VERIFIED_STATIC",
        "build":SOURCE_BUILD,"client_manifest_sha256":SOURCE_MANIFEST,
        "manifest_validation":"target identity only; selected resources independently pinned",
        "sources":[{"source_id":"res/scripts/"+name,"bytes":pin[0],"sha256":pin[1]} for name,pin in sorted(SOURCE_PINS.items())],
        "opcode_table":{"reference_bytes":OPCODE_PIN[0],"reference_sha256":OPCODE_PIN[1],"mode":"audited CPython2.7.3 opcode subset"},
        "facts":verify_facts(raw,AUDIT_OPCODES),"not_run":["native cross-vehicle transfer","GUI penalty display","relogin","server transaction"],
        "unknown":["original server validation beyond client bytecode","combat characteristics with cross-specialization"],
        "no_client_code_executed":True,"no_database_or_service_access":True}


def audit(config_path):
    # Reuse the closed build/region/manifest/path/opcode checks; G adds its own pins.
    try:
        baseline.audit(config_path)
        config = baseline.json_value(baseline.read(baseline.no_links(config_path),65536).removeprefix(b"\xef\xbb\xbf"),depth=12,nodes=1024)
        opcode = pinned_read(baseline.no_links(Path(config["paths"]["local_artifacts_root"])/"vendor/cpython-2.7.3/opcode.py"),OPCODE_PIN)
        table = baseline.opcode_table(opcode.decode("utf-8"))
        require(all(table.get(k) == v for k,v in AUDIT_OPCODES.items()),"opcode subset differs")
        return audit_sources(Path(config["paths"]["original_client_root"]))
    except baseline.SourceAuditError as error:
        raise SourceAuditError(str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    try:
        receipt = write_receipt(audit(args.config),args.out,ROOT)
    except (ValueError,OSError,KeyError,TypeError) as error:
        parser.exit(1,"FAIL_P04G_STATIC_SOURCE_AUDIT: "+str(error)+"\n")
    print(json.dumps(receipt,sort_keys=True))


if __name__ == "__main__": main()
