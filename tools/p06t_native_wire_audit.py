"""Closed original #717 source audit; marshal/disassembly data only, no execution."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import py27_static as ps
from packed_xml import decode
from account_contract_probe import children, scalar
from p06t_shell_catalog import no_links, build, load_sources, canonical, sha, require

ORIGINAL = Path("C:/WoT_0.9.1_RU_0717_original")
PINS = {
 "res/scripts/item_defs/vehicles/common/shot_effects.xml": (168725,"738cab95f623d7cabd8aaf811c6395ebf731a6b632e259c01dad31a2172525d3"),
 "res/scripts/entity_defs/vehicle.def": (5588,"08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297"),
 "res/scripts/entity_defs/interfaces/chat.def": (876,"3f8f0f6d14e21ece8db54af467235110eaf495b04ab404434fd69eaf66270f3d"),
 "res/scripts/client/vehicle.pyc": (24119,"b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c"),
}
METHODS = {
 "common/items/vehicles.pyc": {
  "<module>._readShotEffectGroups":"010078090a91a9f758efde5ca80b7fc37c46d4658f11c484a0e4f20f93a1f986",
  "<module>._readShell":"463526a3bb33827beefb5d95356567a7d9c602471370f38d7ab4cf5b0076a759",
  "<module>.Cache.shotEffectsIndexes":"8b76a8941f02cbd5dd7b689094329af82c6274f71c30f78cb67e66e0f482b42d",
 },
 "client/avatar.pyc": {
  "<module>.PlayerAvatar.updateVehicleAmmo":"f7e524fed66ff748ad8554082064ee8e865d21def71b18f5856f5037d18b98ba",
  "<module>.PlayerAvatar.__processVehicleAmmo":"25843e120ba32f6811a2e2c465f479608f07dce7975a47254c67e1f3861cfe8a",
  "<module>.PlayerAvatar.updateVehicleSetting":"82748b259370dcb870272354f02a0cf0eb085a38d7afc3d186c27477c055b451",
  "<module>.PlayerAvatar.onReloadPartialClipKeyDown":"9d82934110f9f21d14427136a35c0f5d6ff15e498978302e5c3d9faa1ba2bad4",
  "<module>.PlayerAvatar.updateVehicleGunReloadTime":"9f2a6d20413dd313a4fb56692f46883f307638476917745578a3443789a6b0ea",
  "<module>.PlayerAvatar.updateVehicleHealth":"1385c5e594838a7c511a31b8b55b1c58090308e0f0b51d810568a6eb9dbc78a7",
  "<module>.PlayerAvatar.showVehicleDamageInfo":"aa77c565dbdd2dbc7ae233caad744a6af598c84d8bf22a84e559be0ff81ed1ac",
  "<module>.PlayerAvatar.__showDamageIconAndPlaySound":"584d957b3707d0bc650150673173dc00c09b475c67b93a2f80cd46240b930075",
 },
 "client/vehicle.pyc": {
  "<module>.Vehicle.showDamageFromExplosion":"c8af31dd1bb8a1f3bfadc74c41fc80e16c1a105c62da69d92029968d3e8f0c0b",
  "<module>.Vehicle.showAmmoBayExplosion":"2c4e15b4b7f4c375e2de7210c8afe5c8d83d444c07954f547f9db54f6486f326",
  "<module>.Vehicle.set_isCrewActive":"edb1960c97a2bac6e0668630f644c60f09cdf779a445ced4d695d28c7301c186",
 },
}
EFFECTS = ["autoArmorPiercing","autoAPCR","smallArmorPiercing","smallHighExplosive","smallHollowCharge","smallAPCR",
 "mediumArmorPiercing","mediumHighExplosive","mediumHollowCharge","mediumAPCR","mainArmorPiercing","mainHighExplosive","mainHollowCharge","mainAPCR",
 "largeArmorPiercing","largeHighExplosive","largeHollowCharge","largeAPCR","hugeArmorPiercing","hugeHighExplosive","hugeHollowCharge","hugeAPCR","sportHighExplosive"]


def schema_tables(payloads):
    aliases={r["name"]:r["data"] for r in children(decode(payloads["res/scripts/entity_defs/alias.xml"]))}
    fixed={"UINT8":1,"INT8":1,"BOOL":1,"UINT16":2,"INT16":2,"UINT32":4,"INT32":4,"FLOAT":4,"FLOAT32":4,"UINT64":8,"INT64":8,"FLOAT64":8,"VECTOR3":12}
    def size(node,depth=0):
        require(depth<16,"schema alias depth");name=scalar(node)
        if name in fixed:return fixed[name]
        if name in aliases:return size(aliases[name],depth+1)
        attrs={r["name"]:r["data"] for r in children(node)}
        if name=="TUPLE":
            count=attrs.get("size");unit=size(attrs["of"],depth+1)
            return count*unit if isinstance(count,int) and unit is not None else None
        if name=="FIXED_DICT":
            if attrs.get("AllowNone"):return None
            widths=[size(next(r["data"] for r in children(prop["data"]) if r["name"]=="Type"),depth+1) for prop in children(attrs["Properties"])]
            return None if None in widths else sum(widths)
        return None
    tables={}
    for entity in ("avatar","vehicle"):
        groups={"ClientMethods":[],"BaseMethods":[]};seen=set()
        def walk(name):
            require(name not in seen and len(seen)<16,"schema interface bound");seen.add(name)
            node=decode(payloads["res/scripts/entity_defs/"+name])
            for g in children(node):
                if g["name"]=="Implements":
                    for r in children(g["data"]):walk("interfaces/"+scalar(r["data"]).lower()+".def")
            for g in children(node):
                if g["name"] not in groups:continue
                for m in children(g["data"]):
                    attrs=children(m["data"])
                    if g["name"]=="BaseMethods" and not any(r["name"]=="Exposed" for r in attrs):continue
                    args=[r["data"] for r in attrs if r["name"]=="Arg"];widths=list(map(size,args))
                    groups[g["name"]].append({"name":m["name"],"args":args,"bytes":None if None in widths else sum(widths)})
        walk(entity+".def")
        for group,rows in groups.items():
            rows.sort(key=lambda row:(row["bytes"] is None,row["bytes"] or 0))
            for i,row in enumerate(rows):row["candidate_wire_id"]=(0x3b if group=="ClientMethods" else 0x86)+i
        tables[entity]=groups
    props=[]
    for g in children(decode(payloads["res/scripts/entity_defs/vehicle.def"])):
        if g["name"]!="Properties":continue
        for p in children(g["data"]):
            attrs={r["name"]:r["data"] for r in children(p["data"])}
            if scalar(attrs["Flags"])=="ALL_CLIENTS":props.append({"name":p["name"],"bytes":size(attrs["Type"])})
    props.sort(key=lambda row:(row["bytes"] is None,row["bytes"] or 0))
    for i,p in enumerate(props):p["wire_id"]=0x9e+i
    return tables,props


def audit():
    payloads=load_sources(ORIGINAL)
    for relative,(count,digest) in PINS.items():
        path=ORIGINAL/relative
        require(path.is_file() and not path.is_symlink() and path.stat().st_size==count,"source file size/link: "+relative)
        raw=path.read_bytes();require(sha(raw)==digest,"source pin: "+relative);payloads[relative]=raw
    opcode=ROOT/"local/vendor/cpython-2.7.3/opcode.py"
    require(sha(opcode.read_bytes())=="acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884","pinned CPython2.7.3 opcode table")
    table=ps.opcode_table(opcode.read_text())
    methods={};assertions=[]
    for relative,targets in METHODS.items():
        found={name:c for name,c in ps.records(ps.parse_pyc(payloads["res/scripts/"+relative])) if name in targets}
        require(set(found)==set(targets),"source methods missing")
        for name,c in found.items():
            require(sha(c["code"])==targets[name],"source method changed: "+name)
            methods[(relative,name)]={"source":relative,"method":name,"source_line":c["firstlineno"],"code_sha256":targets[name],"varnames":ps.text(c["varnames"]),"instructions":ps.disassemble(c,table)}
    def op(path,name,offset,opcode,value=None):
        name="<module>."+name
        row=next(i for i in methods[(path,name)]["instructions"] if i["offset"]==offset)
        require(row["opname"]==opcode and row.get("value",row.get("arg"))==value,"original instruction assertion: "+name+":"+str(offset))
        assertions.append({"method":name,"offset":offset,"opcode":opcode,"value":value})
    for offset,opcode,value in [(3,"BUILD_LIST",0),(122,"LOAD_GLOBAL","len"),(128,"LOAD_CONST",1),(135,"STORE_FAST","index"),(195,"LOAD_FAST","index"),(205,"LOAD_FAST","sname"),(208,"STORE_SUBSCR",None),(216,"LOAD_ATTR","append")]:
        op("common/items/vehicles.pyc","_readShotEffectGroups",offset,opcode,value)
    for offset,opcode,value in [(677,"LOAD_CONST","effects"),(689,"LOAD_ATTR","shotEffectsIndexes"),(695,"LOAD_FAST","effName"),(742,"LOAD_FAST","v"),(748,"LOAD_CONST","effectsIndex")]:
        op("common/items/vehicles.pyc","_readShell",offset,opcode,value)
    for offset,opcode,value in [(134,"LOAD_GLOBAL","VEHICLE_SETTING"),(137,"LOAD_ATTR","RELOAD_PARTIAL_CLIP"),(140,"LOAD_CONST",0),(143,"CALL_FUNCTION",2)]:
        op("client/avatar.pyc","PlayerAvatar.onReloadPartialClipKeyDown",offset,opcode,value)
    for offset,opcode,value in [(21,"LOAD_FAST","health"),(24,"LOAD_CONST",0),(27,"COMPARE_OP",4),(33,"LOAD_FAST","isCrewActive"),(36,"STORE_FAST","isAlive"),(164,"LOAD_ATTR","onCrewDeactivated"),(180,"LOAD_CONST","crew_deactivated")]:
        op("client/avatar.pyc","PlayerAvatar.updateVehicleHealth",offset,opcode,value)
    for offset,opcode,value in [(91,"LOAD_FAST","compactDescr"),(94,"LOAD_FAST","quantity"),(97,"LOAD_FAST","quantityInClip"),(100,"BUILD_TUPLE",3),(193,"LOAD_FAST","quantity"),(196,"LOAD_FAST","prevAmmo"),(199,"LOAD_CONST",1),(203,"COMPARE_OP",2)]:
        op("client/avatar.pyc","PlayerAvatar.__processVehicleAmmo",offset,opcode,value)
    for offset,opcode,value in [(72,"LOAD_CONST","fire"),(82,"LOAD_CONST","FIRE_STOPPED"),(118,"LOAD_ATTR","onFireInVehicle")]:
        op("client/avatar.pyc","PlayerAvatar.__showDamageIconAndPlaySound",offset,opcode,value)
    names=[row["name"] for row in children(decode(payloads["res/scripts/item_defs/vehicles/common/shot_effects.xml"]))]
    require(names==EFFECTS,"exact original shot-effects order")
    catalog=build({k:v for k,v in payloads.items() if k not in PINS})
    rows=[{"mount":m["id"],"shell":s["resource"],"compact_descr":s["compact_descr"],"effects_resource":s["effects_resource"],"effects_index":names.index(s["effects_resource"])} for m in catalog["mounts"] for s in m["shots"]]
    require(len(rows)==24,"closed source24 count")
    tables,properties=schema_tables(payloads)
    expected={"avatar":{"updateVehicleHealth":(0x3f,3),"updateVehicleSetting":(0x40,5),"updateVehicleAmmo":(0x44,9),"showVehicleDamageInfo":(0x45,10),"updateVehicleGunReloadTime":(0x46,12)},
        "vehicle":{"showAmmoBayExplosion":(0x3d,8),"showDamageFromExplosion":(0x40,17)}}
    methods_out=[]
    for entity,targets in expected.items():
        by_name={r["name"]:r for r in tables[entity]["ClientMethods"]}
        for name,(method_id,count) in targets.items():
            row=by_name[name];require((row["candidate_wire_id"],row["bytes"])==(method_id,count),"native candidate stable sort changed");methods_out.append(dict(entity=entity,**row))
    require([p["name"] for p in properties]==["isStrafing","isCrewActive","gunAnglesPacked","health","engineMode","publicInfo","damageStickers","publicStateModifiers"],"original stable client property ordering")
    constants=next(c for n,c in ps.records(ps.parse_pyc(payloads["res/scripts/common/constants.pyc"])) if n=="<module>")
    codes=next(ps.text(c) for c in constants["consts"] if isinstance(c,list) and ps.text(c[:4])==["DEVICE_CRITICAL","DEVICE_DESTROYED","TANKMAN_HIT","FIRE"])
    require(len(codes)==36 and codes[35]=="FIRE_STOPPED","original damage codes")
    extras=[r["name"] for r in children(next(r["data"] for r in children(decode(payloads["res/scripts/item_defs/vehicles/common/vehicle.xml"])) if r["name"]=="extras"))]
    require(len(extras)==42 and extras[3]=="fire" and extras[25]=="engineHealth" and extras[41]=="loader2Health","original extras namespace")
    return {"schema":"p06t-native-wire-source.v1","status":"PASS_STATIC_SOURCE_ONLY","source_pins":{k:{"bytes":len(v),"sha256":sha(v)}for k,v in sorted(payloads.items())},
        "methods":list(methods.values()),"instruction_assertions":assertions,"effects":dict(enumerate(names)),"shell_effects":rows,"method_layouts":methods_out,"vehicle_client_properties":properties,
        "damage_codes":dict(enumerate(codes)),"extra_indices":{i+1:name for i,name in enumerate(extras)},
        "partial_clip":"VERIFIED original Base code17 value0; scheduling remains test_lab policy",
        "positive_hp_inactive_crew":"VERIFIED owner computes health>0 AND isCrewActive; false with positiveHP calls onCrewDeactivated/postmortem",
        "quantity_convention":"INFERRED compatible with original cassette reload detection; explicit server test_lab counts include clip, no historical server claim",
        "method_ids":"INFERRED stable original size sorting; existing ammo/reload and AP route OBSERVED in prior gates; new native UI NOT_RUN",
        "public_fire_envelope":"VERIFIED PE full property0xa5 VAR1 + ARRAY signed32 count, self-contained original PE audit",
        "original_execution":False,"native":"NOT_RUN","runtime_registration":False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",required=True,type=Path);a=p.parse_args()
    out=no_links(a.out).resolve();require(out.is_relative_to(ROOT / "local") and not out.exists(),"fresh owned local output only")
    out.mkdir(parents=True)
    data=audit()
    from p06t_fire_property_audit import audit as pe_audit
    pe=pe_audit(ORIGINAL)
    (out/"fire-envelope.json").write_bytes(canonical(pe)+b"\n")
    (out/"source.json").write_bytes(canonical(data)+b"\n")
    receipt={"status":"PASS_STATIC_SOURCE_ONLY","source_files":len(data["source_pins"]),"effects":23,"shell_rows":24,"methods":len(data["methods"]),"instruction_assertions":len(data["instruction_assertions"]),
        "source_json_sha256":sha((out/"source.json").read_bytes()),"fire_pe_sha256":sha((out/"fire-envelope.json").read_bytes()),
        "fire_pe_assertions":len(pe["instruction_assertions"]),"fire_pe_pointers":len(pe["pointer_assertions"]),"original_execution":False,"native":"NOT_RUN"}
    (out/"result.json").write_bytes(canonical(receipt)+b"\n");print(json.dumps(receipt))


if __name__=="__main__":main()
