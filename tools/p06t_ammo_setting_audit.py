"""Read-only original setting shape/caller audit; new native UI remains NOT_RUN."""
import argparse
import json
from pathlib import Path
from p06t_shell_catalog import no_links, ROOT, HERE, load_sources, canonical, sha, require
from packed_xml import decode, walk
from py27_static import parse_pyc, records, disassemble, opcode_table


def audit(payloads):
    avatar = dict(walk(decode(payloads["res/scripts/entity_defs/avatar.def"], max_bytes=262144)))
    prefix = "/BaseMethods[1]/vehicle_changeSetting[1]"
    require(avatar[prefix + "/Arg[1]"] == "UINT8" and avatar[prefix + "/Arg[2]"] == "INT32"
            and prefix + "/Arg[3]" not in avatar and prefix + "/Exposed[1]" in avatar, "original setting .def shape")
    targets = {
        "common/constants.pyc": {"<module>.VEHICLE_SETTING": "01d23513fea9fe561004744bd17d96ce98c61aa1823530f1414cc84ba43d4ae0"},
        "client/avatar.pyc": {
            "<module>.PlayerAvatar.onAmmoButtonPressed": "46dafd9ab8965d898c741397d38588ff0824ca81432617ef21e219486f87c541",
            "<module>.PlayerAvatar.updateVehicleSetting": "82748b259370dcb870272354f02a0cf0eb085a38d7afc3d186c27477c055b451",
            "<module>.PlayerAvatar.onReloadPartialClipKeyDown": "9d82934110f9f21d14427136a35c0f5d6ff15e498978302e5c3d9faa1ba2bad4",
        },
    }
    methods = []
    table = opcode_table((ROOT / "local/vendor/cpython-2.7.3/opcode.py").read_text())
    settings = None
    for path, names in targets.items():
        found = {name: r for name, r in records(parse_pyc(payloads["res/scripts/" + path])) if name in names}
        require(set(found) == set(names), "original setting methods missing")
        for name, r in found.items():
            require(sha(r["code"]) == names[name], "original setting method body differs")
            methods.append(dict(path=path, method=name, source_line=r["firstlineno"], code_sha256=names[name]))
            if name.endswith(".VEHICLE_SETTING"):
                instructions = disassemble(r, table)
                settings = {i["value"]: instructions[n - 1]["value"] for n, i in enumerate(instructions)
                            if i["opname"] == "STORE_NAME" and i["value"] != "__module__"}
    require(settings == dict(CURRENT_SHELLS=0, NEXT_SHELLS=1, AUTOROTATION_ENABLED=2, ACTIVATE_EQUIPMENT=16, RELOAD_PARTIAL_CLIP=17), "setting enum values")
    from p06t_native_wire_audit import schema_tables, PINS, ORIGINAL
    extended = dict(payloads)
    for name in ("res/scripts/entity_defs/vehicle.def", "res/scripts/entity_defs/interfaces/chat.def"):
        path=ORIGINAL/name;count,digest=PINS[name]
        require(path.stat().st_size==count,"source schema file size")
        raw=path.read_bytes();require(sha(raw)==digest,"source schema file pin");extended[name]=raw
    tables,_=schema_tables(extended)
    row = next(r for r in tables["avatar"]["BaseMethods"] if r["name"] == "vehicle_changeSetting")
    require(row["args"] == ["UINT8", "INT32"] and row["bytes"] == 5 and row["candidate_wire_id"] == 0x8d, "stable candidate table differs")
    return dict(schema="p06t-original-ammo-setting-source.v1", status="PASS_STATIC_SHAPE_AND_CALLER",
        base_method="vehicle_changeSetting", argument_types=["UINT8", "INT32"], payload_bytes=5, settings=settings,
        candidate_wire_id=0x8d, wire_id_classification="INFERRED_STABLE_METHOD_TABLE; existing automatic setting route OBSERVED; new ammo UI NOT_RUN",
        existing_record_shape="8d 05 00 <code:u8> <compactDescr:i32le>", original_methods=methods,
        source_files=len(payloads), original_bytecode_executed=False, new_native_ammo_ui="NOT_RUN",
        partial_clip_reload="VERIFIED_ORIGINAL_CALLER_CODE17_VALUE0; SERVER_SCHEDULER_TEST_LAB")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    out = no_links(args.out).resolve()
    require(out.is_relative_to(ROOT / "local") and not out.exists(), "fresh local audit output required")
    result = audit(load_sources(args.original))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(canonical(result) + b"\n")
    print(json.dumps(dict(status=result["status"], bytes=out.stat().st_size, sha256=sha(out.read_bytes()), native="NOT_RUN")))


if __name__ == "__main__":
    main()
