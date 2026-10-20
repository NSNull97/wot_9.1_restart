"""Closed #717 shell/clip data importer. No original code is executed.

Preparation only: this module registers no runtime profile or owned ammunition.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "tools/packed_xml.py").is_file() and (p / "docs/ACTIVE_GATE.md").is_file())
sys.path.insert(0, str(ROOT / "tools"))
from packed_xml import decode, walk
from py27_static import parse_pyc, records, disassemble, opcode_table
from vehicle_physics_profile import no_links
from p06t_source_pins import SOURCE_PINS

SCHEMA = "p06t-shell-catalog.v1"
MAX_SOURCE = 256 * 1024
MAX_TOTAL = 1024 * 1024
MAX_EXPORT = 128 * 1024
NATIONS = ("ussr", "germany", "usa", "china", "france", "uk", "japan")
FAMILIES = ("ARMOR_PIERCING", "ARMOR_PIERCING_CR", "HOLLOW_CHARGE", "HIGH_EXPLOSIVE")
PREFIX = "res/scripts/item_defs/vehicles/"
METHOD_HASHES = {
    "_readGun": "80b2e121b6ce74a5c89edbf5cb1ebb6c1f1202edc2c635a0a0519b84f19ec625",
    "_readGunClipBurst": "aeff9e429b92c75b99cff23d74cebd8a5d0616399802cc28347a85831f764b8b",
    "_readShot": "c4f1a10ec84e8f52097ef180e95cb701022ee1a1efffb70513eede2e9682e781",
    "makeIntCompactDescrByID": "00d04a6b4859de88a86d352887866a0947dfe6d6b35a105c2d6f17e71a484ee8",
}
# Exact selected mounts, not a generic arbitrary-vehicle loader. Single-shot
# clip default1/0 is independently verified in the inert original _readGun.
MOUNTS = (
    ("ms1-stock", "ussr", "MS-1", "ms-1", "T-18_Standart", "_37mm_Gochkins", 96, 2.5, 1, 0., ("_37mm_UBRT1", "_37mm_BPT1", "_37mm_UOT1")),
    ("is7-stock", "ussr", "IS-7", "is-7", "IS-7", "_130mm_S-70", 30, 13.7, 1, 0., ("_130mm_UBR-482", "_130mm_UBR-482P", "_130mm_UOF-482")),
    ("t26-stock", "ussr", "T-26", "t-26", "T-26_cylindrical", "_37mm_B-3", 160, 2.3, 1, 0., ("_37mm_UBR-160", "_37mm_UBR-160P", "_37mm_UOF-160")),
    ("t34-stock", "ussr", "T-34", "t-34", "T-34_mod_1940", "_76mm_L-11", 77, 6., 1, 0., ("_76mm_UBR-354A", "_76mm_BP-354", "_76mm_UOF-354")),
    ("t3485-stock", "ussr", "T-34-85", "t-34-85", "T-34-85", "_76mm_S-54", 68, 4.1, 1, 0., ("_76mm_UBR-354MA", "_76mm_UBR-354MP", "_76mm_UOF-354M")),
    ("wt-e100-128", "germany", "Waffentrager_E100", "waffentrager_e100", "Turret_1_Waffentrager_E100", "_128mm_K44_2_L61", 60, 60., 6, 2., ("_128mm_PzGr39L", "_128mm_PzGr43", "_128mm_SprG19")),
    ("wt-e100-150", "germany", "Waffentrager_E100", "waffentrager_e100", "Turret_1_Waffentrager_E100", "_150mm_Rohr_L38", 60, 50., 4, 3., ("_150mm_PzGr42", "_150mmGr_39H3A_G", "_150mm_SprgG_ausf_45")),
    ("fv215b-183", "uk", "GB48_FV215b_183", "gb48_fv215b_183", "Turret_1_GB48_FV215b_183", "_183mm_AT_Gun", 12, 30., 1, 0., ("_183mm_AP_Mk1", "_183mm_HESH", "_183mm_HE_Mk1")),
)


class SourceError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise SourceError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded_number(value, label, maximum, *, zero=False):
    require(type(value) in (int, float, str), "missing/non-number: " + label)
    try:
        result = float(value)
    except (ValueError, OverflowError) as error:
        raise SourceError("invalid number: " + label) from error
    require(math.isfinite(result) and (0 <= result if zero else 0 < result) and result <= maximum, "number bound: " + label)
    return result


def integer(value, label, maximum, *, zero=False):
    n = bounded_number(value, label, maximum, zero=zero)
    require(n == int(n), "noninteger: " + label)
    return int(n)


def pair(value, label):
    raw = value.split() if type(value) is str else value
    require(type(raw) is list and len(raw) == 2, "source pair: " + label)
    return [bounded_number(v, label, 1000, zero=True) for v in raw]


def verify_sources(payloads):
    require(type(payloads) is dict and set(payloads) == set(SOURCE_PINS), "exact closed source set")
    require(sum(len(v) for v in payloads.values() if type(v) is bytes) <= MAX_TOTAL, "total source budget")
    for name, pin in SOURCE_PINS.items():
        raw = payloads[name]
        require(type(raw) is bytes and 0 < len(raw) <= MAX_SOURCE, "source bytes bound: " + name)
        require(dict(bytes=len(raw), sha256=sha(raw)) == pin, "original pin differs: " + name)


def load_sources(original):
    original = no_links(Path(original)).resolve(strict=True)
    require(original.is_dir() and not original.is_relative_to(ROOT / "local"), "read-only original root outside local required")
    payloads = {}
    for name in SOURCE_PINS:
        path = no_links(original / name)
        require(path.is_file() and path.stat().st_size <= MAX_SOURCE, "source file size/type")
        with path.open("rb") as stream:
            payloads[name] = stream.read(MAX_SOURCE + 1)
    verify_sources(payloads)
    return payloads


def validate_bytecode(payloads):
    # parse_pyc returns ordinary dictionaries, lists and bytes, never executable
    # Python code objects. No marshal.load/import of any original module.
    nation = parse_pyc(payloads["res/scripts/common/nations.pyc"])
    require([n.encode() for n in NATIONS] in nation["consts"] and b"NAMES" in nation["names"], "original nation IDs differ")
    items = parse_pyc(payloads["res/scripts/common/items/__init__.pyc"])
    item_names = [b"reserved", b"vehicle", b"vehicleChassis", b"vehicleTurret", b"vehicleGun", b"vehicleEngine", b"vehicleFuelTank", b"vehicleRadio", b"tankman", b"optionalDevice", b"shell", b"equipment"]
    require(item_names in items["consts"], "original item IDs differ")
    tree = parse_pyc(payloads["res/scripts/common/items/vehicles.pyc"])
    selected = {n.removeprefix("<module>."): r for n, r in records(tree) if n.removeprefix("<module>.") in METHOD_HASHES}
    require(set(selected) == set(METHOD_HASHES), "original methods missing")
    for name, r in selected.items():
        require(sha(r["code"]) == METHOD_HASHES[name], "original method body differs: " + name)
    table_path = ROOT / "local/vendor/cpython-2.7.3/opcode.py"
    opcode_raw = table_path.read_bytes()
    require(sha(opcode_raw) == "acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884", "opcode table differs")
    table = opcode_table(opcode_raw.decode("utf-8"))
    instructions = {name: {i["offset"]: i for i in disassemble(r, table)} for name, r in selected.items()}
    checks = []
    def op(method, offset, opname, value):
        i = instructions[method][offset]
        require(i["opname"] == opname and i.get("value", i.get("arg")) == value, "source instruction differs")
        checks.append(dict(method=method, offset=offset, opname=opname, value=value))
    op("_readGun", 1267, "LOAD_CONST", [1, 0.0])
    op("_readGun", 1273, "LOAD_CONST", "clip")
    op("_readGun", 1276, "STORE_SUBSCR", None)
    op("_readGunClipBurst", 28, "LOAD_CONST", 60.0)
    op("_readGunClipBurst", 53, "BINARY_DIVIDE", None)
    op("_readShot", 179, "LOAD_FAST", "projectileSpeedFactor")
    op("_readShot", 182, "BINARY_MULTIPLY", None)
    op("_readShot", 205, "LOAD_FAST", "projectileSpeedFactor")
    op("_readShot", 208, "LOAD_CONST", 2)
    op("_readShot", 211, "BINARY_POWER", None)
    op("_readShot", 212, "BINARY_MULTIPLY", None)
    return dict(method_code_sha256=METHOD_HASHES, instruction_assertions=checks,
                original_nation_ids=dict(enumerate(NATIONS)), original_item_types={"gun": 4, "shell": 10}, client_bytecode_executed=False)


def build(payloads):
    verify_sources(payloads)  # Reject tampering before any data/bytecode parse.
    audit = validate_bytecode(payloads)
    flats = {p: dict(walk(decode(raw, max_bytes=MAX_SOURCE, max_depth=32, max_nodes=30000))) for p, raw in payloads.items() if p.endswith((".xml", ".def"))}
    common = flats[PREFIX + "common/vehicle.xml"]
    factor = bounded_number(common["/miscParams[1]/projectileSpeedFactor[1]"], "projectile factor", 1)
    require(factor == 0.8, "pinned projectile factor differs")
    mounts = []
    all_compact = set()
    for key, nation, vehicle, filename, turret, gun, capacity, reload, clip_count, interval, shells in MOUNTS:
        nf = NATIONS.index(nation)
        source = PREFIX + nation + "/"
        vf, gf, sf = (flats[source + name] for name in (filename + ".xml", "components/guns.xml", "components/shells.xml"))
        path = "/turrets0[1]/" + turret + "[1]/guns[1]/" + gun + "[1]"
        shared = "/shared[1]/" + gun + "[1]"
        require(vf[path] == "shared", "selected mounted source inheritance differs")
        require(not any(p.startswith(path + "/shots[") for p in vf), "unexpected mounted shot override")
        mounted = lambda field: vf.get(path + "/" + field + "[1]", gf.get(shared + "/" + field + "[1]"))
        require(integer(mounted("maxAmmo"), "capacity", 2000) == capacity and bounded_number(mounted("reloadTime"), "reload", 600) == reload, "mounted capacity/reload differs")
        has_clip = mounted("clip") is not None
        if has_clip:
            count = integer(vf.get(path + "/clip[1]/count[1]", gf.get(shared + "/clip[1]/count[1]")), "clip count", 10)
            rate = bounded_number(vf.get(path + "/clip[1]/rate[1]", gf.get(shared + "/clip[1]/rate[1]")), "clip rate", 1000)
            actual_interval = 60.0 / rate if count > 1 else 0.0
        else:
            count, rate, actual_interval = 1, None, 0.0
        require((count, actual_interval) == (clip_count, interval), "historical mounted clip differs")
        require(mounted("burst") is None, "unexpected automatic burst")
        gun_id = integer(gf["/ids[1]/" + gun + "[1]"], "gun ID", 255, zero=True)
        vehicle_id = integer(flats[source + "list.xml"]["/" + vehicle + "[1]/id[1]"], "vehicle ID", 255, zero=True)
        shots_prefix = shared + "/shots[1]/"
        found = tuple(p[len(shots_prefix):-3] for p in gf if p.startswith(shots_prefix) and p.count("/") == 4)
        require(found == shells, "exact original shot order differs")
        shots = []
        for index, shell in enumerate(shells):
            sp, shot = "/" + shell + "[1]", shots_prefix + shell + "[1]"
            family = sf[sp + "/kind[1]"]
            require(family in FAMILIES, "closed original shell family")
            item_id = integer(sf[sp + "/id[1]"], "shell ID", 255, zero=True)
            compact = (item_id << 8) + (nf << 4) + 10
            require(compact not in all_compact, "duplicate selected compact ID")
            all_compact.add(compact)
            radius_value = sf.get(sp + "/explosionRadius[1]")
            radius = None if radius_value is None else bounded_number(radius_value, "explosion radius", 100)
            require((radius is not None) == (family == "HIGH_EXPLOSIVE"), "HE radius presence differs")
            speed = bounded_number(gf[shot + "/speed[1]"], "raw speed", 5000)
            gravity = bounded_number(gf[shot + "/gravity[1]"], "raw gravity", 100, zero=True)
            require(gravity == 9.81, "selected original gravity differs")
            shell_row = dict(index=index, resource=shell, item_id=item_id, compact_descr=compact, family=family,
                caliber_mm=bounded_number(sf[sp + "/caliber[1]"], "caliber", 400),
                damage_hp=integer(sf[sp + "/damage[1]/armor[1]"], "damage", 5000),
                device_damage=integer(sf[sp + "/damage[1]/devices[1]"], "device damage", 1000),
                penetration_mm=pair(gf[shot + "/piercingPower[1]"], "penetration"), explosion_radius_m=radius,
                raw_speed_mps=speed, projectile_speed_factor=factor, speed_mps=speed * factor,
                raw_gravity_mps2=gravity, gravity_mps2=gravity * factor ** 2,
                max_distance_m=bounded_number(gf[shot + "/maxDistance[1]"], "max distance", 10000),
                premium_gold_flag=sp + "/price[1]/gold[1]" in sf, effects_resource=sf[sp + "/effects[1]"],
                piercing_power_loss_factor_by_distance=None if sp + "/piercingPowerLossFactorByDistance[1]" not in sf else bounded_number(sf[sp + "/piercingPowerLossFactorByDistance[1]"], "HEAT loss field", 1, zero=True),
                shell_source_path=source + "components/shells.xml:" + sp, shot_source_path=source + "components/guns.xml:" + shot)
            shots.append(shell_row)
        mounts.append(dict(id=key, nation=nation, native_nation_id=nf, vehicle_resource=vehicle,
            vehicle_type_compact_descr=(vehicle_id << 8) + (nf << 4) + 1,
            gun_resource=gun, gun_compact_descr=(gun_id << 8) + (nf << 4) + 4,
            max_ammo=capacity, reload_seconds=reload, clip_count=count, clip_interval_seconds=actual_interval,
            clip_rate_per_minute=rate, clip_source="MOUNTED" if has_clip else "ORIGINAL_LOADER_DEFAULT",
            burst_count=1, burst_interval_seconds=0., mount_source_path=source + filename + ".xml:" + path,
            future_vehicle_physics_admitted=False if key.startswith(("wt-", "fv")) else None,
            new_battle_admission=False, shots=shots))
    result = dict(schema=SCHEMA, classification="VERIFIED_STATIC_ORIGINAL_717_DATA_ONLY", source_pins=SOURCE_PINS,
        source_revision="p06t-shells-717:" + sha(canonical(dict(pins=SOURCE_PINS, mounts=MOUNTS, methods=METHOD_HASHES))),
        audit=audit, mounts=mounts, runtime_registration=False, native_ui="NOT_RUN",
        unknowns=["historical server HE splash and screen solver", "server APCR/HEAT layer rules and RNG order",
                  "internal module and crew hit volumes", "source accurate critical/fire threshold and chance order",
                  "native partial clip reload server convention", "WT/FV physics and owned-admission qualification",
                  "versioned UK account catalogue correction to original nationID5"])
    require(len(mounts) == 8 and len(all_compact) == 24 and len(canonical(result)) <= MAX_EXPORT, "closed output bounds")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = no_links(args.out).resolve()
    stage = ROOT / "local"
    require(out.is_relative_to(stage) and not out.exists(), "fresh output inside owned local required")
    result = build(load_sources(args.original))
    out.mkdir(parents=True, exist_ok=False)
    raw = canonical(result) + b"\n"
    (out / "shell-catalog.json").write_bytes(raw)
    receipt = dict(schema="p06t-shell-source-audit.v1", status="PASS_STATIC_SOURCE", source_files=len(SOURCE_PINS),
        source_bytes=sum(p["bytes"] for p in SOURCE_PINS.values()), mounts=8, shells=24,
        data_sha256=sha(raw), data_bytes=len(raw), source_revision=result["source_revision"],
        original_bytecode_executed=False, runtime_registered=False, native="NOT_RUN")
    (out / "result.json").write_bytes(canonical(receipt) + b"\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()
